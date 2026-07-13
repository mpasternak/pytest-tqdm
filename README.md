# pytest-tqdm

[![CI](https://github.com/mpasternak/pytest-tqdm/actions/workflows/ci.yml/badge.svg)](https://github.com/mpasternak/pytest-tqdm/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pytest-tqdm.svg)](https://pypi.org/project/pytest-tqdm/)
[![Python versions](https://img.shields.io/pypi/pyversions/pytest-tqdm.svg)](https://pypi.org/project/pytest-tqdm/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**One** [`tqdm`](https://github.com/tqdm/tqdm) progress bar for your whole
pytest run — even under [`pytest-xdist`](https://github.com/pytest-dev/pytest-xdist).
Failures print above the bar with full tracebacks; everything else stays quiet.
Interactive-only, so it never pollutes CI logs or AI-agent output.

```
 42%|███████▉           | 512/1210 [00:37<00:48, 14.3test/s, ✓510 ✗2 s0 ▸ test_bar]
```

…and a one-line summary when the run finishes:

```
pytest-tqdm ▸ 1210 tests in 01:25  ·  14.2 tests/s  ·  ✓1180 ✗2 s28  ·  8 workers
```

## Why

Under `pytest-xdist` the usual pretty progress plugins render a bar *per file*
or *per worker*, and the output interleaves into noise. `pytest-tqdm` collapses
the whole session into a **single** aggregated bar driven on the xdist
controller (which receives every worker's report), so you get one clean line
with ETA and throughput — plus failures surfaced immediately, above the bar.

## Install

```bash
pip install pytest-tqdm
```

The plugin auto-registers via pytest's `pytest11` entry-point. Its only runtime
dependency is `tqdm`.

## Usage

By default the bar turns on **automatically** whenever standard error is an
interactive terminal (and you are on the xdist controller, not a worker). In
CI, when output is piped, or under an AI coding agent, standard error is not a
TTY, so the plugin stays completely silent — your existing reporter is
untouched.

```bash
pytest -n auto            # bar appears in your terminal, nothing changes in CI
```

### Options

| Flag | `pytest.ini` / env | Effect |
| --- | --- | --- |
| *(none)* | — | Auto-on in a TTY; failures print above the bar with a full traceback. |
| `--tqdm` | `PYTEST_TQDM=1` | Force the bar on even without a TTY. |
| `--no-tqdm` | `PYTEST_TQDM=0` | Force the bar off. |
| `--tqdm-names` | `tqdm_names` (ini) | Also stream every finished test name above the bar. |
| `--tqdm-tb=full\|line\|no` | `tqdm_tb` (ini) | Traceback verbosity above the bar for failures (default `full`). |

Resolution order for activation: `--tqdm` / `--no-tqdm` → `PYTEST_TQDM` →
TTY auto-detection.

### The bar

```
 42%|███████▉    | 512/1210 [00:37<00:48, 14.3test/s, ✓510 ✗2 s0 ▸ test_bar]
```

percentage · bar · done/total · elapsed<eta · throughput · live ✓/✗/skip tally ·
current test.

### The end-of-run line

When the session finishes the bar is replaced by a single totals line: number
of tests, wall time, tests/second, the pass/fail/skip tally, and how many xdist
workers ran (`serial` if you ran without `-n`).

## How it works

- **Controller-only.** `pytest-xdist` forwards every worker's
  `pytest_runtest_logreport` to the controller, so one reporter there sees all
  results and drives a single bar. Workers render nothing.
- **Summary preserved.** The plugin subclasses pytest's `TerminalReporter` and
  merely *mutes* its live per-test writes — all bookkeeping still runs, so the
  native end-of-run summary, `--durations`, the failures recap, etc. are
  untouched.
- **stderr.** The bar and above-bar text go to standard error; the normal
  reporter's summary goes to standard out, so they never fight.

## Compatibility

- Python 3.9+
- pytest 8 and 9
- Works with and without `pytest-xdist`; disables `pytest-sugar` while active
  (one bar only).

## License

MIT © Michał Pasternak
