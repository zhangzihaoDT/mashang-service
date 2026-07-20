"""
业务定义工具函数

统一从 shared/schema/business_definition.json 读取上市时间等业务口径。
"""

import json
from pathlib import Path
from typing import Optional

from utils.paths import BUSINESS_DEFINITION_PATH


def get_launch_date(series: str) -> Optional[str]:
    """
    返回指定车系/系列分组的上市日期（time_periods.{series}.end）。
    如果未找到则返回 None。

    用法:
        launch_date = get_launch_date("LS9")       # "2025-11-12"
        launch_date = get_launch_date("CM2")       # "2025-09-10"
        launch_date = get_launch_date("LS9Hyper")  # "2026-07-16"
    """
    try:
        bdef = json.loads(BUSINESS_DEFINITION_PATH.read_text(encoding="utf-8"))
        periods = bdef.get("time_periods", {})
        if series not in periods:
            return None
        return periods[series].get("end")
    except Exception:
        return None


def get_launch_date_or_raise(series: str) -> str:
    """
    同 get_launch_date，但未找到时抛出 KeyError。
    """
    date = get_launch_date(series)
    if date is None:
        raise KeyError(
            f"business_definition.json 中未找到 {series!r} 的 time_periods.end"
        )
    return date


def list_all_series() -> list[dict]:
    """
    返回所有已定义车系/系列分组的上市信息列表。
    """
    try:
        bdef = json.loads(BUSINESS_DEFINITION_PATH.read_text(encoding="utf-8"))
        periods = bdef.get("time_periods", {})
        return [
            {"series": k, "start": v.get("start"), "end": v.get("end"), "finish": v.get("finish")}
            for k, v in periods.items()
        ]
    except Exception:
        return []
