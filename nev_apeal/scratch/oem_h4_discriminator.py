"""T8 OEM Experience Gap — H4 Discriminator: are the international and domestic-startup
residuals vs traditional OEM of the same nature (brand-level residual), or different?

E-006 suggests startup is absorbable by structure+image while international is not.
Sequential coefficient path for ORIGIN3_DP levels 2 (intl) and 3 (startup), on a common
analytic sample, controls as in E-008.
"""

from __future__ import annotations

import statsmodels.formula.api as smf

from analysis._common import load

# ORIGIN3_DP: 1=Domestic Traditional (ref) 2=International 3=Domestic Startup 4=Domestic Affiliated
STEPS = [
    ("raw", []),
    ("+ 结构(能源/价格/豪华/车身)", ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "SEGMENT_DP"]),
    ("+ 年龄", ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "SEGMENT_DP", "AGE_BUCKETS"]),
    ("+ 收入", ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "SEGMENT_DP", "AGE_BUCKETS", "CN_INCOME"]),
    ("+ 教育", ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "SEGMENT_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION"]),
]


def terms(meta, predictors):
    return [f"C({p})" if meta.variable_value_labels.get(p) else p for p in predictors]


def main():
    df, meta = load()
    keep_cols = ["APEAL_Index", "ORIGIN3_DP"] + [c for _, cs in STEPS for c in cs]
    df = df.dropna(subset=keep_cols).copy()
    df["ORIGIN3_DP"] = df["ORIGIN3_DP"].astype(int)
    df2 = df[df["ORIGIN3_DP"] != 4].copy()  # restrict to Intl/Startup/Trad for readability
    df2["ORIGIN3_DP"] = df2["ORIGIN3_DP"].astype(int)
    print(f"analytic sample (Intl/Startup/Trad) n = {len(df2)}\n")

    for label, ctrl in STEPS:
        formula = "APEAL_Index ~ C(ORIGIN3_DP)"
        if ctrl:
            formula += " + " + " + ".join(terms(meta, ctrl))
        fit = smf.ols(formula, data=df2).fit()
        parts = []
        for k in fit.params.index:
            if "C(ORIGIN3_DP)" in k:
                tag = k.split("[T.")[1].replace("]", "")
                parts.append(f"origin{tag}={fit.params[k]:+.2f}(p={fit.pvalues[k]:.4f})")
        print(f"  {label:<44} n={int(fit.nobs):>5}  " + "  ".join(parts))

    # 加权敏感 final
    formula = "APEAL_Index ~ C(ORIGIN3_DP) + " + " + ".join(terms(meta, STEPS[-1][1]))
    wf = smf.wls(formula, data=df2, weights=df2["APEAL_WT"].fillna(1.0)).fit()
    print("\n  加权敏感（WLS, final step）：")
    for k in wf.params.index:
        if "C(ORIGIN3_DP)" in k:
            tag = k.split("[T.")[1].replace("]", "")
            print(f"    origin{tag}: {wf.params[k]:+.2f} p={wf.pvalues[k]:.4f}")

    # WLS with raw n (weighted on all rows, maybe larger n)
    df3 = df[df["ORIGIN3_DP"].isin([1, 2, 3])].copy()
    fitw = smf.wls(formula, data=df3, weights=df3["APEAL_WT"].fillna(1.0)).fit()
    print("\n  加权敏感（WLS, full analytic sample n=%d）：" % len(df3))
    for k in fitw.params.index:
        if "C(ORIGIN3_DP)" in k:
            tag = k.split("[T.")[1].replace("]", "")
            print(f"    origin{tag}: {fitw.params[k]:+.2f} p={fitw.pvalues[k]:.4f}")


if __name__ == "__main__":
    main()