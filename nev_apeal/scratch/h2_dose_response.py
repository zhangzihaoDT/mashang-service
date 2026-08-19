"""H2 Dose-response — ordinal dose analysis for NEV_08 (charging_lifestyle).

NEV_08 is ordered: Everyday(1) < Twice+/wk(2) < Once/wk(3) < 2-3x/mo(4) < <=1x/mo(5) < Never(6).
Tests: per-dose effect with CI, monotone linear trend (ordinal score), departure
from linearity (nested F), and the specific <=1x/mo vs 2-3x/mo inversion.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from analysis._common import labels, load, WEIGHT

DOSE_MAP = {1.0: 1, 2.0: 2, 3.0: 3, 4.0: 4, 5.0: 5, 99.0: 6}
CONTROLS = ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION"]


def terms(meta, predictors: list[str]) -> list[str]:
    return [f"C({p})" if meta.variable_value_labels.get(p) else p for p in predictors]


def weighted_ci(series: pd.Series, weights: pd.Series) -> tuple[float, float]:
    m = series.notna() & weights.notna()
    vals, wts = series[m].to_numpy(), weights[m].to_numpy()
    mean = float(np.average(vals, weights=wts))
    variance = float(np.average((vals - mean) ** 2, weights=wts))
    n_eff = (wts.sum() ** 2) / (wts**2).sum()
    se = np.sqrt(variance / n_eff)
    return mean - 1.96 * se, mean + 1.96 * se


def main() -> None:
    df, meta = load()
    lab = labels(meta, "NEV_08")
    df["DOSE"] = df["NEV_08"].map(DOSE_MAP)
    df = df.dropna(subset=["DOSE"]).copy()
    df["DOSE"] = df["DOSE"].astype(int)

    print("== 原始加权表（dose：1=Everyday … 6=Never used fast charging）==")
    raw = []
    for dose in sorted(df["DOSE"].unique()):
        sub = df[df["DOSE"] == dose]
        w = sub[WEIGHT].fillna(1.0)
        mean = float(np.average(sub["APEAL_Index"], weights=w))
        lo, hi = weighted_ci(sub["APEAL_Index"], w)
        raw.append({"dose": dose, "n": int(len(sub)), "mean": round(mean, 1), "ci_lo": round(lo, 1), "ci_hi": round(hi, 1),
                    "label": lab.get(float([k for k, v in DOSE_MAP.items() if v == dose][0]), "")})
        print(f"  dose{dose} {lab.get(float([k for k, v in DOSE_MAP.items() if v == dose][0]), ''):<30} n={len(sub):>5}  mean={mean:6.1f}  CI=({lo:6.1f},{hi:6.1f})")
    means = [r["mean"] for r in raw]
    adjacent = []
    prev = None
    for r in raw:
        if prev is not None:
            adjacent.append((f"dose{prev['dose']}", f"dose{r['dose']}", round(r["mean"] - prev["mean"], 1)))
        prev = r
    print("  adjacent deltas:", adjacent)
    sign_changes = sum(1 for i in range(1, len(adjacent)) if (adjacent[i][2] > 0) != (adjacent[0][2] > 0) and adjacent[i][2] != 0 and adjacent[0][2] != 0)
    print(f"  raw monotonic(direction changes): {sign_changes}")

    t = " + ".join(terms(meta, CONTROLS))
    fit = smf.ols(f"APEAL_Index ~ C(DOSE) + {t}", data=df).fit()
    print("\n== 控制后各剂量 contrast（ref = dose1 Everyday）==")
    for term in fit.params.index:
        if "C(DOSE)" in term:
            dose = term.split("[T.")[-1].rstrip("]")
            lo, hi = fit.conf_int().loc[term]
            print(f"  dose{dose}: coef={fit.params[term]:+.2f}  (95%CI {lo:+.2f},{hi:+.2f})  p={fit.pvalues[term]:.4f}")

    fitlin = smf.ols(f"APEAL_Index ~ DOSE + {t}", data=df).fit()
    slope, sp = fitlin.params["DOSE"], fitlin.pvalues["DOSE"]
    print(f"\n== 线性趋势检验（ordinal dose 作为连续得分，含全部控制）==")
    print(f"  slope = {slope:+.3f} APEAL/dose-unit, p = {sp:.6f}  → {'单调趋势成立' if slope>0 and sp<0.05 else '不成立'}")

    from scipy import stats as _stats
    rss_lin = float(((fitlin.resid) ** 2).sum())
    rss_dum = float(((fit.resid) ** 2).sum())
    df_diff = fit.df_model - fitlin.df_model
    df_res = fit.df_resid
    f_stat = ((rss_lin - rss_dum) / df_diff) / (rss_dum / df_res)
    f_p = float(_stats.f.sf(f_stat, df_diff, df_res))
    print(f"  偏离线性（nested F）：F={f_stat:.2f} p={f_p:.4f}  → {'非线性显著' if f_p<0.05 else '线性单调可接受'}")

    fit4 = smf.ols(f"APEAL_Index ~ C(DOSE, Treatment(reference=4)) + {t}", data=df).fit()
    term5 = [k for k in fit4.params.index if "C(DOSE" in k and "[T.5" in k][0]
    print(f"\n== 反转检验：dose5(≤1次/月) vs dose4(2-3次/月) ==")
    print(f"  coef={fit4.params[term5]:+.2f} p={fit4.pvalues[term5]:.4f}  → {'反转显著' if fit4.pvalues[term5]<0.05 else '反转不显著（视为噪声/平台期）'}")

    print("\n== dose-response 判定 ==")
    top = max(raw, key=lambda r: r["mean"])
    bottom = min(raw, key=lambda r: r["mean"])
    print(f"  range: {bottom['mean']} → {top['mean']}（dose{bottom['dose']} vs dose{top['dose']}，Δ{top['mean']-bottom['mean']:+.1f}）")
    if slope > 0 and sp < 0.05 and fit4.pvalues[term5] >= 0.05:
        print("  H-002 结论：单调 dose-response（Never→Everyday 体验逐级上升），线性趋势显著，dose4→5 反转不显著。")
    else:
        print("  H-002 结论：dose-response 非严格单调或反转显著，需标注。")


if __name__ == "__main__":
    main()