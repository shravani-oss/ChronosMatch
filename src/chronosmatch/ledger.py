"""Ledger process: drains the engine's trade ring into a SQLite database (Week 4).

    python -m chronosmatch.ledger --trades /tmp/chronos.trades --db trades.sqlite

Runs beside the engine, off the matching path: the engine only copies 32-byte trade records into
shared memory; this process does the slow work (Python tuples, SQL). It writes in batches of up to
LEDGER_BATCH_SIZE trades per transaction and sleeps briefly when there is nothing to write, so it
does not compete with the engine for a CPU core.

It also lowers its own CPU priority (`os.nice(LEDGER_NICE)`): it is background work that only has
to keep up on average, and at normal priority it measurably hurt the engine's tail latency
(note 15).

It stops at the end-of-stream record (buy_order_id 0), then reads every row back from SQLite and
computes the trade fingerprint (trade_digest.py), which must equal the engine's.
"""

import argparse
import json
import os
import sqlite3
import struct
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from chronosmatch import config
from chronosmatch.no_pickle import forbid_pickle
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.trade_digest import TradeDigest
from chronosmatch.types import Trade

TRADE_STRUCT = struct.Struct(config.TRADE_RECORD_FORMAT)
_TIMEOUT_S = 600.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    seq           INTEGER PRIMARY KEY,   -- order in which the engine made the trade
    buy_order_id  INTEGER NOT NULL,
    sell_order_id INTEGER NOT NULL,
    price         INTEGER NOT NULL,      -- ticks
    quantity      INTEGER NOT NULL,
    matched_ns    INTEGER NOT NULL       -- engine clock (perf_counter_ns) when matched
)
"""
_INSERT = "INSERT INTO trades (buy_order_id, sell_order_id, price, quantity, matched_ns) VALUES (?, ?, ?, ?, ?)"


@dataclass(frozen=True)
class LedgerResult:
    trades_written: int
    batches: int
    largest_batch: int
    elapsed_ns: int
    fingerprint: tuple[int, int, int, int]

    @property
    def trades_per_sec(self) -> float:
        return self.trades_written / (self.elapsed_ns / config.NS_PER_SEC) if self.elapsed_ns else 0.0


def open_db(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")      # readers (e.g. a report) do not block the writer
    db.execute("PRAGMA synchronous=NORMAL")    # durable at checkpoints; fine for a simulator
    db.execute(SCHEMA)
    db.commit()
    return db


def fingerprint_from_db(db: sqlite3.Connection) -> tuple[int, int, int, int]:
    digest = TradeDigest()
    rows = db.execute("SELECT buy_order_id, sell_order_id, price, quantity FROM trades ORDER BY seq")
    digest.add(Trade(*row) for row in rows)
    return digest.stats


def run_ledger(trade_ring: RingBuffer, db: sqlite3.Connection, timeout_s: float = _TIMEOUT_S) -> LedgerResult:
    written = batches = largest = 0
    start = 0
    deadline = time.monotonic() + timeout_s
    finished = False
    while not finished:
        batch = trade_ring.pop_batch(TRADE_STRUCT, config.LEDGER_BATCH_SIZE)
        if not batch:
            if time.monotonic() > deadline:
                raise TimeoutError(f"ledger wrote {written} trades and then saw no end of stream")
            time.sleep(config.LEDGER_IDLE_SLEEP_S)
            continue
        if start == 0:
            start = time.perf_counter_ns()
        for i, row in enumerate(batch):
            if row[0] == config.LEDGER_END_OF_STREAM_ID:
                batch, finished = batch[:i], True
                break
        if batch:
            with db:  # one transaction per batch
                db.executemany(_INSERT, batch)
            written += len(batch)
            batches += 1
            largest = max(largest, len(batch))
    elapsed = time.perf_counter_ns() - start if start else 0
    return LedgerResult(written, batches, largest, elapsed, fingerprint_from_db(db))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ChronosMatch SQLite trade ledger process.")
    parser.add_argument("--trades", required=True, help="trade ring created with RING_MAGIC_TRADES")
    parser.add_argument("--db", required=True, help="SQLite database file")
    parser.add_argument("--forbid-pickle", action="store_true")
    parser.add_argument("--nice", type=int, default=config.LEDGER_NICE,
                        help="lower this process's CPU priority by N (0 = normal priority)")
    args = parser.parse_args(argv)
    if args.forbid_pickle:
        forbid_pickle()
    if args.nice:
        os.nice(args.nice)
    db = open_db(args.db)
    try:
        with RingBuffer.attach(args.trades, config.RING_MAGIC_TRADES) as ring:
            result = run_ledger(ring, db)
    finally:
        db.close()
    print(json.dumps(asdict(result)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
