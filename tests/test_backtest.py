import pandas as pd
import pytest

from src.backtest import compare, improved, run, simulate, to_weekly, Result
from tests.synth import ranging, trend


def _bars(rows):
    return pd.DataFrame([{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in rows])


def test_simulate_long_paths():
    zone, stop, target = [99, 101], 95, 113  # risk 6, reward 12 from worst 101
    assert simulate(_bars([(105, 106, 104, 105)] * 6), "long", zone, stop, target)[0] == "unfilled"
    out, f, e, r = simulate(_bars([(105, 106, 100, 102), (102, 114, 101, 113)]), "long", zone, stop, target)
    assert (out, f, e, r) == ("target_hit", 0, 1, 2.0)
    out, f, e, r = simulate(_bars([(105, 106, 100, 102), (102, 114, 94, 100)]), "long", zone, stop, target)
    assert (out, r) == ("stop_hit", -1.0)  # both touched in one bar → stop first
    out, f, e, r = simulate(_bars([(105, 106, 100, 102)] + [(102, 104, 100, 104)] * 40), "long", zone, stop, target, max_hold=10)
    assert out == "timed_out" and r == pytest.approx(0.5)


def test_simulate_short():
    out, f, e, r = simulate(_bars([(95, 100, 94, 96), (96, 97, 86, 89)]), "short", [99, 101], 105, 87)
    assert out == "target_hit" and r == pytest.approx(12 / 6)


def test_to_weekly():
    w = to_weekly(trend(n=70))
    assert 9 <= len(w) <= 11 and set(w.columns) == {"time", "open", "high", "low", "close"}


def test_run_requires_two_years():
    with pytest.raises(ValueError, match="2 years"):
        run(trend(n=400))


def test_run_and_compare_on_synthetic_history():
    df = pd.concat([trend(n=400, seed=7), ranging(n=200, lo=130000, hi=145000).assign(time=lambda d: d.time + pd.Timedelta(days=400)),
                    trend(n=200, drift=-0.004, seed=9, start_price=140000).assign(time=lambda d: d.time + pd.Timedelta(days=600))],
                   ignore_index=True)
    r = run(df, step=2)
    assert r.n_signals > 5 and r.n_filled > 0 and isinstance(r.expectancy_r, float)
    assert all(t.outcome in ("target_hit", "stop_hit", "unfilled", "timed_out") for t in r.trades)
    c = compare(df, {"min_stop_atr": 3.0})
    assert set(c) == {"baseline", "candidate", "overrides", "improved", "why"}
    assert c["candidate"] != c["baseline"]  # the override changed the stops
    with pytest.raises(ValueError, match="unknown parameters"):
        compare(df, {"magic": 1})


def test_improved_rules():
    base = Result(20, 15, 8, 7, 0.4, 0.53, 3.0, 6.0)
    assert improved(base, Result(20, 15, 9, 6, 0.6, 0.6, 3.0, 9.0))[0]
    assert not improved(base, Result(20, 5, 5, 0, 2.0, 1.0, 0.0, 10.0))[0]      # too few trades
    assert not improved(base, Result(20, 15, 8, 7, 0.4, 0.53, 3.0, 6.0))[0]     # no gain
    assert not improved(base, Result(20, 15, 9, 6, 0.6, 0.6, 5.0, 9.0))[0]      # worse drawdown
