"""The C engine loop (`CythonOrderBook.consume_ring`): same results as the Python loop."""

import struct
import time
from array import array
from pathlib import Path

import pytest

from chronosmatch import config
from chronosmatch.cython_book import CythonOrderBook, now_ns, order_record_size
from chronosmatch.order_generator import generate_orders
from chronosmatch.order_record import ORDER_STRUCT
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.types import Side


def latencies(n: int) -> array:
    return array("q", bytes(8 * n))


def direct_book(count: int, seed: int) -> CythonOrderBook:
    book = CythonOrderBook()
    for o in generate_orders(count, seed=seed):
        book.submit_raw(o.side is Side.BUY, o.order_id, o.price, o.quantity)
    return book


def filled_ring(path: Path, count: int, seed: int, capacity: int = 4096) -> RingBuffer:
    ring = RingBuffer.create(path, capacity)
    for o in generate_orders(count, seed=seed):
        assert ring.try_push(o, time.perf_counter_ns())
    return ring


def test_record_layout_is_32_bytes() -> None:
    assert order_record_size() == config.ORDER_RECORD_SIZE == ORDER_STRUCT.size


def test_c_clock_is_the_same_clock_as_perf_counter_ns() -> None:
    for _ in range(1_000):
        before = time.perf_counter_ns()
        c = now_ns()
        after = time.perf_counter_ns()
        assert before - 1 <= c <= after + 1  # same clock, same tick->ns conversion


def test_consume_ring_matches_like_submit_raw(tmp_path: Path) -> None:
    count = 3_000
    with filled_ring(tmp_path / "a.ring", count, seed=4) as ring:
        book, lat = CythonOrderBook(), latencies(count)
        processed, elapsed, *_ = book.consume_ring(ring, count, lat, 5.0)
        assert len(ring) == 0
    expected = direct_book(count, 4)
    assert processed == count and elapsed > 0
    assert book.trade_stats == expected.trade_stats
    assert (book.best_bid, book.best_ask) == (expected.best_bid, expected.best_ask)
    assert min(lat) >= 0 and max(lat) > 0


def test_consume_in_two_calls_continues_where_it_stopped(tmp_path: Path) -> None:
    with filled_ring(tmp_path / "b.ring", 3_000, seed=5) as ring:
        book = CythonOrderBook()
        book.consume_ring(ring, 1_000, latencies(1_000), 5.0)
        book.consume_ring(ring, 2_000, latencies(2_000), 5.0)
    assert book.trade_stats == direct_book(3_000, 5).trade_stats


def test_timeout_reports_how_many_arrived(tmp_path: Path) -> None:
    with filled_ring(tmp_path / "c.ring", 10, seed=1) as ring:
        with pytest.raises(TimeoutError, match="10 of 20"):
            CythonOrderBook().consume_ring(ring, 20, latencies(20), 0.2)


def test_corrupt_record_is_rejected(tmp_path: Path) -> None:
    with RingBuffer.create(tmp_path / "d.ring", 8) as ring:
        offset = config.RING_HEADER_SIZE
        ORDER_STRUCT.pack_into(ring.buffer, offset, 1, 0, 50, 10, 7)  # side code 7 is invalid
        struct.pack_into("<Q", ring.buffer, config.RING_WRITE_INDEX_OFFSET, 1)
        with pytest.raises(ValueError, match="corrupt"):
            CythonOrderBook().consume_ring(ring, 1, latencies(1), 1.0)


def test_latency_buffer_too_short(tmp_path: Path) -> None:
    with filled_ring(tmp_path / "e.ring", 10, seed=1) as ring:
        with pytest.raises(ValueError, match="shorter"):
            CythonOrderBook().consume_ring(ring, 10, latencies(5), 1.0)


def test_publish_callback_is_called_with_progress(tmp_path: Path) -> None:
    calls = []
    with filled_ring(tmp_path / "f.ring", 1_000, seed=2) as ring:
        CythonOrderBook().consume_ring(
            ring, 1_000, latencies(1_000), 5.0,
            publish=lambda done, rate: calls.append((done, rate)),
            publish_check_every=100, publish_interval_ns=0,
        )
    assert [done for done, _ in calls] == list(range(100, 1_001, 100))
    assert all(rate >= 0 for _, rate in calls)


def test_pause_statistics_are_sane(tmp_path: Path) -> None:
    with filled_ring(tmp_path / "g.ring", 2_000, seed=3) as ring:
        _, _, over_50us, over_1ms, max_gap = CythonOrderBook().consume_ring(ring, 2_000, latencies(2_000), 5.0)
    assert 0 <= over_1ms <= over_50us and max_gap >= 0
