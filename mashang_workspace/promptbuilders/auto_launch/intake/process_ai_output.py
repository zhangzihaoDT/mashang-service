#!/usr/bin/env python3
"""
process_ai_output.py — 完整 AI output intake workflow。

一次性完成: validate → normalize → render markdown。
失败时返回非 0 exit code。

用法:
  python intake/process_ai_output.py path/to/ai_output.json \\
      --normalized-output path/to/normalized.json \\
      --report-output path/to/report.md

依赖: 无 (仅 Python 标准库)
"""

import json
import os
import sys
import argparse
from pathlib import Path

# ── Path setup for sibling imports ──────────────────────────────
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT = _THIS_DIR.parent  # promptbuilders/auto_launch/
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from validators.validate_ai_response import run_validation, print_report  # noqa: E402
from validators.normalize_ai_response import normalize  # noqa: E402
from renderers.render_markdown_report import render  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Validate, normalize, and render AI output")
    parser.add_argument("input", help="Path to AI output JSON file")
    parser.add_argument("--normalized-output", "-n", required=True, help="Path to write normalized JSON")
    parser.add_argument("--report-output", "-r", required=True, help="Path to write markdown report")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[auto_launch intake] ERROR: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Step 1: Validate
    print("[auto_launch intake] validating...")
    with open(args.input, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    result = run_validation(raw_data)
    if not result["ok"]:
        print("[auto_launch intake] VALIDATION FAILED")
        print_report(result)
        sys.exit(1)

    # Step 2: Normalize
    print("[auto_launch intake] normalizing...")
    normalized_data = normalize(raw_data)

    out_dir = os.path.dirname(args.normalized_output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.normalized_output, "w", encoding="utf-8") as f:
        json.dump(normalized_data, f, ensure_ascii=False, indent=2)

    print(f"[auto_launch intake] normalize OK: {args.normalized_output}")

    # Step 3: Render
    print("[auto_launch intake] rendering markdown...")
    md = render(normalized_data)

    report_dir = os.path.dirname(args.report_output)
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)

    with open(args.report_output, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"[auto_launch intake] report OK: {args.report_output}")
    print("[auto_launch intake] done")

    # Print summary
    record_type = normalized_data.get("record_type", "?")
    summary = normalized_data.get("executive_summary") or normalized_data.get("confirmed_facts", [""])[0] if normalized_data.get("confirmed_facts") else ""
    print(f"  type={record_type} | facts={len(normalized_data.get('confirmed_facts', []))} | "
          f"inferences={len(normalized_data.get('inferences', []))} | "
          f"unconfirmed={len(normalized_data.get('unconfirmed_claims', []))} | "
          f"missing_evidence={len(normalized_data.get('missing_evidence', []))}")
    sys.exit(0)


if __name__ == "__main__":
    main()
