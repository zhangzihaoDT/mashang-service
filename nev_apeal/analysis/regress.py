"""OLS diagnostics for a declared outcome and exposure.

Exposure contract:
  - categorical (has SAV value labels) -> effect_type=contrast, reference + levels
  - continuous  (numeric, no labels)    -> effect_type=slope, per-unit coefficient

Supports coefficient path (--sequential): refit exposure-only then add controls
one at a time, tracing how the exposure effect evolves.
"""

from __future__ import annotations

import argparse

from ._common import emit, load


def exposure_type(meta, exposure: str) -> str:
    return "categorical" if meta.variable_value_labels.get(exposure) else "continuous"


def _terms(meta, predictors: list[str]) -> list[str]:
    return [
        f"C({p})" if meta.variable_value_labels.get(p) else p
        for p in predictors
    ]


def _fit(outcome: str, predictors: list[str], df, meta):
    import statsmodels.formula.api as smf
    formula = f"{outcome} ~ {' + '.join(_terms(meta, predictors))}"
    return smf.ols(formula, data=df).fit()


def exposure_effect(fit, exposure: str, meta, unit_scale: float, unit_label: str) -> dict:
    if exposure_type(meta, exposure) == "continuous":
        coef = float(fit.params[exposure])
        p = float(fit.pvalues[exposure])
        return {
            "effect_type": "slope",
            "term": exposure,
            "coefficient": round(coef, 5),
            "coefficient_scaled": round(coef * unit_scale, 5),
            "unit": unit_label,
            "p": p,
        }
    mask = fit.params.index.str.contains(f"C({exposure})", regex=False)
    levels = {
        k: {"coef": float(v), "p": float(fit.pvalues[k])}
        for k, v in fit.params[mask].items()
    }
    return {
        "effect_type": "contrast",
        "reference": "1.0",
        "levels": levels,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OLS diagnostic + coefficient path")
    parser.add_argument("--outcome", default="APEAL_Index")
    parser.add_argument("--exposure", default="YPV_01")
    parser.add_argument("--controls", nargs="+", default=["SUPER_SEGMENT_DP", "CN_YNV_07", "MAKE_DP"])
    parser.add_argument("--predictors", nargs="+", default=None, help="向后兼容：首个为 exposure，其余为 controls")
    parser.add_argument("--sequential", action="store_true", help="输出逐控制变量 coefficient path")
    parser.add_argument("--unit-scale", type=float, default=1.0, help="连续 exposure 单位换算系数（如 元→万元 =1e-4）")
    parser.add_argument("--unit-label", default="per_1_unit", help="连续 exposure 单位标签")
    args = parser.parse_args()

    if args.predictors:
        args.exposure = args.predictors[0]
        args.controls = args.predictors[1:]
    df, meta = load()
    etype = exposure_type(meta, args.exposure)

    if not args.sequential:
        fit = _fit(args.outcome, [args.exposure, *args.controls], df, meta)
        emit({
            "formula": fit.model.formula,
            "n": int(fit.nobs),
            "r_squared": round(float(fit.rsquared), 4),
            "f_pvalue": float(fit.f_pvalue),
            "exposure": {"variable": args.exposure, "type": etype,
                         "effect": exposure_effect(fit, args.exposure, meta, args.unit_scale, args.unit_label)},
        })
        return

    steps = []
    included: list[str] = []
    for control in [args.exposure, *args.controls]:
        if control not in included:
            included.append(control)
        fit = _fit(args.outcome, included, df, meta)
        steps.append({
            "step": len(included) - 1,
            "controls": included[1:],
            "n": int(fit.nobs),
            "r_squared": round(float(fit.rsquared), 4),
            "exposure_effect": exposure_effect(fit, args.exposure, meta, args.unit_scale, args.unit_label),
        })
    path = []
    for step in steps:
        eff = step["exposure_effect"]
        if etype == "continuous":
            path.append({"controls": step["controls"], "term": args.exposure,
                         "coef": eff["coefficient"], "p": eff["p"]})
        else:
            for term, level in eff.get("levels", {}).items():
                path.append({"controls": step["controls"], "term": term,
                             "coef": level["coef"], "p": level["p"]})
    emit({
        "formula": f"{args.outcome} ~ {args.exposure} + controls…",
        "mode": "sequential",
        "exposure": {"variable": args.exposure, "type": etype},
        "path": path,
        "steps": steps,
    })


if __name__ == "__main__":
    main()
