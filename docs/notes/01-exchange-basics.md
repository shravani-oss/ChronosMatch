# 01 - Exchange Basics (part A)

## What it is
The vocabulary needed before building a matching engine.

## Concepts (simple words)
- **Bid**: buyer's maximum price. **Ask**: seller's minimum price.
- **Best bid** = highest bid. **Best ask** = lowest ask.
- **Spread** = best ask - best bid. No trade is possible while it is positive.
- **Limit order**: sets a price, may wait. **Market order**: fills now, price not controlled.

## Why it matters for the project
The order book holds only unmatched **limit orders**. Market orders consume them.
The dashboard shows best bid, best ask and spread.

## Toy code
See `learning/01_toy_order_book.py`: two lists of (price, quantity), compute best bid/ask,
spread, and whether a trade is possible (`best_bid >= best_ask`).

## Part B: order book, price-time priority, partial fills
- **Order book**: bids sorted highest first, asks sorted lowest first.
- **Price-time priority**: better price first; at the same price, earliest arrival first (FIFO).
- **Partial fill**: an order may match only part of its quantity. A resting order that is
  partly consumed stays in the book with the reduced quantity and keeps its place in the queue.
- Trades happen at the **resting order's price** (price improvement for the incoming order).

## Worked example (learning/02_toy_matching.py)
Asks: id1 50@51, id2 30@51, id3 40@52. Incoming: buy 100 @ 52.
Trades: 50@51 (id1), 30@51 (id2), 20@52 (id3). id3 stays with 20 left.

## Design implication for the engine
Each price level needs a FIFO queue, and the book needs fast access to the best bid and
best ask. Data structure options are covered later (sorted levels vs arrays indexed by tick).
