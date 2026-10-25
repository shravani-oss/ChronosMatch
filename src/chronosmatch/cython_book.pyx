# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""Price-indexed limit order book in Cython (design: docs/notes/08-cython-order-book-design.md).

Storage is plain C memory: per-price arrays for each side, and a preallocated pool of order
nodes linked into one FIFO queue per price level. The cdef core methods work only on C integers.

Matching: `submit` (Python objects in/out) and `submit_raw` (C integers only) share the cdef
`_match` core, which writes trades into a preallocated C trade buffer.
"""

from libc.stdint cimport int32_t, int64_t, uint64_t
from libc.stdlib cimport free, malloc

from chronosmatch import config
from chronosmatch.types import Side, Trade

cdef int32_t NO_NODE = -1
# FNV-1a 64-bit constants (see trade_digest.py for the identical Python version).
cdef uint64_t FNV_OFFSET = 14695981039346656037ULL
cdef uint64_t FNV_PRIME = 1099511628211ULL


cdef struct Node:
    int64_t order_id
    int64_t price
    int64_t remaining
    int32_t next          # next node in the same price level (FIFO), or NO_NODE


cdef struct TradeRec:
    int64_t buy_order_id
    int64_t sell_order_id
    int64_t price
    int64_t quantity


cdef class CythonOrderBook:
    cdef int64_t max_price
    cdef int32_t capacity

    cdef Node* nodes
    cdef int32_t* free_stack
    cdef int32_t free_top          # number of free nodes on the stack

    cdef int32_t* bid_head
    cdef int32_t* bid_tail
    cdef int64_t* bid_qty
    cdef int32_t* ask_head
    cdef int32_t* ask_tail
    cdef int64_t* ask_qty

    cdef int64_t best_bid_px       # 0 = no bids
    cdef int64_t best_ask_px       # max_price + 1 = no asks
    cdef int64_t resting_qty
    cdef int32_t resting_orders

    cdef TradeRec* trades         # one incoming order makes at most `capacity` trades

    # Running totals over every trade ever made: a fingerprint of the whole trade history.
    cdef int64_t total_trades
    cdef int64_t total_traded_qty
    cdef int64_t total_notional   # sum of price x quantity
    cdef uint64_t checksum        # FNV-1a over (buy_id, sell_id, price, qty) of each trade

    def __cinit__(self, max_price=None, capacity=None):
        cdef int64_t i
        cdef int64_t levels
        self.max_price = config.BOOK_MAX_PRICE_TICKS if max_price is None else max_price
        self.capacity = config.BOOK_MAX_RESTING_ORDERS if capacity is None else capacity
        if self.max_price < 1 or self.capacity < 1:
            raise ValueError("max_price and capacity must be positive")

        levels = self.max_price + 2   # index 0 and max_price + 1 are the "empty" sentinels
        self.nodes = <Node*> malloc(self.capacity * sizeof(Node))
        self.free_stack = <int32_t*> malloc(self.capacity * sizeof(int32_t))
        self.bid_head = <int32_t*> malloc(levels * sizeof(int32_t))
        self.bid_tail = <int32_t*> malloc(levels * sizeof(int32_t))
        self.bid_qty = <int64_t*> malloc(levels * sizeof(int64_t))
        self.ask_head = <int32_t*> malloc(levels * sizeof(int32_t))
        self.ask_tail = <int32_t*> malloc(levels * sizeof(int32_t))
        self.ask_qty = <int64_t*> malloc(levels * sizeof(int64_t))
        self.trades = <TradeRec*> malloc(self.capacity * sizeof(TradeRec))
        if (self.trades == NULL or self.nodes == NULL or self.free_stack == NULL or self.bid_head == NULL
                or self.bid_tail == NULL or self.bid_qty == NULL or self.ask_head == NULL
                or self.ask_tail == NULL or self.ask_qty == NULL):
            raise MemoryError("could not allocate order book memory")

        for i in range(levels):
            self.bid_head[i] = NO_NODE
            self.bid_tail[i] = NO_NODE
            self.bid_qty[i] = 0
            self.ask_head[i] = NO_NODE
            self.ask_tail[i] = NO_NODE
            self.ask_qty[i] = 0
        # Stack holds capacity-1 .. 0, so the first allocation returns node 0.
        for i in range(self.capacity):
            self.free_stack[i] = <int32_t> (self.capacity - 1 - i)
        self.free_top = self.capacity

        self.best_bid_px = 0
        self.best_ask_px = self.max_price + 1
        self.resting_qty = 0
        self.resting_orders = 0
        self.total_trades = 0
        self.total_traded_qty = 0
        self.total_notional = 0
        self.checksum = FNV_OFFSET

    def __dealloc__(self):
        free(self.nodes)
        free(self.free_stack)
        free(self.bid_head)
        free(self.bid_tail)
        free(self.bid_qty)
        free(self.ask_head)
        free(self.ask_tail)
        free(self.ask_qty)
        free(self.trades)

    # ---------------------------------------------------------------- C core

    cdef int32_t _alloc_node(self) except -2:
        if self.free_top == 0:
            raise OverflowError("order book node pool is full")
        self.free_top -= 1
        return self.free_stack[self.free_top]

    cdef void _release_node(self, int32_t node) noexcept:
        self.free_stack[self.free_top] = node
        self.free_top += 1

    cdef inline void _record_trade(self, TradeRec* trade) noexcept:
        self.total_trades += 1
        self.total_traded_qty += trade.quantity
        self.total_notional += trade.price * trade.quantity
        self.checksum = (self.checksum ^ <uint64_t> trade.buy_order_id) * FNV_PRIME
        self.checksum = (self.checksum ^ <uint64_t> trade.sell_order_id) * FNV_PRIME
        self.checksum = (self.checksum ^ <uint64_t> trade.price) * FNV_PRIME
        self.checksum = (self.checksum ^ <uint64_t> trade.quantity) * FNV_PRIME

    cdef int _rest(self, bint is_buy, int64_t order_id, int64_t price, int64_t qty) except -1:
        """Append an order at the tail of its price level (newest = last in the FIFO)."""
        cdef int32_t node = self._alloc_node()
        cdef int32_t* head = self.bid_head if is_buy else self.ask_head
        cdef int32_t* tail = self.bid_tail if is_buy else self.ask_tail
        cdef int64_t* level_qty = self.bid_qty if is_buy else self.ask_qty

        self.nodes[node].order_id = order_id
        self.nodes[node].price = price
        self.nodes[node].remaining = qty
        self.nodes[node].next = NO_NODE

        if tail[price] == NO_NODE:
            head[price] = node
        else:
            self.nodes[tail[price]].next = node
        tail[price] = node
        level_qty[price] += qty

        if is_buy and price > self.best_bid_px:
            self.best_bid_px = price
        elif not is_buy and price < self.best_ask_px:
            self.best_ask_px = price
        self.resting_qty += qty
        self.resting_orders += 1
        return 0

    cdef int64_t _match(self, bint is_buy, int64_t order_id, int64_t price, int64_t qty) except -1:
        """Match against the opposite side, rest any remainder; return the number of trades.

        Price priority: always take the current best opposite level.
        Time priority: within a level, consume from the head of the FIFO (oldest first).
        Trades execute at the resting order's price. Caller guarantees a free node exists.
        """
        cdef int32_t* head = self.ask_head if is_buy else self.bid_head
        cdef int32_t* tail = self.ask_tail if is_buy else self.bid_tail
        cdef int64_t* level_qty = self.ask_qty if is_buy else self.bid_qty
        cdef int64_t remaining = qty
        cdef int64_t n = 0
        cdef int64_t level, fill
        cdef int32_t node, next_node

        while remaining > 0:
            level = self.best_ask_px if is_buy else self.best_bid_px
            if (is_buy and level > price) or (not is_buy and level < price):
                break  # best opposite price no longer crosses (or that side is empty)

            node = head[level]
            while node != NO_NODE and remaining > 0:
                fill = remaining if remaining < self.nodes[node].remaining else self.nodes[node].remaining
                if is_buy:
                    self.trades[n].buy_order_id = order_id
                    self.trades[n].sell_order_id = self.nodes[node].order_id
                else:
                    self.trades[n].buy_order_id = self.nodes[node].order_id
                    self.trades[n].sell_order_id = order_id
                self.trades[n].price = level
                self.trades[n].quantity = fill
                self._record_trade(&self.trades[n])
                n += 1

                self.nodes[node].remaining -= fill
                remaining -= fill
                level_qty[level] -= fill
                self.resting_qty -= fill

                if self.nodes[node].remaining == 0:  # fully filled: unlink and recycle
                    next_node = self.nodes[node].next
                    self._release_node(node)
                    self.resting_orders -= 1
                    node = next_node
                    head[level] = node
                    if node == NO_NODE:
                        tail[level] = NO_NODE

            if head[level] == NO_NODE:  # level emptied: scan to the next non-empty one
                if is_buy:
                    level += 1
                    while level <= self.max_price and head[level] == NO_NODE:
                        level += 1
                    self.best_ask_px = level          # max_price + 1 if none left
                else:
                    level -= 1
                    while level >= 1 and head[level] == NO_NODE:
                        level -= 1
                    self.best_bid_px = level          # 0 if none left

        if remaining > 0:
            self._rest(is_buy, order_id, price, remaining)
        return n

    # ------------------------------------------------------- Python-facing API

    cdef int _check_new_order(self, int64_t price) except -1:
        if price < 1 or price > self.max_price:
            raise ValueError(f"price {price} outside 1..{self.max_price}")
        if self.free_top == 0:
            # Reject up front: matching only frees nodes, so one free node now guarantees
            # the remainder can rest afterwards, and no half-applied order is possible.
            raise OverflowError("order book node pool is full; order rejected")
        return 0

    def submit(self, order):
        """Match a limit order, rest any remainder, and return the trades as Trade objects."""
        self._check_new_order(order.price)
        cdef int64_t n = self._match(
            order.side is Side.BUY, order.order_id, order.price, order.quantity
        )
        cdef int64_t i
        return [
            Trade(
                self.trades[i].buy_order_id,
                self.trades[i].sell_order_id,
                self.trades[i].price,
                self.trades[i].quantity,
            )
            for i in range(n)
        ]

    def submit_raw(self, bint is_buy, int64_t order_id, int64_t price, int64_t quantity):
        """Same as submit, but takes C integers and returns only the trade count.

        No Order or Trade objects are created; used for benchmarks and the Week 3 hot path.
        """
        if quantity <= 0:
            raise ValueError(f"quantity must be positive, got {quantity}")
        self._check_new_order(price)
        return self._match(is_buy, order_id, price, quantity)

    def rest(self, order):
        """Add a non-crossing limit order to the book without matching.

        Raises ValueError if the price is out of range or the order would cross the spread
        (crossing orders must go through `submit`, added with the matching logic).
        """
        cdef bint is_buy = order.side is Side.BUY
        cdef int64_t price = order.price
        if price < 1 or price > self.max_price:
            raise ValueError(f"price {price} outside 1..{self.max_price}")
        if is_buy and price >= self.best_ask_px:
            raise ValueError("buy order would cross the best ask; use submit")
        if not is_buy and price <= self.best_bid_px:
            raise ValueError("sell order would cross the best bid; use submit")
        self._rest(is_buy, order.order_id, price, order.quantity)

    @property
    def best_bid(self):
        return None if self.best_bid_px == 0 else self.best_bid_px

    @property
    def best_ask(self):
        return None if self.best_ask_px == self.max_price + 1 else self.best_ask_px

    @property
    def spread(self):
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask_px - self.best_bid_px

    @property
    def total_resting_quantity(self):
        return self.resting_qty

    @property
    def resting_order_count(self):
        return self.resting_orders

    @property
    def trade_stats(self):
        """(total_trades, total_traded_qty, total_notional, checksum) since construction."""
        return (self.total_trades, self.total_traded_qty, self.total_notional, self.checksum)

    @property
    def free_nodes(self):
        return self.free_top

    def levels(self, side):
        """Aggregate (price, total_quantity) per level, best price first."""
        cdef int64_t price
        result = []
        if side is Side.BUY:
            price = self.best_bid_px
            while price >= 1:
                if self.bid_qty[price] > 0:
                    result.append((price, self.bid_qty[price]))
                price -= 1
        else:
            price = self.best_ask_px
            while price <= self.max_price:
                if self.ask_qty[price] > 0:
                    result.append((price, self.ask_qty[price]))
                price += 1
        return result

    def queue_order_ids(self, side, int64_t price):
        """Order ids waiting at one price level, oldest first (for testing time priority)."""
        if price < 1 or price > self.max_price:
            raise ValueError(f"price {price} outside 1..{self.max_price}")
        cdef int32_t node = self.bid_head[price] if side is Side.BUY else self.ask_head[price]
        result = []
        while node != NO_NODE:
            result.append(self.nodes[node].order_id)
            node = self.nodes[node].next
        return result
