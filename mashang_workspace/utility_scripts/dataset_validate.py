#!/usr/bin/env python
"""
轻量 dataset 校验脚本 — 检查关键数据集是否存在、可读、非空，并报告数据最新时点。

校验清单来自 dataset/updater/dataset_registry.py（与 update_all_datasets.py 同源），
避免「更新清单 / 校验清单」漂移。

校验对象（8 个）:
  - dataset/order_data.parquet
  - dataset/config_attribute.parquet
  - dataset/assign_data.csv
  - dataset/test_drive_data.csv
  - dataset/lock_attribution_data.parquet
  - dataset/delivery_inventory.parquet
  - store_info.csv（仓库外 original 目录）
  - dataset/store_daily_leads.csv

用法:
    python mashang_workspace/utility_scripts/dataset_validate.py
    python mashang_workspace/utility_scripts/dataset_validate.py --json
"""

import sys, argparse, json, importlib.util
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_registry():
    path = REPO_ROOT / "dataset" / "updater" / "dataset_registry.py"
    spec = importlib.util.spec_from_file_location("mashang_dataset_registry", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 dataset registry: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mashang_dataset_registry"] = mod
    spec.loader.exec_module(mod)
    return mod


_registry = _load_registry()
DATASETS = _registry.DATASETS
_describe = _registry.describe


def validate_spec(spec) -> dict:
    d = _describe(spec)
    result = {
        "path": d["path"],
        "key": d["key"],
        "label": d["label"],
        "required": d["required"],
        "exists": d["exists"],
        "rows": d["rows"],
        "size_bytes": d["size_bytes"],
        "modified_at": d["file_mtime"],
        "data_asof": d["data_asof"],
        "data_asof_column": d["data_asof_column"],
        "warnings": [],
        "errors": [],
    }
    if not d["exists"]:
        result["errors"].append("file not found")
        return result

    if result["rows"] is not None and result["rows"] == 0:
        result["warnings"].append("file is empty (0 data rows)")
    if result["rows"] is None:
        result["warnings"].append("could not read row count")

    missing = [f for f in spec.key_fields if f not in d["columns"]]
    if missing:
        result["warnings"].append(f"missing key fields: {missing}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Dataset Validation Utility")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    file_results = [validate_spec(spec) for spec in DATASETS]

    has_errors = any(r["errors"] for r in file_results)
    has_warnings = any(r["warnings"] for r in file_results)
    critical_missing = any(
        r["errors"] and r["required"] for r in file_results
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
            asof = (
                f", asof={r['data_asof'][:16]} ({r['data_asof_column']})"
                if r["data_asof"]
                else ""
            )
            print(f"  {icon} {r['path']}: {status_str}, rows={rows}, size={size_kb:.0f}KB, mod={mod}{asof}")
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
