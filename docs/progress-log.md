# Progress Log

## 2026-10-11
- Read project instructions (CLAUDE.md).
- Phase 0, Step 1: big-picture explanation written (docs/notes/00-big-picture.md).

## 2026-10-11 (later)
- Phase 0 Step 1 check questions answered correctly (matching engine, trade, slow handoffs, GC pauses, serialization).
- Phase 0 Step 2 prerequisite 1 part A taught: bid/ask, spread, limit vs market orders.
- Added glossary, exchange-basics note and a toy order book script.

## 2026-10-12
- Reviewed answers on bid/ask, spread and order types (corrected: spread = ask - bid, a bid at
  52 against a best ask of 51 trades immediately, market sells risk low prices).
- Taught part B of exchange basics: order book, price-time priority, partial fills.
- Added toy matching script and updated glossary and notes.

## 2026-10-13
- Set up environment: venv, pinned requirements.txt (pytest), Xcode CLT confirmed.
- Added src/chronosmatch package skeleton and central config.
- Added pytest configuration and smoke tests (3 passing); README now has setup steps and layout.

## 2026-10-14
- Added viva and interview prep Q&A for the big picture and exchange basics, with a draft
  2-minute project explanation.
- Started the design decisions log with the seven decisions made so far and the open ones.
