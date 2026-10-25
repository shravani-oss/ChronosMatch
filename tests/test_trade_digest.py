"""The trade fingerprint: Cython (in C, during matching) must equal the Python version."""

from pathlib import Path

from chronosmatch import config
from chronosmatch.cython_book import CythonOrderBook
from chronosmatch.order_generator import generate_orders
from chronosmatch.reference_book import ReferenceOrderBook
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.trade_digest import FNV_OFFSET, TradeDigest
from chronosmatch.types import Order, Side, Trade


def test_empty_fingerprint() -> None:
    assert CythonOrderBook(max_price=100, capacity=8).trade_stats == (0, 0, 0, FNV_OFFSET)
    assert TradeDigest().stats == (0, 0, 0, FNV_OFFSET)


def test_known_single_trade() -> None:
    book = CythonOrderBook(max_price=100, capacity=8)
    book.submit(Order(1, Side.SELL, 51, 10))
    book.submit(Order(2, Side.BUY, 52, 4))
    digest = TradeDigest()
    digest.add([Trade(2, 1, 51, 4)])
    assert book.trade_stats == digest.stats
    assert book.trade_stats[:3] == (1, 4, 204)


def test_cython_fingerprint_equals_python_digest_of_reference_trades() -> None:
    ref, cy, digest = ReferenceOrderBook(), CythonOrderBook(), TradeDigest()
    for order in generate_orders(5_000, seed=9):
        digest.add(ref.submit(order))
        cy.submit_raw(order.side is Side.BUY, order.order_id, order.price, order.quantity)
    assert cy.trade_stats == digest.stats
    assert digest.count > 1_000


def test_checksum_depends_on_trade_order() -> None:
    a, b = TradeDigest(), TradeDigest()
    a.add([Trade(1, 2, 50, 5), Trade(3, 4, 50, 5)])
    b.add([Trade(3, 4, 50, 5), Trade(1, 2, 50, 5)])
    assert a.stats[:3] == b.stats[:3]      # same totals...
    assert a.checksum != b.checksum        # ...but a different sequence is detected


def test_try_pop_raw_returns_plain_integers(tmp_path: Path) -> None:
    with RingBuffer.create(tmp_path / "raw.ring", 8) as ring:
        assert ring.try_pop_raw() is None
        ring.try_push(Order(7, Side.SELL, 99, 3), timestamp_ns=123)
        assert ring.try_pop_raw() == (7, 123, 99, 3, config.SIDE_CODE_SELL)
        assert len(ring) == 0
