"""Run the analyst + planner over labelled historical windows and report agreement.

  python evals/run_evals.py [--charts evals/charts] [--labels evals/labels.json]

labels.json: {"<file>.csv": {"cutoff": "YYYY-MM-DD", "expected_class": "...",
              "expected_outcome": "target_hit|stop_hit|no_trade|unfilled", "source": "kraken|synthetic"}}
The analyst sees bars ≤ cutoff; the planner's ticket is simulated on bars after it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.analyst import analyse  # noqa: E402
from src.backtest import ACCOUNT, SETTINGS, simulate, to_weekly  # noqa: E402
from src.market_data import load_ohlc_csv  # noqa: E402
from src.planner import NoTrade, build_ticket  # noqa: E402

TRADE_OUTCOMES = ("target_hit", "stop_hit", "unfilled", "timed_out")


def eval_window(df, cutoff: str, pair: str = "BTC") -> dict:
    hist = df[df["time"] <= f"{cutoff}T23:59:59Z"]
    future = df[df["time"] > f"{cutoff}T23:59:59Z"]
    analysis = analyse(hist, to_weekly(hist))
    out = {"class": analysis["market_class"]["daily"], "weekly": analysis["market_class"]["weekly"],
           "direction": None, "outcome": "no_trade", "reason": None, "bars_seen": len(hist), "bars_after": len(future)}
    try:
        t = build_ticket(pair, cutoff, analysis, ACCOUNT, SETTINGS, None, "go")
    except NoTrade as exc:
        out["reason"] = str(exc)
        return out
    out["direction"] = t["direction"]
    if len(future):
        out["outcome"] = simulate(future, t["direction"], t["entry_zone"], t["stop"], t["target"])[0]
    else:
        out["outcome"] = "trade"  # no forward bars to simulate
    return out


def run(charts: Path, labels_path: Path) -> dict:
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    rows = []
    for name, lab in sorted(labels.items()):
        path = charts / name
        if not path.exists():
            rows.append({"file": name, "error": "missing"}); continue
        got = eval_window(load_ohlc_csv(path), lab["cutoff"], lab.get("pair", "BTC"))
        class_ok = got["class"] == lab["expected_class"]
        exp_out = lab["expected_outcome"]
        outcome_ok = (got["outcome"] == exp_out) if exp_out != "trade" else (got["direction"] is not None)
        rows.append({"file": name, "source": lab.get("source", "kraken"), "expected_class": lab["expected_class"], "class": got["class"],
                     "class_ok": class_ok, "expected_outcome": exp_out, "outcome": got["outcome"], "outcome_ok": outcome_ok,
                     "direction": got["direction"], "reason": got["reason"]})
    scored = [r for r in rows if "error" not in r]

    def pct(key, subset):
        return round(100 * sum(1 for r in subset if r[key]) / len(subset), 1) if subset else None

    by_source = {}
    for src in sorted({r["source"] for r in scored}):
        sub = [r for r in scored if r["source"] == src]
        by_source[src] = {"n": len(sub), "class_agreement_pct": pct("class_ok", sub), "outcome_agreement_pct": pct("outcome_ok", sub)}
    return {"n": len(scored), "class_agreement_pct": pct("class_ok", scored), "outcome_agreement_pct": pct("outcome_ok", scored),
            "by_source": by_source, "rows": rows}


def render(r: dict) -> str:
    lines = [f"EVALS  n={r['n']}  class agreement {r['class_agreement_pct']}%  outcome agreement {r['outcome_agreement_pct']}%"]
    for src, s in r["by_source"].items():
        lines.append(f"  {src:<10} n={s['n']:<3} class {s['class_agreement_pct']}%  outcome {s['outcome_agreement_pct']}%")
    for row in r["rows"]:
        if "error" in row:
            lines.append(f"  {row['file']:<34} ERROR {row['error']}"); continue
        mark = ("✓" if row["class_ok"] else "✗") + ("✓" if row["outcome_ok"] else "✗")
        lines.append(f"  {mark} {row['file']:<32} class {row['expected_class']:<12}→ {row['class']:<12} outcome {row['expected_outcome']:<11}→ {row['outcome']:<11}"
                     + (f" ({row['reason']})" if row["reason"] and not row["outcome_ok"] else ""))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--charts", default=str(ROOT / "evals" / "charts"))
    ap.add_argument("--labels", default=str(ROOT / "evals" / "labels.json"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    r = run(Path(args.charts), Path(args.labels))
    print(json.dumps({k: v for k, v in r.items() if k != "rows"}, indent=2) if args.json else render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
