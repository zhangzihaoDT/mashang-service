#!/usr/bin/env python3
"""
validate_ai_response.py — 校验 AI 输出 JSON 的结构完整性。

检测 AI 输出是 event 类型还是 brief 类型，然后做最小字段校验。

用法:
  python validators/validate_ai_response.py path/to/ai_output.json

依赖: 无 (仅 Python 标准库)
"""

import json
import sys
import os


# ── 最小校验规则 ────────────────────────────────────────────────

DAILY_MONITOR_REQUIRED = [
    "task_name",
    "battle_field",
    "our_model",
    "monitor_date",
    "time_window",
    "input_assets",
    "event_candidates",
    "no_event_models",
    "needs_review",
]

EVENT_REQUIRED = [
    "event_id",
    "battle_field",
    "confirmed_facts",
    "inferences",
    "unconfirmed_claims",
    "confidence_level",
    "missing_evidence",
]

BRIEF_REQUIRED = [
    "brief_id",
    "our_model",
    "event_model",
    "battle_field",
    "executive_summary",
    "source_items",
    "missing_evidence",
    "confidence_level",
    "followup_recommendation",
]

SHARED_REQUIRED = [
    "source_items",
    "confirmed_facts",
    "inferences",
    "unconfirmed_claims",
    "confidence_level",
    "missing_evidence",
]


def detect_type(data: dict) -> str:
    """Detect whether the JSON is daily_monitor, event or brief type."""
    if data.get("task_name") == "auto_launch_daily_sales_action_monitor":
        return "daily_monitor"
    if "event_id" in data and "event" in data:
        return "event"
    if "brief_id" in data or "sections" in data:
        return "brief"
    if "event_model" in data and "event_type" in data and "our_model" not in data:
        return "event"
    return "brief" if "our_model" in data else "unknown"


def check_non_empty(data: dict, key: str) -> tuple[bool, str]:
    """Check a field exists and is non-empty."""
    if key not in data:
        return False, f"missing field: {key}"
    val = data[key]
    if val is None:
        return False, f"field is null: {key}"
    if isinstance(val, (list, tuple)):
        if len(val) == 0:
            return False, f"empty list: {key}"
    if isinstance(val, str) and not val.strip():
        return False, f"empty string: {key}"
    return True, ""


def check_is_array(data: dict, key: str) -> tuple[bool, str]:
    """Check a field is an array (list)."""
    if key not in data:
        return False, f"missing field: {key}"
    if not isinstance(data[key], list):
        return False, f"not an array: {key} (got {type(data[key]).__name__})"
    return True, ""


def check_confidence_level(data: dict) -> tuple[bool, str]:
    """Check confidence_level is a known value."""
    valid = {"high", "medium", "low", "unknown"}
    val = data.get("confidence_level")
    if val is None:
        return False, "missing or null: confidence_level"
    if val not in valid:
        return False, f"invalid confidence_level: {val} (expected high/medium/low/unknown)"
    return True, ""


def run_validation(data: dict) -> dict:
    """Run full validation and return a result dict."""
    result = {
        "ok": True,
        "type": detect_type(data),
        "checks": {},
        "errors": [],
    }

    doc_type = result["type"]
    if doc_type == "unknown":
        result["ok"] = False
        result["errors"].append("cannot determine type (neither daily_monitor, event, nor brief)")
        return result

    # Daily Monitor validation
    if doc_type == "daily_monitor":
        return _validate_daily_monitor(data, result)

    # Determine which fields to check for legacy types
    if doc_type == "event":
        required = EVENT_REQUIRED
    else:  # brief
        required = BRIEF_REQUIRED

    # Check all required fields
    for key in required:
        ok, msg = check_non_empty(data, key)
        result["checks"][key] = msg if not ok else "ok"
        if not ok:
            result["ok"] = False
            result["errors"].append(msg)

    # Check source_items exists and is non-empty
    ok, msg = check_non_empty(data, "source_items")
    if ok:
        ok, msg = check_is_array(data, "source_items")
    result["checks"]["source_items"] = msg if not ok else f"ok ({len(data.get('source_items', []))} items)"
    if not ok:
        result["ok"] = False
        result["errors"].append(msg)

    # Check confirmed_facts / inferences / unconfirmed_claims are arrays
    for key in ["confirmed_facts", "inferences", "unconfirmed_claims"]:
        ok, msg = check_is_array(data, key)
        result["checks"][key] = msg if not ok else f"ok ({len(data.get(key, []))} items)"
        if not ok:
            result["ok"] = False
            result["errors"].append(msg)

    # Check confidence_level
    ok, msg = check_confidence_level(data)
    result["checks"]["confidence_level"] = msg if not ok else f"ok ({data.get('confidence_level')})"
    if not ok:
        result["ok"] = False
        result["errors"].append(msg)

    # Check missing_evidence or unresolved_questions
    if "missing_evidence" not in data and "unresolved_questions" not in data:
        result["ok"] = False
        result["errors"].append("missing both: missing_evidence and unresolved_questions")
        result["checks"]["missing_evidence"] = "missing"
    elif "missing_evidence" in data:
        result["checks"]["missing_evidence"] = f"ok ({len(data.get('missing_evidence', []))} items)"
    else:
        result["checks"]["unresolved_questions"] = f"ok ({len(data.get('unresolved_questions', []))} items)"

    return result


def _validate_daily_monitor(data: dict, result: dict) -> dict:
    """Validate Daily Sales Action Monitor format."""
    # Check required top-level fields exist (allow empty arrays)
    for key in DAILY_MONITOR_REQUIRED:
        if key not in data:
            result["ok"] = False
            result["errors"].append(f"missing field: {key}")
            result["checks"][key] = "missing"
        else:
            val = data[key]
            if val is None:
                result["ok"] = False
                result["errors"].append(f"field is null: {key}")
                result["checks"][key] = "null"
            elif isinstance(val, str) and not val.strip():
                result["ok"] = False
                result["errors"].append(f"empty string: {key}")
                result["checks"][key] = "empty"
            elif isinstance(val, list):
                result["checks"][key] = f"ok ({len(val)} items)"
            elif isinstance(val, dict):
                result["checks"][key] = f"ok ({len(val)} keys)"
            else:
                result["checks"][key] = "ok"

    # task_name must be the expected value
    if data.get("task_name") != "auto_launch_daily_sales_action_monitor":
        result["ok"] = False
        result["errors"].append(f"invalid task_name: {data.get('task_name')}")

    # event_candidates must be array
    if not isinstance(data.get("event_candidates"), list):
        result["ok"] = False
        result["errors"].append("event_candidates must be an array")

    # no_event_models must be array
    if not isinstance(data.get("no_event_models"), list):
        result["ok"] = False
        result["errors"].append("no_event_models must be an array")

    # needs_review must be array
    if not isinstance(data.get("needs_review"), list):
        result["ok"] = False
        result["errors"].append("needs_review must be an array")

    # discovery_signals must be array if present
    ds = data.get("discovery_signals")
    if ds is not None and not isinstance(ds, list):
        result["ok"] = False
        result["errors"].append("discovery_signals must be an array")
    elif ds:
        for idx, s in enumerate(ds):
            if not isinstance(s, dict):
                continue
            conf = s.get("confidence")
            if conf == "high":
                result["ok"] = False
                result["errors"].append(f"discovery_signals[{idx}].confidence cannot be 'high'")
            si = s.get("source_items")
            if si is not None and not isinstance(si, list):
                result["ok"] = False
                result["errors"].append(f"discovery_signals[{idx}].source_items must be an array")

    # search_audit must be array if present
    sa = data.get("search_audit")
    if sa is not None and not isinstance(sa, list):
        result["ok"] = False
        result["errors"].append("search_audit must be an array")

    # Check event_candidates items (lenient)
    for idx, candidate in enumerate(data.get("event_candidates", [])):
        if not isinstance(candidate, dict):
            continue
        # event_type must be non-empty if present
        et = candidate.get("event_type")
        if et is not None and (not isinstance(et, str) or not et.strip()):
            result["ok"] = False
            result["errors"].append(f"event_candidates[{idx}].event_type is empty")
        # source_items must be array if present
        si = candidate.get("source_items")
        if si is not None and not isinstance(si, list):
            result["ok"] = False
            result["errors"].append(f"event_candidates[{idx}].source_items must be an array")
        # impact_vs_our_model must have pressure fields if present
        impact = candidate.get("impact_vs_our_model")
        if isinstance(impact, dict):
            for pf in ["price_pressure", "rights_pressure", "configuration_pressure", "delivery_pressure"]:
                if pf not in impact:
                    result["ok"] = False
                    result["errors"].append(f"event_candidates[{idx}].impact_vs_our_model missing: {pf}")

    # Check needs_review items (lenient)
    for idx, item in enumerate(data.get("needs_review", [])):
        if not isinstance(item, dict):
            continue
        reason = item.get("reason")
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            result["ok"] = False
            result["errors"].append(f"needs_review[{idx}].reason is empty")

    return result


def print_report(result: dict):
    """Print human-readable validation report."""
    status = "OK" if result["ok"] else "FAIL"
    print(f"[auto_launch validate] {status}")
    print(f"  type: {result['type']}")
    schema_name = result["type"]
    if schema_name in ("daily_monitor", "event", "brief"):
        print(f"  schema: auto_launch_{schema_name}.schema.json")
    else:
        print("  schema: unknown")
    print()
    for key, msg in sorted(result["checks"].items()):
        status_char = "✅" if msg == "ok" or msg.startswith("ok ") else "❌"
        print(f"  {status_char} {key}: {msg}")
    if result["errors"]:
        print()
        print("  Errors:")
        for err in result["errors"]:
            print(f"    - {err}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python validators/validate_ai_response.py <ai_output.json>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"[auto_launch validate] ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = run_validation(data)
    print_report(result)
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
