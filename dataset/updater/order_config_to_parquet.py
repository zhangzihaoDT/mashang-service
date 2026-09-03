import pandas as pd
import json
import re
import os
import argparse
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET
import zipfile
import io

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"

def parse_sql_condition(df, condition_str):
    def not_like_replacer(match):
        val = match.group(1)
        return f"~df['product_name'].str.contains('{val}', na=False, regex=False)"

    condition_str = re.sub(r"product_name\s+NOT\s+LIKE\s+'%([^%]+)%+'", not_like_replacer, condition_str)

    def like_replacer(match):
        val = match.group(1)
        return f"df['product_name'].str.contains('{val}', na=False, regex=False)"

    condition_str = re.sub(r"product_name\s+LIKE\s+'%([^%]+)%+'", like_replacer, condition_str)

    condition_str = condition_str.replace(" AND ", " & ").replace(" OR ", " | ")

    try:
        return eval(condition_str)
    except Exception as e:
        print(f"⚠️ 解析条件失败: {condition_str}, Error: {e}")
        return pd.Series([False] * len(df), index=df.index)

def apply_series_group_logic(df, business_def):
    logic = business_def.get("series_group_logic", {})
    if "product_name" not in df.columns:
        df["series_group_logic"] = pd.NA
        return df

    group_col = pd.Series(pd.NA, index=df.index, dtype="string")
    default_group = "其他"
    for group, cond in logic.items():
        if str(cond).strip().upper() == "ELSE":
            default_group = group
            continue
        mask = parse_sql_condition(df, str(cond))
        if not isinstance(mask, pd.Series):
            continue
        mask = mask.fillna(False)
        assignable = group_col.isna() & mask
        if assignable.any():
            group_col = group_col.where(~assignable, group)

    df["series_group_logic"] = group_col.fillna(default_group).astype("string")
    return df

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
    last_status = 0
    last_data = b""
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


def fetch_tableau_data(view: str, output_csv: str, mobile: bool = False, timeout: int = 600) -> bool:
    print(f"正在从 Tableau 导出数据: {view}")
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

    output_path = Path(output_csv)
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
        print("✅ 导出成功")
        return True
    except Exception as e:
        print(f"⚠️ 导出数据失败: {e}")
        return False

def read_tableau_csv(csv_file, min_columns=2):
    encodings_to_try = ["utf-8-sig", "utf-16", "utf-8", "gb18030", "gbk"]
    for enc in encodings_to_try:
        try:
            df_tmp = pd.read_csv(csv_file, encoding=enc, sep="\t", low_memory=False)
            if len(df_tmp.columns) <= 1:
                df_tmp = pd.read_csv(csv_file, encoding=enc, sep=",", low_memory=False)
            if len(df_tmp.columns) >= min_columns:
                return df_tmp
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    return None


def normalize_config_view(df_raw):
    """把 Tableau 视图原始数据规范化为 parquet schema。

    输出列: Order Number, Attribute, value (显示名), value_code (配置 code, 新增 Value 列),
    option_flag, required, price。
    """
    order_col = next(c for c in df_raw.columns if c.lower().replace(" ", "_") in ["order_number", "ordernumber", "order_no"])
    attr_col = next(c for c in df_raw.columns if "attribute" in c.lower() and "name" in c.lower())
    val_col = next(c for c in df_raw.columns if "value" in c.lower() and "display" in c.lower())
    code_col = next((c for c in df_raw.columns if c.strip().lower() == "value"), None)
    opt_col = next((c for c in df_raw.columns if c.lower().replace(" ", "_") == "option_flag"), None)
    req_col = next((c for c in df_raw.columns if c.lower().replace(" ", "_") == "required"), None)
    prc_col = next((c for c in df_raw.columns if c.lower().replace(" ", "_") == "price"), None)
    extra = [c for c in [opt_col, req_col, prc_col, code_col] if c]
    cols = [order_col, attr_col, val_col] + extra
    df = df_raw[cols].dropna(subset=[order_col, attr_col, val_col]).copy()
    df[val_col] = df[val_col].astype(str).str.strip()
    df = df[df[val_col].ne("")]
    rename = {order_col: "Order Number", attr_col: "Attribute", val_col: "value"}
    if opt_col:
        rename[opt_col] = "option_flag"
    if req_col:
        rename[req_col] = "required"
    if prc_col:
        rename[prc_col] = "price"
        df[prc_col] = df[prc_col].astype(str).str.replace(",", "", regex=False)
        df[prc_col] = pd.to_numeric(df[prc_col], errors="coerce").astype("Int64")
    if code_col:
        rename[code_col] = "value_code"
        df[code_col] = df[code_col].astype(str).str.strip()
    return df.rename(columns=rename)


def incremental_update(existing_path: Path, view_df, order_data_path: Path, dry_run: bool = False) -> dict:
    """增量更新：视图订单用最新视图数据整体替换，非视图订单保留历史，并按订单去重。

    按订单去重规则: 每 (Order Number, Attribute) 保留一行；
    优先级: 带 value_code 的行 > 价格高 > 先出现。
    """
    old = pd.read_parquet(existing_path)
    old["Order Number"] = old["Order Number"].astype(str)
    old_orders = set(old["Order Number"])

    view = normalize_config_view(view_df)
    view["Order Number"] = view["Order Number"].astype(str)
    view_orders = set(view["Order Number"])

    kept = old[~old["Order Number"].isin(view_orders)]
    new = pd.concat([view, kept], ignore_index=True)

    # 按订单去重
    rows_before_dedup = len(new)
    prio = new["value_code"].notna().astype(int) * 1_000_000 + new["price"].astype("Int64").fillna(-1).astype(int)
    new = new.assign(_prio=prio).sort_values("_prio", ascending=False, kind="stable")
    new = new.drop_duplicates(subset=["Order Number", "Attribute"], keep="first").drop(columns=["_prio"])
    rows_after_dedup = len(new)

    # 计算视图订单内 (订单, 属性) 的取值变化（视图值 vs 旧快照值集合）
    old_oa = old[old["Order Number"].isin(view_orders)].groupby(["Order Number", "Attribute"])["value"].apply(
        lambda s: set(s.astype(str))
    ).to_dict()
    new_oa = view.groupby(["Order Number", "Attribute"])["value"].apply(
        lambda s: set(s.astype(str))
    ).to_dict()
    changed_pairs = {k for k, v in new_oa.items() if v - old_oa.get(k, set())}
    added_pairs = {k for k in new_oa if k not in old_oa}
    removed_pairs = {k for k in old_oa if k not in new_oa}

    # 重新关联 order_type / vin（先清掉旧表自带/历史合并产生的列，避免后缀重复）
    for c in [c for c in new.columns if c in ("order_type", "vin") or c.startswith(("order_type_", "vin_"))]:
        new = new.drop(columns=[c])
    enrich = pd.read_parquet(order_data_path)[["order_number", "order_type", "vin"]].drop_duplicates(subset=["order_number"])
    enrich["order_number"] = enrich["order_number"].astype(str)
    new = new.merge(enrich, left_on="Order Number", right_on="order_number", how="left").drop(columns=["order_number"])

    diff = {
        "old_rows": int(len(old)), "new_rows": int(len(new)),
        "rows_before_dedup": rows_before_dedup, "rows_after_dedup": rows_after_dedup,
        "old_orders": len(old_orders), "new_orders": len(old_orders | view_orders),
        "view_orders": len(view_orders),
        "updated_orders": len(view_orders & old_orders),
        "inserted_orders": len(view_orders - old_orders),
        "kept_orders": len(old_orders - view_orders),
        "changed_oa_pairs": len(changed_pairs), "added_oa_pairs": len(added_pairs),
        "removed_oa_pairs": len(removed_pairs),
    }
    if not dry_run:
        new.to_parquet(existing_path, index=False)
    return diff, new


def main(force: bool = False, mobile: bool = False, timeout: int = 600, incremental: bool = False, dry_run: bool = False):
    tableau_url = "https://tableau-hs.immotors.com/#/views/17/config_attribute"
    
    load_env_file(REPO_ROOT / ".env")

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    config_csv_path_update = DATASET_DIR / "config_attribute_data_update.csv"
    config_parquet_path = DATASET_DIR / "config_attribute.parquet"
    order_data_path = DATASET_DIR / "order_data.parquet"
    business_def_path = REPO_ROOT / "shared" / "schema" / "business_definition.json"

    # 1. Fetch raw data（最新视图变更数据 → config_attribute_data_update.csv）
    if force or not config_csv_path_update.exists():
        success = fetch_tableau_data(tableau_url, str(config_csv_path_update), mobile=mobile, timeout=timeout)
        if not success:
            print("❌ 无法获取 Tableau 数据，请检查权限或网络。")
            return

    # ── 增量更新模式 ──
    if incremental:
        if not config_parquet_path.exists():
            print("❌ 增量更新需要已存在的 config_attribute.parquet，请先跑全量构建。")
            return
        view_df = read_tableau_csv(config_csv_path_update, min_columns=2)
        if view_df is None:
            print("❌ 无法读取视图数据:", config_csv_path_update)
            return
        print(f"正在对现有 {config_parquet_path.name} 做增量更新（视图数据: {config_csv_path_update.name}）...")
        diff, new = incremental_update(config_parquet_path, view_df, order_data_path, dry_run=dry_run)
        print("\n" + "=" * 70)
        print(f"{'指标':<28}{'旧':<14}{'新':<14}")
        print("-" * 70)
        print(f"{'总行数(去重后)':<28}{diff['old_rows']:<14}{diff['new_rows']:<14}")
        print(f"{'去重前行数':<28}{'':<14}{diff['rows_before_dedup']:<14}")
        print(f"{'唯一订单数':<28}{diff['old_orders']:<14}{diff['new_orders']:<14}")
        print(f"{'视图覆盖订单(替换)':<28}{'':<14}{diff['view_orders']:<14}")
        print(f"{'其中订单已存在(更新)':<28}{'':<14}{diff['updated_orders']:<14}")
        print(f"{'新增订单':<28}{'':<14}{diff['inserted_orders']:<14}")
        print(f"{'保留历史订单(不在视图)':<28}{'':<14}{diff['kept_orders']:<14}")
        print(f"{'(订单,属性)取值变化':<28}{'':<14}{diff['changed_oa_pairs']:<14}")
        print(f"{'(订单,属性)新增':<28}{'':<14}{diff['added_oa_pairs']:<14}")
        print(f"{'(订单,属性)移除':<28}{'':<14}{diff['removed_oa_pairs']:<14}")
        print("=" * 70)
        if dry_run:
            print("⚠️ dry-run 模式：未写入，仅预览。去掉 --dry-run 写入。")
        else:
            print(f"✅ 增量更新完成（按订单去重），已写入 {config_parquet_path}")
        return

    # 2. Convert config data to Parquet
    print("正在加载并处理所有年份的配置文件...")
    year_files = [
        ("2023", "config_attribute_data.csv"),
        ("2024", "config_attribute_data2024.csv"),
        ("2025", "config_attribute_data2025.csv"),
        ("2026", "config_attribute_data2026.csv"),
    ]
    processed_list = []

    for year, fname in year_files:
        csv_file = DATASET_DIR / fname

        if not csv_file.exists():
            print(f"⚠️ 找不到文件: {csv_file.name}")
            continue

        print(f" - 读取: {csv_file.name}")
        df_raw = read_tableau_csv(csv_file, min_columns=2)
        if df_raw is None:
            print(f"❌ 无法读取文件: {csv_file.name}")
            continue

        order_col = next(c for c in df_raw.columns if c.lower().replace(" ", "_") in ["order_number", "ordernumber", "order_no"])
        attr_col = next(c for c in df_raw.columns if "attribute" in c.lower() and "name" in c.lower())
        val_col = next(c for c in df_raw.columns if "value" in c.lower() and "display" in c.lower())
        code_col = next((c for c in df_raw.columns if c.strip().lower() == "value"), None)

        extra_cols = []
        opt_col = next((c for c in df_raw.columns if c.lower().replace(" ", "_") == "option_flag"), None)
        req_col = next((c for c in df_raw.columns if c.lower().replace(" ", "_") == "required"), None)
        prc_col = next((c for c in df_raw.columns if c.lower().replace(" ", "_") == "price"), None)
        for c in [opt_col, req_col, prc_col, code_col]:
            if c:
                extra_cols.append(c)

        cols = [order_col, attr_col, val_col] + extra_cols
        df_year = df_raw[cols].dropna(subset=[order_col, attr_col, val_col]).copy()
        df_year[val_col] = df_year[val_col].astype(str).str.strip()
        df_year = df_year[df_year[val_col].ne("")]
        rename_map = {order_col: "Order Number", attr_col: "Attribute", val_col: "value"}
        if opt_col:
            rename_map[opt_col] = "option_flag"
        if req_col:
            rename_map[req_col] = "required"
        if prc_col:
            rename_map[prc_col] = "price"
            df_year[prc_col] = df_year[prc_col].astype(str).str.replace(",", "", regex=False)
            df_year[prc_col] = pd.to_numeric(df_year[prc_col], errors="coerce").astype("Int64")
        if code_col:
            rename_map[code_col] = "value_code"
            df_year[code_col] = df_year[code_col].astype(str).str.strip()
        df_year = df_year.rename(columns=rename_map)
        processed_list.append(df_year)

    if not processed_list:
        print("❌ 没有找到任何可处理的配置文件。")
        return

    config_df = pd.concat(processed_list, ignore_index=True)
    print(f"✅ 处理完成，总行数: {len(config_df)}")
    order_col_name = "Order Number"

    # Enrich with order-level info from order_data
    print("正在关联订单表的 order_type 和 vin...")
    order_df_enrich = pd.read_parquet(order_data_path)[["order_number", "order_type", "vin"]].drop_duplicates(subset=["order_number"])
    order_df_enrich["order_number"] = order_df_enrich["order_number"].astype(str)
    config_df = config_df.merge(order_df_enrich, left_on="Order Number", right_on="order_number", how="left").drop(columns=["order_number"])
    print(f"  order_type 非空: {config_df['order_type'].notna().sum():,}/{len(config_df):,}")
    print(f"  vin 非空: {config_df['vin'].notna().sum():,}/{len(config_df):,}")

    config_df.to_parquet(config_parquet_path, index=False)
    print(f"✅ 合并解析后的配置文件已保存至 {config_parquet_path}")

    if not order_col_name:
        print("⚠️ 未能在 Tableau 数据中找到订单号列（Order Number），将无法计算选配数！")
        configured_orders = set()
    else:
        configured_orders = set(config_df[order_col_name].dropna().astype(str))

    # 3. Load Business Definition & Order Data
    print("正在准备最终统计...")
    # 由于前面已经读取过一次业务定义和订单数据，这里可以直接使用 order_df_temp
    # 或者重新获取全量列以保证无副作用
    if 'business_def' not in locals():
        with open(business_def_path, 'r', encoding='utf-8') as f:
            business_def = json.load(f)
    
    if 'order_df_temp' in locals():
        order_df = order_df_temp
    else:
        order_df = pd.read_parquet(order_data_path)
        order_df = apply_series_group_logic(order_df, business_def)

    if not pd.api.types.is_datetime64_any_dtype(order_df["intention_payment_time"]):
        order_df["intention_payment_time"] = pd.to_datetime(order_df["intention_payment_time"], errors="coerce")
    if not pd.api.types.is_datetime64_any_dtype(order_df["intention_refund_time"]):
        order_df["intention_refund_time"] = pd.to_datetime(order_df["intention_refund_time"], errors="coerce")
    if "lock_time" in order_df.columns and not pd.api.types.is_datetime64_any_dtype(order_df["lock_time"]):
        order_df["lock_time"] = pd.to_datetime(order_df["lock_time"], errors="coerce")

    target_models = ["CM0", "DM0", "CM1", "DM1", "CM2", "LS9", "LS8"]
    
    print("\n" + "=" * 100)
    print(
        f"{'车型':<8} | {'订单数':<10} | {'选配数':<10} | {'小订数':<10} | {'留存小订数':<12} | {'小订留存选配数':<14} | {'锁单选配数':<12}"
    )
    print("-" * 100)

    time_periods = business_def.get("time_periods", {})

    for model in target_models:
        df_model = order_df[order_df["series_group_logic"] == model]
        
        # 订单数 (Total orders for the model)
        total_orders = df_model["order_number"].nunique()
        
        # 预售期判断相关变量
        tp = time_periods.get(model, {})
        start_str = tp.get("start")
        end_str = tp.get("end")
        
        # 小订数 (Intention payment time is not null)
        intention_mask = df_model["intention_payment_time"].notna()
        intention_orders = df_model[intention_mask]
        small_orders_count = intention_orders["order_number"].nunique()
        
        # 留存小订数计算（对齐 analyze_order.py 口径）：
        # 1. 在预售期间内小订 (start_day <= intention_payment_time < start_day + N_days)
        # 2. 未退订或在窗口外退订 (intention_refund_time is na OR intention_refund_time > start_day + N_days)
        if start_str and end_str:
            start_day = pd.Timestamp(start_str)
            presale_end_day = pd.Timestamp(end_str)
            n_days = int((presale_end_day.normalize() - start_day.normalize()).days + 1)
            n_days = max(1, n_days)
            
            presale_end_excl = presale_end_day + pd.Timedelta(days=1)
            window_end_excl = start_day + pd.Timedelta(days=int(n_days))
            window_end_excl = min(window_end_excl, presale_end_excl)
            
            m_retention = (
                intention_orders["intention_payment_time"] >= start_day
            ) & (
                intention_orders["intention_payment_time"] < window_end_excl
            ) & (
                intention_orders["intention_refund_time"].isna() | (intention_orders["intention_refund_time"] > window_end_excl)
            )
            retention_orders = intention_orders[m_retention]
        else:
            # Fallback 如果没有配置预售期，沿用旧逻辑（仅判断 intention_refund_time 为空）
            retention_mask = intention_orders["intention_refund_time"].isna()
            retention_orders = intention_orders[retention_mask]

        retained_small_orders_count = retention_orders["order_number"].nunique()
        
        # 选配数 (总选配数) & 小订留存选配数
        if configured_orders:
            configured_count = df_model.loc[df_model["order_number"].astype(str).isin(configured_orders), "order_number"].nunique()
            retention_config_base = retention_orders
            if "lock_time" in retention_config_base.columns:
                retention_config_base = retention_config_base[retention_config_base["lock_time"].isna()]
            retained_configured_count = retention_config_base.loc[
                retention_config_base["order_number"].astype(str).isin(configured_orders),
                "order_number",
            ].nunique()
            if "lock_time" in df_model.columns:
                locked_configured_count = df_model.loc[
                    df_model["lock_time"].notna() & df_model["order_number"].astype(str).isin(configured_orders),
                    "order_number",
                ].nunique()
            else:
                locked_configured_count = 0
        else:
            configured_count = 0
            retained_configured_count = 0
            locked_configured_count = 0
            
        print(
            f"{model:<10} | {total_orders:<13} | {configured_count:<10} | {small_orders_count:<13} | {retained_small_orders_count:<15} | {retained_configured_count:<17} | {locked_configured_count:<14}"
        )
    
    print("=" * 100 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="强制从 Tableau 导出最新配置数据并覆盖本地文件")
    parser.add_argument("--mobile", action="store_true", help="使用移动端/非办公网络服务器地址导出")
    parser.add_argument("--timeout", type=int, default=600, help="Tableau 导出超时（秒）")
    parser.add_argument("--incremental", action="store_true", help="增量更新模式：用最新视图数据替换视图覆盖订单，保留历史订单")
    parser.add_argument("--dry-run", action="store_true", help="增量更新仅预览，不写入")
    args = parser.parse_args()
    main(force=args.force, mobile=args.mobile, timeout=args.timeout,
         incremental=args.incremental, dry_run=args.dry_run)
