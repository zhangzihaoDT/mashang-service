#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性重建 dataset/order_data.parquet 完整底座。
数据源：2023~2025 + 2026_0428 原始 CSV，合并后补充当前 parquet 的最新增量。
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

from dataset.updater.order_data_to_parquet import clean_column_names, convert_types

ORIGINAL_DIR = Path("/Users/zihao_/Documents/coding/dataset/original")
DATASET_DIR = REPO_ROOT / "dataset"
OUTPUT_FILE = DATASET_DIR / "order_data.parquet"
CURRENT_PARQUET = DATASET_DIR / "order_data.parquet"

SOURCE_FILES = [
    ("order_data_2023.csv", "2023"),
    ("order_data_2024.csv", "2024"),
    ("order_data_2025.csv", "2025"),
    ("order_data_2026_0428.csv", "2026"),
]


def read_and_clean(filename: str, label: str) -> pd.DataFrame:
    path = ORIGINAL_DIR / filename
    print(f"📖 {label}: {path.name} ({path.stat().st_size / 1024 / 1024:.0f}MB) ...")
    df = pd.read_csv(path, encoding="utf-16", sep="\t")
    print(f"   raw: {len(df)} rows")
    df = clean_column_names(df)
    df = convert_types(df)
    print(f"   cleaned: {len(df)} rows, lock_time range: {df['lock_time'].min()} ~ {df['lock_time'].max()}")
    return df


def main():
    # Step 1: load & clean all yearly CSVs
    chunks = []
    for fname, label in SOURCE_FILES:
        chunks.append(read_and_clean(fname, label))

    df_all = pd.concat(chunks, ignore_index=True, sort=False)
    print(f"\n📊 合并后总行数: {len(df_all)}")
    print(f"  lock_time: {df_all['lock_time'].min()} ~ {df_all['lock_time'].max()}")

    # Step 2: deduplicate by order_number
    before = len(df_all)
    df_all = df_all.drop_duplicates(subset=["order_number"], keep="last")
    removed = before - len(df_all)
    print(f"✂️ 去重(order_number): 移除 {removed} 行")

    # Step 3: merge in newer orders from current parquet (if exists)
    if CURRENT_PARQUET.exists():
        df_curr = pd.read_parquet(CURRENT_PARQUET)
        print(f"\n📖 当前 parquet: {len(df_curr)} rows")
        print(f"  lock_time: {df_curr['lock_time'].min()} ~ {df_curr['lock_time'].max()}")

        # Only keep orders not in the rebuilt base
        existing_orders = set(df_all["order_number"].dropna())
        df_newer = df_curr[~df_curr["order_number"].isin(existing_orders)].copy()
        print(f"  新增 {len(df_newer)} 条不在底座中的订单")

        # Align columns
        all_cols = list(dict.fromkeys(list(df_all.columns) + list(df_newer.columns)))
        for c in all_cols:
            if c not in df_all.columns:
                df_all[c] = pd.NA
            if c not in df_newer.columns:
                df_newer[c] = pd.NA
        df_all = df_all[all_cols]
        df_newer = df_newer[all_cols]

        df_all = pd.concat([df_all, df_newer], ignore_index=True)
        print(f"  合并后总行数: {len(df_all)}")

    # Step 4: final dedup
    before = len(df_all)
    df_all = df_all.drop_duplicates(subset=["order_number"], keep="last")
    print(f"✂️ 最终去重: 移除 {before - len(df_all)} 行")

    # Step 5: write
    print(f"\n💾 写入: {OUTPUT_FILE}")
    df_all.to_parquet(OUTPUT_FILE, index=False)

    size_mb = OUTPUT_FILE.stat().st_size / (1024 * 1024)
    print(f"✅ 完成! {len(df_all)} rows, {size_mb:.1f} MB")
    print(f"  lock_time: {df_all['lock_time'].min()} ~ {df_all['lock_time'].max()}")

    # Verify key series
    for series in ["LS6", "L6", "LS7", "LS8", "LS9"]:
        cnt = df_all[df_all["series"] == series]["order_number"].nunique()
        lt_min = df_all[df_all["series"] == series]["lock_time"].min()
        lt_max = df_all[df_all["series"] == series]["lock_time"].max()
        if cnt > 0:
            print(f"  {series}: {cnt} orders, lock_time {lt_min} ~ {lt_max}")


if __name__ == "__main__":
    main()
