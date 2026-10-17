"""Single place for project-wide constants.

Keep numbers here, not scattered through the code ("no magic numbers").
Layout and buffer sizes are added when those modules are designed.
"""

# Targets from the project brief.
TARGET_ORDERS_PER_SEC: int = 100_000     # Week 1 firehose throughput target
MID_REVIEW_ORDER_COUNT: int = 1_000_000  # orders that must cross two processes
MATCH_LATENCY_BUDGET_US: int = 50        # sub-50 microsecond matching goal

NS_PER_US: int = 1_000

# Defaults for the synthetic order generator (prices are integer ticks).
DEFAULT_MID_PRICE_TICKS: int = 100
DEFAULT_PRICE_BAND_TICKS: int = 5       # prices fall in mid +/- band
DEFAULT_MAX_ORDER_QUANTITY: int = 100

# Binary order record (see docs/notes/03-order-record.md).
# Little-endian, no implicit padding: order_id u64, timestamp_ns u64, price i64,
# quantity u32, side u8, 3 pad bytes  -> 32 bytes (two records per 64-byte cache line).
ORDER_RECORD_FORMAT: str = "<QQqIB3x"
ORDER_RECORD_SIZE: int = 32
SIDE_CODE_BUY: int = 0
SIDE_CODE_SELL: int = 1
