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

## Open decisions (to be made at design time)
- Ring buffer slot count and full-buffer policy (backpressure vs drop).
- Order book data structure (sorted levels vs array indexed by price tick).
