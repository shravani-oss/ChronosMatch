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

## Status
Project scaffolding. Work in progress.
