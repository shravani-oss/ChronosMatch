"""Order cancellation, run on BOTH books, plus a differential test with cancels mixed in."""

import random

import pytest

from chronosmatch.cython_book import CythonOrderBook
from chronosmatch.reference_book import ReferenceOrderBook
from chronosmatch.types import Order, Side, Trade

BOOK_FACTORIES = {
    "reference": ReferenceOrderBook,
    "cython": lambda: CythonOrderBook(max_price=1_000, capacity=4_000),
}


@pytest.fixture(params=list(BOOK_FACTORIES), ids=list(BOOK_FACTORIES))
def book(request):
    return BOOK_FACTORIES[request.param]()


def buy(i: int, price: int, qty: int) -> Order:
    return Order(i, Side.BUY, price, qty)


def sell(i: int, price: int, qty: int) -> Order:
    return Order(i, Side.SELL, price, qty)


def test_cancel_removes_resting_order(book) -> None:
    book.submit(buy(1, 50, 100))
    book.submit(buy(2, 49, 30))
    assert book.cancel(1, Side.BUY, 50) == 100
    assert book.best_bid == 49 and book.levels(Side.BUY) == [(49, 30)]
    assert book.total_resting_quantity == 30


@pytest.mark.parametrize("args", [(9, Side.BUY, 50), (1, Side.SELL, 50), (1, Side.BUY, 51)])
def test_cancel_unknown_or_wrong_side_or_price_returns_zero(book, args) -> None:
    book.submit(buy(1, 50, 10))
    assert book.cancel(*args) == 0
    assert book.levels(Side.BUY) == [(50, 10)]


def test_cancel_twice_returns_zero_second_time(book) -> None:
    book.submit(sell(1, 51, 10))
    assert book.cancel(1, Side.SELL, 51) == 10
    assert book.cancel(1, Side.SELL, 51) == 0


def test_cancel_after_partial_fill_returns_remaining(book) -> None:
    book.submit(sell(1, 51, 50))
    book.submit(buy(2, 51, 20))
    assert book.cancel(1, Side.SELL, 51) == 30
    assert book.best_ask is None


def test_cancelled_order_no_longer_trades(book) -> None:
    book.submit(sell(1, 51, 10))
    book.submit(sell(2, 51, 10))
    book.cancel(1, Side.SELL, 51)
    assert book.submit(buy(3, 51, 10)) == [Trade(3, 2, 51, 10)]


def test_cancel_best_ask_moves_best_up_and_side_can_empty(book) -> None:
    book.submit(sell(1, 51, 5))
    book.submit(sell(2, 55, 5))
    book.cancel(1, Side.SELL, 51)
    assert book.best_ask == 55
    book.cancel(2, Side.SELL, 55)
    assert (book.best_ask, book.spread) == (None, None)


def test_cython_cancel_keeps_fifo_order_and_frees_the_node() -> None:
    book = CythonOrderBook(max_price=100, capacity=4)
    for i in (1, 2, 3):
        book.submit(sell(i, 60, 1))
    assert book.cancel(2, Side.SELL, 60) == 1          # middle of the queue
    assert book.queue_order_ids(Side.SELL, 60) == [1, 3]
    assert book.cancel(3, Side.SELL, 60) == 1          # tail of the queue
    book.submit(sell(4, 60, 1))                        # must append after 1 (tail fixed)
    assert book.queue_order_ids(Side.SELL, 60) == [1, 4]
    assert book.free_nodes == 2 and book.resting_order_count == 2


def test_cython_cancel_out_of_range_price_returns_zero() -> None:
    assert CythonOrderBook(max_price=100, capacity=4).cancel(1, Side.BUY, 101) == 0


@pytest.mark.parametrize("seed", range(6))
def test_cancels_mixed_into_random_flow_match_reference(seed: int) -> None:
    """Random orders, with ~25% of steps cancelling a random earlier order (which may already
    be filled). Both books must return the same cancelled quantity and the same trades."""
    rng = random.Random(seed)
    ref, cy = ReferenceOrderBook(), CythonOrderBook(max_price=1_000, capacity=4_000)
    sent: list[Order] = []
    cancelled_qty = 0
    for order_id in range(1, 3_001):
        if sent and rng.random() < 0.25:
            target = rng.choice(sent)
            got = ref.cancel(target.order_id, target.side, target.price)
            assert cy.cancel(target.order_id, target.side, target.price) == got
            cancelled_qty += got
        side = Side.BUY if rng.random() < 0.5 else Side.SELL
        order = Order(order_id, side, 100 + rng.randint(-5, 5), rng.randint(1, 50))
        sent.append(order)
        assert cy.submit(order) == ref.submit(order), f"diverged at order {order_id}"
    for side in (Side.BUY, Side.SELL):
        assert cy.levels(side) == ref.levels(side)
    assert cy.total_resting_quantity == ref.total_resting_quantity
    assert cancelled_qty > 0  # guard: cancels really happened
