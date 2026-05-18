import pandas as pd


def _parse_cn_date(s: pd.Series) -> pd.Series:
    s = s.astype(str)
    parts = s.str.extract(r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日")
    dt = pd.to_datetime(parts["y"] + "-" + parts["m"] + "-" + parts["d"], errors="coerce").dt.normalize()
    if dt.notna().any():
        return dt
    return pd.to_datetime(s, errors="coerce").dt.normalize()


def _sum_col(day: pd.DataFrame, col_map: dict[str, str], key: str) -> int:
    col = col_map.get(str(key).strip())
    if col is None:
        return 0
    s = day[col].astype("string").str.replace(",", "", regex=False).str.replace("，", "", regex=False)
    return int(pd.to_numeric(s, errors="coerce").fillna(0).sum())


def _sum_any(day: pd.DataFrame, col_map: dict[str, str], candidates: list[str]) -> int:
    for c in candidates:
        v = _sum_col(day, col_map, c)
        if v != 0:
            return v
    return 0


def _safe_ratio(numer: float, denom: float) -> float | None:
    if denom == 0.0:
        return None
    return float(numer) / denom


def _to_pct_1dp(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{round(value * 100.0, 1):.1f}%"


def _per_100_str(value: float | None, total: float) -> str | None:
    if value is None or total == 0:
        return None
    per100 = round((value / total) * 100.0, 1)
    return f"{per100:.1f}‰"


def _build_raw_key_rates(day: pd.DataFrame, col_map: dict[str, str]) -> dict[str, float | None]:
    leads = float(_sum_col(day, col_map, "下发线索数"))
    store_leads = float(_sum_col(day, col_map, "下发线索数 (门店)"))
    lock0 = float(_sum_any(day, col_map, ["下发线索当日锁单数 (门店)", "下发线索当日锁单数"]))
    lock7 = float(_sum_col(day, col_map, "下发线索 7 日锁单数"))
    lock30 = float(_sum_col(day, col_map, "下发线索 30 日锁单数"))
    lock0_rate_denom = store_leads if store_leads > 0 else leads
    return {
        "leads": leads,
        "store_leads": store_leads,
        "lock0": lock0,
        "lock7": lock7,
        "lock30": lock30,
        "lock0_rate_denom": lock0_rate_denom,
    }


def _build_conversion_row(day: pd.DataFrame, col_map: dict[str, str], date_str: str) -> dict:
    raw = _build_raw_key_rates(day, col_map)
    leads = raw["leads"]
    store_leads = raw["store_leads"]
    lock0 = raw["lock0"]
    lock7 = raw["lock7"]
    lock30 = raw["lock30"]
    td0 = _sum_col(day, col_map, "下发线索当日试驾数")
    store_cnt = _sum_col(day, col_map, "下发门店数")

    leads_live = _sum_any(day, col_map, ["下发线索数（直播）", "下发线索数（直播)", "下发线索数 (直播)", "下发线索数 (直播)"])
    leads_platform = _sum_any(day, col_map, ["下发线索数（平台)", "下发线索数（平台）", "下发线索数 (平台)", "下发线索数 (平台)"])
    leads_app = _sum_any(day, col_map, ["下发线索数（APP小程序)", "下发线索数（APP小程序）", "下发线索数 (APP小程序)", "下发线索数 (APP小程序)"])
    leads_flash = _sum_any(day, col_map, ["下发线索数（快慢闪)", "下发线索数（快慢闪）", "下发线索数 (快慢闪)", "下发线索数 (快慢闪)"])

    lock7_store = _sum_any(day, col_map, ["下发线索 7 日锁单数 (门店)", "下发线索 7日锁单数 (门店)", "下发线索7日锁单数 (门店)"])
    lock7_live = _sum_any(day, col_map, ["下发线索 7 日锁单数 (直播)", "下发线索 7日锁单数 (直播)", "下发线索7日锁单数 (直播)"])
    lock7_platform = _sum_any(day, col_map, ["下发线索 7 日锁单数 (平台)", "下发线索 7日锁单数 (平台)", "下发线索7日锁单数 (平台)"])

    lock30_store = _sum_any(day, col_map, ["下发线索 30 日锁单数 (门店)", "下发线索 30日锁单数 (门店)", "下发线索30日锁单数 (门店)"])
    lock30_live = _sum_any(day, col_map, ["下发线索 30 日锁单数 (直播)", "下发线索 30日锁单数 (直播)", "下发线索30日锁单数 (直播)"])
    lock30_platform = _sum_any(day, col_map, ["下发线索 30 日锁单数 (平台)", "下发线索 30日锁单数 (平台)", "下发线索30日锁单数 (平台)"])
    lock30_app = _sum_any(day, col_map, ["下发线索 30 日锁单数 (APP小程序)", "下发线索 30日锁单数 (APP小程序)", "下发线索30日锁单数 (APP小程序)"])
    lock30_flash = _sum_any(day, col_map, ["下发线索 30 日锁单数 (快慢闪)", "下发线索 30日锁单数 (快慢闪)", "下发线索30日锁单数 (快慢闪)"])

    lock0_rate_denom = store_leads if store_leads > 0 else leads

    return {
        "date": date_str,
        "下发线索数": leads,
        "下发线索数 (门店)": store_leads,
        "下发线索数（直播）": leads_live,
        "下发线索数（平台)": leads_platform,
        "下发线索数（APP小程序)": leads_app,
        "下发线索数（快慢闪)": leads_flash,
        "下发线索当日试驾数": td0,
        "下发 (门店)线索当日锁单数": lock0,
        "下发线索 7 日锁单数": lock7,
        "下发线索 30 日锁单数": lock30,
        "下发门店数": store_cnt,
        "门店线索占比": _to_pct_1dp(_safe_ratio(store_leads, leads)),
        "下发线索当日试驾率": _to_pct_1dp(_safe_ratio(td0, leads)),
        "下发 (门店)线索当日锁单率": _to_pct_1dp(_safe_ratio(lock0, lock0_rate_denom)),
        "下发线索当7日锁单率": _to_pct_1dp(_safe_ratio(lock7, leads)),
        "下发线索当30日锁单率": _to_pct_1dp(_safe_ratio(lock30, leads)),
        "下发线索数（门店)7日锁单率": _to_pct_1dp(_safe_ratio(lock7_store, store_leads)),
        "下发线索数（直播)7日锁单率": _to_pct_1dp(_safe_ratio(lock7_live, leads_live)),
        "下发线索数（平台)7日锁单率": _to_pct_1dp(_safe_ratio(lock7_platform, leads_platform)),
        "下发线索数（门店)30日锁单率": _to_pct_1dp(_safe_ratio(lock30_store, store_leads)),
        "下发线索数（直播)30日锁单率": _to_pct_1dp(_safe_ratio(lock30_live, leads_live)),
        "下发线索数（平台)30日锁单率": _to_pct_1dp(_safe_ratio(lock30_platform, leads_platform)),
        "下发线索数（APP小程序)30日锁单率": _to_pct_1dp(_safe_ratio(lock30_app, leads_app)),
        "下发线索数（快慢闪)30日锁单率": _to_pct_1dp(_safe_ratio(lock30_flash, leads_flash)),
    }


def run_assign_conversion_operator(df: pd.DataFrame, start: str, end: str) -> dict:
    if df is None or df.empty:
        return {"type": "assign_conversion", "error": "no_data", "message": "无可用数据。"}

    try:
        start_day = pd.Timestamp(start).normalize()
        end_day = pd.Timestamp(end).normalize()
    except Exception:
        return {"type": "assign_conversion", "error": "invalid_time_window", "message": "时间窗口格式错误。"}
    if end_day <= start_day:
        return {"type": "assign_conversion", "error": "invalid_time_window", "message": "end 必须大于 start。"}

    work = df.copy()
    work["_date"] = _parse_cn_date(work.get("Assign Time 年/月/日", pd.Series(dtype="object")))
    work = work[work["_date"].notna()]
    if work.empty:
        return {"type": "assign_conversion", "error": "no_date_column", "message": "缺少可解析的日期列。"}

    days = pd.date_range(start_day, end_day - pd.Timedelta(days=1), freq="D")
    daily_rows: list[dict] = []

    for d in days:
        day_df = work[work["_date"] == d]
        if day_df.empty:
            continue
        col_map = {str(c).strip(): c for c in day_df.columns}
        daily_rows.append(_build_conversion_row(day_df, col_map, d.strftime("%Y-%m-%d")))

    if not daily_rows:
        return {"type": "assign_conversion", "start": start_day.strftime("%Y-%m-%d"), "end": end_day.strftime("%Y-%m-%d"), "daily_rows": [], "summary_rates": {}}

    summary: dict[str, str | None] = {}
    rate_keys = [
        "门店线索占比", "下发线索当日试驾率", "下发 (门店)线索当日锁单率",
        "下发线索当7日锁单率", "下发线索当30日锁单率",
        "下发线索数（门店)7日锁单率", "下发线索数（直播)7日锁单率", "下发线索数（平台)7日锁单率",
        "下发线索数（门店)30日锁单率", "下发线索数（直播)30日锁单率", "下发线索数（平台)30日锁单率",
        "下发线索数（APP小程序)30日锁单率", "下发线索数（快慢闪)30日锁单率",
    ]
    count_keys = [
        "下发线索数", "下发线索数 (门店)", "下发线索数（直播）", "下发线索数（平台)", "下发线索数（APP小程序)", "下发线索数（快慢闪)",
        "下发线索当日试驾数", "下发 (门店)线索当日锁单数", "下发线索 7 日锁单数", "下发线索 30 日锁单数", "下发门店数",
    ]

    totals: dict[str, float] = {}
    for k in count_keys:
        totals[k] = sum(float(r.get(k, 0) or 0) for r in daily_rows)

    lock0_denom = totals.get("下发线索数 (门店)", 0) if totals.get("下发线索数 (门店)", 0) > 0 else totals.get("下发线索数", 0)
    rate_map: dict[str, tuple[str, str]] = {
        "门店线索占比": ("下发线索数 (门店)", "下发线索数"),
        "下发线索当日试驾率": ("下发线索当日试驾数", "下发线索数"),
        "下发 (门店)线索当日锁单率": ("下发 (门店)线索当日锁单数", "__lock0_denom"),
        "下发线索当7日锁单率": ("下发线索 7 日锁单数", "下发线索数"),
        "下发线索当30日锁单率": ("下发线索 30 日锁单数", "下发线索数"),
        "下发线索数（门店)7日锁单率": ("下发线索 7 日锁单数", "下发线索数 (门店)"),
        "下发线索数（直播)7日锁单率": ("下发线索 7 日锁单数", "下发线索数（直播）"),
        "下发线索数（平台)7日锁单率": ("下发线索 7 日锁单数", "下发线索数（平台)"),
        "下发线索数（门店)30日锁单率": ("下发线索 30 日锁单数", "下发线索数 (门店)"),
        "下发线索数（直播)30日锁单率": ("下发线索 30 日锁单数", "下发线索数（直播）"),
        "下发线索数（平台)30日锁单率": ("下发线索 30 日锁单数", "下发线索数（平台)"),
        "下发线索数（APP小程序)30日锁单率": ("下发线索 30 日锁单数", "下发线索数（APP小程序)"),
        "下发线索数（快慢闪)30日锁单率": ("下发线索 30 日锁单数", "下发线索数（快慢闪)"),
    }
    for key, (numer_key, denom_key) in rate_map.items():
        numer = totals.get(numer_key, 0)
        if denom_key == "__lock0_denom":
            denom = lock0_denom
        else:
            denom = totals.get(denom_key, 0)
        summary[key] = _to_pct_1dp(_safe_ratio(numer, denom))

    return {
        "type": "assign_conversion",
        "start": start_day.strftime("%Y-%m-%d"),
        "end": end_day.strftime("%Y-%m-%d"),
        "window_days": len(daily_rows),
        "summary_totals": {k: int(v) for k, v in totals.items()},
        "summary_rates": summary,
        "daily_rows": daily_rows,
    }
