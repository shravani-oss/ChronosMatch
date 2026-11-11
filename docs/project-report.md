# ChronosMatch: Zero-Copy Order Matching Engine in Python and Cython

**Project report** · Infotact Solutions internship, Python Development · 10 Oct – 10 Nov 2026
Author: Shravani Deore · Repository: github.com/shravani-oss/ChronosMatch

---

## 1. Abstract

ChronosMatch is a learning-grade limit order book matching engine. A Python simulator process
writes orders as fixed 32-byte binary records into a ring buffer in shared memory (`mmap`); a
separate engine process reads the same memory, with no pickle or JSON on the data path, and
matches orders with price-time priority in Cython. Trades flow through a second shared-memory
ring to a background SQLite ledger, and a curses dashboard shows the live order book.

Measured on an Apple M1 laptop: the shared-memory ring moves 1.69M orders/s between processes,
about 12x faster than Python's `multiprocessing.Queue`; the engine matches 24.7M orders/s; and
end-to-end latency at 100,000 orders/s is 0.5 µs median and 0.58 µs p99. Correctness was
verified against a simple reference implementation on 108,000 random orders. Two real bugs were
found and fixed by measurement: a memory-ordering bug on ARM and producer stalls caused by a
sparse file.

## 2. Problem

A matching engine pairs buy and sell orders. During busy periods thousands of orders arrive per
second and latency is measured in microseconds. Python is usually avoided for this because:

1. Passing data between processes normally requires **serialization** (pickle/JSON), which costs
   CPU time and copies data.
2. The **garbage collector** can pause the program at unpredictable moments.

The project goal was to show how far these limits can be pushed with zero-copy shared memory and
compiled code, and to measure the result honestly.

## 3. Objectives (from the brief) and status

| Objective | Status |
|---|---|
| Ring buffer in `mmap` with `struct` records | Done |
| asyncio firehose at 100k orders/s | Done: 99,979 orders/s measured |
| Limit order book with price-time priority in Cython | Done |
| curses dashboard: best bid/ask, spread | Done, plus depth, latency and whales |
| Mid review (a): 1M orders between processes, no pickle | Done: 0 mismatches, pickle disabled |
| Mid review (b): orders match correctly | Done: differential tests, 108k orders |
| Week 3: no Python objects in the matching loop; latency timestamps | Done: C engine loop |
| Week 4: SQLite ledger in a background process | Done |
| Week 4: highlight whale orders | Done |
| Sub-millisecond matching with measured benchmarks | Done: p99 0.58 µs at 100k/s |

## 4. Architecture

```
 Firehose process           Shared memory            Engine process
 (asyncio, 100k/s)  --> [ order ring, SPSC ]  --> (C loop + Cython order book)
                                                       |                 |
                         [ trade ring, SPSC ]  <-------+                 +--> [ telemetry ]
                                 |                                              |
                          Ledger process                                 Dashboard process
                          (SQLite, low priority)                         (curses)
```

Four processes and three shared-memory files. Each shared structure has exactly one writer.

**Life of one order:** the firehose creates an order and takes a timestamp → packs it into 32
bytes in the next ring slot → advances the write index (release store) → the engine sees the
index (acquire load), copies the record as a C struct and frees the slot → `_match` trades it
against the book → trades are copied into the trade ring → the ledger writes them to SQLite in
batches → about 10 times a second the engine publishes a snapshot that the dashboard draws.

## 5. Design of each module

### 5.1 Binary order record (`order_record.py`)
32 bytes, little-endian, format `"<QQqIB3x"`: order id, entry timestamp, price (integer ticks),
quantity, side, padding. A fixed size puts record N at a known offset; 32 bytes fit two records
in a 64-byte cache line. Prices are integers because floats round.

### 5.2 Shared-memory ring buffer (`ring_buffer.py`, `atomics.pyx`)
Single producer, single consumer, in a memory-mapped file. Indices only increase, so empty is
`write == read` and full is `write - read == capacity`; capacity is a power of two so the slot is
`index & (capacity - 1)`. Each index has one writer, so no lock is needed. When full, the producer
waits (backpressure) and nothing is overwritten. The two indices sit on separate cache lines to
avoid false sharing. Indices are written with **release** stores and read with **acquire** loads
(C atomics through Cython) so the reader never sees an index before the data it covers. The file
is created fully allocated, not sparse.

### 5.3 Firehose (`firehose.py`)
An asyncio coroutine generates seeded random orders and pushes them into the ring. Rate control
works per batch of 1,000 orders: it computes when the batch was due and sleeps if ahead, because
`asyncio.sleep` has about millisecond precision. Measured: 99,979 orders/s at a 100k target.

### 5.4 Order book (`cython_book.pyx`)
One array entry per price tick per side holds the head and tail of a FIFO queue and the total
quantity at that price. Orders live in a preallocated pool of C structs linked into those queues,
with a free stack for reuse. Finding a level and adding an order are O(1); matching takes from
the head of the best level (price priority, then time priority) at the resting order's price.
New orders are rejected up front if the pool is full, so an order is never half-applied. The
book also keeps a trade fingerprint in C: count, quantity, notional and a 64-bit FNV-1a checksum
over every trade in order.

Trade-offs: prices must lie in 1–10,000 ticks and memory is fixed up front (about 32 MB).

### 5.5 Engine loop in C (`consume_ring`)
The whole pop-and-match loop runs in Cython: it reads each record from shared memory as a C
struct, calls `_match`, and stores latency in a preallocated C array. No Python object is created
per order. The loop uses the same clock as Python's `perf_counter_ns` (`mach_absolute_time`,
tested) and measures its own pauses.

### 5.6 SQLite ledger (`ledger.py`)
The engine copies trades into a second ring. A separate process drains it in batches of up to
10,000, inserts each batch in one transaction (WAL mode), sleeps when idle, and runs at low CPU
priority (`nice 15`). At the end it reads every row back and recomputes the fingerprint.

### 5.7 Telemetry and dashboard (`telemetry.py`, `dashboard.py`)
The engine publishes a snapshot into a small shared-memory block about every 100 ms, protected
by a seqlock (the writer makes a counter odd while writing; readers retry). The dashboard is a
separate process; its screen is built by a pure function so it can be unit-tested.

### 5.8 Whale orders
A whale is an order that fills at least 500 shares across at least 3 price levels, detected
inside `_match`. The definition came from data: "3 levels" alone flagged 17,481 ordinary orders
in 1M, because levels near the mid are thin; adding the size rule gives 0 false positives.

## 6. Verification

| Check | Result |
|---|---|
| Unit and integration tests | 269 passing |
| Differential testing: Cython book vs pure-Python reference, 6 order-flow types x 6 seeds x 3,000 orders, compared after every order | 108,000 orders identical |
| Can the differential tests fail? (deliberate pricing bug planted) | 36 of 36 failed |
| Proof (a): 1M orders between processes, pickle disabled in both, every order checked | 0 mismatches |
| Pipeline fingerprint vs independent run and vs reference book | Equal |
| Ledger: fingerprint read back from SQLite vs engine | Equal (810,698 trades) |
| One-command readiness check (`scripts/review_check.py`) | 7 of 7 PASS |

## 7. Results

macOS 15.6.1, Apple M1 (4 performance + 4 efficiency cores), Python 3.14.6, Cython 3.3.0.
Medians of repeated runs; scripts and raw JSON in `benchmarks/`.

| Measurement | Result |
|---|---|
| Orders between two processes: mmap ring vs `multiprocessing.Queue` | 1.69M vs 141k orders/s (~12x) |
| One order to bytes and back: struct / JSON / pickle | 594 / 2,293 / 3,660 ns |
| Firehose: unlimited / at 100k target | 831k / 99,979 orders/s |
| Matching: pure-Python reference / Cython `submit` / Cython `submit_raw` | 12.7k / 2.7M / 15.9M orders/s |
| Engine loop draining the ring: Python / C | 2.5M / 24.7M orders/s |
| Pipeline at 100k/s (C loop): p50 / p99 / p99.9 | 0.50 / 0.58 / 13 µs |
| Pipeline at 100k/s with ledger at `nice 15`: p50 / p99 / max | 0.54 / 0.58 / 35 µs |
| Ledger: 1M orders | 810,698 trades stored, engine never waited |

The Cython speedup is measured against a deliberately simple reference book (it re-sorts on
every order), not an optimised Python implementation; part of the gain is the data structure.

## 8. Investigations and bugs found

**Stale reads on ARM.** Identical seeded runs gave different trade counts. A checker showed the
engine sometimes read a slot's contents from one lap earlier: ARM may make the index store
visible before the data stores. About 3 errors per 3M orders; after switching to acquire/release
atomics, 0 in 6M checked orders, with no throughput cost.

**Tail latency.** Median latency was sub-microsecond, but the maximum reached milliseconds.
- Garbage collection: instrumented with `gc.callbacks`; the engine performed 0 collections
  (each per-order object is freed by reference counting). Ruled out.
- Python objects in the loop: removed by the C loop; p99 fell from 2.0 to 0.58 µs.
- Producer stalls: the slowest order was the same order as the firehose's slowest publish, and
  all sat on 128 KB boundaries of the ring file, which was sparse. Preallocating the file:
  0 of 48 boundary crossings stalled, vs 22 of 48.
- Background ledger: at normal priority it raised p99.9 from 7.8 to 423 µs; at `nice 15`, 7.1 µs.
- Remaining: the OS occasionally takes a core away (a hiccup meter saw gaps up to ~15 ms on a
  busy laptop).

Two flawed experiments were caught and corrected along the way (a run-order confound and a GIL
artefact from running a meter in a thread); both are documented in the notes.

## 9. Limitations

- Learning-grade: real trading systems use C++ or FPGAs and dedicated hardware.
- Worst-case latency depends on the OS; macOS offers no core isolation or pinning.
- Bounded price range (1–10,000 ticks); limit orders and cancels only (no market orders);
  cancels work in both books but are not yet sent through the ring (note 17).
- SQLite runs with `synchronous=NORMAL`, which can lose the last transactions on power loss.
- The websocket feed mentioned in the original brief was deferred (decision D16).
- Benchmarks come from one laptop; numbers vary with background load.

## 10. Future work

- Run on Linux with isolated cores (`isolcpus`, `taskset`, real-time scheduling) and compare tails.
- Market orders, and a cancel record type in the ring (book-level cancellation added 11 Nov, note 17).
- Generate orders in C to remove the firehose bottleneck (~800k/s vs the engine's 24.7M/s).
- A websocket market-data feed as an additional asyncio producer.

## 11. Timeline

| Period | Work |
|---|---|
| 10–17 Oct | Setup, reference order book, invariant tests, baseline benchmark |
| 18–24 Oct | Binary records, ring buffer, IPC benchmarks, firehose, 1M demo, Cython order book, differential tests |
| 25–28 Oct | Pipeline and fingerprint, dashboard, ARM ordering fix, tail-latency investigation, C engine loop |
| 29 Oct – 2 Nov | No work |
| 3 Nov | Sparse-file fix, SQLite ledger, whale detection |
| 4–9 Nov | No work |
| 10 Nov | Project report, presentation outline, benchmark runner |
| 11 Nov | Order cancellation in both books (after the internship period) |

## 12. Conclusion

With shared memory, fixed binary records and a compiled matching loop, a Python-based system
reached sub-microsecond typical latency and millions of orders per second on a laptop, with
correctness checked against an independent reference. The most valuable part of the project
was measuring rather than assuming: two real bugs and several wrong hypotheses were found only
because every claim was tested.

Further detail: `docs/notes/` (one note per module), `docs/decisions.md` (29 design decisions),
`docs/viva-and-interview-prep.md`.
