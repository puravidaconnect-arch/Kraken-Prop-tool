import json
from pathlib import Path

from evals.run_evals import eval_window, render, run

ROOT = Path(__file__).resolve().parent.parent


def test_shipped_evals_run_and_report_a_score():
    r = run(ROOT / "evals" / "charts", ROOT / "evals" / "labels.json")
    assert r["n"] >= 20
    assert isinstance(r["class_agreement_pct"], float) and isinstance(r["outcome_agreement_pct"], float)
    assert r["by_source"]["synthetic"]["n"] >= 20
    assert r["class_agreement_pct"] >= 80  # regression guard on the shipped synthetic set
    text = render(r)
    assert text.startswith("EVALS  n=") and "class agreement" in text


def test_labels_are_complete_and_valid():
    labels = json.loads((ROOT / "evals" / "labels.json").read_text())
    for name, lab in labels.items():
        assert (ROOT / "evals" / "charts" / name).exists(), name
        assert lab["expected_class"] in ("uptrend", "downtrend", "ranging", "coiling", "unclassified"), name
        assert lab["expected_outcome"] in ("trade", "no_trade", "target_hit", "stop_hit", "unfilled", "timed_out"), name
        assert lab["source"] in ("kraken", "synthetic")


def test_eval_window_reports_missing_future(tmp_path):
    from src.market_data import load_ohlc_csv
    df = load_ohlc_csv(ROOT / "evals" / "charts" / "synth_uptrend_1.csv")
    got = eval_window(df, str(df["time"].iloc[-1].date()))
    assert got["bars_after"] == 0 and got["outcome"] in ("trade", "no_trade")
