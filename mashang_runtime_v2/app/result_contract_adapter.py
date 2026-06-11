#!/usr/bin/env python
"""
Runtime V2 — Result Contract Adapter

读取 script 输出的 Result Contract JSON 并适配为统一内部格式。
支持 quality check: ok / warning / error。
"""

import json

REQUIRED_CRITICAL = ["status"]
REQUIRED_OPTIONAL = ["metric", "scope", "summary", "dimensions", "results", "followup_context"]
REQUIRED_FIELDS = REQUIRED_CRITICAL + REQUIRED_OPTIONAL


def load(contract: dict | None, stdout: str = "") -> dict:
    """加载和验证 Result Contract。"""
    if contract is None:
        if stdout.strip().startswith("{"):
            try:
                contract = json.loads(stdout)
            except json.JSONDecodeError:
                pass

    if contract is None:
        return {"status": "error", "contract_quality": "error",
                "error": "no valid Result Contract found",
                "warnings": ["stdout did not contain valid JSON"]}

    warnings = []
    quality = "ok"

    # Critical: status must exist
    if "status" not in contract:
        quality = "error"
        warnings.append("missing_required_status")
    else:
        st = contract["status"]
        if st not in ("success", "partial_success"):
            quality = "warning" if quality != "error" else quality

    # Optional fields — check top level and result sub-object
    result_obj = contract.get("result", {})
    if not isinstance(result_obj, dict):
        result_obj = {}
    missing_optional = []
    for f in REQUIRED_OPTIONAL:
        if f not in contract and f not in result_obj:
            missing_optional.append(f)
    if missing_optional:
        if quality != "error":
            quality = "warning"
        warnings.extend(f"missing_{f}" for f in missing_optional)

    # At least one of dimensions or results
    has_dim = bool(contract.get("result", {}).get("dimensions")) if isinstance(contract.get("result"), dict) else False
    has_res = bool(contract.get("result", {}).get("results")) if isinstance(contract.get("result"), dict) else False
    has_tables = bool(contract.get("result", {}).get("tables")) if isinstance(contract.get("result"), dict) else False
    if not (has_dim or has_res or has_tables):
        warnings.append("no_dimensions_or_results")
        if quality == "ok":
            quality = "warning"

    result = contract.get("result", {})
    metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
    summary = result.get("summary", "") if isinstance(result, dict) else ""
    dimensions = result.get("dimensions", []) if isinstance(result, dict) else []

    return {
        "status": contract.get("status", "unknown"),
        "contract_quality": quality,
        "is_contract_valid": quality != "error",
        "metric": contract.get("followup_context", {}).get("metric", ""),
        "scope": contract.get("scope", {}),
        "summary": summary,
        "metrics": metrics,
        "dimensions": dimensions,
        "followup_context": contract.get("followup_context", {}),
        "warnings": warnings,
        "raw_contract": contract,
    }
