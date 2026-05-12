import datetime
import pandas as pd


def _normalize_city(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("市") and len(s) > 1:
        s = s[:-1]
    if s.endswith("地区") and len(s) > 2:
        s = s[: -len("地区")]
    if s.endswith("自治州") and len(s) > 3:
        s = s[: -len("自治州")]
    if s.endswith("盟") and len(s) > 1:
        s = s[:-1]
    return s


def _default_city_tier_mapping() -> dict[str, str]:
    tier1 = {"北京", "上海", "广州", "深圳"}
    new_tier1 = {
        "成都",
        "杭州",
        "重庆",
        "武汉",
        "苏州",
        "西安",
        "天津",
        "南京",
        "郑州",
        "长沙",
        "东莞",
        "宁波",
        "佛山",
        "青岛",
        "沈阳",
        "昆明",
    }
    tier2 = {
        "合肥",
        "无锡",
        "厦门",
        "福州",
        "济南",
        "大连",
        "温州",
        "哈尔滨",
        "长春",
        "泉州",
        "南宁",
        "贵阳",
        "南昌",
        "金华",
        "常州",
        "嘉兴",
        "惠州",
        "珠海",
        "中山",
        "台州",
        "烟台",
        "兰州",
        "绍兴",
        "海口",
        "乌鲁木齐",
        "太原",
        "石家庄",
        "徐州",
        "潍坊",
        "扬州",
    }
    mapping: dict[str, str] = {}
    for c in tier1:
        mapping[c] = "一线"
    for c in new_tier1:
        mapping[c] = "新一线"
    for c in tier2:
        mapping[c] = "二线"
    return mapping


def run_city_tier_distribution_operator(
    df: pd.DataFrame,
    start: str,
    end: str,
    series: str | None,
    city_field: str,
    time_field: str = "lock_time",
) -> dict:
    if df is None or df.empty:
        return {"type": "city_tier_distribution", "error": "no_data", "message": "无可用数据。"}
    if time_field not in df.columns:
        return {"type": "city_tier_distribution", "error": "missing_time_field", "message": f"缺少时间字段: {time_field}"}
    if city_field not in df.columns:
        return {"type": "city_tier_distribution", "error": "missing_city_field", "message": f"缺少城市字段: {city_field}"}

    try:
        start_day = datetime.date.fromisoformat(str(start)[:10])
        end_day = datetime.date.fromisoformat(str(end)[:10])
    except Exception:
        return {"type": "city_tier_distribution", "error": "invalid_time_window", "message": "时间窗口格式错误。"}
    if end_day <= start_day:
        return {"type": "city_tier_distribution", "error": "invalid_time_window", "message": "时间窗口不合法。"}

    work = df.copy()
    work[time_field] = pd.to_datetime(work[time_field], errors="coerce")
    work = work[work[time_field].notna()]
    if series and "series" in work.columns:
        work = work[work["series"] == series]
    if work.empty:
        return {"type": "city_tier_distribution", "error": "no_data", "message": "筛选后无数据。"}

    start_ts = pd.Timestamp(start_day)
    end_ts = pd.Timestamp(end_day)
    work = work[(work[time_field] >= start_ts) & (work[time_field] < end_ts)]
    if work.empty:
        return {"type": "city_tier_distribution", "error": "no_data", "message": "时间窗口内无数据。"}

    mapping = _default_city_tier_mapping()
    city_norm = work[city_field].apply(_normalize_city)
    tier = city_norm.map(mapping)
    tier = tier.fillna("三线及以下")

    total = int(len(work))
    rows: list[dict] = []
    order = ["一线", "新一线", "二线", "三线及以下"]
    for label in order:
        cnt = int((tier == label).sum())
        share = 0.0 if total <= 0 else (cnt / float(total))
        rows.append({"tier": label, "count": cnt, "share": share})

    return {
        "type": "city_tier_distribution",
        "series": series,
        "time_field": time_field,
        "date_start": start_day.isoformat(),
        "date_end": end_day.isoformat(),
        "city_field": city_field,
        "total": total,
        "rows": rows,
    }

