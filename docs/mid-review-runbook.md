# Mid-Review Runbook (27-30 Oct)

## 15 minutes before
```bash
cd ~/Documents/Chronos-match
source .venv/bin/activate
python setup.py build_ext --inplace     # make sure the Cython modules match the source
python scripts/review_check.py          # all 6 checks must say PASS (~1 minute)
```
Last full run (27 Oct): 6/6 PASS. If anything fails, run that one command by hand (listed in
`scripts/review_check.py`) and read its output; do not demo a failing proof.

Make the terminal wide (at least 70 columns) and tall (at least 22 lines) for the dashboard.

## Demo order (about 10 minutes)
| # | Show | Command | Say |
|---|---|---|---|
| 1 | Architecture | README diagram | Three processes, two shared-memory blocks, no pickle on the data path. |
| 2 | Live dashboard | `PYTHONPATH=src python -m chronosmatch.live` | Firehose 100k orders/s -> ring -> Cython engine; dashboard is its own process reading a seqlock snapshot. Press q. |
| 3 | Proof (a) | `PYTHONPATH=src python -m chronosmatch.demo_ipc` | 1M orders across two processes; pickle raises in both; every order checked; PASS. |
| 4 | Proof (b) | `pytest tests/test_differential.py -v` | Cython book vs simple reference book on 108k random orders, identical after every order. A planted bug made 36/36 fail. |
| 5 | Both together | `PYTHONPATH=src python -m chronosmatch.demo_pipeline` | Engine's trade fingerprint equals an independent run; ~800k orders/s end to end; p50 ~0.75 us. |
| 6 | Numbers | README Results table | Ring 12x faster than pickling queue; Cython book 15.9M orders/s raw. State the caveats. |

## Say these limitations before you are asked
- Learning-grade, not real HFT (C++/FPGA territory).
- The Cython speedup is against a deliberately simple reference book (note 09).
- Tail latency at a paced 100k/s is not under control yet: p99 varies ~1-200 us, max spikes up to
  ~18 ms. Measured so far (note 12): not the GC (0 collections); consistent with macOS stopping
  busy-spinning processes on a contended M1 (hiccup meter saw gaps up to ~15 ms).
- Prices must fit 1..10,000 ticks; memory is fixed up front (note 08).
- Websocket feed deferred (decision D16).

## Your best story: the ARM stale-read bug (note 04)
Symptom (different trade counts for identical runs) -> diagnosis (stale record was exactly one
lap old) -> cause (ARM reorders memory operations; Python has no ordering guarantee) -> fix
(release store / acquire load via C atomics in Cython) -> evidence (3 in 3M before, 0 in 6M
after, no speed cost) -> lesson ("unlikely" is not a correctness argument).

## If something goes wrong live
| Problem | Do this |
|---|---|
| Dashboard looks garbled or terminal too small | `python -m chronosmatch.live --headless --count 300000` |
| `ModuleNotFoundError: chronosmatch` | You forgot `PYTHONPATH=src` (or the venv). |
| `ImportError` mentioning `cython_book`/`atomics` | Run `python setup.py build_ext --inplace`. |
| A demo prints FAIL | Show `scripts/review_check.py` output from before the review; explain what the check verifies; do not hide it. |

## Where answers live
`docs/viva-and-interview-prep.md` (Q&A per module + 2-minute pitch), `docs/decisions.md`
(why each choice), `docs/notes/NN-*.md` (one per module).
