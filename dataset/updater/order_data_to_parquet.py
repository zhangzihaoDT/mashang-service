#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增量更新模式：读取现有 order_data.parquet 为底座，导入 order_data_2026.csv（近 60 日）做 upsert。
输出：dataset/order_data.parquet
"""

import sys
import os
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
OUTPUT_FILE = DATASET_DIR / "order_data.parquet"

TABLEAU_VIEW = "core_metric_observation/11"
TABLEAU_OUTPUT_2026 = DATASET_DIR / "order_data_2026.csv"

INPUT_FILE_2026 = DATASET_DIR / "order_data_2026.csv"


def normalize_owner_cell_phone(series: pd.Series) -> pd.Series:
    s_raw = series.astype("string").str.strip()
    num = pd.to_numeric(s_raw, errors="coerce").round(0)
    num_int = num.astype("Int64")
    s_num = num_int.astype("string")
    s = s_raw.where(num.isna(), s_num)
    s = s.str.strip().str.lower()
    s = s.replace(
        {
            "nan": pd.NA,
            "none": pd.NA,
            "null": pd.NA,
            "": pd.NA,
            "-": pd.NA,
            "无": pd.NA,
        }
    )
    digits = s.str.replace(r"\D", "", regex=True)
    digits = digits.str.replace(r"^0086", "", regex=True)
    digits = digits.str.replace(r"^86", "", regex=True)
    valid = digits.str.match(r"^1\d{10}$", na=False)
    return digits.where(valid, pd.NA).astype("string")


def read_csv_smart(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        print(f"⚠️ 文件不存在: {file_path}")
        return pd.DataFrame()

    try:
        if file_path.stat().st_size == 0:
            print(f"❌ 文件为空(0字节): {file_path}")
            return pd.DataFrame()
    except Exception:
        pass

    print(f"📖 正在读取: {file_path.name} ...")

    encodings = ["utf-16", "utf-8", "utf-8-sig", "gb18030", "gbk"]
    separators = ["\t", ","]

    for enc in encodings:
        for sep in separators:
            try:
                df = pd.read_csv(file_path, encoding=enc, sep=sep)
                if df.shape[1] == 1 and sep in str(df.columns[0]):
                    continue
                if df.shape[1] > 1:
                    print(
                        f"✅ 读取成功 (编码: {enc}, 分隔符: '{sep if sep != '\t' else '\\t'}') - 形状: {df.shape}"
                    )
                    return df
            except Exception:
                continue

    try:
        print("⚠️ 尝试默认参数读取...")
        return pd.read_csv(file_path)
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        return pd.DataFrame()


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            if "=" not in line:
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


def step_export_tableau_order_data_2026(mobile: bool = False, timeout: int = 600) -> bool:
    print("\n" + "=" * 60)
    print("步骤 0: 从 Tableau 导出最新 order_data_2026.csv")
    print("=" * 60)

    output_path = TABLEAU_OUTPUT_2026
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
        print(f"✅ Tableau 数据导出成功: {output_path}")
        return True
    except Exception as e:
        print(f"❌ Tableau 数据导出失败: {e}")
        return False


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.astype(str).str.strip()
    df.columns = df.columns.str.replace("_年/月/日", " 年/月/日", regex=False)

    rename_map = {
        "first_touch_time 年/月/日": "first_touch_time",
        "delivery_date 年/月/日": "delivery_date",
        "deposit_payment_time 年/月/日": "deposit_payment_time",
        "deposit_refund_time 年/月/日": "deposit_refund_time",
        "first_test_drive_time 年/月/日": "first_test_drive_time",
        "intention_payment_time 年/月/日": "intention_payment_time",
        "intention_refund_time 年/月/日": "intention_refund_time",
        "invoice_upload_time 年/月/日": "invoice_upload_time",
        "lock_time 年/月/日": "lock_time",
        "order_create_time 年/月/日": "order_create_date",
        "store_create_date 年/月/日": "store_create_date",
        "approve_refund_time 年/月/日": "approve_refund_time",
        "apply_refund_time 年/月/日": "apply_refund_time",
        "first_assign_time 年/月/日": "first_assign_time",
        "lead_assign_time_max 年/月/日": "lead_assign_time_max",
        "final_payment_time 年/月/日": "final_payment_time",
        "actual_refund_time 年/月/日": "actual_refund_time",
        "Td CountD": "td_countd",
        "Drive Series Cn": "drive_series_cn",
        "Main Lead Id": "main_lead_id",
        "Parent Region Name": "parent_region_name",
        "Parent_Region_Name": "parent_region_name",
        "DATE([invoice_upload_time])": "invoice_upload_time",
        "DATE([first_assign_time])": "first_assign_time",
        "DATE([store_create_date])": "store_create_date",
        "Buyer Identity No": "buyer_identity_no",
        "Owner Identity No": "owner_identity_no",
        "Product Name": "product_name",
        "Series": "series",
        "Store Name": "store_name",
        "DATE([Invoice Upload Time])": "invoice_upload_time",
        "Deposit Payment Time": "deposit_payment_time",
        "Final Payment Way": "final_payment_way",
        "Finance Product": "finance_product",
        "Intention Payment Time": "intention_payment_time",
        "License City": "license_city",
        "Lock Time": "lock_time",
        "Order Number": "order_number",
        "Store City": "store_city",
        "Vin": "vin",
        "Invoice Amount": "invoice_amount",
        "Actual Refund Time 年/月/日": "actual_refund_time",
        "Apply Refund Time 年/月/日": "apply_refund_time",
        "Approve Refund Time 年/月/日": "approve_refund_time",
        "Delivery Date 年/月/日": "delivery_date",
        "Final Payment Time 年/月/日": "final_payment_time",
        "First Test Drive Time 年/月/日": "first_test_drive_time",
        "Order Create Time 年/月/日": "order_create_date",
    }

    df = df.rename(columns=rename_map)
    df.columns = df.columns.str.replace(" ", "_")
    return df


def convert_types(df: pd.DataFrame) -> pd.DataFrame:
    date_cols = [
        "first_touch_time",
        "delivery_date",
        "deposit_payment_time",
        "deposit_refund_time",
        "first_test_drive_time",
        "intention_payment_time",
        "intention_refund_time",
        "invoice_upload_time",
        "lock_time",
        "order_create_date",
        "store_create_date",
        "order_create_time",
        "approve_refund_time",
        "apply_refund_time",
        "first_assign_time",
        "lead_assign_time_max",
        "final_payment_time",
        "actual_refund_time",
    ]
    for col in date_cols:
        if col in df.columns:
            s = df[col].astype(str)
            s = (
                s.str.replace("年", "-", regex=False)
                .str.replace("月", "-", regex=False)
                .str.replace("日", "", regex=False)
            )
            s = s.replace({"nan": None, "None": None, "": None})
            df[col] = pd.to_datetime(s, errors="coerce")

    numeric_cols = ["age", "invoice_amount", "Invoice_Amount", "td_countd", "buyer_age", "owner_age"]
    for col in numeric_cols:
        if col in df.columns:
            if pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col]):
                s = df[col].astype(str).str.replace(",", "", regex=False).str.replace("￥", "", regex=False).str.replace("¥", "", regex=False)
                df[col] = pd.to_numeric(s, errors="coerce")
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["buyer_age", "owner_age"]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            valid = s.between(18, 100, inclusive="both")
            df[col] = s.where(valid)

    cat_cols = [
        "product_name",
        "final_payment_way",
        "finance_product",
        "first_middle_channel_name",
        "gender",
        "is_hold",
        "is_staff",
        "license_city",
        "license_city_level",
        "license_province",
        "order_type",
        "series",
        "store_city",
        "belong_intent_series",
        "drive_series_cn",
        "parent_region_name",
    ]
    for col in cat_cols:
        if col in df.columns:
            if df[col].nunique(dropna=True) < df.shape[0] * 0.5:
                df[col] = df[col].astype("category")
            else:
                df[col] = df[col].astype("string")

    if "order_number" in df.columns:
        df["order_number"] = df["order_number"].astype("string")

    if "owner_cell_phone" in df.columns:
        df["owner_cell_phone"] = normalize_owner_cell_phone(df["owner_cell_phone"])

    return df


def merge_order_data(df_base: pd.DataFrame, df_new: pd.DataFrame) -> pd.DataFrame:
    """将增量 CSV（df_new）upsert 进现有 parquet 底座（df_base）。

    规则：
      - CSV 有锁单时间 → 整行覆盖底座同 order_number（CSV 为权威）
      - CSV 无锁单时间且为新订单 → 追加
      - CSV 无锁单时间且已在底座 → 字段级回填（combine_first）：
        底座非空保留（不覆盖历史/截断数据）、底座为空用 CSV 补齐，
        避免丢弃 CSV 带来的字段更新（如已有 order_create_date 的订单
        后补 intention_payment_time，若整行丢弃会造成漏小订）。
    """
    align_cols = list(dict.fromkeys(list(df_base.columns) + list(df_new.columns)))
    for c in align_cols:
        if c not in df_base.columns:
            df_base[c] = pd.NA
        if c not in df_new.columns:
            df_new[c] = pd.NA
    df_base = df_base[align_cols]
    df_new = df_new[align_cols]

    for c in df_base.columns:
        if c in df_new.columns:
            # category dtype 的 categories 可能不包含 CSV 中的新值，
            # 直接 astype 会把新值 cast 成 NaN（如 parent_region_name 换命名体系后丢值）。
            # 因此对 category 列先降级为 string，保留全部值，后续再统一处理。
            if isinstance(df_base[c].dtype, pd.CategoricalDtype):
                df_new[c] = df_new[c].astype("string")
                continue
            try:
                df_new[c] = df_new[c].astype(df_base[c].dtype)
            except Exception:
                pass

    if "order_number" not in df_new.columns or "lock_time" not in df_new.columns:
        return pd.concat([df_base, df_new], ignore_index=True, sort=False)

    df_new_with_lock = df_new[df_new["lock_time"].notna()].copy()
    df_new_no_lock_new = df_new[
        df_new["lock_time"].isna() & ~df_new["order_number"].isin(df_base["order_number"])
    ].copy()
    df_new_no_lock_existing = df_new[
        df_new["lock_time"].isna() & df_new["order_number"].isin(df_base["order_number"])
    ].copy()

    if len(df_new_no_lock_existing) > 0:
        upd = df_new_no_lock_existing[align_cols].set_index("order_number")
        base_sub = df_base[df_base["order_number"].isin(upd.index)].set_index("order_number")
        backfilled = base_sub.combine_first(upd).reset_index()
        df_base = df_base[~df_base["order_number"].isin(backfilled["order_number"])]
        print(f"🔄 回填底座中已存在订单的 CSV 非空字段（无锁单）: {len(backfilled)}")
        df_new_no_lock_existing = backfilled
    if len(df_new_no_lock_new) > 0:
        print(f"➕ 追加底座中不存在的新订单（无锁单时间）: {len(df_new_no_lock_new)}")
    if len(df_new_with_lock) > 0:
        before = len(df_base)
        new_orders = set(df_new_with_lock["order_number"].dropna())
        mask = ~df_base["order_number"].isin(new_orders)
        df_base = df_base[mask]
        removed = before - len(df_base)
        print(f"✂️ 移除底座中被覆盖的订单（含有效锁单时间）: {removed}")

    to_concat = [df_base, df_new_with_lock, df_new_no_lock_new, df_new_no_lock_existing]
    return pd.concat([d for d in to_concat if len(d) > 0], ignore_index=True, sort=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="order_data 合并清洗并写入 Parquet（可选自动从 Tableau 更新 2026 数据）")
    parser.add_argument("--skip-export", action="store_true", help="跳过从 Tableau 导出 2026 数据步骤")
    parser.add_argument("--mobile", action="store_true", help="使用移动端/非办公网络服务器地址导出")
    parser.add_argument("--timeout", type=int, default=600, help="Tableau 导出超时（秒）")
    args = parser.parse_args(argv)

    if not args.skip_export:
        load_env_file(REPO_ROOT / ".env")
        ok = step_export_tableau_order_data_2026(mobile=args.mobile, timeout=args.timeout)
        if not ok:
            return 1

    if not INPUT_FILE_2026.exists():
        print(f"❌ 增量文件不存在: {INPUT_FILE_2026}")
        return 1

    # --- 1. 加载增量 CSV（近 60 日）---
    print(f"📖 正在读取增量数据: {INPUT_FILE_2026.name} ...")
    df_new = read_csv_smart(INPUT_FILE_2026)
    if df_new.empty:
        print("❌ 增量数据为空，终止")
        return 1
    df_new = clean_column_names(df_new)
    df_new = convert_types(df_new)
    print(f"✅ 增量数据加载完成: {df_new.shape[0]} 行, {df_new.shape[1]} 列")

    # --- 2. 加载现有 parquet 底座 ---
    if OUTPUT_FILE.exists():
        df_base = pd.read_parquet(OUTPUT_FILE)
        print(f"✅ 现有数据加载完成: {df_base.shape[0]} 行, {df_base.shape[1]} 列")
        df_all = merge_order_data(df_base, df_new)
    else:
        print("⚠️ 未找到现有 parquet，以增量数据作为初始底座")
        df_all = df_new

    print(f"✅ 合并完成: {df_all.shape[0]} 行, {df_all.shape[1]} 列")

    # --- 3. 全局去重 ---
    if "order_number" in df_all.columns:
        before = int(df_all.shape[0])
        df_all = df_all.drop_duplicates(subset=["order_number"], keep="last")
        after = int(df_all.shape[0])
        print(f"✂️ 去重(order_number): {before} -> {after} (移除 {before - after})")

    # --- 4. 写回 parquet ---
    print(f"💾 保存到: {OUTPUT_FILE}")
    df_all.to_parquet(OUTPUT_FILE, index=False)

    if not OUTPUT_FILE.exists():
        print("❌ 保存失败")
        return 1

    try:
        df_check = pd.read_parquet(OUTPUT_FILE, columns=None)
        print("\n🔎 数据检查（Max 时间）")
        for col in ["order_create_date", "intention_payment_time", "lock_time"]:
            if col not in df_check.columns:
                print(f" - max {col}: Column Not Found")
                continue
            if not pd.api.types.is_datetime64_any_dtype(df_check[col]):
                df_check[col] = pd.to_datetime(df_check[col], errors="coerce")
            max_val = df_check[col].max()
            print(f" - max {col}: {str(max_val) if pd.notna(max_val) else 'None'}")
    except Exception as e:
        print(f"\n⚠️ 数据检查失败: {e}")

    size_mb = OUTPUT_FILE.stat().st_size / (1024 * 1024)
    print(f"✅ 保存成功! 文件大小: {size_mb:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
