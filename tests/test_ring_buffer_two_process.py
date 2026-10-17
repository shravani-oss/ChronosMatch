"""A real second OS process writes orders; this process reads and checks every one."""

import multiprocessing
from pathlib import Path

from chronosmatch.ipc_demo import consume, produce
from chronosmatch.order_generator import generate_orders
from chronosmatch.ring_buffer import RingBuffer

ORDER_COUNT = 50_000
SMALL_CAPACITY = 1024  # far smaller than ORDER_COUNT: forces wrap-around and full-buffer waits
SEED = 7
TIMEOUT_S = 60.0


def test_orders_cross_process_boundary_intact_and_in_order(tmp_path: Path) -> None:
    path = tmp_path / "ipc.ring"
    ctx = multiprocessing.get_context("spawn")  # a fresh interpreter, nothing inherited

    with RingBuffer.create(path, SMALL_CAPACITY) as ring:
        producer = ctx.Process(target=produce, args=(path, ORDER_COUNT, SEED))
        producer.start()
        try:
            received = consume(ring, ORDER_COUNT, TIMEOUT_S)
        finally:
            producer.join(timeout=TIMEOUT_S)
            if producer.is_alive():
                producer.terminate()

        assert producer.exitcode == 0
        assert received == list(generate_orders(ORDER_COUNT, seed=SEED))
        assert len(ring) == 0
