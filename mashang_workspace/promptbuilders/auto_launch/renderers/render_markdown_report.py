#!/usr/bin/env python3
"""
render_markdown_report.py — 将 normalized JSON 渲染为 markdown 简报。

只做格式渲染，不做事实推断。不访问网络，不调用 LLM。

用法:
  python renderers/render_markdown_report.py path/to/normalized.json --output path/to/report.md

依赖: 无 (仅 Python 标准库)
"""

import json
import os
import sys
import argparse


# ── Helpers ──────────────────────────────────────────────────────


def _fmt_list(items, heading="", empty_text="无"):
    """Render a list as markdown bullet points."""
    if not items:
        return f"{heading}（{empty_text}）\n" if heading else f"（{empty_text}）\n"
    lines = [f"{heading}\n" if heading else ""]
    for item in items:
        lines.append(f"- {item}\n")
    return "".join(lines)


def _fmt_structured(items, field_map, empty_text="无"):
    """Render a structured or simple list with dict-aware formatting.

    field_map: dict with:
        _main: list of keys to try for the main text line
        _sub: list of (key, label) tuples for sub-detail lines
    """
    if not items:
        return f"（{empty_text}）\n"
    sub_fields = field_map.get("_sub", [])
    lines = []
    for item in items:
        if isinstance(item, dict):
            main = None
            for key in field_map.get("_main", []):
                val = item.get(key)
                if val:
                    main = val
                    break
            if main:
                lines.append(f"- {main}\n")
            else:
                lines.append(f"- （未提供）\n")
            for key, label in sub_fields:
                val = item.get(key)
                if val is None or val == "" or val == []:
                    continue
                if isinstance(val, list):
                    val_str = ", ".join(str(v) for v in val)
                else:
                    val_str = str(val)
                lines.append(f"  - {label}: {val_str}\n")
        else:
            lines.append(f"- {item}\n")
    return "".join(lines)


CONFIRMED_MAP = {
    "_main": ["fact", "confirmed_fact", "事实"],
    "_sub": [
        ("source_ids", "来源"),
        ("source_id", "来源"),
        ("confidence_level", "置信度"),
        ("confidence", "置信度"),
    ],
}

INFERENCE_MAP = {
    "_main": ["inference", "推断"],
    "_sub": [
        ("basis", "依据"),
        ("source_ids", "来源"),
        ("source_id", "来源"),
        ("confidence_level", "置信度"),
        ("confidence", "置信度"),
    ],
}

CLAIM_MAP = {
    "_main": ["claim", "unconfirmed_claim", "说法"],
    "_sub": [
        ("source_ids", "来源"),
        ("source_id", "来源"),
        ("reason_unconfirmed", "未确认原因"),
        ("reason", "未确认原因"),
    ],
}

MISSING_MAP = {
    "_main": ["field", "missing_field", "evidence_gap", "证据缺口"],
    "_sub": [
        ("why_it_matters", "重要性"),
        ("suggested_followup", "后续补证"),
        ("followup", "后续补证"),
    ],
}

SALES_RESPONSE_MAP = {
    "_main": ["scenario", "场景"],
    "_sub": [
        ("suggested_response", "建议回应"),
        ("response", "建议回应"),
        ("evidence_basis", "证据基础"),
        ("confidence_level", "置信度"),
        ("confidence", "置信度"),
    ],
}


def _is_structured(items):
    """Check if items are structured (list of dicts) rather than plain strings."""
    if not items:
        return False
    for item in items:
        if isinstance(item, dict):
            return True
    return False


def _fmt_dict(d, indent=0):
    """Render a simple dict as key-value lines."""
    if not d:
        return "（无）\n"
    lines = []
    for k, v in d.items():
        prefix = "  " * indent
        if isinstance(v, dict):
            lines.append(f"{prefix}- **{k}**\n")
            for sk, sv in v.items():
                lines.append(f"{prefix}  - {sk}: {sv}\n")
        elif isinstance(v, list):
            lines.append(f"{prefix}- **{k}**: {', '.join(str(x) for x in v)}\n")
        else:
            lines.append(f"{prefix}- **{k}**: {v}\n")
    return "".join(lines)


def _fmt_source_items(items):
    """Render source_items as a markdown table, handling both naming conventions."""
    if not items:
        return "（无来源）\n"
    lines = ["| source_id | source_tier | source_name | source_url |\n",
             "|----------|-------------|-------------|-----------|\n"]
    for item in items:
        sid = item.get("source_id", "?")
        tier = item.get("source_tier") or item.get("tier") or "unknown"
        name = (item.get("source_name") or item.get("name")
                or item.get("source_title") or "?")
        url = item.get("source_url") or item.get("url") or "未提供"
        # Clean Markdown link format: [url](url) → url
        if isinstance(url, str) and "](" in url:
            import re
            m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', url.strip())
            if m:
                url = m.group(2)
        if isinstance(url, str) and not url.startswith("http") and url != "未提供":
            url = f"`{url}`"
        lines.append(f"| {sid} | {tier} | {name} | {url} |\n")
    return "".join(lines)


# ── Renderers ────────────────────────────────────────────────────


def render_brief(data: dict) -> str:
    """Render a brief-type normalized JSON to markdown."""
    raw = data.get("raw", data)
    sections = []

    # Title
    title = data.get("record_key", "Auto Launch 简报")
    sections.append(f"# {title}\n")

    # 1. Executive Summary
    summary = data.get("executive_summary") or raw.get("executive_summary") or ""
    sections.append("## 1. 一句话结论\n")
    sections.append(f"{summary}\n\n" if summary else "（未提供）\n\n")

    # 2. Basic Info
    sections.append("## 2. 基本信息\n\n")
    info_rows = [
        ("记录类型", data.get("record_type", "")),
        ("记录 ID", data.get("record_key", "")),
        ("我方车型（本品）", data.get("our_model") or "未指定"),
        ("事件车型", data.get("event_model") or ""),
        ("事件品牌", data.get("event_brand") or ""),
        ("事件类型", data.get("event_type") or ""),
        ("竞争战场", data.get("battle_field") or ""),
        ("时间窗口", _fmt_time_window(data.get("time_window", {}))),
        ("全局置信度", data.get("confidence_level", "未指定")),
    ]
    for label, value in info_rows:
        sections.append(f"- **{label}**: {value}\n")
    sections.append("\n")

    # 3. Confirmed Facts
    sections.append("## 3. 已确认事实\n\n")
    items = data.get("confirmed_facts", [])
    if _is_structured(items):
        sections.append(_fmt_structured(items, CONFIRMED_MAP, "无已确认事实"))
    else:
        sections.append(_fmt_list(items, empty_text="无已确认事实"))
    sections.append("\n")

    # 4. Inferences
    sections.append("## 4. 推断\n\n")
    items = data.get("inferences", [])
    if _is_structured(items):
        sections.append(_fmt_structured(items, INFERENCE_MAP, "无推断"))
    else:
        sections.append(_fmt_list(items, empty_text="无推断"))
    sections.append("\n")

    # 5. Unconfirmed Claims
    sections.append("## 5. 未确认说法\n\n")
    items = data.get("unconfirmed_claims", [])
    if _is_structured(items):
        sections.append(_fmt_structured(items, CLAIM_MAP, "无未确认说法"))
    else:
        sections.append(_fmt_list(items, empty_text="无未确认说法"))
    sections.append("\n")

    # 6. Missing Evidence
    sections.append("## 6. 证据缺口\n\n")
    items = data.get("missing_evidence", [])
    if _is_structured(items):
        sections.append(_fmt_structured(items, MISSING_MAP, "无缺失证据"))
    else:
        sections.append(_fmt_list(items, empty_text="无缺失证据"))
    sections.append("\n")

    # 7. Follow-up Recommendation
    sections.append("## 7. 后续追踪\n\n")
    fup = data.get("followup_recommendation", {})
    if fup:
        sections.append(_fmt_dict(fup))
    else:
        sections.append("（未提供）\n")
    sections.append("\n")

    # 8. Sources
    sections.append("## 8. 来源\n\n")
    sections.append(_fmt_source_items(data.get("source_items", [])))

    return "".join(sections)


def render_event(data: dict) -> str:
    """Render an event-type normalized JSON to markdown."""
    raw = data.get("raw", data)
    event_info = raw.get("event", {})
    sections = []

    # Title
    title = data.get("record_key", "Auto Launch 事件记录")
    sections.append(f"# {title}\n")

    # 1. Summary
    sections.append("## 1. 事件摘要\n\n")
    confirmed = data.get("confirmed_facts", [])
    if confirmed:
        first = confirmed[0]
        if isinstance(first, dict):
            first_str = first.get("fact") or first.get("confirmed_fact") or str(first)[:60]
        else:
            first_str = str(first)
        sections.append(f"共确认 **{len(confirmed)}** 项事实。关键事件：{first_str}\n\n")
    else:
        sections.append("（未提供事实摘要）\n\n")

    # 2. Basic Info
    sections.append("## 2. 基本信息\n\n")
    info_rows = [
        ("记录类型", data.get("record_type", "")),
        ("记录 ID", data.get("record_key", "")),
        ("事件品牌", data.get("event_brand") or event_info.get("brand", "")),
        ("事件车型", data.get("event_model") or event_info.get("model", "")),
        ("事件类型", data.get("event_type") or event_info.get("event_type", "")),
        ("事件日期", event_info.get("event_date", "未指定")),
        ("事件名称", event_info.get("event_name", "未指定")),
        ("地点", event_info.get("location", "未指定")),
        ("竞争战场", data.get("battle_field", "")),
        ("时间窗口", _fmt_time_window(data.get("time_window", {}))),
        ("全局置信度", data.get("confidence_level", "未指定")),
    ]
    for label, value in info_rows:
        sections.append(f"- **{label}**: {value}\n")
    sections.append("\n")

    # 3. Confirmed Facts
    sections.append("## 3. 已确认事实\n\n")
    items = data.get("confirmed_facts", [])
    if _is_structured(items):
        sections.append(_fmt_structured(items, CONFIRMED_MAP, "无已确认事实"))
    else:
        sections.append(_fmt_list(items, empty_text="无已确认事实"))
    sections.append("\n")

    # 4. Inferences
    sections.append("## 4. 推断\n\n")
    items = data.get("inferences", [])
    if _is_structured(items):
        sections.append(_fmt_structured(items, INFERENCE_MAP, "无推断"))
    else:
        sections.append(_fmt_list(items, empty_text="无推断"))
    sections.append("\n")

    # 5. Unconfirmed Claims
    sections.append("## 5. 未确认说法\n\n")
    items = data.get("unconfirmed_claims", [])
    if _is_structured(items):
        sections.append(_fmt_structured(items, CLAIM_MAP, "无未确认说法"))
    else:
        sections.append(_fmt_list(items, empty_text="无未确认说法"))
    sections.append("\n")

    # 6. Missing Evidence
    sections.append("## 6. 证据缺口\n\n")
    items = data.get("missing_evidence", [])
    if _is_structured(items):
        sections.append(_fmt_structured(items, MISSING_MAP, "无缺失证据"))
    else:
        sections.append(_fmt_list(items, empty_text="无缺失证据"))
    sections.append("\n")

    # 7. Follow-up
    sections.append("## 7. 后续追踪\n\n")
    fup = data.get("followup_recommendation", {})
    if fup:
        sections.append(_fmt_dict(fup))
    else:
        sections.append("（未提供）\n")
    sections.append("\n")

    # 8. Sources
    sections.append("## 8. 来源\n\n")
    sections.append(_fmt_source_items(data.get("source_items", [])))

    return "".join(sections)


def _fmt_time_window(tw):
    """Format time_window dict to readable string."""
    if not tw or not isinstance(tw, dict):
        return "未指定"
    start = tw.get("start", "")
    end = tw.get("end", "")
    desc = tw.get("description", "")
    if desc:
        return desc
    if start and end:
        return f"{start} 至 {end}"
    if start:
        return f"自 {start}"
    if end:
        return f"至 {end}"
    return "未指定"


def render(data: dict) -> str:
    """Render a normalized JSON to markdown, auto-detecting type."""
    record_type = data.get("record_type", "event")
    if record_type == "brief":
        return render_brief(data)
    return render_event(data)


def main():
    parser = argparse.ArgumentParser(description="Render normalized JSON to markdown report")
    parser.add_argument("input", help="Path to normalized JSON file")
    parser.add_argument("--output", "-o", required=True, help="Path to write markdown report")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[auto_launch render] ERROR: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    md = render(data)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"[auto_launch render] OK -> {args.output}")
    sys.exit(0)


if __name__ == "__main__":
    main()
