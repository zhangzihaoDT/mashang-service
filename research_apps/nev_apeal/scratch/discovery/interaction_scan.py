"""Controlled Interaction Discovery pilot.

Only pre-registered parent signals are tested. Segment spread is retained as a
descriptive effect-size aid; qualification is based on the joint interaction
block, HC1 covariance, BH-FDR q-value, cell support, and business magnitude.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from analysis._common import WEIGHT, load, weighted_mean

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "scratch" / "discovery" / "_signals_interaction.json"
MODERATOR = "SEGMENT_DP"
CONTROLS = ["SUPER_SEGMENT_DP", "CN_YNV_07", "PREMMAKE_DP", "AGE_BUCKETS", "CN_INCOME", "CN_EDUCATION"]
MIN_CELL_N = 100
BUSINESS_THRESHOLD = 10.0
MILEAGE_EDGES = [0, 1000, 5000, 10000, 20000, 50000, np.inf]
MILEAGE_LABELS = ["<1k", "1k-5k", "5k-10k", "10k-20k", "20k-50k", "50k+"]

# (parent topic, exposure, outcome, exposure contrast used for descriptive spread)
TESTS = [
    ("T7", "NEV_08", "APEAL_Index", (1.0, 99.0)),
    ("T7", "NEV_08", "AFUEL_Index", (1.0, 99.0)),
    ("T7", "NEV_08", "ACHAR_index", (1.0, 99.0)),
    ("T9", "AFUEL_D_06", "APEAL_Index", (1.0, 3.0)),
    ("T9", "AFUEL_D_06", "AFUEL_Index", (1.0, 3.0)),
    ("T9", "ACHAR_D_05", "APEAL_Index", (1.0, 3.0)),
    ("T9", "ACHAR_D_05", "ACHAR_index", (1.0, 3.0)),
    ("T10", "NEV_12", "APEAL_Index", ("1k-5k", "10k-20k")),
    ("T10", "NEV_12", "AFUEL_Index", ("1k-5k", "10k-20k")),
]


def bh_qvalues(p_values: list[float]) -> list[float]:
    order = np.argsort(p_values)
    q = np.empty(len(p_values), dtype=float)
    running = 1.0
    for rank in range(len(order), 0, -1):
        idx = order[rank - 1]
        running = min(running, p_values[idx] * len(p_values) / rank)
        q[idx] = running
    return [round(float(value), 6) for value in q]


def prepare(df: pd.DataFrame, exposure: str) -> tuple[pd.DataFrame, str, tuple[object, object]]:
    d = df.copy()
    if exposure == "NEV_12":
        d["EXPOSURE"] = pd.cut(d[exposure], bins=MILEAGE_EDGES, labels=MILEAGE_LABELS, right=False, include_lowest=True)
        contrast = ("1k-5k", "10k-20k")
    else:
        d["EXPOSURE"] = pd.to_numeric(d[exposure], errors="coerce")
        valid = [1.0, 2.0, 3.0] if exposure != "NEV_08" else [1.0, 2.0, 3.0, 4.0, 5.0, 99.0]
        d["EXPOSURE"] = d["EXPOSURE"].where(d["EXPOSURE"].isin(valid))
        contrast = (1.0, 3.0) if exposure != "NEV_08" else (1.0, 99.0)
    return d, "EXPOSURE", contrast


def contrast_spread(d: pd.DataFrame, outcome: str) -> tuple[float | None, list[dict]]:
    rows = []
    for segment, group in d.groupby(MODERATOR):
        sub = group.dropna(subset=[outcome]).copy()
        if len(sub) < MIN_CELL_N or sub["EXPOSURE"].nunique() < 2:
            continue
        means = {
            str(level): weighted_mean(g[outcome], g[WEIGHT].fillna(1.0))
            for level, g in sub.groupby("EXPOSURE", observed=True)
        }
        if "low" not in means or "high" not in means:
            continue
        rows.append({
            "segment": str(segment),
            "n": int(len(sub)),
            "contrast": round(float(means["high"] - means["low"]), 2),
        })
    if len(rows) < 3:
        return None, rows
    values = [row["contrast"] for row in rows]
    return round(float(max(values) - min(values)), 2), rows


def run_test(df: pd.DataFrame, parent: str, exposure: str, outcome: str, requested_contrast: tuple[object, object]) -> dict:
    d, exposure_col, contrast = prepare(df, exposure)
    cols = ["EXPOSURE", MODERATOR, outcome, WEIGHT, *CONTROLS]
    d = d[cols].dropna().copy()
    d = d[d["EXPOSURE"].isin(contrast)].copy()
    d["GROUP"] = np.where(d["EXPOSURE"] == contrast[0], "low", "high")
    eligible = (
        d.groupby([MODERATOR, "GROUP"], observed=True).size()
        .unstack(fill_value=0)
    )
    eligible_segments = eligible.index[(eligible.get("low", 0) >= MIN_CELL_N) & (eligible.get("high", 0) >= MIN_CELL_N)]
    d = d[d[MODERATOR].isin(eligible_segments)].copy()
    if len(eligible_segments) < 3:
        return {
            "signal_id": f"interaction_{exposure.lower()}_{outcome.lower()}_by_{MODERATOR.lower()}",
            "analysis_type": "interaction",
            "parent_topic": parent,
            "exposure": exposure,
            "moderator": MODERATOR,
            "outcome": outcome,
            "effect_size": {"interaction_block_p": None, "descriptive_contrast_spread": None, "business_threshold": BUSINESS_THRESHOLD, "unit": "outcome points"},
            "sample_support": {"n": int(len(d)), "segments": int(len(eligible_segments)), "min_cell_n": 0, "coverage": "INSUFFICIENT_CELLS"},
            "stability": "fragile",
            "novelty": 3,
            "controls": CONTROLS,
            "inference": {"covariance": "HC1", "test": "joint interaction block Wald test", "raw_p": None},
            "interpretation": "No interaction model was qualified because fewer than three segments met the pre-registered cell-size threshold.",
            "caveats": "Segment spread is not interaction evidence; do not relax the cell-size gate post hoc.",
            "qualification": {"fdr_pass": False, "cell_support_pass": False, "business_spread_pass": False, "default_action": "insufficient_coverage", "new_candidate_allowed": False},
            "segment_contrasts": [],
        }
    formula = f"{outcome} ~ C(GROUP) * C({MODERATOR}) + " + " + ".join(CONTROLS)
    fit = smf.wls(formula, data=d, weights=d[WEIGHT].fillna(1.0)).fit(cov_type="HC1")
    table = fit.wald_test_terms(skip_single=False).table
    term = f"C(GROUP):C({MODERATOR})"
    if term not in table.index:
        term = f"C({MODERATOR}):C(GROUP)"
    block_p = float(table.loc[term, "pvalue"])
    spread, segment_rows = contrast_spread(d, outcome)
    min_cell = int(d.groupby(["GROUP", MODERATOR], observed=True).size().min()) if len(d) else 0
    return {
        "signal_id": f"interaction_{exposure.lower()}_{outcome.lower()}_by_{MODERATOR.lower()}",
        "analysis_type": "interaction",
        "parent_topic": parent,
        "exposure": exposure,
        "moderator": MODERATOR,
        "outcome": outcome,
        "effect_size": {
            "interaction_block_p": round(block_p, 8),
            "descriptive_contrast_spread": spread,
            "business_threshold": BUSINESS_THRESHOLD,
            "unit": "outcome points",
        },
        "sample_support": {"n": int(fit.nobs), "segments": len(segment_rows), "min_cell_n": min_cell, "coverage": "SEGMENT_QUEUE"},
        "stability": "moderate" if min_cell >= MIN_CELL_N else "fragile",
        "novelty": 3,
        "controls": CONTROLS,
        "inference": {"covariance": "HC1", "test": "joint interaction block Wald test", "raw_p": block_p},
        "interpretation": "Segment spread is descriptive only; formal qualification depends on the joint interaction block and FDR-adjusted q-value.",
        "caveats": "Observational; pre-registered SEGMENT_DP queue; significant interaction defaults to parent-topic refinement, not a new Topic.",
        "segment_contrasts": segment_rows,
    }


def main() -> None:
    df, _ = load()
    signals = [run_test(df, *test) for test in TESTS]
    valid_indices = [i for i, s in enumerate(signals) if s["inference"]["raw_p"] is not None]
    valid_q = bh_qvalues([signals[i]["inference"]["raw_p"] for i in valid_indices])
    q_by_index = dict(zip(valid_indices, valid_q))
    for i, signal in enumerate(signals):
        q_value = q_by_index.get(i)
        signal["inference"]["q_value"] = q_value
        signal["qualification"] = {
            "fdr_pass": q_value is not None and q_value < 0.05,
            "cell_support_pass": signal["sample_support"]["min_cell_n"] >= MIN_CELL_N,
            "business_spread_pass": (signal["effect_size"]["descriptive_contrast_spread"] or 0) >= BUSINESS_THRESHOLD,
            "default_action": "insufficient_coverage" if signal["inference"]["raw_p"] is None else "parent_topic_refinement",
            "new_candidate_allowed": False,
        }
    OUT.write_text(json.dumps(signals, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps([
        {"signal_id": s["signal_id"], "block_p": s["inference"]["raw_p"], "q": s["inference"]["q_value"], "spread": s["effect_size"]["descriptive_contrast_spread"], "action": s["qualification"]["default_action"]}
        for s in signals
    ], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
