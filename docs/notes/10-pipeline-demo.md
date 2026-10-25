# 10 - Full Pipeline: Firehose -> Ring -> Cython Engine

## What it does
Three processes, one shared memory ring:

    [firehose process]  --try_push-->  [ mmap ring ]  --try_pop_raw-->  [engine process]
    asyncio, stamps entry time         32-byte records                  Cython book, submit_raw
                                                                         prints JSON summary
    [demo process] creates the ring, starts both, computes the expected answer independently,
                   compares, prints PASS/FAIL

Run: `PYTHONPATH=src python -m chronosmatch.demo_pipeline` (add `--rate 100000`, or
`--count 200000 --reference` to also check against the pure-Python reference book).

## How correctness is verified without sending trades between processes
The Cython book keeps a **trade fingerprint** in C while it matches: trade count, total quantity,
total notional (price x quantity) and a 64-bit FNV-1a checksum over every trade's
(buy id, sell id, price, quantity) in order. `trade_digest.py` computes the same fingerprint in
pure Python. Equal fingerprints mean the same trades in the same order (a 64-bit collision is
astronomically unlikely). The engine sends only this 4-number fingerprint back, as one JSON
line after the run, so no trade data, and no pickle, crosses processes.

The demo compares the engine's fingerprint with:
1. a fresh Cython book fed the same seeded orders directly (no ring, no processes), and
2. with `--reference`, the reference book's trades run through `TradeDigest`.

## Measured runs (25 Oct, macOS 15.6.1, Apple Silicon, Python 3.14.6)
| Run | Firehose | Engine | Latency p50 / p99 / max | Fingerprint | Result |
|---|---|---|---|---|---|
| 1M unlimited #1 | 750,477/s | 750,521/s | 0.75 / 13.8 / 1,239 us | = expected | PASS |
| 1M unlimited #2 | 758,540/s | 759,562/s | 0.75 / 52.4 / 7,069 us | = expected | PASS |
| 1M at 100k/s | 99,989/s | 100,079/s | 0.75 / 5.2 / 13,804 us | = expected | PASS |
| 200k + reference | - | - | - | = expected = reference | PASS |
| 50k + reference | 763,508/s | 764,051/s | 0.75 / 2.0 / 479 us | = expected = reference | PASS |

All 1M runs gave the identical fingerprint (810,698 trades, checksum 17727127623483955780).
Latency = firehose entry timestamp -> just after the engine matched the order (includes waiting
in the ring). `perf_counter_ns` is a system-wide clock on macOS, so the two processes'
timestamps are comparable.

## Honest reading
- **The engine keeps up with the firehose** (same rate, 0 full-buffer waits), so the pipeline is
  limited by the firehose (~755k/s, Python creating Order objects), not by matching.
- **Typical latency is 0.75 us** (p50), far inside the 50 us goal. p99 is mostly below 50 us
  but one unlimited run reached 52.4 us.
- **The worst case is not under control: max 1.2 to 13.8 ms.** Likely causes: the OS pausing one
  of the spinning processes, and Python's garbage collector (both sides still create some Python
  objects). Not yet investigated. This is exactly the Week 3 work: remove Python objects from the
  hot loop, control GC, and measure again.
- The fingerprint added no measurable cost: `submit_raw` 15.80M/s vs 15.86M/s before (0.4%,
  within noise), measured with the benchmark's own function.

## Gotcha: two bad benchmark comparisons before the fair one
While checking the fingerprint's cost, a quick script first reported 13.7M/s (it called
`f(*row)`, a different calling style) and then 7.7M/s (the loop ran at module level, where every
variable is a dictionary lookup instead of a fast local). Only calling the benchmark's own
`run_raw` function gave a like-for-like number. Lesson: compare with identical code paths.
