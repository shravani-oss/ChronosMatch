# ChronosMatch

Zero-copy high-frequency trading engine in Python + Cython.

## Modules
- **Cython Matching Engine** – Limit Order Book compiled to a C extension (C-structs and pointers, no Python objects).
- **Zero-Copy IPC Bus** – mmap + struct ring buffer shared between processes.
- **Market Simulator** – asyncio websocket client simulating a firehose of tick data.
- **Latency Monitor** – curses terminal dashboard showing end-to-end latency in microseconds.

## Setup (macOS)
```bash
xcode-select --install          # C compiler, needed for Cython later
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest                          # run the tests
```

## Layout
```
src/chronosmatch/   package code (config.py holds all constants)
tests/              pytest tests
docs/               notes, glossary, decisions, progress log
learning/           small throwaway toy scripts used while learning
```

## Mid-review demo: 1M orders between two processes, no pickle
```bash
PYTHONPATH=src python -m chronosmatch.demo_ipc                 # unlimited speed
PYTHONPATH=src python -m chronosmatch.demo_ipc --rate 100000   # at the 100k/sec target
```
The firehose runs as a separate process, pickle is disabled in both processes, and every one of
the 1,000,000 orders is checked on arrival. Latest run: 1,000,000 received, 0 mismatches, PASS.
See `docs/notes/07-mid-review-ipc-demo.md`.

## Results so far
Measured on macOS 15.6.1, Apple Silicon, Python 3.14.6. Details in `docs/notes/`.

| What | Result |
|---|---|
| Orders between two processes, mmap ring buffer | **1.66M orders/sec** |
| Same, `multiprocessing.Queue` (pickle) | 139k orders/sec (ring is 11.9x faster) |
| Encode + decode one order: struct / JSON / pickle | 594 ns / 2,293 ns / 3,660 ns |
| asyncio firehose into the ring (separate process), unlimited | 831k orders/sec |
| asyncio firehose at the 100k/sec target | 99,979 orders/sec |
| Pure-Python reference order book (matching) | 12.8k orders/sec, p50 77 us |

Reproduce: `python benchmarks/bench_ipc.py`, `python benchmarks/bench_serialization.py`,
`python benchmarks/bench_reference_book.py`, `python benchmarks/bench_firehose.py`.

## Status
Project scaffolding. Work in progress.
