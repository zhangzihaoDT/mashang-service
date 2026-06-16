#!/usr/bin/env python3
"""
Build passenger_insurance dataset from raw Tableau CSV exports.

Reads 6 tab-delimited UTF-16 LE CSVs from dataset/passenger_insurance/raw_csv/,
widens pivot format (度量名称/度量值 → columns), cleans & validates,
then outputs Parquet, registry JSON, and quality reports.

Usage:
    python scripts/build_passenger_insurance_dataset.py
"""

from __future__ import annotations
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ---- paths ----
SERVICE_ROOT = Path(__file__).resolve().parent.parent
RAW_CSV_DIR = SERVICE_ROOT / "dataset" / "passenger_insurance" / "raw_csv"
PARQUET_DIR = SERVICE_ROOT / "dataset" / "passenger_insurance" / "parquet"
REGISTRY_DIR = SERVICE_ROOT / "dataset" / "passenger_insurance" / "registry"
QUALITY_DIR = SERVICE_ROOT / "dataset" / "passenger_insurance" / "quality"

REGISTRY_PATH = REGISTRY_DIR / "passenger_insurance_tables.json"
QUALITY_MD_PATH = QUALITY_DIR / "passenger_insurance_dataset_quality.md"
QUALITY_JSON_PATH = QUALITY_DIR / "passenger_insurance_dataset_quality.json"


# ---- source mapping (actual filename → internal table name) ----
SOURCE_MAP: Dict[str, str] = {
    "way1_market_energy_monthly_data.csv": "market_energy_monthly",
    "way2_brand_monthly_data.csv": "brand_monthly",
    "way3_model_monthly_data.csv": "model_monthly",
    "way4_geo_monthly_data.csv": "geo_monthly",
    "way5_price_segment_monthly_data.csv": "price_segment_monthly",
    "way6_product_segment_monthly_data.csv": "product_segment_monthly",
}

# ---- column mappings (Chinese → English snake_case) ----
# Each entry: (Chinese column name including trailing spaces, English name)
COLUMN_MAP: Dict[str, List[Tuple[str, str]]] = {
    "market_energy_monthly": [
        ("日期 年/月", "date_month"),
        ("燃料类型 (组)", "fuel_type_group"),
        ("燃料类型", "fuel_type"),
        ("度量名称", "_measure_name"),
        ("度量值", "_measure_value"),
    ],
    "brand_monthly": [
        ("日期 年/月", "date_month"),
        ("品牌", "brand"),
        ("品牌 (组)", "brand_group"),
        ("品牌 (新豪华分组) ", "brand_luxury_group"),
        ("厂商", "oem"),
        ("厂商集团", "oem_group"),
        ("品牌国别", "brand_country"),
        ("所有权", "ownership_type"),
        ("国产/进口", "domestic_import"),
        ("度量名称", "_measure_name"),
        ("度量值", "_measure_value"),
    ],
    "model_monthly": [
        ("日期 年/月", "date_month"),
        ("品牌", "brand"),
        ("品牌系别", "brand_series"),
        ("SUB_MODEL_ID", "sub_model_id"),
        ("车型", "model"),
        ("子车型", "sub_model"),
        ("燃料类型", "fuel_type"),
        ("燃料类型 (组)", "fuel_type_group"),
        ("车身形式", "body_type"),
        ("车型级别", "vehicle_level"),
        ("车型级别 (组)", "vehicle_level_group"),
        ("上汽细分市场", "saic_segment"),
        ("驱动形式", "drive_type"),
        ("驱动形式 (组)", "drive_type_group"),
        ("度量名称", "_measure_name"),
        ("度量值", "_measure_value"),
    ],
    "geo_monthly": [
        ("日期 年/月", "date_month"),
        ("省", "province"),
        ("市", "city"),
        ("区域划分", "region_group"),
        ("燃料类型 (组)", "fuel_type_group"),
        ("25年城市级别", "city_tier_2025"),
        ("25年城市级别 (组)", "city_tier_group"),
        ("度量名称", "_measure_name"),
        ("度量值", "_measure_value"),
    ],
    "price_segment_monthly": [
        ("日期 年/月", "date_month"),
        ("TP 5万1档", "tp_bucket_5w"),
        ("TP 10万1档", "tp_bucket_10w"),
        ("燃料类型 (组)", "fuel_type_group"),
        ("车身形式", "body_type"),
        ("车型级别 (组)", "vehicle_level_group"),
        ("度量名称", "_measure_name"),
        ("度量值", "_measure_value"),
    ],
    "product_segment_monthly": [
        ("日期 年/月", "date_month"),
        ("上汽细分市场", "saic_segment"),
        ("车身形式", "body_type"),
        ("车型级别", "vehicle_level"),
        ("车型级别 (组)", "vehicle_level_group"),
        ("燃料类型 (组)", "fuel_type_group"),
        ("驱动形式 (组)", "drive_type_group"),
        ("度量名称", "_measure_name"),
        ("度量值", "_measure_value"),
    ],
}

# ---- grain definitions ----
GRAIN_DEFS: Dict[str, List[str]] = {
    "market_energy_monthly": ["date_month", "fuel_type_group", "fuel_type"],
    "brand_monthly": ["date_month", "brand"],
    "model_monthly": ["date_month", "brand", "model", "sub_model", "sub_model_id"],
    "geo_monthly": ["date_month", "province", "city", "city_tier_group", "fuel_type_group"],
    "price_segment_monthly": ["date_month", "tp_bucket_5w", "tp_bucket_10w", "fuel_type_group", "body_type", "vehicle_level_group"],
    "product_segment_monthly": ["date_month", "saic_segment", "body_type", "vehicle_level", "vehicle_level_group", "fuel_type_group", "drive_type_group"],
}

# ---- output parquet filenames ----
PARQUET_FILENAMES: Dict[str, str] = {
    "market_energy_monthly": "market_energy_monthly.parquet",
    "brand_monthly": "brand_monthly.parquet",
    "model_monthly": "model_monthly.parquet",
    "geo_monthly": "geo_monthly.parquet",
    "price_segment_monthly": "price_segment_monthly.parquet",
    "product_segment_monthly": "product_segment_monthly.parquet",
}


def _parse_date_month(raw: str) -> Optional[str]:
    raw = raw.strip()
    try:
        dt = datetime.strptime(raw, "%Y年%m月")
        return dt.strftime("%Y-%m-01")
    except ValueError:
        try:
            dt = datetime.strptime(raw, "%Y年%-m月")
            return dt.strftime("%Y-%m-01")
        except ValueError:
            return None


def _to_numeric(val: Any) -> Optional[float]:
    if val is None:
        return None
    cleaned = str(val).strip().replace(",", "").replace(" ", "")
    if cleaned == "" or cleaned == "-":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _strip_column_spaces(header: List[str]) -> List[str]:
    return [h.strip() for h in header]


def read_and_widen_csv(csv_path: Path, table_name: str) -> pd.DataFrame:
    col_map = dict(COLUMN_MAP[table_name])
    measure_name_col = "_measure_name"
    measure_value_col = "_measure_value"

    with open(csv_path, encoding="utf-16-le", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        raw_header = next(reader)
        raw_header = [h.lstrip("\ufeff") for h in raw_header]

    normalized_col_map = {k.strip(): v for k, v in col_map.items()}

    col_mapping = {}
    for i, raw_col in enumerate(raw_header):
        stripped = raw_col.strip()
        if stripped in normalized_col_map:
            col_mapping[i] = normalized_col_map[stripped]
        else:
            print(f"  [warn] unmapped column [{i}] '{raw_col}' in {csv_path.name}")

    rows = []
    with open(csv_path, encoding="utf-16-le", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)
        for row in reader:
            if len(row) < len(raw_header):
                continue
            parsed = {}
            for i, val in enumerate(row):
                if i in col_mapping:
                    parsed[col_mapping[i]] = val.strip()
            if parsed:
                rows.append(parsed)

    if not rows:
        raise ValueError(f"No data rows read from {csv_path.name}")

    raw_df = pd.DataFrame(rows)

    measure_names = raw_df[measure_name_col].unique()
    print(f"  measure names found: {sorted(measure_names)}")

    wide_rows = []
    dim_cols = [c for c in raw_df.columns if c not in (measure_name_col, measure_value_col)]
    for (group_keys), group in raw_df.groupby(dim_cols, sort=False):
        row_data = dict(zip(dim_cols, group_keys))
        for _, r in group.iterrows():
            mname = r[measure_name_col]
            mval = r[measure_value_col]
            row_data[mname] = mval
        wide_rows.append(row_data)

    wide_df = pd.DataFrame(wide_rows)

    known_measures = {
        "销量": "sales",
        "TP重心": "weighted_tp",
        "加权长(mm)": "weighted_length_mm",
        "加权宽(mm)": "weighted_width_mm",
        "加权高(mm)": "weighted_height_mm",
        "加权轴距(mm)": "weighted_wheelbase_mm",
    }

    for cn, en in known_measures.items():
        if cn in wide_df.columns:
            wide_df.rename(columns={cn: en}, inplace=True)
            wide_df[en] = wide_df[en].apply(_to_numeric)

    wide_df.drop(columns=[measure_name_col, measure_value_col], inplace=True, errors="ignore")

    wide_df["date_month"] = wide_df["date_month"].apply(_parse_date_month)
    before = len(wide_df)
    wide_df.dropna(subset=["date_month"], inplace=True)
    after = len(wide_df)
    if before > after:
        print(f"  dropped {before - after} rows with unparseable date_month")

    for enum_col in ["sales", "weighted_tp", "weighted_length_mm",
                     "weighted_width_mm", "weighted_height_mm", "weighted_wheelbase_mm"]:
        if enum_col in wide_df.columns:
            wide_df[enum_col] = pd.to_numeric(wide_df[enum_col], errors="coerce")

    return wide_df


def _build_quality_report(
    table_name: str,
    df: pd.DataFrame,
    grain_cols: List[str],
    parquet_path: Path,
    build_status: str,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "table_name": table_name,
        "build_status": build_status,
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": list(df.columns),
    }

    if "date_month" in df.columns:
        valid_dates = df["date_month"].dropna()
        if len(valid_dates) > 0:
            report["date_min"] = str(valid_dates.min())
            report["date_max"] = str(valid_dates.max())
        else:
            report["date_min"] = None
            report["date_max"] = None
    else:
        report["date_min"] = None
        report["date_max"] = None

    if "sales" in df.columns:
        report["sales_null_count"] = int(df["sales"].isna().sum())
        report["sales_negative_count"] = int((df["sales"] < 0).sum())
    else:
        report["sales_null_count"] = None
        report["sales_negative_count"] = None

    if "weighted_tp" in df.columns:
        report["weighted_tp_null_count"] = int(df["weighted_tp"].isna().sum())
    else:
        report["weighted_tp_null_count"] = None

    if grain_cols and all(c in df.columns for c in grain_cols):
        dup_mask = df.duplicated(subset=grain_cols, keep=False)
        dup_count = int(dup_mask.sum())
        report["duplicate_grain_count"] = dup_count
        if dup_count > 0:
            dups = df[dup_mask].sort_values(by=grain_cols).head(20)
            report["duplicate_grain_keys"] = [
                {c: str(v) for c, v in r.items() if c in grain_cols}
                for _, r in dups.iterrows()
            ]
        else:
            report["duplicate_grain_keys"] = []
    else:
        report["duplicate_grain_count"] = None
        report["duplicate_grain_keys"] = []

    if "date_month" in df.columns and "sales" in df.columns:
        monthly = df.groupby("date_month")["sales"].sum().to_dict()
        report["total_sales_by_month"] = {str(k): float(v) for k, v in sorted(monthly.items())}
    else:
        report["total_sales_by_month"] = {}

    report["parquet_output_path"] = str(parquet_path.resolve())

    return report


def _format_quality_markdown(all_reports: List[Dict[str, Any]]) -> str:
    lines = [
        "# Passenger Insurance Dataset — Quality Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
    ]
    for r in all_reports:
        dup_flag = "WARNING" if (r.get("duplicate_grain_count") or 0) > 0 else "PASS"
        lines.append(f"## {r['table_name']} — {r['build_status']} ({dup_flag})")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| row_count | {r.get('row_count', 'N/A')} |")
        lines.append(f"| column_count | {r.get('column_count', 'N/A')} |")
        lines.append(f"| date_min | {r.get('date_min', 'N/A')} |")
        lines.append(f"| date_max | {r.get('date_max', 'N/A')} |")
        lines.append(f"| sales_null_count | {r.get('sales_null_count', 'N/A')} |")
        lines.append(f"| sales_negative_count | {r.get('sales_negative_count', 'N/A')} |")
        lines.append(f"| weighted_tp_null_count | {r.get('weighted_tp_null_count', 'N/A')} |")
        lines.append(f"| duplicate_grain_count | {r.get('duplicate_grain_count', 'N/A')} |")
        lines.append(f"| parquet_output | `{r.get('parquet_output_path', 'N/A')}` |")
        lines.append("")
        lines.append(f"**Columns**: {', '.join(r.get('columns', []))}")
        lines.append("")

        if (r.get("duplicate_grain_count") or 0) > 0:
            lines.append(f"### Duplicate Grain Keys (top {len(r.get('duplicate_grain_keys', []))})")
            lines.append("")
            for k in r.get("duplicate_grain_keys", []):
                lines.append(f"- `{k}`")
            lines.append("")
            lines.append("> Duplicate rows detected. These may indicate Tableau export contains "
                         "one-to-many mappings. Review the grain definition or raw data.")
            lines.append("")

        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def build_passenger_insurance_dataset() -> List[Dict[str, Any]]:
    os.makedirs(PARQUET_DIR, exist_ok=True)
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    os.makedirs(QUALITY_DIR, exist_ok=True)

    raw_files = {f.name for f in RAW_CSV_DIR.iterdir() if f.is_file() and f.name.endswith(".csv")}
    expected = set(SOURCE_MAP.keys())
    missing = expected - raw_files
    if missing:
        print(f"\n[ERROR] Missing raw CSV files: {missing}")
        print(f"Files found in {RAW_CSV_DIR}: {sorted(raw_files)}")
        sys.exit(1)

    all_reports: List[Dict[str, Any]] = []
    registry_tables: List[Dict[str, Any]] = []

    for csv_filename, table_name in SOURCE_MAP.items():
        csv_path = RAW_CSV_DIR / csv_filename
        parquet_filename = PARQUET_FILENAMES[table_name]
        parquet_path = PARQUET_DIR / parquet_filename
        grain_cols = GRAIN_DEFS[table_name]

        print(f"\n{'='*60}")
        print(f"Building: {table_name}")
        print(f"  source: {csv_path.name}")
        print(f"  output: {parquet_path.name}")

        try:
            df = read_and_widen_csv(csv_path, table_name)
            build_status = "success"
            print(f"  rows after widen: {len(df)}")
            print(f"  columns: {list(df.columns)}")
        except Exception as e:
            print(f"  [ERROR] Failed to build {table_name}: {e}")
            all_reports.append({
                "table_name": table_name,
                "build_status": "error",
                "error": str(e),
            })
            registry_tables.append({
                "table_name": table_name,
                "source_csv": csv_filename,
                "parquet_path": parquet_filename,
                "build_status": "error",
            })
            continue

        report = _build_quality_report(table_name, df, grain_cols, parquet_path, build_status)

        dup_count = report.get("duplicate_grain_count") or 0
        if dup_count > 0:
            report["duplicate_status"] = "warning"
        else:
            report["duplicate_status"] = "pass"

        all_reports.append(report)

        df.to_parquet(parquet_path, index=False)
        print(f"  parquet written: {parquet_path} ({os.path.getsize(parquet_path) / 1024:.1f} KB)")

        registry_tables.append({
            "table_name": table_name,
            "source_csv": csv_filename,
            "parquet_path": parquet_filename,
            "grain": grain_cols,
            "row_count": report["row_count"],
            "date_min": report.get("date_min"),
            "date_max": report.get("date_max"),
            "build_status": build_status,
            "duplicate_grain_count": dup_count,
            "duplicate_status": report.get("duplicate_status", "pass"),
        })

    registry = {
        "dataset_name": "passenger_insurance",
        "description": "乘用车上险数据 Passenger Insurance Dataset",
        "build_timestamp": datetime.now().isoformat(),
        "source": "Tableau 导出 CSV (UTF-16 LE, tab-delimited, pivot format)",
        "tables": registry_tables,
    }

    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRegistry written: {REGISTRY_PATH}")

    QUALITY_MD_PATH.write_text(_format_quality_markdown(all_reports), encoding="utf-8")
    print(f"Quality MD written: {QUALITY_MD_PATH}")

    quality_json = {
        "dataset_name": "passenger_insurance",
        "build_timestamp": datetime.now().isoformat(),
        "tables": all_reports,
    }
    QUALITY_JSON_PATH.write_text(json.dumps(quality_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Quality JSON written: {QUALITY_JSON_PATH}")

    return all_reports


def main():
    print("=" * 60)
    print("Passenger Insurance Dataset Builder")
    print("=" * 60)
    reports = build_passenger_insurance_dataset()

    success = sum(1 for r in reports if r.get("build_status") == "success")
    errors = sum(1 for r in reports if r.get("build_status") == "error")
    warnings = sum(1 for r in reports if (r.get("duplicate_grain_count") or 0) > 0)

    print(f"\n{'='*60}")
    print(f"Build complete: {success} success, {errors} error(s), {warnings} warning(s)")
    if warnings > 0:
        print("Warnings: duplicate grain rows found in some tables (see quality report).")
    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
