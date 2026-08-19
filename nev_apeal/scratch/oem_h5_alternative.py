"""T8 OEM Experience Gap — H5 Alternative explanation: after adding brand image (YNV_CN_6*),
usage intensity (NEV_12/NEV_13a), and usage scenario (NEV_11A-G) on top of full controls,
does the intl/startup residual survive?

E-006 tested image with n=9450 (intl +5.34 p=0.11). Here run on a common analytic sample
to trace the coefficient path across blocks. ORIGIN3_DP levels 2 (intl) & 3 (startup).
"""

from __future__ import annotations

import numpy as np
import statsmodels.formula.api as smf

from analysis._common import load

FULL = ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "SEGMENT_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION"]
IMAGE = [f"YNV_CN_6_{i}" for i in (1, 2, 3, 5, 11, 13, 14)]
BLOCKS = [
    ("full (结构+人口学)", []),
    ("+ 品牌形象 YNV_CN_6", IMAGE),
    ("+ 使用强度 NEV_12/NEV_13a", ["NEV_12", "NEV_13a"]),
    ("+ 使用场景 NEV_11A-G", ["NEV_11A", "NEV_11B", "NEV_11C", "NEV_11D", "NEV_11E", "NEV_11F", "NEV_11G"]),
]


def terms(meta, predictors):
    return [f"C({p})" if meta.variable_value_labels.get(p) else p for p in predictors]


def main():
    df, meta = load()
    df["ORIGIN3_DP"] = df["ORIGIN3_DP"].astype(int)
    for c in IMAGE:
        df[c] = df[c].replace(99.0, np.nan)
    df["SEGMENT_DP"] = df["SEGMENT_DP"].astype(int)
    keep = ["APEAL_Index", "ORIGIN3_DP"] + FULL + [c for _, cs in BLOCKS for c in cs]
    df = df.dropna(subset=keep).copy()
    df2 = df[df["ORIGIN3_DP"] != 4].copy()
    df2["ORIGIN3_DP"] = df2["ORIGIN3_DP"].astype(int)
    print(f"analytic sample (Intl/Startup/Trad) n = {len(df2)}（union dropna，含形象/使用强度缺失剔除）\n")

    fit = None
    for label, add in BLOCKS:
        preds = FULL + [c for _, cs in BLOCKS[:BLOCKS.index((label, add)) + 1] for c in cs]
        formula = "APEAL_Index ~ C(ORIGIN3_DP) + " + " + ".join(terms(meta, preds))
        fit = smf.ols(formula, data=df2).fit()
        parts = []
        for k in fit.params.index:
            if "C(ORIGIN3_DP)" in k:
                tag = k.split("[T.")[1].replace("]", "")
                parts.append(f"origin{tag}={fit.params[k]:+.2f}(p={fit.pvalues[k]:.4f})")
        print(f"  {label:<42} n={int(fit.nobs):>5}  " + "  ".join(parts))

    # WLS final
    formula = "APEAL_Index ~ C(ORIGIN3_DP) + " + " + ".join(terms(meta, FULL + [c for _, cs in BLOCKS for c in cs]))
    wf = smf.wls(formula, data=df2, weights=df2["APEAL_WT"].fillna(1.0)).fit()
    print("\n  加权敏感（WLS, final model）：")
    for k in wf.params.index:
        if "C(ORIGIN3_DP)" in k:
            tag = k.split("[T.")[1].replace("]", "")
            print(f"    origin{tag}: {wf.params[k]:+.2f} p={wf.pvalues[k]:.4f}")


if __name__ == "__main__":
    main()