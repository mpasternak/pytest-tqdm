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


def test_summary_still_printed(pytester):
    # The native end-of-run summary must survive the reporter swap.
    pytester.makepyfile(BOOM)
    result = pytester.runpytest_subprocess("--tqdm")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*short test summary*"])
