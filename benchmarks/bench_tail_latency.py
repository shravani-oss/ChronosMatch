"""Week 3 investigation: where do the engine's tail-latency spikes come from?

Run from the repo root:  python benchmarks/bench_tail_latency.py
Writes benchmarks/results/tail_latency.json.

Experiment A (GC hypothesis): the full pipeline at 100k orders/s, several runs with the engine's
cyclic GC on vs off (`--gc off` = gc.freeze() + gc.disable()). Records p50/p99/p99.9/max latency
and how many GC collections happened in the engine.

Experiment B (OS-scheduling hypothesis): a "hiccup meter" that only reads the clock in a tight
loop and records every gap. A busy loop should see gaps of well under a microsecond; anything
longer means the process was not running (OS preemption, interrupts, timer coalescing). Run alone,
then while the pipeline is running in *separate processes*. (A first version ran the pipeline in a
thread of this process; the meter then measured ~6.3 ms GIL hand-offs between the two threads,
not the OS. Lesson: the meter must be alone in its interpreter.)
"""

import json
import os
import subprocess
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronosmatch.demo_pipeline import run_pipeline  # noqa: E402

ORDER_COUNT = 300_000
RATE = 100_000
RUNS_PER_MODE = 5
HICCUP_SECONDS = 5.0
HICCUP_THRESHOLDS_US = (10, 100, 1_000)
RESULT_PATH = Path(__file__).parent / "results" / "tail_latency.json"


def pipeline_run(gc_mode: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_pipeline(Path(tmp) / "t.ring", ORDER_COUNT, 0, RATE, 65_536, False,
                              engine_args=("--gc", gc_mode))
    if not result.ok:
        raise RuntimeError(f"pipeline failed: {result}")
    e = result.engine
    return {k: e[k] for k in ("latency_p50_us", "latency_p99_us", "latency_p999_us", "latency_max_us")} | {
        "gc_collections": e["gc"]["collections"], "gc_max_pause_us": e["gc"]["max_pause_us"],
    }


def experiment_a() -> dict:
    # Interleave modes (on, off, on, off, ...) so slow drift in machine state (background load,
    # CPU frequency) affects both modes equally. A first version ran all "on" runs first.
    by_mode: dict[str, list[dict]] = {"on": [], "off": []}
    for _ in range(RUNS_PER_MODE):
        for mode in ("on", "off"):
            by_mode[mode].append(pipeline_run(mode))
    out = {}
    for mode, runs in by_mode.items():
        out[f"gc_{mode}"] = {
            "runs": runs,
            "median_p99_us": statistics.median(r["latency_p99_us"] for r in runs),
            "median_p999_us": statistics.median(r["latency_p999_us"] for r in runs),
            "median_max_us": statistics.median(r["latency_max_us"] for r in runs),
            "total_gc_collections": [sum(r["gc_collections"][g] for r in runs) for g in range(3)],
        }
    return out


def hiccups(seconds: float) -> dict:
    """Spin reading the clock; report gaps between consecutive reads."""
    clock = time.perf_counter_ns
    end = clock() + int(seconds * 1e9)
    counts = dict.fromkeys(HICCUP_THRESHOLDS_US, 0)
    biggest: list[int] = []
    loops = 0
    prev = clock()
    while prev < end:
        now = clock()
        gap = now - prev
        if gap > 10_000:
            for t in HICCUP_THRESHOLDS_US:
                if gap > t * 1_000:
                    counts[t] += 1
            biggest.append(gap)
        prev = now
        loops += 1
    biggest.sort(reverse=True)
    return {
        "seconds": seconds,
        "loop_iterations": loops,
        **{f"gaps_over_{t}us": counts[t] for t in HICCUP_THRESHOLDS_US},
        "largest_gaps_us": [round(g / 1_000, 1) for g in biggest[:5]],
    }


def experiment_b() -> dict:
    alone = hiccups(HICCUP_SECONDS)
    # The pipeline runs as its own processes (demo + firehose + engine); this process only meters.
    src = str(Path(__file__).resolve().parents[1] / "src")
    pipeline = subprocess.Popen(
        [sys.executable, "-m", "chronosmatch.demo_pipeline", "--count", "800000", "--rate", str(RATE)],
        env={**os.environ, "PYTHONPATH": src}, stdout=subprocess.PIPE, text=True,
    )
    time.sleep(1.0)  # let the processes start and the firehose begin pacing
    busy = hiccups(HICCUP_SECONDS)
    out, _ = pipeline.communicate()
    if "RESULT    : PASS" not in out:
        raise RuntimeError(f"pipeline failed during experiment B: {out}")
    return {"meter_alone": alone, "meter_while_pipeline_runs": busy}


def main() -> None:
    result = {
        "order_count": ORDER_COUNT,
        "rate": RATE,
        "runs_per_mode": RUNS_PER_MODE,
        "experiment_a_gc": experiment_a(),
        "experiment_b_os_hiccups": experiment_b(),
        "python": platform.python_version(),
        "machine": platform.platform(),
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
