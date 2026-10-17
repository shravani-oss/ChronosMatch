"""Baseline benchmark: how fast is the pure-Python reference order book?

Run from the repo root:  python benchmarks/bench_reference_book.py
Writes benchmarks/results/reference_book.json. This is the number the Cython engine must beat.
"""

import json
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronosmatch.order_generator import generate_orders  # noqa: E402
from chronosmatch.reference_book import ReferenceOrderBook  # noqa: E402

ORDER_COUNT = 20_000
SEED = 0
WARMUP_RUNS = 1
MEASURED_RUNS = 5
RESULT_PATH = Path(__file__).parent / "results" / "reference_book.json"


def run_once(orders: list) -> tuple[int, int]:
    """Submit all orders to a fresh book; return (elapsed_ns, trade_count)."""
    book = ReferenceOrderBook()
    trades = 0
    start = time.perf_counter_ns()
    for order in orders:
        trades += len(book.submit(order))
    return time.perf_counter_ns() - start, trades


def per_order_latencies_ns(orders: list) -> list[int]:
    book = ReferenceOrderBook()
    samples = []
    for order in orders:
        start = time.perf_counter_ns()
        book.submit(order)
        samples.append(time.perf_counter_ns() - start)
    return samples


def main() -> None:
    orders = list(generate_orders(ORDER_COUNT, seed=SEED))  # generation is not timed

    for _ in range(WARMUP_RUNS):
        run_once(orders)

    runs = [run_once(orders) for _ in range(MEASURED_RUNS)]
    rates = [ORDER_COUNT / (ns / 1e9) for ns, _ in runs]

    latencies_us = [ns / 1_000 for ns in per_order_latencies_ns(orders)]
    cuts = statistics.quantiles(latencies_us, n=100)

    result = {
        "order_count": ORDER_COUNT,
        "seed": SEED,
        "warmup_runs": WARMUP_RUNS,
        "measured_runs": MEASURED_RUNS,
        "trades_per_run": runs[0][1],
        "orders_per_sec_median": round(statistics.median(rates)),
        "orders_per_sec_min": round(min(rates)),
        "orders_per_sec_max": round(max(rates)),
        "latency_us": {
            "p50": round(cuts[49], 2),
            "p99": round(cuts[98], 2),
            "max": round(max(latencies_us), 2),
        },
        "python": platform.python_version(),
        "machine": platform.platform(),
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
