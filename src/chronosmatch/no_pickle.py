"""Turn Python's pickle module off, to *prove* a code path never serializes with it.

Used by the mid-review demo: both processes call this before moving 1M orders. If anything in
the pipeline tried to pickle, it would raise PickleForbiddenError instead of silently working.

Note: this disables the public `pickle` API in the current process only. multiprocessing relies
on pickle, so the demo starts the firehose with subprocess, not multiprocessing.
"""

import pickle
from collections.abc import Iterator
from contextlib import contextmanager

_BLOCKED_NAMES = ("dump", "dumps", "load", "loads", "Pickler", "Unpickler")


class PickleForbiddenError(RuntimeError):
    pass


def _blocked(*_args: object, **_kwargs: object) -> None:
    raise PickleForbiddenError("pickle is forbidden in the zero-copy pipeline")


def forbid_pickle() -> None:
    """Replace the public pickle functions/classes with ones that raise. Permanent."""
    for name in _BLOCKED_NAMES:
        setattr(pickle, name, _blocked)


@contextmanager
def pickle_forbidden() -> Iterator[None]:
    """Temporarily forbid pickle (for tests), restoring the originals afterwards."""
    originals = {name: getattr(pickle, name) for name in _BLOCKED_NAMES}
    forbid_pickle()
    try:
        yield
    finally:
        for name, value in originals.items():
            setattr(pickle, name, value)
