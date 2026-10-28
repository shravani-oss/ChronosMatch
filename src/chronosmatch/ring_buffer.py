"""Single-producer / single-consumer (SPSC) ring buffer in a memory-mapped file.

Two processes open the same file and map it into memory, so they read and write the same RAM.
Orders are stored as fixed 32-byte records (see order_record.py); nothing is pickled.

File layout:
    [0, 64)      metadata: magic u32, version u32, capacity u64, slot_size u64
    [64, 128)    write_index u64  (written only by the producer)
    [128, 192)   read_index  u64  (written only by the consumer)
    [192, ...)   `capacity` slots of `slot_size` bytes

Indices only ever increase; the slot for index i is i & (capacity - 1).
    empty  <=>  write_index == read_index
    full   <=>  write_index - read_index == capacity
Publish order: the producer writes the record first, then advances write_index with a
*release* store; the consumer reads write_index with an *acquire* load before reading the
record. Without this pairing, ARM CPUs (Apple Silicon) were measured to let the consumer read a
slot's previous contents about once per million orders (see docs/notes/04-ring-buffer.md).
The consumer frees a slot the same way: it finishes reading, then release-stores read_index;
the producer acquire-loads read_index before overwriting a slot.
"""

import mmap
import struct
from pathlib import Path
from types import TracebackType

from chronosmatch import config
from chronosmatch.atomics import AtomicU64
from chronosmatch.order_record import ORDER_STRUCT, pack_order_into, unpack_order_from
from chronosmatch.types import Order

_META = struct.Struct("<IIQQ")


class RingBuffer:
    """Use RingBuffer.create(...) in one process and RingBuffer.attach(...) in the other."""

    def __init__(self, file, mm: mmap.mmap) -> None:
        magic, version, capacity, slot_size = _META.unpack_from(mm, config.RING_META_OFFSET)
        if magic != config.RING_MAGIC or version != config.RING_VERSION:
            mm.close()
            file.close()
            raise ValueError("not a ChronosMatch ring buffer file (bad magic or version)")
        if slot_size != config.ORDER_RECORD_SIZE:
            mm.close()
            file.close()
            raise ValueError(f"slot size {slot_size} != {config.ORDER_RECORD_SIZE}")

        self._file = file
        self._mm = mm
        self._capacity = capacity
        self._mask = capacity - 1
        self._slot_size = slot_size
        # Indices live in shared memory; load() is an acquire load, store() a release store.
        self._write_index = AtomicU64(mm, config.RING_WRITE_INDEX_OFFSET)
        self._read_index = AtomicU64(mm, config.RING_READ_INDEX_OFFSET)

    @classmethod
    def create(cls, path: str | Path, capacity: int = config.RING_DEFAULT_CAPACITY) -> "RingBuffer":
        """Create (or overwrite) the ring file, zero-filled, with both indices at 0."""
        if capacity <= 0 or capacity & (capacity - 1):
            raise ValueError(f"capacity must be a positive power of two, got {capacity}")
        size = config.RING_HEADER_SIZE + capacity * config.ORDER_RECORD_SIZE
        with open(path, "wb") as f:
            f.truncate(size)
        file = open(path, "r+b")
        mm = mmap.mmap(file.fileno(), size)
        _META.pack_into(
            mm,
            config.RING_META_OFFSET,
            config.RING_MAGIC,
            config.RING_VERSION,
            capacity,
            config.ORDER_RECORD_SIZE,
        )
        return cls(file, mm)

    @classmethod
    def attach(cls, path: str | Path) -> "RingBuffer":
        """Map an existing ring file created by RingBuffer.create."""
        file = open(path, "r+b")
        mm = mmap.mmap(file.fileno(), 0)
        return cls(file, mm)

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def buffer(self) -> mmap.mmap:
        """The underlying mmap, for the Cython engine loop that reads slots directly."""
        return self._mm

    def __len__(self) -> int:
        return max(0, self._write_index.load() - self._read_index.load())

    def _slot_offset(self, index: int) -> int:
        return config.RING_HEADER_SIZE + (index & self._mask) * self._slot_size

    def try_push(self, order: Order, timestamp_ns: int = 0) -> bool:
        """Producer only. Write one order; return False (and write nothing) if full."""
        write = self._write_index.load()
        if write - self._read_index.load() >= self._capacity:  # acquire: consumer is done with the slot
            return False
        pack_order_into(self._mm, self._slot_offset(write), order, timestamp_ns)  # 1. data
        self._write_index.store(write + 1)  # 2. publish (release: data visible first)
        return True

    def try_pop(self) -> tuple[Order, int] | None:
        """Consumer only. Return (order, timestamp_ns), or None if empty."""
        read = self._read_index.load()
        if self._write_index.load() - read <= 0:  # acquire: the record is fully visible
            return None
        item = unpack_order_from(self._mm, self._slot_offset(read))  # 1. read data
        self._read_index.store(read + 1)  # 2. free the slot (release: reads finished first)
        return item

    def try_pop_raw(self) -> tuple[int, int, int, int, int] | None:
        """Consumer only. Like try_pop but returns plain integers and builds no Order object:
        (order_id, timestamp_ns, price, quantity, side_code), or None if empty."""
        read = self._read_index.load()
        if self._write_index.load() - read <= 0:  # acquire: the record is fully visible
            return None
        item = ORDER_STRUCT.unpack_from(self._mm, self._slot_offset(read))
        self._read_index.store(read + 1)
        return item

    def close(self) -> None:
        # Views into the mmap must be released before the mmap itself can close.
        self._write_index.release()
        self._read_index.release()
        self._mm.close()
        self._file.close()

    def __enter__(self) -> "RingBuffer":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
