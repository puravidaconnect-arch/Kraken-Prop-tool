from datetime import datetime, timedelta, timezone

import pytest
import requests

from src.market_data import (MarketDataError, drop_incomplete_last_bar, fetch_funding_rate,
                             fetch_ohlc, get_market, load_ohlc_csv, parse_funding,
                             parse_ohlc_response, save_ohlc_csv)


def kraken_ohlc_payload(n=3, start=1_700_000_000, step=86400):
    rows = [[start + i * step, "100", "110", "90", "105", "102", "12.5", 300] for i in range(n)]
    return {"error": [], "result": {"XXBTZUSD": rows, "last": start + (n - 1) * step}}


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, ohlc=None, tickers=None, status=200, raise_exc=None):
        self.ohlc, self.tickers, self.status, self.raise_exc, self.calls = ohlc, tickers, status, raise_exc, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if self.raise_exc:
            raise self.raise_exc
        return FakeResp(self.tickers if "futures" in url else self.ohlc, self.status)


def test_parse_ohlc_response_types_and_order():
    df = parse_ohlc_response(kraken_ohlc_payload(3))
    assert list(df.columns) == ["time", "open", "high", "low", "close", "vwap", "volume", "count"]
    assert df["close"].dtype == float and df["count"].dtype == int
    assert str(df["time"].dt.tz) == "UTC" and df["time"].is_monotonic_increasing


@pytest.mark.parametrize("payload", [
    {"error": ["EQuery:Unknown asset pair"], "result": {}},
    {"error": [], "result": {"last": 1}},
    {"error": [], "result": {"XXBTZUSD": [], "last": 1}},
    "not json object",
])
def test_parse_ohlc_rejects_bad_payloads(payload):
    with pytest.raises(MarketDataError):
        parse_ohlc_response(payload)


def test_drop_incomplete_last_bar():
    now = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
    start = int((now - timedelta(days=2)).timestamp())  # bars at now-2d, now-1d, now (forming)
    df = parse_ohlc_response(kraken_ohlc_payload(3, start=start))
    assert len(drop_incomplete_last_bar(df, "daily", now)) == 2
    old = parse_ohlc_response(kraken_ohlc_payload(3, start=start - 10 * 86400))
    assert len(drop_incomplete_last_bar(old, "daily", now)) == 3


def test_fetch_ohlc_uses_kraken_codes_and_never_fabricates():
    s = FakeSession(ohlc=kraken_ohlc_payload(5, start=1_600_000_000))
    df = fetch_ohlc("BTC", "weekly", s)
    assert s.calls[0][1] == {"pair": "XBTUSD", "interval": 10080}
    assert len(df) == 5
    with pytest.raises(MarketDataError):
        fetch_ohlc("SOL", "daily", s)
    with pytest.raises(MarketDataError):
        fetch_ohlc("BTC", "hourly", s)
    with pytest.raises(MarketDataError, match="request failed"):
        fetch_ohlc("BTC", "daily", FakeSession(status=503, ohlc={}))
    with pytest.raises(MarketDataError, match="request failed"):
        fetch_ohlc("BTC", "daily", FakeSession(raise_exc=requests.ConnectionError("down")))


def test_funding_rate_parsing():
    tickers = {"tickers": [{"symbol": "PF_ETHUSD", "fundingRate": "0.0002", "fundingRatePrediction": "0.0001", "markPrice": "3000.5"},
                           {"symbol": "PF_XBTUSD", "fundingRate": "-0.00005", "markPrice": "100000"}]}
    f = fetch_funding_rate("BTC", FakeSession(tickers=tickers))
    assert f == {"symbol": "PF_XBTUSD", "funding_rate": -0.00005, "funding_rate_prediction": None, "mark_price": 100000.0}
    assert parse_funding(tickers, "ETH")["funding_rate_prediction"] == 0.0001
    with pytest.raises(MarketDataError):
        parse_funding({"tickers": [{"symbol": "PF_SOLUSD"}]}, "BTC")
    with pytest.raises(MarketDataError):
        parse_funding({}, "BTC")


def test_get_market_bundles_everything(monkeypatch):
    monkeypatch.setattr("src.market_data.time.sleep", lambda s: None)
    tickers = {"tickers": [{"symbol": "PF_XBTUSD", "fundingRate": "0.0001"}]}
    md = get_market("BTC", FakeSession(ohlc=kraken_ohlc_payload(10, start=1_600_000_000), tickers=tickers))
    assert md.pair == "BTC" and len(md.daily) == 10 and len(md.weekly) == 10
    assert md.funding["funding_rate"] == 0.0001 and md.fetched_at


def test_csv_round_trip(tmp_path):
    df = parse_ohlc_response(kraken_ohlc_payload(4))
    save_ohlc_csv(df, tmp_path / "x.csv")
    back = load_ohlc_csv(tmp_path / "x.csv")
    assert list(back["close"]) == list(df["close"]) and str(back["time"].dt.tz) == "UTC"
    (tmp_path / "bad.csv").write_text("a,b\n1,2\n")
    with pytest.raises(MarketDataError):
        load_ohlc_csv(tmp_path / "bad.csv")
