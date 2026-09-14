import numpy as np
import pandas as pd
import pytest

from src.indicators import (atr, count_higher, count_lower, declining_count, ema, range_bands,
                            range_contracting, rsi, slope_pct, swing_points, true_range)
from tests.synth import trend


def _df(highs, lows, closes=None):
    closes = closes or [(h + l) / 2 for h, l in zip(highs, lows)]
    return pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes})


def test_ema_matches_pandas_and_converges():
    s = pd.Series(np.full(100, 42.0))
    assert ema(s, 10).iloc[-1] == pytest.approx(42.0)
    s = pd.Series(np.linspace(1, 100, 100))
    assert ema(s, 20).iloc[-1] == pytest.approx(s.ewm(span=20, adjust=False).mean().iloc[-1])


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert rsi(up).iloc[-1] == pytest.approx(100.0)
    down = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert rsi(down).iloc[-1] == pytest.approx(0.0)
    mixed = rsi(trend()["close"])
    assert mixed.dropna().between(0, 100).all()


def test_atr_on_constant_range_equals_range():
    df = _df(highs=[110.0] * 50, lows=[100.0] * 50, closes=[105.0] * 50)
    assert true_range(df).iloc[-1] == 10
    assert atr(df).iloc[-1] == pytest.approx(10.0)


def test_slope_pct():
    s = pd.Series([100.0] * 10 + [110.0])
    assert slope_pct(s, 10) == pytest.approx(10.0)
    with pytest.raises(ValueError):
        slope_pct(pd.Series([1.0, 2.0]), 10)


def test_swing_points_zigzag_and_tie_resolution():
    highs = [10, 11, 12, 15, 12, 11, 10, 11, 12, 18, 12, 11, 10, 9, 8, 9, 10]
    lows = [h - 3 for h in highs]
    sh, sl = swing_points(_df(highs, lows), n=3)
    assert list(sh.index) == [3, 9] and list(sh.values) == [15, 18]
    assert list(sl.index) == [6] and list(sl.values) == [7]
    # a tie on the right side resolves to the earliest bar, not to nothing
    highs = [1, 2, 3, 9, 9, 3, 2, 1, 1, 1]
    sh, _ = swing_points(_df(highs, [h - 1 for h in highs]), n=3)
    assert list(sh.index) == [3]


def test_count_higher_lower():
    assert count_higher([1, 2, 3, 2, 4]) == 3
    assert count_lower([5, 4, 6, 3]) == 2
    assert count_higher([]) == 0


def test_range_bands_touch_counts():
    df = trend()
    b = range_bands(df, lookback=60)
    assert b["high"] == df["high"].iloc[-60:].max()
    assert b["low"] == df["low"].iloc[-60:].min()
    assert b["high_touches"] >= 0 and b["low_touches"] >= 0


def test_declining_count_and_range_contracting():
    assert declining_count(pd.Series(np.arange(20, 0, -1, dtype=float)), 10) == 10
    assert declining_count(pd.Series(np.arange(0, 20, dtype=float)), 10) == 0
    wide = _df(highs=[120.0] * 10, lows=[80.0] * 10)
    narrow = _df(highs=[105.0] * 10, lows=[95.0] * 10)
    assert range_contracting(pd.concat([wide, narrow], ignore_index=True), 10) is True
    assert range_contracting(pd.concat([narrow, wide], ignore_index=True), 10) is False
    assert range_contracting(narrow, 10) is False
