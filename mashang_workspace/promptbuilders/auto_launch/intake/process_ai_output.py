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

    # ── Step 1: Validate ────────────────────────────────────────────
    print("[auto_launch intake] validating...")
    with open(args.input, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    result = run_validation(raw_data)
    if not result["ok"]:
        print("[auto_launch intake] VALIDATION FAILED")
        print_report(result)
        sys.exit(1)

    # ── Step 2: Normalize ───────────────────────────────────────────
    print("[auto_launch intake] normalizing...")
    normalized_data = normalize(raw_data)

    # ── Resolve output paths ────────────────────────────────────────
    if has_output_dir:
        output_dir = args.output_dir
        os.makedirs(output_dir, exist_ok=True)
        raw_output_path = os.path.join(output_dir, "raw_ai_output.json")
        norm_output_path = os.path.join(output_dir, "normalized.json")
        report_output_path = os.path.join(output_dir, "report.md")
    else:
        output_dir = os.path.dirname(args.normalized_output) if args.normalized_output else ""
        raw_output_path = None
        norm_output_path = args.normalized_output
        report_output_path = args.report_output

    # ── Write raw copy (output-dir mode only) ───────────────────────
    if raw_output_path:
        with open(raw_output_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2)
        print(f"[auto_launch intake] raw OK: {raw_output_path}")

    # ── Write normalized JSON ───────────────────────────────────────
    if norm_output_path:
        ndir = os.path.dirname(norm_output_path)
        if ndir:
            os.makedirs(ndir, exist_ok=True)
        with open(norm_output_path, "w", encoding="utf-8") as f:
            json.dump(normalized_data, f, ensure_ascii=False, indent=2)
        print(f"[auto_launch intake] normalize OK: {norm_output_path}")

    # ── Render markdown ─────────────────────────────────────────────
    if report_output_path:
        print("[auto_launch intake] rendering markdown...")
        md = render(normalized_data)
        rdir = os.path.dirname(report_output_path)
        if rdir:
            os.makedirs(rdir, exist_ok=True)
        with open(report_output_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"[auto_launch intake] report OK: {report_output_path}")

    # ── Write manifest (output-dir mode only) ───────────────────────
    if has_output_dir:
        write_manifest(output_dir, args.input,
                       norm_output_path, report_output_path,
                       normalized_data)

    # ── Summary ─────────────────────────────────────────────────────
    print("[auto_launch intake] done")
    record_type = normalized_data.get("record_type", "?")
    print(f"  type={record_type} | facts={len(normalized_data.get('confirmed_facts', []))} | "
          f"inferences={len(normalized_data.get('inferences', []))} | "
          f"unconfirmed={len(normalized_data.get('unconfirmed_claims', []))} | "
          f"missing_evidence={len(normalized_data.get('missing_evidence', []))}")
    sys.exit(0)


if __name__ == "__main__":
    main()
