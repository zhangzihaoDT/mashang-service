"""监控测试单过滤 — 排除「总部主理店 + 假身份号」的预埋/测试订单。

规则（口径来自 business_definition.monitor.test_order_filter）：
  store_name ∈ hq_stores 且 buyer_identity_no 非空且不符合 18 位身份证格式 → 测试单。

注意：order_type 为空不作为判定条件（新车型预售期 order_type 常未填充）。
"""

from __future__ import annotations

import re

import pandas as pd

DEFAULT_HQ_STORES = ("总部主理店",)
_VALID_ID_RE = re.compile(r"^\d{17}[\dXx]$")


def hq_stores(bdef: dict | None = None) -> tuple[str, ...]:
    mon = (bdef or {}).get("monitor") or {}
    cfg = mon.get("test_order_filter") or {}
    stores = cfg.get("hq_stores") or DEFAULT_HQ_STORES
    return tuple(str(s) for s in stores)


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


def flag_test_orders(df: pd.DataFrame, bdef: dict | None = None) -> pd.Series:
    """返回测试单布尔掩码（HQ 门店 且 假身份号）。"""
    if "store_name" not in df.columns or "buyer_identity_no" not in df.columns:
        return pd.Series(False, index=df.index)
    hq = df["store_name"].astype("string").isin(list(hq_stores(bdef)))
    fake = df["buyer_identity_no"].map(is_fake_identity)
    return (hq & fake).fillna(False)


def filter_test_orders(df: pd.DataFrame, bdef: dict | None = None) -> pd.DataFrame:
    """剔除测试单，返回副本。"""
    mask = flag_test_orders(df, bdef)
    return df.loc[~mask].copy()
