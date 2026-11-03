"""Sparse vs preallocated ring file: where do slow producer pushes happen? (note 14)

Run from the repo root:  python benchmarks/bench_sparse_ring.py
A producer (this process) pushes 200k orders at 100k/s into a fresh ring while the engine process
consumes them. Every push slower than 50 us is recorded with its position. The ring is created
either as a sparse file (the old `truncate` way) or preallocated (current `RingBuffer.create`).
Modes are interleaved, 3 runs each.
"""
import mmap, os, subprocess, sys, tempfile, time
from pathlib import Path
SRC = str(Path(__file__).resolve().parents[1] / "src")
sys.path.insert(0, SRC)
from chronosmatch import config
from chronosmatch.order_generator import generate_orders
from chronosmatch.ring_buffer import RingBuffer, _META

COUNT, RATE, CAP = 200_000, 100_000, 65_536
SLOTS_PER_128K = 131_072 // 32

def create_sparse(path):
    size = config.RING_HEADER_SIZE + CAP * 32
    with open(path, "wb") as f:
        f.truncate(size)
    file = open(path, "r+b"); mm = mmap.mmap(file.fileno(), size)
    _META.pack_into(mm, 0, config.RING_MAGIC, config.RING_VERSION, CAP, 32)
    return RingBuffer(file, mm)

def run(mode):
    orders = list(generate_orders(COUNT, seed=0))
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "s.ring"
        ring = create_sparse(path) if mode == "sparse" else RingBuffer.create(path, CAP)
        eng = subprocess.Popen([sys.executable, "-m", "chronosmatch.engine", "--ring", str(path), "--count", str(COUNT)],
                               env={**os.environ, "PYTHONPATH": SRC}, stdout=subprocess.PIPE)
        time.sleep(0.5)
        clock = time.perf_counter_ns; slow = []; start = clock()
        for i, o in enumerate(orders, 1):
            s = clock()
            while not ring.try_push(o, s): s = clock()
            g = clock() - s
            if g > 50_000: slow.append((i, g))
            if i % 1000 == 0:
                due = start + i * 1_000_000_000 // RATE
                while clock() < due: time.sleep(0.0005)
        eng.communicate(); ring.close()
    # slot of order i is i-1; byte offset = 192 + (i-1)*32; "boundary" = first slot whose bytes start a new 128 KB chunk of the file
    boundary = [(i, g) for i, g in slow if (config.RING_HEADER_SIZE + (i - 1) * 32) // 131_072 != (config.RING_HEADER_SIZE + (i - 2) * 32) // 131_072 or
                (config.RING_HEADER_SIZE + (i - 1) * 32 + 31) // 131_072 != (config.RING_HEADER_SIZE + (i - 1) * 32) // 131_072]
    first_lap = [s for s in boundary if s[0] <= CAP]
    print(f"{mode:13s}: slow pushes >50us = {len(slow):3d} | at a 128KB boundary in lap 1 = {len(first_lap):2d} "
          f"(median {sorted(g for _, g in first_lap)[len(first_lap)//2]/1000 if first_lap else 0:.0f} us) | worst = {max((g for _, g in slow), default=0)/1000:.0f} us")

for _ in range(3):
    for mode in ("sparse", "preallocated"):
        run(mode)
