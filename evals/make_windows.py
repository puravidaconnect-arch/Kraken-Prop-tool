"""Slice a long daily history CSV into labelled eval windows.

  python evals/make_windows.py evals/history/BTC_daily.csv --pair BTC --cutoffs 2024-03-01 2024-08-15 ...
  python evals/make_windows.py evals/history/BTC_daily.csv --pair BTC --auto 20

Each window = 260 bars before the cutoff + 30 bars after, written to
evals/charts/<PAIR>_<cutoff>.csv, and a stub added to evals/labels.json with
expected_class / expected_outcome set to "TODO" for you to hand-label from the chart.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.market_data import load_ohlc_csv, save_ohlc_csv  # noqa: E402

BEFORE, AFTER = 260, 30


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("history")
    ap.add_argument("--pair", default="BTC")
    ap.add_argument("--cutoffs", nargs="*", default=[])
    ap.add_argument("--auto", type=int, default=0, help="pick N evenly spaced cutoffs instead")
    ap.add_argument("--charts", default=str(ROOT / "evals" / "charts"))
    ap.add_argument("--labels", default=str(ROOT / "evals" / "labels.json"))
    args = ap.parse_args(argv)

    df = load_ohlc_csv(args.history)
    charts, labels_path = Path(args.charts), Path(args.labels)
    labels = json.loads(labels_path.read_text()) if labels_path.exists() else {}
    if args.auto:
        idx = [int(BEFORE + k * (len(df) - BEFORE - AFTER - 1) / max(args.auto - 1, 1)) for k in range(args.auto)]
        cutoffs = [str(df["time"].iloc[i].date()) for i in idx]
    else:
        cutoffs = args.cutoffs
    for c in cutoffs:
        pos = df.index[df["time"] <= f"{c}T23:59:59Z"]
        if len(pos) < BEFORE:
            print(f"skip {c}: fewer than {BEFORE} bars before it"); continue
        i = pos[-1]
        window = df.iloc[max(0, i - BEFORE + 1): i + 1 + AFTER]
        name = f"{args.pair}_{c}.csv"
        save_ohlc_csv(window, charts / name)
        labels.setdefault(name, {"pair": args.pair, "cutoff": c, "expected_class": "TODO", "expected_outcome": "TODO", "source": "kraken"})
        print(f"wrote {name} ({len(window)} bars)")
    labels_path.write_text(json.dumps(labels, indent=2) + "\n")
    print(f"labels: {labels_path} — fill in every TODO by hand before running run_evals.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
