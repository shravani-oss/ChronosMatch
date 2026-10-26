# 11 - Live Terminal Dashboard (curses)

## What it does
Shows the live top of book while orders flow: best bid, best ask, spread, the best 5 price
levels per side (bids green, asks red), throughput, trades, recent latency p50/p99, progress.

    PYTHONPATH=src python -m chronosmatch.live                 # 2M orders at 100k/s (q to quit)
    PYTHONPATH=src python -m chronosmatch.live --rate 0        # unlimited speed
    PYTHONPATH=src python -m chronosmatch.live --headless      # plain-text frames, no curses

## Where it sits

    firehose --> [ring] --> engine --publish ~10x/s--> [telemetry block] --read--> dashboard
                                                       (shared memory, seqlock)

The dashboard is a **separate process**, so drawing the screen never slows matching. It never
talks to the engine directly; it only reads the telemetry block.

## Telemetry block (`telemetry.py`)
- A small mmap file: a sequence counter + one fixed-size `struct` payload (counts, best prices,
  rate, latency p50/p99 of the last 2,048 orders, 5 levels per side, done flag).
- **Seqlock:** writer sets seq odd, writes, sets seq even; reader reads seq, payload, seq again
  and accepts only if both are the same even number. The writer never waits for readers.
- Ordering enforced with acquire/release atomics and fences (same fix as the ring, note 04).
- The engine checks the clock every 1,024 orders and publishes at most every 100 ms. One
  publish measured at ~42 us (median), i.e. at 100k orders/s it can delay ~4 orders per 100 ms.
- `CythonOrderBook.top_levels(side, depth)` stops after `depth` levels, so it is cheap enough to
  call while running (unlike `levels()`, which walks the whole price range).

## Design: rendering is a pure function
`render_lines(snapshot) -> [(text, style)]` builds the whole screen without touching curses, so
it is unit-tested; curses only paints the lines. The same function powers `--headless`.

## Tests
`tests/test_telemetry.py` (9): round trip, empty values, depth limit, sequence parity, reader
refuses a half-written snapshot, wrong file, `top_levels`, engine's final snapshot.
`tests/test_dashboard.py` (7): waiting screen, top of book, progress/rate/latency, depth rows,
empty book, status, and a headless end-to-end run of `live`.
Curses mode was checked in a pseudo-terminal: draws RUNNING then DONE, quits on `q`, exit 0.

## Observations
- With the default random flow, very large quantities pile up at the edges of the generator's
  price band (e.g. 600k+ at 96 and 104-105): orders at extreme prices rarely cross, so they
  accumulate. It is a property of the simulator, not a bug.
- Building this dashboard is what exposed the ring's stale-read bug (note 04): identical seeded
  runs showed slightly different trade counts.
- Tail latency at a paced 100k/s varies widely between runs with or without the dashboard; an
  early run's p99 of ~75-112 us could not be attributed to telemetry (publish cost ~42 us every
  100 ms is far too small). Week 3.
