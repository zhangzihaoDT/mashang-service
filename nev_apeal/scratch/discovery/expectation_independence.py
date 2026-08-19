"""Check whether the two charging expectation signals are independent.

The question is not whether both exposures predict APEAL in isolation, but
whether either exposure still contributes after the other is included.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf

from analysis._common import WEIGHT, load
from expectation_wow_scan import FULL_CONTROLS, clean_levels

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "scratch" / "discovery" / "_expectation_independence.json"
EXPOSURES = ["AFUEL_D_06", "ACHAR_D_05"]


def fit_models(df: pd.DataFrame, meta: object, outcome: str) -> list[dict]:
    cleaned = {var: clean_levels(meta, df, var) for var in EXPOSURES}
    d = df.assign(**cleaned, WT=df[WEIGHT].fillna(1.0)).dropna(
        subset=[*EXPOSURES, outcome, *FULL_CONTROLS]
    )
    d = d[d[EXPOSURES].isin([1.0, 2.0, 3.0]).all(axis=1)].copy()
    formula_base = " + ".join(FULL_CONTROLS)
    formulas = {
        "fuel_only": f"{outcome} ~ C(AFUEL_D_06) + {formula_base}",
        "charge_only": f"{outcome} ~ C(ACHAR_D_05) + {formula_base}",
        "both": f"{outcome} ~ C(AFUEL_D_06) + C(ACHAR_D_05) + {formula_base}",
    }
    result = []
    for name, formula in formulas.items():
        model = smf.wls(formula, data=d, weights=d["WT"]).fit(cov_type="HC1")
        terms = {
            term: {
                "coef": round(float(model.params[term]), 2),
                "p": round(float(model.pvalues[term]), 6),
            }
            for term in model.params.index
            if term.startswith("C(AFUEL_D_06)") or term.startswith("C(ACHAR_D_05)")
        }
        result.append({"model": name, "n": int(model.nobs), "r_squared": round(float(model.rsquared), 4), "terms": terms})
    return result


def main() -> None:
    df, meta = load()
    levels = {var: clean_levels(meta, df, var) for var in EXPOSURES}
    pair = pd.DataFrame(levels).dropna()
    result = {
        "sample": {"pairwise_n": int(len(pair)), "full_n": int(len(df))},
        "spearman": round(float(pair[EXPOSURES].corr(method="spearman").iloc[0, 1]), 4),
        "crosstab_pct": pd.crosstab(pair[EXPOSURES[0]], pair[EXPOSURES[1]], normalize="index").round(4).to_dict(),
        "models": {outcome: fit_models(df, meta, outcome) for outcome in ["APEAL_Index", "AFUEL_Index"]},
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
