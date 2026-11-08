"""Whole-run ETA estimator.

tqdm's own ``remaining`` comes from an exponential moving average of the
*recent* rate, so it jumps around every time a slow (or fast) cluster of tests
goes by. Test suites are bursty — a module of DB tests, then a module of pure
unit tests — so a short window is a poor predictor of the rest of the run.

``EtaEstimator`` instead uses **every completion since the start**:

* **centre** — mean seconds-per-test over the whole run so far
  (``elapsed / done``), times the number of tests left. ``elapsed`` is measured
  up to *now*, so a long-running test still pushes the estimate up.
* **spread** — the completions are cut into ``k`` consecutive batches of equal
  size ``b`` and we look at how much the per-test time varies *between
  batches* (the "batch means" method). Batching keeps the correlation between
  neighbouring tests (slow modules come in clumps) instead of pretending each
  test is independent, which would make the band unrealistically narrow.

  For ``N`` remaining tests the variance of the remaining time is approximated
  as ``N·b·σ²`` (the future batches will vary like the past ones did) plus
  ``N²·σ²/k`` (we don't know the true mean exactly either), where ``σ²`` is the
  variance of the per-test time across batches.

Everything is O(1) per completion except :meth:`estimate`, which is O(k).
"""

from __future__ import annotations

import math
import time

# Don't pretend to know anything before this much evidence.
MIN_DONE = 5
MIN_ELAPSED = 0.5
# Batches used for the spread estimate.
MAX_BATCHES = 30
MIN_BATCHES = 3
# Band width in standard deviations (~80 % central interval).
Z = 1.28


class EtaEstimator:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._t0 = None
        self._times = []  # completion times, seconds since t0

    def start(self, now=None):
        """Start the clock (idempotent). Called on the first sign of life."""
        if self._t0 is None:
            self._t0 = self._clock() if now is None else now

    @property
    def started(self):
        return self._t0 is not None

    def elapsed(self, now=None):
        if self._t0 is None:
            return 0.0
        now = self._clock() if now is None else now
        return max(0.0, now - self._t0)

    def record(self, now=None):
        """Register one finished test."""
        now = self._clock() if now is None else now
        self.start(now)
        self._times.append(max(0.0, now - self._t0))

    @property
    def done(self):
        return len(self._times)

    def rate(self, now=None):
        """Average tests/s since the start, or ``None`` if not enough data."""
        elapsed = self.elapsed(now)
        if not self._times or elapsed <= 0:
            return None
        return len(self._times) / elapsed

    def estimate(self, total, now=None):
        """Return ``(eta_seconds, half_width_seconds)`` or ``None``.

        ``half_width`` is ``None`` while there are too few batches to say
        anything about the spread.
        """
        n = len(self._times)
        elapsed = self.elapsed(now)
        if not total or n < MIN_DONE or elapsed < MIN_ELAPSED:
            return None
        remaining = max(0, total - n)
        if remaining == 0:
            return 0.0, 0.0
        per_test = elapsed / n
        eta = remaining * per_test

        k = min(MAX_BATCHES, n // MIN_DONE)
        if k < MIN_BATCHES:
            return eta, None
        b = n // k
        prev = 0.0
        means = []
        for j in range(1, k + 1):
            t = self._times[j * b - 1]
            means.append((t - prev) / b)
            prev = t
        mu = sum(means) / k
        var = sum((m - mu) ** 2 for m in means) / (k - 1)
        sd = math.sqrt(remaining * b * var + remaining * remaining * var / k)
        return eta, Z * sd


def format_eta(estimate, fmt):
    """Render an :meth:`EtaEstimator.estimate` result with ``fmt`` (seconds →
    str, e.g. ``tqdm.format_interval``)."""
    if estimate is None:
        return "?"
    eta, half = estimate
    if half is None or eta <= 0:
        return f"~{fmt(eta)}"
    # A band narrower than a second is noise; don't clutter the bar with it.
    if half < 1:
        return f"~{fmt(eta)}"
    return f"~{fmt(eta)} ±{fmt(half)}"


def format_rate(rate):
    if rate is None:
        return "?test/s"
    if rate >= 1 or rate == 0:
        return f"{rate:.1f}test/s"
    return f"{1 / rate:.1f}s/test"
