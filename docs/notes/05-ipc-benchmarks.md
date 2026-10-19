# 05 - IPC and Serialization Benchmarks

Machine: macOS 15.6.1, Apple Silicon (arm64), Python 3.14.6. Measured 2026-10-19.
Scripts and raw JSON results are in `benchmarks/`.

## 1. Two-process throughput (`benchmarks/bench_ipc.py`)
500,000 orders from a producer process to a consumer process, 3 measured runs.
Order generation and process start-up are excluded (producer pre-generates, then waits for "go").

| Transport | Median orders/sec | Range |
|---|---|---|
| **mmap ring buffer (struct, zero-copy)** | **1,658,383** | 1,621,683 to 1,689,451 |
| `multiprocessing.Queue` (pickle + pipe) | 139,082 | 128,120 to 144,303 |

**Ring buffer is 11.9x faster** than the standard pickling queue, and about **16x above** the
Week 1 target of 100,000 orders/sec for the transport.

## 2. Encode + decode one order (`benchmarks/bench_serialization.py`)
Round trip ending in an `Order` object, 200,000 orders, median of 5 runs.

| Method | ns per order | Bytes per order | vs struct |
|---|---|---|---|
| **struct** (`pack_into`/`unpack_from`) | **594** | 32 | 1.0x |
| JSON | 2,293 | 19 | 3.9x slower |
| pickle | 3,660 | 116 | 6.2x slower |
| struct, raw numbers only (no `Order` object) | 227 | 32 | 0.38x |

## Honest reading
- The transport is no longer the bottleneck. The pure-Python reference book matches only
  ~12,800 orders/sec (note 02), over 100x slower than the ring delivers them. The matching
  engine is where the Cython work must go.
- About 62% of the struct round trip (594 ns -> 227 ns) is building the Python `Order`
  object, not handling bytes. This is measured evidence for Week 3: keep Python objects out of
  the hot loop.
- JSON is *smaller* here (19 bytes) because these test numbers are short; its size grows with
  digit count, and it is still ~4x slower. Our record spends 8 bytes on a timestamp and 3 on
  padding by design (D11).
- The queue comparison includes pickle *and* a pipe (kernel copies); the ring avoids both. The
  two effects are not separated here.
- Throughput was measured with both processes spinning on separate cores; numbers depend on
  the machine and on what else is running.
- Memory-ordering caveat from note 04 still applies.
