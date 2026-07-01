#!/usr/bin/env python3
"""
process_ai_output.py — 完整 AI output intake workflow。

一次性完成: validate → normalize → render markdown。
支持两种输出模式:
  1. --normalized-output + --report-output (精确指定路径)
  2. --output-dir (自动生成 4 个文件)

用法:
  # 模式 1: 精确指定路径
  python intake/process_ai_output.py input.json \\
      --normalized-output output.normalized.json \\
      --report-output output.md

  # 模式 2: 自动输出目录
  python intake/process_ai_output.py input.json \\
      --output-dir path/to/event_dir/

依赖: 无 (仅 Python 标准库)
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup for sibling imports ──────────────────────────────
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT = _THIS_DIR.parent  # promptbuilders/auto_launch/
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from validators.validate_ai_response import run_validation, print_report  # noqa: E402
from validators.normalize_ai_response import normalize  # noqa: E402
from renderers.render_markdown_report import render  # noqa: E402


def write_manifest(output_dir: str, input_path: str,
                   normalized_path: str, report_path: str,
                   normalized_data: dict) -> dict:
    """Write intake_manifest.json with processing metadata."""
    manifest = {
        "input_path": str(input_path),
        "normalized_path": str(normalized_path),
        "report_path": str(report_path),
        "record_type": normalized_data.get("record_type", "unknown"),
        "record_key": normalized_data.get("record_key", ""),
        "confidence_level": normalized_data.get("confidence_level", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_items_count": len(normalized_data.get("source_items", [])),
        "confirmed_facts_count": len(normalized_data.get("confirmed_facts", [])),
        "inferences_count": len(normalized_data.get("inferences", [])),
        "unconfirmed_claims_count": len(normalized_data.get("unconfirmed_claims", [])),
        "missing_evidence_count": len(normalized_data.get("missing_evidence", [])),
    }
    manifest_path = os.path.join(output_dir, "intake_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[auto_launch intake] manifest OK: {manifest_path}")
    return manifest


def write_daily_monitor_manifest(output_dir: str, input_path: str, payload: dict) -> dict:
    """Write intake_manifest.json for daily monitor."""
    ec = len(payload.get("event_candidates", []))
    nr = len(payload.get("needs_review", []))
    ne = len(payload.get("no_event_models", []))
    ds = len(payload.get("discovery_signals", []))
    sa = len(payload.get("search_audit", []))
    manifest = {
        "input_path": str(input_path),
        "normalized_path": os.path.join(output_dir, "normalized_daily_monitor.json"),
        "report_path": os.path.join(output_dir, "intake_summary.md"),
        "record_type": "daily_monitor",
        "record_key": f"daily_monitor_{payload.get('monitor_date', 'unknown')}",
        "confidence_level": "medium",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event_candidates_count": ec,
        "discovery_signals_count": ds,
        "needs_review_count": nr,
        "no_event_models_count": ne,
        "search_audit_count": sa,
    }
    manifest_path = os.path.join(output_dir, "intake_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[auto_launch intake] manifest OK: {manifest_path}")
    return manifest


def render_daily_monitor_summary(payload: dict) -> str:
    """Render intake_summary.md for daily monitor."""
    ec = payload.get("event_candidates", [])
    nr = payload.get("needs_review", [])
    ne = payload.get("no_event_models", [])
    ds = payload.get("discovery_signals", [])
    sa = payload.get("search_audit", [])
    lines = []
    lines.append("# Auto Launch Daily Monitor Intake Summary\n")
    lines.append(f"- task_name: {payload.get('task_name', '')}\n")
    lines.append(f"- monitor_date: {payload.get('monitor_date', '')}\n")
    lines.append(f"- battle_field: {payload.get('battle_field', '')}\n")
    lines.append(f"- our_model: {payload.get('our_model', '')}\n")
    lines.append(f"- event_candidates: {len(ec)}\n")
    lines.append(f"- discovery_signals: {len(ds)}\n")
    lines.append(f"- needs_review: {len(nr)}\n")
    lines.append(f"- no_event_models: {len(ne)}\n")
    lines.append(f"- search_audit: {len(sa)}\n")
    lines.append("\n## Event Candidates\n")
    if ec:
        for c in ec:
            lines.append(f"- {c.get('event_model', '?')} | {c.get('event_type', '?')} | {c.get('confidence', '?')} | {c.get('event_date', '?')}\n")
    else:
        lines.append("None\n")
    lines.append("\n## Discovery Signals\n")
    if ds:
        for s in ds:
            lines.append(f"- {s.get('event_model', '?')} | {s.get('signal_type', '?')} | {s.get('possible_event_type', '?')} | {s.get('confidence', '?')} | {s.get('why_not_candidate', '?')}\n")
    else:
        lines.append("None\n")
    lines.append("\n## Needs Review\n")
    if nr:
        for item in nr:
            lines.append(f"- {item.get('event_model', '?')} | {item.get('reason', '?')}\n")
    else:
        lines.append("None\n")
    lines.append("\n## No Event Models\n")
    if ne:
        for m in ne:
            lines.append(f"- {m}\n")
    else:
        lines.append("None\n")
    lines.append("\n## Search Audit\n")
    if sa:
        for a in sa:
            sl = a.get("searched_layers", {})
            lines.append(f"- {a.get('event_model', '?')} | official={sl.get('official_confirmation','?')} media={sl.get('media_cross_check','?')} weak={sl.get('sales_weak_signals','?')} | {a.get('coverage_note', '')}\n")
    else:
        lines.append("None\n")
    return "".join(lines)


def process_daily_monitor(payload: dict, output_dir: str, input_path: str):
    """Process Daily Sales Action Monitor output."""
    os.makedirs(output_dir, exist_ok=True)

    # Write normalized (full payload passthrough with type annotation)
    normalized = dict(payload)
    normalized["record_type"] = "daily_monitor"
    norm_path = os.path.join(output_dir, "normalized_daily_monitor.json")
    with open(norm_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    print(f"[auto_launch intake] normalize OK: {norm_path}")

    # Write event_candidates (default to [] if missing)
    ec_path = os.path.join(output_dir, "event_candidates.json")
    with open(ec_path, "w", encoding="utf-8") as f:
        json.dump(payload.get("event_candidates", []), f, ensure_ascii=False, indent=2)
    print(f"[auto_launch intake] event_candidates OK: {ec_path}")

    # Write discovery_signals (default to [] if missing)
    ds_path = os.path.join(output_dir, "discovery_signals.json")
    with open(ds_path, "w", encoding="utf-8") as f:
        json.dump(payload.get("discovery_signals", []), f, ensure_ascii=False, indent=2)
    print(f"[auto_launch intake] discovery_signals OK: {ds_path}")

    # Write needs_review
    nr_path = os.path.join(output_dir, "needs_review.json")
    with open(nr_path, "w", encoding="utf-8") as f:
        json.dump(payload.get("needs_review", []), f, ensure_ascii=False, indent=2)
    print(f"[auto_launch intake] needs_review OK: {nr_path}")

    # Write no_event_models
    ne_path = os.path.join(output_dir, "no_event_models.json")
    with open(ne_path, "w", encoding="utf-8") as f:
        json.dump(payload.get("no_event_models", []), f, ensure_ascii=False, indent=2)
    print(f"[auto_launch intake] no_event_models OK: {ne_path}")

    # Write search_audit (default to [] if missing)
    sa_path = os.path.join(output_dir, "search_audit.json")
    with open(sa_path, "w", encoding="utf-8") as f:
        json.dump(payload.get("search_audit", []), f, ensure_ascii=False, indent=2)
    print(f"[auto_launch intake] search_audit OK: {sa_path}")

    # Write intake_summary.md
    md = render_daily_monitor_summary(payload)
    summary_path = os.path.join(output_dir, "intake_summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[auto_launch intake] summary OK: {summary_path}")

    # Write manifest
    write_daily_monitor_manifest(output_dir, input_path, payload)

    # Summary
    ec_count = len(payload.get("event_candidates", []))
    ds_count = len(payload.get("discovery_signals", []))
    nr_count = len(payload.get("needs_review", []))
    ne_count = len(payload.get("no_event_models", []))
    sa_count = len(payload.get("search_audit", []))
    print(f"[auto_launch intake] done")
    print(f"  type=daily_monitor | candidates={ec_count} | signals={ds_count} | review={nr_count} | no_event={ne_count} | search_audit={sa_count}")


def process_legacy_json(payload: dict, output_dir: str, input_path: str,
                         norm_output_path: str, report_output_path: str,
                         has_output_dir: bool):
    """Process legacy event/brief format."""
    raw_output_path = os.path.join(output_dir, "raw_ai_output.json") if has_output_dir else None

    # Write raw copy (output-dir mode only)
    if raw_output_path:
        with open(raw_output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[auto_launch intake] raw OK: {raw_output_path}")

    # Normalize
    normalized_data = normalize(payload)
    if norm_output_path:
        ndir = os.path.dirname(norm_output_path)
        if ndir:
            os.makedirs(ndir, exist_ok=True)
        with open(norm_output_path, "w", encoding="utf-8") as f:
            json.dump(normalized_data, f, ensure_ascii=False, indent=2)
        print(f"[auto_launch intake] normalize OK: {norm_output_path}")

    # Render markdown
    if report_output_path:
        print("[auto_launch intake] rendering markdown...")
        md = render(normalized_data)
        rdir = os.path.dirname(report_output_path)
        if rdir:
            os.makedirs(rdir, exist_ok=True)
        with open(report_output_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"[auto_launch intake] report OK: {report_output_path}")

    # Manifest
    if has_output_dir:
        write_manifest(output_dir, input_path,
                       norm_output_path, report_output_path,
                       normalized_data)

    record_type = normalized_data.get("record_type", "?")
    print(f"[auto_launch intake] done")
    print(f"  type={record_type} | facts={len(normalized_data.get('confirmed_facts', []))} | "
          f"inferences={len(normalized_data.get('inferences', []))} | "
          f"unconfirmed={len(normalized_data.get('unconfirmed_claims', []))} | "
          f"missing_evidence={len(normalized_data.get('missing_evidence', []))}")


def main():
    parser = argparse.ArgumentParser(description="Validate, normalize, and render AI output")
    parser.add_argument("input", help="Path to AI output JSON file")
    parser.add_argument("--normalized-output", "-n", help="Path to write normalized JSON")
    parser.add_argument("--report-output", "-r", help="Path to write markdown report")
    parser.add_argument("--output-dir", "-o", help="Output directory (auto-generates all files)")
    args = parser.parse_args()

    # ── Validate modes ──────────────────────────────────────────────
    has_explicit = args.normalized_output is not None or args.report_output is not None
    has_output_dir = args.output_dir is not None

    if not has_explicit and not has_output_dir:
        print("[auto_launch intake] ERROR: specify either --output-dir or "
              "--normalized-output + --report-output", file=sys.stderr)
        sys.exit(1)

    if has_explicit and has_output_dir:
        print("[auto_launch intake] ERROR: cannot use both --output-dir and "
              "--normalized-output/--report-output", file=sys.stderr)
        sys.exit(1)

    if has_explicit and (args.normalized_output is None or args.report_output is None):
        print("[auto_launch intake] ERROR: --normalized-output and --report-output must be used together",
              file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"[auto_launch intake] ERROR: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # ── Read input ─────────────────────────────────────────────────
    print("[auto_launch intake] validating...")
    with open(args.input, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # ── Detect type and branch ─────────────────────────────────────
    is_daily_monitor = raw_data.get("task_name") == "auto_launch_daily_sales_action_monitor"

    result = run_validation(raw_data)
    if not result["ok"]:
        print("[auto_launch intake] VALIDATION FAILED")
        print_report(result)
        sys.exit(1)

    # ── Resolve output directory ────────────────────────────────────
    if has_output_dir:
        output_dir = args.output_dir
    else:
        output_dir = os.path.dirname(args.normalized_output) if args.normalized_output else ""

    # ── Branch: Daily Monitor vs Legacy ────────────────────────────
    if is_daily_monitor:
        process_daily_monitor(raw_data, output_dir, args.input)
    else:
        if has_output_dir:
            norm_output_path = os.path.join(output_dir, "normalized.json")
            report_output_path = os.path.join(output_dir, "report.md")
        else:
            norm_output_path = args.normalized_output
            report_output_path = args.report_output
        process_legacy_json(raw_data, output_dir, args.input,
                           norm_output_path, report_output_path,
                           has_output_dir)

    sys.exit(0)


if __name__ == "__main__":
    main()
