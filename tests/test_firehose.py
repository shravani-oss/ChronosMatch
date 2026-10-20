"""Single-process tests for the asyncio firehose."""

import asyncio
import time
from pathlib import Path

import pytest

from chronosmatch.firehose import run_firehose
from chronosmatch.order_generator import generate_orders
from chronosmatch.ring_buffer import RingBuffer


@pytest.fixture
def ring(tmp_path: Path):
    with RingBuffer.create(tmp_path / "fh.ring", 1024) as r:
        yield r


def test_pushes_all_orders_in_order_with_timestamps(ring: RingBuffer) -> None:
    before = time.perf_counter_ns()
    stats = asyncio.run(run_firehose(ring, generate_orders(500, seed=1), target_rate=None))
    assert stats.sent == 500 and stats.full_waits == 0
    popped = [ring.try_pop() for _ in range(500)]
    assert [o for o, _ in popped] == list(generate_orders(500, seed=1))
    stamps = [ts for _, ts in popped]
    assert stamps == sorted(stamps) and stamps[0] >= before


def test_empty_stream(ring: RingBuffer) -> None:
    stats = asyncio.run(run_firehose(ring, [], target_rate=None))
    assert stats.sent == 0 and len(ring) == 0


def test_backpressure_with_concurrent_consumer(tmp_path: Path) -> None:
    """Ring of 8 slots, 2,000 orders, batch of 100: the ring fills before the firehose's
    scheduled yield, so it must wait for an asyncio consumer task in the same event loop.
    Proves the firehose yields when full instead of blocking the loop forever."""
    count = 2_000

    async def scenario(ring: RingBuffer):
        received = []

        async def consumer() -> None:
            while len(received) < count:
                item = ring.try_pop()
                if item is None:
                    await asyncio.sleep(0)
                else:
                    received.append(item[0])

        stats, _ = await asyncio.gather(
            run_firehose(ring, generate_orders(count, seed=2), target_rate=None, batch_size=100),
            consumer(),
        )
        return stats, received

    with RingBuffer.create(tmp_path / "small.ring", 8) as ring:
        stats, received = asyncio.run(scenario(ring))
    assert stats.full_waits > 0
    assert received == list(generate_orders(count, seed=2))


def test_rate_limit_slows_the_stream(ring: RingBuffer) -> None:
    """1,000 orders at 10,000/sec must take at least ~0.1 s."""
    stats = asyncio.run(
        run_firehose(ring, generate_orders(1_000, seed=3), target_rate=10_000, batch_size=100)
    )
    assert stats.elapsed_ns >= 0.09e9
    assert stats.orders_per_sec <= 11_000


@pytest.mark.parametrize("kwargs", [{"target_rate": 0}, {"target_rate": -5}, {"batch_size": 0}])
def test_invalid_arguments(ring: RingBuffer, kwargs: dict) -> None:
    with pytest.raises(ValueError):
        asyncio.run(run_firehose(ring, [], **kwargs))
