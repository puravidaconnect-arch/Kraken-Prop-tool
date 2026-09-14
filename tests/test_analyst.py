import json

import pytest

from src.analyst import CLASSES, analyse, classify, weekly_agrees
from tests.synth import coiling, ranging, trend


@pytest.mark.parametrize("name,df,expected", [
    ("uptrend", trend(), "uptrend"),
    ("downtrend", trend(drift=-0.004, seed=4), "downtrend"),
    ("coiling", coiling(), "coiling"),
    ("range at low band", ranging(n=306), "ranging"),
    ("range at high band", ranging(n=294), "ranging"),
])
def test_classification(name, df, expected):
    r = classify(df)
    assert r.market_class == expected, (name, r.reasons)
    assert r.reasons and r.levels["close"] == df["close"].iloc[-1]


def test_too_few_bars_is_unclassified():
    r = classify(trend(n=100))
    assert r.market_class == "unclassified" and "100 bars" in r.reasons[0]


def test_read_is_json_serialisable():
    json.dumps(classify(trend()).as_dict())


def test_weekly_agreement_rules():
    assert weekly_agrees("uptrend", "uptrend")
    assert weekly_agrees("uptrend", "ranging")
    assert weekly_agrees("uptrend", "unclassified")
    assert not weekly_agrees("uptrend", "downtrend")
    assert not weekly_agrees("downtrend", "uptrend")


def test_analyse_combines_timeframes():
    a = analyse(trend(), trend(n=250))
    assert a["market_class"] == {"daily": "uptrend", "weekly": "uptrend"}
    assert a["weekly_agrees"] and a["strategy"] == "trend_pullback"
    b = analyse(trend(), trend(drift=-0.004, seed=4, n=250))
    assert not b["weekly_agrees"] and b["strategy"] is None
    assert set(a["market_class"].values()) <= set(CLASSES)
