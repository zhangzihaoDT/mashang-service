"""Config attribution — Level 3 matched comparison within brand × price-band cells.

Pooled within-cell has-vs-not difference: for each (brand, price band) cell with
enough has/not samples, compute the weighted gap, then aggregate across cells.
A residual consistent positive gap after matching is far stronger product evidence
than a raw global gap (which mixes price/brand composition).
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from ._common import emit, load, weighted_mean


def main() -> None:
    parser = argparse.ArgumentParser(description="配置归因 Level3：品牌×价格带 cell 内匹配比较")
    parser.add_argument("--config", required=True)
    parser.add_argument("--metric", default="APEAL_Index")
    parser.add_argument("--match-by", nargs="+", default=["MAKE_DP", "CN_YNV_07"],
                        help="匹配键：默认 品牌×价格带")
    parser.add_argument("--price-bands", type=int, default=4, help="价格带数（quantile）")
    parser.add_argument("--min-cell", type=int, default=30, help="cell 内 has/not 最小样本")
    args = parser.parse_args()

    df, meta = load()
    label = (meta.column_labels[meta.column_names.index(args.config)]
             if meta.column_labels and args.config in meta.column_names else args.config)

    cell = pd.Series([""] * len(df), index=df.index, dtype=object)
    for col in args.match_by:
        if col == "CN_YNV_07":
            band = pd.qcut(df[col], args.price_bands, labels=False, duplicates="drop")
            part = band.fillna(-1).astype(int).astype(str)
        else:
            part = df[col].fillna(-1).astype(int).astype(str)
        cell = cell + part
    df = df.assign(_cell=cell)

    rows, deltas = [], []
    for cell, g in df.groupby("_cell"):
        has, no = g[g[args.config] == 1], g[g[args.config] == 0]
        if len(has) < args.min_cell or len(no) < args.min_cell:
            continue
        m_has = weighted_mean(has[args.metric], has["APEAL_WT"].fillna(1.0))
        m_no = weighted_mean(no[args.metric], no["APEAL_WT"].fillna(1.0))
        d = m_has - m_no
        rows.append({
            "cell": cell, "n_has": int(len(has)), "n_not": int(len(no)),
            "wmean_has": round(m_has, 2), "wmean_not": round(m_no, 2), "delta": round(d, 2),
        })
        deltas.append(d)

    if not deltas:
        emit({"config": args.config, "metric": args.metric, "match_by": args.match_by,
              "levels": [{"level": 3, "n_cells": 0, "note": "无足够 cell"}], "rows": rows})
        return

    weighted_cells = [r["delta"] * (r["n_has"] + r["n_not"]) for r in rows]
    pooled = sum(weighted_cells) / sum(r["n_has"] + r["n_not"] for r in rows)
    consistent = sum(1 for d in deltas if d > 0) / len(deltas)
    l3 = {
        "level": 3,
        "method": f"matched within {', '.join(args.match_by)} cells",
        "n_cells": len(rows),
        "mean_cell_delta": round(float(np.mean(deltas)), 2),
        "sample_weighted_delta": round(float(pooled), 2),
        "consistency_pct": round(consistent * 100, 1),
        "interpretation": ("配置效应在匹配 cell 内仍一致为正 → 强于 raw 证据；"
                           "若收缩/翻转 → raw gap 由品牌/价格 mix 驱动"),
    }
    emit({"config": args.config, "config_label": label, "metric": args.metric,
          "match_by": args.match_by, "levels": [l3], "rows": rows})


if __name__ == "__main__":
    main()
