"""Run every mid-review proof and print a PASS/FAIL checklist.

    python scripts/review_check.py            # full check (~1-2 minutes)
    python scripts/review_check.py --quick    # smaller order counts (~30 seconds)

Run it from the repo root with the venv active, after `python setup.py build_ext --inplace`.
Exit code 0 only if every check passes.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def checks(quick: bool) -> list[tuple[str, list[str]]]:
    count = "200000" if quick else "1000000"
    ref_count = "30000" if quick else "100000"  # the reference book is slow (~40 s for 100k)
    py = sys.executable
    return [
        ("Full test suite", [py, "-m", "pytest", "-q"]),
        ("Proof (b): differential tests vs reference book", [py, "-m", "pytest", "-q", "tests/test_differential.py"]),
        (f"Proof (a): {int(count):,} orders between 2 processes, pickle disabled",
         [py, "-m", "chronosmatch.demo_ipc", "--count", count]),
        (f"Pipeline: {int(count):,} orders firehose -> ring -> Cython engine",
         [py, "-m", "chronosmatch.demo_pipeline", "--count", count]),
        (f"Pipeline checked against the reference book ({int(ref_count):,} orders)",
         [py, "-m", "chronosmatch.demo_pipeline", "--count", ref_count, "--reference"]),
        ("Dashboard, headless (50,000 orders)",
         [py, "-m", "chronosmatch.live", "--headless", "--count", "50000", "--rate", "0"]),
    ]


def last_line(text: str) -> str:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Mid-review readiness check.")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    results = []
    for name, cmd in checks(args.quick):
        print(f"... {name}", flush=True)
        start = time.monotonic()
        proc = subprocess.run(cmd, cwd=ROOT, env=ENV, capture_output=True, text=True)
        elapsed = time.monotonic() - start
        ok = proc.returncode == 0
        results.append((ok, name, elapsed, last_line(proc.stdout) or last_line(proc.stderr)))

    print("\nMid-review readiness")
    for ok, name, elapsed, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  ({elapsed:.1f}s)")
        print(f"         {detail}")
    passed = sum(ok for ok, *_ in results)
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
