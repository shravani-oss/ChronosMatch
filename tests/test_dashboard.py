"""Dashboard rendering (pure function, no terminal needed) and the headless live demo."""

import os
import subprocess
import sys
from pathlib import Path

from chronosmatch.dashboard import render_lines
from chronosmatch.telemetry import Snapshot

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def snap(**overrides) -> Snapshot:
    base = dict(
        processed=50, trades=20, traded_qty=300, best_bid=99, best_ask=101, updated_ns=1,
        orders_per_sec=100_000, latency_p50_ns=750, latency_p99_ns=2_040, target_count=100,
        done=False, bids=[(99, 10), (98, 5)], asks=[(101, 7)],
    )
    base.update(overrides)
    return Snapshot(**base)


def text(lines) -> str:
    return "\n".join(t for t, _ in lines)


def test_waiting_screen_before_first_snapshot() -> None:
    assert "waiting" in text(render_lines(None))


def test_top_of_book_and_spread_are_shown() -> None:
    screen = text(render_lines(snap()))
    assert "BEST BID     99" in screen and "BEST ASK    101" in screen and "SPREAD    2" in screen


def test_progress_rate_and_latency_are_shown() -> None:
    screen = text(render_lines(snap()))
    assert "orders 50 / 100 (50.0%)" in screen
    assert "100,000 orders/s" in screen
    assert "p50 0.75 us" in screen and "p99 2.04 us" in screen


def test_depth_rows_and_book_style() -> None:
    lines = render_lines(snap())
    book_rows = [t for t, style in lines if style == "book"]
    assert len(book_rows) == 5
    assert "99" in book_rows[0] and "101" in book_rows[0]
    assert "98" in book_rows[1] and book_rows[1].rstrip().endswith("5")


def test_empty_book_shows_dashes() -> None:
    screen = text(render_lines(snap(best_bid=None, best_ask=None, bids=[], asks=[])))
    assert "BEST BID      -" in screen and "SPREAD    -" in screen


def test_done_status() -> None:
    assert "status: DONE" in text(render_lines(snap(done=True)))
    assert "status: RUNNING" in text(render_lines(snap()))


def test_headless_live_demo_runs_to_completion() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "chronosmatch.live", "--headless", "--count", "20000", "--rate", "0"],
        env={**os.environ, "PYTHONPATH": str(SRC_DIR)}, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "status: DONE" in proc.stdout
    assert "engine  : processed=20,000" in proc.stdout
