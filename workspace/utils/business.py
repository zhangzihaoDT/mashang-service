"""
业务定义工具函数

统一从 shared/schema/business_definition.json 读取上市时间等业务口径。
"""

import json
from pathlib import Path
from typing import Optional

from utils.paths import BUSINESS_DEFINITION_PATH


def is_corporate_owner(owner_identity_no) -> bool:
    """
    判断 owner_identity_no 是否为企业标识（对公批售），而非个人身份证。

    判定规则（按优先级）：
      1. 长度 != 18 → False
      2. 18 位 + 包含字母（非末尾 X，或 X 在非末位）→ 统一社会信用代码 → True
      3. 18 位纯数字，但不符合身份证日期格式（YYYYMMDD）→ 旧版企业注册号 → True
      4. 匹配身份证格式 → False

    用法:
        is_corporate_owner("91320100MA204QQ33M")       # True  (统一社会信用代码)
        is_corporate_owner("914501003307932183")        # True  (旧版企业注册号, 纯数字)
        is_corporate_owner("110101199001011234")        # False (身份证)
        is_corporate_owner("31010120000101567X")        # False (身份证, 末位X)
        is_corporate_owner(None)                        # False
    """
    import pandas as pd
    import re
    if owner_identity_no is None or (isinstance(owner_identity_no, float) and pd.isna(owner_identity_no)):
        return False
    s = str(owner_identity_no).strip().upper()
    if len(s) != 18:
        return False
    # 规则2: 含字母（非末尾X，或X在非末位）→ 统一社会信用代码
    for i, ch in enumerate(s):
        if ch.isalpha() and ch != 'X':
            return True
        if ch == 'X' and i < 17:
            return True
    # 规则3: 纯数字，非身份证日期格式 → 旧版企业注册号
    if s.isdigit():
        # 身份证日期格式: 第7-14位为 YYYYMMDD
        birth_str = s[6:14]
        try:
            import datetime
            datetime.datetime.strptime(birth_str, "%Y%m%d")
            return False  # 有效日期 → 身份证
        except ValueError:
            return True   # 无效日期 → 企业注册号
    return False


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


def classify_product_names(df, series: str, business_definition=None):
    """按共享业务定义返回 product_version / seat_count；保留输入索引。

    调用方传入含 product_name 的 DataFrame；可复用已加载的业务定义。
    版本按 priority 降序、同分按定义顺序首次命中；未知项显式保留。
    """
    import pandas as pd
    from utils.monitors.series_group import (
        eval_series_group_logic_expr, rule_condition, rule_priority,
    )

    if business_definition is None:
        business_definition = json.loads(BUSINESS_DEFINITION_PATH.read_text(encoding='utf-8'))
    result = pd.DataFrame(index=df.index)
    result['product_version'] = '未分类'
    result['seat_count'] = '未标座位'
    definitions = [
        ('product_version', business_definition.get('product_version_logic', {}).get(series, {}), '未分类'),
        ('seat_count', business_definition.get('seat_count_logic', {}), '未标座位'),
    ]
    for column, rules, unknown in definitions:
        ordered = sorted(rules.items(), key=lambda item: -rule_priority(item[1]))
        for label, rule in ordered:
            mask = eval_series_group_logic_expr(df['product_name'], rule_condition(rule))
            result.loc[mask & result[column].eq(unknown), column] = label
    return result
