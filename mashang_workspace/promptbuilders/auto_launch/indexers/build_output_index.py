#!/usr/bin/env python3
"""
build_output_index.py — 扫描 Auto Launch output directories 生成统一索引。

扫描指定 root 下包含 intake_manifest.json 的子目录，
读取 manifest 和 normalized.json 生成 index.json 和 index.md。

用法:
  python indexers/build_output_index.py \\
      --input-dir path/to/outputs/auto_launch \\
      --index-json path/to/index.json \\
      --index-md path/to/index.md

依赖: 无 (仅 Python 标准库)
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path


# ── Manifest field keys ─────────────────────────────────────────

MANIFEST_KEYS = [
    "record_type", "record_key", "confidence_level",
    "source_items_count", "confirmed_facts_count",
    "inferences_count", "unconfirmed_claims_count",
    "missing_evidence_count", "created_at",
]

NORMALIZED_KEYS = [
    "our_model", "event_model", "event_brand", "event_type", "battle_field",
]


def scan_runs(input_dir: str) -> tuple[list[dict], list[str]]:
    """Scan input_dir for subdirectories containing intake_manifest.json.

    Returns (records, warnings).
    """
    records = []
    warnings = []

    root = Path(input_dir)
    if not root.exists():
        return records, [f"input_dir does not exist: {input_dir}"]

    # Collect candidate directories (one level deep)
    candidates = sorted(
        p for p in root.iterdir() if p.is_dir()
    )

    for run_dir in candidates:
        manifest_path = run_dir / "intake_manifest.json"
        if not manifest_path.exists():
            continue

        # Read manifest
        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            warnings.append(f"corrupt manifest in {run_dir.name}: {e}")
            continue

        if not isinstance(manifest, dict):
            warnings.append(f"manifest not a dict in {run_dir.name}")
            continue

        # Build record from manifest
        record = {
            "run_dir": str(run_dir),
            "run_dir_name": run_dir.name,
        }

        for key in MANIFEST_KEYS:
            record[key] = manifest.get(key, None)

        # Try to supplement from normalized.json
        norm_path = run_dir / "normalized.json"
        if norm_path.exists():
            try:
                norm_data = json.loads(norm_path.read_text("utf-8"))
                if isinstance(norm_data, dict):
                    for key in NORMALIZED_KEYS:
                        if key not in record or record[key] is None:
                            record[key] = norm_data.get(key, None)
            except (json.JSONDecodeError, OSError):
                pass  # non-fatal

        # Resolve file paths
        FILE_MAP = {
            "report.md": "report_path",
            "normalized.json": "normalized_path",
            "raw_ai_output.json": "raw_ai_output_path",
        }
        for fname, field in FILE_MAP.items():
            fpath = run_dir / fname
            record[field] = str(fpath) if fpath.exists() else None

        records.append(record)

    # Sort by created_at descending, then by run_dir_name
    def sort_key(r):
        ts = r.get("created_at", "") or ""
        return (-ord(ts[0]) if ts else 0, r.get("run_dir_name", ""))

    records.sort(key=lambda r: (r.get("created_at", "") or "", r.get("run_dir_name", "")), reverse=True)

    return records, warnings


def build_index(input_dir: str, records: list[dict],
                warnings: list[str]) -> dict:
    """Build the index dict."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": os.path.abspath(input_dir),
        "total_records": len(records),
        "warnings": warnings if warnings else None,
        "records": records,
    }


def render_index_md(index: dict) -> str:
    """Render index dict to markdown."""
    lines = []
    lines.append("# Auto Launch Output Index\n")
    lines.append("## Summary\n")
    lines.append(f"- **total_records**: {index['total_records']}\n")
    lines.append(f"- **generated_at**: {index['generated_at']}\n")
    lines.append(f"- **input_dir**: {index['input_dir']}\n")

    if index.get("warnings"):
        lines.append("\n## Warnings\n")
        for w in index["warnings"]:
            lines.append(f"- ⚠️ {w}\n")

    if index['total_records'] == 0:
        lines.append("\n*暂无 intake 记录。*\n")
        return "".join(lines)

    lines.append("\n## Records\n")
    lines.append("| created_at | type | record_key | our_model | event_model | "
                 "event_type | battle_field | confidence | report |\n")
    lines.append("|------------|------|------------|-----------|-------------|"
                 "-------------|--------------|------------|--------|\n")

    for rec in index["records"]:
        created = _val(rec.get("created_at", ""), 16)
        rtype = _val(rec.get("record_type", ""), 4)
        rkey = _val(rec.get("record_key", ""), 10)
        ours = _val(rec.get("our_model") or "—", 9)
        ev_model = _val(rec.get("event_model") or "—", 11)
        ev_type = _val(rec.get("event_type") or "—", 11)
        bfield = _val(rec.get("battle_field") or "—", 12)
        conf = _val(rec.get("confidence_level") or "—", 10)

        report_path = rec.get("report_path")
        if report_path:
            # Convert to relative path if possible
            rel = os.path.relpath(report_path, start=index["input_dir"])
            report_cell = f"[📄 {rel}]({rel})"
        else:
            report_cell = "—"

        lines.append(f"| {created} | {rtype} | {rkey} | {ours} | {ev_model} | "
                     f"{ev_type} | {bfield} | {conf} | {report_cell} |\n")

    return "".join(lines)


def _val(s: str, length: int) -> str:
    """Truncate a string for table display."""
    s = str(s) if s is not None else ""
    return s[:length] if len(s) > length else s


def main():
    parser = argparse.ArgumentParser(
        description="Scan Auto Launch output directories and build index"
    )
    parser.add_argument("--input-dir", "-i", required=True,
                        help="Root directory containing intake output subdirs")
    parser.add_argument("--index-json", "-j", required=True,
                        help="Path to write index.json")
    parser.add_argument("--index-md", "-m", required=True,
                        help="Path to write index.md")
    args = parser.parse_args()

    records, warnings = scan_runs(args.input_dir)
    index = build_index(args.input_dir, records, warnings)

    # Write index.json
    out_dir = os.path.dirname(args.index_json)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.index_json, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"[auto_launch index] JSON OK: {args.index_json}")

    # Write index.md
    md_dir = os.path.dirname(args.index_md)
    if md_dir:
        os.makedirs(md_dir, exist_ok=True)
    md = render_index_md(index)
    with open(args.index_md, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[auto_launch index] MD OK: {args.index_md}")

    print(f"  total_records: {index['total_records']}")
    if warnings:
        print(f"  warnings: {len(warnings)}")
    sys.exit(0)


if __name__ == "__main__":
    main()
