"""Tests for the Cython order book's data structure (resting orders, no matching yet)."""

import pytest

from chronosmatch.cython_book import CythonOrderBook
from chronosmatch.order_generator import generate_orders
from chronosmatch.reference_book import ReferenceOrderBook
from chronosmatch.types import Order, Side


def buy(order_id: int, price: int, qty: int) -> Order:
    return Order(order_id, Side.BUY, price, qty)


def sell(order_id: int, price: int, qty: int) -> Order:
    return Order(order_id, Side.SELL, price, qty)


@pytest.fixture
def book() -> CythonOrderBook:
    return CythonOrderBook(max_price=200, capacity=64)


def test_empty_book(book: CythonOrderBook) -> None:
    assert (book.best_bid, book.best_ask, book.spread) == (None, None, None)
    assert book.levels(Side.BUY) == [] and book.levels(Side.SELL) == []
    assert book.total_resting_quantity == 0 and book.resting_order_count == 0
    assert book.free_nodes == 64


@pytest.mark.parametrize("kwargs", [{"max_price": 0}, {"capacity": 0}, {"max_price": -1}])
def test_invalid_construction(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        CythonOrderBook(**kwargs)


def test_default_sizes_come_from_config() -> None:
    from chronosmatch import config

    assert CythonOrderBook().free_nodes == config.BOOK_MAX_RESTING_ORDERS


def test_best_prices_and_spread(book: CythonOrderBook) -> None:
    book.rest(buy(1, 50, 100))
    book.rest(buy(2, 49, 200))
    book.rest(sell(3, 51, 80))
    book.rest(sell(4, 53, 60))
    assert (book.best_bid, book.best_ask, book.spread) == (50, 51, 1)


def test_levels_aggregate_and_sort_best_first(book: CythonOrderBook) -> None:
    for o in (buy(1, 50, 100), buy(2, 50, 40), buy(3, 48, 10), sell(4, 53, 5), sell(5, 51, 7)):
        book.rest(o)
    assert book.levels(Side.BUY) == [(50, 140), (48, 10)]
    assert book.levels(Side.SELL) == [(51, 7), (53, 5)]
    assert book.total_resting_quantity == 162 and book.resting_order_count == 5


def test_fifo_queue_keeps_arrival_order_at_one_price(book: CythonOrderBook) -> None:
    for order_id in (7, 3, 9):
        book.rest(sell(order_id, 60, 1))
    assert book.queue_order_ids(Side.SELL, 60) == [7, 3, 9]
    assert book.queue_order_ids(Side.BUY, 60) == []


@pytest.mark.parametrize("price", [201, 5_000])
def test_price_above_book_range_rejected(book: CythonOrderBook, price: int) -> None:
    # Prices below 1 never reach the book: Order itself rejects them.
    with pytest.raises(ValueError, match="outside"):
        book.rest(buy(1, price, 1))
    with pytest.raises(ValueError, match="outside"):
        book.queue_order_ids(Side.BUY, price)


def test_crossing_orders_are_rejected_by_rest(book: CythonOrderBook) -> None:
    book.rest(buy(1, 50, 10))
    book.rest(sell(2, 52, 10))
    with pytest.raises(ValueError, match="cross"):
        book.rest(buy(3, 52, 1))
    with pytest.raises(ValueError, match="cross"):
        book.rest(sell(4, 50, 1))
    assert book.resting_order_count == 2  # nothing was added


def test_node_pool_full_raises_overflow() -> None:
    small = CythonOrderBook(max_price=100, capacity=3)
    for i in range(3):
        small.rest(buy(i, 10, 1))
    assert small.free_nodes == 0
    with pytest.raises(OverflowError):
        small.rest(buy(99, 10, 1))
    assert small.resting_order_count == 3


def test_matches_reference_book_for_non_crossing_flow() -> None:
    """Bids below 100, asks above 100: nothing crosses, so both books must look identical."""
    cy = CythonOrderBook(max_price=1_000, capacity=5_000)
    ref = ReferenceOrderBook()
    for o in generate_orders(3_000, seed=11, mid_price=100, price_band=40):
        if (o.side is Side.BUY and o.price < 100) or (o.side is Side.SELL and o.price > 100):
            cy.rest(o)
            assert ref.submit(o) == []
    for side in (Side.BUY, Side.SELL):
        assert cy.levels(side) == ref.levels(side)
    assert (cy.best_bid, cy.best_ask) == (ref.best_bid, ref.best_ask)
    assert cy.total_resting_quantity == ref.total_resting_quantity
