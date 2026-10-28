"""Engine loop tests (single process: orders pushed into the ring first, then matched)."""

import time
from pathlib import Path

import pytest

from chronosmatch.cython_book import CythonOrderBook
from chronosmatch.engine import run_engine
from chronosmatch.order_generator import generate_orders
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.types import Side

COUNT = 3_000


def direct_stats(count: int, seed: int) -> tuple:
    book = CythonOrderBook()
    for o in generate_orders(count, seed=seed):
        book.submit_raw(o.side is Side.BUY, o.order_id, o.price, o.quantity)
    return book.trade_stats


def test_engine_matches_same_as_direct_book(tmp_path: Path) -> None:
    with RingBuffer.create(tmp_path / "e.ring", 4096) as ring:
        for o in generate_orders(COUNT, seed=4):
            assert ring.try_push(o, time.perf_counter_ns())
        result = run_engine(ring, CythonOrderBook(), COUNT)
    assert result.processed == COUNT
    assert result.trade_stats == direct_stats(COUNT, 4)
    assert result.trade_stats[0] > 0


def test_latencies_are_non_negative_and_ordered(tmp_path: Path) -> None:
    with RingBuffer.create(tmp_path / "l.ring", 4096) as ring:
        for o in generate_orders(500, seed=1):
            ring.try_push(o, time.perf_counter_ns())
        result = run_engine(ring, CythonOrderBook(), 500)
    assert 0 <= result.latency_p50_us <= result.latency_p99_us <= result.latency_max_us


def test_engine_times_out_when_orders_stop_arriving(tmp_path: Path) -> None:
    with RingBuffer.create(tmp_path / "t.ring", 64) as ring:
        for o in generate_orders(10, seed=1):
            ring.try_push(o, time.perf_counter_ns())
        with pytest.raises(TimeoutError, match="10 of 20"):
            run_engine(ring, CythonOrderBook(), 20, timeout_s=0.2)


@pytest.mark.parametrize("loop", ["c", "python"])
def test_both_loops_give_identical_results(tmp_path: Path, loop: str) -> None:
    with RingBuffer.create(tmp_path / f"{loop}.ring", 4096) as ring:
        for o in generate_orders(COUNT, seed=8):
            ring.try_push(o, time.perf_counter_ns())
        result = run_engine(ring, CythonOrderBook(), COUNT, loop=loop)
    assert result.trade_stats == direct_stats(COUNT, 8)
    assert result.loop == loop
    assert (result.loop_pauses is not None) == (loop == "c")


def test_unknown_loop_rejected(tmp_path: Path) -> None:
    with RingBuffer.create(tmp_path / "x.ring", 8) as ring:
        with pytest.raises(ValueError, match="loop"):
            run_engine(ring, CythonOrderBook(), 0, loop="rust")
