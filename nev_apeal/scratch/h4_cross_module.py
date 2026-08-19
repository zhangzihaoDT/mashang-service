"""H4 Cross-module discriminator — is the NEV08 gap charging-specific or spread across all modules?

If only charging modules (ACHAR/AFUEL) carry a large gap -> charging-experience mechanism.
If ALL modules carry comparable gaps -> NEV08 is a lifestyle / usage-intensity proxy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from analysis._common import load, WEIGHT

DOSE_MAP = {1.0: 1, 2.0: 2, 3.0: 3, 4.0: 4, 5.0: 5, 99.0: 6}
FULL = ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION"]
MODULES = [
    ("AEXT_Index", "外观"),
    ("AINT_Index", "座舱内装"),
    ("ACMFT_Index", "舒适"),
    ("ADRV_Index", "驾驶感受"),
    ("APERF_Index", "性能"),
    ("ASFTY_Index", "安全"),
    ("AFUEL_Index", "补能·续航"),
    ("ACHAR_index", "补能·充电"),
    ("AINFO_Index", "智能座舱"),
    ("ASET_Index", "设置启动"),
    ("AENT_Index", "进出便利"),
    ("APEAL_Index", "总体"),
]


def terms(meta, predictors):
    return [f"C({p})" if meta.variable_value_labels.get(p) else p for p in predictors]


def wmean(s, w):
    m = s.notna() & w.notna()
    return float(np.average(s[m], weights=w[m])) if m.any() else float("nan")


def main():
    df, meta = load()
    df["DOSE"] = df["NEV_08"].map(DOSE_MAP)
    df = df.dropna(subset=["DOSE"]).copy()
    df["DOSE"] = df["DOSE"].astype(int)
    df["CLUSTER"] = df["DOSE"].map({1: "L", 2: "L", 3: "M", 4: "M", 5: "M", 6: "H"})
    w = df[WEIGHT].fillna(1.0)
    t = " + ".join(terms(meta, FULL))

    print(f"  {'module':<16}{'raw_N-D':>9}{'ctrl_N-D':>10}{'p':>8}{'H-L':>8}  备注")
    out = []
    for col, name in MODULES:
        raw = wmean(df.loc[df["DOSE"] == 6, col], w[df["DOSE"] == 6]) - wmean(df.loc[df["DOSE"] == 1, col], w[df["DOSE"] == 1])
        hl = wmean(df.loc[df["CLUSTER"] == "H", col], w[df["CLUSTER"] == "H"]) - wmean(df.loc[df["CLUSTER"] == "L", col], w[df["CLUSTER"] == "L"])
        fit = smf.ols(f"{col} ~ C(DOSE) + {t}", data=df).fit()
        k = next(k for k in fit.params.index if "C(DOSE)" in k and "[T.6" in k)
        c, p = fit.params[k], fit.pvalues[k]
        out.append((name, col, raw, c, p, hl))
    out.sort(key=lambda r: r[4])
    for name, col, raw, c, p, hl in out:
        tag = " ← 补能" if col in ("ACHAR_index", "AFUEL_Index") else ""
        print(f"  {name:<16}{raw:>+9.1f}{c:>+10.1f}{p:>8.4f}{hl:>+8.1f}{tag}")

    maxp = max(r[4] for r in out)
    print("\n== 判别 ==")
    big = [(n, c, p) for n, _, _, c, p, _ in out if abs(c) >= 20 and p < 0.05]
    print(f"  控制后 |gap|>=20 且 p<0.05 的模块数：{len(big)}/12")
    for n, c, p in big:
        print(f"    {n}: {c:+.1f} (p={p:.4f})")
    charging = [b for b in big if b[0] in ("补能·充电", "补能·续航")]
    others = [b for b in big if b[0] not in ("补能·充电", "补能·续航")]
    print(f"  其中补能模块 {len(charging)} 个、非补能模块 {len(others)} 个")
    if others and max(o[2] for o in others) < 0.05:
        print("  → 差异不止补能，跨模块普遍存在：NEV08 更像生活方式/使用强度 proxy（H-004 拒绝）")
    else:
        print("  → 差异集中于补能模块：补能体验机制更可信（H-004 支持）")


if __name__ == "__main__":
    main()