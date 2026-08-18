"""watchlist 品牌分析公共数据加载。

供 watchlist 品牌月报 / 12 个月趋势 / 车型贡献拆解 三个脚本共用：
- watchlist 品牌归一化（brand_alias_map.yaml 映射）
- 环比/同比月份推导、12 个月窗口
- brand / model 两级销量聚合（groupby-sum 规避重复 grain）
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
WATCHLIST_PATH = ROOT / "MIIT" / "workflow" / "brand_watchlist.yaml"
DEFAULT_OWN_BRAND = "智己"


def load_watchlist() -> Dict[str, List[str]]:
    """读取 brand_watchlist.yaml 并归一化到数据集品牌值（分组名 -> 品牌值列表）。"""
    from utils.brand_mapping import normalize_watchlist_brands

    raw = yaml.safe_load(WATCHLIST_PATH.read_text(encoding="utf-8"))
    return normalize_watchlist_brands(raw)


def month_range(month: str) -> Dict[str, str]:
    """由报告月份推导 环比/同比 三个月份。"""
    cur = pd.Timestamp(month + "-01")
    prev = cur - pd.DateOffset(months=1)
    yoy = cur - pd.DateOffset(years=1)
    return {
        "cur": cur.strftime("%Y-%m-01"),
        "prev": prev.strftime("%Y-%m-01"),
        "yoy": yoy.strftime("%Y-%m-01"),
    }


def trend_months(month: str, n: int = 12) -> List[str]:
    """最近 n 个月（含基准月，升序）。"""
    cur = pd.Timestamp(month + "-01")
    return [(cur - pd.DateOffset(months=i)).strftime("%Y-%m-01") for i in range(n - 1, -1, -1)]


def load_brand_sales() -> pd.DataFrame:
    """brand × month 销量（groupby-sum 规避 brand_monthly 重复 grain）。"""
    from shared.loaders.tp_and_mix_ways_loader import load_tp_and_mix_ways_table

    df = load_tp_and_mix_ways_table("brand_monthly")
    assert df is not None, "brand_monthly 未构建"
    return df.groupby(["brand", "date_month"], as_index=False)["sales"].sum()


def load_model_sales() -> pd.DataFrame:
    """brand × model × month 销量（groupby-sum 规避 model_monthly 重复 grain）。"""
    from shared.loaders.tp_and_mix_ways_loader import load_tp_and_mix_ways_table

    df = load_tp_and_mix_ways_table("model_monthly")
    assert df is not None, "model_monthly 未构建"
    return df.groupby(["brand", "model", "date_month"], as_index=False)["sales"].sum()


def load_market_sales(months) -> pd.DataFrame:
    """大盘（market_energy_monthly）销量。months 为日期列表。"""
    from shared.loaders.tp_and_mix_ways_loader import load_tp_and_mix_ways_table

    df = load_tp_and_mix_ways_table("market_energy_monthly")
    assert df is not None, "market_energy_monthly 未构建"
    return df[df.date_month.isin(months)].groupby("date_month")["sales"].sum().reset_index()


def fmt_pct(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:+.1f}%"


def safe_int(v) -> int:
    """把值安全转 int；NaN / None → 0（用于品牌某月无数据的场景）。"""
    if v is None:
        return 0
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return 0
        return int(v)
    except (TypeError, ValueError):
        return 0
