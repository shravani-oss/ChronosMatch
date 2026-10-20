# 06 - asyncio Market Firehose

## What it does
A simulator process that generates mock orders and pushes them into the shared ring buffer,
either as fast as possible or at a target rate (default 100,000 orders/sec). Each order is
stamped with `time.perf_counter_ns()` as it enters the ring (for Week 3 latency).
Code: `src/chronosmatch/firehose.py`. CLI:

    python -m chronosmatch.firehose --ring /tmp/chronos.ring --count 1000000 --rate 100000

## Where it sits

    [ FIREHOSE process (asyncio) ] --try_push--> [ ring buffer ] --> matching engine

## How it works
- Loops over orders; `try_push` each one with the current timestamp.
- **Ring full** -> `await asyncio.sleep(0)`: yields to the event loop and retries (backpressure,
  nothing dropped). `full_waits` counts how often this happened.
- **Every batch** (1,000 orders): if a target rate is set, compute when this batch was due
  (`start + sent / rate`) and sleep if ahead of schedule; otherwise just yield.
- Pacing by batch instead of per order, because `asyncio.sleep` has roughly millisecond
  precision: at 100k/s one batch is 10 ms, which the event loop can schedule accurately.

## Concepts used (to be taught: asyncio)
Event loop, coroutines, `await`, `asyncio.sleep(0)` as a yield, `asyncio.gather`, rate
limiting by schedule, backpressure.

## Tests
- `tests/test_firehose.py`: order and timestamp correctness, empty stream, backpressure with a
  concurrent asyncio consumer in the same loop (8-slot ring, 2,000 orders), rate limit slows the
  stream, invalid arguments.
- `tests/test_firehose_two_process.py`: runs the real CLI as a separate OS process, consumes
  20,000 orders here and compares every one.

## Benchmark (`benchmarks/bench_firehose.py`, 2026-10-20)
macOS 15.6.1, Apple Silicon, Python 3.14.6. 500,000 orders per run, 3 runs, consumer draining
concurrently in another process.

| Mode | Median orders/sec | Range | Full-buffer waits |
|---|---|---|---|
| Unlimited | **830,571** | 817,746 to 840,948 | 0 |
| Target 100,000/sec | **99,979** | 99,979 to 99,980 | 0 |

## Honest reading
- The Week 1 target (100k orders/sec into the buffer) is met with about **8x headroom**, and the
  rate limiter hits the target within 0.02%.
- Unlimited rate (830k/s) is about half the raw ring rate (1.66M/s, note 05) because it includes
  creating each Order object and taking a timestamp per order.
- Zero full-buffer waits means the consumer (a plain pop loop) kept up. A real matching engine is
  slower (the reference book does 12.8k/s), so with it attached, backpressure will appear.
- The brief mentions a websocket feed; that is deferred (D16).
