"""监控测试单过滤 — 排除预埋/测试订单。

规则（口径来自 business_definition.monitor.test_order_filter）：
  1. store_name ∈ hq_stores 且 buyer_identity_no 非空且不符合 18 位身份证格式 → 测试单；
  2. buyer_identity_no 或 owner_identity_no 为占位号（placeholder_ids，默认 9999999）→ 测试单，
     不限门店：占位号是内部预埋/测试单的显式标记。

注意：order_type 为空不作为判定条件（新车型预售期 order_type 常未填充）。
"""

from __future__ import annotations

import re

import pandas as pd

DEFAULT_HQ_STORES = ("总部主理店",)
DEFAULT_PLACEHOLDER_IDS = ("9999999",)
_VALID_ID_RE = re.compile(r"^\d{17}[\dXx]$")


def _test_order_cfg(bdef: dict | None = None) -> dict:
    mon = (bdef or {}).get("monitor") or {}
    return mon.get("test_order_filter") or {}


def hq_stores(bdef: dict | None = None) -> tuple[str, ...]:
    stores = _test_order_cfg(bdef).get("hq_stores") or DEFAULT_HQ_STORES
    return tuple(str(s) for s in stores)


def placeholder_ids(bdef: dict | None = None) -> tuple[str, ...]:
    """内部占位身份号（如 9999999），命中即视为测试单。"""
    ids = _test_order_cfg(bdef).get("placeholder_ids") or DEFAULT_PLACEHOLDER_IDS
    return tuple(str(s).strip() for s in ids)


def is_fake_identity(value) -> bool:
    """非空且不是 18 位身份证格式（末位可 X）→ 视为假身份号。空值不算。"""
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none", "null"):
        return False
    return _VALID_ID_RE.match(s) is None


def is_placeholder_identity(value, bdef: dict | None = None) -> bool:
    """占位/内部测试号（如 9999999）→ True。空值不算。"""
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none", "null"):
        return False
    return s in placeholder_ids(bdef)


def flag_test_orders(df: pd.DataFrame, bdef: dict | None = None) -> pd.Series:
    """返回测试单布尔掩码。

    命中任一条件即为测试单：
      - HQ 门店 + 假身份号（buyer_identity_no 非 18 位身份证格式）
      - buyer_identity_no / owner_identity_no 为占位号（不限门店）
    """
    mask = pd.Series(False, index=df.index)

    if "store_name" in df.columns and "buyer_identity_no" in df.columns:
        hq = df["store_name"].astype("string").isin(list(hq_stores(bdef)))
        fake = df["buyer_identity_no"].map(is_fake_identity)
        mask = mask | (hq & fake)

    for col in ("buyer_identity_no", "owner_identity_no"):
        if col in df.columns:
            mask = mask | df[col].map(lambda v: is_placeholder_identity(v, bdef))

    return mask.fillna(False)


def filter_test_orders(df: pd.DataFrame, bdef: dict | None = None) -> pd.DataFrame:
    """剔除测试单，返回副本。"""
    mask = flag_test_orders(df, bdef)
    return df.loc[~mask].copy()
