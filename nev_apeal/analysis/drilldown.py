"""Index -> Module -> Question -> Item drilldown for a rating metric.

Maps an index (e.g. AEXT_Index) to its rating items (<prefix>_R_*),
then compares two groups of a categorical variable item by item:
weighted means, delta, Welch t-test p, Cohen's d, N, coverage, question text.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ._common import PROJECT_ROOT, emit, load, weighted_mean

try:
    from scipy import stats
except ImportError:  # pragma: no cover
    stats = None


def _label(meta, column: str) -> str:
    try:
        return str(meta.column_labels[meta.column_names.index(column)])
    except (ValueError, TypeError):
        return column


def _item_columns(df: pd.DataFrame, metric: str) -> list[str]:
    prefix = metric.removesuffix("_Index")
    return sorted(c for c in df.columns if c.startswith(prefix + "_R"))


def _question_text(metric: str, item: str) -> str:
    qm_path = PROJECT_ROOT / "data" / "questionnaire_map.json"
    if not qm_path.exists():
        return ""
    try:
        qm = json.loads(qm_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    qid = item
    for q in qm.get("questions", []):
        if q.get("qid") == qid:
            text = str(q.get("question", ""))
            return text.split(" 1 ")[0].split(" 0 ")[0].strip()
    return ""


def _item_stats(df: pd.DataFrame, item: str, group: str, a, b) -> dict:
    ga = df[df[group] == a]
    gb = df[df[group] == b]
    ya = ga[item].dropna()
    yb = gb[item].dropna()
    row = {
        "item": item,
        "group_a": a,
        "group_b": b,
        "n_a": int(len(ga)),
        "n_b": int(len(gb)),
        "n_valid_a": int(len(ya)),
        "n_valid_b": int(len(yb)),
        "weighted_mean_a": weighted_mean(ga[item], ga["APEAL_WT"].fillna(1.0)),
        "weighted_mean_b": weighted_mean(gb[item], gb["APEAL_WT"].fillna(1.0)),
    }
    row["delta"] = row["weighted_mean_b"] - row["weighted_mean_a"]
    if stats is not None and len(ya) > 5 and len(yb) > 5:
        t, p = stats.ttest_ind(ya.values, yb.values, equal_var=False)
        pooled = np.sqrt((np.var(ya.values, ddof=1) + np.var(yb.values, ddof=1)) / 2)
        row["p"] = float(p)
        row["effect_size"] = float((np.mean(yb.values) - np.mean(ya.values)) / pooled) if pooled else 0.0
    else:
        row["p"] = None
        row["effect_size"] = None
    coverage = max(row["n_valid_a"] / row["n_a"], row["n_valid_b"] / row["n_b"])
    row["coverage"] = "FULL" if coverage >= 0.9 else ("PARTIAL" if coverage >= 0.75 else "LIMITED")
    row["question_text"] = _question_text("", item)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Index → Question → Item 下钻")
    parser.add_argument("--metric", required=True, help="如 AEXT_Index")
    parser.add_argument("--group", default="YPV_01")
    parser.add_argument("--compare", nargs=2, required=True, type=float, help="两组取值，如 2.0 3.0")
    parser.add_argument("--level", default="item", choices=["index", "module", "question", "item"])
    args = parser.parse_args()

    df, meta = load()
    items = _item_columns(df, args.metric)
    rows = []
    if args.level in ("question", "item"):
        for item in items:
            rows.append(_item_stats(df, item, args.group, args.compare[0], args.compare[1]))
    else:
        row = _item_stats(df, args.metric, args.group, args.compare[0], args.compare[1])
        row["item"] = args.metric
        row["question_text"] = f"{args.metric}（模块整体）"
        rows.append(row)

    emit({
        "metric": args.metric,
        "group": args.group,
        "compare": [args.compare[0], args.compare[1]],
        "level": args.level,
        "n_items": len(items),
        "module": args.metric.removesuffix("_Index"),
        "rows": rows,
        "data_boundary": f"{args.metric} 模块仅含 {len(items)} 个 rating 题项；本数据片段无更高粒度的题项时如实反映",
    })


if __name__ == "__main__":
    main()
