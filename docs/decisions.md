# Design and Project Decisions

Each entry: decision, alternatives, reason.

## D1: Single repository, commit directly to `main`
- Alternatives: feature branches with pull requests.
- Reason: solo project; the internship SOP grades commit history on `main`.

## D2: `src/` layout with one package, `chronosmatch`
- Alternatives: flat scripts in the repo root.
- Reason: tests import the installed-style package, imports stay explicit, and the layout is
  what reviewers expect for a placement-grade project.

## D3: All constants live in `src/chronosmatch/config.py`
- Alternatives: literals inside modules; a YAML/JSON config file.
- Reason: avoids magic numbers; a Python module gives type hints and zero parsing cost.

## D4: pytest with `pythonpath = ["src"]` in `pyproject.toml`
- Alternatives: `pip install -e .`; setting `PYTHONPATH` by hand.
- Reason: simplest reproducible test setup for now; revisit when packaging for Cython.

## D5: Pinned `requirements.txt`
- Alternatives: unpinned dependencies.
- Reason: reproducible benchmarks and environment, important when quoting measured numbers.

## D6: Keep `CLAUDE.md` out of version control
- Alternatives: track it in the repo.
- Reason: it is a personal working file, not project documentation. Listed in `.gitignore`.

## D7: Throwaway toy scripts live in `learning/`, not `src/`
- Alternatives: mixing them with package code.
- Reason: keeps the engine code clean while the learning trail stays visible.

## D8: Order prices are integer ticks, not floats
- Alternatives: `float` prices; `decimal.Decimal`.
- Reason: floats round (0.1 + 0.2 != 0.3) which breaks equality at a price level; integers are
  exact and map directly to a C integer in the Cython engine later.

## D9: Keep a slow pure-Python reference order book as a correctness oracle
- Alternatives: test only the Cython engine against hand-written expectations.
- Reason: one obviously-correct implementation lets us compare the fast engine against it on
  the same random order sequences, which is the proof needed for mid review (b).

## D10: Seeded random order generator, and invariant tests on top of it
- Alternatives: hand-written order lists only; unseeded randomness.
- Reason: a fixed seed makes failures reproducible and benchmarks comparable. Invariants (book
  never crossed, quantity conserved, trade prices within both limits) catch bugs that
  hand-picked examples miss. One guard test proves the flow really produces trades.

## D11: 32-byte little-endian order record with explicit padding
- Layout: order_id u64, timestamp_ns u64, price i64, quantity u32, side u8, 3 pad bytes.
- Alternatives: native `@` format (platform-dependent padding/size); a 24-byte record without
  timestamp; floats for price.
- Reason: `<` makes size and byte order identical on every machine and lets tests check exact
  bytes. 32 is a power of two, so two records fit exactly in a 64-byte cache line. The timestamp
  field is reserved now so the layout does not change in Week 3. u32 quantity (max ~4.29B) is
  ample for a simulator.

## D12: File-backed `mmap` for shared memory
- Alternatives: `multiprocessing.shared_memory`; pipes/queues; sockets.
- Reason: the brief asks for mmap; a file path is all a second, unrelated process needs to
  attach; the file can be inspected for debugging. Queues and pipes pickle, which we must avoid.

## D13: SPSC ring with ever-increasing indices and power-of-two capacity
- Alternatives: wrap indices at capacity and keep one slot empty to tell full from empty;
  a "count" field updated by both sides.
- Reason: ever-increasing u64 indices make full vs empty unambiguous and use every slot; each
  index has exactly one writer, so no locks are needed. A power of two turns modulo into a
  bit-mask.

## D14: Full buffer -> `try_push` returns False (backpressure), never overwrite
- Alternatives: overwrite the oldest unread order; block inside the buffer.
- Reason: losing orders silently is unacceptable for a matching engine. Returning False keeps
  the buffer simple and lets the producer choose (spin, sleep or count drops).

## D15: Header with metadata, write index and read index on separate 64-byte cache lines
- Alternatives: pack all header fields together.
- Reason: avoids false sharing between producer and consumer cores; the magic/version check
  catches attaching to the wrong file.

## D16: Firehose writes straight into the ring; websocket feed deferred
- Alternatives: a mock websocket server plus a websocket client feeding the ring now.
- Reason: the Week 1 plan asks for an asyncio firehose into the buffer, and the mid review
  checks IPC and matching. A websocket hop adds a dependency and network latency that would
  blur the zero-copy measurements. It can be added later as another asyncio producer
  (Week 4 polish) without changing the ring.

## D17: Rate control by batch schedule, yielding to the event loop every batch
- Alternatives: `await asyncio.sleep(1/rate)` per order; a token bucket; no yielding.
- Reason: per-order sleeps are far below asyncio's ~1 ms timer precision and would cap the rate.
  Scheduling each 1,000-order batch against `start + sent/rate` self-corrects drift (measured
  99,979/s at a 100k target). Yielding every batch keeps other coroutines responsive.

## D18: Order book indexed by price tick (arrays), not a sorted structure
- Alternatives: sorted list of levels; balanced tree/heap; dict of price -> deque.
- Reason: O(1) access to any level and to the best price; contiguous C arrays are
  cache-friendly. Cost: a bounded price range (1..BOOK_MAX_PRICE_TICKS) and fixed memory.

## D19: Preallocated node pool + free stack; each level is a linked FIFO through the pool
- Alternatives: malloc/free per order; Python deque per level.
- Reason: no allocation and no Python objects while matching (Week 3 goal); FIFO by linking at
  the tail and consuming from the head gives time priority in O(1).

## D20: Build with `python setup.py build_ext --inplace`
- Alternatives: `pip install -e .`; pyximport at import time.
- Reason: simplest explicit compile step with visible compiler output; the compiled .so lands
  next to the Python modules in src/chronosmatch so tests import it unchanged. Generated .c/.so
  files are git-ignored.

## D21: Reject a new order up front when the node pool is full
- Alternatives: match first, then fail if the remainder cannot rest; grow the pool.
- Reason: matching only frees nodes, so one free node before matching guarantees the remainder
  can rest. Checking first means an order is either fully applied or not applied at all; failing
  halfway would leave trades applied but unreported. Growing the pool would mean reallocating
  in the hot path. Cost: while the pool is full, even an order that would fully fill is rejected.

## D22: Trades written to a preallocated C buffer; two APIs over one core
- Alternatives: append Python Trade objects inside the matching loop.
- Reason: keeps the matching loop free of Python objects. `submit` converts to Trade objects
  afterwards for tests and normal use; `submit_raw` skips objects entirely. The buffer holds
  `capacity` records, the most trades one order can produce (one per resting order).

## D23: Verify the engine with a trade fingerprint, not by shipping trades back
- Alternatives: send every trade back to the demo process; write trades to a second ring;
  trust the differential tests only.
- Reason: a 4-number fingerprint (count, quantity, notional, 64-bit FNV-1a checksum of the
  ordered trades) proves the same trades in the same order while keeping the data path free of
  Python objects and pickle. It is computed in C during matching at no measurable cost.
  A second "trades" ring (for the SQLite ledger) is a Week 4 item.

## D24: Engine loop stays in Python for now, using raw integers
- Alternatives: move the pop-and-match loop into Cython, reading the mmap directly.
- Reason: the Python loop with `try_pop_raw` + `submit_raw` already outruns the firehose
  (the engine is never the bottleneck). Moving the loop into Cython, with atomics for the ring
  indices, is the Week 3 step and will be measured against today's numbers.

## D25: Ring and telemetry indices use acquire/release atomics (Cython + C built-ins)
- Alternatives: keep plain Python memoryview writes and rely on timing; a lock (mutex) in shared
  memory; a pipe/semaphore to signal new data.
- Reason: a measured bug (~1 stale read per million orders on Apple Silicon) proved plain writes
  are not safe. Release/acquire is the minimal, lock-free ordering an SPSC ring needs; a lock or
  a syscall per order would cost far more. Measured cost: none (1.69M vs 1.66M orders/sec).

## Open decisions (to be made at design time)
