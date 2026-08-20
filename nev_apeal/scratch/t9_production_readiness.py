"""Production-readiness check for T9 expectation calibration.

This is a bounded follow-up, not a new discovery scanner. It tests whether the
two valid expectation exposures (1/2/3 only) retain item-level associations
after entering the same model together with the frozen full controls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf  # type: ignore[import-not-found]

from analysis._common import load, WEIGHT


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "t9_production_readiness.json"
CONTROLS = [
    "SUPER_SEGMENT_DP",
    "CN_YNV_07",
    "PREMMAKE_DP",
    "AGE_BUCKETS",
    "CN_INCOME",
    "CN_EDUCATION",
]
EXPOSURES = ["AFUEL_D_06", "ACHAR_D_05"]
OUTCOMES = ["APEAL_Index", "AFUEL_Index", "ACHAR_index", "AFUEL_R_01", "ACHAR_R_01", "ACHAR_R_09"]


def fit_item(df: pd.DataFrame, outcome: str) -> dict:
    columns = [outcome, *EXPOSURES, *CONTROLS, WEIGHT]
    d = pd.DataFrame(df[columns]).copy()  # type: ignore
    for exposure in EXPOSURES:
        d = d[d[exposure].isin([1, 2, 3])]  # type: ignore
    d = d.dropna(subset=columns)  # type: ignore
    d["WT"] = d[WEIGHT].fillna(1.0)
    d["fuel_expectation"] = pd.Categorical(d["AFUEL_D_06"], categories=[2, 1, 3])
    d["charge_expectation"] = pd.Categorical(d["ACHAR_D_05"], categories=[2, 1, 3])
    formula = (
        f"{outcome} ~ C(fuel_expectation) + C(charge_expectation) + "
        + " + ".join(CONTROLS)
    )
    fit = smf.wls(formula, data=d, weights=d["WT"]).fit(cov_type="HC1")
    terms = {
        "fuel_worse": "C(fuel_expectation)[T.1]",
        "fuel_better": "C(fuel_expectation)[T.3]",
        "charge_worse": "C(charge_expectation)[T.1]",
        "charge_better": "C(charge_expectation)[T.3]",
    }
    effects = {}
    for label, term in terms.items():
        effects[label] = {
            "coef": round(float(fit.params[term]), 4),
            "p": float(fit.pvalues[term]),
        }
    return {"outcome": outcome, "n": int(fit.nobs), "r_squared": round(float(fit.rsquared), 4), "effects": effects}


def main() -> None:
    df, _ = load()
    results = [fit_item(df, outcome) for outcome in OUTCOMES]
    payload = {
        "analysis": "t9_production_readiness",
        "data_source": "data/source.sav",
        "weight": WEIGHT,
        "valid_expectation_levels": [1, 2, 3],
        "reference_level": 2,
        "controls": CONTROLS,
        "exposures": EXPOSURES,
        "results": results,
        "boundary": "横截面、自报预期；结果用于产品 item 映射，不构成因果或传播 ROI 证据。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
