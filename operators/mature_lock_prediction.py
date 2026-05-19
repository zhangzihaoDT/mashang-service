"""
下发线索成熟度预测锁单数 (Lead Maturity Forecast Locks)

基于成熟度曲线（Maturity Curve）修正右删失数据：
对于未完全成熟的下发线索 cohort（age < 30d），预测其最终30日锁单数。

核心规则（三段式，无指数模型）：
  age >= 30  → pred_30 = lock_30（已成熟，直接使用原始值）
  age >= 7   → pred_30 = lock_7 / r7（7日数据完整，通过历史7→30比例推算）
  age < 7    → pred_30 = 0.5 × avg + 0.5 × lock0 / r0

其中：
  r7 = sum(lock_7) / sum(lock_30)  — 历史完全成熟cohort中7日锁单占30日锁单比例
  r0 = sum(lock0) / sum(lock_30)   — 历史完全成熟cohort中当日锁单占30日锁单比例
"""

import pandas as pd

from operators.assign_conversion import _parse_cn_date, _sum_col, _sum_any


def _extract_keys(
    day: pd.DataFrame, col_map: dict[str, str]
) -> dict[str, float]:
    leads = float(_sum_col(day, col_map, "下发线索数"))
    store_leads = float(_sum_col(day, col_map, "下发线索数 (门店)"))
    lock0 = float(
        _sum_any(
            day, col_map,
            ["下发线索当日锁单数 (门店)", "下发线索当日锁单数"],
        )
    )
    lock7 = float(_sum_col(day, col_map, "下发线索 7 日锁单数"))
    lock30 = float(_sum_col(day, col_map, "下发线索 30 日锁单数"))
    return {
        "leads": leads,
        "store_leads": store_leads,
        "lock0": lock0,
        "lock7": lock7,
        "lock30": lock30,
    }


def run_mature_lock_prediction_operator(
    df: pd.DataFrame, start: str, end: str
) -> dict:
    if df is None or df.empty:
        return {
            "type": "mature_lock_prediction",
            "error": "no_data",
            "message": "无可用数据。",
        }

    try:
        start_day = pd.Timestamp(start).normalize()
        end_day = pd.Timestamp(end).normalize()
    except Exception:
        return {
            "type": "mature_lock_prediction",
            "error": "invalid_time_window",
            "message": "时间窗口格式错误。",
        }
    if end_day <= start_day:
        return {
            "type": "mature_lock_prediction",
            "error": "invalid_time_window",
            "message": "end 必须大于 start。",
        }

    work = df.copy()
    work["_date"] = _parse_cn_date(
        work.get("Assign Time 年/月/日", pd.Series(dtype="object"))
    )
    work = work[work["_date"].notna()]
    if work.empty:
        return {
            "type": "mature_lock_prediction",
            "error": "no_date_column",
            "message": "缺少可解析的日期列。",
        }

    snapshot_date = work["_date"].max()
    work["_age"] = (snapshot_date - work["_date"]).dt.days

    # ── 1. 从完全成熟 cohort (age >= 30) 计算历史比率 ──
    mature = work[work["_age"] >= 30].copy()
    if mature.empty:
        return {
            "type": "mature_lock_prediction",
            "error": "no_mature_cohort",
            "message": "数据集中无 age >= 30d 的完全成熟 cohort，无法构建成熟度基准。",
        }

    mature_keys = mature.apply(
        lambda r: _extract_keys(
            pd.DataFrame([r]),
            {str(c).strip(): c for c in mature.columns},
        ),
        axis=1,
        result_type="expand",
    )
    total_leads_m = float(mature_keys["leads"].sum())
    total_lock0_m = float(mature_keys["lock0"].sum())
    total_lock7_m = float(mature_keys["lock7"].sum())
    total_lock30_m = float(mature_keys["lock30"].sum())

    if total_leads_m == 0 or total_lock30_m == 0:
        return {
            "type": "mature_lock_prediction",
            "error": "insufficient_data",
            "message": "成熟 cohort 线索数或锁单数为 0，无法计算历史比率。",
        }

    avg_7d_rate = total_lock7_m / total_leads_m
    avg_30d_rate = total_lock30_m / total_leads_m
    r7 = total_lock7_m / total_lock30_m       # 7日占30日比例 ≈ 0.7165
    r0 = total_lock0_m / total_lock30_m        # 当日占30日比例

    # ── 2. 逐日预测 ──
    days = pd.date_range(start_day, end_day - pd.Timedelta(days=1), freq="D")
    daily_rows: list[dict] = []
    for d in days:
        day_df = work[work["_date"] == d]
        if day_df.empty:
            continue
        col_map = {str(c).strip(): c for c in day_df.columns}
        raw = _extract_keys(day_df, col_map)
        age = int(day_df["_age"].iloc[0])

        if age >= 30:
            p30 = raw["lock30"]
            p30_method = "actual"

        elif age >= 7:
            p30 = raw["lock7"] / r7 if r7 > 0 else raw["lock30"]
            p30_method = "projected_via_7d"

        else:
            # age < 7: 历史均值预测与当日锁单预测加权平均
            estimate_from_avg = raw["leads"] * avg_30d_rate
            if r0 > 0 and raw["lock0"] > 0:
                estimate_from_day0 = raw["lock0"] / r0
                p30 = 0.5 * estimate_from_avg + 0.5 * estimate_from_day0
                p30_method = "weighted_avg_and_day0"
            else:
                p30 = estimate_from_avg
                p30_method = "estimated_via_avg"

        daily_rows.append(
            {
                "date": d.strftime("%Y-%m-%d"),
                "下发线索数": int(raw["leads"]),
                "当日锁单数": int(raw["lock0"]),
                "原始7日锁单数": int(raw["lock7"]),
                "原始30日锁单数": int(raw["lock30"]),
                "预测30日锁单数": round(p30, 1),
                "cohort年龄": age,
                "预测方法": p30_method,
            }
        )

    if not daily_rows:
        return {
            "type": "mature_lock_prediction",
            "start": start_day.strftime("%Y-%m-%d"),
            "end": end_day.strftime("%Y-%m-%d"),
            "window_days": 0,
            "daily_rows": [],
        }

    total_leads = sum(r["下发线索数"] for r in daily_rows)
    total_raw30 = sum(r["原始30日锁单数"] for r in daily_rows)
    total_pred30 = sum(r["预测30日锁单数"] for r in daily_rows)

    return {
        "type": "mature_lock_prediction",
        "start": start_day.strftime("%Y-%m-%d"),
        "end": end_day.strftime("%Y-%m-%d"),
        "snapshot_date": snapshot_date.strftime("%Y-%m-%d"),
        "window_days": len(daily_rows),
        "mature_cohort_stats": {
            "历史平均30日锁单率": round(avg_30d_rate, 4),
            "历史平均7日锁单率": round(avg_7d_rate, 4),
            "7日占30日比例(r7)": round(r7, 4),
            "当日占30日比例(r0)": round(r0, 4),
        },
        "预测规则": {
            "age>=30": "直接使用原始30日锁单数",
            "age>=7": "原始7日锁单数 ÷ r7",
            "age<7": "max(线索数×平均30日锁单率, 当日锁单数÷r0)",
        },
        "summary": {
            "总下发线索数": int(total_leads),
            "原始30日锁单数合计": int(total_raw30),
            "预测30日锁单数合计": round(total_pred30, 1),
            "原始30日锁单率": round(total_raw30 / total_leads, 4)
            if total_leads > 0
            else 0,
            "预测30日锁单率": round(total_pred30 / total_leads, 4)
            if total_leads > 0
            else 0,
        },
        "daily_rows": daily_rows,
    }
