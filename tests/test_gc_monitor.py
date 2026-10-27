"""GC monitor and the engine's --gc switch."""

import gc

from chronosmatch.gc_monitor import GcMonitor


def test_counts_explicit_collections_by_generation() -> None:
    with GcMonitor() as mon:
        gc.collect(0)
        gc.collect(2)
    summary = mon.summary()
    assert summary["collections"][0] >= 1 and summary["collections"][2] >= 1
    assert summary["max_pause_us"] >= 0 and summary["total_pause_us"] >= summary["max_pause_us"]


def test_callback_is_removed_after_exit() -> None:
    mon = GcMonitor()
    with mon:
        pass
    assert mon._callback not in gc.callbacks
    gc.collect()
    assert mon.collections == [0, 0, 0]


def test_empty_summary() -> None:
    assert GcMonitor().summary() == {"collections": [0, 0, 0], "total_pause_us": 0.0, "max_pause_us": 0.0}


def test_pipeline_reports_gc_stats_and_can_disable_gc(tmp_path) -> None:
    from chronosmatch.demo_pipeline import run_pipeline

    on = run_pipeline(tmp_path / "on.ring", 20_000, 1, 0, 1024, False)
    off = run_pipeline(tmp_path / "off.ring", 20_000, 1, 0, 1024, False, engine_args=("--gc", "off"))
    assert on.ok and off.ok
    assert on.engine["gc_mode"] == "on" and off.engine["gc_mode"] == "off"
    assert off.engine["gc"]["collections"] == [0, 0, 0]
    assert on.engine["latency_p50_us"] <= on.engine["latency_p999_us"] <= on.engine["latency_max_us"]
