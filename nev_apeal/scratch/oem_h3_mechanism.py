"""T8 OEM Experience Gap — H3 Mechanism decomposition: after structural controls, do the
residual gaps concentrate on specific modules/items (engineering shortfalls) or spread
uniformly (brand halo)?

E-002/003/004 showed raw item gaps concentrate on front-seat driving/NVH; E-005 showed
controlled module gaps are uniform. Here test ITEM-level uniformity under full controls.
"""

from __future__ import annotations

import statsmodels.formula.api as smf

from analysis._common import load, weighted_mean

# ORIGIN3_DP: 1=Domestic Traditional (ref) 2=International 3=Domestic Startup 4=Domestic Affiliated
FULL = ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "SEGMENT_DP"]
MODULES = {
    "AEXT": "外观", "AINT": "座舱内装", "ACMFT": "舒适", "ADRV": "驾驶感受",
    "APERF": "性能", "ASFTY": "安全", "AFUEL": "补能续航", "ACHAR": "补能充电",
    "AINFO": "智能座舱", "ASET": "设置启动", "AENT": "进出便利", "ABRAND": "品牌",
}


def terms(meta, predictors):
    return [f"C({p})" if meta.variable_value_labels.get(p) else p for p in predictors]


def main():
    df, meta = load()
    df["ORIGIN3_DP"] = df["ORIGIN3_DP"].astype(int)
    keep = ["APEAL_Index", "ORIGIN3_DP"] + FULL
    df = df.dropna(subset=keep).copy()
    t = " + ".join(terms(meta, FULL))
    print(f"analytic sample n = {len(df)}\n")

    print("== 受控模块 gap（国际 vs 传统国产，完整控制）==")
    results = {}
    for prefix, name in MODULES.items():
        mod = prefix + "_Index"
        if mod not in df.columns:
            mod = prefix + "_index"
        if mod not in df.columns:
            continue
        fit = smf.ols(f"{mod} ~ C(ORIGIN3_DP) + {t}", data=df).fit()
        k = next((k for k in fit.params.index if k.startswith("C(ORIGIN3_DP)[T.2")), None)
        if k is None:
            continue
        results[prefix] = (name, fit.params[k], fit.pvalues[k], int(fit.nobs))
        print(f"  {name:<6} {mod:<16} 国际={fit.params[k]:+.2f} p={fit.pvalues[k]:.4f}")

    print("\n== 驾驶/舒适/性能 item 受控 gap（国际 vs 传统国产；检验原始'前排/NVH集中'是否存活于结构控制）==")
    item_prefixes = ["ADRV", "APERF", "ACMFT"]
    for prefix in item_prefixes:
        base = prefix + "_R_"
        cols = [c for c in df.columns if c.startswith(base) and c[len(base):].isdigit()]
        for col in sorted(cols):
            fit = smf.ols(f"{col} ~ C(ORIGIN3_DP) + {t}", data=df).fit()
            k = next((k for k in fit.params.index if k.startswith("C(ORIGIN3_DP)[T.2")), None)
            if k is None:
                continue
            print(f"  {col}: 国际={fit.params[k]:+.3f} p={fit.pvalues[k]:.4f}")

    print("\n== 原始（未控制）item gap 对照（同一样本）==")
    for prefix in item_prefixes:
        base = prefix + "_R_"
        cols = [c for c in df.columns if c.startswith(base) and c[len(base):].isdigit()]
        df2 = df[df["ORIGIN3_DP"].isin([1, 2])]
        for col in sorted(cols):
            m1 = weighted_mean(df2[df2["ORIGIN3_DP"] == 1][col], df2[df2["ORIGIN3_DP"] == 1]["APEAL_WT"].fillna(1.0))
            m2 = weighted_mean(df2[df2["ORIGIN3_DP"] == 2][col], df2[df2["ORIGIN3_DP"] == 2]["APEAL_WT"].fillna(1.0))
            print(f"  {col}: 国际−传统 raw {m2 - m1:+.3f}")


if __name__ == "__main__":
    main()