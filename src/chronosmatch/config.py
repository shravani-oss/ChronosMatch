"""Single place for project-wide constants.

Keep numbers here, not scattered through the code ("no magic numbers").
Layout and buffer sizes are added when those modules are designed.
"""

# Targets from the project brief.
TARGET_ORDERS_PER_SEC: int = 100_000     # Week 1 firehose throughput target
MID_REVIEW_ORDER_COUNT: int = 1_000_000  # orders that must cross two processes
MATCH_LATENCY_BUDGET_US: int = 50        # sub-50 microsecond matching goal

NS_PER_US: int = 1_000
