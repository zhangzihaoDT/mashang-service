#!/usr/bin/env python3
"""config_semantics 业务定义表加载器。

从 shared/schema/config_semantics.json 读取
基于 (Attribute, value_code) 的配置业务语义，供配置选配/渗透率类报告消费，
替代代码内硬编码判定。

核心能力：
- 按 (series, attribute) 查询属性定义（category / semantic / codes）；
- 按 value_code 归一化 display 名；
- 反推 value_code 为 NaN 的历史行的 code（经 aliases / display 匹配）；
- 判定某 (attribute, value_code) 是否属于"已选/含该配置"语义。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_SEMANTICS_PATH = REPO_ROOT / "shared" / "schema" / "config_semantics.json"

# boolean 型选装属性的正/负 value_code
BOOLEAN_POSITIVE = {"Y", "YES", "TRUE", "1", "是"}
BOOLEAN_NEGATIVE = {"N", "NO", "FALSE", "0", "否"}


def load_config_semantics() -> dict:
    """加载 config_semantics 定义表。"""
    data = json.loads(CONFIG_SEMANTICS_PATH.read_text(encoding="utf-8"))
    return data


def get_series_semantics(config_semantics: dict, series: str) -> dict:
    """返回某车系的 attributes 定义；缺失时返回空。"""
    return (config_semantics.get("series") or {}).get(series, {}).get("attributes", {})


def get_attribute_spec(config_semantics: dict, series: str, attribute: str) -> dict:
    """返回某车系某属性的定义；缺失时返回空 dict。"""
    attrs = get_series_semantics(config_semantics, series)
    return attrs.get(attribute) or {}


def is_noise_attribute(attribute_spec: dict) -> bool:
    """是否为极小量 NaN-only 历史噪音属性。"""
    return attribute_spec.get("semantic") == "noise"


def resolve_value_code(attribute_spec: dict, value_code, value: str) -> tuple:
    """把一行配置归一到 (value_code, display)。

    返回 (code, display)。code 为空表示无法归一到定义表中的任意 code。
    value_code 缺失时，尝试按 value 文本在 codes 的 aliases/display 中反推。
    """
    codes = attribute_spec.get("codes") or {}
    if not codes:
        return "", ""
    raw_code = "" if value_code is None else str(value_code).strip()
    if raw_code in codes:
        return raw_code, codes[raw_code].get("display", value)
    if raw_code:
        # 存在未在定义表中的 code：回退原 value 显示名
        return "", value
    # value_code 缺失 → 反推
    norm = str(value).strip()
    for code, code_spec in codes.items():
        aliases = code_spec.get("aliases") or []
        display = code_spec.get("display", "")
        if norm == display or norm in aliases:
            return code, display
        # 部分 value 为 code 显示名的别名（如 "是"/"否" 对应 Y/N）
        if norm in BOOLEAN_POSITIVE and code == "Y":
            return code, display
        if norm in BOOLEAN_NEGATIVE and code == "N":
            return code, display
    return "", value


def code_is_selected(attribute_spec: dict, code: str) -> bool:
    """某 (attribute, code) 是否表示"含该配置/已选"。

    - boolean 型：included 字段决定（Y=含，N=不含）；
    - enum / selection_tier：每个 code 都是实际选择，included 默认 True。
    """
    codes = attribute_spec.get("codes") or {}
    code_spec = codes.get(code) or {}
    return bool(code_spec.get("included", True))


def build_value_to_code_map(attribute_spec: dict) -> dict:
    """构建 value 文本 → code 的反查表（供 value_code 缺失时快速反推）。"""
    mapping = {}
    for code, code_spec in (attribute_spec.get("codes") or {}).items():
        mapping[code_spec.get("display", "")] = code
        for alias in code_spec.get("aliases") or []:
            mapping[alias] = code
    return mapping
