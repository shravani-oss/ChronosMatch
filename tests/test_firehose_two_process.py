"""Run the firehose as a separate OS process via its command line; consume here."""

import os
import subprocess
import sys
from pathlib import Path

from chronosmatch.ipc_demo import consume
from chronosmatch.order_generator import generate_orders
from chronosmatch.ring_buffer import RingBuffer

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
ORDER_COUNT = 20_000
TIMEOUT_S = 60.0


def test_firehose_cli_feeds_another_process(tmp_path: Path) -> None:
    path = tmp_path / "cli.ring"
    env = {**os.environ, "PYTHONPATH": str(SRC_DIR)}
    with RingBuffer.create(path, 1024) as ring:
        proc = subprocess.Popen(
            [sys.executable, "-m", "chronosmatch.firehose", "--ring", str(path),
             "--count", str(ORDER_COUNT), "--seed", "5", "--rate", "0"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            received = consume(ring, ORDER_COUNT, TIMEOUT_S)
        finally:
            out, err = proc.communicate(timeout=TIMEOUT_S)

    assert proc.returncode == 0, err
    assert f"sent={ORDER_COUNT}" in out
    assert received == list(generate_orders(ORDER_COUNT, seed=5))
