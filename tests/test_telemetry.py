"""Telemetry block (seqlock snapshot), Cython top_levels, and engine publishing."""

import time
from pathlib import Path

import pytest

from chronosmatch import config
from chronosmatch.cython_book import CythonOrderBook
from chronosmatch.engine import run_engine
from chronosmatch.order_generator import generate_orders
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.telemetry import Snapshot, TelemetryBlock
from chronosmatch.types import Order, Side


def snap(**overrides) -> Snapshot:
    base = dict(
        processed=10, trades=4, traded_qty=40, best_bid=99, best_ask=101, updated_ns=5,
        orders_per_sec=1000, latency_p50_ns=700, latency_p99_ns=2000, target_count=100,
        done=False, bids=[(99, 10), (98, 5)], asks=[(101, 7)],
    )
    base.update(overrides)
    return Snapshot(**base)


def test_nothing_published_reads_none(tmp_path: Path) -> None:
    with TelemetryBlock.create(tmp_path / "t.tel") as tel:
        assert tel.read() is None


def test_publish_and_read_round_trip(tmp_path: Path) -> None:
    with TelemetryBlock.create(tmp_path / "t.tel") as writer, TelemetryBlock.attach(tmp_path / "t.tel") as reader:
        writer.publish(snap())
        got = reader.read()
    assert got == snap() and got.spread == 2


def test_missing_prices_and_levels_round_trip(tmp_path: Path) -> None:
    with TelemetryBlock.create(tmp_path / "t.tel") as tel:
        tel.publish(snap(best_bid=None, best_ask=None, bids=[], asks=[], done=True))
        got = tel.read()
    assert (got.best_bid, got.best_ask, got.spread, got.bids, got.asks, got.done) == (None, None, None, [], [], True)


def test_only_depth_levels_are_kept(tmp_path: Path) -> None:
    many = [(100 - i, 1) for i in range(config.TELEMETRY_DEPTH + 3)]
    with TelemetryBlock.create(tmp_path / "t.tel") as tel:
        tel.publish(snap(bids=many))
        assert tel.read().bids == many[: config.TELEMETRY_DEPTH]


def test_sequence_is_even_after_each_publish(tmp_path: Path) -> None:
    with TelemetryBlock.create(tmp_path / "t.tel") as tel:
        for n in range(1, 4):
            tel.publish(snap(processed=n))
            assert tel.sequence == 2 * n


def test_reader_refuses_a_snapshot_being_written(tmp_path: Path) -> None:
    """Simulate a writer stopped mid-write (odd sequence): the reader must not return data."""
    with TelemetryBlock.create(tmp_path / "t.tel") as tel:
        tel.publish(snap())
        tel._seq[0] = tel._seq[0] + 1  # odd = "writing in progress"
        assert tel.read() is None


def test_attach_rejects_wrong_file(tmp_path: Path) -> None:
    (tmp_path / "x.tel").write_bytes(bytes(512))
    with pytest.raises(ValueError, match="magic"):
        TelemetryBlock.attach(tmp_path / "x.tel")


def test_top_levels_stops_at_depth() -> None:
    book = CythonOrderBook(max_price=200, capacity=64)
    for i, price in enumerate([90, 95, 97, 99], start=1):
        book.submit(Order(i, Side.BUY, price, i))
    book.submit(Order(9, Side.SELL, 120, 4))
    assert book.top_levels(Side.BUY, 2) == [(99, 4), (97, 3)]
    assert book.top_levels(Side.SELL, 5) == [(120, 4)]
    assert book.top_levels(Side.BUY, 0) == []


def test_engine_publishes_final_snapshot(tmp_path: Path) -> None:
    count = 3_000
    with RingBuffer.create(tmp_path / "e.ring", 4096) as ring, TelemetryBlock.create(tmp_path / "e.tel") as tel:
        for o in generate_orders(count, seed=6):
            ring.try_push(o, time.perf_counter_ns())
        book = CythonOrderBook()
        result = run_engine(ring, book, count, telemetry=tel)
        final = tel.read()
    assert final.done and final.processed == count and final.target_count == count
    assert final.trades == result.trade_stats[0]
    assert (final.best_bid, final.best_ask) == (result.best_bid, result.best_ask)
    assert final.bids == book.top_levels(Side.BUY, config.TELEMETRY_DEPTH)
