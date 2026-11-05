#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[DEPRECATED] L6 M2 预售情况汇报兼容入口。

通用实现已迁移到 research_scripts/presale_cumulative_order_compare.py：
    python research_scripts/presale_cumulative_order_compare.py \
        --gens DM1 CM2 LS9 LS8 DM2 --as-of 2026-08-24 --format html

本文件保留仅为兼容旧调用（默认 DM2 主代际 + HTML 输出）。
注意：通用脚本已移除「集团 / 观星台」背景模块；--guanxingta-dir 参数不再生效。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(_WS_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.monitors.phase import load_business_definition  # noqa: E402
from utils.monitors.series_group import apply_series_group_logic  # noqa: E402

_ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
_DATETIME_COLS = [
    "intention_payment_time",
    "intention_refund_time",
    "deposit_payment_time",
    "deposit_refund_time",
    "first_assign_time",
    "lock_time",
    "invoice_upload_time",
    "delivery_date",
    "order_create_date",
]
_DEFAULT_GENS = ["DM1", "CM2", "LS9", "LS8", "DM2"]


def load_order(apply_group: bool = True) -> pd.DataFrame:
    """向后兼容：旧调用方（l6_m2_daily_retention / l6_m2_daily_lock_by_edition）使用。"""
    df = pd.read_parquet(_ORDER_PARQUET)
    for c in _DATETIME_COLS:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    if apply_group:
        bd = load_business_definition(REPO_ROOT / "shared/schema/business_definition.json")
        df = apply_series_group_logic(df, bd)
    return df


def main() -> int:
    from research_scripts.presale_cumulative_order_compare import main as _main

    if "--gens" not in sys.argv:
        sys.argv += ["--gens", *_DEFAULT_GENS]
    if "--format" not in sys.argv and "--html" not in sys.argv:
        sys.argv.append("--html")
    if "--guanxingta-dir" in sys.argv:
        print("⚠️ 通用脚本已移除集团/观星台模块，--guanxingta-dir 不再生效")
    return _main()


if __name__ == "__main__":
    raise SystemExit(main())
