# 02 - Reference Order Book and Baseline Benchmark

## What it is
`src/chronosmatch/reference_book.py`: a simple, slow, pure-Python limit order book used as a
**correctness oracle**. The fast Cython engine must produce identical trades for identical input.

## Behaviour (rules)
- Price priority, then time priority (FIFO) at equal price.
- Trades execute at the resting order's price.
- Unfilled remainder rests in the book.
- `levels(side)` returns aggregated `(price, total_quantity)` per level, best price first
  (what the dashboard will display).

## How it works (key code idea)
On each `submit`, the opposite side is sorted best-price-first. Python's `sorted` is stable, so
equal prices keep their arrival order, which gives time priority for free. We then walk the list
until the order is filled or the next price no longer crosses.

## Tests
- 14 behaviour tests (empty book, no cross, exact match, price/time priority, partial fills,
  remainder rests, sell side, limit respected, levels).
- Randomized invariants over 5 seeds x 2,000 orders: book never crossed, quantity conserved,
  trade prices within both limits, levels add up to total resting quantity.

## Baseline benchmark (`benchmarks/bench_reference_book.py`)
Machine: macOS 15.6.1 arm64, Python 3.14.6. 20,000 orders, seed 0, 1 warm-up run, 5 measured runs.

| Metric | Result |
|---|---|
| Throughput (median of 5 runs) | **12,839 orders/sec** (range 12,766 to 12,855) |
| Per-order latency p50 | 77.4 μs |
| Per-order latency p99 | 169.5 μs |
| Per-order latency max | 209.7 μs |
| Trades per run | 16,093 |

Raw output: `benchmarks/results/reference_book.json`.

## Honest reading of the numbers
- This is about **8x below** the 100k orders/sec Week 1 firehose target, and p50 latency is above
  the 50 μs matching goal. That is expected: this class is built for clarity, not speed.
- Likely cause (a hypothesis, not yet profiled): it re-sorts a whole side on every submit and
  uses Python objects throughout.
- The Cython engine and the data-structure choice (sorted levels vs price-indexed arrays) are what
  should close the gap. We will rerun this exact benchmark against it for a fair comparison.
- Per-order timing adds its own timer overhead, so the latency percentiles are slightly inflated.
