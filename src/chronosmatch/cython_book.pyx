# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""Price-indexed limit order book in Cython (design: docs/notes/08-cython-order-book-design.md).

Storage is plain C memory: per-price arrays for each side, and a preallocated pool of order
nodes linked into one FIFO queue per price level. The cdef core methods work only on C integers.

Status (22 Oct): book structure and resting orders. Matching (`submit`) comes next.
"""

from libc.stdint cimport int32_t, int64_t
from libc.stdlib cimport free, malloc

from chronosmatch import config
from chronosmatch.types import Side

cdef int32_t NO_NODE = -1


cdef struct Node:
    int64_t order_id
    int64_t price
    int64_t remaining
    int32_t next          # next node in the same price level (FIFO), or NO_NODE


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
        if (self.nodes == NULL or self.free_stack == NULL or self.bid_head == NULL
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

    def __dealloc__(self):
        free(self.nodes)
        free(self.free_stack)
        free(self.bid_head)
        free(self.bid_tail)
        free(self.bid_qty)
        free(self.ask_head)
        free(self.ask_tail)
        free(self.ask_qty)

    # ---------------------------------------------------------------- C core

    cdef int32_t _alloc_node(self) except -2:
        if self.free_top == 0:
            raise OverflowError("order book node pool is full")
        self.free_top -= 1
        return self.free_stack[self.free_top]

    cdef void _release_node(self, int32_t node) noexcept:
        self.free_stack[self.free_top] = node
        self.free_top += 1

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

    # ------------------------------------------------------- Python-facing API

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
