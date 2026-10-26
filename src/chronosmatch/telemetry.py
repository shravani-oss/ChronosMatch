"""Live engine statistics in a small shared-memory block, read by the dashboard process.

One writer (the engine) and any number of readers. Consistency uses a *seqlock*:
    writer: seq += 1 (odd = "writing"), write payload, seq += 1 (even = "stable")
    reader: read seq, read payload, read seq again; accept only if both reads are the same
            even number, otherwise retry.
So a reader never shows a half-written snapshot, and the writer never waits for readers.
(Same CPU memory-ordering caveat as the ring buffer, note 04.)

Layout: [0, 8) seq u64 | [8, 12) magic u32 | [64, ...) payload (struct below)
"""

import mmap
import struct
from dataclasses import dataclass
from pathlib import Path

from chronosmatch import config

_SEQ_OFFSET = 0
_MAGIC = struct.Struct("<I")
_MAGIC_OFFSET = 8
_PAYLOAD_OFFSET = config.CACHE_LINE_SIZE
_DEPTH = config.TELEMETRY_DEPTH
# processed, trades, traded_qty, best_bid, best_ask, updated_ns, rate, p50_ns, p99_ns,
# target_count, done, then DEPTH x (price, qty) bids, DEPTH x (price, qty) asks.
_PAYLOAD = struct.Struct("<QQQqqQQQQQQ" + "qq" * (2 * _DEPTH))
_SIZE = _PAYLOAD_OFFSET + _PAYLOAD.size
_READ_ATTEMPTS = 1_000


@dataclass(frozen=True)
class Snapshot:
    processed: int
    trades: int
    traded_qty: int
    best_bid: int | None
    best_ask: int | None
    updated_ns: int
    orders_per_sec: int
    latency_p50_ns: int
    latency_p99_ns: int
    target_count: int
    done: bool
    bids: list[tuple[int, int]]   # best first, empty levels omitted
    asks: list[tuple[int, int]]

    @property
    def spread(self) -> int | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid


class TelemetryBlock:
    def __init__(self, file, mm: mmap.mmap) -> None:
        (magic,) = _MAGIC.unpack_from(mm, _MAGIC_OFFSET)
        if magic != config.TELEMETRY_MAGIC:
            mm.close()
            file.close()
            raise ValueError("not a ChronosMatch telemetry file (bad magic)")
        self._file = file
        self._mm = mm
        view = memoryview(mm)
        self._seq = view[_SEQ_OFFSET : _SEQ_OFFSET + 8].cast("Q")
        view.release()

    @classmethod
    def create(cls, path: str | Path) -> "TelemetryBlock":
        with open(path, "wb") as f:
            f.truncate(_SIZE)
        file = open(path, "r+b")
        mm = mmap.mmap(file.fileno(), _SIZE)
        _MAGIC.pack_into(mm, _MAGIC_OFFSET, config.TELEMETRY_MAGIC)
        return cls(file, mm)

    @classmethod
    def attach(cls, path: str | Path) -> "TelemetryBlock":
        file = open(path, "r+b")
        return cls(file, mmap.mmap(file.fileno(), 0))

    def publish(self, snap: Snapshot) -> None:
        """Writer only."""
        levels: list[int] = []
        for side in (snap.bids, snap.asks):
            padded = list(side[:_DEPTH]) + [(0, 0)] * (_DEPTH - min(len(side), _DEPTH))
            for price, qty in padded:
                levels += [price, qty]
        seq = self._seq[0]
        self._seq[0] = seq + 1  # odd: writing
        _PAYLOAD.pack_into(
            self._mm, _PAYLOAD_OFFSET,
            snap.processed, snap.trades, snap.traded_qty,
            snap.best_bid or 0, snap.best_ask or 0, snap.updated_ns, snap.orders_per_sec,
            snap.latency_p50_ns, snap.latency_p99_ns, snap.target_count, int(snap.done),
            *levels,
        )
        self._seq[0] = seq + 2  # even: stable

    @property
    def sequence(self) -> int:
        return self._seq[0]

    def read(self) -> Snapshot | None:
        """A consistent snapshot, or None if nothing was published yet (or the writer is stuck)."""
        for _ in range(_READ_ATTEMPTS):
            before = self._seq[0]
            if before == 0:
                return None
            if before % 2:
                continue
            values = _PAYLOAD.unpack_from(self._mm, _PAYLOAD_OFFSET)
            if self._seq[0] == before:
                return _to_snapshot(values)
        return None

    def close(self) -> None:
        self._seq.release()
        self._mm.close()
        self._file.close()

    def __enter__(self) -> "TelemetryBlock":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _to_snapshot(values: tuple) -> Snapshot:
    (processed, trades, qty, bid, ask, updated, rate, p50, p99, target, done) = values[:11]
    flat = values[11:]
    pairs = [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
    bids = [p for p in pairs[:_DEPTH] if p[1] > 0]
    asks = [p for p in pairs[_DEPTH:] if p[1] > 0]
    return Snapshot(
        processed, trades, qty, bid or None, ask or None, updated, rate, p50, p99, target,
        bool(done), bids, asks,
    )
