"""Producer/consumer helpers that move orders between two processes through the ring buffer.

Used by the two-process test now, and by the 1M-order mid-review demo later.
"""

import time
from pathlib import Path

from chronosmatch.order_generator import generate_orders
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.types import Order


def produce(path: str | Path, count: int, seed: int) -> None:
    """Attach to an existing ring and push `count` seeded orders, spinning while it is full."""
    with RingBuffer.attach(path) as ring:
        for order in generate_orders(count, seed=seed):
            while not ring.try_push(order):
                pass  # backpressure: consumer is behind, retry


def consume(ring: RingBuffer, count: int, timeout_s: float) -> list[Order]:
    """Pop exactly `count` orders, or raise TimeoutError if they do not arrive in time."""
    received: list[Order] = []
    deadline = time.monotonic() + timeout_s
    while len(received) < count:
        item = ring.try_pop()
        if item is not None:
            received.append(item[0])
        elif time.monotonic() > deadline:
            raise TimeoutError(f"received {len(received)} of {count} orders")
    return received
