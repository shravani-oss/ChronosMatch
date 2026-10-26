# 07 - Mid-Review Proof (a): 1M Orders Across Two Processes, No Pickle

## The claim
1,000,000 orders pass from one process to another through shared memory, without pickling.

## How to run it live

    source .venv/bin/activate
    PYTHONPATH=src python -m chronosmatch.demo_ipc                 # as fast as possible
    PYTHONPATH=src python -m chronosmatch.demo_ipc --rate 100000   # at the 100k/sec target

Exit code 0 and `RESULT: PASS` only if every order arrived intact and in order.

## How the demo proves each part of the claim
| Part of claim | Evidence |
|---|---|
| Two processes | The firehose is started with `subprocess` as a separate OS process (own PID, own interpreter). |
| Shared memory | Both sides map the same ring file; orders move as 32-byte records via `struct`. |
| No pickle | `--forbid-pickle` / `forbid_pickle()` replace pickle's public API with a function that raises, in **both** processes. Any pickling would crash the demo. multiprocessing is deliberately not used because it pickles internally. |
| 1M orders, intact | The receiver regenerates the same seeded stream and compares all 1,000,000 orders field by field: `mismatched orders: 0`. |
| The check can fail | `test_demo_reports_failure_when_orders_do_not_match` feeds a different expected stream and asserts FAIL. |

## Measured runs (2026-10-21, macOS 15.6.1, Apple Silicon, Python 3.14.6)
| Run | Producer rate | Receive rate | Full-buffer waits | Mismatches | Result |
|---|---|---|---|---|---|
| Unlimited #1 | 682,921/s | 640,002/s | 16,333 | 0 | PASS |
| Unlimited #2 | 609,150/s | 574,498/s | 16,270 | 0 | PASS |
| Unlimited #3 | 680,062/s | 637,220/s | 16,702 | 0 | PASS |
| Target 100k/s | 99,989/s | 100,075/s | 0 | 0 | PASS |

32,000,000 bytes moved per run (1M x 32-byte records).

## Honest reading
- Unlimited runs show ~16k full-buffer waits: the receiver also regenerates and compares each
  expected order, so it is slower than the producer and backpressure kicks in. No order was
  dropped, which is exactly what backpressure is for.
- Receive rate here (~575-640k/s) is below the raw ring benchmark (1.66M/s, note 05) because
  of that verification work and Order object creation on both sides.
- The pickle guard disables the public `pickle` API; code calling the C module `_pickle`
  directly would bypass it. Nothing in our code does, and the transport path is only
  `struct.pack_into` / `unpack_from` on the mmap.
- **Update 26 Oct:** the memory-ordering risk turned out to be a real bug (about 1 stale read per
  million orders with a faster consumer); this demo's 0 mismatches came from a slower consumer
  that did not expose it. Fixed with acquire/release atomics (note 04).

## Likely viva questions
- *How do you know it didn't pickle?* Pickle raises in both processes, and the demo passed.
- *Why not multiprocessing.Queue?* It pickles every object and copies through a pipe; it was
  11.9x slower in our benchmark (note 05).
- *What happens if the consumer is slow?* The ring fills, the producer waits (full_waits), and
  nothing is lost.
