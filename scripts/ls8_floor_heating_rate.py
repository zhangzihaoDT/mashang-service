#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
LS8 地暖选装率分析脚本
统计 LS8 锁单订单中，5座/6座车型的地暖选装率。

数据源:
  - order_data.parquet: 订单主表 (含 series, product_name, lock_time)
  - config_attribute.parquet: 选配明细表 (含 Attribute, value)
  - business_definition.json: 业务规则 (seat_count_logic)

逻辑:
   1. 从 order_data 中筛选 series=LS8 且已锁单 (lock_time 非空) 的订单
   2. 根据 product_name 按 seat_count_logic 推断 5座/6座
   3. 从 config_attribute 中匹配这些订单在 Attribute="地暖" 的 value
   4. 汇总选装率 = 选装地暖的锁单数 / 总锁单数

时间窗口: 默认"上市以来" (LS8 上市日 2026-03-26 至今)
"""

import pandas as pd
from pathlib import Path
import json
from datetime import date

REPO_ROOT = Path(__file__).resolve().parents[1]

ORDER_DATA = REPO_ROOT / "dataset" / "order_data.parquet"
CONFIG_ATTR = REPO_ROOT / "dataset" / "config_attribute.parquet"
BUSINESS_DEF = REPO_ROOT / "schema" / "business_definition.json"


def load_business_definition() -> dict:
    with open(BUSINESS_DEF, "r", encoding="utf-8") as f:
        return json.load(f)


def _like_to_pattern(like_expr: str) -> str:
    pattern = like_expr.strip().strip("'\"")
    pattern = pattern.replace("%", "")
    return pattern


def infer_seat(product_name: str, seat_logic: dict) -> str:
    for seat_label, rule in seat_logic.items():
        condition = rule.strip()
        if condition.startswith("product_name LIKE "):
            raw = condition[len("product_name LIKE "):].strip()
            pat = _like_to_pattern(raw)
            if pat and pat in str(product_name):
                return seat_label
    return "未知"


def main():
    bd = load_business_definition()
    seat_logic = bd.get("seat_count_logic", {})
    time_periods = bd.get("time_periods", {})
    ls8_period = time_periods.get("LS8", {})
    launch_date = ls8_period.get("start", "2026-03-26")
    today = date.today().isoformat()
    print(f"时间窗口: {launch_date} ~ {today} (上市以来)")

    print("读取 order_data...")
    odf = pd.read_parquet(ORDER_DATA)

    ls8_locked = odf[
        (odf["series"] == "LS8")
        & (odf["lock_time"].notna())
        & (odf["lock_time"] >= launch_date)
        & (odf["order_type"] == "用户车")
    ].copy()
    total_locked = len(ls8_locked)
    print(f"LS8 锁单订单总数: {total_locked}")

    ls8_locked["seat"] = ls8_locked["product_name"].apply(
        lambda x: infer_seat(str(x), seat_logic)
    )

    seat_distribution = ls8_locked["seat"].value_counts()
    print("\n座位分布:")
    for seat, count in seat_distribution.items():
        print(f"  {seat}: {count} ({count/total_locked*100:.1f}%)")

    locked_order_numbers = ls8_locked["order_number"].unique().tolist()
    print(f"\n读取 config_attribute (共 {len(locked_order_numbers)} 个订单号匹配)...")
    cdf = pd.read_parquet(CONFIG_ATTR)

    matching_records = cdf[
        cdf["Order Number"].isin(locked_order_numbers)
        & cdf["Attribute"].str.contains("地暖", na=False)
    ].copy()

    print(f"匹配到地暖选配记录: {len(matching_records)} 条")
    print(f"地暖 value 分布:\n{matching_records['value'].value_counts().to_string()}")

    orders_with_floor_heating = matching_records[
        matching_records["value"] == "是"
    ]["Order Number"].unique()

    ls8_locked["has_floor_heating"] = ls8_locked["order_number"].isin(
        orders_with_floor_heating
    )

    print("\n" + "=" * 50)
    print("LS8 地暖选装率汇总")
    print("=" * 50)
    print(f"{'座位':>6} | {'选装地暖':>8} | {'锁单总数':>8} | {'选装率':>8}")
    print("-" * 42)

    for seat in ["五座", "六座", "未知"]:
        subset = ls8_locked[ls8_locked["seat"] == seat]
        total = len(subset)
        if total == 0:
            continue
        selected = subset["has_floor_heating"].sum()
        rate = selected / total * 100
        print(f"{seat:>6} | {int(selected):>8} | {total:>8} | {rate:>7.1f}%")

    total_selected = ls8_locked["has_floor_heating"].sum()
    total_rate = total_selected / total_locked * 100
    print("-" * 42)
    print(f"{'合计':>6} | {int(total_selected):>8} | {total_locked:>8} | {total_rate:>7.1f}%")


if __name__ == "__main__":
    main()
