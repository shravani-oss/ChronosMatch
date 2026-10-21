"""The mid-review demo, run at a smaller size so the test suite stays fast."""

import pickle
from pathlib import Path

from chronosmatch.demo_ipc import run_demo


def test_demo_passes_with_small_ring_and_pickle_forbidden(tmp_path: Path) -> None:
    originals = {n: getattr(pickle, n) for n in ("dump", "dumps", "load", "loads", "Pickler", "Unpickler")}
    try:
        result = run_demo(tmp_path / "d.ring", count=30_000, seed=3, rate=0, capacity=512)
    finally:
        for name, value in originals.items():  # run_demo forbids pickle permanently
            setattr(pickle, name, value)
    assert result.ok, result
    assert result.received == 30_000 and result.mismatches == 0
    assert "sent=30000" in result.producer_output


def test_demo_reports_failure_when_orders_do_not_match(tmp_path: Path, monkeypatch) -> None:
    """A proof is only meaningful if it can fail: expect a different stream than is sent."""
    from chronosmatch import demo_ipc
    from chronosmatch.order_generator import generate_orders

    monkeypatch.setattr(
        demo_ipc, "generate_orders", lambda count, seed: generate_orders(count, seed=seed + 1)
    )
    originals = {n: getattr(pickle, n) for n in ("dump", "dumps", "load", "loads", "Pickler", "Unpickler")}
    try:
        result = demo_ipc.run_demo(tmp_path / "bad.ring", count=2_000, seed=3, rate=0, capacity=512)
    finally:
        for name, value in originals.items():
            setattr(pickle, name, value)
    assert not result.ok
    assert result.mismatches > 0
