import pandas as pd


def _compute_retained_counts(
    df_model: pd.DataFrame,
    series: str,
    presale_start: pd.Timestamp,
    presale_end_excl: pd.Timestamp,
    as_of_dates: list[pd.Timestamp],
) -> dict:
    m_presale = (
        df_model['intention_payment_time'].notna()
        & (df_model['intention_payment_time'] >= presale_start)
        & (df_model['intention_payment_time'] < presale_end_excl)
    )
    presale_orders = df_model.loc[m_presale, [
        'order_number', 'intention_refund_time', 'deposit_payment_time',
        'deposit_refund_time', 'lock_time',
    ]].copy()
    presale_orders['order_number'] = presale_orders['order_number'].astype('string')
    presale_orders = presale_orders.dropna(subset=['order_number']).drop_duplicates(subset=['order_number'])

    exit_cols = [c for c in ['intention_refund_time', 'deposit_payment_time',
                              'deposit_refund_time', 'lock_time'] if c in presale_orders.columns]
    exit_time = presale_orders[exit_cols].min(axis=1, skipna=True)

    counts = []
    for d in as_of_dates:
        as_of_excl = d + pd.Timedelta(days=1)
        cnt = int((exit_time.isna() | (exit_time >= as_of_excl)).sum())
        counts.append(cnt)
    return {"exit_time": exit_time, "presale_total": len(presale_orders), "daily_counts": counts}


def run_retained_intention_operator(df: pd.DataFrame, series: str, start: str, end: str,
                                    plan: dict | None = None,
                                    business_definition: dict | None = None) -> dict:
    if df is None or df.empty:
        return {"error": "dataset_empty", "message": "数据集为空"}

    # --- resolve presale period from business_definition ---
    presale_start = None
    presale_end_excl = None
    if isinstance(business_definition, dict) and series:
        tp = (business_definition.get("time_periods") or {}).get(series)
        if isinstance(tp, dict):
            s = tp.get("start")
            e = tp.get("end")
            if isinstance(s, str) and isinstance(e, str):
                presale_start = pd.to_datetime(s)
                presale_end_excl = pd.to_datetime(e) + pd.Timedelta(days=1)

    if presale_start is None or presale_end_excl is None:
        return {"type": "retained_intention", "error": "missing_presale_period",
                "message": f"business_definition 中缺少 {series} 的 time_periods 预售期"}

    # --- filter series ---
    df_model = df
    if series:
        if "series_group_logic" in df.columns:
            df_model = df[df['series_group_logic'] == series]
        elif "series" in df.columns:
            df_model = df[df['series'] == series]

    # --- resolve as-of window from start/end (system convention: end is exclusive) ---
    start_day = pd.to_datetime(start)
    end_day = pd.to_datetime(end)
    if end_day.hour == 0 and end_day.minute == 0 and end_day.second == 0:
        actual_end_day = end_day - pd.Timedelta(days=1)
    else:
        actual_end_day = end_day

    n_days = int((actual_end_day.normalize() - start_day.normalize()).days + 1)
    n_days = max(1, n_days)
    as_of_dates = [start_day.normalize() + pd.Timedelta(days=i) for i in range(n_days)]

    result = _compute_retained_counts(df_model, series, presale_start, presale_end_excl, as_of_dates)
    daily_counts = result["daily_counts"]

    stats = (plan or {}).get("statistics", {}) or {}
    if stats.get("type") == "trend_summary":
        daily_rows = [
            {"date": d.strftime("%Y-%m-%d"), "留存小订数": c}
            for d, c in zip(as_of_dates, daily_counts)
        ]
        return {
            "type": "retained_intention",
            "series": series,
            "daily_rows": daily_rows,
            "metric_alias": "留存小订数",
            "window_days": n_days,
            "date_start": start_day.strftime("%Y-%m-%d"),
            "date_end": (actual_end_day + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        }

    retained_count = daily_counts[0] if daily_counts else 0
    return {
        "type": "retained_intention",
        "series": series,
        "start": start_day.strftime("%Y-%m-%d"),
        "end": actual_end_day.strftime("%Y-%m-%d"),
        "retained_count": retained_count,
    }


def run_retained_intention_conversion_operator(
    df: pd.DataFrame,
    series: str,
    lock_start: str,
    lock_end: str,
    business_definition: dict | None = None,
) -> dict:
    if df is None or df.empty:
        return {"type": "retained_intention_conversion", "error": "dataset_empty", "message": "数据集为空"}
    if not series:
        return {"type": "retained_intention_conversion", "error": "missing_series", "message": "缺少 series 过滤条件"}
    required_cols = {"order_number", "intention_payment_time", "intention_refund_time", "lock_time"}
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        return {"type": "retained_intention_conversion", "error": "missing_columns", "missing_columns": missing}

    lock_start_ts = pd.to_datetime(lock_start, errors="coerce")
    lock_end_ts = pd.to_datetime(lock_end, errors="coerce")
    if pd.isna(lock_start_ts) or pd.isna(lock_end_ts) or lock_end_ts <= lock_start_ts:
        return {"type": "retained_intention_conversion", "error": "invalid_time_range", "message": f"lock_start={lock_start} lock_end={lock_end}"}

    df_model = df
    if "series_group_logic" in df.columns:
        df_model = df[df["series_group_logic"] == series]
    elif "series" in df.columns:
        df_model = df[df["series"] == series]

    pay = df_model["intention_payment_time"]
    refund = df_model["intention_refund_time"]
    lock = df_model["lock_time"]

    if not pd.api.types.is_datetime64_any_dtype(pay):
        pay = pd.to_datetime(pay, errors="coerce")
    if not pd.api.types.is_datetime64_any_dtype(refund):
        refund = pd.to_datetime(refund, errors="coerce")
    if not pd.api.types.is_datetime64_any_dtype(lock):
        lock = pd.to_datetime(lock, errors="coerce")

    presale_start_ts = None
    presale_end_excl_ts = None
    if isinstance(business_definition, dict):
        tp = (business_definition.get("time_periods") or {}).get(series)
        if isinstance(tp, dict):
            s = tp.get("start")
            e = tp.get("end")
            if isinstance(s, str) and isinstance(e, str):
                s_ts = pd.to_datetime(s, errors="coerce")
                e_ts = pd.to_datetime(e, errors="coerce")
                if pd.notna(s_ts) and pd.notna(e_ts):
                    presale_start_ts = s_ts
                    presale_end_excl_ts = e_ts + pd.Timedelta(days=1)

    if presale_start_ts is None or presale_end_excl_ts is None:
        presale_start_ts = lock_start_ts
        presale_end_excl_ts = lock_end_ts

    m_presale_pay = pay.notna() & (pay >= presale_start_ts) & (pay < presale_end_excl_ts)

    exit_cols = [c for c in ['intention_refund_time', 'deposit_payment_time',
                              'deposit_refund_time', 'lock_time'] if c in df_model.columns]
    exit_time = df_model[exit_cols].min(axis=1, skipna=True)
    m_retained = exit_time.isna() | (exit_time >= presale_end_excl_ts)

    retained_orders = df_model.loc[m_presale_pay & m_retained, "order_number"].dropna().astype("string").drop_duplicates()

    m_lock = lock.notna() & (lock >= lock_start_ts) & (lock < lock_end_ts)
    lock_orders = df_model.loc[m_lock, "order_number"].dropna().astype("string").drop_duplicates()

    retained_set = set(retained_orders.tolist())
    m_retained_lock = m_lock & df_model["order_number"].astype("string").isin(retained_set)
    retained_lock_orders = df_model.loc[m_retained_lock, "order_number"].dropna().astype("string").drop_duplicates()

    retained_cnt = int(retained_orders.nunique())
    total_lock_cnt = int(lock_orders.nunique())
    retained_lock_cnt = int(retained_lock_orders.nunique())
    share = (retained_lock_cnt / float(total_lock_cnt)) if total_lock_cnt > 0 else 0.0
    rate = (retained_lock_cnt / float(retained_cnt)) if retained_cnt > 0 else 0.0

    return {
        "type": "retained_intention_conversion",
        "series": series,
        "lock_start": lock_start_ts.strftime("%Y-%m-%d"),
        "lock_end": (lock_end_ts - pd.Timedelta(days=1)).strftime("%Y-%m-%d") if lock_end_ts.hour == 0 and lock_end_ts.minute == 0 and lock_end_ts.second == 0 else lock_end_ts.strftime("%Y-%m-%d"),
        "presale_start": presale_start_ts.strftime("%Y-%m-%d") if presale_start_ts is not None else None,
        "presale_end": (presale_end_excl_ts - pd.Timedelta(days=1)).strftime("%Y-%m-%d") if presale_end_excl_ts is not None else None,
        "retained_count": retained_cnt,
        "total_lock_count": total_lock_cnt,
        "retained_lock_count": retained_lock_cnt,
        "retained_lock_share": share,
        "retained_lock_rate": rate,
    }
