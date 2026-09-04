"""Topic verification: 高阶座椅功能对驾驶感受/舒适度的关联。

声明待验证：
  1. 高阶座椅功能配备对驾驶感受有显著影响
  2. 其中驾驶座电动记忆、后排通风/冷却的影响最为明显
  3. 后排座椅电动记忆功能对舒适度提升轻微

口径：
  - 配置（二分类 has=1 / not=0）：
      driver_memory  SCR_SEAT00_04C_R1  驾驶座电动记忆
      rear_memory    SCR_SEAT00_04C_R3  后排电动记忆  (n=91, 极稀疏)
      driver_vent    SCR_SEAT00_04B_R1  驾驶座通风/冷却
      rear_vent      SCR_SEAT00_04B_R3  后排通风/冷却
      driver_heat    SCR_SEAT00_04A_R1  驾驶座加热
      rear_heat      SCR_SEAT00_04A_R3  后排加热
      driver_massage SCR_SEAT00_04D_R1  驾驶座按摩
      rear_massage   SCR_SEAT00_04D_R3  后排按摩
  - 结果：ADRV_Index(驾驶感受), ACMFT_Index(驾乘舒适), APEAL_Index,
           ADRV_R_05(总体驾驶感受), ACMFT_R_05(总体舒适), ACMFT_R_02(后排舒适)
  - 控制：价格 CN_YNV_07 + MAKE_DP + PREMMAKE_DP + SUPER_SEGMENT_DP + Region_DP
          + CITY_TIER_DP + AGE_BUCKETS + CN_INCOME + CN_EDUCATION
分析：
  1. raw 加权均值差
  2. 控制后 OLS (HC1)
  3. 品牌×价格带 cell 匹配（同 config_match L3）
  4. 全配置×结果 BH-FDR 校正
  5. 重点断言：driver_memory→ADRV, rear_vent→ADRV, rear_memory→ACMFT
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf  # type: ignore[import-not-found]

from analysis._common import load, WEIGHT

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "premium_seat_driving.json"

CONFIGS = {
    "driver_memory": ("SCR_SEAT00_04C_R1", "驾驶座电动记忆"),
    "rear_memory": ("SCR_SEAT00_04C_R3", "后排电动记忆"),
    "driver_vent": ("SCR_SEAT00_04B_R1", "驾驶座通风/冷却"),
    "rear_vent": ("SCR_SEAT00_04B_R3", "后排通风/冷却"),
    "driver_heat": ("SCR_SEAT00_04A_R1", "驾驶座加热"),
    "rear_heat": ("SCR_SEAT00_04A_R3", "后排加热"),
    "driver_massage": ("SCR_SEAT00_04D_R1", "驾驶座按摩"),
    "rear_massage": ("SCR_SEAT00_04D_R3", "后排按摩"),
}
OUTCOMES = {
    "ADRV_Index": "驾驶感受",
    "ACMFT_Index": "驾乘舒适",
    "APEAL_Index": "总体魅力",
    "ADRV_R_05": "总体驾驶感受(item)",
    "ACMFT_R_05": "总体舒适(item)",
    "ACMFT_R_02": "后排舒适(item)",
}
CONTROLS = [
    "CN_YNV_07", "MAKE_DP", "PREMMAKE_DP", "SUPER_SEGMENT_DP",
    "Region_DP", "CITY_TIER_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION",
]


def clean99(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = out[c].replace(99.0, np.nan)
    return out


def raw_gap(df: pd.DataFrame, config: str, outcome: str) -> dict:
    d = clean99(df, [outcome])
    has = d[d[config] == 1]
    no = d[d[config] == 0]
    a = has[outcome].dropna()  # type: ignore
    b = no[outcome].dropna()  # type: ignore
    m_h = np.average(a, weights=has.loc[a.index, WEIGHT].fillna(1.0))  # type: ignore
    m_n = np.average(b, weights=no.loc[b.index, WEIGHT].fillna(1.0))  # type: ignore
    pooled = np.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2)
    d_cohen = (np.mean(a) - np.mean(b)) / pooled if pooled else 0.0
    return {
        "config": config, "outcome": outcome,
        "n_has": int(len(has)), "n_not": int(len(no)),
        "wmean_has": round(float(m_h), 2), "wmean_not": round(float(m_n), 2),
        "delta": round(float(m_h - m_n), 2), "cohens_d": round(float(d_cohen), 3),
    }
    pooled = np.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2)
    d = (np.mean(a) - np.mean(b)) / pooled if pooled else 0.0
    return {
        "config": config, "outcome": outcome,
        "n_has": int(len(has)), "n_not": int(len(no)),
        "wmean_has": round(float(m_h), 2), "wmean_not": round(float(m_n), 2),
        "delta": round(float(m_h - m_n), 2), "cohens_d": round(float(d), 3),
    }


def controlled(df: pd.DataFrame, config: str, outcome: str, controls: list[str]) -> dict:
    d = clean99(df, [outcome])
    cols = [outcome, config, *controls, WEIGHT]
    d = pd.DataFrame(d[cols]).copy()  # type: ignore
    d = d[d[config].isin([0.0, 1.0])]  # type: ignore
    d = d.dropna(subset=cols)  # type: ignore
    d["WT"] = d[WEIGHT].fillna(1.0)  # type: ignore
    formula = f"{outcome} ~ {config} + " + " + ".join(f"C({c})" if c != "CN_YNV_07" else c for c in controls)
    fit = smf.wls(formula, data=d, weights=d["WT"]).fit(cov_type="HC1")
    return {
        "config": config, "outcome": outcome,
        "estimator": "WLS(weights=APEAL_WT)",
        "n": int(fit.nobs),  # type: ignore
        "coef": round(float(fit.params[config]), 4),  # type: ignore
        "se": round(float(fit.bse[config]), 4),  # type: ignore
        "p": float(fit.pvalues[config]),  # type: ignore
    }


def matched(df: pd.DataFrame, config: str, outcome: str, min_cell: int = 30) -> dict:
    d = clean99(df, [outcome])
    d = d[d[config].isin([0.0, 1.0])].copy()
    cell = pd.Series([""] * len(d), index=d.index, dtype=object)
    for col in ["MAKE_DP", "CN_YNV_07"]:
        if col == "CN_YNV_07":
            band = pd.qcut(d[col], 4, labels=False, duplicates="drop")  # type: ignore
            part = band.fillna(-1).astype(int).astype(str)  # type: ignore
        else:
            part = d[col].fillna(-1).astype(int).astype(str)  # type: ignore
        cell = cell + part
    d = d.assign(_cell=cell)
    deltas = []
    for _, g in d.groupby("_cell"):
        has, no = g[g[config] == 1], g[g[config] == 0]
        if len(has) < min_cell or len(no) < min_cell:
            continue
        ha = has[outcome].dropna()  # type: ignore
        na = no[outcome].dropna()  # type: ignore
        m_h = np.average(ha, weights=has.loc[ha.index, WEIGHT].fillna(1.0))  # type: ignore
        m_n = np.average(na, weights=no.loc[na.index, WEIGHT].fillna(1.0))  # type: ignore
        deltas.append(m_h - m_n)
    if not deltas:
        return {"config": config, "outcome": outcome, "n_cells": 0, "note": "无足够 cell"}
    consistent = sum(1 for x in deltas if x > 0) / len(deltas)
    return {
        "config": config, "outcome": outcome,
        "n_cells": len(deltas),
        "mean_cell_delta": round(float(np.mean(deltas)), 2),
        "consistent_pct": round(consistent * 100, 1),
    }


def bh_fdr(items: list[dict]) -> list[dict]:
    ps = [(i, float(x["p"])) for i, x in enumerate(items) if x.get("p") is not None]
    ps.sort(key=lambda t: t[1])
    m = len(ps)
    for rank, (i, p) in enumerate(ps, start=1):
        items[i]["q"] = round(float(p * m / rank), 4)
    return items


def main() -> None:
    df, _ = load()
    raw_all, ctrl_all, match_all = [], [], []
    for key, (col, label) in CONFIGS.items():
        for ok, ol in OUTCOMES.items():
            raw_all.append(raw_gap(df, col, ok))
            ctrl_all.append(controlled(df, col, ok, CONTROLS))
            match_all.append(matched(df, col, ok))
    ctrl_all = bh_fdr(ctrl_all)

    # 重点断言
    key_assertions = {}
    for name, (config, outcome) in {
        "驾驶座记忆→驾驶感受": ("SCR_SEAT00_04C_R1", "ADRV_Index"),
        "后排通风→驾驶感受": ("SCR_SEAT00_04B_R3", "ADRV_Index"),
        "后排记忆→驾乘舒适": ("SCR_SEAT00_04C_R3", "ACMFT_Index"),
    }.items():
        key_assertions[name] = {
            "raw": next(x for x in raw_all if x["config"] == config and x["outcome"] == outcome),
            "controlled": next(x for x in ctrl_all if x["config"] == config and x["outcome"] == outcome),
            "matched": next(x for x in match_all if x["config"] == config and x["outcome"] == outcome),
        }

    payload = {
        "analysis": "premium_seat_driving",
        "data_source": "data/source.sav",
        "weight": WEIGHT,
        "definition": "高阶座椅配置 has-vs-not；结果=驾驶感受/舒适/总体魅力及 item；控制=价格+品牌+品牌层级+细分+区域+城市+年龄+收入+教育；受控模型=WLS(weights=APEAL_WT, HC1)",
        "n": int(len(df)),
        "raw_gaps": raw_all,
        "controlled_bh_fdr": ctrl_all,
        "matched": match_all,
        "key_assertions": key_assertions,
        "limitation": "rear_memory(后排电动记忆) n=91 极稀疏，匹配 cell 覆盖有限，结论需谨慎；横截面观察性关联，非因果。",
        "boundary": "高阶座椅配置与高端车型结构高度相关，控制品牌/价格后效应收缩即说明为伴随特征而非独立产品价值。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
