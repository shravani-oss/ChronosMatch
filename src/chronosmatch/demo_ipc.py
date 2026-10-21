"""Mid-review proof (a): 1,000,000 orders cross between two processes without pickling.

    python -m chronosmatch.demo_ipc                 # 1M orders, as fast as possible
    python -m chronosmatch.demo_ipc --rate 100000   # at the 100k/sec target

What it does:
1. Creates a ring buffer file and forbids pickle in this process.
2. Starts the firehose as a *separate OS process* (subprocess), also with pickle forbidden.
3. Pops every order here and compares it, field by field, with the expected seeded stream.
4. Prints a summary and exits 0 only if every order arrived intact and in order.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from chronosmatch import config
from chronosmatch.no_pickle import forbid_pickle
from chronosmatch.order_generator import generate_orders
from chronosmatch.ring_buffer import RingBuffer

_SRC_DIR = Path(__file__).resolve().parents[1]
_TIMEOUT_S = 300.0


@dataclass(frozen=True)
class DemoResult:
    expected: int
    received: int
    mismatches: int
    elapsed_ns: int
    producer_returncode: int
    producer_output: str

    @property
    def ok(self) -> bool:
        return (
            self.received == self.expected
            and self.mismatches == 0
            and self.producer_returncode == 0
        )

    @property
    def orders_per_sec(self) -> float:
        return self.received / (self.elapsed_ns / config.NS_PER_SEC) if self.elapsed_ns else 0.0


def run_demo(ring_path: Path, count: int, seed: int, rate: int, capacity: int) -> DemoResult:
    forbid_pickle()
    with RingBuffer.create(ring_path, capacity) as ring:
        producer = subprocess.Popen(
            [sys.executable, "-m", "chronosmatch.firehose", "--ring", str(ring_path),
             "--count", str(count), "--seed", str(seed), "--rate", str(rate), "--forbid-pickle"],
            env={**os.environ, "PYTHONPATH": str(_SRC_DIR)},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        received = mismatches = 0
        start = None
        deadline = time.monotonic() + _TIMEOUT_S
        try:
            for expected in generate_orders(count, seed=seed):
                item = ring.try_pop()
                while item is None:
                    if time.monotonic() > deadline or producer.poll() not in (None, 0):
                        raise TimeoutError(f"stopped after {received} of {count} orders")
                    item = ring.try_pop()
                if start is None:
                    start = time.perf_counter_ns()  # clock starts at the first order received
                received += 1
                if item[0] != expected:
                    mismatches += 1
            elapsed = time.perf_counter_ns() - start if start is not None else 0
        except TimeoutError:
            elapsed = 0
        finally:
            output, _ = producer.communicate(timeout=_TIMEOUT_S)
    return DemoResult(count, received, mismatches, elapsed, producer.returncode, output.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="1M orders across two processes, no pickle.")
    parser.add_argument("--count", type=int, default=config.MID_REVIEW_ORDER_COUNT)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--rate", type=int, default=0, help="orders/sec, 0 = unlimited")
    parser.add_argument("--capacity", type=int, default=config.RING_DEFAULT_CAPACITY)
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        result = run_demo(Path(tmp) / "demo.ring", args.count, args.seed, args.rate, args.capacity)

    print("ChronosMatch IPC demo: two processes, shared mmap ring buffer, pickle disabled in both")
    print(f"  producer (separate process): {result.producer_output}")
    print(f"  orders expected            : {result.expected:,}")
    print(f"  orders received            : {result.received:,}")
    print(f"  mismatched orders          : {result.mismatches:,}")
    print(f"  bytes moved                : {result.received * config.ORDER_RECORD_SIZE:,}")
    print(f"  receive rate               : {result.orders_per_sec:,.0f} orders/sec")
    print(f"  pickle calls               : 0 (pickle raises in both processes)")
    print(f"  RESULT                     : {'PASS' if result.ok else 'FAIL'}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
