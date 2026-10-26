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
import sys
import time
from array import array
from dataclasses import asdict, dataclass

from chronosmatch import config
from chronosmatch.cython_book import CythonOrderBook
from chronosmatch.no_pickle import forbid_pickle
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.telemetry import Snapshot, TelemetryBlock
from chronosmatch.types import Side

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


def _publish(
    telemetry: TelemetryBlock,
    book: CythonOrderBook,
    processed: int,
    count: int,
    latencies: array,
    orders_per_sec: int,
    done: bool,
) -> None:
    """Write a dashboard snapshot. Called rarely (about every 100 ms), outside the per-order path."""
    recent = sorted(latencies[max(0, processed - config.TELEMETRY_LATENCY_SAMPLE) : processed])
    p50 = recent[len(recent) // 2] if recent else 0
    p99 = recent[min(len(recent) - 1, int(len(recent) * 0.99))] if recent else 0
    trades, traded_qty, _, _ = book.trade_stats
    telemetry.publish(
        Snapshot(
            processed=processed, trades=trades, traded_qty=traded_qty,
            best_bid=book.best_bid, best_ask=book.best_ask, updated_ns=time.perf_counter_ns(),
            orders_per_sec=orders_per_sec, latency_p50_ns=p50, latency_p99_ns=p99,
            target_count=count, done=done,
            bids=book.top_levels(Side.BUY, config.TELEMETRY_DEPTH),
            asks=book.top_levels(Side.SELL, config.TELEMETRY_DEPTH),
        )
    )


def run_engine(
    ring: RingBuffer,
    book: CythonOrderBook,
    count: int,
    timeout_s: float = _TIMEOUT_S,
    telemetry: TelemetryBlock | None = None,
) -> EngineResult:
    """Pop and match exactly `count` orders; raise TimeoutError if they stop arriving.

    With `telemetry`, a dashboard snapshot is published at most every TELEMETRY_INTERVAL_NS,
    checked once every TELEMETRY_CHECK_EVERY orders so the per-order cost stays tiny.
    """
    pop = ring.try_pop_raw
    submit = book.submit_raw
    clock = time.perf_counter_ns
    buy_code = config.SIDE_CODE_BUY
    latencies = array("q", bytes(8 * count))  # preallocated C int64 array, not a Python list

    processed = 0
    start = 0
    deadline = time.monotonic() + timeout_s
    check_every = config.TELEMETRY_CHECK_EVERY
    last_pub_ns = clock()
    last_pub_count = 0
    if telemetry is not None:
        _publish(telemetry, book, 0, count, latencies, 0, done=False)
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
        if telemetry is not None and processed % check_every == 0:
            now = clock()
            if now - last_pub_ns >= config.TELEMETRY_INTERVAL_NS:
                rate = (processed - last_pub_count) * config.NS_PER_SEC // (now - last_pub_ns)
                _publish(telemetry, book, processed, count, latencies, rate, done=False)
                last_pub_ns, last_pub_count = now, processed
    elapsed = clock() - start
    if telemetry is not None:
        overall = processed * config.NS_PER_SEC // elapsed if elapsed else 0
        _publish(telemetry, book, processed, count, latencies, overall, done=True)

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
    parser.add_argument("--telemetry", help="telemetry file created by TelemetryBlock.create")
    args = parser.parse_args(argv)
    if args.forbid_pickle:
        forbid_pickle()

    telemetry = TelemetryBlock.attach(args.telemetry) if args.telemetry else None
    try:
        with RingBuffer.attach(args.ring) as ring:
            result = run_engine(ring, CythonOrderBook(), args.count, telemetry=telemetry)
    finally:
        if telemetry is not None:
            telemetry.close()
    print(json.dumps(asdict(result)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
