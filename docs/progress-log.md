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

## 2026-10-20
- Built the asyncio market firehose (`firehose.py`) with a CLI, batch-scheduled rate limiting,
  backpressure handling and per-order entry timestamps. 7 unit tests + 1 two-process CLI test.
- Fixed a wrong test (not a code bug): the backpressure test never filled the ring because the
  firehose yielded more often than the ring could fill; batch size raised above capacity.
- Benchmark: 830,571 orders/sec unlimited, 99,979 orders/sec at the 100k target. Week 1 target met.
- Decisions D16 (websocket deferred) and D17 (batch rate control). Test suite: 84 passing.

## 2026-10-21
- Mid-review proof (a) done: `python -m chronosmatch.demo_ipc` moves 1,000,000 orders from a
  separate firehose process through the mmap ring with pickle disabled in both processes, and
  checks every order. 3 unlimited runs (575k-640k orders/sec) and 1 run at 100k/sec: all PASS,
  0 mismatches.
- Added the pickle guard (`no_pickle.py`), a `--forbid-pickle` firehose flag, and a negative test
  proving the demo reports FAIL on mismatched data. Test suite: 92 passing.

## 2026-10-22
- Week 2 started. Installed and pinned Cython 3.3.0 + setuptools; `setup.py build_ext --inplace`
  build; README build step.
- Wrote the Cython order book design before coding (note 08; decisions D18-D20): per-price C
  arrays, preallocated node pool with a free stack, linked FIFO per level.
- Implemented `cython_book.pyx`: book structure and resting orders in C memory. 13 tests,
  including an exact comparison with the reference book on random non-crossing orders.
- Test suite: 105 passing.

## 2026-10-23
- Implemented matching in the Cython book: cdef `_match` core (price-time priority, partial
  fills, node recycling, best-price rescans), `submit` and `submit_raw` entry points.
- 10 matching scenarios now run against both books (20 tests); 11 Cython edge-case tests.
- Sanity differential check: 100,000 random orders over 5 seeds, identical trades and books.
- Decisions D21 (up-front rejection when pool full) and D22 (C trade buffer). Suite: 136 passing.

## Learning debt (must be taught and walked through line by line before the mid review)
- [ ] Part B check questions (time priority, partial fill, why arrival time matters)
- [ ] Latency, processes vs threads, the GIL
- [ ] reference_book.py walkthrough
- [ ] Bytes, struct, endianness -> order_record.py walkthrough
- [ ] Serialization cost and zero-copy (benchmarks in note 05)
- [ ] Benchmark method: warm-up, medians, excluding setup -> bench_ipc.py walkthrough
- [ ] mmap and shared memory -> ring_buffer.py walkthrough
- [ ] Ring buffers: indices, full/empty, backpressure, SPSC, publish order, memory ordering
- [ ] asyncio: event loop, coroutines, sleep(0), gather -> firehose.py walkthrough
- [ ] Rehearse the demo_ipc.py demo and its evidence table (note 07)
- [ ] Cython: .pyx, cdef, cdef class, malloc/free, compiling -> cython_book.pyx walkthrough
- [ ] Order book data structures: arrays by price tick, node pool, linked FIFO (note 08)
- [ ] multiprocessing spawn -> ipc_demo.py and the two-process test walkthrough
