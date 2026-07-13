"""The ``--tqdm-chart`` history panel: a sticky mini-TUI above the bar.

Two independent concerns live here:

* **Pure rendering** — ``sparkline_rows`` / ``dot_rows`` turn number series into
  block-character rows. No I/O, no state, fully unit-tested.
* **``LiveChart``** — a small ring-buffer + ``render()`` that composes the framed
  panel (throughput bars + failures lane) plus the caller's bar line.
* **``Region``** — owns the cursor: redraws a fixed-height block in place,
  scrolls arbitrary text above it, and tears it down cleanly.

The panel height is fixed for the whole run, so the redraw is a plain
"cursor up N, rewrite each line" with no grow/shrink bookkeeping.
"""

from __future__ import annotations

from collections import deque

# 9 fill levels, empty → full. Used for the vertical throughput bars.
_BLOCKS = " ▁▂▃▄▅▆▇█"
_DOT = "●"

_ANSI = {
    "green": "\033[32m",
    "red": "\033[31m",
    "dim": "\033[2m",
    "reset": "\033[0m",
}


def sparkline_rows(values, height, peak):
    """Render ``values`` as ``height`` rows of vertical bars (top row first),
    each column scaled to ``peak``. Level 0 is blank, ``peak`` fills all rows."""
    rows = [[] for _ in range(height)]
    steps = height * 8
    for value in values:
        if peak <= 0:
            level = 0
        else:
            level = max(0, min(steps, round(value / peak * steps)))
        for r in range(height):
            filled = level - (height - 1 - r) * 8  # sub-cells filled in this row
            if filled >= 8:
                rows[r].append("█")
            elif filled <= 0:
                rows[r].append(" ")
            else:
                rows[r].append(_BLOCKS[filled])
    return ["".join(row) for row in rows]


def dot_rows(counts, height):
    """Render per-tick failure ``counts`` as a scatter of dots (top row first):
    a tick with ``c`` failures gets one dot, higher for larger ``c``."""
    rows = [[] for _ in range(height)]
    for count in counts:
        target = height - 1 - min(max(count, 0) - 1, height - 1) if count > 0 else None
        for r in range(height):
            rows[r].append(_DOT if r == target else " ")
    return ["".join(row) for row in rows]


class LiveChart:
    """Ring buffer of throughput / failure samples + panel composition."""

    def __init__(self, height=5, fail_height=2, color=False, cap=4000):
        self._height = height
        self._fail_height = fail_height
        self._color = color
        self._rates = deque(maxlen=cap)
        self._fails = deque(maxlen=cap)
        self._peak = 0.0

    def add_sample(self, rate, fails):
        self._rates.append(max(0.0, rate))
        self._fails.append(max(0, fails))
        self._peak = max(self._peak, rate)

    def _paint(self, text, code):
        if not self._color:
            return text
        return _ANSI[code] + text + _ANSI["reset"]

    def render(self, width, bar_line):
        """Return the full block of lines (panel rows + ``bar_line`` last)."""
        gutter = 8  # right-aligned label + " │ "
        inner = max(10, width - gutter)
        rates = list(self._rates)[-inner:]
        fails = list(self._fails)[-inner:]
        if len(rates) < inner:  # right-align: pad the left with empties
            rates = [0.0] * (inner - len(rates)) + rates
            fails = [0] * (inner - len(fails)) + fails

        peak = self._peak
        spark = sparkline_rows(rates, self._height, peak)
        dots = dot_rows(fails, self._fail_height)

        lines = [self._paint(f" throughput  ·  peak {peak:.0f}/s", "dim")]
        for i, row in enumerate(spark):
            if i == 0:
                label = f"{peak:>5.0f}"
            elif i == len(spark) - 1:
                label = f"{0:>5}"
            else:
                label = " " * 5
            lines.append(f"{label} │ {self._paint(row, 'green')}")
        lines.append(self._paint(" failures", "dim"))
        for row in dots:
            lines.append(f"{'':>5} │ {self._paint(row, 'red')}")
        lines.append(bar_line)
        return lines


class Region:
    """A fixed-height, redraw-in-place block anchored to the bottom of the
    terminal. Everything else scrolls above it via :meth:`write_above`."""

    def __init__(self, file):
        self._file = file
        self._n = 0  # number of lines currently drawn

    def _goto_top(self):
        if self._n:
            self._file.write("\r")
            if self._n > 1:
                self._file.write(f"\033[{self._n - 1}A")

    def update(self, lines):
        self._goto_top()
        parts = []
        for i, line in enumerate(lines):
            parts.append("\033[2K")  # clear the whole line first
            parts.append(line)
            if i != len(lines) - 1:
                parts.append("\n")
        parts.append("\033[0J")  # clear any stale lines below (block shrank)
        self._file.write("".join(parts))
        self._file.flush()
        self._n = len(lines)

    def clear(self):
        self._goto_top()
        self._file.write("\033[0J")
        self._file.flush()
        self._n = 0

    def write_above(self, text):
        self.clear()
        self._file.write(text.rstrip("\n") + "\n")
        self._file.flush()

    def close(self, final_line=None):
        self.clear()
        if final_line is not None:
            self._file.write(final_line + "\n")
            self._file.flush()
