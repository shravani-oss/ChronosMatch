"""Matching rules, run against BOTH order books: the pure-Python reference and Cython.

If a scenario passes for one implementation and fails for the other, they disagree.
"""

import pytest

from chronosmatch.cython_book import CythonOrderBook
from chronosmatch.reference_book import ReferenceOrderBook
from chronosmatch.types import Order, Side, Trade

BOOK_FACTORIES = {
    "reference": ReferenceOrderBook,
    "cython": lambda: CythonOrderBook(max_price=1_000, capacity=1_000),
}


@pytest.fixture(params=list(BOOK_FACTORIES), ids=list(BOOK_FACTORIES))
def book(request):
    return BOOK_FACTORIES[request.param]()


def buy(order_id: int, price: int, qty: int) -> Order:
    return Order(order_id, Side.BUY, price, qty)


def sell(order_id: int, price: int, qty: int) -> Order:
    return Order(order_id, Side.SELL, price, qty)


def test_orders_that_do_not_cross_rest(book) -> None:
    assert book.submit(buy(1, 50, 100)) == []
    assert book.submit(sell(2, 51, 80)) == []
    assert (book.best_bid, book.best_ask, book.spread) == (50, 51, 1)


def test_exact_match_clears_both_sides(book) -> None:
    book.submit(sell(1, 51, 100))
    assert book.submit(buy(2, 51, 100)) == [Trade(2, 1, 51, 100)]
    assert (book.best_bid, book.best_ask, book.total_resting_quantity) == (None, None, 0)


def test_trade_executes_at_resting_price(book) -> None:
    book.submit(sell(1, 51, 10))
    assert book.submit(buy(2, 52, 10)) == [Trade(2, 1, 51, 10)]


def test_price_priority_cheapest_ask_first(book) -> None:
    book.submit(sell(1, 52, 10))
    book.submit(sell(2, 51, 10))
    assert book.submit(buy(3, 52, 10)) == [Trade(3, 2, 51, 10)]
    assert book.best_ask == 52


def test_time_priority_earlier_order_first(book) -> None:
    book.submit(sell(1, 51, 10))
    book.submit(sell(2, 51, 10))
    assert book.submit(buy(3, 51, 10)) == [Trade(3, 1, 51, 10)]
    assert book.submit(buy(4, 51, 10)) == [Trade(4, 2, 51, 10)]


def test_partial_fills_across_levels(book) -> None:
    book.submit(sell(1, 51, 50))
    book.submit(sell(2, 51, 30))
    book.submit(sell(3, 52, 40))
    assert book.submit(buy(99, 52, 100)) == [
        Trade(99, 1, 51, 50), Trade(99, 2, 51, 30), Trade(99, 3, 52, 20),
    ]
    assert book.levels(Side.SELL) == [(52, 20)]


def test_unfilled_remainder_rests_and_trades_later(book) -> None:
    book.submit(sell(1, 51, 30))
    assert book.submit(buy(2, 51, 100)) == [Trade(2, 1, 51, 30)]
    assert book.levels(Side.BUY) == [(51, 70)]
    assert book.submit(sell(3, 51, 70)) == [Trade(2, 3, 51, 70)]
    assert book.total_resting_quantity == 0


def test_sell_hits_highest_bid_first(book) -> None:
    book.submit(buy(1, 49, 10))
    book.submit(buy(2, 50, 10))
    assert book.submit(sell(3, 49, 15)) == [Trade(2, 3, 50, 10), Trade(1, 3, 49, 5)]
    assert book.levels(Side.BUY) == [(49, 5)]


def test_incoming_order_never_trades_beyond_its_limit(book) -> None:
    book.submit(sell(1, 53, 10))
    assert book.submit(buy(2, 52, 10)) == []
    assert (book.best_bid, book.best_ask) == (52, 53)


def test_sweep_through_many_levels_and_rest(book) -> None:
    for i, price in enumerate([51, 52, 53, 54], start=1):
        book.submit(sell(i, price, 10))
    trades = book.submit(buy(9, 53, 100))
    assert [t.price for t in trades] == [51, 52, 53]
    assert book.best_bid == 53 and book.best_ask == 54
    assert book.levels(Side.BUY) == [(53, 70)]
