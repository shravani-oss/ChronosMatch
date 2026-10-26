"""Tests for the acquire/release 64-bit integer helper."""

import mmap

import pytest

from chronosmatch.atomics import AtomicU64, fence_acquire, fence_release


def test_store_then_load_round_trip() -> None:
    buf = bytearray(64)
    a = AtomicU64(buf, 8)
    a.store(2**64 - 1)
    assert a.load() == 2**64 - 1
    assert buf[8:16] == b"\xff" * 8 and buf[:8] == bytes(8)


def test_value_lives_in_the_buffer_not_a_copy() -> None:
    buf = bytearray(16)
    AtomicU64(buf, 0).store(5)
    assert AtomicU64(buf, 0).load() == 5


@pytest.mark.parametrize("offset", [-8, 60, 4])
def test_bad_offsets_rejected(offset: int) -> None:
    with pytest.raises(ValueError):
        AtomicU64(bytearray(64), offset)


def test_release_frees_the_mmap_so_it_can_close() -> None:
    mm = mmap.mmap(-1, 4096)
    a = AtomicU64(mm, 64)
    a.store(7)
    a.release()
    with pytest.raises(ValueError, match="released"):
        a.load()
    mm.close()  # would raise BufferError if the view were still held


def test_fences_are_callable() -> None:
    fence_acquire()
    fence_release()
