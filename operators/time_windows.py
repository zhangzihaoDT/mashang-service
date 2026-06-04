import datetime
import re


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
        "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    }
    if raw in mapping:
        return mapping[raw]
    return None


def _normalize_year(y: str) -> int | None:
    if not y:
        return None
    y = str(y).strip()
    if not y.isdigit():
        return None
    if len(y) == 2:
        return 2000 + int(y)
    if len(y) == 4:
        return int(y)
    return None


def _safe_date(y: int, m: int, d: int) -> datetime.date | None:
    try:
        return datetime.date(int(y), int(m), int(d))
    except Exception:
        return None


def _month_window(year: int, month: int) -> tuple[str, str] | None:
    if month < 1 or month > 12:
        return None
    start = _safe_date(year, month, 1)
    if not start:
        return None
    if month == 12:
        end = _safe_date(year + 1, 1, 1)
    else:
        end = _safe_date(year, month + 1, 1)
    if not end:
        return None
    return (start.isoformat(), end.isoformat())


def _year_window(year: int) -> tuple[str, str] | None:
    start = _safe_date(year, 1, 1)
    end = _safe_date(year + 1, 1, 1)
    if not start or not end:
        return None
    return (start.isoformat(), end.isoformat())


def _parse_month_token(token: str) -> int | None:
    if not token:
        return None
    raw = str(token).strip()
    if not raw:
        return None
    if raw.isdigit():
        try:
            v = int(raw)
            return v if 1 <= v <= 12 else None
        except Exception:
            return None
    mapping = {
        "正": 1, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
        "十一": 11, "十二": 12,
    }
    if raw in mapping:
        return mapping[raw]
    return None


def _has_range_indicator(q: str) -> bool:
    return bool(re.search(r"[日月号年\d][~到至\-\u2014\u2013\uFF0D][\d年月]", q.replace(" ", "")))


# ── extractors ────────────────────────────────────────────

def extract_listed_dates(user_query: str, today: datetime.date) -> list[str]:
    q = (user_query or "").replace(" ", "")
    if not q:
        return []

    dates: list[datetime.date] = []
    for raw in re.findall(r"\d{4}-\d{2}-\d{2}", q):
        try:
            dates.append(datetime.date.fromisoformat(raw))
        except Exception:
            continue

    mds = list(re.finditer(r"(?:(?P<y>\d{2,4})\s*年\s*)?(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*[日号]?", q))
    if mds:
        base_year = None
        for mt in mds:
            yv = _normalize_year(mt.group("y"))
            if yv:
                base_year = yv
                break
        if base_year is None:
            base_year = today.year
        for mt in mds:
            yv = _normalize_year(mt.group("y")) or base_year
            try:
                mv = int(mt.group("m"))
                dv = int(mt.group("d"))
            except Exception:
                continue
            try:
                dates.append(datetime.date(int(yv), int(mv), int(dv)))
            except Exception:
                continue

    if not dates:
        return []
    uniq = sorted(set(dates))
    return [d.isoformat() for d in uniq]


def parse_until_end_date(user_query: str) -> datetime.date | None:
    q = (user_query or "").replace(" ", "")
    if not q:
        return None
    if not any(k in q for k in ["截至", "截止", "到", "至"]):
        return None
    m = re.search(r"(?:截至|截止)(\d{4}-\d{2}-\d{2})", q)
    if m:
        try:
            return datetime.date.fromisoformat(m.group(1))
        except Exception:
            return None
    m = re.search(r"(?:截至|截止)(?P<y>\d{2,4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})", q)
    if m:
        try:
            yv = m.group("y")
            y = int(yv) if len(str(yv)) == 4 else 2000 + int(yv)
            return datetime.date(y, int(m.group("m")), int(m.group("d")))
        except Exception:
            return None
    m = re.search(r"(?:到|至)(\d{4}-\d{2}-\d{2})(?:为止|截止|之前|以前)", q)
    if m:
        try:
            return datetime.date.fromisoformat(m.group(1))
        except Exception:
            return None
    return None


# ── window resolvers ─────────────────────────────────────

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
    q = (user_query or "").replace(" ", "")
    if not q:
        return None
    m = re.search(r"近(?P<n>\d+|[一二两三四五六七八九十])(?:\s*个)?\s*(?P<u>日|天|周|月|年)", q)
    if not m:
        return None
    n = _parse_int_token(m.group("n"))
    if not n or n <= 0:
        return None
    unit = m.group("u")
    days = n
    if unit == "周":
        days = n * 7
    elif unit == "月":
        days = n * 30
    elif unit == "年":
        days = n * 365
    start = today - datetime.timedelta(days=days)
    end = today
    if end <= start:
        return None
    return (start.isoformat(), end.isoformat())


def resolve_time_window(user_query: str, today: datetime.date, business_definition: dict) -> tuple[str, str] | None:
    window = resolve_listed_since_window(user_query=user_query, today=today, business_definition=business_definition)
    if window:
        return window
    dates = extract_listed_dates(user_query=user_query, today=today)
    if len(dates) >= 2:
        try:
            start_day = datetime.date.fromisoformat(dates[0])
            end_day = datetime.date.fromisoformat(dates[-1])
            end_open = end_day + datetime.timedelta(days=1)
            if end_open > start_day:
                return (start_day.isoformat(), end_open.isoformat())
        except Exception:
            pass
    window = resolve_recent_window(user_query=user_query, today=today)
    if window:
        return window
    return None


# ── enhanced parser (superset of resolve_time_window) ────

def parse_time_window(user_query: str, today: datetime.date) -> tuple[str, str] | None:
    q = user_query or ""
    if "昨天" in q or "昨日" in q:
        start = today - datetime.timedelta(days=1)
        end = today
        return (start.isoformat(), end.isoformat())

    window = resolve_time_window(user_query=user_query, today=today, business_definition={})
    if window:
        return window

    if "本月" in q:
        start = _safe_date(today.year, today.month, 1)
        if start:
            return (start.isoformat(), today.isoformat())
    if "本周" in q:
        monday = today - datetime.timedelta(days=today.weekday())
        if monday:
            return (monday.isoformat(), today.isoformat())
    if "上月" in q:
        year = today.year
        month = today.month - 1
        if month <= 0:
            year -= 1
            month = 12
        w = _month_window(year, month)
        if w:
            return w

    m = re.search(
        r"(?:(?P<y>\d{2,4})\s*年\s*)?(?P<m>\d{1,2}|正|十一|十二|[一二两三四五六七八九十])\s*月\s*"
        r"(?:(?:到|至|[-~—–－])\s*)?(?:至今|到今|现在|目前|今天|今日|截至今日|截至今天|截至昨日|昨日)",
        q,
    )
    if m:
        year = _normalize_year(m.group("y")) or today.year
        month = _parse_month_token(m.group("m")) or today.month
        start = _safe_date(year, month, 1)
        if start:
            return (start.isoformat(), today.isoformat())

    if "前年" in q:
        w = _year_window(today.year - 2)
        if w:
            return w
    if "去年" in q:
        w = _year_window(today.year - 1)
        if w:
            return w
    if "今年" in q:
        w = _year_window(today.year)
        if w:
            return w

    m = re.search(
        r"(?P<y>\d{2,4})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*[日号]?\s*(?:到|至|[-~—–－])\s*(?P<iso>\d{4}-\d{2}-\d{2})",
        q,
    )
    if m:
        y1 = _normalize_year(m.group("y")) or today.year
        start_date = _safe_date(y1, int(m.group("m")), int(m.group("d")))
        end_date = datetime.date.fromisoformat(m.group("iso"))
        if start_date and end_date:
            return (start_date.isoformat(), (end_date + datetime.timedelta(days=1)).isoformat())

    m = re.search(
        r"(?P<y>\d{2,4})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*[日号]?\s*(?:到|至|[-~—–－])\s*"
        r"(?!\d{4}-\d{2}-\d{2})"
        r"(?:(?P<y2>\d{2,4})\s*年\s*)?(?:(?P<m2>\d{1,2})\s*月\s*)?(?P<d2>\d{1,2})\s*[日号]?",
        q,
    )
    if m:
        y1 = _normalize_year(m.group("y")) or today.year
        m1 = int(m.group("m"))
        d1 = int(m.group("d"))
        y2 = _normalize_year(m.group("y2")) or y1
        m2 = int(m.group("m2") or m1)
        d2 = int(m.group("d2"))
        start_date = _safe_date(y1, m1, d1)
        end_date = _safe_date(y2, m2, d2)
        if start_date and end_date:
            return (start_date.isoformat(), (end_date + datetime.timedelta(days=1)).isoformat())

    m = re.search(r"(?P<y>\d{2,4})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?:整月|全月|整个月)", q)
    if m:
        w = _month_window(_normalize_year(m.group("y")) or today.year, int(m.group("m")))
        if w:
            return w

    m = re.search(r"(?P<y>\d{2,4})\s*年\s*(?P<m>\d{1,2})\s*月(?!\s*\d)", q)
    if m:
        w = _month_window(_normalize_year(m.group("y")) or today.year, int(m.group("m")))
        if w:
            return w

    m = re.search(r"(?:(?P<y>\d{2,4})\s*年\s*)?(?P<m>正|十一|十二|[一二两三四五六七八九十])\s*月(?!\s*\d)", q)
    if m:
        month = _parse_month_token(m.group("m"))
        if month:
            w = _month_window(_normalize_year(m.group("y")) or today.year, month)
            if w:
                return w

    m = re.search(r"(?P<y>\d{2,4})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*[日号]?", q)
    if m:
        start_date = _safe_date(_normalize_year(m.group("y")) or today.year, int(m.group("m")), int(m.group("d")))
        if start_date:
            return (start_date.isoformat(), (start_date + datetime.timedelta(days=1)).isoformat())

    m = re.search(r"(?P<y>\d{2,4})年(?!\s*\d|\s*月\s*(?:\d|整|全))", q)
    if m:
        w = _year_window(_normalize_year(m.group("y")) or today.year)
        if w:
            return w

    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:到|至|[-~—–－])\s*(\d{4}-\d{2}-\d{2})", q)
    if m:
        start_date = datetime.date.fromisoformat(m.group(1))
        end_date = datetime.date.fromisoformat(m.group(2))
        return (start_date.isoformat(), (end_date + datetime.timedelta(days=1)).isoformat())

    m = re.search(
        r"(?P<y>\d{4})-(?P<m1>\d{1,2})-(?P<d1>\d{1,2})\s*(?:到|至|[-~—–－])\s*(?P<m2>\d{1,2})-(?P<d2>\d{1,2})",
        q,
    )
    if m:
        year = int(m.group("y"))
        start_date = _safe_date(year, int(m.group("m1")), int(m.group("d1")))
        end_date = _safe_date(year, int(m.group("m2")), int(m.group("d2")))
        if start_date and end_date:
            return (start_date.isoformat(), (end_date + datetime.timedelta(days=1)).isoformat())

    m = re.search(r"(\d{4}-\d{2}-\d{2})", q)
    if m:
        start = datetime.date.fromisoformat(m.group(1))
        return (start.isoformat(), (start + datetime.timedelta(days=1)).isoformat())

    return None


def parse_time_window_with_business(
    user_query: str,
    today: datetime.date,
    business_definition: dict | None = None,
) -> tuple[str, str] | None:
    if isinstance(business_definition, dict):
        window = resolve_time_window(user_query=user_query, today=today, business_definition=business_definition)
        if window:
            return window
    return parse_time_window(user_query, today)


# ── classifiers ──────────────────────────────────────────

def infer_time_window_type(user_query: str) -> str | None:
    q = (user_query or "").strip()
    if not q:
        return None
    if "昨天" in q or "昨日" in q:
        return "yesterday"
    if "本周" in q:
        return "this_week"
    if "本月" in q:
        return "this_month_to_today"
    if "上月" in q:
        return "last_month"
    if any(k in q for k in ["至今", "截至", "目前", "现在", "今日", "今天"]) and ("月" in q):
        return "month_to_today"
    if re.search(r"\d{2,4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*[日号]?\s*(?:到|至|[-~—–－])\s*(?:\d{2,4}\s*年\s*)?(?:\d{1,2}\s*月\s*)?\d{1,2}\s*[日号]?", q):
        return "date_range"
    if re.search(r"\d{4}-\d{2}-\d{2}\s*(?:到|至|[-~—–－])\s*\d{4}-\d{2}-\d{2}", q):
        return "date_range"
    if re.search(r"\d{2,4}\s*年\s*\d{1,2}\s*月(?!\s*\d)", q) or re.search(r"(?:(?:\d{2,4}\s*年\s*)?)(?:正|十一|十二|[一二两三四五六七八九十])\s*月(?!\s*\d)", q):
        return "month"
    if re.search(r"\d{2,4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*[日号]?", q):
        return "date"
    if re.search(r"\d{2,4}\s*年(?!\s*\d|\s*月\s*(?:\d|整|全))", q):
        return "year"
    if re.search(r"\d{4}-\d{2}-\d{2}", q):
        return "date"
    return None


def parse_comparison_type(user_query: str) -> str:
    q = user_query or ""
    if "日环比" in q or "天环比" in q:
        return "dod"
    if ("昨天" in q or "昨日" in q or "今天" in q or "今日" in q) and ("环比" in q) and ("周环比" not in q):
        return "dod"
    if "同比" in q or "年同比" in q:
        return "yoy"
    if "环比" in q or "周环比" in q:
        return "wow"
    return "none"


def is_cumulative_query(user_query: str) -> bool:
    return any(k in (user_query or "") for k in ["累计", "累积"])


def extract_compare_year(user_query: str, current_year: int) -> int | None:
    q = user_query or ""
    m = re.search(r"同比\s*(\d{4})\s*年", q)
    if m:
        return int(m.group(1))
    for m in re.finditer(r"(\d{4})\s*年\s*同期", q):
        y = int(m.group(1))
        if y != current_year:
            return y
    return None


def contains_relative_to_today_hint(user_query: str) -> bool:
    q = user_query or ""
    return any(k in q for k in ["至今", "截至", "目前", "现在", "今日", "今天", "本月"])


# ── goal inference ───────────────────────────────────────

def infer_goal_time_window_rule(user_query: str, today: datetime.date) -> dict:
    q = user_query or ""
    until_end = parse_until_end_date(q)
    if until_end:
        end_open = until_end + datetime.timedelta(days=1)
        start = until_end - datetime.timedelta(days=30)
        return {"window": (start.isoformat(), end_open.isoformat()), "confidence": "medium", "source": "until_date"}

    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:到|至|[-~—–－])\s*(\d{4}-\d{2}-\d{2})", q)
    if m:
        start_date = datetime.date.fromisoformat(m.group(1))
        end_date = datetime.date.fromisoformat(m.group(2))
        return {"window": (start_date.isoformat(), (end_date + datetime.timedelta(days=1)).isoformat()), "confidence": "high", "source": "iso_range"}

    m = re.search(
        r"(?P<y>\d{2,4})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*[日号]?\s*(?:到|至|[-~—–－])\s*(?P<iso>\d{4}-\d{2}-\d{2})",
        q,
    )
    if m:
        y1 = m.group("y")
        start_date = datetime.date(int(y1) if len(str(y1)) == 4 else 2000 + int(y1), int(m.group("m")), int(m.group("d")))
        end_date = datetime.date.fromisoformat(m.group("iso"))
        return {"window": (start_date.isoformat(), (end_date + datetime.timedelta(days=1)).isoformat()), "confidence": "high", "source": "mixed_cn_iso"}

    window = parse_time_window(q, today)
    if not window:
        return {"window": None, "confidence": "low", "source": "none"}

    iso_dates = []
    for raw in re.findall(r"\d{4}-\d{2}-\d{2}", q):
        try:
            iso_dates.append(datetime.date.fromisoformat(raw))
        except Exception:
            pass
    cn_dates = []
    for m_cn in re.finditer(r"(?P<y>\d{2,4})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*[日号]?", q):
        yv = m_cn.group("y")
        y = int(yv) if len(str(yv)) == 4 else 2000 + int(yv)
        try:
            cn_dates.append(datetime.date(y, int(m_cn.group("m")), int(m_cn.group("d"))))
        except Exception:
            pass

    confidence = "low"
    source = "fallback"
    if any(k in q for k in ["昨天", "昨日", "今天", "今日", "本周", "上周", "本月", "上月", "今年", "去年", "前年", "至今", "截至", "目前", "现在"]):
        confidence = "medium"
        source = "relative"
    elif ("到" in q or "至" in q or "-" in q or "~" in q or "—" in q or "–" in q or "－" in q) and (len(cn_dates) >= 2):
        confidence = "high"
        source = "cn_range"
    elif len(iso_dates) == 1 and len(cn_dates) >= 1 and ("到" in q or "至" in q):
        try:
            parsed_end = datetime.date.fromisoformat(window[1])
            max_iso = max(iso_dates)
            if parsed_end <= max_iso:
                start_date = min(cn_dates)
                end_date = max_iso
                return {"window": (start_date.isoformat(), (end_date + datetime.timedelta(days=1)).isoformat()), "confidence": "medium", "source": "mixed_fallback"}
        except Exception:
            pass
    elif len(iso_dates) == 1 or len(cn_dates) == 1:
        confidence = "medium"
        source = "single_date"

    return {"window": window, "confidence": confidence, "source": source}


def infer_goal_time_window(
    user_query: str,
    today: datetime.date,
    business_definition: dict | None = None,
) -> dict:
    q = user_query or ""
    has_retention_hint = ("留存" in q) or ("预售期" in q)
    until_end = parse_until_end_date(q)
    if has_retention_hint and until_end and isinstance(business_definition, dict):
        if isinstance(business_definition.get("time_periods"), dict):
            for token in business_definition["time_periods"]:
                if isinstance(token, str) and token.upper() in q.upper().replace(" ", ""):
                    meta = business_definition["time_periods"].get(token)
                    if isinstance(meta, dict):
                        s = meta.get("start")
                        if isinstance(s, str) and s.strip():
                            try:
                                start_day = datetime.date.fromisoformat(s.strip())
                                end_open = until_end + datetime.timedelta(days=1)
                                if end_open > start_day:
                                    return {"window": (start_day.isoformat(), end_open.isoformat()), "confidence": "high", "source": "until_date_series_start"}
                            except Exception:
                                pass
                    break
    window = None
    if isinstance(business_definition, dict):
        window = resolve_time_window(user_query=user_query, today=today, business_definition=business_definition)
    if window:
        return {"window": window, "confidence": "high", "source": "resolve_time_window"}
    return infer_goal_time_window_rule(user_query, today)


# ── plan helpers ─────────────────────────────────────────

def cumulative_adjust_time(plan_time: dict, user_query: str) -> dict:
    if not is_cumulative_query(user_query):
        return plan_time
    today = datetime.date.today()
    q = (user_query or "").replace(" ", "")
    current_year_str = str(today.year)
    if current_year_str in q and isinstance(plan_time, dict):
        end_str = plan_time.get("end")
        if isinstance(end_str, str):
            try:
                end_date = datetime.date.fromisoformat(end_str[:10])
            except Exception:
                end_date = None
            if end_date and end_date > today:
                plan_time["end"] = (today + datetime.timedelta(days=1)).isoformat()
    return plan_time


def remove_cumulative_time_dim(plan: dict, user_query: str) -> dict:
    if not is_cumulative_query(user_query):
        return plan
    time_field = None
    time_info = plan.get("time")
    if isinstance(time_info, dict):
        time_field = time_info.get("field")
    if not isinstance(time_field, str) or not time_field:
        return plan
    dims = plan.get("dimensions")
    if isinstance(dims, list) and time_field in dims:
        has_other_dim = any(isinstance(d, str) and d and d != time_field for d in dims)
        if has_other_dim:
            plan["dimensions"] = [d for d in dims if d != time_field]
        else:
            plan["dimensions"] = []
    if isinstance(plan.get("post_process"), list):
        plan["post_process"] = [s for s in plan["post_process"] if isinstance(s, dict) and s.get("type") != "window_share"]

    cumulative_adjust_time(plan.get("time") or {}, user_query)
    return plan


# ── facade ───────────────────────────────────────────────

def parse_time_semantics(
    user_query: str,
    today: datetime.date,
    business_definition: dict | None = None,
) -> dict:
    result: dict = {}

    result["comparison_type"] = parse_comparison_type(user_query)
    result["is_cumulative"] = is_cumulative_query(user_query)
    result["time_window_type"] = infer_time_window_type(user_query)

    window = parse_time_window_with_business(user_query, today, business_definition)
    result["window"] = window

    result["confidence"] = "low"
    result["source"] = "none"
    goal = infer_goal_time_window(user_query, today, business_definition)
    if isinstance(goal, dict):
        result["confidence"] = goal.get("confidence", "low")
        result["source"] = goal.get("source", "none")

    dates = extract_listed_dates(user_query, today)
    result["dates_are_range"] = _has_range_indicator(user_query) if len(dates) >= 2 else False

    if window and result["time_window_type"] in ("year", "date") and result["is_cumulative"]:
        result["time_mode"] = "ytd"
    elif window and result["time_window_type"] == "year":
        result["time_mode"] = "year"
    elif window and result["time_window_type"] in ("month", "this_month_to_today", "last_month"):
        result["time_mode"] = "month"
    elif window and result["time_window_type"] in ("date", "date_range"):
        result["time_mode"] = "range"
    elif window and result["time_window_type"] in ("yesterday", "this_week"):
        result["time_mode"] = "relative"
    else:
        result["time_mode"] = "unknown"

    return result
