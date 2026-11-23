import pandas as pd
import json
import re
import os
import argparse
from tempfile import NamedTemporaryFile
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET
import zipfile
import io

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"
CONFIG_SNAPSHOT_SUBDIR = Path("tableau-hs") / "configuration"
CONFIG_ANNUAL_FILES = tuple(
    (str(year), f"config_attribute_data_{year}.csv") for year in range(2026, 2021, -1)
)
CONFIG_UPDATE_FILE = "config_attribute_data_update.csv"
CONFIG_KEY = ["Order Number", "Attribute"]
CONFIG_VIEW_COLUMNS = [
    *CONFIG_KEY, "value", "option_flag", "required", "price", "value_code", "attribute_code",
]

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

def _rule_condition(rule) -> str:
    """提取规则表达式字符串，兼容旧字符串格式与新的 {priority, condition} 对象格式。"""
    if isinstance(rule, dict):
        return str(rule.get("condition", ""))
    return str(rule)


def _rule_priority(rule, default: int = 0) -> int:
    """提取规则优先级；旧字符串格式视为 priority=0。"""
    if isinstance(rule, dict):
        try:
            return int(rule.get("priority", default))
        except (TypeError, ValueError):
            return default
    return default


def apply_series_group_logic(df, business_def):
    logic = business_def.get("series_group_logic", {})
    if "product_name" not in df.columns:
        df["series_group_logic"] = pd.NA
        return df

    group_col = pd.Series(pd.NA, index=df.index, dtype="string")
    default_group = "其他"
    rules = []
    for i, (group, cond) in enumerate(logic.items()):
        expr = _rule_condition(cond)
        if str(expr).strip().upper() == "ELSE":
            default_group = group
            continue
        rules.append((_rule_priority(cond), i, group, expr))
    rules.sort(key=lambda r: (-r[0], r[1]))

    for _, _, group, expr in rules:
        mask = parse_sql_condition(df, str(expr))
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
    """规范化新旧 Tableau 视图，优先从 Attribute Value 读取取值编码。"""
    columns = {"_".join(c.lower().split()): c for c in df_raw.columns}
    order_col = next((columns[k] for k in ("order_number", "ordernumber", "order_no") if k in columns), None)
    attr_col = next((c for k, c in columns.items() if "attribute" in k and "name" in k), None)
    val_col = next((c for k, c in columns.items() if "value" in k and "display" in k), None)
    required = {"Order Number": order_col, "Attribute": attr_col, "value": val_col}
    missing = [name for name, source in required.items() if source is None]
    if missing:
        raise ValueError(f"配置输入缺少字段: {', '.join(missing)}")

    sources = {**required, **{k: columns.get(k) for k in ("option_flag", "required", "price")}}
    df = df_raw[[c for c in sources.values() if c is not None]].rename(
        columns={source: name for name, source in sources.items() if source is not None}
    ).dropna(subset=list(required))
    df["Order Number"] = df["Order Number"].astype(str)
    df["value"] = df["value"].astype(str).str.strip()
    df = df.loc[df["value"].ne("")].reindex(columns=CONFIG_VIEW_COLUMNS)
    df["price"] = pd.to_numeric(
        df["price"].astype("string").str.replace(",", "", regex=False), errors="coerce"
    ).astype("Int64")

    def read_code(name):
        if name not in columns:
            return pd.Series(pd.NA, index=df.index, dtype="string")
        return (df_raw.loc[df.index, columns[name]].astype("string").str.strip()
                .replace({"": pd.NA, "nan": pd.NA, "<NA>": pd.NA, "None": pd.NA}))

    df["value_code"] = read_code("attribute_value").fillna(read_code("value"))
    df["attribute_code"] = read_code("attribute_code")
    return df


def annual_config_snapshots(raw_dir):
    """返回已知和新发现的年度快照，按年份从新到旧排列。"""
    files = dict(CONFIG_ANNUAL_FILES)
    for path in raw_dir.glob("config_attribute_data_*.csv"):
        match = re.fullmatch(r"config_attribute_data_(\d{4})\.csv", path.name)
        if match:
            files[match[1]] = path.name
    return sorted(files.items(), reverse=True)


def require_config_snapshots(raw_dir):
    snapshots = [raw_dir / name for _, name in annual_config_snapshots(raw_dir)]
    missing = [path.name for path in snapshots if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"年度配置快照缺失: {', '.join(missing)}")
    return snapshots


def enrich_order_fields(frame, order_data_path):
    enrich = pd.read_parquet(order_data_path, columns=["order_number", "order_type", "vin"])
    enrich["order_number"] = enrich["order_number"].astype(str)
    enrich = enrich.drop_duplicates(subset=["order_number"])
    return frame.merge(enrich, left_on="Order Number", right_on="order_number", how="left").drop(
        columns=["order_number"]
    )


def rebuild_config_parquet(raw_dir, order_data_path, config_parquet_path):
    print("正在加载并处理所有年份的配置文件...")
    paths = [raw_dir / CONFIG_UPDATE_FILE, *require_config_snapshots(raw_dir)]
    parts = []
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"配置输入缺失: {path}")
        raw = read_tableau_csv(path)
        if raw is None:
            raise ValueError(f"无法读取配置输入: {path}")
        try:
            frame = normalize_config_view(raw)
        except ValueError as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
        if frame.empty:
            raise ValueError(f"配置输入无有效记录: {path}")
        parts.append(frame)
        print(f" - 读取成功: {path.name}（{len(frame):,} 行）")

    # 滚动导出优先，随后按年度从新到旧；同一订单可有多个不同属性。
    config = pd.concat(parts, ignore_index=True)
    rows_before = len(config)
    config = config.drop_duplicates(CONFIG_KEY, keep="first")
    print(f"✅ 去重前 {rows_before:,} 行 → 去重后 {len(config):,} 行")
    config = enrich_order_fields(config, order_data_path)
    write_config_parquet(config, config_parquet_path)
    for col in ("attribute_code", "value_code", "order_type", "vin"):
        print(f"  {col} 非空: {config[col].notna().sum():,}/{len(config):,}")
    print(f"✅ 合并解析后的配置文件已保存至 {config_parquet_path}")
    return config


def write_config_parquet(frame, path):
    with NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as temp:
        staged = Path(temp.name)
    try:
        frame.to_parquet(staged, index=False)
        checked_columns = [*CONFIG_KEY, "attribute_code", "value_code"]
        saved = pd.read_parquet(staged, columns=checked_columns)
        if not saved.equals(frame[checked_columns].reset_index(drop=True)):
            raise ValueError("配置 Parquet 写入校验失败")
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)


def incremental_update(existing_path: Path, view_df, order_data_path: Path, dry_run: bool = False):
    """按订单和属性更新，保留未在输入中出现的历史配置。"""
    old = pd.read_parquet(existing_path).reindex(columns=CONFIG_VIEW_COLUMNS)
    old["Order Number"] = old["Order Number"].astype(str)
    old_orders = set(old["Order Number"])

    view = normalize_config_view(view_df)
    if view.empty:
        raise ValueError("配置输入无有效记录")
    view_orders = set(view["Order Number"])

    def deduplicate(frame):
        return frame.sort_values(
            ["value_code", "price"], key=lambda col: col.notna() if col.name == "value_code" else col,
            ascending=False, kind="stable",
        ).drop_duplicates(CONFIG_KEY)

    view = deduplicate(view)
    old = deduplicate(old)
    old_keys = pd.MultiIndex.from_frame(old[CONFIG_KEY])
    view_keys = pd.MultiIndex.from_frame(view[CONFIG_KEY])
    # 旧格式滚动导出可能没有属性编码，保留同一订单属性的已有编码。
    view["attribute_code"] = view["attribute_code"].fillna(
        old.set_index(CONFIG_KEY)["attribute_code"].reindex(view_keys).set_axis(view.index)
    )
    kept = old.loc[~old_keys.isin(view_keys)]
    new = pd.concat([view, kept], ignore_index=True)
    new_keys = pd.MultiIndex.from_frame(new[CONFIG_KEY])
    if not new_keys.is_unique or not old_keys.isin(new_keys).all():
        raise ValueError("配置增量合并校验失败")

    rows_before_dedup = len(view_df) + len(old)
    rows_after_dedup = len(new)
    old_values = old.set_index(CONFIG_KEY)["value"]
    view_values = view.set_index(CONFIG_KEY)["value"]
    common_keys = view_keys.intersection(old_keys)
    changed_pairs = (view_values.loc[common_keys] != old_values.loc[common_keys]).sum()
    added_pairs = len(view_keys.difference(old_keys))

    new = enrich_order_fields(new, order_data_path)

    diff = {
        "old_rows": int(len(old)), "new_rows": int(len(new)),
        "rows_before_dedup": rows_before_dedup, "rows_after_dedup": rows_after_dedup,
        "old_orders": len(old_orders), "new_orders": len(old_orders | view_orders),
        "view_orders": len(view_orders),
        "updated_orders": len(view_orders & old_orders),
        "inserted_orders": len(view_orders - old_orders),
        "kept_orders": len(old_orders - view_orders),
        "changed_oa_pairs": int(changed_pairs), "added_oa_pairs": added_pairs,
        "removed_oa_pairs": 0,
    }
    if not dry_run:
        write_config_parquet(new, existing_path)
    return diff, new


def main(force: bool = False, mobile: bool = False, timeout: int = 600, incremental: bool = False, dry_run: bool = False, input_csv: Path | None = None):
    tableau_url = "https://tableau-hs.immotors.com/#/views/17/config_attribute"
    
    load_env_file(REPO_ROOT / ".env")

    raw_dir = DATASET_DIR / CONFIG_SNAPSHOT_SUBDIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    config_csv_path_update = raw_dir / CONFIG_UPDATE_FILE
    config_parquet_path = DATASET_DIR / "config_attribute.parquet"
    order_data_path = DATASET_DIR / "order_data.parquet"
    business_def_path = REPO_ROOT / "shared" / "schema" / "business_definition.json"

    # 1. Fetch raw data（最新视图变更数据 → config_attribute_data_update.csv）
    if incremental and not config_parquet_path.exists():
        raise FileNotFoundError("缺少配置底表，请先运行全量构建")
    if input_csv is None and (force or not config_csv_path_update.exists()):
        if not incremental:
            require_config_snapshots(raw_dir)
        success = fetch_tableau_data(tableau_url, str(config_csv_path_update), mobile=mobile, timeout=timeout)
        if not success:
            print("❌ 无法获取 Tableau 数据，请检查权限或网络。")
            raise SystemExit(1)

    # ── 增量更新模式 ──
    if incremental:
        source = input_csv or config_csv_path_update
        view_df = read_tableau_csv(source, min_columns=2)
        if view_df is None:
            raise ValueError(f"无法读取配置输入: {source}")
        print(f"正在对现有 {config_parquet_path.name} 做增量更新（输入: {source.name}）...")
        diff, new = incremental_update(config_parquet_path, view_df, order_data_path, dry_run=dry_run)
        print("\n" + "=" * 70)
        print(f"{'指标':<28}{'旧':<14}{'新':<14}")
        print("-" * 70)
        print(f"{'总行数':<28}{diff['old_rows']:<14}{diff['new_rows']:<14}")
        print(f"{'唯一订单数':<28}{diff['old_orders']:<14}{diff['new_orders']:<14}")
        print(f"{'输入覆盖订单':<28}{'':<14}{diff['view_orders']:<14}")
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

    config_df = rebuild_config_parquet(raw_dir, order_data_path, config_parquet_path)
    configured_orders = set(config_df["Order Number"])

    print("正在准备最终统计...")
    with open(business_def_path, encoding="utf-8") as f:
        business_def = json.load(f)
    order_df = apply_series_group_logic(pd.read_parquet(order_data_path), business_def)

    if not pd.api.types.is_datetime64_any_dtype(order_df["intention_payment_time"]):
        order_df["intention_payment_time"] = pd.to_datetime(order_df["intention_payment_time"], errors="coerce")
    if not pd.api.types.is_datetime64_any_dtype(order_df["intention_refund_time"]):
        order_df["intention_refund_time"] = pd.to_datetime(order_df["intention_refund_time"], errors="coerce")
    if "lock_time" in order_df.columns and not pd.api.types.is_datetime64_any_dtype(order_df["lock_time"]):
        order_df["lock_time"] = pd.to_datetime(order_df["lock_time"], errors="coerce")

    target_models = ["CM0", "DM0", "CM1", "DM1", "CM2", "DM2", "CM3", "LS9", "LS8"]
    
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
    parser.add_argument("--incremental", action="store_true", help="增量更新模式：按订单和属性更新，保留未覆盖的配置")
    parser.add_argument("--dry-run", action="store_true", help="增量更新仅预览，不写入")
    parser.add_argument("--input-csv", type=Path, help="使用指定配置 CSV 做一次本地增量")
    args = parser.parse_args()
    if (args.input_csv or args.dry_run) and not args.incremental:
        parser.error("--input-csv 和 --dry-run 需要 --incremental")
    if args.input_csv and args.force:
        parser.error("--input-csv 与 --force 互斥")
    main(force=args.force, mobile=args.mobile, timeout=args.timeout,
         incremental=args.incremental, dry_run=args.dry_run, input_csv=args.input_csv)
