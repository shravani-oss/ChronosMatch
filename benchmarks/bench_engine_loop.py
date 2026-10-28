"""Week 3: engine loop in Python vs in C (Cython `consume_ring`).

Run from the repo root:  python benchmarks/bench_engine_loop.py
Writes benchmarks/results/engine_loop.json.

A. Engine capacity: the ring is pre-filled with 1M orders (so the firehose cannot be the
   bottleneck), then one loop drains and matches them. Same process, runs interleaved.
B. Pipeline at 100k orders/s (firehose and engine as separate processes), runs interleaved:
   latency percentiles, plus the C loop's own pause measurements (gaps between iterations).
"""

import json
import platform
import statistics
import sys
import tempfile
import time
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronosmatch.cython_book import CythonOrderBook  # noqa: E402
from chronosmatch.demo_pipeline import run_pipeline  # noqa: E402
from chronosmatch.engine import run_engine  # noqa: E402
from chronosmatch.order_generator import generate_orders  # noqa: E402
from chronosmatch.ring_buffer import RingBuffer  # noqa: E402

CAPACITY_ORDERS = 1_000_000
CAPACITY_RING = 1 << 20
CAPACITY_RUNS = 3
PIPELINE_ORDERS = 300_000
PIPELINE_RATE = 100_000
PIPELINE_RUNS = 5
RESULT_PATH = Path(__file__).parent / "results" / "engine_loop.json"


def capacity_run(orders: list, loop: str) -> tuple[float, tuple]:
    with tempfile.TemporaryDirectory() as tmp, RingBuffer.create(Path(tmp) / "c.ring", CAPACITY_RING) as ring:
        stamp = time.perf_counter_ns()
        for o in orders:
            ring.try_push(o, stamp)
        result = run_engine(ring, CythonOrderBook(), len(orders), loop=loop)
    return result.orders_per_sec, result.trade_stats


def experiment_a() -> dict:
    orders = list(generate_orders(CAPACITY_ORDERS, seed=0))
    rates: dict[str, list[float]] = {"python": [], "c": []}
    stats = set()
    for _ in range(CAPACITY_RUNS):
        for loop in ("python", "c"):
            rate, trade_stats = capacity_run(orders, loop)
            rates[loop].append(rate)
            stats.add(trade_stats)
    assert len(stats) == 1, "loops disagree on trades"
    out = {loop: {"orders_per_sec_median": round(statistics.median(r)),
                  "orders_per_sec_runs": [round(x) for x in r]} for loop, r in rates.items()}
    out["speedup_c_vs_python"] = round(out["c"]["orders_per_sec_median"] / out["python"]["orders_per_sec_median"], 2)
    return out


def pipeline_run(loop: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        r = run_pipeline(Path(tmp) / "p.ring", PIPELINE_ORDERS, 0, PIPELINE_RATE, 65_536, False,
                         engine_args=("--loop", loop))
    if not r.ok:
        raise RuntimeError(f"pipeline failed: {r}")
    e = r.engine
    run = {k: e[k] for k in ("latency_p50_us", "latency_p99_us", "latency_p999_us", "latency_max_us")}
    if e["loop_pauses"]:
        run["loop_pauses"] = e["loop_pauses"]
    return run


def experiment_b() -> dict:
    runs: dict[str, list[dict]] = {"python": [], "c": []}
    for _ in range(PIPELINE_RUNS):
        for loop in ("python", "c"):
            runs[loop].append(pipeline_run(loop))
    out = {}
    for loop, rs in runs.items():
        out[loop] = {
            "runs": rs,
            **{f"median_{k[8:]}": statistics.median(r[k] for r in rs)
               for k in ("latency_p50_us", "latency_p99_us", "latency_p999_us", "latency_max_us")},
        }
    return out


def main() -> None:
    result = {
        "experiment_a_engine_capacity": experiment_a(),
        "experiment_b_pipeline_100k": experiment_b(),
        "python": platform.python_version(),
        "machine": platform.platform(),
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
