# Glossary

Terms are added as they appear in the project.

| Term | Simple meaning |
|---|---|
| **Order** | One offer to buy or sell, e.g. "Buy 100 shares at 50". |
| **Trade** | The deal created when a buy order and a sell order are matched. |
| **Matching engine** | The program that takes orders in and produces trades (the "clerk"). |
| **Bid** | A buyer's offer: the maximum price they will pay. |
| **Ask (offer)** | A seller's offer: the minimum price they will accept. |
| **Best bid** | The highest bid currently available. |
| **Best ask** | The lowest ask currently available. |
| **Spread** | Best ask minus best bid. A trade becomes possible when the gap closes. |
| **Limit order** | "Buy/sell, but only at this price or better." Waits in the book if not matched. |
| **Market order** | "Buy/sell now at whatever price is available." Fills immediately, price not controlled. |
| **Microsecond (μs)** | One millionth of a second. |
| **Serialization** | Converting data to bytes/text (JSON, pickle) so it can be sent elsewhere. Slow. |
| **Shared memory (mmap)** | Memory that two processes can both read and write directly. |
| **Ring buffer** | A fixed-size circular queue in memory. |
| **Garbage collector (GC)** | Python's cleaner that sometimes pauses the program to free unused objects. |
| **Order book** | The clerk's notebook: all unmatched (resting) limit orders, bids on one side, asks on the other. |
| **Resting order** | A limit order that has not matched yet and waits in the book. |
| **Price level** | All resting orders at the same price. |
| **Price priority** | Better prices match first (lowest ask for a buyer, highest bid for a seller). |
| **Time priority** | At the same price, the order that arrived first matches first (FIFO). |
| **Partial fill** | An order matches only part of its quantity; the rest keeps waiting or continues to the next level. |
| **Crossing the spread** | Sending a bid at or above the best ask (or an ask at or below the best bid) so a trade happens immediately. |
| **Price improvement** | Trading at the resting order's price, which is better than the limit the incoming order allowed. |
| **Liquidity** | How easily you can trade without moving the price; a small spread usually means high liquidity. |
