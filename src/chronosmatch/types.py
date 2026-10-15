"""Plain-Python domain types: orders and trades.

These describe *what* an order is. How an order is laid out as raw bytes in shared
memory is a separate, later decision (see docs/decisions.md).
"""

from dataclasses import dataclass
from enum import Enum


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Order:
    """A limit order. Price is an integer number of ticks to avoid float rounding."""

    order_id: int
    side: Side
    price: int
    quantity: int

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError(f"price must be positive, got {self.price}")
        if self.quantity <= 0:
            raise ValueError(f"quantity must be positive, got {self.quantity}")


@dataclass(frozen=True)
class Trade:
    """A match between one buy order and one sell order."""

    buy_order_id: int
    sell_order_id: int
    price: int
    quantity: int
