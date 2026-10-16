"""Seeded synthetic order stream.

Same seed -> same orders, so tests and benchmarks are reproducible. Prices cluster around a
mid price so buys and sells regularly cross and trades actually happen.
"""

import random
from collections.abc import Iterator

from chronosmatch import config
from chronosmatch.types import Order, Side


def generate_orders(
    count: int,
    seed: int = 0,
    mid_price: int = config.DEFAULT_MID_PRICE_TICKS,
    price_band: int = config.DEFAULT_PRICE_BAND_TICKS,
    max_quantity: int = config.DEFAULT_MAX_ORDER_QUANTITY,
) -> Iterator[Order]:
    """Yield `count` random limit orders with sequential ids starting at 1."""
    if count < 0:
        raise ValueError(f"count must be >= 0, got {count}")
    if price_band >= mid_price:
        raise ValueError("price_band must be smaller than mid_price so prices stay positive")
    if max_quantity < 1:
        raise ValueError(f"max_quantity must be >= 1, got {max_quantity}")

    rng = random.Random(seed)
    for order_id in range(1, count + 1):
        side = rng.choice((Side.BUY, Side.SELL))
        price = mid_price + rng.randint(-price_band, price_band)
        quantity = rng.randint(1, max_quantity)
        yield Order(order_id, side, price, quantity)
