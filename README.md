# ChronosMatch

A learning-grade, zero-copy limit order book matching engine in Python + Cython.

A Python **firehose** process writes orders as raw 32-byte records into a **memory-mapped ring
buffer**. A separate **Cython matching engine** process reads the same memory, with no pickle or
JSON on the data path, and matches orders with price-time priority in a C loop. Every trade
goes through a second ring to a background **SQLite ledger** process. A **curses dashboard**
shows the live top of book, latency in microseconds, and highlights "whale" orders.

> Honest scope: real HFT systems use C++ or FPGAs. This project demonstrates the techniques
> (zero-copy IPC, lock-free SPSC ring, C data structures, measured latency) and states its
> limits; see the notes in `docs/notes/`.

## Architecture

```
 firehose process              shared memory                engine process
+-------------------+     +-----------------------+     +------------------------+
| asyncio, 100k/s   | --> | order ring (SPSC)     | --> | C loop + Cython book   |
| stamps entry time |     | mmap, 32-byte records |     | price-indexed arrays,  |
+-------------------+     | acquire/release index |     | FIFO per price level   |
                          +-----------------------+     +-----+------------+-----+
                                                              |            | ~10x per second
                          +-----------------------+           |            v
 ledger process     <---- | trade ring (SPSC)     | <---------+   +-----------------+
 (SQLite, nice 15)        | mmap, 32-byte records |               | telemetry block | --> dashboard
                          +-----------------------+               | mmap, seqlock   |     (curses)
                                                                  +-----------------+
```

## Setup (macOS)
```bash
xcode-select --install                # C compiler for Cython
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python setup.py build_ext --inplace   # compile the Cython modules (rerun after editing .pyx)
pytest                                # 245 tests
```

## Demos
All commands from the repo root with the venv active.

| Command | What it shows |
|---|---|
| `PYTHONPATH=src python -m chronosmatch.live` | Live dashboard: 2M orders at 100k/s, whale highlighting (q quits) |
| `PYTHONPATH=src python -m chronosmatch.demo_pipeline --ledger trades.sqlite` | Pipeline + SQLite ledger: every trade stored, fingerprint read back from SQLite |
| `PYTHONPATH=src python -m chronosmatch.demo_pipeline` | Full pipeline, 1M orders, engine's trades verified, PASS/FAIL |
| `PYTHONPATH=src python -m chronosmatch.demo_pipeline --count 200000 --reference` | Same, also checked against the pure-Python reference book |
| `PYTHONPATH=src python -m chronosmatch.demo_ipc` | 1M orders between two processes, pickle disabled, every order checked |
| `pytest tests/test_differential.py -v` | Cython book vs reference book on 108,000 random orders |
| `python scripts/review_check.py` | Runs every proof above and prints a PASS/FAIL checklist |

### Mid-review proofs
- **(a) 1M orders between two processes without pickling:** `demo_ipc` and `demo_pipeline`
  disable `pickle` in every process (any use would crash) and verify all 1,000,000 orders.
  Notes 07 and 10.
- **(b) Buy/sell orders match correctly:** differential tests against a hand-checkable reference
  book (identical trades after every order, 6 kinds of order flow), 20 shared rule tests, 11
  edge-case tests, and a trade fingerprint check in the pipeline demo. A deliberately planted bug
  made 36/36 differential tests fail. Notes 08 and 09.

## Results
macOS 15.6.1, Apple Silicon, Python 3.14.6, Cython 3.3.0. Medians of repeated runs; details and
caveats in `docs/notes/`.

| What | Result | Note |
|---|---|---|
| Orders between two processes, mmap ring | **1.69M orders/sec** | 05, 04 |
| Same with `multiprocessing.Queue` (pickle) | 141k orders/sec (ring ~12x faster) | 05 |
| One order to bytes and back: struct / JSON / pickle | 594 / 2,293 / 3,660 ns | 05 |
| asyncio firehose, unlimited / at 100k target | 831k / 99,979 orders/sec | 06 |
| Reference order book (pure Python) | 12.7k orders/sec, p50 77.8 us | 02, 09 |
| Cython book `submit` / `submit_raw` | 2.7M / 15.9M orders/sec | 09 |
| Engine loop draining the ring: Python / C (`consume_ring`) | 2.5M / **24.7M** orders/sec | 13 |
| Full pipeline, 1M orders, unlimited | 819k orders/sec, p50 0.50 us, p99 0.58 us | 10, 13 |
| Pipeline at 100k/s with ledger (nice 15), 300k orders | p50 0.54 us, p99 0.58 us, max 35 us | 15 |
| SQLite ledger, 1M orders unlimited | 810,698 trades stored at ~603k/s, engine never waited | 15 |

Reproduce everything: `python benchmarks/run_all.py` (or one script, e.g. `python benchmarks/bench_ipc.py`; also `bench_serialization`, `bench_firehose`,
`bench_reference_book`, `bench_order_books`). Raw results in `benchmarks/results/`.

**Caveats:** the Cython speedup is against our deliberately simple reference book, not an
optimised pure-Python book (note 09). Sub-microsecond latencies are limited by the ~42 ns
timer resolution. Tail latency (notes 12-15): garbage collection ruled out (0 collections);
Python objects removed from the engine loop; a sparse-file stall fixed; a normal-priority ledger
hurt the tail, `nice 15` fixed it. What remains is the OS occasionally pausing a process on a
busy 4-performance-core laptop (up to several ms in noisy runs); production systems avoid this
with isolated CPU cores, which macOS does not offer.

## Bugs found along the way
- **Stale reads on ARM (fixed 26 Oct):** without acquire/release ordering, the ring's consumer
  occasionally (~1 per million orders) read a slot's previous contents. Found because identical
  runs gave different trade counts; fixed with C atomics; 0 stale reads in 6M checked orders
  afterwards. Note 04.
- **Producer stalls on a sparse ring file (fixed 3 Nov):** the first write into each new 128 KB
  chunk of the ring file stalled the producer ~200 us, because the file was created sparse.
  Preallocating it: 0 of 48 boundary crossings stalled, vs 22 of 48 before. Note 14.

## Layout
```
src/chronosmatch/   package (config.py holds all constants; *.pyx are Cython)
tests/              pytest tests
benchmarks/         benchmark scripts and saved JSON results
docs/notes/         one note per module: design, code walkthrough, results, gotchas
docs/               glossary, decisions log, viva prep, progress log
learning/           small toy scripts used while learning
```

## Status
- Weeks 1-2: ring buffer, firehose, Cython order book, pipeline, dashboard (complete).
- Week 3: engine loop in C with no per-order Python objects; GC ruled out; tail-latency causes
  found and fixed where possible (notes 12-14) (complete).
- Week 4: SQLite trade ledger (note 15) and whale-order highlighting (note 16) (complete).
- Deliverables: [project report](docs/project-report.md),
  [presentation outline](docs/presentation-outline.md), [review runbook](docs/mid-review-runbook.md).
