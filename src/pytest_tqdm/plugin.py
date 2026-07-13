"""pytest-tqdm — one aggregated tqdm progress bar for the whole session.

Design notes:

* **Controller-only.** Under ``pytest-xdist`` every worker's
  ``pytest_runtest_logreport`` is forwarded to the controller, so a single
  reporter living on the controller sees every result and drives one bar.
  Workers themselves are a no-op (they have ``config.workerinput``).
* **Interactive-only by default.** ``resolve_mode`` is the single activation
  decision point (and the seam where a future "agent mode" would slot in).
* **Summary preserved.** We subclass ``TerminalReporter`` and only *mute* its
  live per-test writes — all its bookkeeping still runs, so the native
  end-of-run summary, ``--durations`` etc. are untouched.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from enum import Enum

import pytest
from _pytest.terminal import TerminalReporter


class Mode(Enum):
    OFF = "off"
    BAR = "bar"


# tqdm hardcodes a ", " before {postfix}, so we keep the tally inside the
# brackets where that comma reads as a natural separator.
BAR_FORMAT = (
    "{percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} "
    "[{elapsed}<{remaining}, {rate_fmt}{postfix}]"
)


def pytest_addoption(parser):
    group = parser.getgroup("tqdm", "single tqdm progress bar")
    group.addoption(
        "--tqdm",
        dest="tqdm_force",
        action="store_true",
        default=None,
        help="Force the single tqdm progress bar on (even without a TTY).",
    )
    group.addoption(
        "--no-tqdm",
        dest="tqdm_force",
        action="store_false",
        help="Force the single tqdm progress bar off.",
    )
    group.addoption(
        "--tqdm-names",
        dest="tqdm_names",
        action="store_true",
        default=None,
        help="Also stream each finished test name above the bar.",
    )
    group.addoption(
        "--tqdm-tb",
        dest="tqdm_tb",
        choices=("full", "line", "no"),
        default=None,
        help="Traceback verbosity printed above the bar for failures (default: full).",
    )
    group.addoption(
        "--tqdm-color",
        dest="tqdm_color",
        choices=("auto", "always", "never"),
        default=None,
        help="Colorize the bar: auto (TTY only, default), always, or never. "
        "NO_COLOR is always respected.",
    )
    group.addoption(
        "--tqdm-no-face",
        dest="tqdm_face",
        action="store_false",
        default=None,
        help="Hide the Doom-style health face on the bar.",
    )
    group.addoption(
        "--tqdm-interval",
        dest="tqdm_interval",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Minimum seconds between bar redraws (default: 0.4).",
    )
    parser.addini(
        "tqdm_names",
        "Stream finished test names above the bar",
        type="bool",
        default=False,
    )
    parser.addini(
        "tqdm_tb",
        "Traceback verbosity above the bar (full|line|no)",
        default="full",
    )
    parser.addini(
        "tqdm_color",
        "Colorize the bar (auto|always|never)",
        default="auto",
    )
    parser.addini(
        "tqdm_face",
        "Show a Doom-style health face on the bar",
        type="bool",
        default=True,
    )
    parser.addini(
        "tqdm_interval",
        "Minimum seconds between bar redraws (default 0.4)",
        default="0.4",
    )


# Doom-guy-ish health faces, best → worst by failure ratio. The more tests
# fail, the more the face suffers. All green = insufferably smug.
_FACES = [
    (0.02, "🙂"),
    (0.10, "😐"),
    (0.25, "😟"),
    (0.50, "😰"),
    (0.90, "🤕"),
    (1.01, "💀"),
]


# ANSI SGR codes; only ever emitted when colour is enabled (TTY + not NO_COLOR).
_ANSI = {
    "green": "\033[32m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "reset": "\033[0m",
}


def _env_bool(name):
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() in ("1", "true", "yes", "on")


def resolve_mode(config) -> Mode:
    """The single activation decision (seam for a future ``AGENT`` mode)."""
    if hasattr(config, "workerinput"):
        return Mode.OFF  # xdist worker: never renders
    forced = config.getoption("tqdm_force", None)
    if forced is True:
        return Mode.BAR
    if forced is False:
        return Mode.OFF
    env = _env_bool("PYTEST_TQDM")
    if env is not None:
        return Mode.BAR if env else Mode.OFF
    # auto: only when the stream the bar writes to is interactive
    return Mode.BAR if sys.stderr.isatty() else Mode.OFF


def _resolve_names(config):
    val = config.getoption("tqdm_names", None)
    if val is None:
        val = config.getini("tqdm_names")
    return bool(val)


def _resolve_tb(config):
    val = config.getoption("tqdm_tb", None)
    if val is None:
        val = config.getini("tqdm_tb") or "full"
    return val


def _resolve_color(config):
    mode = config.getoption("tqdm_color", None) or config.getini("tqdm_color") or "auto"
    if mode == "never":
        return False
    if "NO_COLOR" in os.environ:  # https://no-color.org — always wins
        return False
    if mode == "always":
        return True
    return sys.stderr.isatty()


def _resolve_face(config):
    val = config.getoption("tqdm_face", None)
    if val is None:
        val = config.getini("tqdm_face")
    return bool(val)


def _resolve_interval(config):
    val = config.getoption("tqdm_interval", None)
    if val is None:
        try:
            val = float(config.getini("tqdm_interval"))
        except (TypeError, ValueError):
            val = 0.4
    return max(0.0, float(val))


@contextmanager
def _muted(writer):
    """Swallow a ``TerminalWriter``'s output, keeping its attributes intact."""
    saved = (writer.write, writer.line, writer.flush, writer.sep)

    def _noop(*args, **kwargs):
        return None

    writer.write = writer.line = writer.flush = writer.sep = _noop
    try:
        yield
    finally:
        writer.write, writer.line, writer.flush, writer.sep = saved


class TqdmTerminalReporter(TerminalReporter):
    def __init__(
        self, config, names=False, tb="full", color=False, face=True, interval=0.4
    ):
        super().__init__(config)
        self._names = names
        self._tb = tb
        self._color = color
        self._show_face = face
        self._interval = interval
        self._bar = None
        self._total = None
        self._seen = set()
        self._passed = 0
        self._failed = 0
        self._skipped = 0
        self._workers = set()

    # -- suppress live per-test output, but keep the bookkeeping intact --------
    def pytest_runtest_logstart(self, nodeid, location):
        with _muted(self._tw):
            super().pytest_runtest_logstart(nodeid, location)

    def pytest_runtest_logreport(self, report):
        with _muted(self._tw):
            super().pytest_runtest_logreport(report)
        self._on_report(report)

    # -- bar lifecycle ---------------------------------------------------------
    def set_total(self, total):
        self._total = total
        if self._bar is not None:
            self._bar.total = total
            self._bar.refresh()

    def _ensure_bar(self):
        if self._bar is None:
            from tqdm import tqdm

            self._bar = tqdm(
                total=self._total,
                dynamic_ncols=True,
                leave=False,
                disable=False,
                mininterval=self._interval,  # min seconds between redraws
                bar_format=BAR_FORMAT,
                colour=self._state_colour(),
                file=sys.stderr,
            )
        return self._bar

    def _paint(self, text, *codes):
        if not self._color or not codes:
            return text
        return "".join(_ANSI[c] for c in codes) + text + _ANSI["reset"]

    def _state_colour(self):
        """Bar colour name for tqdm: red on any failure, else green (yellow if
        only skips so far). Returns ``None`` when colour is disabled."""
        if not self._color:
            return None
        if self._failed:
            return "red"
        if self._passed == 0 and self._skipped:
            return "yellow"
        return "green"

    def _face(self):
        """Doom-guy-ish health face by failure ratio (best → worst)."""
        if self._failed == 0:
            return "😎"
        done = self._passed + self._failed + self._skipped
        ratio = self._failed / done if done else 1.0
        for threshold, glyph in _FACES:
            if ratio < threshold:
                return glyph
        return "💀"

    def _postfix(self):
        passed = self._paint(f"✓{self._passed}", "green")
        if self._failed:
            failed = self._paint(f"✗{self._failed}", "bold", "red")
        else:
            failed = self._paint("✗0", "dim")
        if self._skipped:
            skipped = self._paint(f"s{self._skipped}", "yellow")
        else:
            skipped = self._paint("s0", "dim")
        tally = f"{passed} {failed} {skipped}"
        return f"{self._face()}  {tally}" if self._show_face else tally

    def close_bar(self):
        if self._bar is None:
            return
        elapsed = self._bar.format_dict.get("elapsed", 0.0)
        self._bar.refresh()  # force the final frame into the stream
        self._bar.close()
        self._bar = None
        self._write_totals(elapsed)

    def _write_totals(self, elapsed):
        from tqdm import tqdm

        n = self._passed + self._failed + self._skipped
        rate = n / elapsed if elapsed else 0.0
        workers = len(self._workers)
        worker_str = f"{workers} workers" if workers else "serial"
        parts = [
            f"{n} tests in {tqdm.format_interval(elapsed)}",
            f"{rate:.1f} tests/s",
            f"✓{self._passed} ✗{self._failed} s{self._skipped}",
            worker_str,
        ]
        line = "pytest-tqdm ▸ " + "  ·  ".join(parts)
        face = f"{self._face()}  " if self._show_face else ""
        colour = "red" if self._failed else "green"
        self._write(face + self._paint(line, "bold", colour))

    # -- per-report handling ---------------------------------------------------
    def _on_report(self, report):
        # Track distinct xdist workers (reports carry .node on the controller).
        node = getattr(report, "node", None)
        if node is not None:
            self._workers.add(node.gateway.id)
        # pytest-rerunfailures marks intermediate attempts with outcome "rerun".
        if getattr(report, "outcome", None) == "rerun":
            return
        outcome = self._final_outcome(report)
        if outcome is None:
            # A teardown error on an already-counted test: surface it, no advance.
            if report.when == "teardown" and report.failed:
                self._write_failure(report)
            return
        nodeid = report.nodeid
        if nodeid in self._seen:
            return
        self._seen.add(nodeid)

        if outcome == "failed":
            self._failed += 1
            self._write_failure(report)
        elif outcome == "skipped":
            self._skipped += 1
        else:
            self._passed += 1
        if self._names:
            self._write_name(report, outcome)

        bar = self._ensure_bar()
        if self._color:
            bar.colour = self._state_colour()
        bar.set_postfix_str(self._postfix(), refresh=False)
        bar.update(1)

    @staticmethod
    def _final_outcome(report):
        """The test's final outcome, or ``None`` if this report is not final."""
        if report.when == "call":
            if report.failed:
                return "failed"
            if report.skipped:
                return "skipped"
            return "passed"
        if report.when == "setup":
            if report.failed:
                return "failed"  # error during setup/fixture
            if report.skipped:
                return "skipped"  # skip marker / skipped fixture
        return None

    # -- above-bar writes ------------------------------------------------------
    def _write(self, text):
        from tqdm import tqdm

        tqdm.write(text, file=sys.stderr)

    def _write_failure(self, report):
        if self._tb == "no":
            return
        if self._tb == "line":
            self._write(self._paint(f"FAILED {report.nodeid}", "bold", "red"))
            return
        self._write(self._paint(f"── FAILED {report.nodeid} ──", "bold", "red"))
        text = report.longreprtext
        if text:
            self._write(text)

    def _write_name(self, report, outcome):
        label = {"passed": "PASSED", "failed": "FAILED", "skipped": "SKIPPED"}
        self._write(f"{label[outcome]} {report.nodeid}")


class _TqdmHelper:
    """Companion plugin: feeds the collection total to the reporter and closes
    the bar during ``pytest_sessionfinish`` — i.e. *before* the reporter's
    wrapper prints the end-of-run summary (which runs after its ``yield``)."""

    def __init__(self, reporter):
        self._reporter = reporter

    def pytest_collection_finish(self, session):
        # Serial runs (and some xdist versions) populate the controller's items.
        if session.items:
            self._reporter.set_total(len(session.items))

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(self, node, ids):
        # xdist controller: every worker collects the same set, so ``ids`` is
        # the full test list. This is where the total actually comes from under
        # xdist, because ``session.items`` on the controller is often empty.
        if ids:
            self._reporter.set_total(len(ids))

    def pytest_sessionfinish(self, session, exitstatus):
        self._reporter.close_bar()


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    if resolve_mode(config) is Mode.OFF:
        return
    if config.pluginmanager.getplugin("terminalreporter") is None:
        return
    # Drop pytest-sugar and the standard reporter — one bar only.
    for name in ("sugar", "terminalreporter"):
        plugin = config.pluginmanager.getplugin(name)
        if plugin is not None:
            config.pluginmanager.unregister(plugin)
    reporter = TqdmTerminalReporter(
        config,
        names=_resolve_names(config),
        tb=_resolve_tb(config),
        color=_resolve_color(config),
        face=_resolve_face(config),
        interval=_resolve_interval(config),
    )
    config.pluginmanager.register(reporter, "terminalreporter")
    config.pluginmanager.register(_TqdmHelper(reporter), "tqdm-helper")
