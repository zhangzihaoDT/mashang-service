"""Surprise / anomaly detector for research results.

Detects patterns an Agent should not gloss over:
  1. coefficient amplification   (adjusted effect > raw effect)
  2. sign reversal               (adjusted sign != raw sign)
  3. significance disappears     (raw p<.05, adjusted p>=.05)
  4. significance emerges        (raw p>=.05, adjusted p<.05)
  5. tiny effect but significant (p<.05 yet effect below business threshold)
"""

from __future__ import annotations

import argparse

from ._common import emit


def _severity(ratio: float) -> str:
    if ratio >= 2.0:
        return "high"
    if ratio >= 1.3:
        return "medium"
    return "low"


def detect(raw_effect: float, adjusted_effect: float, raw_p: float | None,
           adjusted_p: float | None, business_threshold: float) -> list[dict]:
    diagnostics = []
    if raw_effect == 0:
        return diagnostics
    ratio = adjusted_effect / raw_effect

    if raw_effect * adjusted_effect < 0:
        diagnostics.append({
            "type": "sign_reversal",
            "raw_effect": raw_effect,
            "adjusted_effect": adjusted_effect,
            "ratio": ratio,
            "severity": "high",
            "message": f"调整后效应符号反转（raw {raw_effect:+.2f} → adjusted {adjusted_effect:+.2f}），存在结构性混淆。",
        })
    elif abs(ratio) >= 1.2:
        diagnostics.append({
            "type": "coefficient_amplification",
            "raw_effect": raw_effect,
            "adjusted_effect": adjusted_effect,
            "ratio": round(ratio, 2),
            "severity": _severity(abs(ratio)),
            "message": f"控制后效应放大 {ratio:.2f}×（raw {raw_effect:+.2f} → adjusted {adjusted_effect:+.2f}），存在 suppression/negative confounding。",
        })

    if raw_p is not None and adjusted_p is not None:
        if raw_p < 0.05 <= adjusted_p:
            diagnostics.append({
                "type": "significance_disappears",
                "raw_effect": raw_effect,
                "adjusted_effect": adjusted_effect,
                "raw_p": raw_p,
                "adjusted_p": adjusted_p,
                "severity": "high",
                "message": f"控制后显著性消失（p {raw_p:.3g} → {adjusted_p:.3g}），原始差异可能由混淆驱动。",
            })
        elif raw_p >= 0.05 > adjusted_p:
            diagnostics.append({
                "type": "significance_emerges",
                "raw_effect": raw_effect,
                "adjusted_effect": adjusted_effect,
                "raw_p": raw_p,
                "adjusted_p": adjusted_p,
                "severity": "medium",
                "message": f"控制后效应显现（p {raw_p:.3g} → {adjusted_p:.3g}），可能存在负混淆。",
            })
        if adjusted_p is not None and adjusted_p < 0.05 and abs(adjusted_effect) < business_threshold:
            diagnostics.append({
                "type": "tiny_effect_significant",
                "raw_effect": raw_effect,
                "adjusted_effect": adjusted_effect,
                "adjusted_p": adjusted_p,
                "business_threshold": business_threshold,
                "severity": "low",
                "message": f"统计显著但效应量低于业务阈值（|{adjusted_effect:.2f}| < {business_threshold}），避免大样本显著性陷阱。",
            })
    return diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(description="研究结果 surprise/anomaly 检测")
    parser.add_argument("--metric", default="APEAL_Index")
    parser.add_argument("--group", default="YPV_01")
    parser.add_argument("--comparison", default="增购 vs 首购")
    parser.add_argument("--raw-effect", type=float, required=True)
    parser.add_argument("--adjusted-effect", type=float, required=True)
    parser.add_argument("--raw-p", type=float, default=None)
    parser.add_argument("--adjusted-p", type=float, default=None)
    parser.add_argument("--business-threshold", type=float, default=5.0)
    args = parser.parse_args()

    diagnostics = detect(args.raw_effect, args.adjusted_effect, args.raw_p,
                         args.adjusted_p, args.business_threshold)
    emit({
        "metric": args.metric,
        "group": args.group,
        "comparison": args.comparison,
        "raw_effect": args.raw_effect,
        "adjusted_effect": args.adjusted_effect,
        "diagnostics": diagnostics,
    })


if __name__ == "__main__":
    main()
