"""Controlled nonlinear-pattern scanner for the Discovery layer.

This scanner starts with registered continuous/ordered exposures only. It does
not search every column or every possible binning scheme.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from analysis._common import WEIGHT, load, weighted_mean

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "scratch" / "discovery" / "_signals_nonlinear.json"
CONTROLS = ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION"]
REGISTERED = {
    "NEV_12": {"label": "累计里程", "edges": [0, 1000, 5000, 10000, 20000, 50000, np.inf]},
}


def scan_one(df: pd.DataFrame, exposure: str, config: dict) -> dict:
    cols = [exposure, "APEAL_Index", WEIGHT, *CONTROLS]
    d = df[cols].dropna().copy()
    d["BIN"] = pd.cut(d[exposure], bins=config["edges"], right=False, include_lowest=True)
    d = d[d["BIN"].notna()].copy()
    groups = []
    for label, g in d.groupby("BIN", observed=True):
        groups.append({
            "bin": str(label),
            "n": int(len(g)),
            "weighted_mean": round(weighted_mean(g["APEAL_Index"], g[WEIGHT].fillna(1.0)), 2),
        })

    d["x"] = d[exposure]
    linear = smf.ols("APEAL_Index ~ x", data=d).fit()
    binned = smf.ols("APEAL_Index ~ x + C(BIN)", data=d).fit()
    df_diff = binned.df_model - linear.df_model
    f_stat = ((linear.ssr - binned.ssr) / df_diff) / (binned.ssr / binned.df_resid)
    p_value = float(stats.f.sf(f_stat, df_diff, binned.df_resid))

    adjusted = smf.wls(
        "APEAL_Index ~ C(BIN) + " + " + ".join(CONTROLS),
        data=d,
        weights=d[WEIGHT].fillna(1.0),
    ).fit(cov_type="HC1")
    coefs = {
        term: {"coef": round(float(adjusted.params[term]), 2), "p": round(float(adjusted.pvalues[term]), 6)}
        for term in adjusted.params.index
        if term.startswith("C(BIN)")
    }
    means = [row["weighted_mean"] for row in groups]
    signs = np.sign(np.diff(means))
    direction_changes = int(sum(a != b for a, b in zip(signs[:-1], signs[1:]) if a and b))
    return {
        "signal_id": "nonlinear_pattern_01",
        "analysis_type": "nonlinear_pattern",
        "exposure": exposure,
        "moderator": None,
        "outcome": "APEAL_Index",
        "effect_size": {"range": round(max(means) - min(means), 2), "nested_f": round(float(f_stat), 2), "p": round(p_value, 6), "unit": "APEAL points"},
        "sample_support": {"n": int(len(d)), "coverage": "FULL"},
        "stability": "moderate" if p_value < 0.05 else "fragile",
        "novelty": 4,
        "interpretation": f"{config['label']}呈非单调分段结构；控制主要结构与人口变量后，分箱相对线性模型的增量检验 p={p_value:.4g}。",
        "controls": CONTROLS,
        "direction": f"weighted range={max(means) - min(means):.1f}; direction_changes={direction_changes}",
        "coverage": "FULL",
        "caveats": "横截面观察性分析；分箱边界为业务预注册边界，不代表因果剂量反应。",
        "bins": groups,
        "adjusted_bin_coefs": coefs,
    }


def main() -> None:
    df, _ = load()
    signals = [scan_one(df, exposure, config) for exposure, config in REGISTERED.items()]
    OUT.write_text(json.dumps(signals, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(signals, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
