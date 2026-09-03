#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增量更新 tp_and_mix_ways 数据集：
1. 从 Tableau 下载 6 个视图的 CSV（仅当月数据）
2. 解析、宽表化
3. Upsert 到现有 parquet（按 date_month 替换）
4. 更新 registry + quality report

用法:
    python dataset/updater/update_tp_and_mix_ways_tableau.py
    python dataset/updater/update_tp_and_mix_ways_tableau.py --mobile
    python dataset/updater/update_tp_and_mix_ways_tableau.py --timeout 300
"""

from __future__ import annotations

import csv
import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET
import zipfile
import io

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_CSV_DIR = REPO_ROOT / "dataset" / "TP&MIX-ways" / "raw_csv"
PARQUET_DIR = REPO_ROOT / "dataset" / "TP&MIX-ways" / "parquet"
REGISTRY_DIR = REPO_ROOT / "dataset" / "TP&MIX-ways" / "registry"
QUALITY_DIR = REPO_ROOT / "dataset" / "TP&MIX-ways" / "quality"

REGISTRY_PATH = REGISTRY_DIR / "tp_and_mix_ways_tables.json"
QUALITY_MD_PATH = QUALITY_DIR / "tp_and_mix_ways_dataset_quality.md"
QUALITY_JSON_PATH = QUALITY_DIR / "tp_and_mix_ways_dataset_quality.json"

TABLEAU_VIEWS: list[dict[str, str]] = [
    {"view_path": "-ways/market_monthly", "output": "way1_market_energy_monthly_data.csv"},
    {"view_path": "-ways/brand_monthly", "output": "way2_brand_monthly_data.csv"},
    {"view_path": "-ways/way3_model_monthly", "output": "way3_model_monthly_data.csv"},
    {"view_path": "-ways/way4_geo_monthly", "output": "way4_geo_monthly_data.csv"},
    {"view_path": "-ways/way5_price_segment_monthly", "output": "way5_price_segment_monthly_data.csv"},
    {"view_path": "-ways/way6_product_segment_monthly", "output": "way6_product_segment_monthly_data.csv"},
]

# Tableau REST API 返回的列名与 build 脚本预期不一致，做归一化映射
COLUMN_NORMALIZE: dict[str, str] = {
    "品牌 (新势力/传统自主/自主新品牌/其他)": "品牌 (组)",
    "品牌 (豪华分组) ": "品牌 (新豪华分组) ",
    "自主/合资/进口": "国产/进口",
    "前驱/后驱/四驱": "驱动形式 (组)",
}

# ---- column mappings (Chinese → English snake_case) - 与 build 脚本一致 ----
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

GRAIN_DEFS: Dict[str, List[str]] = {
    "market_energy_monthly": ["date_month", "fuel_type_group", "fuel_type"],
    "brand_monthly": ["date_month", "brand"],
    "model_monthly": ["date_month", "brand", "model", "sub_model", "sub_model_id"],
    "geo_monthly": ["date_month", "province", "city", "city_tier_group", "fuel_type_group"],
    "price_segment_monthly": ["date_month", "tp_bucket_5w", "tp_bucket_10w", "fuel_type_group", "body_type", "vehicle_level_group"],
    "product_segment_monthly": ["date_month", "saic_segment", "body_type", "vehicle_level", "vehicle_level_group", "fuel_type_group", "drive_type_group"],
}

PARQUET_FILENAMES: Dict[str, str] = {
    "market_energy_monthly": "market_energy_monthly.parquet",
    "brand_monthly": "brand_monthly.parquet",
    "model_monthly": "model_monthly.parquet",
    "geo_monthly": "geo_monthly.parquet",
    "price_segment_monthly": "price_segment_monthly.parquet",
    "product_segment_monthly": "product_segment_monthly.parquet",
}

TABLE_NAMES = [
    "market_energy_monthly",
    "brand_monthly",
    "model_monthly",
    "geo_monthly",
    "price_segment_monthly",
    "product_segment_monthly",
]

SOURCE_CSV_MAP: Dict[str, str] = {
    "market_energy_monthly": "way1_market_energy_monthly_data.csv",
    "brand_monthly": "way2_brand_monthly_data.csv",
    "model_monthly": "way3_model_monthly_data.csv",
    "geo_monthly": "way4_geo_monthly_data.csv",
    "price_segment_monthly": "way5_price_segment_monthly_data.csv",
    "product_segment_monthly": "way6_product_segment_monthly_data.csv",
}


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        return


def _http_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 60,
) -> tuple[int, bytes]:
    req = Request(url=url, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urlopen(req, data=body, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200))
            data = resp.read()
            return status, data
    except HTTPError as e:
        try:
            payload = e.read()
        except Exception:
            payload = str(e).encode("utf-8", errors="ignore")
        return int(getattr(e, "code", 0) or 0), payload
    except URLError as e:
        return 0, str(e).encode("utf-8", errors="ignore")


def _xml_find_first_attr(xml_bytes: bytes, tag_name: str, attr: str) -> str | None:
    root = ET.fromstring(xml_bytes)
    elem = root.find(f".//{{*}}{tag_name}")
    if elem is None:
        return None
    return elem.attrib.get(attr)


def _xml_escape_attr(value: str) -> str:
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def tableau_sign_in(
    *,
    base_url: str,
    token_name: str,
    token_value: str,
    site_content_url: str,
    timeout: int,
) -> tuple[str, str, str]:
    base = base_url.rstrip("/")
    site_part = _xml_escape_attr(site_content_url or "")
    token_name_esc = _xml_escape_attr(token_name)
    token_value_esc = _xml_escape_attr(token_value)
    payload = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<tsRequest>"
        f'<credentials personalAccessTokenName="{token_name_esc}" personalAccessTokenSecret="{token_value_esc}">'
        f'<site contentUrl="{site_part}"/>'
        "</credentials>"
        "</tsRequest>"
    ).encode("utf-8")

    versions = ["3.25", "3.24", "3.23", "3.22", "3.21", "3.20", "3.19", "3.18", "3.17", "3.16", "3.15", "3.14"]
    for ver in versions:
        url = f"{base}/api/{ver}/auth/signin"
        status, data = _http_request(
            method="POST",
            url=url,
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
            body=payload,
            timeout=timeout,
        )
        if status in {200, 201}:
            token = _xml_find_first_attr(data, "credentials", "token")
            site_id = _xml_find_first_attr(data, "site", "id")
            if token and site_id:
                return ver, token, site_id
        if status == 404:
            continue
    msg = data.decode("utf-8", errors="ignore")
    raise RuntimeError(f"Tableau 登录失败 (HTTP {status}): {msg[:3000]}")


def tableau_sign_out(*, base_url: str, api_version: str, auth_token: str, timeout: int) -> None:
    base = base_url.rstrip("/")
    url = f"{base}/api/{api_version}/auth/signout"
    _http_request(method="POST", url=url, headers={"X-Tableau-Auth": auth_token}, body=b"", timeout=timeout)


def tableau_find_view_id(
    *,
    base_url: str,
    api_version: str,
    auth_token: str,
    site_id: str,
    workbook_url_name: str,
    view_url_name: str,
    timeout: int,
) -> str:
    base = base_url.rstrip("/")
    expected = f"{workbook_url_name}/{view_url_name}"

    def _match_view_id_from_xml(xml_bytes: bytes) -> str | None:
        root = ET.fromstring(xml_bytes)
        for v in root.findall(".//{*}view"):
            view_id = (v.attrib.get("id") or "").strip()
            if not view_id:
                continue
            content_url = (v.attrib.get("contentUrl") or "").strip().strip("/")
            view_url = (v.attrib.get("viewUrlName") or "").strip().strip("/")
            name = (v.attrib.get("name") or "").strip()
            if content_url == expected:
                return view_id
            if content_url == view_url_name:
                return view_id
            if content_url.endswith("/" + view_url_name) and content_url.split("/", 1)[0] == workbook_url_name:
                return view_id
            if view_url == view_url_name and content_url.split("/", 1)[0] == workbook_url_name:
                return view_id
            if name == view_url_name and content_url.split("/", 1)[0] == workbook_url_name:
                return view_id
        return None

    def _query_views(*, filter_expr: str) -> str | None:
        page_number = 1
        page_size = 1000
        while True:
            params = {"pageSize": str(page_size), "pageNumber": str(page_number), "filter": filter_expr}
            url = f"{base}/api/{api_version}/sites/{site_id}/views?{urlencode(params, quote_via=quote)}"
            status, data = _http_request(
                method="GET",
                url=url,
                headers={"X-Tableau-Auth": auth_token, "Accept": "application/xml"},
                timeout=timeout,
            )
            if status != 200:
                msg = data.decode("utf-8", errors="ignore")
                raise RuntimeError(f"Tableau 查询视图失败 (HTTP {status}): {msg[:3000]}")
            vid = _match_view_id_from_xml(data)
            if vid:
                return vid
            root = ET.fromstring(data)
            pagination = root.find(".//{*}pagination")
            if pagination is None:
                break
            total = int(pagination.attrib.get("totalAvailable", "0") or "0")
            if page_number * page_size >= total or page_number >= 20:
                break
            page_number += 1
        return None

    for f in [f"contentUrl:eq:{expected}", f"viewUrlName:eq:{view_url_name}", f"name:eq:{view_url_name}"]:
        vid = _query_views(filter_expr=f)
        if vid:
            return vid

    raise RuntimeError(f"未找到视图: {expected}")


def tableau_download_view_data_csv(
    *,
    base_url: str,
    api_version: str,
    auth_token: str,
    site_id: str,
    view_id: str,
    output_path: Path,
    timeout: int,
) -> None:
    base = base_url.rstrip("/")
    candidates = [
        f"{base}/api/{api_version}/sites/{site_id}/views/{view_id}/data?maxAge=1",
        f"{base}/api/{api_version}/sites/{site_id}/views/{view_id}/crosstab?maxAge=1",
    ]
    last_status = 0
    last_data: bytes = b""
    for url in candidates:
        status, data = _http_request(
            method="GET",
            url=url,
            headers={"X-Tableau-Auth": auth_token, "Accept": "*/*"},
            timeout=timeout,
        )
        last_status, last_data = status, data
        if status == 200 and data:
            payload = data
            if payload[:4] == b"PK\x03\x04":
                with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                    names = [n for n in zf.namelist() if not n.endswith("/") and n.strip()]
                    pick = None
                    for n in names:
                        low = n.lower()
                        if low.endswith(".csv") or low.endswith(".tsv") or low.endswith(".txt"):
                            pick = n
                            break
                    if pick is None and names:
                        pick = names[0]
                    if pick is None:
                        raise RuntimeError("Tableau 导出 zip 为空")
                    payload = zf.read(pick)
            tmp_path = output_path.with_name(output_path.name + ".tmp")
            tmp_path.write_bytes(payload)
            if tmp_path.stat().st_size == 0:
                raise RuntimeError("Tableau 导出结果为空文件")
            tmp_path.replace(output_path)
            return
        if status not in {406, 415}:
            break
    msg = (last_data or b"").decode("utf-8", errors="ignore")
    raise RuntimeError(f"Tableau 下载数据失败 (HTTP {last_status}): {msg[:3000]}")


def parse_tableau_view_path(view: str) -> tuple[str, str]:
    raw = (view or "").strip()
    if not raw:
        raise ValueError("empty view")
    s = raw
    if "#/views/" in s:
        s = s.split("#/views/", 1)[1]
    elif "/views/" in s:
        s = s.split("/views/", 1)[1]
    s = s.split("?", 1)[0].strip().strip("/")
    parts = [p for p in s.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"invalid view: {view}")
    return parts[0], parts[1]


# ---- CSV 解析（与 build 脚本一致） ----

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


def normalize_csv(csv_path: Path) -> None:
    """归一化 CSV header：列名对齐 build 脚本预期。"""
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return
    header = rows[0]
    normalized_header = [COLUMN_NORMALIZE.get(col, col) for col in header]
    tmp_path = csv_path.with_name(csv_path.name + ".norm.tmp")
    with open(tmp_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(normalized_header)
        for row in rows[1:]:
            writer.writerow(row)
    tmp_path.replace(csv_path)


def read_and_widen_csv(csv_path: Path, table_name: str) -> pd.DataFrame:
    """读取归一化后的 CSV（UTF-8 逗号分隔）并宽表化。"""
    col_map = dict(COLUMN_MAP[table_name])
    measure_name_col = "_measure_name"
    measure_value_col = "_measure_value"

    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        raw_header = next(reader)

    normalized_col_map = {k.strip(): v for k, v in col_map.items()}
    col_mapping = {}
    for i, raw_col in enumerate(raw_header):
        stripped = raw_col.strip()
        if stripped in normalized_col_map:
            col_mapping[i] = normalized_col_map[stripped]

    rows = []
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
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
    wide_df.dropna(subset=["date_month"], inplace=True)

    for enum_col in ["sales", "weighted_tp", "weighted_length_mm",
                     "weighted_width_mm", "weighted_height_mm", "weighted_wheelbase_mm"]:
        if enum_col in wide_df.columns:
            wide_df[enum_col] = pd.to_numeric(wide_df[enum_col], errors="coerce")

    return wide_df


def upsert_table(existing: pd.DataFrame, new: pd.DataFrame, grain_cols: List[str]) -> pd.DataFrame:
    """按 date_month + grain 做 upsert。"""
    if existing.empty:
        return new

    new_months = set(new["date_month"].dropna().unique())
    if not new_months:
        return existing

    print(f"    new data months: {sorted(new_months)}")
    print(f"    existing rows before: {len(existing)}")

    # 移除与新数据月份重叠的行
    existing = existing[~existing["date_month"].isin(new_months)]
    print(f"    existing rows after removing overlap: {len(existing)}")

    # 列对齐
    all_cols = list(dict.fromkeys(list(existing.columns) + list(new.columns)))
    for c in all_cols:
        if c not in existing.columns:
            existing[c] = pd.NA
        if c not in new.columns:
            new[c] = pd.NA
    existing = existing[all_cols]
    new = new[all_cols]

    # 类型对齐
    for c in existing.columns:
        if c in new.columns and c != "date_month":
            try:
                new[c] = new[c].astype(existing[c].dtype)
            except Exception:
                pass

    merged = pd.concat([existing, new], ignore_index=True, sort=False)
    print(f"    merged rows: {len(merged)}")
    return merged


def build_quality_report(
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
        dup_count = int(df.duplicated(subset=grain_cols, keep=False).sum())
        report["duplicate_grain_count"] = dup_count
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


def format_quality_markdown(all_reports: List[Dict[str, Any]]) -> str:
    lines = [
        "# TP&MIX-ways Dataset — Quality Report",
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
            lines.append("> Duplicate rows detected.")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def step_export_all_views(mobile: bool = False, timeout: int = 600) -> bool:
    print("\n" + "=" * 60)
    print("从 Tableau 导出 TP&MIX-ways 6 个视图")
    print("=" * 60)

    RAW_CSV_DIR.mkdir(parents=True, exist_ok=True)

    token_name = os.getenv("TABLEAU_TOKEN_NAME")
    token_value = os.getenv("TABLEAU_TOKEN_VALUE")
    if not token_name or not token_value:
        print("❌ 缺少 Tableau PAT：TABLEAU_TOKEN_NAME / TABLEAU_TOKEN_VALUE")
        return False

    if mobile:
        base_url = os.getenv("TABLEAU_SERVER_URL_MOBILE") or "https://mobile-tableau-hs.immotors.com"
    else:
        base_url = os.getenv("TABLEAU_SERVER_URL") or "https://tableau-hs.immotors.com"
    site_content_url = os.getenv("TABLEAU_SITE_CONTENT_URL", "")

    view_defs = list(TABLEAU_VIEWS)
    for v in view_defs:
        try:
            wb, vn = parse_tableau_view_path(v["view_path"])
            v["workbook"] = wb
            v["view_name"] = vn
        except ValueError as e:
            print(f"❌ 解析视图路径失败 {v['view_path']}: {e}")
            return False

    try:
        api_version, auth_token, site_id = tableau_sign_in(
            base_url=base_url,
            token_name=token_name,
            token_value=token_value,
            site_content_url=site_content_url,
            timeout=timeout,
        )
    except Exception as e:
        print(f"❌ Tableau 登录失败: {e}")
        return False

    all_ok = True
    try:
        for v in view_defs:
            output_path = RAW_CSV_DIR / v["output"]
            print(f"\n  [{v['output']}] 导出 {v['workbook']}/{v['view_name']} ...")
            try:
                view_id = tableau_find_view_id(
                    base_url=base_url,
                    api_version=api_version,
                    auth_token=auth_token,
                    site_id=site_id,
                    workbook_url_name=v["workbook"],
                    view_url_name=v["view_name"],
                    timeout=timeout,
                )
                tableau_download_view_data_csv(
                    base_url=base_url,
                    api_version=api_version,
                    auth_token=auth_token,
                    site_id=site_id,
                    view_id=view_id,
                    output_path=output_path,
                    timeout=timeout,
                )
                normalize_csv(output_path)
                size_kb = output_path.stat().st_size / 1024
                print(f"  ✅ {v['output']} ({size_kb:.1f} KB)")
            except Exception as e:
                print(f"  ❌ {v['output']} 失败: {e}")
                all_ok = False
    finally:
        tableau_sign_out(base_url=base_url, api_version=api_version, auth_token=auth_token, timeout=timeout)

    if all_ok:
        print(f"\n✅ 全部导出成功 ({len(view_defs)}/6)")
    else:
        print(f"\n⚠️ 部分导出失败")
    return all_ok


def step_incremental_update() -> bool:
    print("\n" + "=" * 60)
    print("增量更新 parquet 数据集")
    print("=" * 60)

    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)

    all_reports: List[Dict[str, Any]] = []
    registry_tables: List[Dict[str, Any]] = []

    for table_name in TABLE_NAMES:
        csv_filename = SOURCE_CSV_MAP[table_name]
        csv_path = RAW_CSV_DIR / csv_filename
        parquet_filename = PARQUET_FILENAMES[table_name]
        parquet_path = PARQUET_DIR / parquet_filename
        grain_cols = GRAIN_DEFS[table_name]

        print(f"\n{'='*50}")
        print(f"处理: {table_name}")
        print(f"  source: {csv_path.name}")

        if not csv_path.exists():
            print(f"  ⏭️  跳过: CSV 不存在 {csv_path.name}")
            continue

        # 读取新 CSV
        try:
            df_new = read_and_widen_csv(csv_path, table_name)
            print(f"  新数据: {len(df_new)} 行, 月份: {sorted(df_new['date_month'].unique())}")
        except Exception as e:
            print(f"  ❌ 解析 CSV 失败: {e}")
            all_reports.append({"table_name": table_name, "build_status": "error", "error": str(e)})
            registry_tables.append({"table_name": table_name, "source_csv": csv_filename, "parquet_path": parquet_filename, "build_status": "error"})
            continue

        # 加载现有 parquet
        if parquet_path.exists():
            try:
                df_existing = pd.read_parquet(parquet_path)
                print(f"  现有数据: {len(df_existing)} 行")
            except Exception as e:
                print(f"  ⚠️  读取现有 parquet 失败，将使用新数据作为底座: {e}")
                df_existing = pd.DataFrame()
        else:
            print(f"  无现有 parquet，将创建新文件")
            df_existing = pd.DataFrame()

        # Upsert
        df_merged = upsert_table(df_existing, df_new, grain_cols)
        df_merged.to_parquet(parquet_path, index=False)
        print(f"  ✅ parquet 已保存: {parquet_path.name}")

        # 质量报告
        report = build_quality_report(table_name, df_merged, grain_cols, parquet_path, "success")
        dup_count = report.get("duplicate_grain_count") or 0
        report["duplicate_status"] = "warning" if dup_count > 0 else "pass"
        all_reports.append(report)

        registry_tables.append({
            "table_name": table_name,
            "source_csv": csv_filename,
            "parquet_path": parquet_filename,
            "grain": grain_cols,
            "row_count": report["row_count"],
            "date_min": report.get("date_min"),
            "date_max": report.get("date_max"),
            "build_status": "success",
            "duplicate_grain_count": dup_count,
            "duplicate_status": report["duplicate_status"],
        })

    # 写 registry
    registry = {
        "dataset_name": "tp_and_mix_ways",
        "description": "乘用车上险数据 TP&MIX-ways Dataset",
        "build_timestamp": datetime.now().isoformat(),
        "source": "Tableau API → 增量更新",
        "tables": registry_tables,
    }
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRegistry written: {REGISTRY_PATH}")

    QUALITY_MD_PATH.write_text(format_quality_markdown(all_reports), encoding="utf-8")
    print(f"Quality MD written: {QUALITY_MD_PATH}")

    quality_json = {"dataset_name": "tp_and_mix_ways", "build_timestamp": datetime.now().isoformat(), "tables": all_reports}
    QUALITY_JSON_PATH.write_text(json.dumps(quality_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Quality JSON written: {QUALITY_JSON_PATH}")

    success = sum(1 for r in all_reports if r.get("build_status") == "success")
    errors = sum(1 for r in all_reports if r.get("build_status") == "error")
    print(f"\n更新完成: {success} 成功, {errors} 失败")

    return errors == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="增量更新 tp_and_mix_ways 数据集（Tableau → CSV → parquet）")
    parser.add_argument("--mobile", action="store_true", help="使用移动端/非办公网络服务器地址导出")
    parser.add_argument("--timeout", type=int, default=600, help="Tableau 导出超时（秒）")
    parser.add_argument("--skip-export", action="store_true", help="跳过 Tableau 导出，仅做增量更新（使用已有 CSV）")
    args = parser.parse_args(argv)

    load_env_file(REPO_ROOT / ".env")

    if not args.skip_export:
        ok = step_export_all_views(mobile=args.mobile, timeout=args.timeout)
        if not ok:
            return 1

    ok = step_incremental_update()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
