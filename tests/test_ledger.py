"""Trade ring, C engine writing trades, SQLite ledger, and the pipeline with a ledger."""

import sqlite3
import struct
import time
from array import array
from pathlib import Path

import pytest

from chronosmatch import config
from chronosmatch.cython_book import CythonOrderBook, trade_record_size
from chronosmatch.demo_pipeline import PipelineResult, run_pipeline
from chronosmatch.engine import end_trades
from chronosmatch.ledger import TRADE_STRUCT, fingerprint_from_db, open_db, run_ledger
from chronosmatch.order_generator import generate_orders
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.trade_digest import TradeDigest
from chronosmatch.types import Side, Trade


def trade_ring(path: Path, capacity: int = 1 << 14) -> RingBuffer:
    return RingBuffer.create(path, capacity, config.RING_MAGIC_TRADES)


def test_trade_record_layout_is_32_bytes() -> None:
    assert trade_record_size() == TRADE_STRUCT.size == config.TRADE_RECORD_SIZE


def test_ring_kinds_cannot_be_mixed_up(tmp_path: Path) -> None:
    with RingBuffer.create(tmp_path / "o.ring", 8):
        with pytest.raises(ValueError, match="magic"):
            RingBuffer.attach(tmp_path / "o.ring", config.RING_MAGIC_TRADES)


def test_push_raw_and_pop_batch(tmp_path: Path) -> None:
    with trade_ring(tmp_path / "t.ring", 8) as ring:
        rows = [(i, i + 100, 50 + i, i, 7) for i in range(1, 9)]
        assert all(ring.try_push_raw(TRADE_STRUCT, r) for r in rows)
        assert not ring.try_push_raw(TRADE_STRUCT, rows[0])  # full
        assert ring.pop_batch(TRADE_STRUCT, 3) == rows[:3]
        assert ring.pop_batch(TRADE_STRUCT, 100) == rows[3:]
        assert ring.pop_batch(TRADE_STRUCT, 100) == []


def test_record_size_mismatch_rejected(tmp_path: Path) -> None:
    with trade_ring(tmp_path / "m.ring", 8) as ring:
        with pytest.raises(ValueError, match="record size"):
            ring.pop_batch(struct.Struct("<Q"), 1)


def test_ledger_writes_rows_until_end_of_stream(tmp_path: Path) -> None:
    trades = [Trade(2, 1, 51, 10), Trade(3, 1, 52, 5), Trade(4, 9, 50, 1)]
    with trade_ring(tmp_path / "l.ring") as ring:
        for t in trades:
            ring.try_push_raw(TRADE_STRUCT, (t.buy_order_id, t.sell_order_id, t.price, t.quantity, 123))
        end_trades(ring)
        db = open_db(tmp_path / "l.sqlite")
        result = run_ledger(ring, db, timeout_s=5)
    rows = db.execute("SELECT buy_order_id, sell_order_id, price, quantity, matched_ns FROM trades ORDER BY seq").fetchall()
    assert rows == [(2, 1, 51, 10, 123), (3, 1, 52, 5, 123), (4, 9, 50, 1, 123)]
    digest = TradeDigest()
    digest.add(trades)
    assert result.trades_written == 3 and result.fingerprint == digest.stats == fingerprint_from_db(db)


def test_ledger_times_out_without_end_of_stream(tmp_path: Path) -> None:
    with trade_ring(tmp_path / "x.ring") as ring:
        with pytest.raises(TimeoutError):
            run_ledger(ring, open_db(tmp_path / "x.sqlite"), timeout_s=0.1)


def test_c_engine_copies_every_trade_into_the_trade_ring(tmp_path: Path) -> None:
    count = 3_000
    with RingBuffer.create(tmp_path / "o.ring", 4096) as orders, trade_ring(tmp_path / "t.ring") as trades:
        for o in generate_orders(count, seed=6):
            orders.try_push(o, time.perf_counter_ns())
        book = CythonOrderBook()
        *_, waits = book.consume_ring(orders, count, array("q", bytes(8 * count)), 5.0, None, 1024, 10**9, trades)
        rows = trades.pop_batch(TRADE_STRUCT, 1 << 14)
    digest = TradeDigest()
    digest.add(Trade(b, s, p, q) for b, s, p, q, _ in rows)
    assert waits == 0
    assert digest.stats == book.trade_stats


def test_engine_waits_then_times_out_if_ledger_never_drains(tmp_path: Path) -> None:
    with RingBuffer.create(tmp_path / "o.ring", 4096) as orders, trade_ring(tmp_path / "t.ring", 4) as trades:
        for o in generate_orders(2_000, seed=6):
            orders.try_push(o, time.perf_counter_ns())
        with pytest.raises(TimeoutError, match="trade ring full"):
            CythonOrderBook().consume_ring(orders, 2_000, array("q", bytes(16_000)), 0.2, None, 1024, 10**9, trades)


def test_pipeline_with_ledger_stores_every_trade(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    result = run_pipeline(tmp_path / "p.ring", 20_000, 3, 0, 1024, False, ledger_db=db)
    assert result.ok, result
    assert tuple(result.ledger["fingerprint"]) == tuple(result.engine["trade_stats"]) == result.expected_stats
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == result.expected_stats[0]


def test_ledger_mismatch_makes_the_pipeline_fail() -> None:
    engine = {"processed": 1, "trade_stats": [1, 5, 250, 99]}
    base = dict(count=1, firehose_output="sent=1", firehose_returncode=0, engine=engine,
                engine_returncode=0, engine_error="", expected_stats=(1, 5, 250, 99), reference_stats=None)
    good = PipelineResult(**base, ledger={"trades_written": 1, "fingerprint": [1, 5, 250, 99]}, ledger_returncode=0)
    bad = PipelineResult(**base, ledger={"trades_written": 1, "fingerprint": [1, 5, 250, 98]}, ledger_returncode=0)
    assert good.ok and not bad.ok
