#!/usr/bin/env python
"""Read raw forecast JSON and produce a Result Contract for HTML rendering."""
import json
import sys
from pathlib import Path

RAW = Path(__file__).with_name("june_2026_forecast.json")
data = json.loads(RAW.read_text("utf-8"))

mt = data["scenario_forecast"]["month_forecast"]["month_totals"]
h1_actual = int(mt["actual_lock_orders_to_date"])
p10 = int(round(mt["remaining_lock_orders_bias_corrected_p10"]))
p50 = int(round(mt["remaining_lock_orders_bias_corrected_p50"]))
mode = int(round(mt["remaining_lock_orders_bias_corrected_mode"]))
p90 = int(round(mt["remaining_lock_orders_bias_corrected_p90"]))

contract = {
    "status": "success",
    "script": "research_scripts/structured_business_forecast.py",
    "brand_name": "Raccoon Research",
    "generated_at": "2026-06-15T00:00:00",
    "scope": {
        "data_source": "index_summary_daily_matrix.csv",
        "time_window": {"start_date": "2026-06-01", "end_date": "2026-06-30"},
        "metric_definition": "Metrics Map 预测（Bias 校正，Bootstrap 8000 次/天）",
    },
    "result": {
        "summary": "2026年6月销量预测：P50 6,727 ｜ 最可能 6,704 ｜ 预测区间 6,219 – 7,275",
        "forecast": {
            "p10": p10,
            "p50": p50,
            "mode": mode,
            "p90": p90,
            "range_low": p10,
            "range_high": p90,
            "h1_actual": h1_actual,
            "scenarios": [
                {"name": "P10（保守）", "actual": h1_actual, "forecast": p10, "total": h1_actual + p10, "highlight": False},
                {"name": "P50（中位）", "actual": h1_actual, "forecast": p50, "total": h1_actual + p50, "highlight": True},
                {"name": "Mode（最可能）", "actual": h1_actual, "forecast": mode, "total": h1_actual + mode, "highlight": True},
                {"name": "P90（乐观）", "actual": h1_actual, "forecast": p90, "total": h1_actual + p90, "highlight": False},
            ],
            "insights": [
                {"title": "同比微增 +2%", "body": "6月预计 ~6,700。"},
                {"title": "环比回落 -15%", "body": "环比 5 月下降约 15%。"},
                {"title": "周末动能持续", "body": "6 月上半月周末日均 366。"},
                {"title": "下半月预计回升", "body": "下半月基线回归正常节奏。"},
            ],
            "methodology": [
                {"param": "历史回看", "value": "365 天"},
                {"param": "Bootstrap 模拟", "value": "8,000 次 / 天"},
            ],
        },
    },
    "followup_context": {
        "metric": "lock_forecast",
        "available_dimensions": ["series", "model", "city"],
    },
}

json.dump(contract, sys.stdout, ensure_ascii=False, indent=2)
