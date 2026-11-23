#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多代际用户车锁单的配置选装比例横向对比。

被比较的 5 个车型（业务术语经 generation_terminology_mapping 解析，避免硬编码）：
  大F M0 → LS9；小F M0 → LS8；CM3 → CM3（纯电）；CM2 纯电 → CM2 按动力拆分；DM2 → DM2

口径：
  - 锁单：order_data.parquet，series_group_logic 命中目标代际、lock_time 非空，order_number 去重；
  - 时间窗：使用数据中已有锁单，上市日期取 business_definition.time_periods.<gen>.end；
  - 仅用户车：order_type == '用户车'（严格零售口径，不含 NaN/试驾车/员工等）；
  - CM2 纯电：CM2 内按 product_type_logic 拆分（52/66 → 增程，其余 → 纯电），只保留纯电；
  - 配置：config_attribute.parquet 中该批订单的配置行，按 attribute_code 对齐属性。

选装比例定义（分母 = 该组全部用户车锁单；**无记录 = 未选**）：
  - 是/否型（BIN）：比例 = 显式「是」的订单数 / 全部锁单；无记录的订单计入「否」。
    例：LS8「全线控转向系统」只对选了它的订单落行，无记录的订单视为没选，
    故比例是 11.67%（1,446 / 12,390），而不是 31.6%（1,446 / 4,574 有记录）。
  - 多值单选型（CHO）：各取值 / 全部锁单，取值过多时其余归入「其它（合计）」。
  - 轮毂：按尺寸档位（19/20/21/22 英寸）归并后再算——同一 value_code 在不同代际
    对应不同中文名，尺寸是唯一稳定的可比维度。

缺少属性编码时使用原名称及 SYNONYM_GROUPS。属性归并后按订单去重，
任一记录为「是」即计一次，分母仍是全部锁单。

系列内拆分（SUBSERIES）：LS9 → 普通 / Hyper，DM2 → 普通 / JimChoo，CM2 → 纯电 / 增程；
LS8 → 大五座 / 大六座（座位归属：产品名优先，2026-11-06 起改由「座椅」属性还原）。

录入异常订单（audit_mixed_templates）从所有统计中剔除，只在页面底部列出清单；
判据仅限「走另一套配置录入模板」的订单，正常产品差异与加装一律保留。

用法：
  python research_scripts/lock_config_option_compare.py
  python research_scripts/lock_config_option_compare.py --format json --output outputs/tables
  python research_scripts/lock_config_option_compare.py --html
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = REPO_ROOT / "workspace"
for _p in (str(REPO_ROOT), str(_WS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.monitors.launch import resolve_launch_date, resolve_launch_open_from_data  # noqa: E402
from utils.monitors.order_filter import filter_test_orders  # noqa: E402
from utils.monitors.phase import load_business_definition  # noqa: E402
from utils.monitors.series_group import apply_series_group_logic  # noqa: E402

_BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
_ORDER_DATA = REPO_ROOT / "dataset" / "order_data.parquet"
_CONFIG_DATA = REPO_ROOT / "dataset" / "config_attribute.parquet"
_DEFAULT_OUT = _WS / "outputs" / "tables"

# (展示名, 解析 token)；token 依次支持 代际键 / series_labels / 业务术语
DEFAULT_CELLS: list[tuple[str, str]] = [
    ("大F M0", "大F M0"),
    ("小F M0", "小F M0"),
    ("CM3", "CM3"),
    ("CM2 纯电", "CM2"),
    ("DM2", "DM2"),
]

# 系列内拆分（子车型）：父级 token → [(展示名, 附加过滤函数名, 参数)]
# 子车型与父级同时展示，子车型的 n 之和 = 父级 n（每张单只归入一个子车型）。
# Hyper / Jimmy Choo 用 product_name 识别；CM2 增程/纯电按 product_type_logic 识别。
SUBSERIES: dict[str, list[tuple[str, str, str]]] = {
    "LS9": [
        ("LS9 普通", "NOT_CONTAINS", "Hyper"),
        ("LS9 Hyper", "CONTAINS", "Hyper"),
    ],
    "DM2": [
        ("DM2 普通", "NOT_CONTAINS", "Jimmy"),
        ("DM2 JimChoo", "CONTAINS", "Jimmy"),
    ],
    "CM2": [
        ("CM2 纯电", "POWER", "纯电"),
        ("CM2 增程", "POWER", "增程"),
    ],
}
# 默认在 5 个主车型之外，额外输出这些拆分
DEFAULT_SPLITS = ["LS9", "DM2", "CM2"]
CN2GEN = {"大F M0": "LS9", "小F M0": "LS8", "CM3": "CM3", "CM2 纯电": "CM2", "DM2": "DM2"}
# 默认排除：内饰 / 外饰 / 方向盘（按归一化后的属性名包含判断，覆盖「内饰风格」「YAT巡航型…方向盘」等变体）
DEFAULT_EXCLUDE_NAMES = ["内饰", "外饰", "方向盘", "座椅"]
# 多值单项超过该数量时，其余取值归入「其它（合计）」
MAX_CHO_VALUES = 6
YES, NO = "是", "否"

# 缺少属性编码时，用以下名称归并同一配置。
#   - 车载冰箱 / 智能冷暖双用冰箱：LS9 Hyper 用前者、普通版用后者，是同一台冰箱
#   - 拖挂系统 / 拖挂尾勾：LS9 两套命名并存
#   - 21.5英寸二排观影屏 / 21.5英寸4K二排观影屏：LS8 同一块屏的两个命名版本
SYNONYM_GROUPS: dict[str, list[str]] = {
    "冰箱": ["车载冰箱", "智能冷暖双用冰箱"],
    "拖挂": ["拖挂系统", "拖挂尾勾"],
    "21.5英寸二排观影屏": ["21.5英寸二排观影屏", "21.5英寸4K二排观影屏"],
}
ATTRIBUTE_NOTES = {
    "OP-LASER": "各代际的激光雷达取值对应不同档位。LS8 按选装包档位派生。",
    "OP-Battery": "该编码也用于「5C 超快充电池+车载冰箱」套包。套包与单独电池的选装率需分别解读。",
}

# ── 档位型属性（selection_tier）────────────────────────────────────────────
# 「已选」不是并列选项，而是【选装包档位】：config_semantics.json 定义为 selection_tier。
#   Stand = 超远距高精度激光雷达（标配方案，**不含**奢华智选包）
#   Pro   = 奢华智选包
#   Plus  = 奢华智选包 + 一体式超广域探射灯
# 因此不能把三个取值并列当选项报「奢华智选包 95%」——Plus 档也含智选包。
# 正确派生：
#   - 奢华智选包 = Pro ∪ Plus
#   - 一体式超广域探射灯 = Plus
#   - 标配激光雷达方案 = Stand
# 历史实现见 research_scripts/ls8_configuration_selection_report.py。
TIER_ATTRS = {"已选"}
# ── 旧版档位字段 → 标准档位的同义归并 ─────────────────────────────────────
# LS8 早期订单用三个独立属性记录选装方案，而不是「已选」档位字段：
#   舒适包 = 是                     → 含奢华智选包
#   超远距高精度双激光雷达 = 标准      → 标配激光雷达方案（对应 Stand 档语义）
#   顶探照灯 = 否                   → 未加装一体式超广域探射灯
# 三者同时出现且取值唯一（LS8 共 70 单），等价于「已选 = Pro」：含智选包、无探射灯。
# 因此把它们归并为 Pro 档，而不是把订单剔出统计——这些是真实用户订单。
LEGACY_TIER_ATTRS = {
    "舒适包": {"是"},
    "超远距高精度双激光雷达": {"标准"},
    "顶探照灯": {"否"},
}
LEGACY_TIER_TARGET = "Pro"      # 三项同时命中 → 视为 Pro 档

# 注意 Stand 档的取值名恰好是「超远距高精度激光雷达」，这是【已选列的一个档位名】，
# 不是一个独立的激光雷达属性（LS8 数据里没有独立的激光雷达属性，记录数为 0）。
# 因此只派生「是否购买智选包」这一个有数据支撑的对照维度，不再单独派生
# 「激光雷达 100%」——那会与 Stand 档同名，读者会看到「不含智选包」与「含于全部档位」
# 两条自相矛盾的表述。
TIER_DERIVED: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "已选": [
        ("奢华智选包", ("Pro", "Plus")),
        ("一体式超广域探射灯", ("Plus",)),
        ("不购买智选包（选标配方案，Stand 档）", ("Stand",)),
    ],
}

# ── 配置项的适用范围：某些配置只对特定动力类型/结构可用 ──────────────────────
# 这类配置在不适用的组里出现，只可能是数据串入或结构不可选：
#   - 5C 超快充电池：纯电专属配置。增程组里出现 2 单（1 单标价 8000 元选了纯电专属件，
#     1 单显式记「否」），对增程而言该配置不存在，整项不呈现。
# 键为属性名，值为该属性「适用于哪些 (gen, power_type)」，未列出的组不展示该配置项。
ATTR_APPLICABILITY: dict[str, set[tuple[str, str]]] = {
    "5C 超快充电池": {("CM2", "纯电")},
}

# LS8 座位归属：产品名带「大五座/大六座」时以产品名为准；
# 2026-11-06 起产品名不再带座位，座位改由「座椅」属性记录，此时从属性还原。
SEAT_ATTR_MAP = {"旗舰大五座": "大五座", "奢享大六座": "大六座"}
# 座位属性是归属口径，不作为选装比例统计
SEAT_ATTRS = {"座椅"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text)).upper()


def resolve_token(bd: dict, token: str) -> str:
    """解析代际 token：先精确键，再忽略大小写键，最后业务术语（generation_terminology_mapping）。"""
    keys = list((bd.get("series_group_logic") or {}).keys())
    if token in keys:
        return token
    low = {k.lower(): k for k in keys}
    if token.lower() in low:
        return low[token.lower()]
    labels = (bd.get("monitor") or {}).get("series_labels") or {}
    for gen, label in labels.items():
        if token == label:
            return gen
    index = {}
    for gen, names in (bd.get("generation_terminology_mapping") or {}).items():
        for name in (names if isinstance(names, list) else [names]):
            index[_norm(name)] = gen
    if _norm(token) in index:
        return index[_norm(token)]
    raise SystemExit(
        f"无法解析车型 token {token!r}：不在 series_group_logic 键、series_labels 或业务术语中"
    )


def power_type(product_name: str) -> str:
    """product_type_logic：52/66 → 增程，其余 → 纯电（LS8 家族除外，见 business_definition 语义）。"""
    n = _norm(product_name)
    return "增程" if ("52" in n or "66" in n) else "纯电"


def load_lock_universe(bd: dict) -> pd.DataFrame:
    """用户车 + 已锁单 + 剔除测试单，含代际归属与动力类型。"""
    cols = [
        "order_number", "order_type", "lock_time", "product_name", "series",
        "store_name", "buyer_identity_no", "owner_identity_no", "intention_payment_time",
    ]
    df = pd.read_parquet(_ORDER_DATA, columns=cols)
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df["intention_payment_time"] = pd.to_datetime(df["intention_payment_time"], errors="coerce")
    df = apply_series_group_logic(df, bd)
    d = df[df["order_type"].eq("用户车") & df["lock_time"].notna()].copy()
    # 剔除测试单（总部主理店 + 假身份号 / 占位号），与上市监控同口径
    d = filter_test_orders(d, bd)
    d["order_number"] = d["order_number"].astype(str).str.strip()
    d = d.drop_duplicates("order_number")
    d["power_type"] = d["product_name"].map(power_type)
    return d


def launch_open_time(base: pd.DataFrame, bd: dict, gen: str) -> pd.Timestamp | None:
    """上市开放时刻（open_t）：上市当天首个真实锁单时刻，与上市监控同口径。"""
    launch = resolve_launch_date(bd.get("time_periods") or {}, gen)
    if launch is None:
        return None
    return resolve_launch_open_from_data(base, gen, launch, bdef=bd)


def select_orders(d: pd.DataFrame, gen: str, bev_only: bool, bd: dict,
                  open_t: pd.Timestamp | None = None) -> pd.DataFrame:
    """选定代际订单：上市至今（lock_time >= 开放时刻），剔除上市前锁单。"""
    s = d[d["series_group_logic"].eq(gen)]
    if open_t is not None:
        s = s[s["lock_time"] >= open_t]
    if bev_only:
        s = s[s["power_type"].eq("纯电")]
    return s


def attribute_keys(cfg: pd.DataFrame) -> pd.Series:
    names = cfg["Attribute"]
    aliases = {alias: name for name, members in SYNONYM_GROUPS.items() for alias in members}
    fallback = names.replace(aliases)
    if "attribute_code" not in cfg:
        return "name:" + fallback
    codes = (cfg["attribute_code"].astype("string").str.strip()
             .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "<NA>": pd.NA}))
    missing = codes.isna()
    if missing.any():
        pairs = pd.DataFrame({"name": names, "fallback": fallback, "code": codes}).dropna()
        for name_col, labels in (("name", names), ("fallback", fallback)):
            unique = pairs.groupby(name_col)["code"].agg(["nunique", "first"])
            unambiguous = unique.loc[unique["nunique"].eq(1), "first"]
            codes = codes.fillna(labels.map(unambiguous))
    return ("code:" + codes).fillna("name:" + fallback)


def attribute_identity(key: str, names: Counter) -> dict:
    code = key.removeprefix("code:") if key.startswith("code:") else None
    variants = sorted(names, key=lambda name: (-names[name], name))
    attr = variants[0] if code else key.removeprefix("name:")
    merged_from = variants if len(variants) > 1 else []
    if code is None:
        merged_from = SYNONYM_GROUPS.get(attr, merged_from)
    return {
        "attribute": attr, "attribute_code": code,
        **({"merged_from": merged_from} if merged_from else {}),
        **({"note": ATTRIBUTE_NOTES[code]} if code in ATTRIBUTE_NOTES else {}),
    }


def build_cell(s: pd.DataFrame, cfg_sub: pd.DataFrame, label: str, gen: str,
               bev_only: bool, exclude: list[str], as_of: pd.Timestamp) -> dict:
    """构建一个统计单元。

    分母口径（已与业务逐车型确认）：**无记录 = 未选**，分母统一用该单元全部用户车锁单，
    不再用「有记录的订单」做分母。这对「仅对已选订单落行」的配置（如全线控转向系统）
    尤其重要：无记录的那些订单视为没选，而不是从分母中剔除。
    """
    n = int(s["order_number"].nunique())
    # 本单元的动力类型（CM2 父级同时含纯电+增程，此时为 "混合"，不适用按动力类型过滤的配置）
    pts = set(s["power_type"].astype(str).unique()) if "power_type" in s else set()
    power_type = next(iter(pts)) if len(pts) == 1 else "混合"
    launch = pd.Timestamp(load_business_definition(_BUSINESS_DEF)["time_periods"][gen]["end"])
    ex_norms = [_norm(x) for x in exclude]
    attributes = []

    if "_attribute_key" not in cfg_sub:
        cfg_sub = cfg_sub.assign(_attribute_key=attribute_keys(cfg_sub))
    consumed: set[str] = set()

    # 旧版档位字段 → 补全为「已选」档位（同义归并，不剔除订单）
    legacy = cfg_sub[cfg_sub["Attribute"].astype(str).isin(list(LEGACY_TIER_ATTRS))]
    legacy_orders = set()
    if not legacy.empty:
        ok = None
        for attr, values in LEGACY_TIER_ATTRS.items():
            hit = set(legacy.loc[legacy["Attribute"].astype(str).eq(attr)
                                 & legacy["value"].astype(str).isin(list(values)), "Order Number"])
            ok = hit if ok is None else (ok & hit)
        legacy_orders = ok or set()
        consumed |= set(LEGACY_TIER_ATTRS)
    # 档位型属性（已选）→ 派生为「是否含某包」的配置项，而不是并列选项
    for attr, derived in TIER_DERIVED.items():
        g = cfg_sub[cfg_sub["Attribute"].eq(attr)]
        if g.empty and not legacy_orders:
            continue
        consumed.add(attr)
        codes = g.get("value_code", pd.Series(index=g.index, dtype="string"))
        for name, tiers in derived:
            hit = set(g.loc[codes.isin(tiers), "Order Number"])
            if LEGACY_TIER_TARGET in tiers:
                hit |= legacy_orders
            attributes.append({
                "attribute": name, "kind": "BIN", "raw_variants": {},
                "denominator_scope": "full",
                "orders_with_record": len(hit),
                "record_coverage": round(len(hit) / n, 4) if n else 0,
                "items": [{"value": YES, "count": len(hit),
                           "rate": round(len(hit) / n, 4) if n else 0},
                          {"value": NO, "count": n - len(hit),
                           "rate": round((n - len(hit)) / n, 4) if n else 0}],
                "derived_from": f"{attr} ⊆ {' ∪ '.join(tiers)}",
            })

    visible_names = [
        name for name in cfg_sub["Attribute"].unique()
        if not any(x and x in _norm(name) for x in ex_norms)
        and (name not in ATTR_APPLICABILITY or (gen, power_type) in ATTR_APPLICABILITY[name])
    ]
    axis = {}
    for key, grp in cfg_sub[cfg_sub["Attribute"].isin(visible_names)].groupby("_attribute_key"):
        names = Counter(grp["Attribute"].value_counts().to_dict())
        axis[key] = {"names": names, "orders_with_record": int(grp["Order Number"].nunique())}
        identity = attribute_identity(key, names)
        grp = grp[~grp["Attribute"].isin(consumed)]
        if grp.empty:
            continue
        with_value = int(grp["Order Number"].nunique())
        coverage = with_value / n if n else 0
        is_wheel = key == "code:WHEEL" or identity["attribute"] == "轮毂"
        raw_variants = {}
        # 属性编码只对齐属性。轮毂取值仍按尺寸归并，例如 SD-TI21 在不同代际对应不同显示名。
        if is_wheel:
            wheel = grp.drop_duplicates(["Order Number", "value"]).copy()
            raw_variants = wheel["value"].value_counts().to_dict()
            size = wheel["value"].astype(str).str.extract(r"(\d{2})英寸")[0]
            wheel["_display"] = size.map(lambda x: f"{x}英寸" if pd.notna(x) else "")
            vc = (wheel.groupby("Order Number")["_display"]
                  .agg(lambda x: " / ".join(v for v in dict.fromkeys(x) if v) or "未标注尺寸")
                  .value_counts())
            kind = "CHO"
        else:
            values = grp.drop_duplicates(["Order Number", "value"])
            vals = set(values["value"])
            kind = "BIN" if vals <= {YES, NO} else ("SOLO" if len(vals) == 1 else "CHO")
            if kind == "BIN":
                vc = values["value"].value_counts()
            else:
                multiple = values["Order Number"].duplicated(keep=False)
                vc = values.loc[~multiple, "value"].value_counts()
                if multiple.any():
                    combined = (values.loc[multiple].groupby("Order Number")["value"]
                                .agg(lambda v: YES if YES in set(v) else " / ".join(sorted(v))))
                    vc = pd.concat([vc, combined.value_counts()]).groupby(level=0).sum().sort_values(
                        ascending=False
                    )
        items = []
        if kind == "BIN":
            # 无记录 = 未选：显式「是」按记录数，其余全部计入「否」（含无记录订单）
            yes = int(vc.get(YES, 0))
            items = [{"value": YES, "count": yes, "rate": round(yes / n, 4) if n else 0},
                     {"value": NO, "count": n - yes,
                      "rate": round((n - yes) / n, 4) if n else 0}]
        else:
            top = vc.iloc[:MAX_CHO_VALUES]
            items = [{"value": str(v), "count": int(c),
                      "rate": round(int(c) / n, 4) if n else 0} for v, c in top.items()]
            rest = int(vc.iloc[MAX_CHO_VALUES:].sum())
            if rest:
                items.append({"value": f"其它（{len(vc) - MAX_CHO_VALUES} 项合计）",
                              "count": rest, "rate": round(rest / n, 4) if n else 0})
        attributes.append({
            **identity, "_key": key, "kind": kind,
            "raw_variants": raw_variants,
            "denominator_scope": "full",
            "orders_with_record": with_value,
            "record_coverage": round(coverage, 4),
            "items": items,
        })

    # 排序：有「是」比例的先按该比例降序（体现拥有率高低），其余按覆盖率
    def _sort_key(a: dict):
        if a["kind"] == "BIN":
            yes = next((i["rate"] for i in a["items"] if i["value"] == YES), 0)
            return (0, -yes, a["attribute"])
        return (1, -a["record_coverage"], a["attribute"])
    attributes.sort(key=_sort_key)
    return {
        "label": label, "gen": gen, "bev_only": bev_only, "n": n,
        "launch": launch.date().isoformat(), "as_of": as_of.date().isoformat(),
        "attributes_excluded": exclude,
        "attributes": attributes,
        "n_attributes": len(attributes),
        "_attribute_axis": axis,
    }


# 跨车型取值比较限轮毂尺寸及冰箱是否选装；旧表使用对应名称。
# OP-LASER 在不同代际对应不同档位（含 LS8 选装包），只对齐属性。
COMPARABLE_ATTRS: frozenset[str] = frozenset({
    "code:WHEEL", "code:OP-FRIDGE", "name:轮毂", "name:冰箱", "name:智能冷暖双用冰箱",
})


def compare_cells(cells: list[dict]) -> list[dict]:
    """在全量锁单口径下比较语义已对齐的取值。"""
    attr_map: dict[str, dict[str, dict]] = {}
    for c in cells:
        for a in c["attributes"]:
            key = a.get("_key", f"name:{a['attribute']}")
            attr_map.setdefault(key, {})[c["label"]] = a
    rows = []
    for key, per_cell in attr_map.items():
        if key not in COMPARABLE_ATTRS or len(per_cell) < 2:
            continue
        identity = next(iter(per_cell.values()))
        values: dict[str, dict[str, float]] = {}
        for label, a in per_cell.items():
            if a["denominator_scope"] != "full":
                continue
            if key not in {"code:WHEEL", "name:轮毂"} and a["kind"] != "BIN":
                continue
            for it in a["items"]:
                values.setdefault(it["value"], {})[label] = it["rate"]
        for val, per_label in values.items():
            nonzero = [r for r in per_label.values() if r > 0]
            if len(nonzero) < 2:
                continue
            rows.append({
                "attribute": identity["attribute"],
                "attribute_code": identity.get("attribute_code"),
                "value": val,
                "cells_present": sorted(per_label),
                "denominator_scope": "full",
                "rates": {lb: per_label.get(lb) for lb in (c["label"] for c in cells)},
                "gap": round(max(nonzero) - min(nonzero), 4),
            })
    rows.sort(key=lambda r: (-r["gap"], r["attribute"], r["value"]))
    return rows


def align_attributes(cells: list[dict]) -> list[dict]:
    """用主车型的名称频次统一显示名，并输出每个属性的记录覆盖。"""
    names_by_key: dict[str, Counter] = {}
    orders_by_key: dict[str, dict] = {}
    for c in cells:
        for key, data in c["_attribute_axis"].items():
            names_by_key.setdefault(key, Counter()).update(data["names"])
            orders_by_key.setdefault(key, {})[c["label"]] = data["orders_with_record"]
    identities = {key: attribute_identity(key, names) for key, names in names_by_key.items()}
    for c in cells:
        for cell in [c, *c.get("children", [])]:
            for a in cell["attributes"]:
                key = a.get("_key")
                if key in identities:
                    a.update(identities[key])
    return [
        {**identities[key], "orders_by_cell": orders_by_key[key]}
        for key in sorted(identities, key=lambda k: (-len(orders_by_key[k]), identities[k]["attribute"], k))
    ]


def assign_seat(orders: pd.DataFrame | None, cfg: pd.DataFrame
                ) -> list[tuple[str, pd.DataFrame]] | None:
    """还原 LS8 订单的座位归属，返回 [(大五座, df), (大六座, df)]。

    LS8 的座位信息有两个来源，二者互斥、无冲突（已核验）：
      - 2026-11-06 之前：座位写在 product_name 里（…科技旗舰大五座 / …奢享大六座）
      - 2026-11-06 起：product_name 不再带座位，座位改由「座椅」属性记录
                      （旗舰大五座 / 奢享大六座）
    因此「座椅」是归属口径而非选装项，不参与选装比例统计。
    """
    if orders is None or orders.empty:
        return None
    s = orders.copy()
    s["_seat_name"] = s["product_name"].astype(str).str.extract(r"(大五座|大六座)")[0]
    ids = set(s["order_number"])
    seat = cfg[cfg["Order Number"].isin(ids) & cfg["Attribute"].isin(SEAT_ATTRS)]
    seat = seat[["Order Number", "value"]].rename(
        columns={"Order Number": "order_number", "value": "_seat_attr"})
    s = s.merge(seat, on="order_number", how="left")
    s["seat"] = s["_seat_name"].fillna(s["_seat_attr"].map(SEAT_ATTR_MAP))
    out = [(name, s[s["seat"].eq(name)].drop(columns=["_seat_name", "_seat_attr"], errors="ignore"))
           for name in ("大五座", "大六座") if s["seat"].eq(name).any()]
    return out or None


def apply_subfilter(s: pd.DataFrame, op: str, arg: str) -> pd.DataFrame:
    """子车型过滤：CONTAINS / NOT_CONTAINS（product_name）或 POWER（product_type_logic）。"""
    if op == "POWER":
        return s[s["power_type"].eq(arg)]
    name = s["product_name"].astype(str)
    hit = name.str.contains(arg, case=False, na=False)
    return s[hit if op == "CONTAINS" else ~hit]


def _make_cell(d: pd.DataFrame, cfg: pd.DataFrame, label: str, gen: str,
               bev_only: bool, exclude: list[str], as_of: pd.Timestamp,
               orders: pd.DataFrame | None = None, bd: dict | None = None,
               open_t: pd.Timestamp | None = None) -> dict:
    """构建一个统计单元。先做录入异常审计并剔除异常单，再统计（不再含异常）。

    gen_cover 基于「整个代际」而非本单元的订单集合：子车型（如 LS9 Hyper）只是代际的一个切片，
    若用切片自身算覆盖率，会把代的正常属性（如 97% 覆盖的拖挂系统）误判成稀有。
    """
    s = orders if orders is not None else select_orders(
        d, gen, bev_only, bd or load_business_definition(_BUSINESS_DEF), open_t)
    sub = cfg[cfg["Order Number"].isin(set(s["order_number"]))]
    audit = audit_mixed_templates(s, sub, label)
    bad = set(audit["excluded_order_numbers"])
    if bad:
        s = s[~s["order_number"].isin(bad)]
        sub = sub[~sub["Order Number"].isin(bad)]
    cell = build_cell(s, sub, label, gen, bev_only, exclude, as_of)
    audit.setdefault("n_total_before_exclusion", cell["n"] + len(bad))
    cell["audit"] = audit
    cell["_orders"] = s          # 供座位/子车型二次分组；渲染与导出时会剔除
    cell["_open_t"] = open_t if orders is None else None   # 子车型复用同一开放时刻
    return cell


def compute(cells_arg: list[tuple[str, str]] | None = None,
            exclude: list[str] | None = None,
            splits: list[str] | None = None,
            cells_only: bool = False) -> dict:
    """cells_only=True 时只算主车型（不展开子车型）。

    splits 指定要展开子车型的父级 token（如 LS9）；子车型挂在其父 cell 的 "children" 下。
    录入异常订单（见 audit_mixed_templates）一律剔除，不出现在任何统计里。
    """
    bd = load_business_definition(_BUSINESS_DEF)
    exclude = DEFAULT_EXCLUDE_NAMES if exclude is None else exclude
    cells_arg = cells_arg or DEFAULT_CELLS
    d = load_lock_universe(bd)
    as_of = pd.Timestamp(d["lock_time"].max()).normalize()
    cfg = pd.read_parquet(_CONFIG_DATA)
    cfg["Order Number"] = cfg["Order Number"].astype(str).str.strip()
    cfg = cfg.dropna(subset=["Attribute", "value"]).copy()
    cfg["_attribute_key"] = attribute_keys(cfg)

    out_cells = []
    for label, token in cells_arg:
        gen = resolve_token(bd, token)
        bev_only = "纯电" in label
        open_t = launch_open_time(d, bd, gen)
        cell = _make_cell(d, cfg, label, gen, bev_only, exclude, as_of,
                          bd=bd, open_t=open_t)
        want_split = (not cells_only) and splits and gen in splits
        if want_split:
            children = []
            # CM2 的父级本身只取纯电（CM2 纯电），拆分要覆盖整个代际（纯电+增程）；
            # 其余（LS9/DM2）直接在父级订单池上划分。
            pool = (select_orders(d, gen, False, bd, cell.get("_open_t"))
                    if bev_only and gen in ("CM2", "LS6") else cell["_orders"])
            # 剔除集合沿用父级审计结果（父级已按 product_name 分组判定过），
            # 子切片再判会把 Hyper 等特配产品自己的模板当成异常，造成父级 ≠ 子级之和。
            parent_bad = set(cell["audit"].get("excluded_order_numbers", []))
            pool = pool[~pool["order_number"].isin(parent_bad)]
            for sub_label, op, arg in SUBSERIES.get(gen, []):
                base = apply_subfilter(pool, op, arg)
                if base.empty:
                    continue
                ch = build_cell(base, cfg[cfg["Order Number"].isin(
                    set(base["order_number"]))], sub_label, gen, False, exclude, as_of)
                ch["audit"] = {"label": sub_label, "groups": [], "n_suspect": 0,
                               "excluded_order_numbers": [],
                               "inherited_from_parent": label}
                ch["split_of"] = label
                children.append(ch)
            if children:
                cell["children"] = children
        # LS8：按座位归属拆分（大五座 / 大六座）——座位是归属口径，不是选装项。
        # 座位子组基于父级已剔除异常的订单池划分，不再各自审计。
        if gen == "LS8" and not cells_only:
            seat_of = assign_seat(cell.get("_orders"), cfg)
            if seat_of:
                children = []
                for seat_name, seat_orders in seat_of:
                    ch = build_cell(seat_orders, cfg[cfg["Order Number"].isin(
                        set(seat_orders["order_number"]))], f"{label} · {seat_name}",
                        gen, bev_only, exclude, as_of)
                    ch["audit"] = {"label": ch["label"], "groups": [], "n_suspect": 0,
                                   "excluded_order_numbers": [],
                                   "inherited_from_parent": label}
                    ch["split_of"] = label
                    ch["seat"] = seat_name
                    children.append(ch)
                if children:
                    cell["children"] = children
        out_cells.append(cell)
    axis = align_attributes(out_cells)
    return {"cells": out_cells, "matrix": compare_cells(out_cells), "attribute_axis": axis,
            "as_of": as_of.date().isoformat(),
            "excluded": sum(len(c.get("audit", {}).get("excluded_order_numbers", []))
                            for c in out_cells)}


# ── 录入异常订单识别 ────────────────────────────────────────────────────
# 只保留经业务逐单核对确认为「真异常」的规则；其余一律保留在统计中。
# 判定原则：异常 = 该订单走了另一套配置录入模板，而不是消费者选择差异。
#
# 已确认剔除的真实案例：
#   1) 小F M0 的 70 单：同批订单带着主模板里不存在的「舒适包 / 顶探照灯 /
#      超远距高精度双激光雷达」，且这些属性全代际仅此 70-77 单出现；
#   2) CM3 的 2 张非标单：一张把「激光雷达」写成「超远距高精度激光雷达」，
#      另一张整单携带 ISC尾灯/副驾副屏/冰箱（全代际各仅 1 单）。
#
# 明确**不剔除**（曾误判、已纠正）：
#   - LS9 的 2 单（66 Ultra 带了 Hyper 才标配的拖挂/冰箱，属正常加装）；
#   - CM2 的个别单、LS8 奢享大六座缺二排屏、Hyper 多带冰箱拖挂——均为正常产品差异。
CORE_ATTRS = {"内饰", "外饰", "轮毂", "方向盘"}
# 「全代际几乎无人有的属性」阈值：某属性在本代际覆盖率低于此值，才可能是录错表
# 阈值取 1%：LS9 的「拖挂尾勾/车载冰箱/线控转向」在全代际各 3~4.3%（就是 Hyper 那 638 单
# 在用），不属于「全代际几乎无人有」，不能据此判为录入异常；CM3 那台三属性单的属性
# 覆盖率仅 0.011%，据此可以安全识别。
RARE_ATTR_MAX_COVERAGE = 0.01
# 小样本产品阈值：某产品订单数低于此值时，它自己不足以定义「主流模板」，
# 改用全代际主流模板作参照判定换名录入（如仅 1 单的 LS6 M3 76RWD 工程名单）。
MIN_PRODUCT_ORDERS = 20


def audit_mixed_templates(s: pd.DataFrame, sub: pd.DataFrame, label: str) -> dict:
    """识别「配置录入链路异常」订单，返回需要剔除的订单号。

    规则（按 product_name 分组，避免把特配产品的正常差异当异常）：
      A. 同产品内，某单缺了该产品主流属性集合中的属性、同时多出该产品稀有属性 → 换名录入
      B. 同产品内，主流属性不缺，但整单额外携带 ≥2 个「本代际几乎无人有」的属性
         → 遗留配置项（历史遗留/已废弃字段，如 LS8 全库无一单选「是」的「顶探照灯」）
    """
    empty = {"label": label, "groups": [], "n_suspect": 0, "excluded_order_numbers": []}
    if sub.empty:
        return empty
    n_orders = sub["Order Number"].nunique()
    per_order = sub.groupby("Order Number").agg(attrs=("Attribute", lambda x: frozenset(x)))
    order_prod = s.set_index("order_number")["product_name"].astype(str)
    po = per_order.join(order_prod.rename("product"))
    gen_cover = (sub.groupby("Attribute")["Order Number"].nunique() / n_orders).to_dict()
    # 全代际主流模板（由全代际最常见的属性集合定义），供小样本产品判换名用
    main_set = per_order["attrs"].value_counts().idxmax()

    groups: dict[tuple, list[str]] = {}
    for prod, idx in po.groupby("product").groups.items():
        sub_po = po.loc[idx, "attrs"]
        if sub_po.map(len).eq(0).all():
            continue
        # 小样本产品（如仅 1 单的工程名单）无法用自身定义模板，改用「全代际主流模板」
        # 作参照；这类单往往携带一个换名的稀有属性（如把「激光雷达」写成「超远距高精度激光雷达」）
        if len(sub_po) < MIN_PRODUCT_ORDERS:
            for oid, attrs in sub_po.items():
                renamed = {a for a in attrs - main_set
                           if gen_cover.get(str(a), 1.0) < RARE_ATTR_MAX_COVERAGE}
                if renamed and (main_set - attrs):
                    groups.setdefault((prod, tuple(sorted(renamed)),
                                       tuple(sorted(main_set - attrs))), []).append(str(oid))
            continue
        p_main = sub_po.value_counts().idxmax()
        p_all = sub[sub["Order Number"].isin(list(idx))]
        p_cover = (p_all.groupby("Attribute")["Order Number"].nunique() / len(sub_po)).to_dict()
        for oid, attrs in sub_po.items():
            missing = p_main - attrs
            extra = attrs - p_main
            if not extra:
                continue
            # A: 换名录入
            if missing and all(p_cover.get(str(a), 1.0) < RARE_ATTR_MAX_COVERAGE for a in extra):
                if not _is_synonym_only(extra, attrs):
                    groups.setdefault((prod, tuple(sorted(extra)), tuple(sorted(missing))),
                                      []).append(str(oid))
                    continue
            # B: 遗留配置项。要求「成组的稀有属性」，且这些属性不构成消费者对超配版本标配的加装。
            #    反例（不剔除）：LS9 66 Ultra 的 2 单同时带了拖挂尾勾+车载冰箱+线控转向——
            #    这正是 Hyper 的标配组合，属用户加装，且这些属性名在全代际各有 3~4.3% 覆盖
            #    （即 Hyper 那 638 单在用），不是「全代际几乎无人有」。
            rare = {a for a in extra
                    if gen_cover.get(str(a), 1.0) < RARE_ATTR_MAX_COVERAGE
                    and str(a) not in CORE_ATTRS
                    and str(a) not in LEGACY_TIER_ATTRS}
            if len(rare) >= 2:
                groups.setdefault((prod, tuple(sorted(rare)), ()), []).append(str(oid))

    out = []
    for (prod, extra, missing), orders in groups.items():
        o = s[s["order_number"].isin(orders)]
        if missing:
            reason = (f"属性被换名录入（{prod}：缺 {'/'.join(missing)}、"
                      f"多出 {'/'.join(extra)}）")
        else:
            reason = (f"跨代际配置串入（{prod}：整单携带 {'/'.join(extra)}，"
                      f"这些属性在本代际几乎无人有）")
        out.append({
            "label": label, "n_orders": len(orders), "reason": reason,
            "extra_attributes": list(extra), "missing_attributes": list(missing),
            "sample_orders": orders[:3], "_all": orders,
            "share": round(len(orders) / len(s), 4) if len(s) else 0,
            "lock_range": [str(o["lock_time"].min())[:10],
                           str(o["lock_time"].max())[:10]] if len(o) else [],
        })
    out.sort(key=lambda g: -g["n_orders"])
    excluded = sorted({o for g in out for o in g["_all"]})
    for g in out:
        g.pop("_all", None)
    return {"label": label, "groups": out, "n_suspect": len(excluded),
            "excluded_order_numbers": excluded}


def _sibling_attrs(po: pd.DataFrame, prod: str, attrs: frozenset) -> set[str]:
    """同一代际内其他产品普遍具备的属性集合（用于识别「加装其他版本的标配」）。"""
    out: set[str] = set()
    for p_name, idx in po.groupby("product").groups.items():
        if p_name == prod:
            continue
        sub_po = po.loc[idx, "attrs"]
        common = set(sub_po.value_counts().idxmax())
        out |= common
    return out


def _is_synonym_only(extra: set[str], against: set[str]) -> bool:
    """extra 中每个属性都能在 against 找到同义项 → 同义并存，不算录入异常。"""
    return bool(extra) and all(
        any(other in against for name, aliases in SYNONYM_GROUPS.items()
            if str(a) in aliases for other in aliases) for a in extra)


def _fmt_pct(v) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def render_terminal(rc: dict) -> str:
    lines = ["[Summary]"]
    for c in rc["cells"]:
        n_seat = ""
        lines.append(f"  {c['label']}: {c['n']:,} 单" + (
            f"（剔除异常 {c['audit']['n_suspect']}）" if c["audit"].get("n_suspect") else ""))
        for ch in c.get("children") or []:
            lines.append(f"      ↪ {ch['label']}: {ch['n']:,} 单")
    lines.append("  口径：无记录=未选（分母=该组全部用户车锁单）；属性按编码归并；"
                 "排除 " + "/".join(rc["cells"][0]["attributes_excluded"]))
    axis = rc["attribute_axis"]
    lines.append(f"  属性维度 {len(axis)} 项，其中 {sum(len(a['orders_by_cell']) == 1 for a in axis)} 项仅一组有记录")
    for c in rc["cells"]:
        for cell in [c] + (c.get("children") or []):
            lines.append(f"\n## {cell['label']}   n={cell['n']:,}")
            for a in cell["attributes"]:
                vals = ", ".join(f"{i['value']} {i['rate'] * 100:.2f}%" for i in a["items"][:4])
                lines.append(f"  {a['attribute']:<24} {vals}")
    return "\n".join(lines)


def render_html(rc: dict, out_path: Path) -> None:
    cells = rc["cells"]
    e = lambda x: str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def attribute_notes(a):
        notes = []
        if a.get("note"):
            notes.append(a["note"])
        return "".join(f"<div class='mini'>{e(note)}</div>" for note in notes)

    def code_cell(a):
        """编码列：同义合并明细收敛到 title 提示，避免逐行堆叠小字。"""
        code = a.get("attribute_code") or "—"
        merged = a.get("merged_from")
        if not merged:
            return f"<td>{e(code)}</td>"
        detail = "同义合并：" + " ∪ ".join(merged)
        return f"<td title='{e(detail)}'>{e(code)} ∪{len(merged) - 1}</td>"

    def table(cell: dict, level: int = 0) -> list[str]:
        cls = " class='sub'" if level else ""
        out = [f"<table{cls}><tr><th>配置项</th><th>取值</th><th class='num'>单数</th>"
               "<th class='num'>占该组</th><th>分布</th></tr>"]
        for a in cell["attributes"]:
            items = a["items"]
            note = attribute_notes(a)
            if a.get("derived_from"):
                note += f"<div class='mini'>档位派生：{e(a['derived_from'])}</div>"
                if "Stand" in a["derived_from"]:
                    note += ("<div class='mini'>Stand 档的取值名本身叫「超远距高精度激光雷达」，"
                             "对应「已选」属性的标配方案。</div>")
            elif a["record_coverage"] < 0.999 and a["attribute"] != "轮毂":
                note += f"<div class='mini'>有记录 {a['record_coverage'] * 100:.1f}%，其余按未选计</div>"
            for i, it in enumerate(items):
                first = i == 0
                out.append("<tr>"
                           + (f"<td rowspan={len(items)}>{e(a['attribute'])}{note}</td>" if first else "")
                           + f"<td>{e(it['value'])}</td><td class='num'>{it['count']:,}</td>"
                           f"<td class='num'>{it['rate'] * 100:.2f}%</td>"
                           f"<td><span class='bar' style='width:{max(1, round(it['rate'] * 140))}px'></span></td></tr>")
        out.append("</table>")
        return out

    css = """
    body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#F7F9FB;color:#1F2933}
    .wrap{max-width:1180px;margin:0 auto;padding:32px 24px 64px}
    h1{font-size:25px;margin:0 0 6px} .sub2{color:#66727E;font-size:13px;margin-bottom:22px}
    .kpis{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px}
    .kpi{background:#fff;border-radius:10px;padding:13px 17px;flex:1 1 140px;box-shadow:0 1px 3px rgba(16,24,40,.08)}
    .kpi .l{font-size:12px;color:#66727E} .kpi .v{font-size:21px;font-weight:600;margin-top:3px}
    .kpi .h{font-size:11px;color:#8A94A0;margin-top:2px}
    table{border-collapse:collapse;width:100%;background:#fff;border-radius:10px;overflow:hidden;
      box-shadow:0 1px 3px rgba(16,24,40,.08);font-size:13px;margin-bottom:22px}
    th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #EEF1F4}
    th{background:#F0F4F8;font-weight:600}
    td.num{text-align:right;font-variant-numeric:tabular-nums}
    .bar{display:inline-block;height:8px;background:#4F6F82;border-radius:4px}
    h2{font-size:18px;margin:30px 0 8px}
    h3{font-size:15px;margin:18px 0 6px;color:#2F5D73}
    table.sub{border-left:3px solid #C9D6DF;margin-left:10px;width:calc(100% - 10px)}
    .mini{font-size:11px;color:#8A94A0;font-weight:400}
    .legend{background:#FFF;border:1px solid #E4E9EE;border-radius:10px;padding:14px 18px;
      margin-bottom:24px;font-size:13px;line-height:1.85}
    .legend code{background:#F0F4F8;padding:1px 5px;border-radius:3px;font-size:12px}
    .warn{background:#FDF6E7;border-left:3px solid #D79A2B;padding:8px 12px;border-radius:0 6px 6px 0;
      font-size:12px;color:#6B5322;margin-bottom:20px}
    """

    parts = ["<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
             f"<title>5 车型配置选装比例对比</title><style>{css}</style></head><body><div class='wrap'>",
             "<h1>5 车型 · 用户车锁单配置选装比例</h1>",
             f"<div class='sub2'>数据截至 {e(rc['as_of'])} ｜ 分母 = 该组全部用户车锁单 ｜ "
             f"排除 {'/'.join(cells[0]['attributes_excluded'])} ｜ "
             "数据源 dataset/order_data.parquet + dataset/config_attribute.parquet</div>",
             "<div class='kpis'>"]
    for c in cells:
        parts.append(f"<div class='kpi'><div class='l'>{e(c['label'])}</div>"
                     f"<div class='v'>{c['n']:,}</div>"
                     f"<div class='h'>上市 {e(c['launch'])}</div></div>")
    parts.append("</div>")

    parts.append("<div class='legend'><b>口径说明</b><br>"
                 "① <b>无记录 = 未选</b>：分母统一用该组全部用户车锁单。像「全线控转向系统」"
                 "只对选了它的订单落行，无记录的订单视为没选，而不是从分母剔除。<br>"
                 "①' <b>上市至今</b>：锁单时刻早于上市开放时刻（上市当天首个真实锁单，"
                 "与上市监控同口径）的订单不计入；已剔除测试单（总部主理店 + 假身份号 / 占位号）。<br>"
                 "② <b>按属性编码归并</b>：同一编码用主车型样本中最常见的中文名展示，"
                 "任一记录为「是」的订单计一次。表内以「∪」标注被合并的同义名。<br>"
                 "③ <b>轮毂按尺寸档位</b>（19/20/21/22 英寸）归并后再比：同一 value_code 在不同代际"
                 "对应不同中文名（如 <code>SD-TI21</code> 在大F M0 是「21″星耀超多辐」、"
                 "CM3/CM2 是「21″都市出行闪耀」），尺寸是唯一稳定的可比维度。<br>"
                 "④ <b>档位型属性按派生口径</b>：LS8 的「已选」是**三选一的选装方案**"
                 "（<code>Stand</code> / <code>Pro</code> / <code>Plus</code>，每单仅一个），"
                 "不是可叠加的并列选项，因此不直接展示档位分布，而是派生为「是否含某个包」：<br>"
                 "&nbsp;&nbsp;奢华智选包 = <code>Pro ∪ Plus</code>（Plus 档同样含智选包，漏掉会低估）；"
                 "一体式超广域探射灯 = <code>Plus</code>；"
                 "不购买智选包 = <code>Stand</code>。<br>"
                 "&nbsp;&nbsp;<b>旧版档位字段</b>：LS8 早期订单同时出现 <code>舒适包=是</code>、"
                 "<code>超远距高精度双激光雷达=标准</code>、<code>顶探照灯=否</code> 时，"
                 "按 Pro 档计入统计。<br>"
                 "⑤ <b>配置项按适用范围呈现</b>：某些配置只对特定动力类型可用。"
                 "例如 CM2 的 <code>5C 超快充电池</code> 仅在纯电组统计。<br>"
                 "⑥ <b>录入异常订单已剔除</b>（见页面底部），不计入任何比例。<br>"
                 "⑦ 表内「占该组」= 该取值单数 ÷ 该组全部用户车锁单数。"
                 "</div>")

    axis = rc["attribute_axis"]
    single = sum(len(a["orders_by_cell"]) == 1 for a in axis)
    parts.append(f"<h2>配置属性覆盖</h2><p class='mini'>{len(axis)} 项属性，{single} 项仅一组有记录。"
                 "表中为记录订单数，选装比例见各车型明细。</p>")
    parts.append("<table><tr><th>属性</th><th>编码</th>"
                 + "".join(f"<th class='num'>{e(c['label'])}</th>" for c in cells) + "</tr>")
    for a in axis:
        parts.append(f"<tr><td>{e(a['attribute'])}{attribute_notes(a)}</td>"
                     + code_cell(a)
                     + "".join(f"<td class='num'>{a['orders_by_cell'].get(c['label'], 0):,}</td>" for c in cells)
                     + "</tr>")
    parts.append("</table>")

    for c in cells:
        parts.append(f"<h2>{e(c['label'])}（{e(c['gen'])}）· {c['n']:,} 单</h2>")
        if c["audit"].get("n_suspect"):
            total = c["audit"].get("n_total_before_exclusion", c["n"] + c["audit"]["n_suspect"])
            k = c["audit"]["n_suspect"]
            parts.append(
                f"<div class='warn'>已剔除 <b>{k}</b> 单"
                f"（占原始 {total:,} 单的 {k / total * 100:.2f}%），不计入下表："
                + "；".join(e(g["reason"]) for g in c["audit"]["groups"]) + "</div>")
        parts.extend(table(c))
        for ch in c.get("children") or []:
            parts.append(f"<h3>↪ {e(ch['label'])} · {ch['n']:,} 单</h3>")
            parts.extend(table(ch, level=1))

    parts.append("<h2>已剔除的订单及原因</h2>")
    parts.append("<div class='legend'>按原始配置录入模板审计，保留正常加装和产品差异。</div>")
    parts.append("<table><tr><th>车型</th><th class='num'>剔除</th><th>原因</th><th>样例订单</th></tr>")
    any_bad = False
    for c in cells:
        for cell in [c] + (c.get("children") or []):
            au = cell.get("audit") or {}
            if not au.get("n_suspect"):
                continue
            any_bad = True
            for g in au["groups"]:
                parts.append(f"<tr><td>{e(cell['label'])}</td><td class='num'>{g['n_orders']}</td>"
                             f"<td>{e(g['reason'])}</td>"
                             f"<td><code>{e(', '.join(g['sample_orders'][:2]))}</code></td></tr>")
    if not any_bad:
        parts.append("<tr><td colspan=4>无</td></tr>")
    parts.append("</table></div></body></html>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(parts), encoding="utf-8")
    print(f"  HTML: {out_path.resolve()}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="5 车型用户车锁单配置选装比例对比")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    p.add_argument("--output", default=str(_DEFAULT_OUT), help="CSV/JSON 输出目录")
    p.add_argument("--html", action="store_true", help="输出品牌化 HTML 报告")
    p.add_argument("--exclude-names", default=",".join(DEFAULT_EXCLUDE_NAMES),
                   help="排除的属性名（逗号分隔，按包含匹配），默认 内饰,外饰,方向盘")
    p.add_argument("--splits", default=",".join(DEFAULT_SPLITS),
                   help="要展开系列内拆分的代际（逗号分隔），默认 LS9,DM2,CM2；传空串关闭拆分")
    args = p.parse_args(argv)
    exclude = [x.strip() for x in args.exclude_names.split(",") if x.strip()]
    splits = [x.strip() for x in args.splits.split(",") if x.strip()]
    rc = compute(exclude=exclude, splits=splits)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    def _rows_for(c: dict, parent: str | None = None) -> list[dict]:
        rows = []
        for a in c["attributes"]:
            for it in a["items"]:
                rows.append({"cell": c["label"], "parent": parent or "", "gen": c["gen"],
                             "n_lock": c["n"], "attribute": a["attribute"],
                             "attribute_code": a.get("attribute_code"), "kind": a["kind"],
                             "denominator_scope": a["denominator_scope"],
                             "orders_with_record": a["orders_with_record"],
                             "record_coverage": a["record_coverage"],
                             "value": it["value"], "count": it["count"], "rate": it["rate"]})
        return rows

    rows = []
    for c in rc["cells"]:
        rows.extend(_rows_for(c))
        for ch in c.get("children") or []:
            rows.extend(_rows_for(ch, parent=c["label"]))
    detail_csv = out / "lock_config_option_compare_detail.csv"
    pd.DataFrame(rows).to_csv(detail_csv, index=False, encoding="utf-8-sig")

    mrows = []
    for r in rc["matrix"]:
        for lb in [c["label"] for c in rc["cells"]]:
            mrows.append({"attribute": r["attribute"], "attribute_code": r["attribute_code"],
                          "value": r["value"], "cell": lb,
                          "rate": r["rates"].get(lb), "gap": r["gap"]})
    matrix_csv = out / "lock_config_option_compare_matrix.csv"
    pd.DataFrame(mrows).to_csv(matrix_csv, index=False, encoding="utf-8-sig")

    if args.html:
        render_html(rc, _WS / "outputs" / "reports" / "lock_config_option_compare_5cars.html")

    if args.format == "json":
        def _clean(c: dict) -> dict:
            return {
                **{k: v for k, v in c.items() if not k.startswith("_")},
                "attributes": [{k: v for k, v in a.items() if not k.startswith("_")}
                               for a in c["attributes"]],
            }
        payload = {
            "as_of": rc["as_of"], "excluded": rc["excluded"],
            "cells": [{**_clean(c), "children": [_clean(ch) for ch in c.get("children") or []]}
                      for c in rc["cells"]],
            "matrix": rc["matrix"],
            "attribute_axis": rc["attribute_axis"],
        }
        (out / "lock_config_option_compare.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"已输出: {detail_csv}\n已输出: {matrix_csv}"
              f"\n已输出: {out / 'lock_config_option_compare.json'}")
        return 0

    print(render_terminal(rc))
    print(f"\n[Output]\n  {detail_csv}\n  {matrix_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
