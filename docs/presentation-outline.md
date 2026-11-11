# ChronosMatch: Presentation Outline (final review, ~12 slides, ~10 minutes)

Each slide: title, what goes on it, and what to say. Numbers come from `docs/project-report.md`.

---

### 1. Title
- ChronosMatch: Zero-Copy Order Matching Engine in Python + Cython
- Name, internship, dates (10 Oct – 10 Nov 2026), GitHub link
- Say: "A small version of the program an exchange uses to match buyers and sellers."

### 2. The problem
- Exchanges match thousands of orders per second; latency in microseconds
- Python's two problems: serialization between processes, garbage-collector pauses
- Say: "The goal was to see how far Python can go with shared memory and compiled code, and measure it honestly."

### 3. Exchange basics (keep short)
- Order, bid/ask, spread, order book, price-time priority, trade
- Picture: a small order book with bids on the left, asks on the right
- Say: "Best price first; at the same price, whoever came first."

### 4. Architecture
- The 4-process diagram from the report (firehose, engine, ledger, dashboard; 3 shared-memory files)
- Say: "No process ever pickles or sends a message; they share memory."

### 5. Life of one order
- Numbered arrows on the diagram: create + timestamp → 32 bytes into ring → publish index →
  engine reads as C struct → match → trade ring → SQLite; snapshot → dashboard
- Say: walk through it slowly; this slide carries the whole design.

### 6. Zero-copy ring buffer
- Circular buffer picture: write index, read index, full/empty rule
- One writer per index → no locks; backpressure when full
- Result: 1.69M orders/s vs 141k with `multiprocessing.Queue` (~12x)

### 7. The order book in Cython
- Array indexed by price → FIFO queue per price → node pool
- O(1) level lookup; no Python objects while matching
- Result: engine loop 24.7M orders/s (C) vs 2.5M (Python loop)

### 8. Proving it is correct
- Differential testing: Cython book vs simple reference, 108,000 random orders, compared after every order
- Planted bug → 36/36 tests fail (tests can catch errors)
- 1M orders across processes with pickle disabled: 0 mismatches
- Ledger fingerprint read back from SQLite equals the engine's

### 9. Results table
- Ring 1.69M/s · firehose 99,979/s at target · engine 24.7M/s · latency p50 0.50 µs, p99 0.58 µs at 100k/s · 810,698 trades stored
- Say the caveat: the Cython speedup is against a deliberately simple reference.

### 10. Bugs found by measuring
- ARM memory ordering: stale reads ~1 in a million → acquire/release atomics → 0 in 6M
- Sparse ring file: ~200 µs stalls at 128 KB boundaries → preallocate → 0 of 48
- Ledger priority: p99.9 423 µs → `nice 15` → 7.1 µs
- Say: "Each one was found because a number didn't look right."

### 11. Live demo (2–3 minutes)
- `PYTHONPATH=src python -m chronosmatch.live` (dashboard, whales flash)
- Optional: `PYTHONPATH=src python -m chronosmatch.demo_pipeline --ledger trades.sqlite`
- Backup if the terminal misbehaves: `--headless`

### 12. Limitations and future work
- Learning-grade; OS can still pause processes (no core isolation on macOS)
- Limit orders and cancels (no market orders); bounded price range; websocket feed deferred
- Next: Linux with isolated cores, cancellations and market orders, C order generator
- Say: "What I learned most: measure instead of assuming."

---

**Before presenting:** close other apps, keep the charger in, run
`python scripts/review_check.py` (all PASS), and have the dashboard command ready in a terminal.
