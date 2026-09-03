#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Tableau 导出交付-库存（vin-table）视图数据，写入 delivery_inventory.parquet。

用法:
    python dataset/updater/delivery_inventory_to_parquet.py
    python dataset/updater/delivery_inventory_to_parquet.py --mobile
    python dataset/updater/delivery_inventory_to_parquet.py --timeout 300
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET
import zipfile
import io

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"

OUTPUT_FILE = DATASET_DIR / "delivery_inventory.parquet"
TABLEAU_OUTPUT_CSV = Path("/Users/zihao_/Documents/coding/dataset/original/vin-table_data.csv")

TABLEAU_VIEW = "-_17851319020730/vin-table"

COLUMN_RENAME_MAP = {
    "VIN": "vin",
    "Vin": "vin",
    "vin": "vin",
    "Real As Offline Time": "real_as_offline_time",
    "Real Qc Offline Time": "real_qc_offline_time",
    "Real Out Vac Time": "real_out_vac_time",
    "First In Inv Time": "first_in_inv_time",
    "Actual In Inv Time": "actual_in_inv_time",
    "Actual Waybill Out Time": "actual_waybill_out_time",
    "Real In Dc Time": "real_in_dc_time",
    "Out Delivery Center Time": "out_delivery_center_time",
    "Schedule Effective Time": "schedule_effective_time",
    "Order Binding Time": "order_binding_time",
    "Plan In Dc Time": "plan_in_dc_time",
    "Order Number": "order_number",
    "订单号": "order_number",
    "车辆最早的生产完成时间": "real_as_offline_time",
    "实际质检完成时间": "real_qc_offline_time",
    "车辆最早进入库存的时间": "first_in_inv_time",
    "当前一次实际入库时间": "actual_in_inv_time",
    "实际运单发运时间": "actual_waybill_out_time",
    "实际到达交付中心时间": "real_in_dc_time",
    "实际离开交付中心时间": "out_delivery_center_time",
    "排产最早记录时间": "schedule_effective_time",
    "订单与具体 VIN 绑定时间": "order_binding_time",
    "计划到达交付中心时间": "plan_in_dc_time",
    "Actual In Inv Time 年/月/日": "actual_in_inv_time",
    "Actual Waybill Out Time 年/月/日": "actual_waybill_out_time",
    "Actual In Inv Time_年/月/日": "actual_in_inv_time",
    "Actual Waybill Out Time_年/月/日": "actual_waybill_out_time",
    "Real Out Vdc Time": "real_out_vdc_time",
    "Real_Out_Vdc_Time": "real_out_vdc_time",
    "Attribute Dealer Date": "attribute_dealer_date",
    "Attribute_Dealer_Date": "attribute_dealer_date",
    "Is Retailed": "is_retailed",
    "Is_Retailed": "is_retailed",
    "Bloc Name": "bloc_name",
    "Bloc_Name": "bloc_name",
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


def tableau_find_workbook_id(
    *,
    base_url: str,
    api_version: str,
    auth_token: str,
    site_id: str,
    workbook_url_name: str,
    timeout: int,
) -> str:
    base = base_url.rstrip("/")
    page_number = 1
    page_size = 1000
    while True:
        params = {"pageSize": str(page_size), "pageNumber": str(page_number)}
        params["filter"] = f"contentUrl:eq:{workbook_url_name}"
        url = f"{base}/api/{api_version}/sites/{site_id}/workbooks?{urlencode(params, quote_via=quote)}"
        status, data = _http_request(
            method="GET",
            url=url,
            headers={"X-Tableau-Auth": auth_token, "Accept": "application/xml"},
            timeout=timeout,
        )
        if status != 200:
            msg = data.decode("utf-8", errors="ignore")
            raise RuntimeError(f"Tableau 查询工作簿失败 (HTTP {status}): {msg[:3000]}")

        root = ET.fromstring(data)
        for wb in root.findall(".//{*}workbook"):
            content_url = (wb.attrib.get("contentUrl") or "").strip().strip("/")
            if content_url == workbook_url_name:
                wb_id = wb.attrib.get("id")
                if wb_id:
                    return wb_id

        pagination = root.find(".//{*}pagination")
        if pagination is None:
            break
        total = int(pagination.attrib.get("totalAvailable", "0") or "0")
        if page_number * page_size >= total or page_number >= 20:
            break
        page_number += 1

    raise RuntimeError(f"未找到工作簿: {workbook_url_name}")


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

    workbook_id = tableau_find_workbook_id(
        base_url=base_url,
        api_version=api_version,
        auth_token=auth_token,
        site_id=site_id,
        workbook_url_name=workbook_url_name,
        timeout=timeout,
    )
    url = f"{base}/api/{api_version}/sites/{site_id}/workbooks/{workbook_id}/views"
    status, data = _http_request(
        method="GET",
        url=url,
        headers={"X-Tableau-Auth": auth_token, "Accept": "application/xml"},
        timeout=timeout,
    )
    if status != 200:
        msg = data.decode("utf-8", errors="ignore")
        raise RuntimeError(f"Tableau 查询工作簿视图失败 (HTTP {status}): {msg[:3000]}")

    vid = _match_view_id_from_xml(data)
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


def read_csv_smart(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        return pd.DataFrame()

    try:
        if file_path.stat().st_size == 0:
            return pd.DataFrame()
    except Exception:
        pass

    encodings = ["utf-16", "utf-8", "utf-8-sig", "gb18030", "gbk"]
    separators = ["\t", ","]

    for enc in encodings:
        for sep in separators:
            try:
                df = pd.read_csv(file_path, encoding=enc, sep=sep)
                if df.shape[1] == 1 and sep in str(df.columns[0]):
                    continue
                if df.shape[1] > 1:
                    return df
            except Exception:
                continue

    return pd.read_csv(file_path)


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.astype(str).str.strip()
    df.columns = df.columns.str.replace("_年/月/日", " 年/月/日", regex=False)
    df = df.rename(columns=COLUMN_RENAME_MAP)
    df.columns = df.columns.str.replace(" ", "_").str.replace("?", "")
    return df


def convert_types(df: pd.DataFrame) -> pd.DataFrame:
    time_cols = [
        "real_as_offline_time",
        "real_qc_offline_time",
        "real_out_vac_time",
        "first_in_inv_time",
        "actual_in_inv_time",
        "actual_waybill_out_time",
        "real_in_dc_time",
        "out_delivery_center_time",
        "schedule_effective_time",
        "order_binding_time",
        "plan_in_dc_time",
    ]
    for col in time_cols:
        if col in df.columns:
            s = df[col].astype(str)
            s = (
                s.str.replace("年", "-", regex=False)
                .str.replace("月", "-", regex=False)
                .str.replace("日", "", regex=False)
            )
            s = s.replace({"nan": None, "None": None, "": None})
            df[col] = pd.to_datetime(s, errors="coerce")
            # Tableau 用 2000-01-01 表示空日期，转 null
            df.loc[df[col] == "2000-01-01", col] = pd.NaT
            df.loc[df[col] == pd.Timestamp("2000-01-01"), col] = pd.NaT

    if "vin" in df.columns:
        df["vin"] = df["vin"].astype("string")

    if "order_number" in df.columns:
        df["order_number"] = df["order_number"].astype("string")

    return df


def step_export_tableau(mobile: bool = False, timeout: int = 600) -> bool:
    print("\n" + "=" * 60)
    print("从 Tableau 导出 delivery_inventory 数据")
    print("=" * 60)

    output_path = TABLEAU_OUTPUT_CSV
    print(f"目标文件: {output_path}")

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

    try:
        workbook_url_name, view_url_name = parse_tableau_view_path(TABLEAU_VIEW)
        api_version, auth_token, site_id = tableau_sign_in(
            base_url=base_url,
            token_name=token_name,
            token_value=token_value,
            site_content_url=site_content_url,
            timeout=timeout,
        )
        try:
            view_id = tableau_find_view_id(
                base_url=base_url,
                api_version=api_version,
                auth_token=auth_token,
                site_id=site_id,
                workbook_url_name=workbook_url_name,
                view_url_name=view_url_name,
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
        finally:
            tableau_sign_out(base_url=base_url, api_version=api_version, auth_token=auth_token, timeout=timeout)

        size_kb = output_path.stat().st_size / 1024
        print(f"✅ Tableau 数据导出成功: {output_path} ({size_kb:.1f} KB)")
        return True
    except Exception as e:
        print(f"❌ Tableau 数据导出失败: {e}")
        return False


def step_upsert_parquet(df_new: pd.DataFrame) -> pd.DataFrame:
    """增量合并：按 vin upsert 到现有 parquet。"""
    if not OUTPUT_FILE.exists():
        print("  无现有 parquet，将创建新文件")
        return df_new

    df_existing = pd.read_parquet(OUTPUT_FILE)
    print(f"  全量底座: {len(df_existing)} 行, {len(df_existing.columns)} 列")

    # 列对齐
    all_cols = list(dict.fromkeys(list(df_existing.columns) + list(df_new.columns)))
    for c in all_cols:
        if c not in df_existing.columns:
            df_existing[c] = pd.NA
        if c not in df_new.columns:
            df_new[c] = pd.NA
    df_existing = df_existing[all_cols]
    df_new = df_new[all_cols]

    # 类型对齐
    for c in df_existing.columns:
        if c in df_new.columns:
            try:
                df_new[c] = df_new[c].astype(df_existing[c].dtype)
            except Exception:
                pass

    # 移除旧数据中与新数据 vin 重叠的行
    if "vin" in df_new.columns:
        before = len(df_existing)
        new_vins = set(df_new["vin"].dropna())
        df_existing = df_existing[~df_existing["vin"].isin(new_vins)]
        removed = before - len(df_existing)
        print(f"  移除旧数据中被覆盖的 VIN: {removed}")
    else:
        print("  警告: 新数据无 vin 列，跳过去重")

    df_merged = pd.concat([df_existing, df_new], ignore_index=True, sort=False)

    # 全局去重(按 vin)
    if "vin" in df_merged.columns:
        before = len(df_merged)
        df_merged = df_merged.drop_duplicates(subset=["vin"], keep="last")
        after = len(df_merged)
        dup_removed = before - after
        if dup_removed:
            print(f"  全局去重(vin): {before} -> {after}")

    return df_merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="交付-库存数据增量更新：Tableau → vin-table_data.csv → delivery_inventory.parquet")
    parser.add_argument("--mobile", action="store_true", help="使用移动端/非办公网络服务器地址导出")
    parser.add_argument("--timeout", type=int, default=600, help="Tableau 导出超时（秒）")
    parser.add_argument("--skip-export", action="store_true", help="跳过 Tableau 导出，使用已有 CSV")
    parser.add_argument("--full-refresh", action="store_true", help="全量刷新（不合并现有数据）")
    args = parser.parse_args(argv)

    load_env_file(REPO_ROOT / ".env")

    if not args.skip_export:
        ok = step_export_tableau(mobile=args.mobile, timeout=args.timeout)
        if not ok:
            return 1

    if not TABLEAU_OUTPUT_CSV.exists():
        print(f"❌ CSV 文件不存在: {TABLEAU_OUTPUT_CSV}")
        return 1

    print(f"\n📖 读取 CSV: {TABLEAU_OUTPUT_CSV.name} ...")
    df = read_csv_smart(TABLEAU_OUTPUT_CSV)
    if df.empty:
        print("❌ CSV 为空")
        return 1
    print(f"✅ 读取成功: {df.shape[0]} 行, {df.shape[1]} 列")

    df = clean_column_names(df)
    df = convert_types(df)
    print(f"列名: {list(df.columns)}")

    if args.full_refresh:
        df_final = df
        print("\n🔁 全量刷新模式，跳过合并")
    else:
        print("\n🔁 增量合并模式")
        df_final = step_upsert_parquet(df)

    print(f"\n💾 保存到: {OUTPUT_FILE}")
    df_final.to_parquet(OUTPUT_FILE, index=False)

    if not OUTPUT_FILE.exists():
        print("❌ 保存失败")
        return 1

    size_mb = OUTPUT_FILE.stat().st_size / (1024 * 1024)
    print(f"✅ 保存成功! {size_mb:.2f} MB ({len(df_final)} 行)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
