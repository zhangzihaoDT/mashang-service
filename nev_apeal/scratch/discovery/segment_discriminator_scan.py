"""Controlled segment-discriminator scanner.

Rather than testing every exposure against every segment, this scanner uses a
small registered queue and compares a pre-specified exposure contrast inside
each segment. It is a candidate generator, not the final interaction test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf

from analysis._common import WEIGHT, load

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "scratch" / "discovery" / "_signals_segment_discriminator.json"
CONTROLS = ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION"]
REGISTERED = [
    # (exposure, moderator, label, moderator label, low/high contrast)
    ("NEV_08", "SEGMENT_DP", "快充频率", "车型结构段", (1.0, 99.0)),
    ("AFUEL_D_06", "SEGMENT_DP", "续航预期违背", "车型结构段", (1.0, 3.0)),
    ("ACHAR_D_05", "SEGMENT_DP", "充电时长预期违背", "车型结构段", (1.0, 3.0)),
]


def scan_pair(df: pd.DataFrame, exposure: str, moderator: str, exposure_label: str, moderator_label: str, contrast: tuple[float, float]) -> dict | None:
    cols = [exposure, moderator, "APEAL_Index", WEIGHT, *CONTROLS]
    d = df[cols].dropna().copy()
    d = d[d[exposure].isin(contrast)].copy()
    rows = []
    for segment, g in d.groupby(moderator):
        subset = g[g[exposure].isin(contrast)].copy()
        if len(subset) < 50 or subset[exposure].nunique() < 2:
            continue
        fit = smf.wls(
            "APEAL_Index ~ C(" + exposure + ") + " + " + ".join(c for c in CONTROLS if c != moderator),
            data=subset,
            weights=subset[WEIGHT].fillna(1.0),
        ).fit(cov_type="HC1")
        term = next((name for name in fit.params.index if name.startswith(f"C({exposure})[T.{contrast[1]:g}")), None)
        if term is None:
            continue
        rows.append({"moderator_value": str(segment), "n": int(fit.nobs), "coef_better_vs_worse": round(float(fit.params[term]), 2), "p": round(float(fit.pvalues[term]), 6)})
    if len(rows) < 3:
        return None
    spread = max(row["coef_better_vs_worse"] for row in rows) - min(row["coef_better_vs_worse"] for row in rows)
    return {
        "signal_id": f"segment_discriminator_{exposure.lower()}_{moderator.lower()}",
        "analysis_type": "segment_discriminator",
        "exposure": exposure,
        "moderator": moderator,
        "outcome": "APEAL_Index",
        "effect_size": {"within_segment_spread": round(spread, 2), "unit": "APEAL points"},
        "sample_support": {"n": int(sum(row["n"] for row in rows)), "segments": len(rows), "coverage": "SEGMENT_QUEUE"},
        "stability": "moderate",
        "novelty": 3,
        "interpretation": f"{exposure_label}在不同{moderator_label}内的效应幅度存在候选差异，需后续正式 interaction 验证。",
        "controls": [c for c in CONTROLS if c != moderator],
        "direction": f"within-segment {contrast[1]:g} vs {contrast[0]:g} contrast",
        "coverage": "SEGMENT_QUEUE",
        "caveats": "分段筛选使用预注册组合；小段剔除；本轮不将筛选结果解释为正式交互因果效应。",
        "segments": rows,
    }


def main() -> None:
    df, _ = load()
    signals = []
    for exposure, moderator, exposure_label, moderator_label, contrast in REGISTERED:
        signal = scan_pair(df, exposure, moderator, exposure_label, moderator_label, contrast)
        if signal:
            signals.append(signal)
    OUT.write_text(json.dumps(signals, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(signals, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
