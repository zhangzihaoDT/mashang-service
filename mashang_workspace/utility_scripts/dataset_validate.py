#!/usr/bin/env python
"""
轻量 dataset 校验脚本 — 检查关键数据集是否存在、可读、非空。

校验对象:
  - dataset/order_data.parquet
  - dataset/config_attribute.parquet
  - dataset/assign_data.csv
  - dataset/test_drive_data.csv
  - dataset/lock_attribution_data.parquet

用法:
    python mashang_workspace/utility_scripts/dataset_validate.py
    python mashang_workspace/utility_scripts/dataset_validate.py --json
"""

import sys, argparse, json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"

DATASET_FILES = [
    {
        "path": "dataset/order_data.parquet",
        "key_fields": ["order_number", "lock_time"],
        "required": True,
    },
    {
        "path": "dataset/config_attribute.parquet",
        "key_fields": ["order_number"],
        "required": True,
    },
    {
        "path": "dataset/assign_data.csv",
        "key_fields": ["first_assign_time"],
        "required": True,
    },
    {
        "path": "dataset/test_drive_data.csv",
        "key_fields": [],
        "required": False,
    },
    {
        "path": "dataset/lock_attribution_data.parquet",
        "key_fields": [],
        "required": False,
    },
]


def _read_parquet_meta(filepath: Path) -> tuple[int | None, list[str]]:
    try:
        import pandas as pd
        df = pd.read_parquet(filepath)
        return len(df), list(df.columns)
    except Exception:
        return None, []


def _get_row_count(filepath: Path) -> int | None:
    try:
        if filepath.suffix == ".parquet":
            n, _ = _read_parquet_meta(filepath)
            return n
        elif filepath.suffix == ".csv":
            with open(filepath) as f:
                return sum(1 for _ in f) - 1
    except Exception:
        return None


def _get_columns(filepath: Path) -> list[str]:
    try:
        if filepath.suffix == ".parquet":
            _, cols = _read_parquet_meta(filepath)
            return cols
        elif filepath.suffix == ".csv":
            with open(filepath) as f:
                header = f.readline().strip()
                return [c.strip() for c in header.split(",")]
    except Exception:
        return []


def validate_file(spec: dict) -> dict:
    rel_path = spec["path"]
    full_path = DATASET_DIR / rel_path.split("/", 1)[1]
    result = {
        "path": rel_path,
        "exists": full_path.exists(),
        "rows": None,
        "size_bytes": None,
        "modified_at": None,
        "warnings": [],
        "errors": [],
    }
    if not result["exists"]:
        result["errors"].append("file not found")
        return result

    stat = full_path.stat()
    result["size_bytes"] = stat.st_size
    result["modified_at"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
    result["rows"] = _get_row_count(full_path)

    if result["rows"] is not None and result["rows"] == 0:
        result["warnings"].append("file is empty (0 data rows)")

    if result["rows"] is None:
        result["warnings"].append("could not read row count")

    key_fields = spec.get("key_fields", [])
    if key_fields:
        columns = _get_columns(full_path)
        missing = [f for f in key_fields if f not in columns]
        if missing:
            result["warnings"].append(f"missing key fields: {missing}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Dataset Validation Utility")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    file_results = [validate_file(spec) for spec in DATASET_FILES]

    has_errors = any(r["errors"] for r in file_results)
    has_warnings = any(r["warnings"] for r in file_results)
    critical_missing = any(
        r["errors"] and spec["required"]
        for r, spec in zip(file_results, DATASET_FILES)
    )

    if critical_missing:
        status = "error"
    elif has_errors or has_warnings:
        status = "warning"
    else:
        status = "ok"

    output = {
        "status": status,
        "checked_at": datetime.now().isoformat(),
        "files": file_results,
    }

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print("Dataset Validation Summary")
        print("=" * 50)
        for r in file_results:
            icon = "✅" if not r["errors"] else "❌"
            status_str = "OK" if not r["errors"] else "ERROR"
            if r["warnings"]:
                status_str = "WARN"
                icon = "⚠️"
            rows = r["rows"] if r["rows"] is not None else "?"
            size_kb = r["size_bytes"] / 1024 if r["size_bytes"] else 0
            mod = r["modified_at"][:19] if r["modified_at"] else "N/A"
            print(f"  {icon} {r['path']}: {status_str}, rows={rows}, size={size_kb:.0f}KB, mod={mod}")
            for w in r["warnings"]:
                print(f"       warning: {w}")
            for e in r["errors"]:
                print(f"       error: {e}")
        print(f"  Status: {status.upper()}")
        if critical_missing:
            print("  Critical files missing — dataset may be incomplete.")

    return 0 if status != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
