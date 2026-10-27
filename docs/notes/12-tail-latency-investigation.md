# 12 - Week 3: Tail-Latency Investigation (part 1)

## The problem
End-to-end latency (firehose entry -> matched) has an excellent median (~0.75 us) but an
unstable tail at a paced 100k orders/s: p99 from ~1 us to ~200 us between runs, max spikes of
~0.25 ms to ~18 ms (notes 10, 11).

## Hypothesis 1: Python's garbage collector -> REJECTED
**Instrument:** `gc_monitor.py` registers `gc.callbacks` and records every collection's
generation and pause. Validated first: 300,000 lists kept alive -> 149 collections, longest
pause 7.5 ms. So the instrument works, and GC pauses *can* be milliseconds.

**Result:** across every engine run (5 + 5 interleaved, 300k orders each) the engine performed
**0 collections**, with GC on or off.

**Why:** CPython triggers a young collection when allocations *minus* deallocations of container
objects exceed 2,000. The engine creates a tuple per order, but each dies immediately and is
freed by reference counting, so the count never grows. A loop that allocates and frees did not
trigger GC either; only objects that *stay alive* do.

**GC on vs off** (`--gc off` = `gc.freeze()` + `gc.disable()`), runs interleaved:
| Mode | p99 per run (us) | median p99 | median p99.9 | median max | collections |
|---|---|---|---|---|---|
| on | 5.4, 3.5, 1.2, 1.5, 2.2 | 2.2 us | 39.0 us | 278 us | 0 |
| off | 5.6, 1.3, 1.1, 3.0, 633.2 | 3.0 us | 38.9 us | 307 us | 0 |
No consistent difference. Disabling GC is not the fix, so `--gc off` stays an experiment
switch, not the default.

**Mistake caught:** the first version ran all "on" runs and then all "off" runs; "off" looked
better (median p99 1.25 vs 3.58 us). With 0 collections in both modes that could not be GC, and
interleaving the runs made the difference disappear. Run order was the confound.

## Hypothesis 2: the operating system stops our spinning processes -> SUPPORTED
**Instrument:** a "hiccup meter" (`benchmarks/bench_tail_latency.py`, experiment B): a process
that only reads the clock in a tight loop for 5 s and records every gap. A running loop reads
the clock every ~80 ns; a long gap means the process was not running.

| Condition | Gaps > 100 us | Gaps > 1 ms | Largest gaps |
|---|---|---|---|
| Meter alone, run 1 | 0 | 0 | 96 us |
| Meter alone, run 2 | 0 | 0 | 59 us |
| Meter + pipeline running, run 1 | 11 | 0 | 581 us |
| Meter + pipeline running, run 2 | 76 | 23 | 14.8 ms, 14.4 ms, 10.0 ms |

Machine: Apple M1, 4 performance + 4 efficiency cores; ~0.5 core already used by other apps.
While the pipeline runs, the engine and the meter each spin a full core, the firehose bursts,
and the demo process computes its expected answer.

**Reading:** a process that never blocks still gets stopped by the OS, for tens of microseconds
on a quiet machine and for **up to ~15 ms** when cores are contended. That is the same size as
the engine's worst spikes (0.25-18 ms). The ~10-15 ms gaps are consistent with a process losing
its core for a full scheduler time slice, though that is an interpretation, not a measurement.
This is strong circumstantial evidence, not proof that every engine spike is a preemption; the
next step is to record gaps *inside* the engine loop and line them up with slow orders.

**Mistake caught:** the first version of experiment B ran the pipeline in a *thread* of the
meter's process. The meter then saw uniform ~6.3 ms gaps: the GIL being handed between the two
threads (switch interval 5 ms), not the OS. The meter must be alone in its interpreter.

## What would help (not done yet)
| Idea | Expected effect | Catch |
|---|---|---|
| Fewer busy-spinning processes; let the engine sleep briefly when idle | Less core contention | Adds wake-up latency when orders arrive |
| Raise the engine's scheduling priority (macOS QoS class "user interactive") | OS prefers it on performance cores | A hint, not a guarantee; no hard core pinning on macOS |
| Run on Linux with isolated cores (`isolcpus`, `taskset`, `SCHED_FIFO`) | Real HFT practice: nothing else runs on the engine's core | Different machine |
| Move the pop-and-match loop into Cython | Fewer Python objects and instructions per order | Does not stop OS preemption |

## Interview takeaway
"I measured instead of guessing. The obvious suspect, Python's GC, ran zero times. The real
cause was the OS descheduling busy-spinning processes on a contended 4-performance-core laptop,
which a hiccup meter showed directly. Production systems handle this with core isolation, which
macOS does not offer. I also caught two flaws in my own experiments: a run-order confound and a
GIL artefact."

Raw data: `benchmarks/results/tail_latency.json` (latest run).
