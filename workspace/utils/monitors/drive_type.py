"""drive_type_logic 统一入口。

读取 `business_definition.json: drive_type_logic`，基于 product_name 生成
`drive_type`（四驱 / 后驱；未覆盖车系保持默认值）。

当前覆盖 LS6 家族（CM0–CM3），非 LS6 车系不分类。
规则为 `{label: "product_name LIKE ..."}`，各分支互斥，标签命中即生效。
"""

from __future__ import annotations

import pandas as pd

from utils.monitors.series_group import eval_series_group_logic_expr

DEFAULT_DRIVE_TYPE = "未知"


def apply_drive_type_logic(df: pd.DataFrame, business_definition: dict) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if "drive_type" in df.columns:
        return df
    if "product_name" not in df.columns:
        df["drive_type"] = pd.NA
        return df

    logic = (business_definition or {}).get("drive_type_logic") or {}
    if not isinstance(logic, dict) or not logic:
        df["drive_type"] = pd.NA
        return df

    product_name = df["product_name"]
    out = pd.Series([DEFAULT_DRIVE_TYPE] * len(df), index=df.index, dtype="string")
    for label, expr in logic.items():
        mask = eval_series_group_logic_expr(product_name, str(expr))
        out = out.where(~mask, other=label)
    df["drive_type"] = out
    return df
