"""Matching engine process: reads orders from the shared ring and matches them in the Cython book.

    python -m chronosmatch.engine --ring /tmp/chronos.ring --count 1000000 --forbid-pickle

The loop uses only plain integers (`try_pop_raw` -> `submit_raw`): no Order or Trade objects.
Each order's entry timestamp (stamped by the firehose) is compared with the time right after
matching, giving end-to-end latency: queueing in the ring + matching.
At the end it prints one JSON line with the results. JSON is fine here: it is a single small
summary after the run, not the order data path.
"""

import argparse
import json
import statistics
import sys
import time
from array import array
from dataclasses import asdict, dataclass

from chronosmatch import config
from chronosmatch.cython_book import CythonOrderBook
from chronosmatch.no_pickle import forbid_pickle
from chronosmatch.ring_buffer import RingBuffer

_TIMEOUT_S = 300.0


@dataclass(frozen=True)
class EngineResult:
    processed: int
    elapsed_ns: int
    trade_stats: tuple[int, int, int, int]
    latency_p50_us: float
    latency_p99_us: float
    latency_max_us: float
    best_bid: int | None
    best_ask: int | None

    @property
    def orders_per_sec(self) -> float:
        return self.processed / (self.elapsed_ns / config.NS_PER_SEC) if self.elapsed_ns else 0.0


def run_engine(ring: RingBuffer, book: CythonOrderBook, count: int, timeout_s: float = _TIMEOUT_S) -> EngineResult:
    """Pop and match exactly `count` orders; raise TimeoutError if they stop arriving."""
    pop = ring.try_pop_raw
    submit = book.submit_raw
    clock = time.perf_counter_ns
    buy_code = config.SIDE_CODE_BUY
    latencies = array("q", bytes(8 * count))  # preallocated C int64 array, not a Python list

    processed = 0
    start = 0
    deadline = time.monotonic() + timeout_s
    while processed < count:
        item = pop()
        if item is None:
            if time.monotonic() > deadline:
                raise TimeoutError(f"engine received {processed} of {count} orders")
            continue
        order_id, entry_ns, price, quantity, side_code = item
        if processed == 0:
            start = clock()
        submit(side_code == buy_code, order_id, price, quantity)
        latencies[processed] = clock() - entry_ns
        processed += 1
    elapsed = clock() - start

    ordered = sorted(latencies)
    pick = lambda q: ordered[min(count - 1, int(q * count))] / 1_000  # noqa: E731
    return EngineResult(
        processed=processed,
        elapsed_ns=elapsed,
        trade_stats=book.trade_stats,
        latency_p50_us=round(pick(0.50), 3) if count else 0.0,
        latency_p99_us=round(pick(0.99), 3) if count else 0.0,
        latency_max_us=round(ordered[-1] / 1_000, 3) if count else 0.0,
        best_bid=book.best_bid,
        best_ask=book.best_ask,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ChronosMatch matching engine process.")
    parser.add_argument("--ring", required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--forbid-pickle", action="store_true")
    args = parser.parse_args(argv)
    if args.forbid_pickle:
        forbid_pickle()

    with RingBuffer.attach(args.ring) as ring:
        result = run_engine(ring, CythonOrderBook(), args.count)
    print(json.dumps(asdict(result)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
