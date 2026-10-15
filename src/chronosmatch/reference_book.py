"""A deliberately simple, slow, pure-Python limit order book.

Purpose: a *correctness oracle*. The fast Cython engine must produce exactly the same
trades as this class for the same sequence of orders. Clarity beats speed here.

Rules implemented (limit orders only):
- Price priority: a buyer meets the lowest asks first; a seller meets the highest bids first.
- Time priority: at equal price, the order that arrived first matches first.
- Trades execute at the resting order's price.
- Any unfilled remainder rests in the book.
"""

from dataclasses import dataclass

from chronosmatch.types import Order, Side, Trade


@dataclass
class _Resting:
    """An order waiting in the book. `remaining` shrinks on partial fills."""

    order_id: int
    price: int
    remaining: int


class ReferenceOrderBook:
    def __init__(self) -> None:
        # Both lists are kept in arrival order (oldest first).
        self._bids: list[_Resting] = []
        self._asks: list[_Resting] = []

    @property
    def best_bid(self) -> int | None:
        return max((r.price for r in self._bids), default=None)

    @property
    def best_ask(self) -> int | None:
        return min((r.price for r in self._asks), default=None)

    @property
    def spread(self) -> int | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    def submit(self, order: Order) -> list[Trade]:
        """Match `order` against the opposite side, rest any remainder, return trades."""
        is_buy = order.side is Side.BUY
        opposite = self._asks if is_buy else self._bids
        same = self._bids if is_buy else self._asks

        # Best price first. sorted() is stable, so equal prices keep arrival order.
        best_first = sorted(opposite, key=lambda r: r.price if is_buy else -r.price)

        trades: list[Trade] = []
        remaining = order.quantity
        for resting in best_first:
            if remaining == 0:
                break
            crosses = resting.price <= order.price if is_buy else resting.price >= order.price
            if not crosses:
                break  # list is best-first, so nothing later can cross either

            fill = min(remaining, resting.remaining)
            buy_id, sell_id = (
                (order.order_id, resting.order_id) if is_buy else (resting.order_id, order.order_id)
            )
            trades.append(Trade(buy_id, sell_id, resting.price, fill))
            resting.remaining -= fill
            remaining -= fill

        opposite[:] = [r for r in opposite if r.remaining > 0]
        if remaining > 0:
            same.append(_Resting(order.order_id, order.price, remaining))
        return trades
