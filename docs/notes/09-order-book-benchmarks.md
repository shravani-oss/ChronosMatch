# 09 - Mid-Review Proof (b) and Order Book Benchmarks

## Proof (b): buy/sell orders match correctly
`tests/test_differential.py` sends the same random order streams to the Cython book and to the
simple pure-Python reference book, and checks after **every order** that the trades are
identical, then that the final books are identical (levels, best prices, quantities).

- 6 flows x 6 seeds x 3,000 orders = 108,000 orders, all identical:
  tight band (many crosses), wide band (deep book), buy-heavy, sell-heavy, whales that sweep
  several levels, and single-lot orders.
- Guard tests: every flow produces trades, and the whale flow really clears >= 3 levels at once.
- **The test can fail:** on 24 Oct a bug was planted on purpose (trades priced at the incoming
  order's price instead of the resting price). 36 of 36 differential tests failed. Reverted.
- Plus 20 shared rule tests (note 08) and 11 Cython edge-case tests.

Run it: `pytest tests/test_differential.py -v`

## Speed (`benchmarks/bench_order_books.py`, 24 Oct)
macOS 15.6.1, Apple Silicon, Python 3.14.6, Cython 3.3.0, clang -O3. Same seeded orders for
every mode, 1 warm-up + median of 5 runs. Raw output: `benchmarks/results/order_books.json`.

### Throughput
| Mode | 20k orders | 1M orders | vs reference |
|---|---|---|---|
| Reference (pure Python) | 12,747/s | (too slow) | 1x |
| Cython `submit` (Order in, Trade objects out) | 2,716,422/s | 2,689,961/s | 213x |
| Cython `submit_raw` (integers in, count out) | 15,908,785/s | 15,858,636/s | 1,248x |

Trades per run were identical across modes (16,093 for 20k; 810,698 for 1M).

### Per-order latency (20k orders)
| Mode | p50 | p99 | max |
|---|---|---|---|
| Reference | 77.8 us | 170.8 us | 2,453.6 us |
| Cython `submit` | 0.167 us | 1.459 us | 9.7 us |
| Cython `submit_raw` | 0.125 us | 0.167 us | 8.3 us |

Matching goal from the brief: under 50 us. Cython is far below it; the reference book is not.

## Honest reading (important for the viva)
- **"1,248x" is against a deliberately naive baseline.** The reference re-sorts a whole side on
  every order (note 02). A well-written pure-Python book (dict of deques, heaps) would be much
  faster than 12.7k/s. So the fair claim is "the Cython book is ~1,250x faster than our simple
  reference", **not** "Cython is 1,000x faster than Python". Part of the gain is the better data
  structure (O(1) arrays), part is compiled C code.
- **Python objects are now the main cost.** `submit` vs `submit_raw` is 2.7M vs 15.9M orders/sec:
  building Order/Trade objects costs about 5.8x the matching itself. Same lesson as note 05 and
  the reason for the Week 3 work.
- `submit_raw` still pays for the Python `for` loop and a method call per order (~63 ns per order
  in total). Moving the loop into Cython (reading straight from the ring) would remove that.
- **Timer limits:** `perf_counter_ns` on Apple Silicon ticks every ~41.7 ns (24 MHz), and one
  timer call pair costs ~42 ns. Sub-microsecond numbers above are therefore only accurate to
  about +/- 42 ns; p50 = 0.125 us is "3 ticks". Throughput numbers do not have this problem.
- The reference max of 2.45 ms is a single outlier, probably a GC pause or OS scheduling; not
  investigated yet (Week 3 topic).
- End-to-end pipeline speed (firehose -> ring -> engine) is not measured yet; the engine is not
  yet connected to the ring.
