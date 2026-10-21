"""asyncio market firehose: pushes a stream of orders into the ring buffer at a target rate.

Each order is stamped with time.perf_counter_ns() as it enters the ring, so Week 3 can
measure end-to-end latency. Run as a separate process:

    python -m chronosmatch.firehose --ring /tmp/chronos.ring --count 1000000 --rate 100000

Why asyncio: the firehose yields to the event loop after every batch, so other coroutines in
the same process (a stats reporter, later a websocket feed) can run without threads.
"""

import argparse
import asyncio
import time
from collections.abc import Iterable
from dataclasses import dataclass

from chronosmatch import config
from chronosmatch.no_pickle import forbid_pickle
from chronosmatch.order_generator import generate_orders
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.types import Order


@dataclass(frozen=True)
class FirehoseStats:
    sent: int
    full_waits: int  # times the ring was full and we had to wait (backpressure)
    elapsed_ns: int

    @property
    def orders_per_sec(self) -> float:
        return self.sent / (self.elapsed_ns / config.NS_PER_SEC) if self.elapsed_ns else 0.0


async def run_firehose(
    ring: RingBuffer,
    orders: Iterable[Order],
    target_rate: int | None = config.TARGET_ORDERS_PER_SEC,
    batch_size: int = config.FIREHOSE_BATCH_SIZE,
) -> FirehoseStats:
    """Push every order into `ring`. `target_rate=None` means as fast as possible."""
    if target_rate is not None and target_rate <= 0:
        raise ValueError(f"target_rate must be positive or None, got {target_rate}")
    if batch_size <= 0:
        raise ValueError(f"batch_size must be positive, got {batch_size}")

    sent = 0
    full_waits = 0
    start = time.perf_counter_ns()
    for order in orders:
        while not ring.try_push(order, time.perf_counter_ns()):
            full_waits += 1
            await asyncio.sleep(0)  # ring full: let other tasks (e.g. a consumer) run
        sent += 1

        if sent % batch_size == 0:
            delay_s = 0.0
            if target_rate is not None:
                due_ns = start + sent * config.NS_PER_SEC // target_rate
                delay_s = (due_ns - time.perf_counter_ns()) / config.NS_PER_SEC
            await asyncio.sleep(max(0.0, delay_s))  # ahead of schedule: wait; else just yield

    return FirehoseStats(sent, full_waits, time.perf_counter_ns() - start)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Blast mock orders into a ChronosMatch ring.")
    parser.add_argument("--ring", required=True, help="path of a ring created by RingBuffer.create")
    parser.add_argument("--count", type=int, default=config.MID_REVIEW_ORDER_COUNT)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--rate", type=int, default=config.TARGET_ORDERS_PER_SEC, help="orders/sec, 0 = unlimited"
    )
    parser.add_argument("--batch", type=int, default=config.FIREHOSE_BATCH_SIZE)
    parser.add_argument(
        "--forbid-pickle", action="store_true", help="make any use of pickle raise (proof mode)"
    )
    args = parser.parse_args(argv)
    if args.forbid_pickle:
        forbid_pickle()

    with RingBuffer.attach(args.ring) as ring:
        stats = asyncio.run(
            run_firehose(ring, generate_orders(args.count, args.seed), args.rate or None, args.batch)
        )
    print(
        f"sent={stats.sent} elapsed_ms={stats.elapsed_ns / 1e6:.1f} "
        f"rate={stats.orders_per_sec:,.0f}/s full_waits={stats.full_waits}"
    )


if __name__ == "__main__":
    main()
