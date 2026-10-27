# Viva and Interview Prep

Questions and model answers, added phase by phase.

## How I'd explain this project in 2 minutes (draft, will be refined)
ChronosMatch is a learning-grade matching engine, the program an exchange uses to pair buy
and sell orders. A Python process writes orders as raw bytes into a memory-mapped ring
buffer, and a separate Cython process reads the same memory and matches orders with
price-time priority, so no JSON or pickle serialization is needed between processes.
A terminal dashboard shows best bid, best ask, spread and latency in microseconds.
It is not a real HFT system (those use C++ or hardware); it demonstrates the techniques:
zero-copy IPC and keeping Python objects out of the hot loop.

## Phase 0: Big picture

**Q: What problem does ChronosMatch solve?**
A: It pairs buy and sell orders quickly and in the right order, and it shows how to move
order data between processes without serialization and without garbage-collection pauses.

**Q: Why is plain Python considered a poor fit for high-frequency trading?**
A: Two reasons: passing data between processes normally needs serialization (JSON/pickle),
which is slow, and the garbage collector can pause the program at unpredictable times,
causing latency spikes.

**Q: What does "zero-copy" mean in this project?**
A: Two processes read and write the same bytes in shared memory, so the data is not copied
or converted between them.

**Q: Is this really an HFT engine?**
A: No. Real HFT uses C++ or FPGAs. This is a learning-grade engine that demonstrates the
core techniques, and I can state its limits honestly.

## Phase 0: Exchange basics

**Q: What is the difference between a bid and an ask?**
A: A bid is a buyer's maximum price; an ask is a seller's minimum price.

**Q: What is the spread, and what does a small spread mean?**
A: Spread = best ask - best bid. A small spread means buyers and sellers nearly agree, which
usually indicates a liquid market with cheap trading. A trade only happens when a bid
reaches or exceeds an ask.

**Q: Limit order vs market order?**
A: A limit order sets a price and may wait in the book. A market order fills immediately at
the best available prices, so you control speed but not price.

**Q: What is price-time priority?**
A: Better prices match first; at the same price, the earliest order matches first (FIFO).

**Q: What is a partial fill?**
A: An order matches only part of its quantity. An incoming order continues to the next
price level or rests in the book; a partly consumed resting order stays with reduced
quantity and keeps its place in the queue.

**Q: At what price does a trade execute?**
A: At the resting order's price, so the incoming order may get price improvement.

**Q: What happens if a buyer posts a bid at 52 and the best ask is 51?**
A: The buyer crosses the spread and trades immediately, at 51.

## Weeks 1-2: Binary order record (`struct`)

**Q: Why a fixed-size binary record instead of JSON?**
A: Every order is exactly 32 bytes, so order N sits at a known offset and can be written or read
in place with `struct.pack_into` / `unpack_from`. Measured: struct round trip 594 ns vs JSON
2,293 ns vs pickle 3,660 ns per order.

**Q: Why `<` in the format string and why 32 bytes?**
A: `<` fixes little-endian byte order with no automatic padding, so the layout is identical on
every machine and tests can check exact bytes. 32 is a power of two: two records per 64-byte
cache line. The timestamp field was reserved early so the layout would not change later.

## Weeks 1-2: Shared-memory ring buffer

**Q: How do two processes share data without serialization?**
A: Both map the same file with `mmap`, so they read and write the same physical RAM. Orders are
written as raw bytes into slots; only two 8-byte indices are exchanged.

**Q: How do you tell full from empty?**
A: The indices only ever increase. Empty: write == read. Full: write - read == capacity. The slot
is index & (capacity - 1), which is why capacity is a power of two.

**Q: Why is no lock needed?**
A: Single producer, single consumer: each index has exactly one writer. The producer owns
write_index, the consumer owns read_index.

**Q: What happens when the consumer is slower?**
A: Backpressure: `try_push` returns False and writes nothing; the producer waits and retries.
Nothing is overwritten or lost.

**Q: Tell me about a bug you found.** (Strong interview answer: say this one.)
A: On Apple Silicon the consumer occasionally, about once per million orders, read a slot's old
contents. ARM may make the index store visible before the data stores. I had noted the risk but
judged it unlikely; it surfaced when the dashboard showed different trade counts for identical
seeded runs. I confirmed it with a checker that showed the stale record was exactly one lap old,
then fixed it with release stores and acquire loads via C atomics from Cython. After the fix:
0 stale reads in 6M checked orders, with no throughput cost.

**Q: Why put indices on separate cache lines?**
A: To avoid false sharing: if both indices shared a 64-byte line, the two cores would keep
invalidating each other's cache on every update.

## Weeks 1-2: asyncio firehose

**Q: Why asyncio for the simulator?**
A: The firehose yields to the event loop every batch, so other tasks (a consumer in tests, a
future websocket feed or stats task) can run in the same process without threads.

**Q: How do you hit exactly 100k orders/sec?**
A: Pace by batch: after each 1,000 orders, compute when that batch was due (start + sent/rate)
and sleep if ahead. Per-order sleeps would be below asyncio's ~1 ms timer precision.
Measured 99,979 orders/sec at a 100k target.

## Weeks 1-2: Cython order book

**Q: What data structure does the order book use and why?**
A: One array entry per price tick per side, holding the head and tail of a FIFO queue and the
total quantity at that price. Orders live in a preallocated pool of C structs, linked into those
queues. Finding a level is O(1), adding an order is O(1), and matching takes from the head of
the best level. The trade-off is a bounded price range and fixed memory.

**Q: How do you guarantee price-time priority?**
A: Price: always match against the stored best opposite price. Time: within a price, consume
from the head of a FIFO linked list; new orders join at the tail.

**Q: What does Cython actually buy you here?**
A: C integers and structs instead of Python objects, compiled loops, and no allocation while
matching. Measured: 15.9M orders/sec with integer input vs 12.7k for our simple Python
reference. But that baseline is naive; part of the gain is the better data structure, part is
compiled code. With Python Order/Trade objects it drops to 2.7M/s, so object creation is now the
biggest cost.

**Q: What happens if the node pool is full?**
A: New orders are rejected before matching. Matching only frees nodes, so one free node up
front guarantees the remainder can rest; an order is never half-applied.

**Q: How do you know the matching is correct?**
A: Differential testing: the Cython book and a simple pure-Python reference book receive the
same random order streams (6 kinds of flow, including whales sweeping levels) and must produce
identical trades after every order and identical final books. I checked that the test can fail
by planting a pricing bug: 36 of 36 tests failed.

## Weeks 1-2: Pipeline, verification and dashboard

**Q: How do you verify the engine process without sending trades back?**
A: The book keeps a fingerprint in C while matching: trade count, total quantity, notional and a
64-bit FNV-1a checksum over every trade in order. Only those 4 numbers cross processes; they
must equal an independent run of the same orders.

**Q: How does the dashboard get live data without slowing the engine?**
A: The engine publishes a small snapshot into a shared-memory block about 10 times a second,
using a seqlock: readers retry if the writer was mid-update, and the writer never waits. The
dashboard is a separate process and only reads.

**Q: What is still weak?**
A: Tail latency. p50 is ~0.75 us end to end, but at a paced 100k/s the p99 varies from ~1 us to
~200 us between runs and max spikes reach ~18 ms. Likely OS scheduling and garbage collection;
that is the Week 3 work. The firehose (Python object creation) is the throughput bottleneck.

## How I'd explain this project in 2 minutes (updated 26 Oct)
ChronosMatch is a small matching engine, the component of an exchange that pairs buy and sell
orders. A simulator process generates orders at 100,000 per second and writes them as 32-byte
binary records into a ring buffer in shared memory. A separate engine process reads the same
memory, so there is no serialization: moving orders this way was about 12x faster than Python's
standard pickling queue. The engine is written in Cython with C arrays indexed by price and FIFO
queues per price, which gives price-time priority; it matches about 16 million orders per second
on raw integers, and end-to-end median latency is under a microsecond. I verified correctness by
comparing it against a simple reference implementation on over 100,000 random orders, and a
terminal dashboard shows the live order book. Along the way I found and fixed a real concurrency
bug on Apple Silicon: without acquire/release memory ordering, the reader occasionally saw stale
data. It's not a production HFT system; the honest remaining weakness is tail latency, which is
what I'm working on next.

## Week 3: Tail latency

**Q: Your p50 is under a microsecond but your max is milliseconds. Why?**
A: I tested two hypotheses. Garbage collection: I instrumented every GC run with `gc.callbacks`
and the engine performed zero collections, because each per-order object is freed immediately
by reference counting, so the collection threshold is never reached. Disabling GC made no
consistent difference. OS scheduling: a "hiccup meter" that just spins reading the clock saw
gaps of up to ~15 ms while the pipeline ran, the same size as the engine's spikes. On a laptop
with 4 performance cores and several spinning processes, the OS takes cores away.

**Q: How would a real trading system avoid that?**
A: Dedicated, isolated CPU cores (Linux `isolcpus`, pinning with `taskset`, real-time scheduling),
no other work on those cores, and busy-polling only on them. macOS has no hard core pinning.

**Q: What mistakes did you make while measuring?**
A: Two. I first ran all GC-on runs before all GC-off runs, and GC-off looked faster, but with
zero collections in both it could not be GC; interleaving the runs removed the difference. And
my first hiccup experiment ran the pipeline in a thread of the meter's process, so it measured
GIL hand-offs (~6.3 ms, switch interval 5 ms), not the OS.
