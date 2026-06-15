#!/usr/bin/env python
"""从本地 dataset 构建 daily matrix CSV（供 structured_business_forecast.py 使用）"""
import sys, json
from pathlib import Path

import pandas as pd
import numpy as np

WS_ROOT = Path(__file__).resolve().parents[1]
PRJ_ROOT = WS_ROOT.parent
ORDER_PARQUET = PRJ_ROOT / "dataset" / "order_data.parquet"
ASSIGN_CSV = PRJ_ROOT / "dataset" / "assign_data.csv"
OUTPUT = WS_ROOT / "schema" / "index_summary_daily_matrix.csv"

# 1. Daily lock orders from order_data
df = pd.read_parquet(ORDER_PARQUET)
lock = df[df["lock_time"].notna()].copy()
lock["date"] = pd.to_datetime(lock["lock_time"]).dt.normalize()
daily_lock = lock.groupby("date").agg(**{"订单分析.锁单数": ("order_number", "nunique")}).reset_index()
daily_lock = daily_lock.sort_values("date")

# 2. Daily leads from assign_data (handle Chinese date format)
def parse_cn_date(s):
    s = s.astype(str)
    parts = s.str.extract(r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日")
    return pd.to_datetime(parts["y"] + "-" + parts["m"] + "-" + parts["d"], errors="coerce").dt.normalize()

assign = pd.read_csv(ASSIGN_CSV)
assign["date"] = parse_cn_date(assign["Assign Time 年/月/日"])
assign = assign.dropna(subset=["date"])
assign["date"] = assign["date"].dt.normalize()
daily_assign = assign.groupby("date").agg(
    **{"下发线索转化率.下发线索数": ("下发线索数", lambda x: pd.to_numeric(x, errors="coerce").sum())}
).reset_index()

# 3. Merge
merged = pd.merge(daily_lock, daily_assign, on="date", how="outer").sort_values("date")
merged = merged.fillna(0)

# 4. Compute lock rate (30d rolling)
merged["lock_30d"] = merged["订单分析.锁单数"].rolling(30, min_periods=1).sum()
merged["leads_30d"] = merged["下发线索转化率.下发线索数"].rolling(30, min_periods=1).sum()
merged["下发线索转化率.下发线索当30日锁单率"] = np.where(
    merged["leads_30d"] > 0, merged["lock_30d"] / merged["leads_30d"], 0
)

# Also 7d
merged["lock_7d"] = merged["订单分析.锁单数"].rolling(7, min_periods=1).sum()
merged["leads_7d"] = merged["下发线索转化率.下发线索数"].rolling(7, min_periods=1).sum()
merged["下发线索转化率.下发线索当7日锁单率"] = np.where(
    merged["leads_7d"] > 0, merged["lock_7d"] / merged["leads_7d"], 0
)

# 5. Pivot to matrix format (metrics as rows, dates as columns)
metrics = [
    "订单分析.锁单数",
    "下发线索转化率.下发线索数",
    "下发线索转化率.下发线索当30日锁单率",
    "下发线索转化率.下发线索当7日锁单率",
]

pivot_data = {"metric": metrics}
for _, row in merged.iterrows():
    d = row["date"].strftime("%Y-%m-%d")
    pivot_data[d] = [row[m] for m in metrics]

matrix = pd.DataFrame(pivot_data)
matrix.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
print(f"Matrix saved: {OUTPUT} ({len(merged)} days, {len(metrics)} metrics)")
print(f"Date range: {merged['date'].min().date()} ~ {merged['date'].max().date()}")
