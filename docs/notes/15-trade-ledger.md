# 15 - Week 4: SQLite Trade Ledger

## What it does
Every trade the engine makes is stored in a SQLite database by a separate background process,
without slowing the matching loop.

    engine (C loop) --32-byte trade records--> [trade ring, shared memory] --batches--> ledger --> SQLite

    PYTHONPATH=src python -m chronosmatch.demo_pipeline --ledger trades.sqlite
    sqlite3 trades.sqlite "SELECT COUNT(*), SUM(quantity) FROM trades"

## Design
- **Trade ring:** the same SPSC ring buffer as the orders (acquire/release, preallocated file),
  created with a different magic number (`RING_MAGIC_TRADES`) so the two kinds cannot be mixed
  up. Trade record `"<QQiIQ"`: buy id, sell id, price, quantity, matched_ns = 32 bytes.
- **Engine side (C):** after `_match`, the loop copies that order's trades from the book's C trade
  buffer into the trade ring and publishes them with one release store. If the ring is full the
  engine **waits** (trades are never dropped) and counts `trade_ring_waits`.
- **End of stream:** when the engine finishes it sends a record with `buy_order_id = 0`
  (real order ids start at 1).
- **Ledger process (`ledger.py`):** pops up to 10,000 trades at a time with one release store,
  inserts them in **one transaction per batch** (`executemany`), and **sleeps 1 ms when idle**
  instead of spinning. SQLite runs in WAL mode with `synchronous=NORMAL`.
- **Verification:** at the end the ledger reads every row back (`ORDER BY seq`) and computes the
  trade fingerprint; the demo checks it equals the engine's and the expected answer.

## Results (3 Nov, Apple M1, Python 3.14.6)
1M orders, unlimited rate: 810,698 trades written to SQLite at ~603k trades/s, the engine never
waited for the ledger, and the fingerprint read back from SQLite equalled the engine's: PASS.

**Cost to the engine's latency** (300k orders at 100k/s, runs interleaved, medians):
| Configuration | p50 | p99 | p99.9 | max |
|---|---|---|---|---|
| No ledger | 0.50 us | 0.60 us | 7.8 us | 185 us |
| Ledger, normal priority | 0.54 us | 3.96 us | 423 us | 734 us |
| **Ledger, `nice 15`** | **0.54 us** | **0.58 us** | **7.1 us** | **35 us** |

At normal priority the ledger's SQLite bursts competed with the engine and firehose for the M1's 4
performance cores and hurt the tail badly. Lowering its priority with `os.nice(15)` made p99
identical in all 4 runs (0.584 us), and the maximum (35 us) is the best measured in this project,
even better than without a ledger (that comparison was not interleaved with the nice runs, so do
not over-read it). The engine still never waited, so the ledger keeps up. `nice 15` is now the
default (`config.LEDGER_NICE`).

## Tests (`tests/test_ledger.py`, 10)
Record layout; order and trade rings cannot be mixed up; raw push and batch pop; record-size
mismatch rejected; ledger writes rows and stops at end of stream with the right fingerprint;
ledger timeout; C engine copies every trade into the trade ring; engine times out if the ledger
never drains; full pipeline with ledger; a ledger fingerprint mismatch makes the pipeline FAIL.

## Limits
- `synchronous=NORMAL` in WAL mode can lose the last transactions on a power cut (not on a
  process crash). A real ledger would use `FULL` and accept the cost.
- If the ledger falls far behind, the engine waits: correctness over latency, by design.
- Order and trade rings use the same 32-byte slot size; a different record size would need the
  slot size to become a parameter.
