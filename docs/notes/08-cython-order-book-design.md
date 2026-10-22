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
