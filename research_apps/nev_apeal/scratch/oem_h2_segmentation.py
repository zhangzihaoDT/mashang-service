"""T8 OEM Experience Gap — H2 Segmentation: is the international premium concentrated
in premium segments / high price bands, or broad?

E-007 stratified cells had insufficient power. Problem: SEGMENT×ORIGIN interaction is
not identifiable (premium segments are almost exclusively international; most mass-market
segments are almost exclusively traditional). Use price-band interaction (more overlap)
+ controlled within-segment contrasts where both origins exist.
"""

from __future__ import annotations

import numpy as np
import statsmodels.formula.api as smf

from analysis._common import load, weighted_mean

# ORIGIN3_DP: 1=Domestic Traditional (ref) 2=International 3=Domestic Startup 4=Domestic Affiliated
STRUCT = ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP"]


def band(price):
    if price < 100000:
        return "lt10"
    if price < 150000:
        return "1015"
    if price < 200000:
        return "1520"
    if price < 300000:
        return "2030"
    return "30p"


def terms(meta, predictors):
    return [f"C({p})" if meta.variable_value_labels.get(p) else p for p in predictors]


def main():
    df, meta = load()
    df["ORIGIN3_DP"] = df["ORIGIN3_DP"].astype(int)
    df = df[df["CN_YNV_07"].notna()].copy()
    df["PRICE_BAND"] = df["CN_YNV_07"].map(band)
    keep = ["APEAL_Index", "ORIGIN3_DP", "PRICE_BAND"] + STRUCT
    df = df.dropna(subset=keep).copy()
    print(f"analytic sample n = {len(df)}\n")

    # --- price band interaction (pooled variance, no 7-stratum power loss) ---
    formula2 = ("APEAL_Index ~ C(ORIGIN3_DP)*C(PRICE_BAND) + "
                + " + ".join(terms(meta, [c for c in STRUCT if c != "CN_YNV_07"])))
    fit2 = smf.ols(formula2, data=df).fit()
    print("价格带 × ORIGIN 交互（vs 传统国产×该带），控制 SUPER_SEGMENT+PREMMAKE：")
    base = fit2.params.get("C(ORIGIN3_DP)[T.2.0]", float("nan"))
    print(f"  价格带ref 国际主效应: +{base:.2f} p={fit2.pvalues.get('C(ORIGIN3_DP)[T.2.0]', float('nan')):.4f}")
    for k in fit2.params.index:
        if "C(ORIGIN3_DP)" in k and "C(PRICE_BAND)" in k:
            tag = k.replace("C(ORIGIN3_DP)[T.", "o").replace("]:C(PRICE_BAND)[T.", " x price ").replace("]", "")
            print(f"  {tag}: {fit2.params[k]:+.2f} p={fit2.pvalues[k]:.4f}")
    # joint interaction F-test
    int_terms = [k for k in fit2.params.index if "C(PRICE_BAND)" in k and "C(ORIGIN3_DP)" in k]
    if int_terms:
        from statsmodels.stats.anova import anova_lm
        reduced = smf.ols("APEAL_Index ~ C(ORIGIN3_DP) + C(PRICE_BAND) + " + " + ".join(terms(meta, [c for c in STRUCT if c != "CN_YNV_07"])), data=df).fit()
        print(f"\n  交互联合检验（含全部 ORIGIN×价格带）F={anova_lm(reduced, fit2).F.iloc[-1]:.2f} p={anova_lm(reduced, fit2)['Pr(>F)'].iloc[-1]:.4f}")

    # --- within-segment controlled contrast where both origins coexist (from E-007 cells) ---
    print("\n  两来源共存的细分内控制对比（raw 与结构控制，加权）：")
    df["SEGMENT_DP"] = df["SEGMENT_DP"].astype(int)
    for seg in sorted(df["SEGMENT_DP"].unique()):
        sub = df[df["SEGMENT_DP"] == seg]
        origins = sorted(set(sub["ORIGIN3_DP"]) & {1, 2})
        if len(origins) < 2:
            continue
        means = {}
        for origin in origins:
            o = sub[sub["ORIGIN3_DP"] == origin]
            means[origin] = (len(o), weighted_mean(o["APEAL_Index"], o["APEAL_WT"].fillna(1.0)))
        lbl = meta.variable_value_labels.get("SEGMENT_DP", {}).get(seg, str(seg))
        diff = means.get(2, (0, 0))[1] - means.get(1, (0, 0))[1]
        outs = " | ".join(f"origin{o} n={n} raw={m:.1f}" for o, (n, m) in means.items())
        print(f"  {lbl} (国际−传统 raw {'+%.1f' % diff}): " + outs)

    # --- controlled within-segment gap for coexistence segments ---
    print("\n  两来源共存细分的受控 gap（国际−传统，控制 SUPER_SEGMENT+PREMMAKE，段内子样本）：")
    for seg in sorted(df["SEGMENT_DP"].unique()):
        sub = df[df["SEGMENT_DP"] == seg]
        origins = sorted(set(sub["ORIGIN3_DP"]) & {1, 2})
        if len(origins) < 2:
            continue
        sub = sub[sub["ORIGIN3_DP"].isin([1, 2])].copy()
        ctrl = ["CN_YNV_07", "PREMMAKE_DP"]
        formula = "APEAL_Index ~ C(ORIGIN3_DP)"
        add = terms(meta, ctrl)
        if add:
            formula += " + " + " + ".join(add)
        try:
            fit = smf.ols(formula, data=sub).fit()
            k = next(k for k in fit.params.index if k.startswith("C(ORIGIN3_DP)[T.2"))
            lbl = meta.variable_value_labels.get("SEGMENT_DP", {}).get(seg, str(seg))
            print(f"  {lbl}: n={len(sub)} 国际={fit.params[k]:+.2f} p={fit.pvalues[k]:.4f}")
        except Exception as e:  # noqa: BLE001
            print(f"  seg {seg}: skipped ({e})")


if __name__ == "__main__":
    main()
