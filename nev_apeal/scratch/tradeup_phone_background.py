"""Topic verification: 换购用户是否更倾向选择手机厂商背景车企。

操作定义：
  - 手机厂商背景车企 = MAKE_DP in {69512 (AITO/问界, 华为), 69211 (AVATR/阿维塔, 华为生态)}
  - 数据中无小米品牌（Xiaomi），作为 coverage limitation 记录。
  - 换购 = YPV_01 == 1.0（替换另一辆车）；增购 = 2.0；首购 = 3.0（参照组）。
分析：
  - 加权组占比 + 卡方独立性
  - 换购 vs 首购 logistic（Firth/标准）控制 价格/品牌层级/能源/区域/城市/年龄/收入/教育/世代
  - 敏感性：分别只看 AITO 与 AVATR
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf  # type: ignore[import-not-found]

from analysis._common import load, WEIGHT

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "tradeup_phone_background.json"

PHONE_MAKES = {69512.0, 69211.0}  # AITO, AVATR
# 注意：SCR_FUEL_TYPE 与手机背景完全共线（AITO 全为 PHEV/REEV，AVATR 全为 BEV），
# 从控制集移除以免奇异矩阵；GENERATION 与 AGE_BUCKETS 高度相关(r=-0.776)，只保留 AGE_BUCKETS。
CONTROLS = [
    "CN_YNV_07",
    "PREMMAKE_DP",
    "Region_DP",
    "CITY_TIER_DP",
    "AGE_BUCKETS",
    "CN_INCOME",
    "CN_EDUCATION",
]


def weighted_share(df: pd.DataFrame) -> list[dict]:
    rows = []
    for mission in [1.0, 2.0, 3.0]:
        sub = df[df["YPV_01"] == mission]
        if len(sub) == 0:
            continue
        w = sub[WEIGHT].fillna(1.0)  # type: ignore
        rows.append({
            "mission": mission,
            "label": {1.0: "换购(替换)", 2.0: "增购", 3.0: "首购"}[mission],
            "n": int(len(sub)),  # type: ignore
            "n_phone": int(sub["phone_backed"].sum()),  # type: ignore
            "raw_pct": round(float(sub["phone_backed"].mean()) * 100, 2),  # type: ignore
            "weighted_pct": round(float(np.average(sub["phone_backed"], weights=w)) * 100, 2),  # type: ignore
        })
    return rows


def chisq(df: pd.DataFrame) -> dict | None:
    import scipy.stats as stats  # type: ignore[import-not-found]
    table = pd.crosstab(df["YPV_01"], df["phone_backed"])  # type: ignore
    chi2, p, dof, _ = stats.chi2_contingency(table)
    return {"chi2": round(float(chi2), 3), "p": float(p), "dof": int(dof)}


def _fit_logit(d: pd.DataFrame, outcome: str, controls: list[str]):
    formula = f"{outcome} ~ C(YPV_C) + " + " + ".join(f"C({c})" if c != "CN_YNV_07" else c for c in controls)
    return smf.logit(formula, data=d).fit(disp=False)


def logistic(df: pd.DataFrame, outcome: str, controls: list[str]) -> dict:
    cols = [outcome, "YPV_01", *controls]
    d: pd.DataFrame = pd.DataFrame(df[cols]).copy()  # type: ignore
    d = d[d["YPV_01"].isin([1.0, 2.0, 3.0])]  # type: ignore
    d = d.dropna(subset=cols)  # type: ignore
    d["YPV_C"] = pd.Categorical(d["YPV_01"], categories=[3.0, 1.0, 2.0])

    # rare-outcome / sparse-cell 时逐级降级控制集，避免奇异矩阵与分离
    control_tiers = [
        controls,
        ["CN_YNV_07", "PREMMAKE_DP", "Region_DP", "AGE_BUCKETS"],
        ["CN_YNV_07", "PREMMAKE_DP", "Region_DP"],
        ["CN_YNV_07"],
        [],
    ]
    fit, used = None, None
    for tier in control_tiers:
        try:
            fit = _fit_logit(d, outcome, tier)
            used = tier
            break
        except Exception:
            continue
    if fit is None:
        return {"outcome": outcome, "error": "no converged model", "effects": {}}

    terms = {
        "换购(替换) vs 首购": "C(YPV_C)[T.1.0]",
        "增购 vs 首购": "C(YPV_C)[T.2.0]",
    }
    effects = {}
    for label, term in terms.items():
        if term not in fit.params.index:
            continue
        effects[label] = {
            "coef": round(float(fit.params[term]), 4),
            "or": round(float(np.exp(fit.params[term])), 3),
            "p": float(fit.pvalues[term]),
            "ci95": [round(float(np.exp(fit.conf_int().loc[term][0])), 3),
                     round(float(np.exp(fit.conf_int().loc[term][1])), 3)],
        }
    return {
        "outcome": outcome,
        "n": int(fit.nobs),  # type: ignore
        "pseudo_r2": round(float(fit.prsquared), 4),  # type: ignore
        "n_positive": int(d[outcome].sum()),  # type: ignore
        "control_level": "full" if used == controls else f"reduced({len(used)})",  # type: ignore
        "controls_used": used,
        "effects": effects,
    }


def main() -> None:
    df, _ = load()
    df = df.assign(
        phone_backed=(df["MAKE_DP"].isin(list(PHONE_MAKES))).astype(int),  # type: ignore
        aito=(df["MAKE_DP"] == 69512.0).astype(int),
        avatar=(df["MAKE_DP"] == 69211.0).astype(int),
    )
    payload = {
        "analysis": "tradeup_phone_background",
        "data_source": "data/source.sav",
        "weight": WEIGHT,
        "definition": "手机厂商背景车企 = AITO(问界, 华为) + AVATR(阿维塔, 华为生态)；数据无小米品牌",
        "shares": weighted_share(df),
        "chisq": chisq(df),
        "logistic_main": logistic(df, "phone_backed", CONTROLS),
        "sensitivity": {
            "aito_only": logistic(df, "aito", CONTROLS),
            "avatar_only": logistic(df, "avatar", CONTROLS),
        },
        "boundary": "手机背景车企样本较少(n=325)；选择行为为观察性关联，非品牌选择因果关系。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
