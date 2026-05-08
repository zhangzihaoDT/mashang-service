import datetime


def _parse_int_token(token: str) -> int | None:
    if not isinstance(token, str):
        return None
    raw = token.strip()
    if not raw:
        return None
    if raw.isdigit():
        try:
            return int(raw)
        except Exception:
            return None
    mapping = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if raw in mapping:
        return mapping[raw]
    return None


def resolve_listed_since_window(user_query: str, today: datetime.date, business_definition: dict) -> tuple[str, str] | None:
    q = user_query or ""
    want_listed_since = any(k in q for k in ["上市至今", "上市以来"])
    want_presale_since = any(k in q for k in ["预售至今", "预售以来"])
    if not (want_listed_since or want_presale_since):
        return None
    time_periods = business_definition.get("time_periods") if isinstance(business_definition, dict) else None
    if not isinstance(time_periods, dict) or not time_periods:
        return None

    q_upper = q.upper().replace(" ", "")
    keys = [k for k in time_periods.keys() if isinstance(k, str) and k.strip()]
    keys.sort(key=lambda x: len(x), reverse=True)
    for key in keys:
        if key.upper() not in q_upper:
            continue
        meta = time_periods.get(key)
        if not isinstance(meta, dict):
            continue
        field = "end" if want_listed_since else "start"
        start = meta.get(field)
        if not isinstance(start, str) or not start.strip():
            fallback = meta.get("start")
            if not isinstance(fallback, str) or not fallback.strip():
                continue
            start = fallback
        try:
            start_date = datetime.date.fromisoformat(start.strip())
        except Exception:
            continue
        if today <= start_date:
            return None
        return (start_date.isoformat(), today.isoformat())
    return None


def resolve_recent_window(user_query: str, today: datetime.date) -> tuple[str, str] | None:
    import re

    q = (user_query or "").replace(" ", "")
    if not q:
        return None
    m = re.search(r"近(?P<n>\d+|[一二两三四五六七八九十])(?P<u>日|天|周)", q)
    if not m:
        return None
    n = _parse_int_token(m.group("n"))
    if not n or n <= 0:
        return None
    unit = m.group("u")
    days = n
    if unit == "周":
        days = n * 7
    start = today - datetime.timedelta(days=days)
    end = today
    if end <= start:
        return None
    return (start.isoformat(), end.isoformat())


def resolve_time_window(user_query: str, today: datetime.date, business_definition: dict) -> tuple[str, str] | None:
    window = resolve_listed_since_window(user_query=user_query, today=today, business_definition=business_definition)
    if window:
        return window
    window = resolve_recent_window(user_query=user_query, today=today)
    if window:
        return window
    return None
