"""Synthetic OHLCV series for tests only. Never used for trading."""
import numpy as np
import pandas as pd


def _frame(close: np.ndarray, wick_pct: float, start="2024-01-01") -> pd.DataFrame:
    n = len(close)
    opn = np.concatenate([[close[0]], close[:-1]])
    hi = np.maximum(opn, close) * (1 + wick_pct)
    lo = np.minimum(opn, close) * (1 - wick_pct)
    return pd.DataFrame({
        "time": pd.date_range(start, periods=n, freq="D", tz="UTC"),
        "open": opn, "high": hi, "low": lo, "close": close,
        "vwap": close, "volume": np.full(n, 100.0), "count": np.full(n, 1000),
    })


def trend(n=300, drift=0.004, vol=0.015, seed=1, start_price=50000.0, swing_period=12, swing_amp=0.03):
    """Drifting random walk with a regular swing so fractal lows step higher."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    noise = rng.normal(0, vol, n).cumsum()
    swing = swing_amp * np.sin(2 * np.pi * t / swing_period)
    close = start_price * np.exp(drift * t + noise * 0.3 + swing)
    return _frame(close, 0.004)


def ranging(n=300, lo=42000.0, hi=46000.0, period=24, seed=2):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    mid, amp = (hi + lo) / 2, (hi - lo) / 2
    close = mid + amp * np.sin(2 * np.pi * t / period) + rng.normal(0, amp * 0.02, n)
    return _frame(close, 0.003)


def coiling(n=300, mid=45000.0, seed=3):
    """Range that contracts: oscillation amplitude decays over the last 60 bars."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    amp = np.where(t < n - 60, 0.10, 0.10 * np.exp(-(t - (n - 60)) / 15))
    close = mid * (1 + amp * np.sin(2 * np.pi * t / 8)) + rng.normal(0, 20, n)
    wick = np.where(t < n - 60, 0.004, 0.004 * np.exp(-(t - (n - 60)) / 15)) + 0.0002
    df = _frame(close, 0.0)
    df["high"] = np.maximum(df["open"], df["close"]) * (1 + wick)
    df["low"] = np.minimum(df["open"], df["close"]) * (1 - wick)
    return df
