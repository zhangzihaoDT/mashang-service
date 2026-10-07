#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享 Tableau REST 导出能力（dataset updater 通用底座）。

从历史 `lock_attribution_data_to_parquet.py` 抽出的通用 Tableau 导出实现，
供各数据集 updater 复用，避免「谁需要导出谁反向依赖锁单归因脚本」。

使用方：
- dataset/updater/assign_data_to_csv.py
- dataset/updater/test_drive_data_to_csv.py
- dataset/updater/lock_attribution_data_to_parquet.py
- dataset/updater/store_info_to_csv.py
- dataset/updater/store_daily_leads_to_csv.py
- dataset/updater/store_daily_zhuli_to_csv.py

Tableau PAT 从仓库根目录 .env 读取:
- TABLEAU_TOKEN_NAME="..."
- TABLEAU_TOKEN_VALUE="..."
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TABLEAU_URL = "https://tableau-hs.immotors.com"
DEFAULT_TABLEAU_MOBILE_URL = "https://mobile-tableau-hs.immotors.com"

# 常用 Tableau 视图（Workbook/Sheet 形式）
VIEW_ASSIGN = "core_metric_observation/assign"
VIEW_TEST_DRIVE = "core_metric_observation/7"


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


def resolve_tableau_base_url(mobile: bool = False) -> str:
    """办公网 / 移动链路 Tableau 入口。"""
    if mobile:
        return os.getenv("TABLEAU_SERVER_URL_MOBILE") or DEFAULT_TABLEAU_MOBILE_URL
    return os.getenv("TABLEAU_SERVER_URL") or DEFAULT_TABLEAU_URL


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
    last_status = 0
    last_data: bytes = b""
    for ver in versions:
        url = f"{base}/api/{ver}/auth/signin"
        status, data = _http_request(
            method="POST",
            url=url,
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
            body=payload,
            timeout=timeout,
        )
        last_status, last_data = status, data
        if status in {200, 201}:
            token = _xml_find_first_attr(data, "credentials", "token")
            site_id = _xml_find_first_attr(data, "site", "id")
            if token and site_id:
                return ver, token, site_id
        if status == 404:
            continue
    msg = (last_data or b"").decode("utf-8", errors="ignore")
    raise RuntimeError(f"Tableau 登录失败 (HTTP {last_status}): {msg[:3000]}")


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
        params = {"pageSize": str(page_size), "pageNumber": str(page_number), "filter": f"contentUrl:eq:{workbook_url_name}"}
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


def export_tableau_csv_to_original(
    *,
    view: str,
    output_path: Path,
    token_name: str,
    token_value: str,
    timeout: int,
    mobile: bool,
) -> bool:
    """从 Tableau 视图导出 CSV 到指定路径（原子落盘）。"""
    print(f"视图: {view}")
    print(f"目标文件: {output_path}")
    base_url = resolve_tableau_base_url(mobile)
    site_content_url = os.getenv("TABLEAU_SITE_CONTENT_URL", "")

    try:
        workbook_url_name, view_url_name = parse_tableau_view_path(view)
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
