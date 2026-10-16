"""Randomized invariant tests: properties that must hold for ANY order sequence."""

import pytest

from chronosmatch.order_generator import generate_orders
from chronosmatch.reference_book import ReferenceOrderBook

SEEDS = [0, 1, 2, 42, 1234]
ORDERS_PER_RUN = 2_000


@pytest.mark.parametrize("seed", SEEDS)
def test_book_is_never_crossed(seed: int) -> None:
    """After every order, best bid must be strictly below best ask (else a trade was missed)."""
    book = ReferenceOrderBook()
    for order in generate_orders(ORDERS_PER_RUN, seed=seed):
        book.submit(order)
        if book.best_bid is not None and book.best_ask is not None:
            assert book.best_bid < book.best_ask


@pytest.mark.parametrize("seed", SEEDS)
def test_quantity_is_conserved(seed: int) -> None:
    """Every share submitted is either still resting or was traded (counted on both sides)."""
    book = ReferenceOrderBook()
    submitted = 0
    traded = 0
    for order in generate_orders(ORDERS_PER_RUN, seed=seed):
        submitted += order.quantity
        traded += sum(t.quantity for t in book.submit(order))
    assert submitted == 2 * traded + book.total_resting_quantity


@pytest.mark.parametrize("seed", SEEDS)
def test_trades_respect_both_limits(seed: int) -> None:
    """A trade price never exceeds the buyer's limit or goes below the seller's limit."""
    book = ReferenceOrderBook()
    limits = {}
    for order in generate_orders(ORDERS_PER_RUN, seed=seed):
        limits[order.order_id] = order.price
        for trade in book.submit(order):
            assert trade.price <= limits[trade.buy_order_id]
            assert trade.price >= limits[trade.sell_order_id]


def test_generated_flow_actually_produces_trades() -> None:
    """Guard against vacuous tests: the random flow must trade, not just rest."""
    book = ReferenceOrderBook()
    total_trades = sum(len(book.submit(o)) for o in generate_orders(ORDERS_PER_RUN, seed=0))
    assert total_trades > 100
