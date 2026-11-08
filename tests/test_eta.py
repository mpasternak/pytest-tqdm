import random

from pytest_tqdm.eta import EtaEstimator, format_eta, format_rate


def _fed(gaps):
    est = EtaEstimator(clock=lambda: 0.0)
    est.start(0.0)
    t = 0.0
    for g in gaps:
        t += g
        est.record(t)
    return est, t


def test_no_estimate_before_enough_data():
    est, t = _fed([0.1] * 3)
    assert est.estimate(100, now=t) is None
    assert format_eta(None, str) == "?"


def test_constant_pace_gives_exact_eta_and_no_spread():
    est, t = _fed([1.0] * 50)
    eta, half = est.estimate(100, now=t)
    assert eta == 50.0
    assert half == 0.0


def test_eta_uses_whole_history_not_recent_burst():
    # 90 slow tests (1 s), then 10 instant ones: a recent-rate ETA would say
    # "almost done"; the whole-run mean must still say ~1 s/test.
    est, t = _fed([1.0] * 90 + [0.001] * 10)
    eta, _ = est.estimate(200, now=t)
    assert 80 < eta < 100


def test_spread_grows_with_variability():
    rng = random.Random(0)
    steady, t1 = _fed([1.0 + rng.uniform(-0.05, 0.05) for _ in range(200)])
    bursty, t2 = _fed([rng.choice([0.1] * 9 + [9.0]) for _ in range(200)])
    _, half_steady = steady.estimate(400, now=t1)
    _, half_bursty = bursty.estimate(400, now=t2)
    assert half_bursty > 5 * half_steady


def test_stalled_test_pushes_eta_up():
    est, t = _fed([1.0] * 20)
    eta_now, _ = est.estimate(40, now=t)
    eta_later, _ = est.estimate(40, now=t + 20)
    assert eta_later > eta_now


def test_finished_run():
    est, t = _fed([1.0] * 10)
    assert est.estimate(10, now=t) == (0.0, 0.0)


def test_format():
    fmt = lambda s: f"{s:.0f}s"  # noqa: E731
    assert format_eta((60.0, None), fmt) == "~60s"
    assert format_eta((60.0, 0.4), fmt) == "~60s"
    assert format_eta((60.0, 12.0), fmt) == "~60s ±12s"
    assert format_rate(None) == "?test/s"
    assert format_rate(12.34) == "12.3test/s"
    assert format_rate(0.25) == "4.0s/test"
