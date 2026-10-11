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

## Still to cover (part B)
Order book structure, price-time priority, partial fills.
