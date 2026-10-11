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
