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
import contextlib
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
    ledger: dict | None = None          # ledger summary when run with a ledger
    ledger_returncode: int | None = None
    ledger_error: str = ""

    @property
    def ledger_ok(self) -> bool:
        """Every trade the engine made is in SQLite, in order (fingerprints equal)."""
        if self.ledger_returncode is None:
            return True  # no ledger in this run
        return (
            self.ledger_returncode == 0
            and self.ledger is not None
            and self.engine is not None
            and tuple(self.ledger["fingerprint"]) == tuple(self.engine["trade_stats"])
            and self.ledger["trades_written"] == self.engine["trade_stats"][0]
        )

    @property
    def ok(self) -> bool:
        if self.firehose_returncode != 0 or self.engine_returncode != 0 or self.engine is None:
            return False
        if f"sent={self.count}" not in self.firehose_output:
            return False
        engine_stats = tuple(self.engine["trade_stats"])
        if self.engine["processed"] != self.count or engine_stats != self.expected_stats:
            return False
        if self.reference_stats is not None and self.reference_stats != self.expected_stats:
            return False
        return self.ledger_ok


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
    ring_path: Path,
    count: int,
    seed: int,
    rate: int,
    capacity: int,
    with_reference: bool,
    engine_args: tuple[str, ...] = (),
    ledger_db: Path | None = None,
    ledger_args: tuple[str, ...] = (),
) -> PipelineResult:
    """With `ledger_db`, a trade ring and a ledger process are added and checked as well."""
    env = {**os.environ, "PYTHONPATH": str(_SRC_DIR)}
    trades_path = ring_path.with_suffix(".trades")
    ledger = None
    with contextlib.ExitStack() as stack:
        stack.enter_context(RingBuffer.create(ring_path, capacity))
        if ledger_db is not None:
            stack.enter_context(
                RingBuffer.create(trades_path, config.TRADE_RING_DEFAULT_CAPACITY, config.RING_MAGIC_TRADES)
            )
            ledger = subprocess.Popen(
                [sys.executable, "-m", "chronosmatch.ledger", "--trades", str(trades_path),
                 "--db", str(ledger_db), "--forbid-pickle", *ledger_args],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            engine_args = (*engine_args, "--trades", str(trades_path))
        engine = subprocess.Popen(
            [sys.executable, "-m", "chronosmatch.engine", "--ring", str(ring_path),
             "--count", str(count), "--forbid-pickle", *engine_args],
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
        if ledger is not None:
            if engine.returncode != 0 and ledger.poll() is None:
                ledger.terminate()  # no end-of-stream will come
            led_out, led_err = ledger.communicate(timeout=_TIMEOUT_S)

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
        ledger=json.loads(led_out) if ledger is not None and ledger.returncode == 0 and led_out.strip() else None,
        ledger_returncode=ledger.returncode if ledger is not None else None,
        ledger_error=led_err.strip() if ledger is not None else "",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Firehose -> ring -> Cython engine, verified.")
    parser.add_argument("--count", type=int, default=config.MID_REVIEW_ORDER_COUNT)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--rate", type=int, default=0, help="orders/sec, 0 = unlimited")
    parser.add_argument("--capacity", type=int, default=config.RING_DEFAULT_CAPACITY)
    parser.add_argument("--reference", action="store_true", help="also verify with the slow reference book")
    parser.add_argument("--ledger", metavar="DB", help="also run the SQLite ledger, writing trades to DB")
    args = parser.parse_args(argv)
    forbid_pickle()

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(args.ledger).resolve() if args.ledger else None
        if db is not None and db.exists():
            db.unlink()  # a fresh ledger per run, so its fingerprint covers exactly this run
        r = run_pipeline(Path(tmp) / "pipe.ring", args.count, args.seed, args.rate, args.capacity,
                         args.reference, ledger_db=db)

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
              f"p99={e['latency_p99_us']} us p99.9={e['latency_p999_us']} us "
              f"max={e['latency_max_us']} us")
        gc_info = e["gc"]
        print(f"  gc        : mode={e['gc_mode']} collections(gen0,1,2)={gc_info['collections']} "
              f"total pause={gc_info['total_pause_us']} us max pause={gc_info['max_pause_us']} us")
        if e["loop_pauses"] is not None:
            lp = e["loop_pauses"]
            print(f"  loop      : {e['loop']}  paused >50us={lp['gaps_over_50us']} "
                  f">1ms={lp['gaps_over_1ms']} longest={lp['max_gap_us']} us")
        else:
            print(f"  loop      : {e['loop']}")
        print(f"  trades    : engine    {tuple(e['trade_stats'])}")
    print(f"  trades    : expected  {r.expected_stats}")
    if r.reference_stats is not None:
        print(f"  trades    : reference {r.reference_stats}")
    if r.ledger_returncode is not None:
        if r.ledger is None:
            print(f"  ledger    : FAILED (exit {r.ledger_returncode}) {r.ledger_error}")
        else:
            lg = r.ledger
            rate = lg["trades_written"] / (lg["elapsed_ns"] / 1e9) if lg["elapsed_ns"] else 0
            print(f"  ledger    : {lg['trades_written']:,} trades in SQLite ({rate:,.0f}/s, "
                  f"{lg['batches']} transactions, largest {lg['largest_batch']:,}), "
                  f"engine waited for it {r.engine.get('trade_ring_waits')} times")
            print(f"  trades    : ledger    {tuple(lg['fingerprint'])}  (read back from SQLite)")
    print("  pickle    : disabled in every process")
    print(f"  RESULT    : {'PASS' if r.ok else 'FAIL'}")
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
