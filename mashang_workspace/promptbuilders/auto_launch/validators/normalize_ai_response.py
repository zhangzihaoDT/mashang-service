#!/usr/bin/env python3
"""
normalize_ai_response.py — 将 AI 输出 JSON 归一化为统一结构的 normalized JSON。

用法:
  python validators/normalize_ai_response.py path/to/ai_output.json --output path/to/normalized.json

依赖: 无 (仅 Python 标准库)
"""

import json
import os
import sys
import argparse
from pathlib import Path

# Ensure validators/ is importable for sibling module access
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from validate_ai_response import run_validation  # noqa: E402


# ── Normalized output structure ─────────────────────────────────

NORMALIZED_KEYS = [
    "record_type",
    "record_key",
    "our_model",
    "event_model",
    "event_brand",
    "event_type",
    "battle_field",
    "time_window",
    "confidence_level",
    "source_items",
    "confirmed_facts",
    "inferences",
    "unconfirmed_claims",
    "missing_evidence",
    "followup_recommendation",
    "raw",
]


def build_record_key(data: dict, doc_type: str) -> str:
    """Generate a stable record_key from available fields."""
    if doc_type == "event":
        eid = data.get("event_id", "")
        if eid:
            return eid
        parts = [data.get("event_brand", ""), data.get("event_model", ""),
                 data.get("event_type", ""), str(data.get("event_date", ""))]
        return "_".join(p for p in parts if p)
    if doc_type == "brief":
        bid = data.get("brief_id", "")
        if bid:
            return bid
        parts = ["brief", data.get("event_brand", ""), data.get("event_model", ""),
                 data.get("event_type", ""), str(data.get("event_date", ""))]
        return "_".join(p for p in parts if p)
    return "unknown"


def extract_time_window(data: dict, doc_type: str):
    """Extract or build a time_window string."""
    if doc_type == "event":
        tw = data.get("event_time_window", {})
        if isinstance(tw, dict):
            start = tw.get("start", "")
            end = tw.get("end", "")
            if start or end:
                return {"start": start, "end": end}
    # Try top-level time_window
    tw = data.get("time_window", {})
    if isinstance(tw, dict) and (tw.get("start") or tw.get("end")):
        return tw
    # Fallback: string or null
    if isinstance(tw, str) and tw:
        return {"start": "", "end": "", "description": tw}
    return {"start": "", "end": ""}


def extract_followup(data: dict, doc_type: str):
    """Extract followup_recommendation."""
    recommendation = data.get("followup_recommendation", {})
    if isinstance(recommendation, str) and recommendation:
        return {"action": recommendation}
    if isinstance(recommendation, dict):
        return recommendation
    # Try top-level followup_recommendation string
    if isinstance(data.get("followup_recommendation"), str):
        return {"action": data["followup_recommendation"]}
    return {}


def _clean_url(url: str) -> str:
    """Clean a source_url: strip Markdown link format, whitespace, etc."""
    if not isinstance(url, str):
        return ""
    url = url.strip()
    # [url](url) → url
    if "](" in url:
        import re
        m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', url)
        if m:
            url = m.group(2).strip()
    return url


def normalize(data: dict) -> dict:
    """Normalize an AI output JSON into the unified structure."""
    result = run_validation(data)
    doc_type = result["type"] if result["type"] != "unknown" else "event"

    # Clean source_items: pass through original fields + clean URL
    raw_items = data.get("source_items", [])
    cleaned_items = []
    for item in raw_items:
        if isinstance(item, dict):
            item = dict(item)
            url = item.get("source_url") or item.get("url", "")
            item["source_url"] = _clean_url(str(url))
            item.pop("url", None)  # normalize to source_url
        cleaned_items.append(item)

    normalized = {
        "record_type": doc_type,
        "record_key": build_record_key(data, doc_type),
        "our_model": data.get("our_model") if doc_type == "brief" else (data.get("our_model") or None),
        "event_model": data.get("event_model", data.get("event", {}).get("model", "")),
        "event_brand": data.get("event_brand", data.get("event", {}).get("brand", "")),
        "event_type": data.get("event_type", data.get("event", {}).get("event_type", "")),
        "battle_field": data.get("battle_field", ""),
        "time_window": extract_time_window(data, doc_type),
        "confidence_level": data.get("confidence_level", "unknown"),
        "source_items": cleaned_items,
        "confirmed_facts": data.get("confirmed_facts", []),
        "inferences": data.get("inferences", []),
        "unconfirmed_claims": data.get("unconfirmed_claims", []),
        "missing_evidence": data.get("missing_evidence", data.get("unresolved_questions", [])),
        "followup_recommendation": extract_followup(data, doc_type),
        "raw": data,
    }

    return normalized


def main():
    parser = argparse.ArgumentParser(description="Normalize AI output JSON into unified structure")
    parser.add_argument("input", help="Path to AI output JSON file")
    parser.add_argument("--output", "-o", required=True, help="Path to write normalized JSON")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[auto_launch normalize] ERROR: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    normalized = normalize(data)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(f"[auto_launch normalize] OK -> {args.output}")
    print(f"  record_type: {normalized['record_type']}")
    print(f"  record_key: {normalized['record_key']}")
    print(f"  source_items: {len(normalized['source_items'])}")
    print(f"  confirmed_facts: {len(normalized['confirmed_facts'])}")
    print(f"  inferences: {len(normalized['inferences'])}")
    print(f"  unconfirmed_claims: {len(normalized['unconfirmed_claims'])}")
    print(f"  missing_evidence: {len(normalized['missing_evidence'])}")


if __name__ == "__main__":
    main()
