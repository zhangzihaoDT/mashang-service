import pandas as pd

from operators.active_store import _calc_active_store_count


def run_store_avg_lock_operator(df: pd.DataFrame, start: str, end: str) -> dict:
    start_ts = pd.to_datetime(start, errors="coerce")
    end_ts = pd.to_datetime(end, errors="coerce")
    if pd.isna(start_ts) or pd.isna(end_ts):
        return {"type": "store_avg_lock", "error": "invalid_time_range", "message": "start/end 时间解析失败"}
    start_day = pd.Timestamp(start_ts).normalize()
    end_day = pd.Timestamp(end_ts).normalize()
    if end_day <= start_day:
        return {"type": "store_avg_lock", "error": "invalid_time_range", "message": "end 必须大于 start"}

    df = df.copy()
    lock_time = pd.to_datetime(df.get("lock_time"), errors="coerce")
    df["_lock_day"] = lock_time.dt.normalize()

    days = pd.date_range(start_day, end_day - pd.Timedelta(days=1), freq="D")
    rows: list[dict] = []
    for d in days:
        lock_count = int(df[df["_lock_day"] == d].shape[0])
        store_count = _calc_active_store_count(df, d)
        avg = round(lock_count / store_count, 2) if store_count > 0 else 0.0
        rows.append({"date": d.strftime("%Y-%m-%d"), "lock_count": lock_count, "active_store_count": store_count, "store_avg_lock": avg})

    if not rows:
        return {"type": "store_avg_lock", "start": start_day.strftime("%Y-%m-%d"), "end": end_day.strftime("%Y-%m-%d"), "daily_rows": []}

    max_row = max(rows, key=lambda x: x["store_avg_lock"])
    min_row = min(rows, key=lambda x: x["store_avg_lock"])
    total_lock = sum(r["lock_count"] for r in rows)
    total_store_days = sum(r["active_store_count"] for r in rows)
    overall_avg = round(total_lock / total_store_days, 2) if total_store_days > 0 else 0.0

    return {
        "type": "store_avg_lock",
        "start": start_day.strftime("%Y-%m-%d"),
        "end": end_day.strftime("%Y-%m-%d"),
        "window_days": len(rows),
        "overall_store_avg_lock": overall_avg,
        "max_store_avg_lock": max_row["store_avg_lock"],
        "max_date": max_row["date"],
        "min_store_avg_lock": min_row["store_avg_lock"],
        "min_date": min_row["date"],
        "daily_rows": rows,
    }
