# 16 - Week 4: Whale Orders

## What it does
The brief asks the dashboard to highlight "whale" orders that clear several price levels. The
engine detects them inside the C matching core; the dashboard shows the count and the latest
whale, with a highlighted `>>> NEW WHALE <<<` banner for 2 seconds when a new one appears.

    PYTHONPATH=src python -m chronosmatch.live     # injects a large order every 20,000 orders

## Definition, chosen from measured data
A whale is an incoming order that **fills at least 500 shares across at least 3 price levels**
(`config.WHALE_MIN_QTY`, `WHALE_MIN_LEVELS`).

The first version used "trades at >= 3 levels" only. On 1M ordinary orders (max 100 shares) it
flagged **17,481** whales: levels near the mid are thin (often < 150 shares), so ordinary orders
sweep 3 of them about 1.8% of the time. Measured distribution of levels cleared per order:

| Levels traded at | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| Ordinary orders (999,950) | 554,285 | 319,258 | 108,812 | 16,388 | 1,170 | 37 | 0 |
| Injected 2,000-share orders (50) | 0 | 10 | 18 | 7 | 8 | 3 | 4 |

So size *and* levels are needed: with both rules, 1M ordinary orders give **0 whales**, and
**22 of the 50** injected large orders are whales. The other 28 were big but were absorbed by the
huge resting "walls" that build up at the edges of the simulator's price band (note 11) within
1-2 levels, so by the brief's definition they did not clear several levels.

## Implementation
- `_match` (C) counts each pass of its outer loop (one pass = one price level traded at). If the
  order qualifies it updates `whale_count` and the last whale (id, side, levels, filled quantity,
  first and last price). Works for `submit`, `submit_raw` and `consume_ring` alike; no extra pass
  over the trades.
- `generate_orders(..., whale_every=N)`: every N-th order becomes a 2,000-share order priced at the
  far edge of the band. The same random numbers are drawn as for a normal order, so the rest of
  the seeded stream is unchanged (tested). Default 0 keeps all existing demos and fingerprints
  identical. Firehose and live demo: `--whale-every N`.
- Telemetry carries the whale count and last whale; the dashboard renders a yellow line, reversed
  for 2 s after a new whale.

## Tests (`tests/test_whales.py`, 10)
Large order across enough levels is a whale; too few levels is not; small order across many thin
levels is not; sell-side prices; 100k ordinary orders give 0 whales; injection changes only every
N-th order; invalid arguments; telemetry round trip; dashboard line and flash.
Curses mode checked in a pseudo-terminal: the NEW WHALE banner appeared, `q` quit cleanly.
