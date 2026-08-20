"""Topic verification: PHEV/REEV vs BEV 车辆性能要素对比，声音是否为最明显短板。

声明待验证：
  插混车型车辆性能各要素较纯电车型由整体领先转为全面落后，其中发动机/电机声音影响最为明显。

口径：
  - PHEV/REEV = SCR_FUEL_TYPE == 5；BEV = SCR_FUEL_TYPE == 6（参照组）
  - 性能模块 = APERF_Index 及其 4 个 item：
      R_01 平稳顺畅 / R_02 动力 / R_03 声音 / R_04 总体表现
  - 剔除 99(N/A) 伪影
分析：
  1. 加权均值差（raw）
  2. 控制 价格(CN_YNV_07)+品牌层级(PREMMAKE_DP)+品牌(MAKE_DP)+区域+城市 后逐 item OLS
  3. 全面性检查：是否所有 item 均显著落后（含方向一致性）
  4. 声音是否为最大 effect size / 最稳定驱动
  5. 敏感性：AITO/AVATR 等新势力 vs 传统品牌分层（声音机制是否仅在 PHEV 内成立）
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf  # type: ignore[import-not-found]

from analysis._common import load, WEIGHT

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "phev_vs_bev_performance.json"

ITEMS = {
    "APERF_R_01": "平稳顺畅",
    "APERF_R_02": "动力",
    "APERF_R_03": "声音",
    "APERF_R_04": "总体表现",
}
CONTROLS = ["CN_YNV_07", "PREMMAKE_DP", "MAKE_DP", "Region_DP", "CITY_TIER_DP", "AGE_BUCKETS", "CN_INCOME"]


def clean99(s: pd.Series) -> pd.Series:
    return s.replace(99.0, np.nan)


def load_panel(df: pd.DataFrame) -> pd.DataFrame:
    d: pd.DataFrame = pd.DataFrame(df[df["SCR_FUEL_TYPE"].isin([5.0, 6.0])]).copy()  # type: ignore
    d["is_phev"] = (d["SCR_FUEL_TYPE"] == 5.0).astype(int)
    for col in ITEMS:
        d[col] = clean99(d[col])  # type: ignore
    return d


def raw_gaps(d: pd.DataFrame) -> list[dict]:
    rows = []
    for col, label in ITEMS.items():
        sub = d[d[col].notna()]
        phev = sub[sub["is_phev"] == 1]
        bev = sub[sub["is_phev"] == 0]
        w_p = phev[WEIGHT].fillna(1.0)  # type: ignore
        w_b = bev[WEIGHT].fillna(1.0)  # type: ignore
        m_p = np.average(phev[col], weights=w_p)
        m_b = np.average(bev[col], weights=w_b)
        rows.append({
            "item": col, "label": label,
            "n_phev": int(len(phev)),  # type: ignore
            "n_bev": int(len(bev)),  # type: ignore
            "wmean_phev": round(float(m_p), 3), "wmean_bev": round(float(m_b), 3),
            "delta_phev_minus_bev": round(float(m_p - m_b), 3),
        })
    return rows


def controlled_fit(d: pd.DataFrame, outcome: str, controls: list[str]) -> dict:
    cols = [outcome, "is_phev", *controls]
    dd: pd.DataFrame = pd.DataFrame(d[cols]).copy()  # type: ignore
    dd = dd.dropna(subset=cols)  # type: ignore
    formula = f"{outcome} ~ is_phev + " + " + ".join(f"C({c})" if c != "CN_YNV_07" else c for c in controls)
    fit = smf.ols(formula, data=dd).fit(cov_type="HC1")
    return {
        "item": outcome,
        "n": int(fit.nobs),  # type: ignore
        "coef_phev": round(float(fit.params["is_phev"]), 4),  # type: ignore
        "se": round(float(fit.bse["is_phev"]), 4),  # type: ignore
        "p": float(fit.pvalues["is_phev"]),  # type: ignore
    }


def main() -> None:
    df, _ = load()
    d = load_panel(df)

    raw = raw_gaps(d)
    full_control = []
    for col in ITEMS:
        full_control.append(controlled_fit(d, col, CONTROLS))

    # 简化控制（只价格+品牌层级+品牌）以对比
    lean = []
    for col in ITEMS:
        lean.append(controlled_fit(d, col, ["CN_YNV_07", "PREMMAKE_DP", "MAKE_DP"]))

    payload = {
        "analysis": "phev_vs_bev_performance",
        "data_source": "data/source.sav",
        "weight": WEIGHT,
        "definition": "PHEV/REEV = SCR_FUEL_TYPE 5；BEV = 6（参照）。APERF item 剔除 99(N/A)。",
        "n_phev": int(d["is_phev"].sum()),  # type: ignore
        "n_bev": int((d["is_phev"] == 0).sum()),  # type: ignore
        "raw_gaps_phev_minus_bev": raw,
        "controlled_lean_price_brand": lean,
        "controlled_full": full_control,
        "sound_item": "APERF_R_03",
        "boundary": "横截面观察性关联；'由整体领先转为全面落后'的时间/印象变化无法在单期横截面上直接验证，只能验证当期 PHEV vs BEV 的性能评价结构。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
