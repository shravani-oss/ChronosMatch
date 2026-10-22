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
| **Byte** | 8 bits; the smallest addressable unit of memory. |
| **Fixed-size record** | Every item uses the same number of bytes, so item N starts at N x size. |
| **Endianness** | The order bytes of a multi-byte number are stored in. Little-endian = least significant byte first. |
| **`struct`** | Python module that converts numbers to and from raw bytes using a format string. |
| **Padding** | Unused bytes added so a record has a convenient size or alignment. |
| **Cache line** | The 64-byte chunk the CPU moves between RAM and its cache in one go. |
| **mmap** | Mapping a file into memory so reading/writing memory reads/writes the file; two processes mapping the same file share the same RAM. |
| **SPSC** | Single-producer / single-consumer: exactly one writer and one reader. Allows a lock-free design. |
| **Write index / read index** | Counters of how many items have been written / read. Their difference is how many items are waiting. |
| **Wrap-around** | After the last slot, the ring continues at slot 0 again. |
| **Backpressure** | When the consumer is slower, the full buffer pushes back on the producer instead of losing data. |
| **False sharing** | Two cores writing different variables that sit on the same cache line, slowing each other down. |
| **Memory ordering** | Whether other CPU cores see your writes in the order you made them. Not guaranteed on ARM without barriers. |
| **asyncio** | Python's library for running many tasks in one thread by switching between them at `await` points. |
| **Event loop** | The asyncio scheduler that decides which waiting task runs next. |
| **Coroutine** | An `async def` function; it can pause at `await` and resume later. |
| **Firehose** | A very high-volume, continuous stream of messages (here, mock orders). |
| **Rate limiting** | Deliberately slowing a sender to a target number of messages per second. |
| **Cython** | A language close to Python that compiles to C, allowing C types and structs for speed. |
| **`.pyx`** | A Cython source file; compiled into a C extension module (`.so`). |
| **`cdef`** | Cython keyword declaring C-level variables, functions or classes (no Python object overhead). |
| **Price tick** | The smallest price step; prices are stored as whole numbers of ticks. |
| **Node pool / free list** | A preallocated array of slots plus a stack of free slot indices, so no memory is allocated while running. |
| **Linked list** | Items that each store the index of the next item; here, the FIFO queue at one price level. |
