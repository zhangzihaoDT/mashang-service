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
CONTRACTS_PATH = PROJECT_ROOT / "contracts" / "measurement.json"
WEIGHT = "APEAL_WT"

# 测量伪影语义（值标签命中任一即视为不应成为研究 segment）
import re as _re

ARTIFACT_LABEL_PATTERNS = (
    _re.compile(r"prefer not", _re.I),
    _re.compile(r"refus", _re.I),
    _re.compile(r"don'?t know", _re.I),
    _re.compile(r"not applicable", _re.I),
    _re.compile(r"\bn/?a\b", _re.I),
    _re.compile(r"none of the above", _re.I),
    _re.compile(r"not sure", _re.I),
    _re.compile(r"\bunknown\b", _re.I),
    _re.compile(r"\bother\b", _re.I),
    _re.compile(r"no answer", _re.I),
    _re.compile(r"not answered", _re.I),
)

REFUSAL_PATTERNS = (_re.compile(r"prefer not", _re.I), _re.compile(r"refus", _re.I),
                    _re.compile(r"no answer", _re.I), _re.compile(r"not answered", _re.I))


def load() -> tuple[pd.DataFrame, Any]:
    return pyreadstat.read_sav(str(DATA_PATH), user_missing=True)


def labels(meta: Any, column: str) -> dict[Any, str]:
    return meta.variable_value_labels.get(column) or {}


def detect_artifact_values(meta: Any, column: str) -> list[dict[str, Any]]:
    """返回该变量的测量伪影取值列表（如 98=Prefer not to answer）。"""
    out = []
    for value, text in (labels(meta, column) or {}).items():
        lowered = str(text).strip()
        is_artifact = any(p.search(lowered) for p in ARTIFACT_LABEL_PATTERNS)
        if is_artifact:
            is_refusal = any(p.search(lowered) for p in REFUSAL_PATTERNS)
            out.append({"value": value, "reason": "refusal" if is_refusal else "artifact_label"})
    return out
    return out


def excluded_values(meta: Any, column: str) -> list[Any]:
    """从 Measurement Contract 读取该变量排除值；缺失则运行时检测。"""
    try:
        if CONTRACTS_PATH.exists():
            contract = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
            for entry in contract.get("excluded_values", []):
                if entry.get("variable") == column:
                    return [e["value"] for e in entry.get("values", [])]
    except Exception:
        pass
    return [d["value"] for d in detect_artifact_values(meta, column)]


def valid_groups(df: pd.DataFrame, meta: Any, column: str) -> pd.Series:
    """返回剔除测量伪影后的取值掩码（伪影值置 NaN，下游自然排除）。"""
    ex = excluded_values(meta, column)
    if not ex:
        return df[column]
    return df[column].replace(ex, np.nan)


def weighted_mean(series: pd.Series, weights: pd.Series) -> float:
    valid = series.notna() & weights.notna()
    if not valid.any():
        return float("nan")
    return float(np.average(series[valid], weights=weights[valid]))


def weighted_group(df: pd.DataFrame, group: str, metrics: list[str], meta: Any) -> list[dict[str, Any]]:
    out = []
    clean = valid_groups(df, meta, group)
    for value in sorted(clean.dropna().unique()):
        sub = df[clean == value]
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
