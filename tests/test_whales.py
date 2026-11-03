"""Whale detection (large orders that clear several price levels), injection and display."""

from pathlib import Path

import pytest

from chronosmatch import config
from chronosmatch.cython_book import CythonOrderBook
from chronosmatch.dashboard import render_lines
from chronosmatch.order_generator import generate_orders
from chronosmatch.telemetry import Snapshot, TelemetryBlock
from chronosmatch.types import Order, Side

MIN_QTY, MIN_LEVELS = config.WHALE_MIN_QTY, config.WHALE_MIN_LEVELS


def book_with_asks(levels: int, qty_each: int) -> CythonOrderBook:
    book = CythonOrderBook(max_price=1_000, capacity=64)
    for i in range(levels):
        book.submit(Order(i + 1, Side.SELL, 101 + i, qty_each))
    return book


def test_large_order_across_enough_levels_is_a_whale() -> None:
    book = book_with_asks(MIN_LEVELS, MIN_QTY)
    book.submit(Order(99, Side.BUY, 200, MIN_QTY * MIN_LEVELS))
    assert book.whale_count == 1
    assert book.last_whale == (99, Side.BUY, MIN_LEVELS, MIN_QTY * MIN_LEVELS, 101, 100 + MIN_LEVELS)


def test_too_few_levels_is_not_a_whale() -> None:
    book = book_with_asks(MIN_LEVELS - 1, MIN_QTY)
    book.submit(Order(99, Side.BUY, 200, MIN_QTY * MIN_LEVELS))
    assert book.whale_count == 0 and book.last_whale is None


def test_small_order_across_many_levels_is_not_a_whale() -> None:
    book = book_with_asks(MIN_LEVELS + 2, 1)          # thin levels
    book.submit(Order(99, Side.BUY, 200, MIN_LEVELS + 2))
    assert book.whale_count == 0


def test_sell_whale_records_prices_downwards() -> None:
    book = CythonOrderBook(max_price=1_000, capacity=64)
    for i in range(MIN_LEVELS):
        book.submit(Order(i + 1, Side.BUY, 100 - i, MIN_QTY))
    book.submit(Order(50, Side.SELL, 1, MIN_QTY * MIN_LEVELS))
    assert book.last_whale == (50, Side.SELL, MIN_LEVELS, MIN_QTY * MIN_LEVELS, 100, 101 - MIN_LEVELS)


def test_ordinary_random_flow_has_no_whales() -> None:
    book = CythonOrderBook()
    for o in generate_orders(100_000, seed=0):
        book.submit_raw(o.side is Side.BUY, o.order_id, o.price, o.quantity)
    assert book.whale_count == 0


def test_whale_injection_only_changes_every_nth_order() -> None:
    plain = list(generate_orders(1_000, seed=3))
    injected = list(generate_orders(1_000, seed=3, whale_every=100))
    for a, b in zip(plain, injected):
        if a.order_id % 100:
            assert a == b
        else:
            assert b.quantity == config.WHALE_DEFAULT_QTY and b.side == a.side


@pytest.mark.parametrize("kwargs", [{"whale_every": -1}, {"whale_every": 10, "whale_qty": 0}])
def test_invalid_whale_arguments(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        list(generate_orders(10, **kwargs))


def snap(**overrides) -> Snapshot:
    base = dict(processed=1, trades=1, traded_qty=1, best_bid=99, best_ask=101, updated_ns=1,
                orders_per_sec=1, latency_p50_ns=1, latency_p99_ns=1, target_count=1, done=False,
                bids=[], asks=[])
    base.update(overrides)
    return Snapshot(**base)


def test_telemetry_round_trips_whales(tmp_path: Path) -> None:
    whale = (40_000, Side.SELL, 4, 2_000, 101, 97)
    with TelemetryBlock.create(tmp_path / "w.tel") as tel:
        tel.publish(snap(whale_count=3, last_whale=whale))
        got = tel.read()
    assert got.whale_count == 3 and got.last_whale == whale


def test_dashboard_whale_line_and_flash() -> None:
    whale = (40_000, Side.SELL, 4, 2_000, 101, 97)
    normal = dict(render_lines(snap(whale_count=3, last_whale=whale)))
    flashed = dict(render_lines(snap(whale_count=3, last_whale=whale), whale_flash=True))
    line = "WHALES 3  last: SELL #40,000 filled 2,000 across 4 levels (101 -> 97)"
    assert normal[line] == "whale"
    assert flashed[">>> NEW WHALE <<<  " + line] == "whale_new"
    assert any("none yet" in text for text, _ in render_lines(snap()))
