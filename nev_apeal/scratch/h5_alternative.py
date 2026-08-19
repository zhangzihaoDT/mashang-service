"""H5 Alternative explanation — does the NEV08 effect survive usage intensity / usage scenario / home-charging controls?

Decisive round: if the Never-vs-Everyday coefficient collapses after adding NEV_12 (km) / NEV_13a (driving
hours) / NEV_11A-G (scenarios) / NEV_05+NEV_07 (home charging), then NEV08 is a downstream proxy and the
topic pivots to the underlying axis.  Same analytic sample across all blocks (listwise-delete on the union).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from analysis._common import load, WEIGHT

DOSE_MAP = {1.0: 1, 2.0: 2, 3.0: 3, 4.0: 4, 5.0: 5, 99.0: 6}
FULL = ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION"]
BLOCKS = [
    ("base (FULL)", []),
    ("+ 使用强度 NEV_12/NEV_13a", ["NEV_12", "NEV_13a"]),
    ("+ 使用场景 NEV_11A-G", ["NEV_11A", "NEV_11B", "NEV_11C", "NEV_11D", "NEV_11E", "NEV_11F", "NEV_11G"]),
    ("+ 家充 NEV_05_R1/NEV_07", ["NEV_05_R1", "NEV_07"]),
    ("+ 慢充 NEV_01", ["NEV_01"]),
]
ALL_PREDICTORS = [c for _, cs in BLOCKS for c in cs]


def terms(meta, predictors):
    return [f"C({p})" if meta.variable_value_labels.get(p) else p for p in predictors]


def main():
    df, meta = load()
    df["DOSE"] = df["NEV_08"].map(DOSE_MAP)
    df = df.dropna(subset=["DOSE"]).copy()
    df["DOSE"] = df["DOSE"].astype(int)
    # NEV_07 '99 = Don't know' -> NaN (measurement artifact), NEV_05_R1 binary
    df["NEV_07"] = df["NEV_07"].replace(99.0, np.nan)
    # keep a single analytic sample across all blocks
    keep_cols = ["APEAL_Index", "DOSE"] + FULL + ALL_PREDICTORS
    df = df.dropna(subset=keep_cols).copy()
    print(f"analytic sample n = {len(df)}（union dropna，含 NEV_13a/NEV_05 缺失剔除）")

    fit = None
    for label, add in BLOCKS:
        preds = FULL + [p for _, cs in BLOCKS[:BLOCKS.index((label, add)) + 1] for p in cs]
        formula = "APEAL_Index ~ C(DOSE) + " + " + ".join(terms(meta, preds))
        fit = smf.ols(formula, data=df).fit()
        k = next(k for k in fit.params.index if "C(DOSE)" in k and "[T.6" in k)
        k4 = next(k for k in fit.params.index if "C(DOSE)" in k and "[T.4" in k)
        print(f"  {label:<34} dose6(从不) coef={fit.params[k]:+.2f} p={fit.pvalues[k]:.4f}   | dose4(2-3次/月) coef={fit.params[k4]:+.2f} p={fit.pvalues[k4]:.4f}   n={int(fit.nobs)}")

    # weighted sensitivity on final model
    wf = smf.wls(formula, data=df, weights=df[WEIGHT].fillna(1.0)).fit()
    k = next(k for k in wf.params.index if "C(DOSE)" in k and "[T.6" in k)
    print(f"\n  加权敏感（WLS, final model）：dose6 coef={wf.params[k]:+.2f} p={wf.pvalues[k]:.4f}")

    # what did usage-intensity blocks absorb? report NEV_12 / NEV_13a raw direction
    print("\n  使用强度原始关系（信号板已见）：NEV_12 1k-5k 峰(795.5)/10k-20k(769.2)；NEV_13a 2-4h(804.2)/1-2h(773.2)")

    # collinearity sanity: NEV08 dose vs usage vars (raw weighted means of usage by NEV08 dose)
    print("\n  NEV08 dose 与使用强度/场景共变（原始加权均值）：")
    for var in ["NEV_12", "NEV_13a"]:
        row = []
        for dose in [1, 2, 6]:
            sub = df[df["DOSE"] == dose]
            w = sub[WEIGHT].fillna(1.0)
            row.append(f"dose{dose}={np.average(sub[var], weights=w):.0f}")
        print(f"    {var}: " + "  ".join(row))


if __name__ == "__main__":
    main()