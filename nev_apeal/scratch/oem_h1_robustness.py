"""T8 OEM Experience Gap — H1 Robustness: does the Traditional-Chinese-OEM APEAL gap
survive full controls (energy/price/premium/segment + demographics)?

Sequential coefficient path for ORIGIN3_DP (reference = Domestic Traditional Brands).
Uses PREMMAKE_DP (not collinear MAKE_DP) per E-001 caveat. Same analytic sample across steps.
"""

from __future__ import annotations

import statsmodels.formula.api as smf

from analysis._common import load

# ORIGIN3_DP: 1=Domestic Traditional (ref) 2=International 3=Domestic Startup 4=Domestic Affiliated
STEPS = [
    ("raw", []),
    ("+ 能源 SUPER_SEGMENT_DP", ["SUPER_SEGMENT_DP"]),
    ("+ 价格 CN_YNV_07", ["SUPER_SEGMENT_DP", "CN_YNV_07"]),
    ("+ 豪华/大众 PREMMAKE_DP", ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP"]),
    ("+ 车身 SEGMENT_DP", ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "SEGMENT_DP"]),
    ("+ 年龄 AGE_BUCKETS", ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "SEGMENT_DP", "AGE_BUCKETS"]),
    ("+ 收入 CN_INCOME", ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "SEGMENT_DP", "AGE_BUCKETS", "CN_INCOME"]),
    ("+ 教育 CN_EDUCATION", ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "SEGMENT_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION"]),
]


def terms(meta, predictors):
    return [f"C({p})" if meta.variable_value_labels.get(p) else p for p in predictors]


def main():
    df, meta = load()
    keep_cols = ["APEAL_Index", "ORIGIN3_DP"] + [c for _, cs in STEPS for c in cs]
    df = df.dropna(subset=keep_cols).copy()
    df["ORIGIN3_DP"] = df["ORIGIN3_DP"].astype(int)
    print(f"analytic sample n = {len(df)}（union dropna，含 SEGMENT_DP/人口学缺失剔除）\n")

    fit = None
    for label, ctrl in STEPS:
        formula = "APEAL_Index ~ C(ORIGIN3_DP)"
        if ctrl:
            formula += " + " + " + ".join(terms(meta, ctrl))
        fit = smf.ols(formula, data=df).fit()
        parts = []
        for k in fit.params.index:
            if "C(ORIGIN3_DP)" in k:
                parts.append(f"{k.split('[')[1].replace(']', '')}:{fit.params[k]:+.2f}(p={fit.pvalues[k]:.4f})")
        print(f"  {label:<34} n={int(fit.nobs):>5}  " + "  ".join(parts))

    # 加权敏感（WLS, final step）
    formula = "APEAL_Index ~ C(ORIGIN3_DP) + " + " + ".join(terms(meta, STEPS[-1][1]))
    wf = smf.wls(formula, data=df, weights=df["APEAL_WT"].fillna(1.0)).fit()
    print("\n  加权敏感（WLS, final step）：")
    for k in wf.params.index:
        if "C(ORIGIN3_DP)" in k:
            print(f"    {k.split('[')[1].replace(']', '')}: {wf.params[k]:+.2f} p={wf.pvalues[k]:.4f}")


if __name__ == "__main__":
    main()
