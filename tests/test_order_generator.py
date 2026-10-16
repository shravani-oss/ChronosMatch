"""Tests for the seeded order generator."""

import pytest

from chronosmatch.order_generator import generate_orders
from chronosmatch.types import Side


def test_generates_requested_count_with_sequential_ids() -> None:
    orders = list(generate_orders(50, seed=1))
    assert [o.order_id for o in orders] == list(range(1, 51))


def test_zero_count_is_empty() -> None:
    assert list(generate_orders(0)) == []


def test_same_seed_gives_same_orders() -> None:
    assert list(generate_orders(200, seed=7)) == list(generate_orders(200, seed=7))


def test_different_seeds_give_different_orders() -> None:
    assert list(generate_orders(200, seed=1)) != list(generate_orders(200, seed=2))


def test_prices_and_quantities_stay_in_bounds() -> None:
    for order in generate_orders(500, seed=3, mid_price=100, price_band=5, max_quantity=20):
        assert 95 <= order.price <= 105
        assert 1 <= order.quantity <= 20


def test_both_sides_appear() -> None:
    sides = {o.side for o in generate_orders(100, seed=4)}
    assert sides == {Side.BUY, Side.SELL}


@pytest.mark.parametrize(
    "kwargs",
    [{"count": -1}, {"count": 1, "price_band": 100, "mid_price": 100}, {"count": 1, "max_quantity": 0}],
)
def test_invalid_arguments_raise(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        list(generate_orders(**kwargs))
