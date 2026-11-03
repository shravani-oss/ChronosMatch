# 14 - Tail Latency, Part 3: Producer Stalls and the Sparse Ring File

Follows notes 12 (GC ruled out) and 13 (engine pauses do not explain the max).

## Hypothesis from 28 Oct
"The firehose stamps an order and then publishes it; if it is paused in between, that order's
latency includes the pause."

## Instrument
- Firehose: time from taking the entry stamp to the index being published, per order; reports
  the maximum, which order it was, and how many exceeded 50 us.
- Engine: the arrival position of the slowest order.

## Result 1: the slowest order is a producer stall (confirmed)
Pipeline at 100k/s, 300k orders, 5 runs: in 4 of 5 runs the engine's slowest order was **the same
order** as the firehose's slowest publish, with the same delay to within ~1 us
(e.g. 276.75 us vs 276.3 us, both order 28,667). In the 5th the engine itself was paused (962 us).

## Result 2: the stalls sit exactly on 128 KB boundaries of a sparse file
The slow orders (1,019; 8,187; 12,283; 16,379; 20,475; 28,667; 45,051) are all 4,096k - 5 and all
in the ring's first lap. Order 4,096k - 5 lands in slot 4,096k - 6 at byte
192 + (4,096k - 6) x 32 = 131,072k: **the first write into each new 128 KB chunk of the file.**

Cause: `RingBuffer.create` made the file with `truncate`, i.e. a *sparse* file. Its disk blocks
did not exist, so the first write into each 128 KB chunk made macOS allocate it while the
producer waited.

Two wrong guesses on the way (kept here because they are part of the method):
1. Page faults in general: a single-process test showed first-lap pushes of at most 21 us. That
   did not reproduce the effect.
2. CPU contention from the demo computing its expected answer during start-up: precomputing it
   changed nothing.

## Fix
`RingBuffer.create` now writes real zeros for the whole file and touches every page before use
(telemetry file too). A test checks the file is fully allocated (`st_blocks * 512 >= st_size`).

## Evidence (`benchmarks/bench_sparse_ring.py`, interleaved, 200k orders at 100k/s, engine consuming)
| Ring file | Slow pushes at a 128 KB boundary in lap 1 (16 boundaries) | All slow pushes > 50 us | Worst |
|---|---|---|---|
| Sparse (old) | 3, 11, 8 | 39, 298, 68 | 827, 2,811, 455 us |
| **Preallocated** | **0, 0, 0** | 25, 240, 6 | 309, 1,279, 287 us |

The systematic stall is gone. The remaining slow pushes are spread randomly and vary hugely
between runs (6 to 240): OS scheduling noise on a busy laptop (note 12), not something in our code.

## Where tail latency stands now
| Cause | Status |
|---|---|
| Garbage collection | Ruled out (0 collections) - note 12 |
| Python objects in the engine loop | Removed (C loop) - note 13 |
| Sparse ring file stalling the producer | **Fixed** - this note |
| OS preempting the producer or the engine | Remains; needs isolated cores (Linux), not available on macOS |

Best run after the fix: max end-to-end latency 73 us for 300k orders at 100k/s. Noisy runs still
reach several ms when the OS takes a core away.
