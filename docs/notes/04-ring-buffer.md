# 04 - Shared-Memory Ring Buffer (`mmap`)

## What it does
A fixed-size circular queue of 32-byte order records, stored in a **memory-mapped file**.
One process (producer) writes orders, another (consumer) reads them, both touching the same
RAM. No pickle, no JSON, no sockets. Code: `src/chronosmatch/ring_buffer.py`.

## Where it sits

    Simulator --try_push--> [ RING BUFFER in mmap file ] --try_pop--> Matching engine

## File layout
| Bytes | Content | Written by |
|---|---|---|
| 0-63 | magic, version, capacity, slot size | creator, once |
| 64-127 | write_index (u64) | producer only |
| 128-191 | read_index (u64) | consumer only |
| 192+ | capacity x 32-byte slots | producer writes, consumer reads |

## How it works
- Indices only grow. Slot for index `i` is `i & (capacity - 1)` (same as `i % capacity`
  because capacity is a power of two, but cheaper).
- **Empty**: `write_index == read_index`. **Full**: `write_index - read_index == capacity`.
  Because indices never wrap, full and empty are never confused (a classic ring buffer bug).
- **Publish order**: producer writes the record, *then* advances `write_index`. Consumer reads
  the record, *then* advances `read_index`. The index is the "it's ready" signal.
- **Backpressure**: `try_push` returns `False` when full and writes nothing. The caller decides
  whether to retry, wait or drop. Nothing is overwritten.
- Each index has its own cache line so the two processes do not keep stealing the same
  64-byte line from each other ("false sharing").

## Concepts used (to be taught: mmap, ring buffers, SPSC, memory ordering)
`mmap`, file-backed shared memory, memoryview casts, SPSC, head/tail, wrap-around,
backpressure, false sharing.

## Design decisions
See D12 to D15 in `docs/decisions.md`.

## Tests
- `tests/test_ring_buffer.py`: capacity validation, file size, empty, round trip with
  timestamp, FIFO, full and recover, wrap-around (150 items through 4 slots), attach from a
  second handle, reject non-ring files, header cache-line separation.
- `tests/test_ring_buffer_two_process.py`: a separate OS process (spawn start method) pushes
  50,000 seeded orders through a 1,024-slot ring (about 49 wrap-arounds, constant full-buffer
  backpressure); the parent pops them and compares every field against the expected sequence.
  Run 20 times in a row on 2026-10-18: 20/20 passed (1,000,000 orders checked in total).
  This is groundwork for mid-review proof (a); the dedicated 1M demo script comes later.

## Bug found and fixed: stale reads on ARM (26 Oct) - say this in the viva
**What I originally wrote (18 Oct):** Python gives no memory-ordering guarantee, but the many
interpreter instructions between the two writes make a problem "extremely unlikely".
**That was wrong.**

**How it was found:** on 26 Oct the live dashboard showed slightly different trade counts for
identical seeded runs. Matching is deterministic, so the engine had to be receiving different
data. The 25 Oct pipeline demo then FAILED at 300k orders / 100k per second.

**Diagnosis:** a consumer comparing every record with the expected stream found that, e.g., at
index 232,038 it received order 166,503: exactly what that slot held one lap (65,536 slots)
earlier. The consumer had seen the new `write_index` but read the slot *before* the new bytes
were visible to its core. ARM CPUs (Apple Silicon) may make stores visible to other cores out of
order, and may perform loads out of order. Measured rate: **3 stale reads in 3,000,000 orders**
(plus 1 in another 900k), roughly 1 per million.
It became visible once the engine used `try_pop_raw` (25 Oct), which reads the slot sooner after
the index than `try_pop` did; that is why earlier tests (note 07) saw 0 mismatches.

**Fix:** `atomics.pyx` exposes C11-style atomics from the C compiler:
- producer: write record, then **release-store** `write_index` (data visible first);
- consumer: **acquire-load** `write_index`, then read the record;
- consumer frees a slot with a release-store of `read_index`; producer acquire-loads it before
  overwriting a slot.
The telemetry seqlock got the same treatment (plus fences).

**Evidence after the fix:** 6,000,000 orders (20 runs x 300k at 100k/s) with every record
checked: **0 stale reads**. At the old rate (~1 per million), a clean run of 6M would happen by
chance only about e^-6 = 0.25% of the time. Strong evidence, not a formal proof. Ring throughput
is unchanged (1.69M orders/sec vs 1.66M before, `benchmarks/bench_ipc.py`).

**Lesson for the viva:** "unlikely in practice" is not a correctness argument for concurrent
code; I stated a known risk, deferred it, and it turned into a real bug the moment the timing
changed. The fix belongs to the data structure, not to luck.
