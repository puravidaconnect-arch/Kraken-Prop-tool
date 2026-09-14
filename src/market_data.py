"""Kraken public data → OHLCV DataFrames + funding rate. Never fabricates:
any API problem raises MarketDataError and the caller must stop."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
KRAKEN_FUTURES_TICKERS_URL = "https://futures.kraken.com/derivatives/api/v3/tickers"
SPOT_PAIRS = {"BTC": "XBTUSD", "ETH": "ETHUSD"}
PERP_SYMBOLS = {"BTC": "PF_XBTUSD", "ETH": "PF_ETHUSD"}
INTERVALS = {"daily": 1440, "weekly": 10080}  # minutes, Kraken's own codes
COLUMNS = ["time", "open", "high", "low", "close", "vwap", "volume", "count"]
TIMEOUT = 20


class MarketDataError(RuntimeError):
    """Raised when market data cannot be fetched or is malformed."""


@dataclass
class MarketData:
    pair: str
    daily: pd.DataFrame
    weekly: pd.DataFrame
    funding: dict
    fetched_at: str


def _check_pair(pair: str) -> None:
    if pair not in SPOT_PAIRS:
        raise MarketDataError(f"unsupported pair {pair!r}: only {sorted(SPOT_PAIRS)}")


def parse_ohlc_response(payload: dict) -> pd.DataFrame:
    """Turn a Kraken OHLC JSON body into a typed DataFrame (pure, testable)."""
    if not isinstance(payload, dict):
        raise MarketDataError("OHLC response is not a JSON object")
    if payload.get("error"):
        raise MarketDataError(f"Kraken OHLC error: {payload['error']}")
    result = payload.get("result") or {}
    keys = [k for k in result if k != "last"]
    if len(keys) != 1 or not result[keys[0]]:
        raise MarketDataError("OHLC response contains no candle data")
    df = pd.DataFrame(result[keys[0]], columns=COLUMNS)
    df["time"] = pd.to_datetime(df["time"].astype(int), unit="s", utc=True)
    for col in ("open", "high", "low", "close", "vwap", "volume"):
        df[col] = df[col].astype(float)
    df["count"] = df["count"].astype(int)
    if df["time"].is_monotonic_increasing is False:
        df = df.sort_values("time")
    return df.reset_index(drop=True)


def drop_incomplete_last_bar(df: pd.DataFrame, timeframe: str, now: datetime | None = None) -> pd.DataFrame:
    """Kraken's final candle is the one still forming. Drop it so the analyst
    only sees completed closes."""
    now = now or datetime.now(timezone.utc)
    bar_seconds = INTERVALS[timeframe] * 60
    last_open = df["time"].iloc[-1].to_pydatetime()
    if (now - last_open).total_seconds() < bar_seconds:
        return df.iloc[:-1].reset_index(drop=True)
    return df


def fetch_ohlc(pair: str, timeframe: str, session: requests.Session | None = None,
               include_partial: bool = False) -> pd.DataFrame:
    """Daily or weekly OHLCV from Kraken spot (up to 720 candles)."""
    _check_pair(pair)
    if timeframe not in INTERVALS:
        raise MarketDataError(f"timeframe must be one of {sorted(INTERVALS)}")
    http = session or requests
    try:
        resp = http.get(KRAKEN_OHLC_URL, params={"pair": SPOT_PAIRS[pair], "interval": INTERVALS[timeframe]},
                        timeout=TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise MarketDataError(f"Kraken OHLC request failed for {pair} {timeframe}: {exc}") from exc
    df = parse_ohlc_response(payload)
    return df if include_partial else drop_incomplete_last_bar(df, timeframe)


def parse_funding(payload: dict, pair: str) -> dict:
    tickers = payload.get("tickers") if isinstance(payload, dict) else None
    if not tickers:
        raise MarketDataError("futures tickers response contains no tickers")
    symbol = PERP_SYMBOLS[pair]
    for t in tickers:
        if t.get("symbol") == symbol:
            if t.get("fundingRate") is None:
                raise MarketDataError(f"no fundingRate for {symbol}")
            return {
                "symbol": symbol,
                "funding_rate": float(t["fundingRate"]),
                "funding_rate_prediction": float(t["fundingRatePrediction"]) if t.get("fundingRatePrediction") is not None else None,
                "mark_price": float(t["markPrice"]) if t.get("markPrice") is not None else None,
            }
    raise MarketDataError(f"{symbol} not in futures tickers")


def fetch_funding_rate(pair: str, session: requests.Session | None = None) -> dict:
    """Current funding rate for the Kraken perpetual (PF_XBTUSD / PF_ETHUSD)."""
    _check_pair(pair)
    http = session or requests
    try:
        resp = http.get(KRAKEN_FUTURES_TICKERS_URL, timeout=TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise MarketDataError(f"Kraken futures tickers request failed: {exc}") from exc
    return parse_funding(payload, pair)


def get_market(pair: str, session: requests.Session | None = None) -> MarketData:
    """Everything the analyst and planner need for one pair, from live data."""
    _check_pair(pair)
    daily = fetch_ohlc(pair, "daily", session)
    time.sleep(0.5)  # be polite to the public rate limit
    weekly = fetch_ohlc(pair, "weekly", session)
    funding = fetch_funding_rate(pair, session)
    return MarketData(pair, daily, weekly, funding, datetime.now(timezone.utc).isoformat(timespec="seconds"))


def load_ohlc_csv(path: str | Path) -> pd.DataFrame:
    """OHLCV from a CSV with the same columns (evals/backtests only, never /plan)."""
    df = pd.read_csv(path)
    missing = {"time", "open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise MarketDataError(f"CSV {path} missing columns {sorted(missing)}")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.sort_values("time").reset_index(drop=True)


def save_ohlc_csv(df: pd.DataFrame, path: str | Path) -> None:
    df.to_csv(path, index=False)
