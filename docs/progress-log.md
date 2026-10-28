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

## 2026-10-24
- Mid-review proof (b): differential tests, 6 flows x 6 seeds x 3,000 orders, Cython book and
  reference book identical after every order. Planted-bug check: 36/36 differential tests failed
  with a deliberate pricing bug, then reverted.
- Order book benchmark: reference 12,747/s; Cython submit 2.72M/s (213x); Cython submit_raw
  15.9M/s (1,248x vs the naive reference). p50 latency 0.17 us / 0.13 us vs 77.8 us.
- Documented why the speedup headline must be qualified (naive baseline, timer resolution).
- Suite: 173 passing.

## 2026-10-25
- Connected the pipeline: engine process (`engine.py`) reads raw integers from the ring and
  matches in the Cython book; `demo_pipeline.py` runs firehose + engine as separate processes.
- Added an in-C trade fingerprint (count, quantity, notional, FNV-1a checksum) and a matching
  pure-Python `TradeDigest`; added `RingBuffer.try_pop_raw`.
- 1M-order pipeline runs: ~755k orders/sec, p50 latency 0.75 us, all PASS with identical
  fingerprints; 200k run also equal to the reference book. Max latency spikes of 1-14 ms are
  open (Week 3).
- Caught two unfair quick benchmarks before the like-for-like one (fingerprint cost ~0.4%).
- Decisions D23, D24. Suite: 183 passing.

## 2026-10-26 (Weeks 1-2 deadline)
- Live telemetry: engine publishes a seqlock snapshot into shared memory ~10x/s;
  `CythonOrderBook.top_levels` for cheap depth snapshots.
- **Bug found and fixed:** identical seeded runs gave different trade counts. Diagnosed stale
  ring reads on ARM (~1 per million orders: consumer saw the new index before the data). Fixed
  with acquire/release atomics (`atomics.pyx`) for ring and telemetry indices. 0 stale reads in
  6M checked orders after the fix; ring throughput unchanged (1.69M/s).
- curses dashboard (best bid/ask, spread, 5 levels per side, rate, latency) and one-command live
  demo (`python -m chronosmatch.live`), with a headless mode.
- README rewritten; viva prep extended for all Weeks 1-2 modules; notes 04, 07, 10, 11 updated.
- Suite: 206 passing.

## Weeks 1-2 summary (status at 26 Oct)
| Planned | Status |
|---|---|
| mmap ring buffer with struct records | Done (notes 03, 04), ARM ordering bug fixed |
| asyncio firehose, 100k orders/sec | Done: 99,979/s at target, 831k/s unlimited (note 06) |
| Cython limit order book, price-time priority | Done: 15.9M orders/s raw (notes 08, 09) |
| curses dashboard, top of book | Done (note 11) |
| Mid review (a): 1M orders between processes, no pickle | Done: `demo_ipc`, `demo_pipeline` |
| Mid review (b): matching correct | Done: differential tests, fingerprint check |
| Deferred | Websocket feed (D16); tail latency (Week 3) |

## 2026-10-27 (mid-review window opens)
- Mid-review readiness: `scripts/review_check.py` runs every proof (6/6 PASS, full and quick
  modes) and `docs/mid-review-runbook.md` (demo order, what to say, fallbacks).
- Week 3 started: GC monitor (`gc_monitor.py`), p99.9 latency, `--gc off` switch.
- Tail-latency investigation (note 12): GC rejected (0 collections in all engine runs; on/off no
  consistent difference once runs were interleaved). OS scheduling supported: hiccup meter saw
  gaps up to 14.8 ms while the pipeline ran vs at most 96 us alone (Apple M1, 4 P-cores).
- Caught two flaws in my own experiments (run-order confound; GIL artefact from using a thread).
- Suite: 210 passing.

## 2026-10-28
- Week 3 goal done: engine loop moved into Cython (`consume_ring`): records read from shared
  memory as C structs, no Python object per order; same clock as perf_counter_ns (tested).
  `--loop python` kept for comparison. 12 new tests.
- Engine capacity 24.7M orders/s (C) vs 2.5M (Python), 9.9x; pipeline at 100k/s p50 0.50 us,
  p99 0.58 us (vs 0.71 / 2.0).
- Finding: the engine's own longest pause (59-131 us) is far shorter than the max latency
  (221-409 us), so engine preemption does not explain the worst spikes. New hypothesis: firehose
  paused between stamping and publishing an order (to measure next).
- Suite: 222 passing; review check 6/6 PASS.

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
- [ ] Differential testing and the planted-bug check (note 09)
- [ ] Reading benchmarks honestly: naive baselines, timer resolution, p50/p99 (note 09)
- [ ] Pipeline demo and the trade fingerprint (note 10): rehearse running and explaining it
- [ ] Memory ordering, acquire/release, the stale-read bug and fix (note 04): rehearse as an interview story
- [ ] Seqlock and the dashboard design (note 11)
- [ ] GC: refcounting vs cyclic GC, thresholds, why the engine never collects (note 12)
- [ ] Tail latency, OS scheduling, the hiccup meter, experiment design pitfalls (note 12)
- [ ] consume_ring: C structs over shared memory, same-clock latency, loop pause meter (note 13)
- [ ] multiprocessing spawn -> ipc_demo.py and the two-process test walkthrough
