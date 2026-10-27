"""Record every garbage-collector run (generation and pause length) during a block of code.

Python's cyclic GC runs when enough container objects (tuples, lists, ...) have been allocated.
While it runs, the program is paused. `gc.callbacks` lets us time each run:

    with GcMonitor() as mon:
        run_engine(...)
    mon.summary()  # {"collections": [gen0, gen1, gen2], "total_pause_us": ..., "max_pause_us": ...}
"""

import gc
import time


class GcMonitor:
    def __init__(self) -> None:
        self.collections = [0, 0, 0]
        self.pauses_ns: list[int] = []
        self._started_ns = 0

    def _callback(self, phase: str, info: dict) -> None:
        if phase == "start":
            self._started_ns = time.perf_counter_ns()
        else:
            self.pauses_ns.append(time.perf_counter_ns() - self._started_ns)
            self.collections[info["generation"]] += 1

    def __enter__(self) -> "GcMonitor":
        gc.callbacks.append(self._callback)
        return self

    def __exit__(self, *exc: object) -> None:
        gc.callbacks.remove(self._callback)

    def summary(self) -> dict:
        return {
            "collections": list(self.collections),
            "total_pause_us": round(sum(self.pauses_ns) / 1_000, 1),
            "max_pause_us": round(max(self.pauses_ns, default=0) / 1_000, 1),
        }
