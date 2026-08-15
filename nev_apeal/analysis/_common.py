"""Shared loading and weighted-statistics helpers for the NEV-APEAL project."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import pyreadstat
except ImportError as exc:  # pragma: no cover
    raise SystemExit("缺少 pyreadstat，请安装项目依赖") from exc

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "source.sav"
WEIGHT = "APEAL_WT"


def load() -> tuple[pd.DataFrame, Any]:
    return pyreadstat.read_sav(str(DATA_PATH), user_missing=True)


def labels(meta: Any, column: str) -> dict[Any, str]:
    return meta.variable_value_labels.get(column) or {}


def weighted_mean(series: pd.Series, weights: pd.Series) -> float:
    valid = series.notna() & weights.notna()
    if not valid.any():
        return float("nan")
    return float(np.average(series[valid], weights=weights[valid]))


def weighted_group(df: pd.DataFrame, group: str, metrics: list[str], meta: Any) -> list[dict[str, Any]]:
    out = []
    for value in sorted(df[group].dropna().unique()):
        sub = df[df[group] == value]
        row = {"value": value, "label": labels(meta, group).get(value, str(value)), "n": len(sub)}
        for metric in metrics:
            row[metric] = weighted_mean(sub[metric], sub[WEIGHT].fillna(1.0))
        out.append(row)
    return out


def emit(payload: Any, *, question: str = "") -> None:
    """Emit the common Analysis Result Contract consumed by the research loop."""
    contract = {
        "status": "success",
        "analysis_id": Path(sys.argv[0]).stem,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "data_source": "data/source.sav",
            "weight": WEIGHT,
            "question": question,
        },
        "result": payload,
        "evidence": [],
        "warnings": [],
        "errors": [],
    }
    json.dump(contract, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
