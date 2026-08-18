#!/usr/bin/env python
"""
TP&MIX-ways — workspace 侧 smoke check。

仅做 workspace 验证和熟悉数据资产，不负责构建数据集。
使用 shared.loaders，不直接拼 parquet 路径，不读 raw_csv。

用法：
    python mashang_workspace/research_scripts/tp_and_mix_ways/check_tp_and_mix_ways_asset.py

输出：
    mashang_workspace/outputs/reports/tp_and_mix_ways_workspace_smoke.md
"""

from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from shared.loaders.tp_and_mix_ways_loader import (
    get_tp_and_mix_ways_dataset_root,
    list_tp_and_mix_ways_tables,
    load_tp_and_mix_ways_registry,
    load_tp_and_mix_ways_table,
)
from shared.schema.tp_and_mix_ways_schema import TP_AND_MIX_WAYS_TABLES

_WS_ROOT = _REPO_ROOT / "mashang_workspace"
REPORTS_DIR = _WS_ROOT / "outputs" / "reports"
SMOKE_REPORT_PATH = REPORTS_DIR / "tp_and_mix_ways_workspace_smoke.md"


def check_all_tables():
    registry = load_tp_and_mix_ways_registry()
    tables_from_registry = [t["table_name"] for t in registry.get("tables", [])]
    tables_from_loader = list_tp_and_mix_ways_tables()
    tables_from_schema = [t.table_name for t in TP_AND_MIX_WAYS_TABLES]

    print(f"[check] Registry tables: {len(tables_from_registry)}")
    print(f"[check] Loader tables:   {len(tables_from_loader)}")
    print(f"[check] Schema tables:   {len(tables_from_schema)}")

    assert len(tables_from_registry) == 6, f"Expected 6 in registry, got {len(tables_from_registry)}"
    assert len(tables_from_loader) == 6, f"Expected 6 from loader, got {len(tables_from_loader)}"
    assert len(tables_from_schema) == 6, f"Expected 6 in schema, got {len(tables_from_schema)}"
    assert tables_from_registry == tables_from_loader == tables_from_schema, \
        "Registry / Loader / Schema table lists don't match"

    rows = []
    for table_name in tables_from_registry:
        print(f"\n[check] Loading: {table_name} ...")
        df = load_tp_and_mix_ways_table(table_name)
        if df is None:
            print(f"  [FAIL] {table_name}: could not load")
            rows.append((table_name, "error", 0, 0, "N/A", "N/A", 0))
            continue

        date_min = str(df["date_month"].min()) if "date_month" in df.columns else "N/A"
        date_max = str(df["date_month"].max()) if "date_month" in df.columns else "N/A"
        sales_sum = float(df["sales"].sum()) if "sales" in df.columns else 0

        row = (
            table_name,
            "ok",
            len(df),
            len(df.columns),
            date_min,
            date_max,
            sales_sum,
        )
        rows.append(row)

        print(f"  rows={len(df)}, cols={list(df.columns)}")
        print(f"  date: {date_min} ~ {date_max}, sales_sum={sales_sum:.0f}")

    return rows


def generate_smoke_report(rows):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "# TP&MIX-ways — Workspace Smoke Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Loader: `shared.loaders.tp_and_mix_ways_loader`",
        f"Schema: `shared.schema.tp_and_mix_ways_schema`",
        f"Registry: `dataset/TP&MIX-ways/registry/tp_and_mix_ways_tables.json`",
        "",
        "---",
        "",
        "## Table Overview",
        "",
        "| Table | Status | Rows | Columns | Date Min | Date Max | Sales Sum |",
        "|-------|--------|------|---------|----------|----------|-----------|",
    ]
    for r in rows:
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]:.0f} |")

    n_ok = sum(1 for r in rows if r[1] == "ok")
    n_err = sum(1 for r in rows if r[1] == "error")
    lines.extend([
        "",
        "---",
        "",
        f"**Summary**: {n_ok} tables loaded successfully",
        f"**Errors**: {n_err}",
        "",
        "### Notes",
        "",
        "- This smoke check uses `shared.loaders`, not raw CSV paths.",
        "- No Parquet files were copied into workspace.",
        "- No raw CSV files were read.",
        "- This script does not build or modify the dataset.",
        "",
    ])
    if n_err > 0:
        lines.extend([
            "### Tables with errors",
            "",
        ])
        for r in rows:
            if r[1] == "error":
                lines.append(f"- **{r[0]}**: failed to load — check registry or parquet files\n")
        lines.append("")

    SMOKE_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[smoke] Report written: {SMOKE_REPORT_PATH}")


def main():
    print("=" * 60)
    print("TP&MIX-ways — Workspace Smoke Check")
    print("=" * 60)

    dset_root = get_tp_and_mix_ways_dataset_root()
    print(f"Dataset root: {dset_root}")
    assert dset_root.exists(), f"Dataset root not found: {dset_root}"

    rows = check_all_tables()
    generate_smoke_report(rows)

    n_ok = sum(1 for r in rows if r[1] == "ok")
    n_err = sum(1 for r in rows if r[1] == "error")
    print(f"\n{'=' * 60}")
    print(f"Smoke check complete: {n_ok} ok, {n_err} error(s)")
    print(f"Report: {SMOKE_REPORT_PATH}")

    if n_err > 0:
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()
