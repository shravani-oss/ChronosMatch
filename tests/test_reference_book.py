"""Behaviour tests for the reference order book."""

from chronosmatch.reference_book import ReferenceOrderBook
from chronosmatch.types import Order, Side, Trade


def buy(order_id: int, price: int, qty: int) -> Order:
    return Order(order_id, Side.BUY, price, qty)


def sell(order_id: int, price: int, qty: int) -> Order:
    return Order(order_id, Side.SELL, price, qty)


def test_empty_book_has_no_prices() -> None:
    book = ReferenceOrderBook()
    assert book.best_bid is None
    assert book.best_ask is None
    assert book.spread is None


def test_orders_that_do_not_cross_rest_in_the_book() -> None:
    book = ReferenceOrderBook()
    assert book.submit(buy(1, 50, 100)) == []
    assert book.submit(sell(2, 51, 80)) == []
    assert (book.best_bid, book.best_ask, book.spread) == (50, 51, 1)


def test_exact_match_clears_both_sides() -> None:
    book = ReferenceOrderBook()
    book.submit(sell(1, 51, 100))
    assert book.submit(buy(2, 51, 100)) == [Trade(2, 1, 51, 100)]
    assert book.best_bid is None and book.best_ask is None


def test_trade_executes_at_resting_price() -> None:
    book = ReferenceOrderBook()
    book.submit(sell(1, 51, 10))
    assert book.submit(buy(2, 52, 10)) == [Trade(2, 1, 51, 10)]


def test_price_priority_cheapest_ask_first() -> None:
    book = ReferenceOrderBook()
    book.submit(sell(1, 52, 10))
    book.submit(sell(2, 51, 10))
    assert book.submit(buy(3, 52, 10)) == [Trade(3, 2, 51, 10)]
    assert book.best_ask == 52


def test_time_priority_earlier_order_first_at_same_price() -> None:
    book = ReferenceOrderBook()
    book.submit(sell(1, 51, 10))
    book.submit(sell(2, 51, 10))
    assert book.submit(buy(3, 51, 10)) == [Trade(3, 1, 51, 10)]


def test_partial_fills_across_levels_match_toy_example() -> None:
    book = ReferenceOrderBook()
    book.submit(sell(1, 51, 50))
    book.submit(sell(2, 51, 30))
    book.submit(sell(3, 52, 40))
    trades = book.submit(buy(99, 52, 100))
    assert trades == [Trade(99, 1, 51, 50), Trade(99, 2, 51, 30), Trade(99, 3, 52, 20)]
    assert book.best_ask == 52  # order 3 stays with 20 left


def test_unfilled_remainder_rests_as_a_bid() -> None:
    book = ReferenceOrderBook()
    book.submit(sell(1, 51, 30))
    assert book.submit(buy(2, 51, 100)) == [Trade(2, 1, 51, 30)]
    assert book.best_bid == 51
    # the resting remainder (70) is consumed by the next seller
    assert book.submit(sell(3, 51, 70)) == [Trade(2, 3, 51, 70)]


def test_sell_side_hits_highest_bid_first() -> None:
    book = ReferenceOrderBook()
    book.submit(buy(1, 49, 10))
    book.submit(buy(2, 50, 10))
    assert book.submit(sell(3, 49, 10)) == [Trade(2, 3, 50, 10)]
    assert book.best_bid == 49


def test_incoming_order_does_not_trade_beyond_its_limit() -> None:
    book = ReferenceOrderBook()
    book.submit(sell(1, 53, 10))
    assert book.submit(buy(2, 52, 10)) == []
    assert (book.best_bid, book.best_ask) == (52, 53)


def test_levels_empty_book() -> None:
    book = ReferenceOrderBook()
    assert book.levels(Side.BUY) == []
    assert book.levels(Side.SELL) == []


def test_levels_aggregate_quantity_at_same_price() -> None:
    book = ReferenceOrderBook()
    book.submit(buy(1, 50, 100))
    book.submit(buy(2, 50, 40))
    book.submit(buy(3, 49, 10))
    assert book.levels(Side.BUY) == [(50, 140), (49, 10)]  # best (highest) bid first


def test_levels_asks_are_lowest_price_first() -> None:
    book = ReferenceOrderBook()
    book.submit(sell(1, 53, 5))
    book.submit(sell(2, 51, 7))
    book.submit(sell(3, 52, 9))
    assert book.levels(Side.SELL) == [(51, 7), (52, 9), (53, 5)]


def test_levels_reflect_partial_fills() -> None:
    book = ReferenceOrderBook()
    book.submit(sell(1, 51, 50))
    book.submit(buy(2, 51, 20))
    assert book.levels(Side.SELL) == [(51, 30)]
