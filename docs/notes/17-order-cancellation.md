# 17 - Order Cancellation (added 11 Nov, after the internship period)

## What it does
`book.cancel(order_id, side, price)` removes a resting order from either book and returns the
quantity it still had (0 if it is not resting: already filled, cancelled, or never existed).

## Design
- The caller gives side and price, as many simplified venues require. The Cython book then walks
  only that price level's FIFO to find the order: O(orders at that price), and no extra
  `order_id -> node` index, so no Python objects are added to the matching path.
- Unlinking from the singly linked FIFO tracks the previous node; if the cancelled order was the
  tail, the tail moves back to the previous node (otherwise the next new order at that price
  would be linked to a freed node).
- Level quantity and totals are reduced, the node returns to the free pool, and if the level
  empties and was the best price, the best price is rescanned.
- Alternative not taken: cancel by order id alone, which needs an id -> node map (a C hash table,
  or a Python dict that would add objects per order).

## Tests (`tests/test_cancel.py`, 24)
Rule tests run on both books (remove, unknown/wrong side/wrong price, twice, after partial fill,
cancelled order no longer trades, best price moves, side empties); Cython FIFO order and node
reuse; and a differential test: 6 seeds x 3,000 orders with ~25% of steps cancelling a random
earlier order, where both books must return the same cancelled quantity, the same trades and the
same final book.

**The tests can fail:** removing the tail fix made 7 of them fail (11 Nov). Reverted.

## Not done
Cancels are not yet sent through the ring buffer (the order record has no "cancel" type), so the
pipeline demos still send only new orders.
