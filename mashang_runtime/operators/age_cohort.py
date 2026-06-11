import datetime
import re
import pandas as pd


def _extract_cohort_tokens(user_query: str) -> list[str]:
    q = (user_query or "").replace(" ", "")
    if not q:
        return []
    order = ["00后", "95后", "90后", "85后", "80后", "75后", "70后", "65后", "60前"]
    out = [t for t in order if t in q]
    return out


def _cohort_to_birth_year_range(token: str) -> tuple[int | None, int | None] | None:
    mapping: dict[str, tuple[int | None, int | None]] = {
        "00后": (2000, 2009),
        "95后": (1995, 1999),
        "90后": (1990, 1994),
        "85后": (1985, 1989),
        "80后": (1980, 1984),
        "75后": (1975, 1979),
        "70后": (1970, 1974),
        "65后": (1965, 1969),
        "60前": (None, 1959),
    }
    return mapping.get(token)


def _infer_birth_year_from_identity(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.where(series.notna(), other=pd.NA)
    pattern = re.compile(r"^\d{17}[\dXx]$")
    valid = s.apply(lambda x: bool(pattern.match(str(x))) if x is not pd.NA else False)
    birth_year = pd.Series(pd.NA, index=s.index, dtype="Int64")
    if int(valid.sum()) == 0:
        return birth_year
    years = s[valid].str.slice(6, 10)
    parsed = pd.to_numeric(years, errors="coerce").round().astype("Int64")
    birth_year.loc[valid] = parsed
    return birth_year


def _infer_birth_year_from_age(lock_time: pd.Series, age: pd.Series) -> pd.Series:
    lock_dt = pd.to_datetime(lock_time, errors="coerce")
    age_num = pd.to_numeric(age, errors="coerce")
    birth_year = pd.Series(pd.NA, index=lock_dt.index, dtype="Int64")
    valid = lock_dt.notna() & age_num.notna()
    if float(valid.mean()) < 0.01:
        return birth_year
    lock_year = lock_dt.dt.year.astype("Int64")
    est = (lock_year[valid].astype("float") - age_num[valid].astype("float")).round()
    birth_year.loc[valid] = pd.to_numeric(est, errors="coerce").astype("Int64")
    return birth_year


def run_age_cohort_operator(
    df: pd.DataFrame,
    user_query: str,
    start: str,
    end: str,
    series: str | None,
    age_field: str,
    identity_field: str | None = None,
    time_field: str = "lock_time",
) -> dict:
    if df is None or df.empty:
        return {"type": "age_cohort_distribution", "error": "no_data", "message": "无可用数据。"}
    if time_field not in df.columns:
        return {"type": "age_cohort_distribution", "error": "missing_time_field", "message": f"缺少时间字段: {time_field}"}
    if age_field not in df.columns and (not identity_field or identity_field not in df.columns):
        return {
            "type": "age_cohort_distribution",
            "error": "missing_age_fields",
            "message": f"缺少年龄字段: {age_field}",
        }

    try:
        start_day = datetime.date.fromisoformat(str(start)[:10])
        end_day = datetime.date.fromisoformat(str(end)[:10])
    except Exception:
        return {"type": "age_cohort_distribution", "error": "invalid_time_window", "message": "时间窗口格式错误。"}
    if end_day <= start_day:
        return {"type": "age_cohort_distribution", "error": "invalid_time_window", "message": "时间窗口不合法。"}

    work = df.copy()
    work[time_field] = pd.to_datetime(work[time_field], errors="coerce")
    work = work[work[time_field].notna()]
    if series and "series" in work.columns:
        work = work[work["series"] == series]
    if work.empty:
        return {"type": "age_cohort_distribution", "error": "no_data", "message": "筛选后无数据。"}

    start_ts = pd.Timestamp(start_day)
    end_ts = pd.Timestamp(end_day)
    work = work[(work[time_field] >= start_ts) & (work[time_field] < end_ts)]
    if work.empty:
        return {"type": "age_cohort_distribution", "error": "no_data", "message": "时间窗口内无数据。"}

    birth_year = pd.Series(pd.NA, index=work.index, dtype="Int64")
    if identity_field and identity_field in work.columns:
        by_id = _infer_birth_year_from_identity(work[identity_field])
        if float(by_id.notna().mean()) >= 0.2:
            birth_year = by_id
    if birth_year.notna().sum() == 0 and age_field in work.columns:
        birth_year = _infer_birth_year_from_age(lock_time=work[time_field], age=work[age_field])

    cohorts = _extract_cohort_tokens(user_query)
    if not cohorts:
        cohorts = ["00后", "95后", "90后", "85后", "80后", "75后", "70后", "65后", "60前"]

    def _bucket(y: object) -> str | None:
        if y is None or pd.isna(y):
            return None
        try:
            year = int(y)
        except Exception:
            return None
        for token in cohorts:
            rng = _cohort_to_birth_year_range(token)
            if not rng:
                continue
            lo, hi = rng
            if lo is None and hi is not None and year <= hi:
                return token
            if hi is None and lo is not None and year >= lo:
                return token
            if lo is not None and hi is not None and lo <= year <= hi:
                return token
        return None

    cohort_series = birth_year.apply(_bucket)
    total = int(len(work))
    unknown = int(cohort_series.isna().sum())
    known = total - unknown

    rows: list[dict] = []
    for token in cohorts:
        cnt = int((cohort_series == token).sum())
        share = 0.0 if known <= 0 else (cnt / float(known))
        rows.append({"cohort": token, "count": cnt, "share": share})

    return {
        "type": "age_cohort_distribution",
        "series": series,
        "time_field": time_field,
        "date_start": start_day.isoformat(),
        "date_end": end_day.isoformat(),
        "age_field": age_field,
        "identity_field": identity_field,
        "total": total,
        "known": known,
        "unknown": unknown,
        "rows": rows,
    }

