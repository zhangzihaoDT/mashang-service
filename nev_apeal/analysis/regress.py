"""OLS diagnostics for a declared outcome and exposure.

Supports two modes:
  - default: full model with all controls, report exposure effect terms.
  - --sequential: coefficient path — refit exposure-only, then add controls one
    at a time, tracing how the exposure coefficient evolves (suppression path).

Variables with SAV value labels are categorical (C()); continuous variables
(e.g. price CN_YNV_07) stay numeric to avoid exploding dummy sets.
"""

from __future__ import annotations

import argparse

from ._common import emit, load


def _terms(meta, predictors: list[str]) -> list[str]:
    return [
        f"C({p})" if meta.variable_value_labels.get(p) else p
        for p in predictors
    ]


def _fit(outcome: str, predictors: list[str], df, meta):
    import statsmodels.formula.api as smf
    formula = f"{outcome} ~ {' + '.join(_terms(meta, predictors))}"
    return smf.ols(formula, data=df).fit()


def _exposure_effect(fit, exposure: str) -> dict:
    mask = fit.params.index.str.contains(f"C({exposure})", regex=False)
    return {
        k: {"coef": float(v), "p": float(fit.pvalues[k])}
        for k, v in fit.params[mask].items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OLS diagnostic + coefficient path")
    parser.add_argument("--outcome", default="APEAL_Index")
    parser.add_argument("--exposure", default="YPV_01")
    parser.add_argument("--controls", nargs="+", default=["SUPER_SEGMENT_DP", "CN_YNV_07", "MAKE_DP"])
    parser.add_argument("--predictors", nargs="+", default=None, help="向后兼容：首个为 exposure，其余为 controls")
    parser.add_argument("--sequential", action="store_true", help="输出逐控制变量 coefficient path")
    args = parser.parse_args()

    if args.predictors:
        args.exposure = args.predictors[0]
        args.controls = args.predictors[1:]
    df, meta = load()
    try:
        import statsmodels.formula.api as smf  # noqa: F401
    except ImportError as exc:
        raise SystemExit("缺少 statsmodels，请安装项目依赖") from exc

    if not args.sequential:
        fit = _fit(args.outcome, [args.exposure, *args.controls], df, meta)
        emit({
            "formula": fit.model.formula,
            "n": int(fit.nobs),
            "r_squared": float(fit.rsquared),
            "f_pvalue": float(fit.f_pvalue),
            "effect_terms": _exposure_effect(fit, args.exposure),
        })
        return

    steps = []
    included: list[str] = []
    for control in [args.exposure, *args.controls]:
        if control not in included:
            included.append(control)
        fit = _fit(args.outcome, included, df, meta)
        effects = _exposure_effect(fit, args.exposure)
        steps.append({
            "step": len(included) - 1,
            "controls": included[1:],
            "n": int(fit.nobs),
            "r_squared": round(float(fit.rsquared), 4),
            "exposure_effect": effects,
        })
    raw = steps[0]["exposure_effect"]
    final = steps[-1]["exposure_effect"]
    path = []
    for step in steps:
        for key, term in step["exposure_effect"].items():
            path.append({"controls": step["controls"], "term": key, "coef": term["coef"], "p": term["p"]})
    emit({
        "formula": f"{args.outcome} ~ C({args.exposure}) + controls…",
        "mode": "sequential",
        "raw_effect": raw,
        "adjusted_effect": final,
        "path": path,
        "steps": steps,
    })


if __name__ == "__main__":
    main()
