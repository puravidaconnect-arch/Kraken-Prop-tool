"""Generate SYNTHETIC labelled eval windows so the pipeline can be scored before
real Kraken windows are labelled. These are not market data and are never used
for trading. Replace them with real windows via make_windows.py.

  python evals/make_synthetic.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.market_data import save_ohlc_csv  # noqa: E402
from tests.synth import coiling, ranging, trend  # noqa: E402

AFTER = 30


def cases():
    for seed in range(5):
        yield f"synth_uptrend_{seed}", trend(n=300 + AFTER, seed=seed, drift=0.006, vol=0.01), "uptrend", "trade"
    for seed in range(5):
        yield f"synth_downtrend_{seed}", trend(n=300 + AFTER, seed=10 + seed, drift=-0.006, vol=0.01), "downtrend", "trade"
    for k in range(5):
        yield f"synth_coiling_{k}", coiling(n=300 + AFTER, seed=20 + k), "coiling", "no_trade"
    for k, n in enumerate((306, 294, 318, 282, 330)):
        yield f"synth_range_{k}", ranging(n=n + AFTER, seed=30 + k), "ranging", "trade"


def main() -> int:
    charts, labels_path = ROOT / "evals" / "charts", ROOT / "evals" / "labels.json"
    labels = json.loads(labels_path.read_text()) if labels_path.exists() else {}
    for name, df, klass, outcome in cases():
        # the last AFTER bars are the "future"; the coiling/range windows classify on the bar before them
        cutoff = str(df["time"].iloc[-AFTER - 1].date())
        save_ohlc_csv(df, charts / f"{name}.csv")
        labels[f"{name}.csv"] = {"pair": "BTC", "cutoff": cutoff, "expected_class": klass, "expected_outcome": outcome, "source": "synthetic"}
    labels_path.write_text(json.dumps(labels, indent=2) + "\n")
    print(f"wrote {sum(1 for _ in cases())} synthetic windows and labels")
    return 0


if __name__ == "__main__":
    sys.exit(main())
