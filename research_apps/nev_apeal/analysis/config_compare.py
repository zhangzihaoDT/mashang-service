"""Config attribution — Level 1 raw gap + Level 2 controlled regression.

Level 1: has-vs-not raw weighted gap (mean, delta, t-test, Cohen's d).
Level 2: same config in a regression controlled by price/brand/energy —
         shows how much of the raw gap survives confounders.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from ._common import emit, load, weighted_mean

try:
    from scipy import stats
    import statsmodels.formula.api as smf
except ImportError:  # pragma: no cover
    stats, smf = None, None


def level1_raw(df: pd.DataFrame, config: str, metric: str) -> dict:
    has = df[df[config] == 1]
    no = df[df[config] == 0]
    m_has = weighted_mean(has[metric], has["APEAL_WT"].fillna(1.0))
    m_no = weighted_mean(no[metric], no["APEAL_WT"].fillna(1.0))
    out = {
        "level": 1, "method": "raw has-vs-not",
        "n_has": int(len(has)), "n_not": int(len(no)),
        "wmean_has": round(m_has, 2), "wmean_not": round(m_no, 2),
        "delta": round(m_has - m_no, 2),
    }
    if stats is not None:
        a = has[metric].dropna().to_numpy()
        b = no[metric].dropna().to_numpy()
        if len(a) > 5 and len(b) > 5:
            _, p = stats.ttest_ind(a, b, equal_var=False)
            pooled = np.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2)
            out["p"] = float(p)
            out["cohens_d"] = round(float((np.mean(a) - np.mean(b)) / pooled), 3) if pooled else 0.0
        else:
            out["p"], out["cohens_d"] = None, None
    return out


def _term_for(col: str, df: pd.DataFrame) -> str:
    if col in ("MAKE_DP", "SUPER_SEGMENT_DP", "SEGMENT_DP", "GENERATION2", "CITY_TIER_DP", "BODYTYPE_DP"):
        return f"C({col})"
    return col


def level2_controlled(df: pd.DataFrame, config: str, metric: str, controls: list[str]) -> dict:
    controls = [c for c in controls if c in df.columns]
    terms = [f"C({config})"] + [_term_for(c, df) for c in controls]
    formula = f"{metric} ~ {' + '.join(terms)}"
    fit = smf.ols(formula, data=df).fit()
    coefs = {}
    for term in fit.params.index:
        if f"C({config})" in term:
            coefs[term] = {"coef": round(float(fit.params[term]), 2), "p": float(fit.pvalues[term])}
    return {
        "level": 2, "method": f"controlled ({', '.join(controls)})",
        "n": int(fit.nobs), "r_squared": round(float(fit.rsquared), 4),
        "adjusted_effect": coefs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="配置归因：Level1 raw gap + Level2 controlled")
    parser.add_argument("--config", required=True, help="二分配置列")
    parser.add_argument("--metric", default="APEAL_Index")
    parser.add_argument("--controls", nargs="+", default=["CN_YNV_07", "MAKE_DP", "SUPER_SEGMENT_DP"])
    args = parser.parse_args()

    df, meta = load()
    label = (meta.column_labels[meta.column_names.index(args.config)]
             if meta.column_labels and args.config in meta.column_names else args.config)
    l1 = level1_raw(df, args.config, args.metric)
    l2 = level2_controlled(df, args.config, args.metric, args.controls)
    emit({"config": args.config, "config_label": label, "metric": args.metric, "levels": [l1, l2]})


if __name__ == "__main__":
    main()
