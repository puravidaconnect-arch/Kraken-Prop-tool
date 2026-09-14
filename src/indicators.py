"""Indicators as small pandas functions. All inputs are OHLCV DataFrames with
columns open, high, low, close (float) in chronological order."""
from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI. 100 when there are no losses in the window, 0 when no gains."""
    delta = close.diff()
    avg_gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    out = 100 - 100 / (1 + avg_gain / avg_loss)
    return out.where(avg_loss > 0, 100.0).where(avg_gain > 0, 0.0)


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder ATR."""
    return true_range(df).ewm(alpha=1 / period, adjust=False).mean()


def slope_pct(series: pd.Series, bars: int = 10) -> float:
    """Percent change of a series over the last ``bars`` bars."""
    if len(series) <= bars:
        raise ValueError(f"need more than {bars} bars, got {len(series)}")
    start, end = float(series.iloc[-1 - bars]), float(series.iloc[-1])
    return (end - start) / start * 100


def swing_points(df: pd.DataFrame, n: int = 3) -> tuple[pd.Series, pd.Series]:
    """Fractal swing highs/lows: a bar whose high (low) beats the ``n`` bars on
    each side. Ties resolve to the earliest bar. Returns (highs, lows) as price
    Series indexed by bar position. The last ``n`` bars can never be swings."""
    highs, lows = {}, {}
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    for i in range(n, len(df) - n):
        left_h, right_h = h[i - n : i], h[i + 1 : i + n + 1]
        left_l, right_l = l[i - n : i], l[i + 1 : i + n + 1]
        if h[i] > left_h.max() and h[i] >= right_h.max():
            highs[i] = float(h[i])
        if l[i] < left_l.min() and l[i] <= right_l.min():
            lows[i] = float(l[i])
    return pd.Series(highs, dtype=float), pd.Series(lows, dtype=float)


def count_higher(values) -> int:
    """How many consecutive-pair steps go up in a sequence (higher lows)."""
    vals = list(values)
    return sum(1 for a, b in zip(vals, vals[1:]) if b > a)


def count_lower(values) -> int:
    vals = list(values)
    return sum(1 for a, b in zip(vals, vals[1:]) if b < a)


def range_bands(df: pd.DataFrame, swing_n: int = 3, lookback: int = 60, tol_frac: float = 0.10) -> dict:
    """High/low band of the last ``lookback`` bars and how many swing points
    touched each band (within ``tol_frac`` of the range height)."""
    window = df.iloc[-lookback:]
    hi, lo = float(window["high"].max()), float(window["low"].min())
    height = hi - lo
    tol = height * tol_frac
    sh, sl = swing_points(window, swing_n)
    return {
        "high": hi,
        "low": lo,
        "height_pct": height / lo * 100 if lo else float("nan"),
        "high_touches": int((sh >= hi - tol).sum()),
        "low_touches": int((sl <= lo + tol).sum()),
    }


def declining_count(series: pd.Series, bars: int = 10) -> int:
    """Number of bar-to-bar declines in the last ``bars`` steps."""
    tail = series.iloc[-(bars + 1):]
    return int((tail.diff().dropna() < 0).sum())


def range_contracting(df: pd.DataFrame, bars: int = 10) -> bool:
    """Is the high-low span of the last ``bars`` smaller than the prior ``bars``?"""
    recent = df.iloc[-bars:]
    prior = df.iloc[-2 * bars : -bars]
    if len(prior) < bars:
        return False
    return bool((recent["high"].max() - recent["low"].min()) < (prior["high"].max() - prior["low"].min()))
