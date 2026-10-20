"""Firehose throughput as a separate process: unlimited, and against the 100k/sec target.

Run from the repo root:  python benchmarks/bench_firehose.py
Writes benchmarks/results/firehose.json.

The firehose runs via its CLI (`python -m chronosmatch.firehose`) in its own process, exactly
as in the demo. Its reported rate *includes* generating each Order (realistic for a simulator).
This process drains the ring concurrently so the firehose is not blocked by a full buffer.
"""

import json
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from chronosmatch import config  # noqa: E402
from chronosmatch.ring_buffer import RingBuffer  # noqa: E402

ORDER_COUNT = 500_000
MEASURED_RUNS = 3
RESULT_PATH = Path(__file__).parent / "results" / "firehose.json"
_RATE_RE = re.compile(r"rate=([\d,]+)/s full_waits=(\d+)")


def run_once(rate: int) -> tuple[float, int]:
    """Return (orders_per_sec reported by the firehose, full_waits)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bench.ring"
        with RingBuffer.create(path, config.RING_DEFAULT_CAPACITY) as ring:
            proc = subprocess.Popen(
                [sys.executable, "-m", "chronosmatch.firehose", "--ring", str(path),
                 "--count", str(ORDER_COUNT), "--rate", str(rate)],
                env={**os.environ, "PYTHONPATH": str(SRC_DIR)},
                stdout=subprocess.PIPE, text=True,
            )
            received = 0
            while received < ORDER_COUNT:
                if ring.try_pop() is not None:
                    received += 1
            out, _ = proc.communicate()
    match = _RATE_RE.search(out)
    if proc.returncode != 0 or match is None:
        raise RuntimeError(f"firehose failed: {out!r}")
    return float(match.group(1).replace(",", "")), int(match.group(2))


def measure(rate: int) -> dict:
    runs = [run_once(rate) for _ in range(MEASURED_RUNS)]
    rates = [r for r, _ in runs]
    return {
        "requested_rate": rate or "unlimited",
        "orders_per_sec_median": round(statistics.median(rates)),
        "orders_per_sec_min": round(min(rates)),
        "orders_per_sec_max": round(max(rates)),
        "full_waits_per_run": [w for _, w in runs],
    }


def main() -> None:
    result = {
        "order_count": ORDER_COUNT,
        "measured_runs": MEASURED_RUNS,
        "batch_size": config.FIREHOSE_BATCH_SIZE,
        "ring_capacity": config.RING_DEFAULT_CAPACITY,
        "unlimited": measure(0),
        "target_100k": measure(config.TARGET_ORDERS_PER_SEC),
        "python": platform.python_version(),
        "machine": platform.platform(),
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
