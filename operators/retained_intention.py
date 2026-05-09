import pandas as pd

def run_retained_intention_operator(df: pd.DataFrame, series: str, start: str, end: str) -> dict:
    if df is None or df.empty:
        return {"error": "dataset_empty", "message": "数据集为空"}

    start_day = pd.to_datetime(start)
    end_day = pd.to_datetime(end)
    
    # 由于 planner 解析自然语言时，如果是“2025-08-15到2025-09-10”，
    # end_day 会被处理成开区间 2025-09-11 00:00:00，
    # 而如果 end_day 是 00:00:00 的开区间，实际上代表的业务截止日是它减去 1 天。
    if end_day.hour == 0 and end_day.minute == 0 and end_day.second == 0:
        actual_end_day = end_day - pd.Timedelta(days=1)
    else:
        actual_end_day = end_day

    n_days = int((actual_end_day.normalize() - start_day.normalize()).days + 1)
    n_days = max(1, n_days)
    
    presale_end_excl = actual_end_day + pd.Timedelta(days=1)
    window_end_excl = start_day + pd.Timedelta(days=n_days)
    window_end_excl = min(window_end_excl, presale_end_excl)

    df_model = df
    if series:
        if "series_group_logic" in df.columns:
            df_model = df[df['series_group_logic'] == series]
        elif "series" in df.columns:
            df_model = df[df['series'] == series]

    mask_time = (df_model['intention_payment_time'].notna()) & \
                (df_model['intention_payment_time'] >= start_day) & \
                (df_model['intention_payment_time'] < window_end_excl)

    mask_retained = df_model['intention_refund_time'].isna() | \
                    (df_model['intention_refund_time'] > window_end_excl)

    retained_orders = df_model.loc[mask_time & mask_retained, 'order_number'].dropna().drop_duplicates()
    retained_count = int(retained_orders.nunique())

    return {
        "type": "retained_intention",
        "series": series,
        "start": start_day.strftime("%Y-%m-%d"),
        "end": actual_end_day.strftime("%Y-%m-%d"),
        "retained_count": retained_count
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
    m_retained = refund.isna() | (refund >= presale_end_excl_ts)
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
