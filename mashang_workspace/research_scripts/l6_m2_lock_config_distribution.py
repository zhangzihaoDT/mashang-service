#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DM2 上市以来零售锁单的配置分布报告

数据源：
  - dataset/order_data.parquet（锁单：DM2 series_group，上市日 time_periods.DM2.end 起）
  - dataset/config_attribute.parquet（选配：order_config_to_parquet.py 增量更新后含 DM2）

口径：
  - 锁单 = lock_time 落在上市窗口 [DM2.end, as-of) 的 DM2 订单（order_number 去重）
  - 默认零售口径 = order_type ∈ {用户车, NaN}；--include-test-drive 时含试驾车
  - 配置归属 = config_attribute.parquet 中 (Order Number) 匹配锁单且 value 非空的 Attribute/value
  - 核心配置 = 内饰 / 外饰 / 轮毂 / 方向盘 / 超远距高精度激光雷达（5 大核心属性，每单 1 值）
  - 分布 = 各 Attribute 下 value(显示名) 的计数与占锁单比例

用法：
  python research_scripts/l6_m2_lock_config_distribution.py
  python research_scripts/l6_m2_lock_config_distribution.py --include-test-drive
  python research_scripts/l6_m2_lock_config_distribution.py --format json --output outputs/tables/
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = REPO_ROOT / "mashang_workspace"
for p in (str(REPO_ROOT), str(_WS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from research_scripts.l6_m2_launch_lock_metrics_to_feishu import (  # noqa: E402
    _parse_logic,
    _rule_condition,
    apply_series_group_logic,
    load_business_definition,
)
from utils.result_contract import build_success_contract  # noqa: E402

_BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
_ORDER_DATA = REPO_ROOT / "dataset" / "order_data.parquet"
_CONFIG_DATA = REPO_ROOT / "dataset" / "config_attribute.parquet"
_DEFAULT_TABLE = _WS / "outputs" / "tables"
NON_RETAIL = {"试驾车", "大客户", "员工", "集团员工", "经销商员工", "享道", "仅批售", "项目", "展车", "海外"}
GEN = "DM2"
CORE_ATTRS = ["内饰", "外饰", "轮毂", "方向盘", "超远距高精度激光雷达"]


def _retail_mask(order_type: pd.Series) -> pd.Series:
    ot = order_type.fillna("").astype("string")
    return ot.isin(["", "用户车"]) & ~ot.isin(NON_RETAIL)


def load_order() -> tuple[pd.DataFrame, pd.Timestamp]:
    bd = load_business_definition(_BUSINESS_DEF)
    end = pd.Timestamp(bd["time_periods"][GEN]["end"]).normalize()
    asts = {g: _parse_logic(_rule_condition(c)) for g, c in bd["series_group_logic"].items()}
    df = pd.read_parquet(_ORDER_DATA)
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = apply_series_group_logic(df, bd, asts)
    return df, end


def compute_lock_config_distribution(
    as_of: pd.Timestamp | None = None,
    include_test_drive: bool = False,
) -> dict:
    """DM2 上市以来锁单配置分布（可复用；供 CLI 与 launch 报告模块 8 引用）。

    返回结构：
      - n / covered / core_complete / core_total_orders
      - attrs: 各 Attribute 值分布（选择型，量度 = count/share per 锁单）
      - option_attrs: 是/否型选装项（拥有率 = yes / n）
      - launch / hi: 窗口起止
    """
    df, launch = load_order()
    lo = launch
    max_lock = pd.to_datetime(df["lock_time"], errors="coerce").max()
    if as_of is None:
        as_of = pd.Timestamp(datetime.now().date()).normalize()
    hi = min(pd.Timestamp(as_of).normalize(), pd.Timestamp(max_lock).normalize())

    d2 = df[df["series_group_logic"].eq(GEN) & df["lock_time"].notna()
            & (df["lock_time"] >= lo) & (df["lock_time"] < hi)].copy()
    if not include_test_drive:
        d2 = d2[_retail_mask(d2["order_type"])]
    locks = d2.drop_duplicates(subset=["order_number"])
    lock_ids = set(locks["order_number"].astype(str).str.strip())
    n = len(lock_ids)

    cfg = pd.read_parquet(_CONFIG_DATA)
    cfg["Order Number"] = cfg["Order Number"].astype(str).str.strip()
    sub = cfg[cfg["Order Number"].isin(lock_ids) & cfg["value"].notna()].copy()
    covered = int(sub["Order Number"].nunique())

    # 核心 5 属性完整覆盖
    per_order_attrs = sub.groupby("Order Number")["Attribute"].apply(set).to_dict()
    core_complete = sum(1 for o in lock_ids
                        if len(set(CORE_ATTRS) & per_order_attrs.get(o, set())) == len(CORE_ATTRS))

    # 各 Attribute 值分布（value 去空后计数）
    attrs = []
    option_attrs = []
    core_total_orders = {a: int(sub[sub["Attribute"].eq(a)]["Order Number"].nunique())
                         for a in CORE_ATTRS}
    for attr, grp in sub.groupby("Attribute"):
        vc = grp["value"].value_counts()
        vset = {str(v) for v in vc.index}
        is_binary = vset <= {"是", "否"} and "是" in vset
        if is_binary:
            yes = int(vc.get("是", 0))
            items = [{"value": "是（选装）", "count": yes,
                      "share": round(yes / n, 4)},
                     {"value": "否 / 未选", "count": int(n - yes),
                      "share": round(1 - yes / n, 4)}]
            option_attrs.append({"attribute": attr,
                                 "orders_with_value": int(grp["Order Number"].nunique()),
                                 "yes_count": yes, "items": items})
        else:
            items = [{"value": str(v), "count": int(cnt),
                      "share": round(int(cnt) / n, 4)} for v, cnt in vc.items()]
            attrs.append({"attribute": attr,
                          "orders_with_value": int(grp["Order Number"].nunique()),
                          "items": items})
    attrs.sort(key=lambda a: CORE_ATTRS.index(a["attribute"])
               if a["attribute"] in CORE_ATTRS else len(CORE_ATTRS) + 1)

    return {
        "gen": GEN,
        "launch": launch.date().isoformat(),
        "hi": hi.date().isoformat(),
        "include_test_drive": include_test_drive,
        "n": n, "covered": covered, "core_complete": core_complete,
        "core_total_orders": core_total_orders,
        "attrs": attrs, "option_attrs": option_attrs,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DM2 上市以来零售锁单配置分布")
    p.add_argument("--as-of", type=str, default=None, help="锁单截止日 YYYY-MM-DD（默认含数据最新完整日）")
    p.add_argument("--include-test-drive", action="store_true",
                   help="含试驾车锁单（默认零售口径：用户车/NaN）")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    p.add_argument("--output", type=str, default=None, help="JSON 输出目录")
    args = p.parse_args(argv)

    rc = compute_lock_config_distribution(
        as_of=pd.Timestamp(args.as_of) if args.as_of else None,
        include_test_drive=args.include_test_drive,
    )
    n, covered, core_complete = rc["n"], rc["covered"], rc["core_complete"]
    launch = pd.Timestamp(rc["launch"])
    hi = pd.Timestamp(rc["hi"])
    if n == 0:
        print("无 DM2 锁单（检查数据与窗口）")
        return 1

    attrs = rc["attrs"]
    option_attrs = rc["option_attrs"]
    core_total_orders = rc["core_total_orders"]

    scope = {
        "data_source": "dataset/order_data.parquet + dataset/config_attribute.parquet",
        "time_window": {"type": "since_launch", "series": GEN,
                        "start": launch.date().isoformat(), "end": hi.date().isoformat()},
        "filters": {"order_type": "用户车/NaN（零售）" if not args.include_test_drive
                    else "含试驾车（全口径）",
                    "metric_definition": "配置分布 = config_attribute 中锁单订单的 Attribute/value 显示名分布；核心 5 属性 = 内饰/外饰/轮毂/方向盘/超远距高精度激光雷达；是/否型选装项按「是」占锁单比例计拥有率"},
    }
    result = {
        "summary": f"{GEN} 上市以来锁单 {n} 单（{launch.date()} 起，至 {hi.date()}），"
                   f"配置可关联 {covered} 单；核心 5 配置完整 {core_complete} 单。",
        "metrics": {"lock_orders": n, "config_covered_orders": covered,
                    "core_complete_orders": core_complete,
                    "core_orders_with_value": core_total_orders,
                    "option_attrs": {a["attribute"]: a["yes_count"] for a in option_attrs}},
        "dimensions": [
            {"name": "attribute", "label": "配置属性",
             "items": [{"value": a["attribute"],
                        "metrics": {"orders_with_value": a["orders_with_value"]}} for a in attrs]}
        ],
        "tables": [
            {"name": f"{GEN}_lock_core_config_distribution",
             "columns": ["attribute", "value", "count", "share"],
             "rows": [{"attribute": a["attribute"], "value": it["value"],
                       "count": it["count"], "share": it["share"]}
                      for a in attrs for it in a["items"]]},
            {"name": f"{GEN}_lock_option_ownership",
             "columns": ["attribute", "yes_count", "total", "ownership"],
             "rows": [{"attribute": a["attribute"], "yes_count": a["yes_count"],
                       "total": n, "ownership": round(a["yes_count"] / n, 4)}
                      for a in option_attrs]},
        ],
    }
    contract = build_success_contract(
        script="research_scripts/l6_m2_lock_config_distribution.py",
        command="python research_scripts/l6_m2_lock_config_distribution.py" +
                (" --include-test-drive" if args.include_test_drive else "") +
                (" --format json" if args.format == "json" else ""),
        scope=scope, result=result,
    )

    if args.format == "json":
        out_dir = Path(args.output) if args.output else _DEFAULT_TABLE
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{GEN}_lock_config_distribution.json"
        out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已输出: {out}")
        return 0

    # terminal
    print(f"[Summary]")
    print(f"  {GEN} 上市以来锁单 {n} 单；配置可关联 {covered} 单；核心 5 配置完整 {core_complete} 单。")
    print()
    for a in attrs:
        tag = "核心" if a["attribute"] in CORE_ATTRS else ""
        print(f"[{a['attribute']}{(' · ' + tag) if tag else ''}] 关联 {a['orders_with_value']}/{n} 单")
        for it in a["items"]:
            bar = "#" * int(round(it["share"] * 60))
            print(f"  {str(it['value'])[:28]:<30} {it['count']:>4} ({it['share'] * 100:>5.1f}%) {bar}")
        print()
    if option_attrs:
        print("[选装项拥有率 · 是/锁单]")
        for a in option_attrs:
            own = a["yes_count"] / n if n else 0
            bar = "#" * int(round(own * 60))
            print(f"  {a['attribute']:<28} 是={a['yes_count']:>4} 单 ({own * 100:>5.1f}%) {bar}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
