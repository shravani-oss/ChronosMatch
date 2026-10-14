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
