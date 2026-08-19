"""H3 Mechanism decomposition — how much of the NEV08 APEAL gap rides on charging-experience modules (ACHAR/AFUEL)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from analysis._common import load, labels, WEIGHT

DOSE_MAP = {1.0: 1, 2.0: 2, 3.0: 3, 4.0: 4, 5.0: 5, 99.0: 6}
FULL = ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION"]
ACHAR_ITEMS = [f"ACHAR_R_{i:02d}" for i in range(1, 10)]
MODULES = ["ACHAR_index", "AFUEL_Index", "APEAL_Index"]


def terms(meta, predictors):
    return [f"C({p})" if meta.variable_value_labels.get(p) else p for p in predictors]


def wmean(s, w):
    m = s.notna() & w.notna()
    return float(np.average(s[m], weights=w[m])) if m.any() else float("nan")


def main():
    df, meta = load()
    lab = labels(meta, "NEV_08")
    df["DOSE"] = df["NEV_08"].map(DOSE_MAP)
    df = df.dropna(subset=["DOSE"]).copy()
    df["DOSE"] = df["DOSE"].astype(int)
    df["CLUSTER"] = df["DOSE"].map({1: "L", 2: "L", 3: "M", 4: "M", 5: "M", 6: "H"})
    df["NEV08_LABEL"] = df["NEV_08"].map(lab)
    lab_name = lambda d: lab.get(float([k for k, v in DOSE_MAP.items() if v == d][0]), "")

    w = df[WEIGHT].fillna(1.0)
    print("== 模块指数 gap（Never vs Everyday，加权原始；及三聚集 H-L）==")
    rows = []
    for mod in MODULES:
        m_Never = wmean(df.loc[df["DOSE"] == 6, mod], w[df["DOSE"] == 6])
        m_Daily = wmean(df.loc[df["DOSE"] == 1, mod], w[df["DOSE"] == 1])
        m_H = wmean(df.loc[df["CLUSTER"] == "H", mod], w[df["CLUSTER"] == "H"])
        m_L = wmean(df.loc[df["CLUSTER"] == "L", mod], w[df["CLUSTER"] == "L"])
        rows.append((mod, m_Daily, m_Never, m_Never - m_Daily, m_L, m_H, m_H - m_L))
    print(f"  {'module':<14}{'Daily':>8}{'Never':>8}{'ΔNever-Da':>10}{'L':>8}{'H':>8}{'ΔH-L':>8}")
    for r in rows:
        print(f"  {r[0]:<14}{r[1]:>8.1f}{r[2]:>8.1f}{r[3]:>+10.1f}{r[4]:>8.1f}{r[5]:>8.1f}{r[6]:>+8.1f}")

    t = " + ".join(terms(meta, FULL))
    print("\n== 模块指数受控 contrast（Never vs Everyday，完整控制）==")
    for mod in ["ACHAR_index", "AFUEL_Index", "APEAL_Index"]:
        fit = smf.ols(f"{mod} ~ C(DOSE) + {t}", data=df).fit()
        terms5 = {k: (fit.params[k], fit.pvalues[k]) for k in fit.params.index if "C(DOSE)" in k and "[T.6" in k}
        assert terms5, f"no dose6 term for {mod}"
        k, (c, p) = next(iter(terms5.items()))
        print(f"  {mod}: dose6(从不) vs dose1(每天) coef={c:+.2f}  p={p:.4f}")

    print("\n== ACHAR/AFUEL item gap（Never vs Everyday，加权；10-point rating）==")
    items = ACHAR_ITEMS + ["AFUEL_R_01"]
    print(f"  {'item':<14}{'Daily':>8}{'Never':>8}{'Δ':>8}")
    for it in items:
        s = df[it].clip(lower=1, upper=10)
        m_d = wmean(s[df["DOSE"] == 1], w[df["DOSE"] == 1])
        m_n = wmean(s[df["DOSE"] == 6], w[df["DOSE"] == 6])
        print(f"  {it:<14}{m_d:>8.2f}{m_n:>8.2f}{m_n - m_d:>+8.2f}")


if __name__ == "__main__":
    main()