"""Smoke tests: the package imports and the config constants are sane."""

import chronosmatch
from chronosmatch import config


def test_package_has_version() -> None:
    assert chronosmatch.__version__ == "0.1.0"


def test_targets_match_project_brief() -> None:
    assert config.TARGET_ORDERS_PER_SEC == 100_000
    assert config.MID_REVIEW_ORDER_COUNT == 1_000_000


def test_latency_budget_converts_to_nanoseconds() -> None:
    assert config.MATCH_LATENCY_BUDGET_US * config.NS_PER_US == 50_000
