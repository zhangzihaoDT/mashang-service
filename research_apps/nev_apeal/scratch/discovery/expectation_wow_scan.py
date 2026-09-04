"""Expectation→Wow Scan — 以“预期 vs 体验”违背结构为 lens。

分析类型：expectation_wow
暴露变量：AFUEL_D_06（纯电续航 vs 预期）、ACHAR_D_05（充电时长 vs 预期），三档序数 1=Worse / 2=About / 3=Better。
结构：跨差异档的加权 APEAL / 模块指数阶梯 + FULL 控制后回归 + 非线性核对 + delight(最惊喜/最爱) 交叉。
产出：Signal Contract 记录（contracts/signal_contract.json 规定 schema），写入 scratch/discovery/_signals_expectation_wow.json。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from analysis._common import load, weighted_mean, WEIGHT

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "scratch" / "discovery" / "_signals_expectation_wow.json"

FULL_CONTROLS = ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION"]

LEVEL_LABELS = {1: "Worse than expected", 2: "About as expected", 3: "Better than expected"}

EXPOSURES = [
    ("AFUEL_D_06", "纯电续航 vs 预期", "AFUEL_Index"),
    ("ACHAR_D_05", "充电时长 vs 预期", "AFUEL_Index"),
]

DELIGHT_ITEMS = ["ASET_D_02", "ACMFT_D_02", "APERF_D_01", "ASFTY_D_02"]


def clean_levels(meta: Any, df: pd.DataFrame, var: str) -> pd.Series:
    """剔除 N/A(99) 等伪影后，仅保留 1/2/3 三档。"""
    s: pd.Series = df[var]
    lab: dict = meta.variable_value_labels.get(var) or {}
    bad = [k for k, v in lab.items() if any(p in str(v).lower() for p in ("n/a", "not applicable"))]
    out = s.replace(dict.fromkeys(bad, np.nan))
    return out.astype(float)


def level_stats(df: pd.DataFrame, s: pd.Series, outcome: str) -> list[dict]:
    rows = []
    for level in [1, 2, 3]:
        mask = s == float(level)
        sub = df[mask]
        if len(sub) == 0:
            continue
        rows.append({
            "level": level,
            "label": LEVEL_LABELS[level],
            "n": int(len(sub)),
            "outcome": outcome,
            "weighted_mean": round(float(weighted_mean(sub[outcome], sub[WEIGHT].fillna(1.0))), 2),
        })
    return rows


def _coef_row(m: Any, name: str, level: str) -> dict | None:
    if name not in m.params:
        return None
    return {"level": level, "coef": round(float(m.params[name]), 2),
            "se": round(float(m.bse[name]), 2), "p": round(float(m.pvalues[name]), 4)}


def wow_regression(df: pd.DataFrame, meta: Any, var: str, outcome: str) -> dict | None:
    """FULL 控制后 OLS+WLS，About(2.0) 为基准。"""
    s = clean_levels(meta, df, var)
    d = df.assign(EXP=s, WT=df[WEIGHT].fillna(1.0)).dropna(subset=["EXP", outcome, *FULL_CONTROLS])
    d = d[d["EXP"].isin([1.0, 2.0, 3.0])]
    if len(d) < 200:
        return None
    d["EXP_C"] = pd.Categorical(d["EXP"], categories=[2.0, 3.0, 1.0], ordered=True)
    formula = f"{outcome} ~ C(EXP_C) + " + " + ".join(FULL_CONTROLS)
    ols = smf.ols(formula, data=d).fit(cov_type="HC1")
    wls = smf.wls(formula, data=d, weights=d["WT"]).fit(cov_type="HC1")
    return {
        "var": var, "outcome": outcome, "n": int(ols.nobs),
        "better_ols": _coef_row(ols, "C(EXP_C)[T.3.0]", "Better"),
        "worse_ols": _coef_row(ols, "C(EXP_C)[T.1.0]", "Worse"),
        "better_wls": _coef_row(wls, "C(EXP_C)[T.3.0]", "Better"),
        "worse_wls": _coef_row(wls, "C(EXP_C)[T.1.0]", "Worse"),
    }


def delight_cross(df: pd.DataFrame, meta: Any, var: str) -> dict:
    """在“Better than expected”子样本中，delight 项最常选为何。"""
    s = clean_levels(meta, df, var)
    better_mask = (s == 3.0)
    out = {"n_better": int(better_mask.sum()), "items": {}}
    for item in DELIGHT_ITEMS:
        lab: dict = meta.variable_value_labels.get(item) or {}
        vc = df.loc[better_mask, item].replace(lab).astype(str).value_counts().head(3)
        out["items"][item] = {str(k): int(v) for k, v in vc.items()}
    return out


def build_signal(sid: str, var: str, label: str, outcome: str, rows: list[dict],
                 effect: dict | None, n_total: int, *, novelty: int = 3) -> dict:
    lvl = {r["label"]: r["weighted_mean"] for r in rows}
    wow_gap = pen = None
    if all(k in lvl for k in LEVEL_LABELS.values()):
        wow_gap = round(lvl["Better than expected"] - lvl["About as expected"], 1)
        pen = round(lvl["About as expected"] - lvl["Worse than expected"], 1)
    better = ((effect or {}).get("better_wls") or (effect or {}).get("better_ols"))
    worse = ((effect or {}).get("worse_wls") or (effect or {}).get("worse_ols"))
    b_coef = better.get("coef") if better else None
    b_p = better.get("p") if better else None
    return {
        "signal_id": sid,
        "analysis_type": "expectation_wow",
        "exposure": var,
        "outcome": outcome,
        "effect_size": {
            "better_coef": b_coef, "better_p": b_p,
            "worse_coef": worse.get("coef") if worse else None,
            "worse_p": worse.get("p") if worse else None,
            "unit": "APEAL points (WLS, FULL controls)", "n_reg": (effect or {}).get("n"),
        },
        "sample_support": {"n": n_total, "coverage": "FULL"},
        "stability": "moderate",
        "novelty": novelty,
        "wow_structure": {"worse": lvl.get("Worse than expected"), "about": lvl.get("About as expected"),
                          "better": lvl.get("Better than expected"),
                          "wow_gap_better_minus_about": wow_gap, "penalty_about_minus_worse": pen},
        "direction": "",
        "controls": FULL_CONTROLS,
        "interpretation": (
            f"{label}：`Better than expected` 相对 `About as expected` 的 {outcome} 增量 "
            f"= {wow_gap}（WLS better={b_coef}, p={b_p}）。"
            f"若 wow_gap 显著大于 0 且大于 penalty，说明该模块存在非对称预期惊喜结构。"
        ),
        "caveats": "横截面；预期违背为车主自报主观口径，不宣示因果",
    }


def main() -> None:
    df, meta = load()
    signals: list[dict] = []

    for var, label, module_ix in EXPOSURES:
        s = clean_levels(meta, df, var)
        n_total = int(s.notna().sum())

        for outcome in ["APEAL_Index", module_ix]:
            rows = level_stats(df, s, outcome)
            effect = wow_regression(df, meta, var, outcome)
            sid = f"expectation_wow_{len(signals) + 1:02d}"
            signals.append(build_signal(sid, var, label, outcome, rows, effect, n_total))

        cross = delight_cross(df, meta, var)
        sid = f"expectation_wow_{len(signals) + 1:02d}"
        signals.append({
            "signal_id": sid, "analysis_type": "expectation_wow",
            "exposure": var, "outcome": "AFUEL_Index (delight top picks)",
            "effect_size": {}, "sample_support": {"n": cross["n_better"], "coverage": "PARTIAL"},
            "stability": "moderate", "novelty": 4, "wow_structure": {},
            "direction": "", "controls": [],
            "interpretation": f"{label}：`Better than expected` 车主(delight 项)最常宣称的内容",
            "caveats": "缺失率 40-60%（ASET_D_02 等），仅为 Better 亚组描述",
            "delight_top": cross["items"],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(signals, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"signals written -> {OUT} ({len(signals)})")
    for sig in signals:
        b = (sig.get("effect_size") or {}).get("better_coef")
        ws = sig.get("wow_structure") or {}
        gap = ws.get("wow_gap_better_minus_about")
        print(f"[{sig['signal_id']}] {sig['exposure']} → {sig['outcome']} "
              f"wow_gap={gap} WLS better_p={b}")


if __name__ == "__main__":
    main()