"""store_info_loader — 门店/经销商主数据加载与「订单门店简称 → 经销商」解析。

数据源: store_info.csv（Tableau store_info_1 视图导出，路径登记于
shared/schema/data_path.md 的『门店信息』条目）。

用途:
- 将 order_data 的门店简称 store_name（如『合肥包河』）解析为经销商维度：
  Bloc Name（经销商集团）/ Dealer Name Fc（门店全名）/ Dealer_type（业态）/
  Region Name（大区）/ City Name（城市）/ Dealer Code。
- 门店锁单活性、试驾车按经销商归属、经销商 TopN 等场景的统一底座。

与 skills_store_lock_alert.py 内嵌映射的关系: 该脚本是首个内嵌实现，本 loader
把映射逻辑收敛为共享能力，供 workspace / runtime 复用。

唯一事实源原则: 门店→经销商归属不应在多处各自维护一套清洗规则，统一从这里读取。
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

_COL_DEALER_NAME = "Dealer Name Fc"
_COL_BLOC = "Bloc Name"
_COL_TYPE = "Dealer_type"
_COL_REGION = "Region Name"
_COL_CITY = "City Name"
_COL_CODE = "Dealer Code"
_COL_STATUS = "Store Create Status Desc"

# 行级忽略的聚合/表头残留值
_IGNORED_ROW_VALUES = {"全部"}


def get_service_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_store_info_schema_path() -> Path:
    return get_service_root() / "shared" / "schema" / "store_info_schema.json"


def get_data_path_md() -> Path:
    return get_service_root() / "shared" / "schema" / "data_path.md"


def get_store_info_csv_path() -> Optional[Path]:
    """从 data_path.md 的『门店信息』条目解析 store_info.csv 绝对路径。"""
    md = get_data_path_md()
    if not md.exists():
        return None
    for line in md.read_text(encoding="utf-8").splitlines():
        if "：" not in line:
            continue
        desc, path_raw = line.split("：", 1)
        if "门店信息" in desc:
            path = Path(path_raw.strip().replace("\\_", "_").replace("\\", ""))
            if path.exists():
                return path
    return None


def _normalize_name(name: Any) -> str:
    """门店名归一化：去括号注释、去空白；用于 Dealer Name Fc / store_name 两侧比对。"""
    if name is None:
        return ""
    if isinstance(name, float) and name != name:  # NaN
        return ""
    s = re.sub(r"[（(].*?[）)]", "", str(name)).strip()
    return re.sub(r"\s+", "", s)


def _strip_noise_tokens(sn: str) -> str:
    """去掉门店简称中的临时代际后缀（快闪档期/换铺/迁址/车城等）。"""
    return re.sub(
        r"车城店.*|分销店.*|换铺.*|迁址.*|换址.*|\(作废\).*|（作废）.*|.*2026|.*\d{4}-\d{4}",
        "",
        sn,
    ).strip()


def _clean_dealer_name_fc(name: Any) -> str:
    """Dealer Name Fc 的归一化键：仅去括号与空白，保留业态后缀区分。"""
    return _normalize_name(name)


@functools.lru_cache(maxsize=1)
def load_store_info_raw() -> "Optional[pd.DataFrame]":
    """加载完整 store_info 原始表（dtype=str，空值保留为 ''）。"""
    if pd is None:
        raise ImportError("pandas is required to load store_info")
    path = get_store_info_csv_path()
    if path is None:
        return None
    df = pd.read_csv(path, encoding="utf-8", dtype=str, keep_default_na=False)
    return df


def load_store_info() -> "Optional[pd.DataFrame]":
    """加载清洗后的 store_info：rename 时间列、剔除『全部』聚合行。"""
    df = load_store_info_raw()
    if df is None:
        return None
    df = df.copy()
    rename = {
        "DATE(MIN(DATETRUNC('day', [store_create_time])))": "store_create_time",
        "日(store_stop_time)": "store_stop_time",
    }
    df = df.rename(columns={c: rename.get(c, c) for c in df.columns})
    if _COL_STATUS in df.columns:
        df = df[~df[_COL_STATUS].isin(_IGNORED_ROW_VALUES)]
    return df


def _build_index() -> Dict[str, List[Dict[str, Any]]]:
    """以归一化 Dealer Name Fc 为主键的索引。一行门店名 → 其全部代码行信息。"""
    df = load_store_info()
    if df is None or df.empty:
        return {}
    idx: Dict[str, List[Dict[str, Any]]] = {}
    for _, r in df.iterrows():
        key = _clean_dealer_name_fc(r.get(_COL_DEALER_NAME, ""))
        if not key:
            continue
        idx.setdefault(key, []).append(
            {
                "bloc_name": r.get(_COL_BLOC, ""),
                "dealer_type": r.get(_COL_TYPE, ""),
                "region_name": r.get(_COL_REGION, ""),
                "city_name": r.get(_COL_CITY, ""),
                "dealer_code": r.get(_COL_CODE, ""),
                "dealer_name_fc": r.get(_COL_DEALER_NAME, ""),
            }
        )
    return idx


@functools.lru_cache(maxsize=1)
def get_dealer_lookup() -> Dict[str, List[Dict[str, Any]]]:
    """返回 store_info 中所有门店的 dealer 信息索引（归一化门店名 → 行列表）。"""
    return _build_index()


def resolve_dealer_info(store_name: str) -> Optional[Dict[str, Any]]:
    """把订单侧门店简称解析为经销商信息 dict；无法解析返回 None。

    返回字段: bloc_name / dealer_type / region_name / city_name / dealer_code /
    dealer_name_fc / store_name(入参)
    """
    idx = get_dealer_lookup()
    if not idx:
        return None

    def _first(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        row = dict(rows[0])
        row["store_name"] = store_name
        return row

    sn = _normalize_name(store_name)
    if not sn:
        return None
    for key, rows in idx.items():
        if store_name in key or (sn and sn in key):
            return _first(rows)
    sn2 = _strip_noise_tokens(sn)
    if sn2 and sn2 != sn:
        for key, rows in idx.items():
            if sn2 in key:
                return _first(rows)
    return None


def enrich_store_df(orders: "pd.DataFrame", store_col: str = "store_name") -> "pd.DataFrame":
    """为订单/分析 DataFrame 追加经销商维度列（bloc_name/dealer_type/region 等）。

    返回副本；对未命中门店置空。非必须列存在性由调用方负责。
    """
    out = orders.copy()
    for col in ("bloc_name", "dealer_type", "region_name", "city_name", "dealer_code", "dealer_name_fc"):
        out[col] = None
    if store_col not in out.columns:
        return out
    for i, name in out[store_col].items():
        info = resolve_dealer_info(name)
        if info is None:
            continue
        for col in ("bloc_name", "dealer_type", "region_name", "city_name", "dealer_code", "dealer_name_fc"):
            out.at[i, col] = info.get(col, "")
    return out


def list_open_stores(statuses: Optional[List[str]] = None) -> List[str]:
    """返回指定状态（默认 开业）的门店全名列表。"""
    df = load_store_info()
    if df is None or df.empty:
        return []
    statuses = statuses or ["开业"]
    if _COL_STATUS in df.columns:
        df = df[df[_COL_STATUS].isin(statuses)]
    if _COL_DEALER_NAME not in df.columns:
        return []
    return sorted(df[_COL_DEALER_NAME].dropna().unique().tolist())


def summary() -> Dict[str, Any]:
    """返回数据规模摘要，便于展示与测试。"""
    df = load_store_info_raw()
    if df is None:
        return {"loaded": False}
    return {
        "loaded": True,
        "source": str(get_store_info_csv_path()),
        "rows": int(len(df)),
        "unique_store_names": int(df[_COL_DEALER_NAME].nunique()) if _COL_DEALER_NAME in df.columns else 0,
        "unique_blocs": int(df[_COL_BLOC].nunique()) if _COL_BLOC in df.columns else 0,
        "unique_codes": int(df[_COL_CODE].nunique()) if _COL_CODE in df.columns else 0,
    }
