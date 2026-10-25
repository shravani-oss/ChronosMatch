"""Pure-Python version of the Cython book's trade fingerprint.

A fingerprint is (trade count, total quantity, total notional, checksum). The checksum is
64-bit FNV-1a over (buy_order_id, sell_order_id, price, quantity) of every trade, in order, so
two trade histories have the same fingerprint only if they contain the same trades in the
same order (barring an astronomically unlikely 64-bit collision).

This lets one process verify another's matching without sending any Trade objects.
"""

from collections.abc import Iterable

from chronosmatch.types import Trade

FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
_MASK_64 = (1 << 64) - 1

TradeStats = tuple[int, int, int, int]


class TradeDigest:
    def __init__(self) -> None:
        self.count = 0
        self.quantity = 0
        self.notional = 0
        self.checksum = FNV_OFFSET

    def add(self, trades: Iterable[Trade]) -> None:
        for t in trades:
            self.count += 1
            self.quantity += t.quantity
            self.notional += t.price * t.quantity
            h = self.checksum
            for value in (t.buy_order_id, t.sell_order_id, t.price, t.quantity):
                h = ((h ^ (value & _MASK_64)) * FNV_PRIME) & _MASK_64
            self.checksum = h

    @property
    def stats(self) -> TradeStats:
        return (self.count, self.quantity, self.notional, self.checksum)
