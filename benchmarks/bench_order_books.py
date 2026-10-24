"""Matching speed: pure-Python reference book vs Cython book (two APIs).

Run from the repo root (after `python setup.py build_ext --inplace`):
    python benchmarks/bench_order_books.py
Writes benchmarks/results/order_books.json.

Modes:
- reference      ReferenceOrderBook.submit(Order) -> list[Trade]
- cython_submit  CythonOrderBook.submit(Order)    -> list[Trade]  (same API as reference)
- cython_raw     CythonOrderBook.submit_raw(ints) -> trade count  (no Order/Trade objects)
The same seeded orders are used for every mode; generating them is not timed. Book construction
is not timed. The Python `for` loop that feeds the book is timed in every mode.
"""

import json
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronosmatch.cython_book import CythonOrderBook  # noqa: E402
from chronosmatch.order_generator import generate_orders  # noqa: E402
from chronosmatch.reference_book import ReferenceOrderBook  # noqa: E402
from chronosmatch.types import Side  # noqa: E402

SMALL_COUNT = 20_000      # same as the 17 Oct baseline, so numbers are comparable
LARGE_COUNT = 1_000_000   # Cython modes only; the reference book would take minutes
SEED = 0
WARMUP_RUNS = 1
MEASURED_RUNS = 5
RESULT_PATH = Path(__file__).parent / "results" / "order_books.json"


def run_objects(make_book, orders) -> tuple[int, int]:
    book = make_book()
    submit = book.submit
    trades = 0
    start = time.perf_counter_ns()
    for order in orders:
        trades += len(submit(order))
    return time.perf_counter_ns() - start, trades


def run_raw(rows) -> tuple[int, int]:
    book = CythonOrderBook()
    submit_raw = book.submit_raw
    trades = 0
    start = time.perf_counter_ns()
    for is_buy, order_id, price, qty in rows:
        trades += submit_raw(is_buy, order_id, price, qty)
    return time.perf_counter_ns() - start, trades


def throughput(fn, count: int) -> dict:
    for _ in range(WARMUP_RUNS):
        fn()
    runs = [fn() for _ in range(MEASURED_RUNS)]
    trade_counts = {t for _, t in runs}
    assert len(trade_counts) == 1, "runs disagree on trade count"
    rates = [count / (ns / 1e9) for ns, _ in runs]
    return {
        "orders_per_sec_median": round(statistics.median(rates)),
        "orders_per_sec_min": round(min(rates)),
        "orders_per_sec_max": round(max(rates)),
        "trades_per_run": trade_counts.pop(),
    }


def timer_overhead_ns(samples: int = 200_000) -> float:
    deltas = []
    for _ in range(samples):
        a = time.perf_counter_ns()
        deltas.append(time.perf_counter_ns() - a)
    return statistics.median(deltas)


def latency_us(submit_one, items) -> dict:
    samples = []
    for item in items:
        start = time.perf_counter_ns()
        submit_one(item)
        samples.append(time.perf_counter_ns() - start)
    cuts = statistics.quantiles(samples, n=100)
    return {"p50": round(cuts[49] / 1e3, 3), "p99": round(cuts[98] / 1e3, 3), "max": round(max(samples) / 1e3, 3)}


def main() -> None:
    small = list(generate_orders(SMALL_COUNT, seed=SEED))
    small_rows = [(o.side is Side.BUY, o.order_id, o.price, o.quantity) for o in small]
    large = list(generate_orders(LARGE_COUNT, seed=SEED))
    large_rows = [(o.side is Side.BUY, o.order_id, o.price, o.quantity) for o in large]

    small_results = {
        "reference": throughput(lambda: run_objects(ReferenceOrderBook, small), SMALL_COUNT),
        "cython_submit": throughput(lambda: run_objects(CythonOrderBook, small), SMALL_COUNT),
        "cython_raw": throughput(lambda: run_raw(small_rows), SMALL_COUNT),
    }
    large_results = {
        "cython_submit": throughput(lambda: run_objects(CythonOrderBook, large), LARGE_COUNT),
        "cython_raw": throughput(lambda: run_raw(large_rows), LARGE_COUNT),
    }
    base = small_results["reference"]["orders_per_sec_median"]
    for entry in small_results.values():
        entry["speedup_vs_reference"] = round(entry["orders_per_sec_median"] / base, 1)

    ref_book, cy_book, raw_book = ReferenceOrderBook(), CythonOrderBook(), CythonOrderBook()
    latency = {
        "timer_overhead_ns_median": timer_overhead_ns(),
        "reference": latency_us(ref_book.submit, small),
        "cython_submit": latency_us(cy_book.submit, small),
        "cython_raw": latency_us(lambda r: raw_book.submit_raw(*r), small_rows),
    }

    result = {
        "seed": SEED,
        "warmup_runs": WARMUP_RUNS,
        "measured_runs": MEASURED_RUNS,
        f"throughput_{SMALL_COUNT}_orders": small_results,
        f"throughput_{LARGE_COUNT}_orders": large_results,
        f"latency_us_{SMALL_COUNT}_orders": latency,
        "python": platform.python_version(),
        "machine": platform.platform(),
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
