"""Full pipeline demo: firehose process -> shared ring -> Cython engine process.

    python -m chronosmatch.demo_pipeline                         # 1M orders, unlimited rate
    python -m chronosmatch.demo_pipeline --rate 100000           # at the 100k/sec target
    python -m chronosmatch.demo_pipeline --count 100000 --reference   # also check vs reference

Proves both mid-review claims in one run:
(a) orders cross between separate processes through shared memory, pickle disabled in both;
(b) the engine's trades are correct: its trade fingerprint (count, quantity, notional, 64-bit
    checksum of every trade in order) must equal an independent run of the same orders, and
    with --reference also the pure-Python reference book's trades.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from chronosmatch import config
from chronosmatch.cython_book import CythonOrderBook
from chronosmatch.no_pickle import forbid_pickle
from chronosmatch.order_generator import generate_orders
from chronosmatch.reference_book import ReferenceOrderBook
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.trade_digest import TradeDigest
from chronosmatch.types import Side

_SRC_DIR = Path(__file__).resolve().parents[1]
_TIMEOUT_S = 600.0


@dataclass(frozen=True)
class PipelineResult:
    count: int
    firehose_output: str
    firehose_returncode: int
    engine: dict | None
    engine_returncode: int
    engine_error: str
    expected_stats: tuple[int, int, int, int]
    reference_stats: tuple[int, int, int, int] | None

    @property
    def ok(self) -> bool:
        if self.firehose_returncode != 0 or self.engine_returncode != 0 or self.engine is None:
            return False
        if f"sent={self.count}" not in self.firehose_output:
            return False
        engine_stats = tuple(self.engine["trade_stats"])
        if self.engine["processed"] != self.count or engine_stats != self.expected_stats:
            return False
        return self.reference_stats is None or self.reference_stats == self.expected_stats


def expected_trade_stats(count: int, seed: int) -> tuple[int, int, int, int]:
    """Match the same seeded orders directly (no ring, no processes) in a fresh Cython book."""
    book = CythonOrderBook()
    for o in generate_orders(count, seed=seed):
        book.submit_raw(o.side is Side.BUY, o.order_id, o.price, o.quantity)
    return book.trade_stats


def reference_trade_stats(count: int, seed: int) -> tuple[int, int, int, int]:
    """Same orders through the pure-Python reference book (slow: ~13k orders/sec)."""
    book, digest = ReferenceOrderBook(), TradeDigest()
    for o in generate_orders(count, seed=seed):
        digest.add(book.submit(o))
    return digest.stats


def run_pipeline(
    ring_path: Path, count: int, seed: int, rate: int, capacity: int, with_reference: bool
) -> PipelineResult:
    env = {**os.environ, "PYTHONPATH": str(_SRC_DIR)}
    with RingBuffer.create(ring_path, capacity):
        engine = subprocess.Popen(
            [sys.executable, "-m", "chronosmatch.engine", "--ring", str(ring_path),
             "--count", str(count), "--forbid-pickle"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        firehose = subprocess.Popen(
            [sys.executable, "-m", "chronosmatch.firehose", "--ring", str(ring_path),
             "--count", str(count), "--seed", str(seed), "--rate", str(rate), "--forbid-pickle"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        # While the two processes run, compute the independent expected answers here.
        expected = expected_trade_stats(count, seed)
        reference = reference_trade_stats(count, seed) if with_reference else None

        fh_out, _ = firehose.communicate(timeout=_TIMEOUT_S)
        eng_out, eng_err = engine.communicate(timeout=_TIMEOUT_S)

    engine_summary = json.loads(eng_out) if engine.returncode == 0 and eng_out.strip() else None
    return PipelineResult(
        count=count,
        firehose_output=fh_out.strip(),
        firehose_returncode=firehose.returncode,
        engine=engine_summary,
        engine_returncode=engine.returncode,
        engine_error=eng_err.strip(),
        expected_stats=expected,
        reference_stats=reference,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Firehose -> ring -> Cython engine, verified.")
    parser.add_argument("--count", type=int, default=config.MID_REVIEW_ORDER_COUNT)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--rate", type=int, default=0, help="orders/sec, 0 = unlimited")
    parser.add_argument("--capacity", type=int, default=config.RING_DEFAULT_CAPACITY)
    parser.add_argument("--reference", action="store_true", help="also verify with the slow reference book")
    args = parser.parse_args(argv)
    forbid_pickle()

    with tempfile.TemporaryDirectory() as tmp:
        r = run_pipeline(Path(tmp) / "pipe.ring", args.count, args.seed, args.rate, args.capacity, args.reference)

    print("ChronosMatch pipeline: firehose process -> mmap ring -> Cython engine process")
    print(f"  firehose  : {r.firehose_output}")
    if r.engine is None:
        print(f"  engine    : FAILED (exit {r.engine_returncode}) {r.engine_error}")
    else:
        e = r.engine
        rate = e["processed"] / (e["elapsed_ns"] / 1e9) if e["elapsed_ns"] else 0
        print(f"  engine    : processed={e['processed']:,} rate={rate:,.0f}/s "
              f"best_bid={e['best_bid']} best_ask={e['best_ask']}")
        print(f"  latency   : entry->matched p50={e['latency_p50_us']} us "
              f"p99={e['latency_p99_us']} us max={e['latency_max_us']} us")
        print(f"  trades    : engine    {tuple(e['trade_stats'])}")
    print(f"  trades    : expected  {r.expected_stats}")
    if r.reference_stats is not None:
        print(f"  trades    : reference {r.reference_stats}")
    print("  pickle    : disabled in firehose, engine and this process")
    print(f"  RESULT    : {'PASS' if r.ok else 'FAIL'}")
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
