"""Tests for Order and Trade."""

import dataclasses

import pytest

from chronosmatch.types import Order, Side, Trade


def test_order_stores_fields() -> None:
    order = Order(order_id=1, side=Side.BUY, price=50, quantity=100)
    assert (order.order_id, order.side, order.price, order.quantity) == (1, Side.BUY, 50, 100)


@pytest.mark.parametrize("price,quantity", [(0, 10), (-5, 10), (10, 0), (10, -1)])
def test_order_rejects_non_positive_price_or_quantity(price: int, quantity: int) -> None:
    with pytest.raises(ValueError):
        Order(order_id=1, side=Side.SELL, price=price, quantity=quantity)


def test_order_is_immutable() -> None:
    order = Order(order_id=1, side=Side.BUY, price=50, quantity=100)
    with pytest.raises(dataclasses.FrozenInstanceError):
        order.price = 51  # type: ignore[misc]


def test_trade_equality_compares_by_value() -> None:
    assert Trade(1, 2, 51, 30) == Trade(1, 2, 51, 30)
