# ChronosMatch

Zero-copy high-frequency trading engine in Python + Cython.

## Modules
- **Cython Matching Engine** – Limit Order Book compiled to a C extension (C-structs and pointers, no Python objects).
- **Zero-Copy IPC Bus** – mmap + struct ring buffer shared between processes.
- **Market Simulator** – asyncio websocket client simulating a firehose of tick data.
- **Latency Monitor** – curses terminal dashboard showing end-to-end latency in microseconds.

## Status
Project scaffolding. Work in progress.
