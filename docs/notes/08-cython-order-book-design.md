# 08 - Cython Order Book: Design

Written before the code, as required. Implementation: `src/chronosmatch/cython_book.pyx`.

## What it must do
Same behaviour as the reference book (note 02): price-time priority, trades at the resting
price, partial fills, remainder rests. But fast, and with no Python objects inside the core
loop (Week 3 goal), so the design uses C arrays and C structs from day one.

## Data layout

    prices are integer ticks 1..MAX_PRICE (config.BOOK_MAX_PRICE_TICKS)

    BID side, one entry per price tick          ASK side, same shape
    bid_head[price] -> first node (oldest)      ask_head[price] -> ...
    bid_tail[price] -> last node (newest)       ask_tail[price] -> ...
    bid_qty[price]  =  total resting quantity   ask_qty[price]  =  ...

    node pool (preallocated array of C structs, size config.BOOK_MAX_RESTING_ORDERS)
    struct Node { order_id, price, remaining, next }   next = index of next node in the
                                                       same price level, or -1
    free stack: indices of unused nodes (pop to allocate, push to release)

    best_bid = highest price with bid_qty > 0  (0 means "no bids")
    best_ask = lowest price with ask_qty > 0   (MAX_PRICE + 1 means "no asks")

Each price level is a FIFO queue implemented as a singly linked list through the node pool:
append at the tail (new order), consume from the head (oldest first) -> time priority.

## Operation costs
| Operation | Cost |
|---|---|
| Find a price level | O(1): array index |
| Add resting order | O(1): pop free node, link at tail |
| Consume head of a level | O(1) |
| Best bid/ask lookup | O(1): stored |
| Update best after a level empties | O(gap): scan to the next non-empty tick |
| levels() snapshot for the dashboard | O(price range), outside the hot path |

## Alternatives rejected
| Option | Why not |
|---|---|
| Sorted list of levels (like the reference book) | O(n log n) re-sorting or O(n) inserts; Python objects. |
| Balanced tree / heap of prices (e.g. `std::map`) | O(log n) per lookup, pointer chasing, C++ dependency; arrays win when the price range is bounded. |
| `collections.deque` per level | Python objects in the hot loop, which triggers GC and refcounting. |
| malloc/free per order | Allocation cost and fragmentation; a preallocated pool is predictable. |

## Trade-offs and limits (say these in the viva)
- Prices must fit in 1..MAX_PRICE. Real exchanges use a bounded band around the last price
  for the same reason. Out-of-range prices raise ValueError.
- Memory is fixed up front: two arrays of MAX_PRICE+1 per side, plus the node pool
  (~32 bytes x 1M nodes = ~32 MB by default). A full pool raises OverflowError.
- If prices are spread thinly, finding the next best level after one empties scans empty ticks.
  Our order flow clusters around the mid price, so the gap is small.

## Build plan
- 22 Oct: toolchain, this design, book structure (resting orders, best prices, levels, FIFO).
- 24-25 Oct: matching (`submit`), then differential tests against the reference book on
  random order streams = mid-review proof (b), and a benchmark against the baseline.

## Implementation status (22 Oct)
`cython_book.pyx` compiles cleanly (Cython 3.3.0, Apple clang 17, `-O3`) and implements:
- `__cinit__`/`__dealloc__`: malloc/free of all arrays and the node pool; MemoryError on failure.
- `_alloc_node` / `_release_node`: O(1) free-stack pool; OverflowError when full.
- `_rest` (cdef, C integers only): link a node at the tail of its level, update level quantity,
  best price and totals.
- Python API: `rest(order)` (non-crossing only; rejects out-of-range prices and crossing
  orders), `best_bid`, `best_ask`, `spread`, `levels(side)`, `queue_order_ids(side, price)`,
  `total_resting_quantity`, `resting_order_count`, `free_nodes`.

Tests (`tests/test_cython_book_structure.py`, 13): empty book, invalid construction, config
defaults, best prices and spread, level aggregation, FIFO order at a price, out-of-range prices,
crossing orders rejected, pool full, and **identical levels/best prices/quantity to the reference
book** on 3,000 random non-crossing orders.

Gotcha: a test tried to build `Order(price=0)` to check the book's range check, but `Order`
already rejects it at construction. Prices below 1 can never reach the book.

Not yet: matching (`submit`), releasing nodes when orders fill, re-scanning the best price when a
level empties. Those come with the matching logic.

## Implementation status (23 Oct): matching
`_match` (cdef, C integers only) implements price-time priority:
1. Look at the best opposite price; stop if it no longer crosses (or the side is empty: the
   sentinels 0 / max_price + 1 can never cross a valid price, so no extra check is needed).
2. Consume that level's FIFO from the head: fill `min(remaining, resting)`, write a C trade
   record at the **resting** price, reduce level quantity and totals.
3. Fully filled resting order: unlink it and push its node back on the free stack.
4. Level empty: scan outward to the next non-empty price and store it as the new best.
5. Leftover quantity rests via `_rest`.

Two entry points share the core:
- `submit(order) -> list[Trade]`: Python objects in and out (same API as the reference book).
- `submit_raw(is_buy, order_id, price, quantity) -> int`: C integers in, trade count out; no
  Order/Trade objects (for benchmarks and the Week 3 hot path).

Tests:
- `tests/test_matching_behaviour.py`: 10 matching scenarios run on **both** books (20 tests).
- `tests/test_cython_book_edge_cases.py` (11): node recycling (2,000 orders through a 4-node
  pool), best-price rescans across wide gaps, side emptying, partially filled order keeps queue
  position, full pool rejects without changing the book, boundary prices 1 and max,
  submit_raw = submit, submit_raw input validation.
- Sanity check run on 23 Oct (not yet a committed test): 5 seeds x 20,000 random orders,
  Cython and reference produced identical trades (~16,100 per seed) and identical final books.
  The committed differential test is next.
