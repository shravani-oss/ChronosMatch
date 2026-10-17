"""Fixed-size binary layout of one order, used inside the shared-memory ring buffer.

Layout (little-endian, 32 bytes):

    offset  size  field
    0       8     order_id      unsigned 64-bit
    8       8     timestamp_ns  unsigned 64-bit (entry time; 0 if unused)
    16      8     price         signed 64-bit, integer ticks
    24      4     quantity      unsigned 32-bit
    28      1     side          0 = BUY, 1 = SELL
    29      3     padding       always zero

pack_into / unpack_from read and write directly at an offset inside an existing buffer
(the mmap), so no intermediate bytes object is created for the record.
"""

import struct

from chronosmatch import config
from chronosmatch.types import Order, Side

ORDER_STRUCT = struct.Struct(config.ORDER_RECORD_FORMAT)

_SIDE_TO_CODE = {Side.BUY: config.SIDE_CODE_BUY, Side.SELL: config.SIDE_CODE_SELL}
_CODE_TO_SIDE = {code: side for side, code in _SIDE_TO_CODE.items()}


def pack_order_into(buffer, offset: int, order: Order, timestamp_ns: int = 0) -> None:
    """Write `order` as 32 raw bytes into `buffer` starting at `offset`."""
    ORDER_STRUCT.pack_into(
        buffer,
        offset,
        order.order_id,
        timestamp_ns,
        order.price,
        order.quantity,
        _SIDE_TO_CODE[order.side],
    )


def unpack_order_from(buffer, offset: int) -> tuple[Order, int]:
    """Read the 32-byte record at `offset`; return (order, timestamp_ns)."""
    order_id, timestamp_ns, price, quantity, side_code = ORDER_STRUCT.unpack_from(buffer, offset)
    try:
        side = _CODE_TO_SIDE[side_code]
    except KeyError:
        raise ValueError(f"corrupt order record: unknown side code {side_code}") from None
    return Order(order_id, side, price, quantity), timestamp_ns
