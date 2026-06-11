import pandas as pd

from operators.assign_conversion import _parse_cn_date, _build_raw_key_rates


def _to_pct_1dp(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{round(value * 100.0, 1):.1f}%"


def _safe_div(numer: float, denom: float) -> float | None:
    if denom == 0.0:
        return None
    return float(numer) / denom


def _calc_weighted(
    store_day0_lock: float | None,
    store_share: float | None,
    lock7_rate: float | None,
    lock30_rate: float | None,
) -> float | None:
    if store_day0_lock is not None and store_share is not None:
        term1 = 0.4 * store_day0_lock * store_share
    else:
        term1 = None
    term2 = 0.4 * lock7_rate if lock7_rate is not None else None
    term3 = 0.2 * lock30_rate if lock30_rate is not None else None
    parts = [v for v in [term1, term2, term3] if v is not None]
    if not parts:
        return None
    return sum(parts)


def run_weighted_lead_conversion_operator(df: pd.DataFrame, start: str, end: str) -> dict:
    if df is None or df.empty:
        return {"type": "weighted_lead_conversion", "error": "no_data", "message": "无可用数据。"}

    try:
        start_day = pd.Timestamp(start).normalize()
        end_day = pd.Timestamp(end).normalize()
    except Exception:
        return {"type": "weighted_lead_conversion", "error": "invalid_time_window", "message": "时间窗口格式错误。"}
    if end_day <= start_day:
        return {"type": "weighted_lead_conversion", "error": "invalid_time_window", "message": "end 必须大于 start。"}

    work = df.copy()
    work["_date"] = _parse_cn_date(work.get("Assign Time 年/月/日", pd.Series(dtype="object")))
    work = work[work["_date"].notna()]
    if work.empty:
        return {"type": "weighted_lead_conversion", "error": "no_date_column", "message": "缺少可解析的日期列。"}

    latest_data_date = work["_date"].max()
    cutoff = latest_data_date - pd.Timedelta(days=30)
    effective_start = start_day
    effective_end = min(end_day, cutoff + pd.Timedelta(days=1))
    excluded_prefix = 0
    if effective_end <= effective_start:
        return {
            "type": "weighted_lead_conversion",
            "error": "insufficient_data_window",
            "message": f"数据集最新日期为 {latest_data_date.strftime('%Y-%m-%d')}，"
                       f"30 日锁单率需要 30 天回看窗口。请求窗口 {start_day.strftime('%Y-%m-%d')}~{end_day.strftime('%Y-%m-%d')} "
                       f"内无 30 日数据完整的日期（有效截止日为 {cutoff.strftime('%Y-%m-%d')}）。",
        }

    days = pd.date_range(effective_start, effective_end - pd.Timedelta(days=1), freq="D")
    daily_rows: list[dict] = []
    total_leads = 0.0
    total_store_leads = 0.0
    total_lock0 = 0.0
    total_lock7 = 0.0
    total_lock30 = 0.0

    for d in days:
        day_df = work[work["_date"] == d]
        if day_df.empty:
            continue
        col_map = {str(c).strip(): c for c in day_df.columns}
        raw = _build_raw_key_rates(day_df, col_map)
        total_leads += raw["leads"]
        total_store_leads += raw["store_leads"]
        total_lock0 += raw["lock0"]
        total_lock7 += raw["lock7"]
        total_lock30 += raw["lock30"]
        lock7_rate = _safe_div(raw["lock7"], raw["leads"])
        lock30_rate = _safe_div(raw["lock30"], raw["leads"])
        store_share = _safe_div(raw["store_leads"], raw["leads"])
        store_day0_lock = _safe_div(raw["lock0"], raw["lock0_rate_denom"])
        weighted = _calc_weighted(store_day0_lock, store_share, lock7_rate, lock30_rate)
        daily_rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "下发线索数": int(raw["leads"]),
            "门店线索占比": _to_pct_1dp(store_share),
            "门店当日锁单率": _to_pct_1dp(store_day0_lock),
            "7日锁单率": _to_pct_1dp(lock7_rate),
            "30日锁单率": _to_pct_1dp(lock30_rate),
            "加权锁单率": _to_pct_1dp(weighted),
        })

    overall_store_share = _safe_div(total_store_leads, total_leads)
    overall_store_day0_lock = _safe_div(total_lock0, total_store_leads if total_store_leads > 0 else total_leads)
    overall_lock7 = _safe_div(total_lock7, total_leads)
    overall_lock30 = _safe_div(total_lock30, total_leads)
    overall_weighted = _calc_weighted(overall_store_day0_lock, overall_store_share, overall_lock7, overall_lock30)

    return {
        "type": "weighted_lead_conversion",
        "requested_start": start_day.strftime("%Y-%m-%d"),
        "requested_end": end_day.strftime("%Y-%m-%d"),
        "effective_start": effective_start.strftime("%Y-%m-%d"),
        "effective_end": effective_end.strftime("%Y-%m-%d"),
        "window_days": len(daily_rows),
        "latest_data_date": latest_data_date.strftime("%Y-%m-%d"),
        "加权锁单率": _to_pct_1dp(overall_weighted),
        "门店线索占比": _to_pct_1dp(overall_store_share),
        "门店当日锁单率": _to_pct_1dp(overall_store_day0_lock),
        "7日锁单率": _to_pct_1dp(overall_lock7),
        "30日锁单率": _to_pct_1dp(overall_lock30),
        "权重公式": "0.4 × (门店当日锁单率 × 门店线索占比) + 0.4 × 7日锁单率 + 0.2 × 30日锁单率",
        "daily_rows": daily_rows,
    }
