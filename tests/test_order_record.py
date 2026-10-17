"""Tests for the 32-byte binary order record."""

import struct

import pytest

from chronosmatch import config
from chronosmatch.order_record import ORDER_STRUCT, pack_order_into, unpack_order_from
from chronosmatch.types import Order, Side

SIZE = config.ORDER_RECORD_SIZE


def test_record_size_matches_format() -> None:
    assert ORDER_STRUCT.size == SIZE == 32


@pytest.mark.parametrize("side", [Side.BUY, Side.SELL])
def test_round_trip(side: Side) -> None:
    buf = bytearray(SIZE)
    order = Order(order_id=2**63, side=side, price=123_456, quantity=4_000_000_000)
    pack_order_into(buf, 0, order, timestamp_ns=987_654_321)
    assert unpack_order_from(buf, 0) == (order, 987_654_321)


def test_exact_byte_layout_is_little_endian() -> None:
    buf = bytearray(SIZE)
    pack_order_into(buf, 0, Order(1, Side.SELL, 2, 3), timestamp_ns=4)
    expected = (
        (1).to_bytes(8, "little")
        + (4).to_bytes(8, "little")
        + (2).to_bytes(8, "little", signed=True)
        + (3).to_bytes(4, "little")
        + bytes([config.SIDE_CODE_SELL])
        + bytes(3)
    )
    assert bytes(buf) == expected


def test_pack_at_offset_leaves_neighbours_untouched() -> None:
    buf = bytearray(b"\xff" * (3 * SIZE))
    pack_order_into(buf, SIZE, Order(7, Side.BUY, 50, 10))
    assert buf[:SIZE] == b"\xff" * SIZE
    assert buf[2 * SIZE :] == b"\xff" * SIZE
    assert unpack_order_from(buf, SIZE) == (Order(7, Side.BUY, 50, 10), 0)


def test_unknown_side_code_is_rejected() -> None:
    buf = bytearray(SIZE)
    pack_order_into(buf, 0, Order(1, Side.BUY, 50, 10))
    buf[28] = 9
    with pytest.raises(ValueError, match="side code"):
        unpack_order_from(buf, 0)


def test_quantity_too_large_for_u32_raises() -> None:
    with pytest.raises(struct.error):
        pack_order_into(bytearray(SIZE), 0, Order(1, Side.BUY, 50, 2**32))


def test_buffer_too_small_raises() -> None:
    with pytest.raises(struct.error):
        pack_order_into(bytearray(SIZE - 1), 0, Order(1, Side.BUY, 50, 10))
