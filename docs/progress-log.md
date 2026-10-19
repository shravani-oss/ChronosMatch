# Progress Log

## 2026-10-11
- Read project instructions (CLAUDE.md).
- Phase 0, Step 1: big-picture explanation written (docs/notes/00-big-picture.md).

## 2026-10-11 (later)
- Phase 0 Step 1 check questions answered correctly (matching engine, trade, slow handoffs, GC pauses, serialization).
- Phase 0 Step 2 prerequisite 1 part A taught: bid/ask, spread, limit vs market orders.
- Added glossary, exchange-basics note and a toy order book script.

## 2026-10-12
- Reviewed answers on bid/ask, spread and order types (corrected: spread = ask - bid, a bid at
  52 against a best ask of 51 trades immediately, market sells risk low prices).
- Taught part B of exchange basics: order book, price-time priority, partial fills.
- Added toy matching script and updated glossary and notes.

## 2026-10-13
- Set up environment: venv, pinned requirements.txt (pytest), Xcode CLT confirmed.
- Added src/chronosmatch package skeleton and central config.
- Added pytest configuration and smoke tests (3 passing); README now has setup steps and layout.

## 2026-10-14
- Added viva and interview prep Q&A for the big picture and exchange basics, with a draft
  2-minute project explanation.
- Started the design decisions log with the seven decisions made so far and the open ones.

## 2026-10-15
- Added Order, Side and Trade types with validation (src/chronosmatch/types.py).
- Added a pure-Python reference order book as a correctness oracle for the future Cython
  engine, with 10 behaviour tests (price priority, time priority, partial fills, resting
  remainder, both sides).
- Logged decisions D8 (integer ticks) and D9 (reference oracle).

## 2026-10-16
- Added a seeded synthetic order generator (config defaults, input validation, 7 tests).
- Added randomized invariant tests on the reference book: never crossed, quantity conserved,
  trade prices within both limits, plus a guard test that trades really occur.
- Logged decision D10.

## 2026-10-17
- Added levels(side) price-level snapshot to the reference book, with 5 tests.
- Fixed a mistake caught before pushing: a failing import slipped into a local commit because the
  test run's exit code was hidden by a pipe; amended before pushing.
- Added a reproducible baseline benchmark: 12,839 orders/sec median, p50 77.4 us, p99 169.5 us.

## 2026-10-18
- Built ahead of the lessons (by choice, to match the schedule):
  - 32-byte binary order record with struct (`order_record.py`), 8 tests.
  - SPSC ring buffer in a memory-mapped file (`ring_buffer.py`), 13 tests: empty, full,
    wrap-around, attach, bad file.
  - Two-process test: 50,000 orders through a 1,024-slot ring between two OS processes.
    20/20 repeated runs passed.
- Logged decisions D11 to D15; added notes 03 and 04 and glossary terms.
- Test suite: 76 passing.

## 2026-10-19
- Two-process IPC benchmark: mmap ring buffer 1.66M orders/sec vs multiprocessing.Queue
  139k orders/sec (11.9x).
- Serialization benchmark: struct 594 ns, JSON 2,293 ns, pickle 3,660 ns per order round trip;
  raw struct without an Order object 227 ns (Order creation is ~62% of the cost).
- Added note 05 and a results table to the README.

## Learning debt (must be taught and walked through line by line before the mid review)
- [ ] Part B check questions (time priority, partial fill, why arrival time matters)
- [ ] Latency, processes vs threads, the GIL
- [ ] reference_book.py walkthrough
- [ ] Bytes, struct, endianness -> order_record.py walkthrough
- [ ] Serialization cost and zero-copy (benchmarks in note 05)
- [ ] Benchmark method: warm-up, medians, excluding setup -> bench_ipc.py walkthrough
- [ ] mmap and shared memory -> ring_buffer.py walkthrough
- [ ] Ring buffers: indices, full/empty, backpressure, SPSC, publish order, memory ordering
- [ ] multiprocessing spawn -> ipc_demo.py and the two-process test walkthrough
