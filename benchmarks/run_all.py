"""Run every benchmark in order and report which succeeded.

    python benchmarks/run_all.py             # all benchmarks (several minutes)
    python benchmarks/run_all.py --dry-run   # list what would run
    python benchmarks/run_all.py --only ipc firehose

Each script overwrites its own JSON in benchmarks/results/, so re-running replaces the numbers
quoted in the docs. Close other apps first: background load changes latency results a lot
(docs/notes/12-tail-latency-investigation.md).
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCHMARKS = {
    "serialization": "bench_serialization.py",
    "reference_book": "bench_reference_book.py",
    "order_books": "bench_order_books.py",
    "ipc": "bench_ipc.py",
    "firehose": "bench_firehose.py",
    "engine_loop": "bench_engine_loop.py",
    "tail_latency": "bench_tail_latency.py",
    "sparse_ring": "bench_sparse_ring.py",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all ChronosMatch benchmarks.")
    parser.add_argument("--only", nargs="+", choices=sorted(BENCHMARKS), help="run just these")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    names = args.only or list(BENCHMARKS)
    missing = [n for n in names if not (HERE / BENCHMARKS[n]).exists()]
    if missing:
        print(f"missing benchmark scripts: {missing}")
        return 1
    if args.dry_run:
        for name in names:
            print(f"would run: python benchmarks/{BENCHMARKS[name]}")
        return 0

    failures = []
    for name in names:
        print(f"... {name}", flush=True)
        start = time.monotonic()
        proc = subprocess.run([sys.executable, str(HERE / BENCHMARKS[name])], cwd=HERE.parent,
                              capture_output=True, text=True)
        status = "ok" if proc.returncode == 0 else "FAILED"
        print(f"    {status} in {time.monotonic() - start:.0f}s")
        if proc.returncode != 0:
            failures.append(name)
            print(proc.stderr.strip()[-500:])
    print(f"\n{len(names) - len(failures)}/{len(names)} benchmarks succeeded")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
