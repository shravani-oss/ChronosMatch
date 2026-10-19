"""Cost of turning one order into bytes and back: struct vs pickle vs JSON.

Run from the repo root:  python benchmarks/bench_serialization.py
Writes benchmarks/results/serialization.json.

Each method does a full round trip that ends with an Order object, so the comparison is fair.
"struct_raw" is reported separately: it packs/unpacks plain numbers and builds no Order, to show
how much of the struct cost is the Python object rather than the bytes.
"""

import json
import pickle
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronosmatch import config  # noqa: E402
from chronosmatch.order_generator import generate_orders  # noqa: E402
from chronosmatch.order_record import (  # noqa: E402
    ORDER_STRUCT,
    pack_order_into,
    unpack_order_from,
)
from chronosmatch.types import Order, Side  # noqa: E402

ORDER_COUNT = 200_000
SEED = 0
MEASURED_RUNS = 5
RESULT_PATH = Path(__file__).parent / "results" / "serialization.json"

_BUFFER = bytearray(config.ORDER_RECORD_SIZE)


def struct_round_trip(order: Order) -> Order:
    pack_order_into(_BUFFER, 0, order)
    return unpack_order_from(_BUFFER, 0)[0]


def pickle_round_trip(order: Order) -> Order:
    return pickle.loads(pickle.dumps(order, protocol=pickle.HIGHEST_PROTOCOL))


def json_round_trip(order: Order) -> Order:
    text = json.dumps([order.order_id, order.side.value, order.price, order.quantity])
    order_id, side, price, quantity = json.loads(text)
    return Order(order_id, Side(side), price, quantity)


def struct_raw_round_trip(order: Order) -> tuple:
    ORDER_STRUCT.pack_into(_BUFFER, 0, order.order_id, 0, order.price, order.quantity, 0)
    return ORDER_STRUCT.unpack_from(_BUFFER, 0)


METHODS = {"struct": struct_round_trip, "pickle": pickle_round_trip, "json": json_round_trip}


def encoded_size(name: str, order: Order) -> int:
    if name == "struct":
        return config.ORDER_RECORD_SIZE
    if name == "pickle":
        return len(pickle.dumps(order, protocol=pickle.HIGHEST_PROTOCOL))
    return len(json.dumps([order.order_id, order.side.value, order.price, order.quantity]).encode())


def ns_per_order(fn, orders: list[Order]) -> float:
    start = time.perf_counter_ns()
    for order in orders:
        fn(order)
    return (time.perf_counter_ns() - start) / len(orders)


def main() -> None:
    orders = list(generate_orders(ORDER_COUNT, seed=SEED))
    for name, fn in METHODS.items():  # correctness first, then warm-up
        assert all(fn(o) == o for o in orders[:1000]), name

    results = {}
    for name, fn in METHODS.items():
        samples = [ns_per_order(fn, orders) for _ in range(MEASURED_RUNS)]
        results[name] = {
            "round_trip_ns_per_order_median": round(statistics.median(samples), 1),
            "bytes_per_order": encoded_size(name, orders[0]),
        }
    raw_samples = [ns_per_order(struct_raw_round_trip, orders) for _ in range(MEASURED_RUNS)]
    results["struct_raw_no_order_object"] = {
        "round_trip_ns_per_order_median": round(statistics.median(raw_samples), 1),
        "bytes_per_order": config.ORDER_RECORD_SIZE,
    }
    base = results["struct"]["round_trip_ns_per_order_median"]
    for entry in results.values():
        entry["relative_to_struct"] = round(entry["round_trip_ns_per_order_median"] / base, 2)

    result = {
        "order_count": ORDER_COUNT,
        "measured_runs": MEASURED_RUNS,
        "methods": results,
        "python": platform.python_version(),
        "machine": platform.platform(),
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
