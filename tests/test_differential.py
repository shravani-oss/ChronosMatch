"""Mid-review proof (b): the Cython book matches EXACTLY like the reference book.

Both books receive the same random order streams. After every single order, the trades must be
identical; at the end, the whole book (levels, best prices, quantities) must be identical.
The reference book is simple enough to check by hand, so agreement is evidence of correctness.
"""

import random
from collections.abc import Iterator

import pytest

from chronosmatch.cython_book import CythonOrderBook
from chronosmatch.reference_book import ReferenceOrderBook
from chronosmatch.types import Order, Side

ORDERS_PER_RUN = 3_000
SEEDS = range(6)


def order_stream(
    seed: int,
    count: int,
    mid: int,
    band: int,
    max_qty: int,
    buy_bias: float = 0.5,
    whale_prob: float = 0.0,
    whale_qty: int = 0,
) -> Iterator[Order]:
    """Random limit orders; optional side bias and occasional very large ("whale") orders."""
    rng = random.Random(seed)
    for order_id in range(1, count + 1):
        side = Side.BUY if rng.random() < buy_bias else Side.SELL
        price = mid + rng.randint(-band, band)
        qty = whale_qty if rng.random() < whale_prob else rng.randint(1, max_qty)
        yield Order(order_id, side, price, qty)


FLOWS = {
    # name: keyword arguments for order_stream
    "tight_band_many_crosses": dict(mid=100, band=2, max_qty=50),
    "wide_band_deep_book": dict(mid=500, band=200, max_qty=100),
    "buy_heavy_bursts": dict(mid=100, band=10, max_qty=80, buy_bias=0.8),
    "sell_heavy_bursts": dict(mid=100, band=10, max_qty=80, buy_bias=0.2),
    "whales_sweep_levels": dict(mid=100, band=8, max_qty=20, whale_prob=0.02, whale_qty=2_000),
    "single_lot_orders": dict(mid=100, band=3, max_qty=1),
}


def assert_books_identical(ref: ReferenceOrderBook, cy: CythonOrderBook) -> None:
    for side in (Side.BUY, Side.SELL):
        assert cy.levels(side) == ref.levels(side)
    assert (cy.best_bid, cy.best_ask, cy.spread) == (ref.best_bid, ref.best_ask, ref.spread)
    assert cy.total_resting_quantity == ref.total_resting_quantity


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("flow", list(FLOWS))
def test_cython_book_matches_reference_on_random_flow(flow: str, seed: int) -> None:
    ref = ReferenceOrderBook()
    cy = CythonOrderBook(max_price=1_000, capacity=ORDERS_PER_RUN)
    total_trades = 0
    for order in order_stream(seed, ORDERS_PER_RUN, **FLOWS[flow]):
        expected = ref.submit(order)
        assert cy.submit(order) == expected, f"diverged at order {order.order_id}"
        total_trades += len(expected)
    assert_books_identical(ref, cy)
    assert total_trades > 0  # guard: the flow really exercised matching


def test_whale_flow_really_sweeps_multiple_levels() -> None:
    """Guard: the whale flow must contain orders that clear several price levels at once."""
    ref = ReferenceOrderBook()
    widest = 0
    for order in order_stream(0, ORDERS_PER_RUN, **FLOWS["whales_sweep_levels"]):
        widest = max(widest, len({t.price for t in ref.submit(order)}))
    assert widest >= 3
