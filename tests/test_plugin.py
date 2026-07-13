"""Behavioural tests for pytest-tqdm.

Every test runs a real pytest subprocess (via the ``pytester`` fixture) with
the plugin auto-loaded through its ``pytest11`` entry-point, and asserts on the
captured **stderr** — the stream the tqdm bar and above-bar output are written
to. ``--tqdm`` forces the bar on regardless of the (non-TTY) subprocess.
"""

PASS3 = """
def test_a(): assert True
def test_b(): assert True
def test_c(): assert True
"""

BOOM = """
def test_boom():
    assert 1 == 2
"""

RECORD_REPORTER_CONFTEST = """
def pytest_unconfigure(config):
    tr = config.pluginmanager.getplugin("terminalreporter")
    (config.rootpath / "reporter.txt").write_text(type(tr).__name__)
"""


def test_bar_appears_when_forced(pytester):
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess("--tqdm")
    err = result.stderr.str()
    assert "✓3 ✗0 s0" in err
    assert "3/3" in err


def test_no_bar_with_no_tqdm(pytester):
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess("--no-tqdm")
    err = result.stderr.str()
    assert "✓" not in err
    result.assert_outcomes(passed=3)


def test_no_bar_when_not_tty_by_default(pytester):
    # A subprocess is never a TTY, so the default (auto) mode stays OFF.
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess()
    err = result.stderr.str()
    assert "✓" not in err
    result.assert_outcomes(passed=3)


def test_env_var_forces_on(pytester, monkeypatch):
    # The subprocess inherits the parent env, so PYTEST_TQDM propagates.
    monkeypatch.setenv("PYTEST_TQDM", "1")
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess()
    err = result.stderr.str()
    assert "✓3 ✗0 s0" in err


def test_failure_full_traceback_above_bar(pytester):
    pytester.makepyfile(BOOM)
    result = pytester.runpytest_subprocess("--tqdm")
    err = result.stderr.str()
    assert "── FAILED" in err
    assert "test_boom" in err
    assert "assert 1 == 2" in err
    assert "✗1" in err


def test_failure_tb_line(pytester):
    pytester.makepyfile(BOOM)
    result = pytester.runpytest_subprocess("--tqdm", "--tqdm-tb=line")
    err = result.stderr.str()
    assert "FAILED" in err
    assert "test_boom" in err
    assert "── FAILED" not in err
    assert "assert 1 == 2" not in err


def test_failure_tb_no(pytester):
    pytester.makepyfile(BOOM)
    result = pytester.runpytest_subprocess("--tqdm", "--tqdm-tb=no")
    err = result.stderr.str()
    assert "✗1" in err
    assert "FAILED" not in err
    assert "assert 1 == 2" not in err


def test_names_streamed_with_flag(pytester):
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess("--tqdm", "--tqdm-names")
    err = result.stderr.str()
    assert err.count("PASSED") == 3


def test_names_not_streamed_by_default(pytester):
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess("--tqdm")
    err = result.stderr.str()
    assert "PASSED" not in err


def test_skips_counted_separately(pytester):
    pytester.makepyfile(
        """
        import pytest
        def test_ok(): assert True
        @pytest.mark.skip(reason="nope")
        def test_sk(): assert True
        """
    )
    result = pytester.runpytest_subprocess("--tqdm")
    err = result.stderr.str()
    assert "✓1 ✗0 s1" in err


def test_total_taken_from_collection(pytester):
    pytester.makepyfile(
        """
        def test_1(): pass
        def test_2(): pass
        def test_3(): pass
        def test_4(): pass
        def test_5(): pass
        """
    )
    result = pytester.runpytest_subprocess("--tqdm")
    err = result.stderr.str()
    assert "/5" in err


def test_bar_total_known_under_xdist(pytester):
    # Regression: under xdist the controller's session.items can be empty, so
    # the total must come from pytest_xdist_node_collection_finished instead.
    pytester.makepyfile("\n".join(f"def test_{i}(): pass" for i in range(8)))
    result = pytester.runpytest_subprocess("--tqdm", "-n2")
    err = result.stderr.str()
    assert "/8" in err
    assert "/?" not in err


def test_postfix_has_no_test_name(pytester):
    # The current-test name is intentionally NOT in the bar (it churns the line).
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess("--tqdm")
    err = result.stderr.str()
    assert "✓3 ✗0 s0]" in err  # tally sits right before the closing bracket
    assert "▸ test_" not in err  # no current-test name pushed into the bar


def test_xdist_aggregates_into_single_bar(pytester):
    pytester.makepyfile(
        """
        def test_1(): pass
        def test_2(): pass
        def test_3(): pass
        def test_4(): pass
        """
    )
    result = pytester.runpytest_subprocess("--tqdm", "-n2")
    err = result.stderr.str()
    assert "✓4 ✗0 s0" in err


def test_replaces_terminalreporter_when_active(pytester):
    pytester.makepyfile(PASS3)
    pytester.makeconftest(RECORD_REPORTER_CONFTEST)
    pytester.runpytest_subprocess("--tqdm")
    assert (pytester.path / "reporter.txt").read_text() == "TqdmTerminalReporter"


def test_keeps_standard_reporter_when_off(pytester):
    pytester.makepyfile(PASS3)
    pytester.makeconftest(RECORD_REPORTER_CONFTEST)
    pytester.runpytest_subprocess("--no-tqdm")
    assert (pytester.path / "reporter.txt").read_text() != "TqdmTerminalReporter"


def test_rerun_advances_bar_once(pytester):
    pytester.makepyfile(BOOM)
    # 2 reruns => 3 attempts total; the bar must count the test once.
    result = pytester.runpytest_subprocess("--tqdm", "--reruns", "2")
    err = result.stderr.str()
    assert "✗1" in err
    assert "✗3" not in err
    assert "/1" in err


def test_totals_line_at_end(pytester):
    pytester.makepyfile(
        """
        def test_1(): pass
        def test_2(): pass
        def test_3(): assert 1 == 2
        """
    )
    result = pytester.runpytest_subprocess("--tqdm")
    err = result.stderr.str()
    assert "pytest-tqdm ▸" in err
    assert "3 tests in" in err
    assert "tests/s" in err
    assert "✓2 ✗1 s0" in err
    assert "serial" in err


def test_totals_line_reports_worker_count(pytester):
    pytester.makepyfile(
        """
        def test_1(): pass
        def test_2(): pass
        def test_3(): pass
        def test_4(): pass
        def test_5(): pass
        def test_6(): pass
        def test_7(): pass
        def test_8(): pass
        """
    )
    result = pytester.runpytest_subprocess("--tqdm", "-n2")
    err = result.stderr.str()
    assert "pytest-tqdm ▸" in err
    assert "8 tests in" in err
    assert "2 workers" in err


GREEN = "\x1b[32m"
RED = "\x1b[31m"


def test_color_always_emits_ansi(pytester):
    pytester.makepyfile(BOOM)
    result = pytester.runpytest_subprocess("--tqdm", "--tqdm-color=always")
    err = result.stderr.str()
    assert RED in err  # our painted ✗ / failure header


def test_color_never_no_ansi(pytester):
    pytester.makepyfile(BOOM)
    result = pytester.runpytest_subprocess("--tqdm", "--tqdm-color=never")
    err = result.stderr.str()
    assert GREEN not in err
    assert RED not in err


def test_color_auto_off_when_not_tty(pytester):
    # Default (auto) + non-TTY subprocess => no colour even with the bar forced.
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess("--tqdm")
    err = result.stderr.str()
    assert GREEN not in err
    assert RED not in err


def test_no_color_env_beats_always(pytester, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess("--tqdm", "--tqdm-color=always")
    err = result.stderr.str()
    assert GREEN not in err
    assert RED not in err


def test_bar_green_when_all_pass(pytester):
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess("--tqdm", "--tqdm-color=always")
    err = result.stderr.str()
    assert GREEN in err


def test_face_smug_when_all_pass(pytester):
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess("--tqdm")
    err = result.stderr.str()
    assert "😎" in err


def test_face_skull_when_all_fail(pytester):
    pytester.makepyfile(
        """
        def test_a(): assert 0
        def test_b(): assert 0
        """
    )
    result = pytester.runpytest_subprocess("--tqdm")
    err = result.stderr.str()
    assert "💀" in err


def test_face_hidden_with_no_face(pytester):
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess("--tqdm", "--tqdm-no-face")
    err = result.stderr.str()
    assert "😎" not in err
    assert "✓3 ✗0 s0" in err


def test_interval_option_accepted(pytester):
    pytester.makepyfile(PASS3)
    result = pytester.runpytest_subprocess("--tqdm", "--tqdm-interval=0.1")
    err = result.stderr.str()
    assert "✓3 ✗0 s0" in err


def test_summary_still_printed(pytester):
    # The native end-of-run summary must survive the reporter swap.
    pytester.makepyfile(BOOM)
    result = pytester.runpytest_subprocess("--tqdm")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*short test summary*"])
