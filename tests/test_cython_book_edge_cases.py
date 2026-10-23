"""Edge cases specific to the Cython book's C data structures."""

import pytest

from chronosmatch.cython_book import CythonOrderBook
from chronosmatch.types import Order, Side, Trade


def buy(order_id: int, price: int, qty: int) -> Order:
    return Order(order_id, Side.BUY, price, qty)


def sell(order_id: int, price: int, qty: int) -> Order:
    return Order(order_id, Side.SELL, price, qty)


def test_filled_orders_return_their_nodes_to_the_pool() -> None:
    book = CythonOrderBook(max_price=100, capacity=4)
    for cycle in range(1_000):  # 2,000 orders through a 4-node pool
        book.submit(sell(2 * cycle, 50, 3))
        assert book.submit(buy(2 * cycle + 1, 50, 3)) == [Trade(2 * cycle + 1, 2 * cycle, 50, 3)]
    assert book.free_nodes == 4 and book.resting_order_count == 0


def test_best_ask_rescans_across_a_wide_gap() -> None:
    book = CythonOrderBook(max_price=1_000, capacity=16)
    book.submit(sell(1, 10, 5))
    book.submit(sell(2, 900, 5))
    book.submit(buy(3, 10, 5))
    assert book.best_ask == 900


def test_best_bid_rescans_down_and_side_can_empty() -> None:
    book = CythonOrderBook(max_price=1_000, capacity=16)
    book.submit(buy(1, 900, 5))
    book.submit(buy(2, 3, 5))
    book.submit(sell(3, 900, 5))
    assert book.best_bid == 3
    book.submit(sell(4, 3, 5))
    assert book.best_bid is None and book.spread is None


def test_partially_filled_order_keeps_its_place_in_the_queue() -> None:
    book = CythonOrderBook(max_price=100, capacity=16)
    book.submit(sell(1, 51, 10))
    book.submit(sell(2, 51, 10))
    assert book.submit(buy(3, 51, 5)) == [Trade(3, 1, 51, 5)]
    assert book.queue_order_ids(Side.SELL, 51) == [1, 2]
    assert book.submit(buy(4, 51, 7)) == [Trade(4, 1, 51, 5), Trade(4, 2, 51, 2)]
    assert book.queue_order_ids(Side.SELL, 51) == [2]


def test_full_pool_rejects_new_orders_without_changing_the_book() -> None:
    book = CythonOrderBook(max_price=100, capacity=2)
    book.submit(sell(1, 51, 10))
    book.submit(sell(2, 52, 10))
    with pytest.raises(OverflowError):
        book.submit(buy(3, 51, 10))  # would fully fill, but is rejected up front
    assert book.levels(Side.SELL) == [(51, 10), (52, 10)]
    assert book.resting_order_count == 2


def test_prices_at_both_ends_of_the_range() -> None:
    book = CythonOrderBook(max_price=100, capacity=8)
    book.submit(buy(1, 1, 5))
    book.submit(sell(2, 100, 5))
    assert (book.best_bid, book.best_ask, book.spread) == (1, 100, 99)
    assert book.submit(buy(3, 100, 5)) == [Trade(3, 2, 100, 5)]
    assert book.submit(sell(4, 1, 5)) == [Trade(1, 4, 1, 5)]


def test_submit_raw_gives_same_book_state_as_submit() -> None:
    a = CythonOrderBook(max_price=200, capacity=64)
    b = CythonOrderBook(max_price=200, capacity=64)
    orders = [sell(1, 101, 30), sell(2, 102, 30), buy(3, 99, 10), buy(4, 102, 45), sell(5, 99, 20)]
    for o in orders:
        trades = a.submit(o)
        count = b.submit_raw(o.side is Side.BUY, o.order_id, o.price, o.quantity)
        assert count == len(trades)
    for side in (Side.BUY, Side.SELL):
        assert a.levels(side) == b.levels(side)


@pytest.mark.parametrize("args", [(True, 1, 50, 0), (True, 1, 50, -3), (True, 1, 0, 5), (False, 1, 201, 5)])
def test_submit_raw_validates_input(args: tuple) -> None:
    with pytest.raises(ValueError):
        CythonOrderBook(max_price=200, capacity=8).submit_raw(*args)
