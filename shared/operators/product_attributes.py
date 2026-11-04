"""产品属性解析 —— product_name → 代际 → 版本 → 动力类型（单一事实来源）。

设计原则（shared/schema/business_definition.json）：

  product_name → series_group_logic（代际）
               → product_version_logic（版本）
               → product_version_series.power_type（动力类型）
  座位、电池容量独立识别，不参与动力判定。

为什么不再各自猜测动力类型：
  历史实现用 product_type_logic 的「含 52/66 ⇒ 增程，否则纯电」模糊匹配，
  与 product_version_logic 的版本串两套规则并存，容易互相打架（如 93 RWD 被判成纯电
  纯属"没有 52/66"，NEO 103 Max+ 同理）。本模块让版本成为动力分类的事实来源：
  新增纯电版本只需在 product_version_series 补一行，不必再改多处 SQL/正则。

对生产口径的守护：
  product_version_series 未覆盖的 LS8/LS8Neo product_name 不是静默猜一个动力，
  而是返回 动力=未知 并在 warnings 中列出，避免新名字悄悄改变增程/纯电拆分。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

UNKNOWN = "未知"
NO_SEAT = "未标座位"
UNCLASSIFIED = "未分类"
KWH_NOT_CONFIRMED = "未证实"

# 由 product_version_series 管理动力的车系（版本即事实来源）
SERIES_WITH_VERSION_POWER: tuple[str, ...] = ("LS8", "LS8Neo")


def _strip_ws(value) -> str:
    return "".join(str(value).split())


def _rule_condition(rule) -> str:
    if isinstance(rule, dict):
        return str(rule.get("condition", ""))
    return str(rule)


def _rule_priority(rule, default: int = 0) -> int:
    if isinstance(rule, dict):
        try:
            return int(rule.get("priority", default))
        except (TypeError, ValueError):
            return default
    return default


def _eval_expr(product_name: pd.Series, expr: str) -> pd.Series:
    """复用 series_group_logic 的 LIKE/NOT LIKE/AND/OR/括号语义（空格不敏感）。"""
    from operators.series_group_logic import _eval_series_group_logic_expr

    return _eval_series_group_logic_expr(product_name, expr)


def _first_match(product_name: pd.Series, rules: dict, unknown: str) -> pd.Series:
    out = pd.Series([unknown] * len(product_name), index=product_name.index, dtype="object")
    ordered = sorted(rules.items(), key=lambda kv: (-_rule_priority(kv[1]), 0))
    for label, rule in ordered:
        mask = _eval_expr(product_name, _rule_condition(rule))
        if mask.any():
            out = out.where(~(mask & out.eq(unknown)), other=label)
    return out


@dataclass
class ProductAttributes:
    """解析结果（列与 df 同索引）。"""

    generation: pd.Series
    version: pd.Series
    power_type: pd.Series
    seat_count: pd.Series
    battery_kwh: pd.Series
    warnings: list[str] = field(default_factory=list)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "series_group_logic": self.generation,
                "product_version": self.version,
                "product_type": self.power_type,
                "seat_count": self.seat_count,
                "battery_kwh": self.battery_kwh,
            }
        )


def _series_table(series_key: str, bdef: dict) -> dict:
    """版本字典按车系（model_series_mapping 的族）组织；代际组（如 LS8Neo）回退到所属车系。

    LS8 族下 LS8 / LS8Neo 两个代际组共用同一张版本表，避免同一版本在两个代际重复维护。
    """
    series_map = (bdef.get("product_version_series") or {}).get("series") or {}
    if series_key in series_map:
        return series_map[series_key] or {}
    for series_name, groups in (bdef.get("model_series_mapping") or {}).items():
        if series_key in groups:
            return series_map.get(series_name) or {}
    return {}


def _power_for_series(series_key: str, version: pd.Series, bdef: dict) -> tuple[pd.Series, list[str]]:
    table = _series_table(series_key, bdef)
    out = pd.Series([UNKNOWN] * len(version), index=version.index, dtype="object")
    for version_name, meta in table.items():
        power = (meta or {}).get("power_type")
        if power:
            out = out.where(~version.eq(version_name), other=power)
    unmatched = sorted(version[out.eq(UNKNOWN)].dropna().unique().tolist())
    warnings = []
    if unmatched:
        warnings.append(
            f"{series_key} 有版本未在 product_version_series 登记动力类型：{unmatched}"
            f"（{int(out.eq(UNKNOWN).sum())} 行），已标记为未知；请在版本字典补登记"
        )
    return out, warnings


def _battery_for_series(series_key: str, version: pd.Series, bdef: dict) -> pd.Series:
    table = _series_table(series_key, bdef)
    out = pd.Series([KWH_NOT_CONFIRMED] * len(version), index=version.index, dtype="object")
    for version_name, meta in table.items():
        kwh = (meta or {}).get("battery_kwh")
        label = f"{kwh}kwh" if kwh not in (None, "") else KWH_NOT_CONFIRMED
        out = out.where(~version.eq(version_name), other=label)
    return out


def product_type_of(product_name: str, bdef: dict) -> str:
    """单个 product_name 的动力类型（增程/纯电/未知）。无法解析返回「未知」，不默认纯电。"""
    if product_name is None:
        return UNKNOWN
    name = str(product_name).strip()
    if not name or name.lower() in {"nan", "none", "null"}:
        return UNKNOWN
    frame = pd.DataFrame({"product_name": [name]})
    return str(resolve_product_attributes(frame, bdef).power_type.iloc[0])


def resolve_product_attributes(df: pd.DataFrame, bdef: dict) -> ProductAttributes:
    """解析整表产品归属：代际 / 版本 / 动力 / 座位 / 电池。

    输入 df 需含 product_name；若已含 series_group_logic 列则直接复用（避免重复分类）。
    """
    if "product_name" not in df.columns:
        raise ValueError("resolve_product_attributes 需要 product_name 列")

    unknown_cols = pd.Series([UNCLASSIFIED] * len(df), index=df.index, dtype="object")
    if "series_group_logic" in df.columns:
        generation = df["series_group_logic"].fillna(UNCLASSIFIED).astype("object")
    else:
        from operators.series_group_logic import apply_series_group_logic

        generation = apply_series_group_logic(df.copy(), bdef)["series_group_logic"].astype("object")

    product_name = df["product_name"]
    version_rules = bdef.get("product_version_logic") or {}
    seat_rules = bdef.get("seat_count_logic") or {}

    version = pd.Series([UNCLASSIFIED] * len(df), index=df.index, dtype="object")
    seat = _first_match(product_name, seat_rules, NO_SEAT) if seat_rules else pd.Series(
        [NO_SEAT] * len(df), index=df.index, dtype="object"
    )
    if not version_rules:
        version = unknown_cols
    else:
        for gen_key, rules in version_rules.items():
            mask = generation.eq(gen_key)
            if mask.any():
                version = version.where(~mask, other=_first_match(product_name[mask], rules, UNCLASSIFIED))

    power = pd.Series([UNKNOWN] * len(df), index=df.index, dtype="object")
    battery = pd.Series([KWH_NOT_CONFIRMED] * len(df), index=df.index, dtype="object")
    warnings: list[str] = []
    for gen_key in version_rules:
        mask = generation.eq(gen_key)
        if not mask.any():
            continue
        if gen_key not in SERIES_WITH_VERSION_POWER:
            continue
        p, w = _power_for_series(gen_key, version[mask], bdef)
        power = power.where(~mask, other=p)
        battery = battery.where(~mask, other=_battery_for_series(gen_key, version[mask], bdef))
        warnings.extend(w)

    # 非版本字典管理的车系（LS6 / L6 / LS9…）：沿用 product_type_logic 模糊规则
    rest = ~generation.isin(SERIES_WITH_VERSION_POWER)
    if rest.any():
        pname = product_name[rest]
        rest_power = pd.Series([UNKNOWN] * len(pname), index=pname.index, dtype="object")
        for ptype, expr in (bdef.get("product_type_logic") or {}).items():
            if not expr:
                continue
            mask = _eval_expr(pname, str(expr))
            rest_power = rest_power.where(~mask, other=ptype)
        power = power.where(~rest, other=rest_power)

    return ProductAttributes(
        generation=generation,
        version=version,
        power_type=power,
        seat_count=seat,
        battery_kwh=battery,
        warnings=warnings,
    )
