"""Full pipeline (three processes) at a small size, plus a check that it can report FAIL."""

from pathlib import Path

from chronosmatch import demo_pipeline
from chronosmatch.order_generator import generate_orders


def test_pipeline_passes_and_agrees_with_reference(tmp_path: Path) -> None:
    result = demo_pipeline.run_pipeline(
        tmp_path / "p.ring", count=20_000, seed=2, rate=0, capacity=1024, with_reference=True
    )
    assert result.ok, result
    assert result.engine["processed"] == 20_000
    assert tuple(result.engine["trade_stats"]) == result.expected_stats == result.reference_stats


def test_pipeline_reports_failure_when_expectation_differs(tmp_path: Path, monkeypatch) -> None:
    """Only this process's expected answer uses a different stream; the engine is untouched."""
    monkeypatch.setattr(
        demo_pipeline, "generate_orders", lambda count, seed: generate_orders(count, seed=seed + 1)
    )
    result = demo_pipeline.run_pipeline(
        tmp_path / "bad.ring", count=5_000, seed=2, rate=0, capacity=1024, with_reference=False
    )
    assert result.engine is not None and result.engine["processed"] == 5_000
    assert not result.ok
