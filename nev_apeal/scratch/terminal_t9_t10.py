"""Terminal qualification analyses for T9 and T10.

This is deliberately a bounded terminal pass: no new variable mining, only
the mechanisms and controls specified in the qualification document.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from analysis._common import WEIGHT, load, weighted_mean

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "terminal_t9_t10.json"
FULL = ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION"]
FULL_WITH_SEGMENT = [*FULL, "SEGMENT_DP"]
EXPECTATIONS = ["AFUEL_D_06", "ACHAR_D_05"]
EXPECTATION_OUTCOMES = ["APEAL_Index", "AFUEL_Index", "ACHAR_index"]
CHARGE_ITEMS = [f"ACHAR_R_{i:02d}" for i in range(1, 10)] + ["AFUEL_R_01"]
MILEAGE_BINS = [0, 1000, 5000, 10000, 20000, 50000, np.inf]
MILEAGE_LABELS = ["<1k", "1k-5k", "5k-10k", "10k-20k", "20k-50k", "50k+"]
MILEAGE_OUTCOMES = ["APEAL_Index", "AEXT_Index", "AINT_Index", "ACMFT_Index", "ADRV_Index", "APERF_Index", "ASFTY_Index", "AFUEL_Index", "ACHAR_index"]


def clean_expectation(df: pd.DataFrame, var: str) -> pd.Series:
    s = pd.to_numeric(df[var], errors="coerce")
    return s.where(s.isin([1.0, 2.0, 3.0]))


def coef_table(model: object, prefix: str) -> dict:
    return {
        term: {"coef": round(float(model.params[term]), 2), "p": round(float(model.pvalues[term]), 6)}
        for term in model.params.index
        if term.startswith(prefix)
    }


def t9_run(df: pd.DataFrame) -> dict:
    d = df.copy()
    for var in EXPECTATIONS:
        d[var] = clean_expectation(d, var)
    d = d.dropna(subset=[*EXPECTATIONS, *FULL]).copy()
    d["WT"] = d[WEIGHT].fillna(1.0)
    formula_controls = " + ".join(FULL)
    models = {}
    for outcome in EXPECTATION_OUTCOMES:
        fit = smf.wls(
            f"{outcome} ~ C(AFUEL_D_06) + C(ACHAR_D_05) + {formula_controls}",
            data=d.dropna(subset=[outcome]), weights=d["WT"],
        ).fit(cov_type="HC1")
        models[outcome] = {"n": int(fit.nobs), "fuel": coef_table(fit, "C(AFUEL_D_06)"), "charge": coef_table(fit, "C(ACHAR_D_05)")}

    item_rows = []
    for exposure in EXPECTATIONS:
        for item in CHARGE_ITEMS:
            if item not in d:
                continue
            sub = d.dropna(subset=[item]).copy()
            fit = smf.wls(f"{item} ~ C({exposure}, Treatment(reference=2.0)) + {formula_controls}", data=sub, weights=sub["WT"]).fit(cov_type="HC1")
            terms = coef_table(fit, f"C({exposure}, Treatment(reference=2.0))")
            better = next((v for k, v in terms.items() if "T.3" in k), None)
            worse = next((v for k, v in terms.items() if "T.1" in k), None)
            item_rows.append({"exposure": exposure, "item": item, "n": int(fit.nobs), "better": better, "worse": worse})
    return {"analytic_n": int(len(d)), "models": models, "item_models": item_rows}


def t10_run(df: pd.DataFrame) -> dict:
    mileage_items = CHARGE_ITEMS + ["ADRV_R_01", "ADRV_R_02", "ACMFT_R_01", "APERF_R_01"]
    available_items = [item for item in mileage_items if item in df.columns]
    d = df[["NEV_12", WEIGHT, *MILEAGE_OUTCOMES, *available_items, *FULL_WITH_SEGMENT]].dropna(subset=["NEV_12"]).copy()
    d["BIN"] = pd.cut(d["NEV_12"], bins=MILEAGE_BINS, labels=MILEAGE_LABELS, right=False, include_lowest=True)
    d = d.dropna(subset=["BIN", *FULL_WITH_SEGMENT]).copy()
    d["WT"] = d[WEIGHT].fillna(1.0)
    control_formula = " + ".join(FULL)
    structural_formula = " + ".join(FULL_WITH_SEGMENT)
    module_models = {}
    for outcome in MILEAGE_OUTCOMES:
        sub = d.dropna(subset=[outcome])
        fit = smf.wls(f"{outcome} ~ C(BIN) + {structural_formula}", data=sub, weights=sub["WT"]).fit(cov_type="HC1")
        module_models[outcome] = {"n": int(fit.nobs), "bin_coefs": coef_table(fit, "C(BIN)")}

    item_rows = []
    for item in mileage_items:
        if item not in d:
            continue
        sub = d.dropna(subset=[item])
        means = {
            str(label): round(weighted_mean(g[item].clip(lower=1, upper=10), g["WT"]), 2)
            for label, g in sub.groupby("BIN", observed=True)
        }
        item_rows.append({"item": item, "n": int(len(sub)), "weighted_means": means})

    return {"analytic_n": int(len(d)), "module_models": module_models, "item_means": item_rows}


def main() -> None:
    df, _ = load()
    result = {"T9": t9_run(df), "T10": t10_run(df)}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"terminal results written -> {OUT}")
    print(json.dumps({k: {"analytic_n": v["analytic_n"]} for k, v in result.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
