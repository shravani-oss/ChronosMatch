"""Tests for the pickle guard used by the zero-copy proof."""

import pickle
from pathlib import Path

import pytest

from chronosmatch.no_pickle import PickleForbiddenError, pickle_forbidden
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.types import Order, Side


@pytest.mark.parametrize("call", [
    lambda: pickle.dumps(1),
    lambda: pickle.loads(b""),
    lambda: pickle.Pickler(None),
    lambda: pickle.Unpickler(None),
])
def test_pickle_raises_inside_guard(call) -> None:
    with pickle_forbidden():
        with pytest.raises(PickleForbiddenError):
            call()


def test_pickle_is_restored_after_guard() -> None:
    with pickle_forbidden():
        pass
    assert pickle.loads(pickle.dumps({"a": 1})) == {"a": 1}


def test_ring_buffer_works_with_pickle_forbidden(tmp_path: Path) -> None:
    """The whole push/pop path must not touch pickle."""
    order = Order(1, Side.BUY, 100, 5)
    with pickle_forbidden(), RingBuffer.create(tmp_path / "np.ring", 8) as ring:
        assert ring.try_push(order, 9)
        assert ring.try_pop() == (order, 9)
