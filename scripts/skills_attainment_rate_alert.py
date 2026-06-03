#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
description: "⚠️ 达成率预警排查工作流"
运行方式
1. 默认输出近 10 日（结束日期默认昨天）：python3 scripts/skills_attainment_rate_alert.py
2. 可选：指定窗口天数与结束日期：python3 scripts/skills_attainment_rate_alert.py --days 10 --end 2026-05-25
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from operators.assign_conversion import run_assign_conversion_operator

PARQUET_FILE = REPO_ROOT / "dataset" / "order_data.parquet"
ASSIGN_CSV_FILE = REPO_ROOT / "dataset" / "assign_data.csv"


def _parse_args() -> tuple[date, int]:
    parser = argparse.ArgumentParser(description="⚠️ 达成率预警排查工作流（近 N 日）")
    parser.add_argument("--days", type=int, default=10, help="统计窗口天数（默认 10）")
    parser.add_argument("--end", type=str, help="结束日期（YYYY-MM-DD，默认昨天）")
    args = parser.parse_args()

    if args.days <= 0:
        raise SystemExit("--days 必须为正整数")

    if args.end:
        try:
            end_day = datetime.strptime(args.end, "%Y-%m-%d").date()
        except ValueError:
            raise SystemExit("--end 日期格式错误，应为 YYYY-MM-DD")
    else:
        end_day = (datetime.now().date() - timedelta(days=1))

    return end_day, args.days


def _load_orders() -> pd.DataFrame:
    if not PARQUET_FILE.exists():
        raise SystemExit(f"未找到订单数据: {PARQUET_FILE}")
    df = pd.read_parquet(str(PARQUET_FILE))
    need = {"lock_time", "order_number", "series"}
    missing = sorted(need - set(df.columns))
    if missing:
        raise SystemExit(f"订单数据缺失列: {missing}")
    work = df.loc[:, ["lock_time", "order_number", "series"]].copy()
    work["lock_time"] = pd.to_datetime(work["lock_time"], errors="coerce").dt.date
    work = work[work["lock_time"].notna()]
    return work


def _lock_orders_last_n_days_by_series(end_day: date, days: int) -> pd.DataFrame:
    start_day = end_day - timedelta(days=days - 1)
    orders = _load_orders()
    window = orders[(orders["lock_time"] >= start_day) & (orders["lock_time"] <= end_day)]
    if window.empty:
        idx = pd.date_range(start_day, end_day, freq="D").date
        return pd.DataFrame(index=idx)

    g = (
        window.groupby(["lock_time", "series"])["order_number"]
        .nunique()
        .rename("lock_orders")
        .reset_index()
    )
    pivot = g.pivot_table(index="lock_time", columns="series", values="lock_orders", fill_value=0, aggfunc="sum")
    idx = pd.date_range(start_day, end_day, freq="D").date
    pivot = pivot.reindex(idx, fill_value=0)
    pivot["TOTAL"] = pivot.sum(axis=1)
    return pivot


def _load_assign() -> pd.DataFrame:
    if not ASSIGN_CSV_FILE.exists():
        raise SystemExit(f"未找到下发线索数据: {ASSIGN_CSV_FILE}")
    df = pd.read_csv(str(ASSIGN_CSV_FILE))
    if df.empty:
        raise SystemExit("下发线索数据为空")
    return df


def _assign_last_n_days(end_day: date, days: int) -> pd.DataFrame:
    start_day = end_day - timedelta(days=days - 1)
    end_exclusive = end_day + timedelta(days=1)

    result = run_assign_conversion_operator(
        _load_assign(),
        start=start_day.strftime("%Y-%m-%d"),
        end=end_exclusive.strftime("%Y-%m-%d"),
    )
    daily_rows = result.get("daily_rows") or []
    df = pd.DataFrame(daily_rows)
    if df.empty:
        idx = pd.date_range(start_day, end_day, freq="D").strftime("%Y-%m-%d")
        return pd.DataFrame({"date": idx})

    channel_cols = [
        "下发线索数 (门店)",
        "下发线索数（直播）",
        "下发线索数（平台)",
        "下发线索数（APP小程序)",
        "下发线索数（快慢闪)",
    ]
    need_cols = [
        "date",
        "下发线索数",
        *channel_cols,
        "门店线索占比",
        "下发 (门店)线索当日锁单率",
    ]
    for c in need_cols:
        if c not in df.columns:
            df[c] = None

    df = df.loc[:, need_cols].copy()
    idx = pd.date_range(start_day, end_day, freq="D").strftime("%Y-%m-%d")
    df = pd.DataFrame({"date": idx}).merge(df, on="date", how="left")
    df["下发线索数"] = pd.to_numeric(df["下发线索数"], errors="coerce").fillna(0).astype(int)
    for c in channel_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    return df


def main() -> None:
    end_day, days = _parse_args()
    start_day = end_day - timedelta(days=days - 1)

    print(f"⚠️ 达成率预警排查工作流")
    print(f"时间窗口: {start_day} ~ {end_day}（{days} 天）")
    print()

    lock_pivot = _lock_orders_last_n_days_by_series(end_day=end_day, days=days)
    print(f"1) 近 {days} 日分 series 的锁单数（按日）")
    if lock_pivot.empty:
        print("  无锁单数据")
    else:
        display = lock_pivot.copy()
        display.index = pd.Index([str(d) for d in display.index], name="date")
        print(display.to_string())
        totals = lock_pivot.drop(columns=["TOTAL"], errors="ignore").sum(axis=0).sort_values(ascending=False)
        print()
        print(f"  近 {days} 日累计（按 series）")
        print(totals.to_string())
    print()

    assign_df = _assign_last_n_days(end_day=end_day, days=days)

    channel_cols = [
        "下发线索数 (门店)",
        "下发线索数（快慢闪)",
        "下发线索数（APP小程序)",
        "下发线索数（平台)",
        "下发线索数（直播）",
    ]
    channel_alias = {
        "下发线索数 (门店)": "门店",
        "下发线索数（快慢闪)": "快慢闪",
        "下发线索数（APP小程序)": "APP小程序",
        "下发线索数（平台)": "平台",
        "下发线索数（直播）": "直播",
    }
    channel_df = assign_df[["date"]].copy()
    for c in channel_cols:
        channel_df[channel_alias[c]] = assign_df[c]
    channel_df["其他"] = assign_df["下发线索数"] - assign_df[channel_cols].sum(axis=1)
    channel_df["合计"] = assign_df["下发线索数"]

    print(f"2) 近 {days} 日的下发线索数（按渠道）")
    print(channel_df.to_string(index=False))
    print()
    channel_totals = channel_df.drop(columns=["date", "合计"]).sum().sort_values(ascending=False)
    print(f"  近 {days} 日累计（按渠道）")
    print(channel_totals.to_string())
    print()

    print(f"3) 近 {days} 日的下发线索（门店）的占比")
    print(assign_df.loc[:, ["date", "门店线索占比"]].to_string(index=False))
    print()

    print(f"4) 近 {days} 日的门店当日线索转化率")
    print(assign_df.loc[:, ["date", "下发 (门店)线索当日锁单率"]].to_string(index=False))


if __name__ == "__main__":
    main()
