"""Two-process throughput: mmap ring buffer vs multiprocessing.Queue (pickle).

Run from the repo root:  python benchmarks/bench_ipc.py
Writes benchmarks/results/ipc.json.

Method (same for both transports):
- The producer process generates all orders *before* timing starts, then signals "ready".
- The parent starts the clock, signals "go", and stops it when the last order is received.
- Process start-up and order generation are therefore excluded from the measurement.
"""

import json
import multiprocessing
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronosmatch import config  # noqa: E402
from chronosmatch.order_generator import generate_orders  # noqa: E402
from chronosmatch.ring_buffer import RingBuffer  # noqa: E402

ORDER_COUNT = 500_000
SEED = 0
MEASURED_RUNS = 3
RING_CAPACITY = config.RING_DEFAULT_CAPACITY
RESULT_PATH = Path(__file__).parent / "results" / "ipc.json"


def ring_producer(path: str, count: int, seed: int, ready, go) -> None:
    orders = list(generate_orders(count, seed=seed))
    with RingBuffer.attach(path) as ring:
        ready.set()
        go.wait()
        for order in orders:
            while not ring.try_push(order):
                pass


def queue_producer(queue, count: int, seed: int, ready, go) -> None:
    orders = list(generate_orders(count, seed=seed))
    ready.set()
    go.wait()
    for order in orders:
        queue.put(order)


def run_ring(ctx, count: int) -> float:
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "bench.ring")
        with RingBuffer.create(path, RING_CAPACITY) as ring:
            ready, go = ctx.Event(), ctx.Event()
            proc = ctx.Process(target=ring_producer, args=(path, count, SEED, ready, go))
            proc.start()
            ready.wait()
            start = time.perf_counter_ns()
            go.set()
            received = 0
            while received < count:
                if ring.try_pop() is not None:
                    received += 1
            elapsed = time.perf_counter_ns() - start
            proc.join()
    return count / (elapsed / 1e9)


def run_queue(ctx, count: int) -> float:
    queue = ctx.Queue()
    ready, go = ctx.Event(), ctx.Event()
    proc = ctx.Process(target=queue_producer, args=(queue, count, SEED, ready, go))
    proc.start()
    ready.wait()
    start = time.perf_counter_ns()
    go.set()
    for _ in range(count):
        queue.get()
    elapsed = time.perf_counter_ns() - start
    proc.join()
    return count / (elapsed / 1e9)


def summarise(rates: list[float]) -> dict:
    return {
        "orders_per_sec_median": round(statistics.median(rates)),
        "orders_per_sec_min": round(min(rates)),
        "orders_per_sec_max": round(max(rates)),
    }


def main() -> None:
    ctx = multiprocessing.get_context("spawn")
    ring_rates = [run_ring(ctx, ORDER_COUNT) for _ in range(MEASURED_RUNS)]
    queue_rates = [run_queue(ctx, ORDER_COUNT) for _ in range(MEASURED_RUNS)]
    ring, queue = summarise(ring_rates), summarise(queue_rates)
    result = {
        "order_count": ORDER_COUNT,
        "seed": SEED,
        "measured_runs": MEASURED_RUNS,
        "ring_capacity": RING_CAPACITY,
        "mmap_ring_buffer": ring,
        "multiprocessing_queue_pickle": queue,
        "speedup_median": round(ring["orders_per_sec_median"] / queue["orders_per_sec_median"], 2),
        "python": platform.python_version(),
        "machine": platform.platform(),
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
