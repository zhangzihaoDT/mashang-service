"""Lightweight OLS diagnostic for a declared numeric outcome and predictors."""

import argparse

from ._common import emit, load


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outcome", default="APEAL_Index")
    parser.add_argument("--predictors", nargs="+", default=["YPV_01", "SUPER_SEGMENT_DP"])
    args = parser.parse_args()
    df, _ = load()
    try:
        import statsmodels.formula.api as smf
    except ImportError as exc:
        raise SystemExit("缺少 statsmodels，请安装项目依赖") from exc
    terms = " + ".join(f"C({p})" for p in args.predictors)
    fit = smf.ols(f"{args.outcome} ~ {terms}", data=df).fit()
    emit({"formula": fit.model.formula, "n": int(fit.nobs), "r_squared": float(fit.rsquared), "params": fit.params.to_dict()})


if __name__ == "__main__":
    main()
