"""Single-process tests for the mmap ring buffer: empty, full, wrap-around, attach."""

from pathlib import Path

import pytest

from chronosmatch import config
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.types import Order, Side


def order(n: int) -> Order:
    return Order(n, Side.BUY if n % 2 else Side.SELL, 100 + n % 7, n % 50 + 1)


@pytest.fixture
def ring_path(tmp_path: Path) -> Path:
    return tmp_path / "test.ring"


@pytest.mark.parametrize("capacity", [0, -4, 3, 100])
def test_capacity_must_be_power_of_two(ring_path: Path, capacity: int) -> None:
    with pytest.raises(ValueError):
        RingBuffer.create(ring_path, capacity)


def test_file_size_is_header_plus_slots(ring_path: Path) -> None:
    with RingBuffer.create(ring_path, 8):
        pass
    assert ring_path.stat().st_size == config.RING_HEADER_SIZE + 8 * config.ORDER_RECORD_SIZE


def test_new_ring_is_empty(ring_path: Path) -> None:
    with RingBuffer.create(ring_path, 8) as ring:
        assert len(ring) == 0
        assert ring.try_pop() is None


def test_push_pop_round_trip_with_timestamp(ring_path: Path) -> None:
    with RingBuffer.create(ring_path, 8) as ring:
        assert ring.try_push(order(1), timestamp_ns=555)
        assert len(ring) == 1
        assert ring.try_pop() == (order(1), 555)
        assert ring.try_pop() is None


def test_fifo_order(ring_path: Path) -> None:
    with RingBuffer.create(ring_path, 8) as ring:
        for n in range(1, 6):
            ring.try_push(order(n))
        assert [ring.try_pop()[0] for _ in range(5)] == [order(n) for n in range(1, 6)]


def test_full_ring_rejects_push_until_a_slot_frees(ring_path: Path) -> None:
    with RingBuffer.create(ring_path, 4) as ring:
        assert all(ring.try_push(order(n)) for n in range(1, 5))
        assert len(ring) == 4
        assert not ring.try_push(order(5))  # full: nothing written
        assert ring.try_pop()[0] == order(1)
        assert ring.try_push(order(5))
        assert [ring.try_pop()[0] for _ in range(4)] == [order(n) for n in range(2, 6)]


def test_wrap_around_many_times(ring_path: Path) -> None:
    """Indices grow far past capacity; slots are reused in order."""
    with RingBuffer.create(ring_path, 4) as ring:
        next_in, next_out = 1, 1
        for _ in range(50):
            for _ in range(3):
                assert ring.try_push(order(next_in))
                next_in += 1
            for _ in range(3):
                assert ring.try_pop()[0] == order(next_out)
                next_out += 1
        assert len(ring) == 0
        assert next_in - 1 == 150  # 150 items through 4 slots


def test_attach_sees_the_same_memory(ring_path: Path) -> None:
    with RingBuffer.create(ring_path, 8) as producer, RingBuffer.attach(ring_path) as consumer:
        assert consumer.capacity == 8
        producer.try_push(order(42), timestamp_ns=7)
        assert len(consumer) == 1
        assert consumer.try_pop() == (order(42), 7)
        assert len(producer) == 0  # the consumer's read index is shared too


def test_attach_rejects_a_file_that_is_not_a_ring(ring_path: Path) -> None:
    ring_path.write_bytes(bytes(config.RING_HEADER_SIZE + 64))
    with pytest.raises(ValueError, match="magic"):
        RingBuffer.attach(ring_path)


def test_header_indices_sit_on_separate_cache_lines() -> None:
    offsets = [config.RING_META_OFFSET, config.RING_WRITE_INDEX_OFFSET, config.RING_READ_INDEX_OFFSET]
    lines = {o // config.CACHE_LINE_SIZE for o in offsets}
    assert len(lines) == 3
    assert config.RING_HEADER_SIZE % config.CACHE_LINE_SIZE == 0
