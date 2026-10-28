# 13 - Week 3: Engine Loop in C (`consume_ring`)

## What changed
Until now the engine process ran a Python loop: `try_pop_raw()` built a tuple per order, then
Python called `submit_raw(...)`. Now the whole loop runs inside Cython,
`CythonOrderBook.consume_ring(ring, count, latencies, timeout_s, publish)`:

1. acquire-load the ring's write index;
2. copy the 32-byte record out of shared memory as a C struct (`OrderRecord`, same layout as
   `"<QQqIB3x"`; a test checks it is 32 bytes);
3. release-store the read index (the slot is free once our copy is done);
4. validate side/price/quantity (corrupt record -> ValueError) and pool space;
5. `_match` (C) and write latency = now - entry timestamp into a preallocated C int64 array.

**No Python object is created per order** (the Week 3 goal in the brief). The only Python call
inside the loop is the telemetry `publish` callback, about every 100 ms.
`python -m chronosmatch.engine --loop python` keeps the old loop for comparison.

## The clock must be the same clock
Latency subtracts the firehose's Python timestamp from a C timestamp, so both must read the same
clock. `time.get_clock_info("perf_counter")` reports `mach_absolute_time()` on macOS; the C loop
calls `mach_absolute_time()` and converts ticks to ns with the same integer formula CPython uses.
Test: over 1,000 samples, the C clock always fell between two `perf_counter_ns()` readings.

## The loop measures its own pauses
A spinning C loop iterates every few tens of nanoseconds, so the gap between consecutive
iterations is a built-in hiccup meter for the engine process itself (its own `publish` calls are
excluded).

## Results (28 Oct, Apple M1, Python 3.14.6; `benchmarks/bench_engine_loop.py`)
**A. Engine capacity** (ring pre-filled with 1M orders, one loop drains it, 3 interleaved runs):
| Loop | Median orders/sec |
|---|---|
| Python loop | 2,499,913 |
| **C loop** | **24,651,338** (9.9x) |
Identical trade fingerprints in every run.

**B. Pipeline at 100k orders/s** (separate processes, 300k orders, 5 interleaved runs, medians):
| Loop | p50 | p99 | p99.9 | max |
|---|---|---|---|---|
| Python | 0.71 us | 2.0 us | 19.8 us | 272 us |
| **C** | **0.50 us** | **0.58 us** | 13.1 us | 303 us |

C-loop pauses per run (longest gap between iterations): 131, 59, 78, 66, 84 us; never > 1 ms.
Max latency in the same runs: 310, 257, 221, 303, 409 us.

Also: 1M-order pipeline with the C loop: 818,808 orders/s (firehose-limited), p50 0.5 us,
p99 0.58 us, PASS; 100k-order run equal to the reference book.

## Honest reading
- The C loop makes the engine ~10x faster and the typical latency better (p99 3.4x lower).
  The firehose (Python creating Order objects) is now by far the bottleneck: ~820k/s vs the
  engine's 24.7M/s capacity.
- **The worst spikes are not caused by the engine being paused.** In every C run the engine's
  longest pause (59-131 us) was much shorter than the slowest order (221-409 us). This revises
  note 12: OS preemption of the *engine* explains pauses up to ~130 us here, not the maximum.
- **New hypothesis (untested):** the delay happens before the order is visible. The firehose
  takes the timestamp and *then* writes the record and publishes the index; if the OS pauses the
  firehose between those steps, that one order's latency includes the pause. This fits "only a
  few orders are slow" (p99.9 is fine, max is not). Next step: measure stamp-to-publish time
  inside the firehose.
- On this run no pause exceeded 1 ms; the ~15 ms gaps seen on 27 Oct depend on what else the
  machine is doing.

## Gotcha
Cython's generated C for any module using Python string comparisons triggers one clang warning
(`-Wunreachable-code` in `__Pyx__PyUnicode_EqualsUCS4`). It is in Cython's helper code, not ours.
