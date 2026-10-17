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

## Known limitation (important, say it in the viva)
Python gives no **memory-ordering guarantee**. On Apple Silicon (ARM), the CPU may in theory
make the index update visible to another core before the record bytes. In practice the many
interpreter instructions between the two writes make this extremely unlikely, and the
two-process test checks every record, but it is not a formal guarantee. The fix belongs in the
Cython engine (Week 3): C11 atomics with release (producer) / acquire (consumer) ordering.
The 8-byte index itself is written through a native 'Q' memoryview, which on 64-bit CPUs is a
single aligned store in practice.
