"""One command for the live demo: firehose + engine processes, with the dashboard in front.

    python -m chronosmatch.live                        # 2M orders at 100k/sec, curses dashboard
    python -m chronosmatch.live --rate 0               # unlimited speed
    python -m chronosmatch.live --headless             # plain-text frames instead of curses

Pressing q stops the dashboard; any process still running is stopped.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from chronosmatch import config
from chronosmatch.dashboard import render_lines, run_curses
from chronosmatch.ring_buffer import RingBuffer
from chronosmatch.telemetry import TelemetryBlock

_SRC_DIR = Path(__file__).resolve().parents[1]
_DEFAULT_COUNT = 2_000_000
_HEADLESS_FRAME_S = 1.0
_STOP_TIMEOUT_S = 10.0


def _start(module: str, args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", module, *args, "--forbid-pickle"],
        env={**os.environ, "PYTHONPATH": str(_SRC_DIR)},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def _run_headless(tel: TelemetryBlock, engine: subprocess.Popen) -> None:
    while True:
        snap = tel.read()
        print("\n".join(text for text, _ in render_lines(snap)), end="\n\n", flush=True)
        if (snap is not None and snap.done) or engine.poll() is not None:
            return
        time.sleep(_HEADLESS_FRAME_S)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ChronosMatch live demo with dashboard.")
    parser.add_argument("--count", type=int, default=_DEFAULT_COUNT)
    parser.add_argument("--rate", type=int, default=config.TARGET_ORDERS_PER_SEC, help="0 = unlimited")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        ring_path, tel_path = Path(tmp) / "live.ring", Path(tmp) / "live.tel"
        with RingBuffer.create(ring_path), TelemetryBlock.create(tel_path) as tel:
            engine = _start("chronosmatch.engine",
                            ["--ring", str(ring_path), "--count", str(args.count), "--telemetry", str(tel_path)])
            firehose = _start("chronosmatch.firehose",
                              ["--ring", str(ring_path), "--count", str(args.count),
                               "--seed", str(args.seed), "--rate", str(args.rate)])
            try:
                if args.headless:
                    _run_headless(tel, engine)
                else:
                    run_curses(tel, footer=f"{args.count:,} orders at "
                                           f"{'unlimited' if args.rate == 0 else f'{args.rate:,}/s'}  |  q: quit")
            finally:
                for proc in (firehose, engine):
                    if proc.poll() is None:
                        proc.terminate()
                outputs = {name: proc.communicate(timeout=_STOP_TIMEOUT_S)
                           for name, proc in (("firehose", firehose), ("engine", engine))}

    print(f"firehose: {outputs['firehose'][0].strip() or 'stopped early'}")
    engine_out = outputs["engine"][0].strip()
    if engine.returncode == 0 and engine_out:
        summary = json.loads(engine_out)
        print(f"engine  : processed={summary['processed']:,} trades={summary['trade_stats'][0]:,} "
              f"p50={summary['latency_p50_us']} us p99={summary['latency_p99_us']} us")
        return 0
    print("engine  : stopped early")
    return 0


if __name__ == "__main__":
    sys.exit(main())
