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
    """Detect whether the JSON is event or brief type."""
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
        result["errors"].append("cannot determine type (neither event nor brief)")
        return result

    # Determine which fields to check
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


def print_report(result: dict):
    """Print human-readable validation report."""
    status = "OK" if result["ok"] else "FAIL"
    print(f"[auto_launch validate] {status}")
    print(f"  type: {result['type']}")
    print(f"  schema: auto_launch_{result['type']}.schema.json" if result["type"] != "unknown" else "  schema: unknown")
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
