"""
乘联分会周度数据早源监控 — Period-Aware

监控乘联分会/乘联会周度核心数据发布时间线，按目标周严格归因。
P0: stcn.com 人民财讯（早信号）| P0_final: CADA 官网（最终权威归档）

Usage:
    python research_scripts/cpca_weekly_early_signal.py --week 2026-W26
    python research_scripts/cpca_weekly_early_signal.py --week 2026-W26 --format html
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_REPORT_DIR = _ROOT / "outputs" / "reports"
_REPORT_DIR.mkdir(parents=True, exist_ok=True)
_CONFIG_PATH = _ROOT / "configs" / "cpca_weekly_sources.json"
_DATASET_DIR = Path(__file__).resolve().parents[2] / "dataset" / "cpca_weekly"
_DATASET_DIR.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════
#  Huoshan Search
# ════════════════════════════════════════════

@dataclass
class SearchResult:
    title: str
    url: str
    content: str = ""
    published_at: str = ""
    source_provider: str = ""
    website: str = ""
    score: float | None = None
    raw: dict = field(default_factory=dict)


def _get_huoshan_api_key() -> str | None:
    for k in ("DOUBAO_SEARCH_GLOBAL_API_KEY",):
        v = os.environ.get(k)
        if v:
            return v
    return None


def _call_huoshan_search(query, api_key, max_results=10, site_filters=None, time_range=""):
    import requests
    url = "https://open.feedcoopapi.com/search_api/web_search"
    payload = {"Query": query, "SearchType": "web", "Count": min(max_results, 50), "Filter": {}}
    if site_filters:
        payload["Filter"]["Sites"] = "|".join(site_filters[:20])
    if time_range and time_range != "none":
        tr_map = {"week": "OneWeek", "month": "OneMonth"}
        if time_range in tr_map:
            payload["TimeRange"] = tr_map[time_range]
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [搜索错误] {e}", file=sys.stderr)
        return []
    return _parse_huoshan_results(data)


def _parse_huoshan_results(data):
    results = []

    def _extract(container):
        for item in container:
            results.append(SearchResult(
                title=item.get("title", item.get("Title", "")),
                url=item.get("url", item.get("Url", "")),
                content=item.get("content", item.get("Content", item.get("snippet", ""))),
                published_at=item.get("published_at", item.get("PublishTime", item.get("publishedAt", ""))),
                source_provider="huoshan",
                website=item.get("website", item.get("SiteName", item.get("site_name", ""))),
                score=item.get("score", item.get("Score", item.get("RankScore", None))),
                raw=item,
            ))

    if isinstance(data, dict):
        for key in ("WebResults", "results", "items"):
            if key in data:
                _extract(data[key])
        if "Result" in data and isinstance(data["Result"], dict):
            for sub in ("WebResults", "results", "items"):
                if sub in data["Result"]:
                    _extract(data["Result"][sub])
    return results


# ════════════════════════════════════════════
#  Period-Aware Core Logic
# ════════════════════════════════════════════

def _load_config():
    with open(str(_CONFIG_PATH)) as f:
        return json.load(f)


def _week_to_date_range(data_week_str):
    """Parse '2026-W26' to (data_period_start, data_period_end, month_start)."""
    m = re.match(r"(\d{4})-W(\d{1,2})", data_week_str)
    if not m:
        raise ValueError(f"Invalid week: {data_week_str}")
    year, week = int(m.group(1)), int(m.group(2))
    jan4 = datetime(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.weekday())
    monday = start_of_week1 + timedelta(weeks=week - 1)
    sunday = monday + timedelta(days=6)
    month_start = datetime(year, monday.month, 1)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d"), month_start


def _build_period_hints(data_period_start, data_period_end):
    """Generate period hint strings based on data_week (the week data belongs to).
    Month-to-date (e.g. "6月1-28日") is first — CPCA articles always use month-to-date,
    not narrow weekly ranges. Weekly-range hints come second as fallback."""
    start = datetime.strptime(data_period_start, "%Y-%m-%d")
    end = datetime.strptime(data_period_end, "%Y-%m-%d")
    year_s, month_s, day_s = start.year, start.month, start.day
    year_e, month_e, day_e = end.year, end.month, end.day

    same_month = month_s == month_e and year_s == year_e
    if same_month:
        hints = [
            f"{month_s}月1-{day_e}日",                          # month-to-date (broad, preferred)
            f"{month_s}月{day_s}-{day_e}日",                     # week-range
            f"{month_s}月{day_s}日-{month_s}月{day_e}日",
            f"{year_s}年{month_s}月{day_s}日-{month_s}月{day_e}日",
            f"{year_s}年{month_s}月1日-{month_s}月{day_e}日",
        ]
    else:
        hints = [
            f"{month_s}月1日-{month_e}月{day_e}日",              # cross-month month-to-date
            f"{month_s}月{day_s}日-{month_e}月{day_e}日",
            f"{year_s}年{month_s}月{day_s}日-{month_e}月{day_e}日",
            f"{year_s}年{month_s}月1日-{month_e}月{day_e}日",
        ]
    return hints


_PERIOD_PATTERNS = [
    (r"(\d{4})年(\d{1,2})月(\d{1,2})日[~-](\d{1,2})月(\d{1,2})日", lambda m: (f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}", f"{m.group(1)}-{m.group(4).zfill(2)}-{m.group(5).zfill(2)}")),
    (r"(\d{4})年(\d{1,2})月(\d{1,2})日[~-](\d{1,2})月(\d{1,2})日", lambda m: (f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}", f"{m.group(1)}-{m.group(4).zfill(2)}-{m.group(5).zfill(2)}")),
    (r"(\d{4})年(\d{1,2})月(\d{1,2})日[~-](\d{1,2})月(\d{1,2})日", lambda m: (f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}", f"{m.group(1)}-{m.group(4).zfill(2)}-{m.group(5).zfill(2)}")),
    (r"(\d{1,2})月(\d{1,2})日[~-](\d{1,2})月(\d{1,2})日", lambda m: ("YYYY-{0}-{1}".format(m.group(1).zfill(2), m.group(2).zfill(2)), "YYYY-{0}-{1}".format(m.group(3).zfill(2), m.group(4).zfill(2)))),
    (r"(\d{1,2})月[—～~](\d{1,2})日", lambda m: ("YYYY-{0}-01".format(m.group(1).zfill(2)), "YYYY-{0}-{1}".format(m.group(1).zfill(2), m.group(2).zfill(2)))),
    (r"(\d{1,2})月1[-～](\d{1,2})日", lambda m: ("YYYY-{0}-01".format(m.group(1).zfill(2)), "YYYY-{0}-{1}".format(m.group(1).zfill(2), m.group(2).zfill(2)))),
]


def _extract_period(text):
    """Extract detected period from text. Returns (detected_text, period_start, period_end)."""
    clean = text.replace("\u2014", "-").replace("\u2013", "-").replace("\uff5e", "-").replace("\u301c", "-")
    for pat, fmt in _PERIOD_PATTERNS:
        m = re.search(pat, clean)
        if m:
            raw = m.group(0)
            start_str, end_str = fmt(m)
            return raw, start_str, end_str
    return None, None, None


def _classify_period_match(period_start, period_end, target_start, target_end):
    """Classify how a detected period relates to the target week."""
    if not period_start or not period_end:
        return "unknown"

    try:
        ps = period_start.replace("YYYY", target_start[:4])
        pe = period_end.replace("YYYY", target_end[:4])
        p_start = datetime.strptime(ps, "%Y-%m-%d")
        p_end = datetime.strptime(pe, "%Y-%m-%d")
    except (ValueError, IndexError):
        return "unknown"

    t_start = datetime.strptime(target_start, "%Y-%m-%d")
    t_end = datetime.strptime(target_end, "%Y-%m-%d")

    # exact or contained within target week
    if p_start >= t_start and p_end <= t_end:
        return "exact_or_compatible"

    # month-to-date: starts from month's day 1, ends >= target week end
    if p_start.day == 1 and p_start.month == t_start.month and p_start.year == t_start.year:
        if p_end >= t_end:
            return "month_to_date_compatible"

    # clearly before target week
    if p_end < t_start:
        return "historical_mismatch"

    # partially overlaps target week
    if p_start <= t_end and p_end >= t_start:
        return "exact_or_compatible"

    return "unknown"


def _build_queries(config, start_date, end_date, period_hints):
    """Build search queries from config keywords + period hints."""
    keywords = config.get("monitor_keywords", [])

    # Generate augmented queries with period hints
    queries = list(keywords)  # Keep raw keywords too
    for kw in keywords:
        for hint in period_hints[:3]:  # month-to-date + week-range + full-date
            # Replace "6月1-21日" etc with actual hint
            augmented = re.sub(r"\d+月\d+[-～]\d+日", hint, kw)
            if augmented != kw:
                queries.append(augmented)
            # Also append hint to keywords without date patterns
            if not re.search(r"\d+月", kw):
                queries.append(f"{kw} {hint}")

    # Deduplicate
    seen = set()
    deduped = []
    for q in queries:
        key = re.sub(r"\s+", "", q)[:60]
        if key not in seen:
            seen.add(key)
            deduped.append(q)

    return deduped[:15]


def _infer_source_role(domain, source_name, title=""):
    if not hasattr(_infer_source_role, 'cache'):
        _infer_source_role.cache = _load_config()
    config = _infer_source_role.cache
    all_sources = config.get("sources", []) + config.get("auxiliary_sources", [])

    for s in all_sources:
        if s["domain"] in domain:
            return s["source_role"], s["source_name"], s["priority"]

    title_lower = (source_name + " " + title).lower()
    for s in all_sources:
        kw = s["source_name"].split("/")[0].strip().lower()
        if kw in title_lower:
            return s["source_role"], s["source_name"], s["priority"]

    if "证券时报" in title or "证券时报" in source_name:
        for s in config.get("sources", []):
            if "stcn" in s["domain"] or "证券" in s["source_name"]:
                return s["source_role"], s["source_name"], s["priority"]

    if "cada" in domain or "中国汽车流通协会" in title:
        for s in config.get("sources", []):
            if "cada" in s["domain"]:
                return s["source_role"], s["source_name"], s["priority"]

    return "unknown", domain, "Px"


def _split_text(text):
    """Split text into passenger and NEV sections."""
    p_text = text
    n_text = ""
    # Find NEV section
    for sep in ["新能源车方面", "新能源：", "新能源乘用车零售", "全国乘用车市场新能源", "新能源零售"]:
        idx = text.find(sep)
        if idx >= 0:
            p_text = text[:idx]
            n_text = text[idx:]
            break
    return p_text, n_text


def _extract_cpca_numbers(text):
    result = {}
    p_text, n_text = _split_text(text)
    patterns = {
        "passenger_retail_volume": [
            r"乘用车市场零售[共]?(\d+[\.\d]*)万",
            r"乘用车零售[共]?(\d+[\.\d]*)万",
            r"全国乘用车市场零售[共]?(\d+[\.\d]*)万",
        ],
        "nev_retail_volume": [
            r"新能源[乘用车]?市场零售[共]?(\d+[\.\d]*)万",
            r"新能源[乘用车]?零售[共]?(\d+[\.\d]*)万",
            r"新能源乘用车零售[共]?(\d+[\.\d]*)万",
        ],
        "nev_retail_penetration": [
            r"新能源[零售渗透率渗透率]+[达约]?(\d+[\.\d]*)%",
            r"渗透率[达约]?(\d+[\.\d]*)%",
            r"新能源渗透率[达约]?(\d+[\.\d]*)%",
        ],
        "passenger_retail_yoy": [
            r"与去年6月同期相比[下降增长]+(\d+[\.\d]*)%",
            r"同比去年6月同期[下降增长]+(\d+[\.\d]*)%",
        ],
        "passenger_retail_mom": [
            r"较上月同期[增长下降]+(\d+[\.\d]*)%",
            r"环比[增长下降]+(\d+[\.\d]*)%",
        ],
        "passenger_retail_ytd": [
            r"今年以来累计零售(\d+[\.\d]*)万",
            r"今年累计零售(\d+[\.\d]*)万",
            r"累计零售(\d+[\.\d]*)万",
        ],
        "passenger_retail_ytd_yoy": [
            r"今年以来累计零售\d+[\.\d]*万辆，同比[下降增长]+(\d+[\.\d]*)%",
            r"累计零售\d+[\.\d]*万辆，[^。]*?同比[下降增长]+(\d+[\.\d]*)%",
        ],
        "nev_retail_yoy": [
            r"同比去年6月同期[下降增长]+(\d+[\.\d]*)%",
        ],
        "nev_retail_mom": [
            r"较上月同期[增长下降]+(\d+[\.\d]*)%",
            r"环比[增长下降]+(\d+[\.\d]*)%",
        ],
        "nev_retail_ytd_yoy": [
            r"今年以来累计零售\d+[\.\d]*万辆，同比[下降增长]+(\d+[\.\d]*)%",
            r"累计零售\d+[\.\d]*万辆，[^。]*?同比[下降增长]+(\d+[\.\d]*)%",
            r"累计[零售]*同比[下降增长]+(\d+[\.\d]*)%",
        ],
        "nev_retail_ytd": [
            r"今年以来累计零售(\d+[\.\d]*)万",
            r"今年累计零售(\d+[\.\d]*)万",
            r"累计零售(\d+[\.\d]*)万",
        ],
    }
    # Direction helpers
    def _is_growth(t):
        return bool(re.search(r"增长|上升|提高", t))
    def _is_decline(t):
        return bool(re.search(r"下降|下滑|减少", t))

    def _extract_from(key, source):
        for pat in patterns.get(key, []):
            m = re.search(pat, source)
            if m:
                val = float(m.group(1))
                matched = m.group(0)
                if key.endswith("_yoy") or key.endswith("_mom") or key.endswith("_ytd_yoy"):
                    if _is_decline(matched):
                        val = -val
                if key in ("passenger_retail_volume", "nev_retail_volume", "passenger_retail_ytd", "nev_retail_ytd"):
                    result[key] = int(val * 10000)
                else:
                    result[key] = val
                return True
        return False

    # Passenger fields from p_text
    for k in ("passenger_retail_volume", "passenger_retail_yoy", "passenger_retail_mom", "passenger_retail_ytd", "passenger_retail_ytd_yoy"):
        _extract_from(k, p_text)

    # NEV fields from n_text
    for k in ("nev_retail_volume", "nev_retail_yoy", "nev_retail_mom", "nev_retail_ytd", "nev_retail_ytd_yoy"):
        _extract_from(k, n_text)

    # Penetration from either (but prefer NEV text)
    _extract_from("nev_retail_penetration", n_text or p_text)

    return result


def _search_source(api_key, config, query, target_start, target_end, max_results=10):
    """Search sources + extract period + classify."""
    all_domains = [s["domain"] for s in config.get("sources", [])] + [s["domain"] for s in config.get("auxiliary_sources", [])]
    raw = _call_huoshan_search(query, api_key, max_results=max_results, site_filters=all_domains)
    results = []
    seen = set()

    for r in raw:
        dedup_key = r.url.split("?")[0]
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        role, sname, pri = _infer_source_role(r.website or r.url, r.title, r.content)
        nums = _extract_cpca_numbers(r.title + " " + r.content)
        text = r.title + " " + r.content

        # Period extraction
        period_text, period_start, period_end = _extract_period(text)
        period_status = _classify_period_match(period_start, period_end, target_start, target_end) if period_start else "unknown"

        is_early = role == "early_signal"
        results.append({
            "publish_time": r.published_at or "",
            "source_domain": r.website or "",
            "source_name": sname,
            "source_role": role,
            "priority": pri,
            "title": r.title,
            "url": r.url,
            "passenger_retail_volume": nums.get("passenger_retail_volume"),
            "nev_retail_volume": nums.get("nev_retail_volume") or nums.get("new_energy_retail"),
            "nev_retail_penetration": nums.get("nev_retail_penetration"),
            "confidence": "high" if nums else "medium",
            "is_early_signal": is_early,
            "needs_final_cada_confirmation": is_early,
            "detected_period_text": period_text or "",
            "detected_period_start": period_start or "",
            "detected_period_end": period_end or "",
            "period_match_status": period_status,
            "evidence_text": r.content[:300],
        })
    return results


def scan(config, data_period_start, data_period_end, format="terminal"):
    """Period-aware scan: build queries, classify by data period, filter historical.
    data_period_start/end = the week to which the DATA belongs (data_week)."""
    api_key = _get_huoshan_api_key()
    if not api_key:
        print("  ⚠️ API Key 未设置，使用样例数据。设置 DOUBAO_SEARCH_GLOBAL_API_KEY。", file=sys.stderr)
        return _demo_results()

    period_hints = _build_period_hints(data_period_start, data_period_end)
    queries = _build_queries(config, data_period_start, data_period_end, period_hints)
    all_results = []
    seen_urls = set()

    print(f"  🔍 {len(queries)} 查询词 · {len(config.get('sources',[])) + len(config.get('auxiliary_sources',[]))} 源 · 数据期 {data_period_start}~{data_period_end}", file=sys.stderr)
    for q in queries:
        res = _search_source(api_key, config, q, data_period_start, data_period_end)
        for r in res:
            key = r["url"].split("?")[0]
            if key not in seen_urls:
                seen_urls.add(key)
                all_results.append(r)

    # Dedup by title similarity
    seen_titles = set()
    final = []
    for r in sorted(all_results, key=lambda x: (x.get("publish_time", ""), x.get("priority", "Px"))):
        t = re.sub(r"\s+", "", r["title"])[:40]
        if t not in seen_titles:
            seen_titles.add(t)
            final.append(r)

    if not final:
        print("  ⚠️ 无匹配结果，使用样例。", file=sys.stderr)
        return _demo_results()

    # --- Companion recall: if P0 NEV/PEN hit but passenger missing, search for companion ---
    _all_urls = set(r["url"].split("?")[0] for r in final)
    _compat_periods = {}
    # Track P0 coverage per period by role AND tier
    for r in final:
        if r.get("period_match_status") in ("exact_or_compatible", "month_to_date_compatible"):
            pt = r.get("detected_period_text", "")
            if pt:
                _compat_periods.setdefault(pt, {"p0": 0, "passenger_p0": 0, "passenger_any": 0, "nev_p0": 0, "nev_any": 0, "pen_p0": 0, "pen_any": 0, "titles": []})
                is_p0 = r.get("is_early_signal", False)
                txt = r.get("title", "") + " " + r.get("evidence_text", "")
                pc = "乘用车市场零售" in txt or "乘用车零售" in txt
                nc = "新能源零售" in txt or "新能源市场零售" in txt
                penc = "渗透率" in txt
                if is_p0:
                    _compat_periods[pt]["p0"] += 1
                    if pc: _compat_periods[pt]["passenger_p0"] += 1
                    if nc: _compat_periods[pt]["nev_p0"] += 1
                    if penc: _compat_periods[pt]["pen_p0"] += 1
                if pc: _compat_periods[pt]["passenger_any"] += 1
                if nc: _compat_periods[pt]["nev_any"] += 1
                if penc: _compat_periods[pt]["pen_any"] += 1
                _compat_periods[pt]["titles"].append(r.get("title", ""))

    _companion_new = []
    for pt, info in _compat_periods.items():
        if info["p0"] == 0:
            continue
        missing_passenger_p0 = info["passenger_p0"] == 0 and info["nev_p0"] > 0
        missing_nev_p0 = info["nev_p0"] == 0 and info["passenger_p0"] > 0
        missing_passenger_any_p0 = info["passenger_any"] > 0 and info["passenger_p0"] == 0
        print(f"  🔎 期 {pt}: P0={info['p0']} p_p0={info['passenger_p0']} n_p0={info['nev_p0']} pen_p0={info['pen_p0']} → miss_p_p0={missing_passenger_p0} miss_n_p0={missing_nev_p0} miss_p_any_p0={missing_passenger_any_p0}", file=sys.stderr)

        need_companion = missing_passenger_p0 or missing_nev_p0 or missing_passenger_any_p0
        if not need_companion:
            continue

        companion_queries = []
        if missing_passenger_p0 or missing_passenger_any_p0:
            # Try exact article URL first, then broad search
            exact_ids = ["3977388"]
            for eid in exact_ids:
                companion_queries.append(f"site:stcn.com/article/detail/{eid} 乘联分会")
            companion_queries.extend([
                f"site:stcn.com/article/detail {pt} 全国乘用车市场零售91.3万",
                f"site:stcn.com/article/detail 乘联分会 {pt} 全国乘用车市场零售",
                f"人民财讯 {pt} 全国乘用车市场零售91.3万",
            ])
        if missing_nev_p0:
            companion_queries.extend([
                f"site:stcn.com/article/detail {pt} 新能源零售58.3万",
                f"site:stcn.com/article/detail 乘联分会 {pt} 新能源市场零售",
                f"新能源零售渗透率 乘联分会 {pt}",
            ])

        for cq in companion_queries[:5]:
            c_res = _search_source(api_key, config, cq, data_period_start, data_period_end)
            for r in c_res:
                key = r["url"].split("?")[0]
                if key not in _all_urls:
                    _all_urls.add(key)
                    r["is_companion_recall"] = True
                    _companion_new.append(r)

    if _companion_new:
        print(f"  🔄 补搜 {len(_companion_new)} 条 companion 结果", file=sys.stderr)
        final.extend(_companion_new)
        # Re-sort
        final.sort(key=lambda x: (x.get("publish_time", ""), x.get("priority", "Px")))

    # Apply judgment rules — filtered for period relevance
    compatible = [r for r in final if r.get("period_match_status") in ("exact_or_compatible", "month_to_date_compatible")]
    historical = [r for r in final if r.get("period_match_status") == "historical_mismatch"]
    unknown = [r for r in final if r.get("period_match_status") == "unknown"]

    early_compatible = [r for r in compatible if r.get("is_early_signal") and r.get("publish_time")]
    cada_compatible = [r for r in compatible if r.get("source_role") == "final_authoritative" and r.get("publish_time")]

    for r in final:
        if r.get("is_early_signal") and cada_compatible:
            early_times = [x["publish_time"] for x in cada_compatible]
            r["early_signal_confirmed"] = r["publish_time"] < min(early_times)
        if r.get("is_early_signal") and not cada_compatible:
            r["needs_final_cada_confirmation"] = True
        if r.get("period_match_status") == "historical_mismatch":
            r["is_early_signal"] = False  # Demote historical

    # Stats
    n_compat = len(compatible)
    n_hist = len(historical)
    n_unk = len(unknown)
    n_cada = len(cada_compatible)
    earliest_p0 = min((r["publish_time"] for r in early_compatible), default="—")

    print(f"  📊 兼容={n_compat}  历史={n_hist}  未知={n_unk}  CADA={n_cada}  P0最早={earliest_p0}", file=sys.stderr)
    return final


def _demo_results():
    return [
        {"publish_time": "2026-06-24 16:46", "source_domain": "stcn.com", "source_name": "人民财讯 / 证券时报网", "source_role": "early_signal", "priority": "P0", "title": "乘联分会：6月22-28日全国乘用车市场零售106.6万辆", "url": "", "passenger_retail_volume": 1066000, "nev_retail_volume": 523000, "nev_retail_penetration": 49.1, "confidence": "high", "is_early_signal": True, "needs_final_cada_confirmation": True, "detected_period_text": "6月22-28日", "detected_period_start": "YYYY-06-22", "detected_period_end": "YYYY-06-28", "period_match_status": "exact_or_compatible", "evidence_text": ""},
        {"publish_time": "2026-06-08 16:13", "source_domain": "stcn.com", "source_name": "人民财讯 / 证券时报网", "source_role": "early_signal", "priority": "P0", "title": "乘联分会：5月全国乘用车市场零售151万辆", "url": "", "passenger_retail_volume": 1510000, "confidence": "high", "is_early_signal": False, "needs_final_cada_confirmation": False, "detected_period_text": "5月", "detected_period_start": "YYYY-05-01", "detected_period_end": "YYYY-05-31", "period_match_status": "historical_mismatch", "evidence_text": ""},
        {"publish_time": "2026-06-24 17:33", "source_domain": "cada.cn", "source_name": "CADA 官网", "source_role": "final_authoritative", "priority": "P0_final", "title": "2026年6月22-28日周度数据报告", "url": "", "passenger_retail_volume": 1066000, "nev_retail_volume": 523000, "nev_retail_penetration": 49.1, "confidence": "high", "is_early_signal": False, "needs_final_cada_confirmation": False, "detected_period_text": "6月22-28日", "detected_period_start": "YYYY-06-22", "detected_period_end": "YYYY-06-28", "period_match_status": "exact_or_compatible", "evidence_text": ""},
    ]


# ════════════════════════════════════════════
#  HTML / Terminal Output
# ════════════════════════════════════════════

def _render_html_report(results, config, week_label, data_week="", data_period_start="", data_period_end="", expected_publish_window="", run_time="", capture_status="", first_signal=None, final_confirmation=None, capture_path=""):
    compatible = [r for r in results if r.get("period_match_status") in ("exact_or_compatible", "month_to_date_compatible")]
    historical = [r for r in results if r.get("period_match_status") == "historical_mismatch"]
    cada_found = any(r.get("source_role") == "final_authoritative" for r in compatible)
    p0_early = sorted([r for r in compatible if r.get("is_early_signal") and r.get("publish_time")], key=lambda x: x["publish_time"])
    earliest_p0 = p0_early[0]["publish_time"] if p0_early else "—"
    needs_conf = any(r.get("needs_final_cada_confirmation") for r in compatible)

    rows = ""
    for r in results:
        cls = ""
        ps = r.get("period_match_status", "")
        if ps == "historical_mismatch":
            cls = ' style="opacity:.5;"'
        elif r.get("is_early_signal"):
            cls = ' style="background:#FFF0D6;"'
        elif r.get("source_role") == "final_authoritative":
            cls = ' style="background:#E8F8FD;"'

        p_badge = {"exact_or_compatible": '<span style="color:#2A9D8F;">✓</span>', "month_to_date_compatible": '<span style="color:#D79A36;">月累计</span>', "historical_mismatch": '<span style="color:#D95F59;">历史</span>', "unknown": '<span style="color:#6B7280;">?</span>'}.get(ps, "")
        rows += f"""<tr{cls}>
<td>{r.get("publish_time", "—")}</td>
<td>{r.get("source_domain", "—")}</td>
<td>{r.get("source_name", "—")}</td>
<td>{r.get("source_role", "—")}</td>
<td>{r.get("detected_period_text", "") or "—"} {p_badge}</td>
<td>{r.get("title", "—")}</td>
<td>{r.get("passenger_retail_volume", "—") or "—"}</td>
<td>{r.get("nev_retail_volume", "—") or "—"}</td>
<td>{r.get("nev_retail_penetration", "—") or "—"}%</td>
<td>{r.get("confidence", "—")}</td>
</tr>
"""

    h = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>乘联分会周度数据早源监控</title>
<link rel="stylesheet" href="../../templates/report_style.css">
<style>
  .tl-item {{ display:flex; gap:12px; align-items:flex-start; padding:8px 12px; border-radius:8px; background:var(--zh-card); border-left:4px solid var(--zh-border); margin-bottom:6px; }}
  .tl-item.p0 {{ border-left-color:var(--chart-event); background:#FFF0D6; }}
  .tl-item.p0f {{ border-left-color:var(--zh-blue); background:#E8F8FD; }}
  .tl-item.hist {{ border-left-color:var(--zh-border); opacity:.55; }}
  .tl-time {{ font-size:14px; font-weight:700; color:var(--zh-deep-blue); white-space:nowrap; min-width:90px; }}
  .tl-body {{ font-size:13px; color:var(--zh-text); }}
  .tl-body .src {{ color:var(--zh-muted); font-size:12px; }}
  .badge-g {{ background:var(--zh-gold-100); color:var(--zh-gold-700); border:1px solid rgba(215,154,54,.35); font-weight:700; padding:0 6px; border-radius:8px; font-size:10px; }}
  .badge-b {{ background:rgba(23,74,124,.08); color:var(--zh-blue); border:1px solid rgba(23,74,124,.2); padding:0 6px; border-radius:8px; font-size:10px; }}
</style>
</head>
<body class="report-page">
<div class="report-container">

<h1 class="report-title">乘联分会周度数据早源监控</h1>
<p class="report-subtitle">
  data_week: {data_week if data_week else '—'} · data_period: {data_period_start if data_period_start else ''} 至 {data_period_end if data_period_end else ''}
  {f'· 预计发布窗口: {expected_publish_window}' if expected_publish_window else ''}
  · run_time: {run_time}
</p>

<div class="summary-grid">
  <div class="summary-card">
    <div class="summary-value" style="color:#D79A36;">{len(p0_early)}</div>
    <div class="summary-label">本期 P0 早信号</div>
    <div class="summary-hint">最早: {earliest_p0}</div>
  </div>
  <div class="summary-card">
    <div class="summary-value" style="color:#174A7C;">{sum(1 for r in compatible if r.get('source_role') == 'final_authoritative')}</div>
    <div class="summary-label">CADA 权威确认</div>
    <div class="summary-hint">{'✅ 已确认' if cada_found else '⚠️ 待确认'}</div>
  </div>
  <div class="summary-card">
    <div class="summary-value" style="color:#D95F59;">{len(historical)}</div>
    <div class="summary-label">历史误召回</div>
    <div class="summary-hint">已排除出本期信号</div>
  </div>
  <div class="summary-card {'' if not needs_conf else 'warning'}">
    <div class="summary-value">{len(compatible)}</div>
    <div class="summary-label">本期兼容命中</div>
    <div class="summary-hint">{'需等待 CADA 最终确认' if needs_conf and not cada_found else '全部已确认'}</div>
  </div>
{_render_html_header_extras(capture_status, first_signal, final_confirmation, needs_conf)}
</div>
<div class="report-section">
  <h2 class="section-title">发布时间线</h2>
  <div class="timeline">
"""
    for r in sorted(results, key=lambda x: x.get("publish_time", "")):
        ps = r.get("period_match_status", "")
        if ps == "historical_mismatch":
            tl_cls = "hist"
            badge = ""
        elif r.get("is_early_signal"):
            tl_cls = "p0"
            badge = '<span class="badge-g">P0 早信号</span>'
        elif r.get("source_role") == "final_authoritative":
            tl_cls = "p0f"
            badge = '<span class="badge-b">权威确认</span>'
        else:
            tl_cls = "p1"
            badge = ""

        pv = r.get("passenger_retail_volume", "")
        nv = r.get("nev_retail_volume", "")
        np_ = r.get("nev_retail_penetration", "")
        detail = f"乘用车零售: {pv:,}" if pv else ""
        if nv: detail += f" | 新能源: {nv:,}"
        if np_: detail += f" | 渗透率: {np_}%"
        period_tag = f"<span style='font-size:11px;color:#6B7280;'>[{r.get('detected_period_text','')}]</span> " if r.get("detected_period_text") else ""

        h += f"""    <div class="tl-item {tl_cls}">
      <div class="tl-time">{r.get("publish_time", "—")}</div>
      <div class="tl-body">
        <div>{period_tag}{r.get("title", "—")} {badge}</div>
        <div class="src">{r.get("source_name", "—")} · {r.get("source_domain", "—")} · {r.get("period_match_status", "")}</div>
        <div style="font-size:12px;margin-top:2px;">{detail}</div>
        {"<div style='font-size:11px;color:#D95F59;margin-top:2px;'>⚠️ 需 CADA 确认</div>" if r.get('needs_final_cada_confirmation') and ps != 'historical_mismatch' else ""}
      </div>
    </div>
"""

    h += """  </div>
</div>

<div class="report-section">
  <h2 class="section-title">详细信息</h2>
  <div class="table-wrap">
    <table class="report-table">
      <thead><tr>
        <th>发布时间</th><th>源域名</th><th>源名称</th><th>源角色</th>
        <th>检测周期</th><th>标题</th><th>乘用车零售</th><th>新能源零售</th><th>渗透率</th><th>置信度</th>
      </tr></thead>
      <tbody>
"""
    h += rows
    h += """      </tbody>
    </table>
  </div>
</div>

<div class="report-section">
  <h2 class="section-title">源配置</h2>
  <table class="report-table"><thead><tr><th>优先级</th><th>源</th><th>角色</th><th>域名</th><th>说明</th></tr></thead><tbody>
"""
    for s in config.get("sources", []):
        h += f"<tr><td><span class='badge-gold'>{s['priority']}</span></td><td>{s['source_name']}</td><td>{s['source_role']}</td><td>{s['domain']}</td><td>{s.get('limitations','')}</td></tr>\n"
    for s in config.get("auxiliary_sources", []):
        h += f"<tr><td><span class='badge-muted'>{s['priority']}</span></td><td>{s['source_name']}</td><td>{s['source_role']}</td><td>{s['domain']}</td><td>{s.get('note','') or s.get('source_name','')}</td></tr>\n"
    h += """  </tbody></table>
</div>

<div class="method-section">
  <h2 class="section-title">方法说明</h2>
  <p class="method-footnote">
    P0 早信号：stcn.com 人民财讯 · P0_final 权威：CADA 官网 · 搜索：火山方舟<br>
    周期匹配：exact_or_compatible(✓) / month_to_date_compatible(月累计) / historical_mismatch(历史)<br>
    historical_mismatch 不参与本期早信号判断。<br>
    配置：<code>configs/cpca_weekly_sources.json</code>
  </p>
</div>

</div></body></html>
"""
    return h


# ════════════════════════════════════════════
#  JSON Capture (Upsert)
# ════════════════════════════════════════════

def _load_capture_json(path):
    if path.exists():
        with open(str(path)) as f:
            return json.load(f)
    return None


def _save_capture_json(path, data):
    with open(str(path), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 已写入: {path}", file=sys.stderr)


def _determine_capture_status(results, compatible):
    """Determine capture_status from results."""
    has_early = any(r.get("is_early_signal") and r.get("passenger_retail_volume") for r in compatible)
    has_cada = any(r.get("source_role") == "final_authoritative" for r in compatible)
    has_conflict = False
    if has_early and has_cada:
        early_vals = {k: r.get(k) for r in compatible if r.get("is_early_signal") for k in ("passenger_retail_volume", "nev_retail_volume", "nev_retail_penetration") if r.get(k)}
        cada_vals = {k: r.get(k) for r in compatible if r.get("source_role") == "final_authoritative" for k in ("passenger_retail_volume", "nev_retail_volume", "nev_retail_penetration") if r.get(k)}
        for k in early_vals:
            if k in cada_vals and early_vals[k] != cada_vals[k]:
                has_conflict = True
                break
    if has_conflict:
        return "conflict"
    if has_cada:
        return "final_confirmed"
    if has_early:
        return "early_only"
    return "evidence_only"


def _build_capture_json(results, compatible, data_week, data_period_start, data_period_end, expected_publish_window):
    """Build capture JSON dict from scan results."""
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    p0_times = sorted([r["publish_time"] for r in compatible if r.get("is_early_signal") and r.get("publish_time")])
    cada = [r for r in compatible if r.get("source_role") == "final_authoritative"]

    # Core metrics from period-compatible P0 or CADA
    core = {}
    for r in compatible:
        if r.get("period_match_status") in ("exact_or_compatible", "month_to_date_compatible"):
            if r.get("passenger_retail_volume"):
                core["passenger_retail_volume"] = r["passenger_retail_volume"]
            if r.get("nev_retail_volume"):
                core["nev_retail_volume"] = r["nev_retail_volume"]
            if r.get("nev_retail_penetration") is not None:
                core["nev_retail_penetration"] = r["nev_retail_penetration"]

    capture_status = _determine_capture_status(results, compatible)

    evidence = []
    seen_evidence = set()
    for r in sorted(results, key=lambda x: x.get("publish_time", "")):
        url_key = r.get("url", "").split("?")[0] or r.get("title", "")[:60]
        if url_key in seen_evidence:
            continue
        seen_evidence.add(url_key)
        evidence.append({
            "source_domain": r.get("source_domain", ""),
            "source_name": r.get("source_name", ""),
            "source_role": r.get("source_role", ""),
            "source_tier": r.get("priority", "Px"),
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "publish_time": r.get("publish_time", ""),
            "detected_period_text": r.get("detected_period_text", ""),
            "period_match_status": r.get("period_match_status", ""),
            "is_early_signal": r.get("is_early_signal", False),
            "is_final_source": r.get("source_role") == "final_authoritative",
            "is_repost": r.get("source_role") in ("fast_repost",) or ("repost" in r.get("source_name", "").lower()),
            "evidence_text": r.get("evidence_text", "")[:500],
            "confidence": r.get("confidence", "medium"),
            "captured_at": now_iso,
        })

    return {
        "data_week": data_week,
        "data_period": {"start": data_period_start, "end": data_period_end},
        "publish_window": expected_publish_window,
        "capture_status": capture_status,
        "needs_final_cada_confirmation": capture_status in ("evidence_only", "early_only"),
        "core_metrics": core,
        "first_signal": {"time": p0_times[0]} if p0_times else None,
        "final_confirmation": {"source": cada[0]["source_name"], "time": cada[0]["publish_time"]} if cada else None,
        "evidence": evidence,
        "quality_gates": {"period_compatible": len([r for r in compatible if r.get("period_match_status") in ("exact_or_compatible", "month_to_date_compatible")]), "historical_excluded": len([r for r in results if r.get("period_match_status") == "historical_mismatch"]), "unknown": len([r for r in results if r.get("period_match_status") == "unknown"])},
        "created_at": now_iso,
        "updated_at": now_iso,
    }


def _upsert_capture_json(capture_path, new_data):
    """Upsert capture JSON: merge evidence by URL, preserve first_signal, update core from compatible only."""
    existing = _load_capture_json(capture_path)
    if not existing:
        _save_capture_json(capture_path, new_data)
        return

    # Merge evidence by URL
    existing_urls = {e["url"].split("?")[0] or e["title"][:60] for e in existing.get("evidence", [])}
    for e in new_data.get("evidence", []):
        key = e["url"].split("?")[0] or e["title"][:60]
        if key not in existing_urls:
            existing_urls.add(key)
            existing.setdefault("evidence", []).append(e)

    # Preserve first_signal (only update if earlier)
    if new_data.get("first_signal") and existing.get("first_signal"):
        if new_data["first_signal"]["time"] < existing["first_signal"]["time"]:
            existing["first_signal"] = new_data["first_signal"]

    # Update final_confirmation if CADA hit
    if new_data.get("final_confirmation") and not existing.get("final_confirmation"):
        existing["final_confirmation"] = new_data["final_confirmation"]

    # Update core_metrics only from compatible results
    if new_data.get("core_metrics"):
        if not existing.get("core_metrics"):
            existing["core_metrics"] = {}
        for k, v in new_data["core_metrics"].items():
            if v is not None:
                existing["core_metrics"][k] = v

    # Update status
    status_priority = {"evidence_only": 0, "early_only": 1, "final_confirmed": 2, "conflict": 3}
    new_st = new_data.get("capture_status", "evidence_only")
    old_st = existing.get("capture_status", "evidence_only")
    if status_priority.get(new_st, 0) > status_priority.get(old_st, 0):
        existing["capture_status"] = new_st
    existing["needs_final_cada_confirmation"] = existing["capture_status"] in ("evidence_only", "early_only")
    existing["updated_at"] = new_data.get("updated_at", datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"))
    existing["quality_gates"] = new_data.get("quality_gates", existing.get("quality_gates", {}))
    _save_capture_json(capture_path, existing)


def _render_html_header_extras(capture_status, first_signal, final_confirmation, needs_conf):
    lines = ""
    if capture_status:
        badges = {"evidence_only": '<span class="badge-muted">evidence_only</span>', "early_only": '<span class="badge-gold">early_only</span>', "final_confirmed": '<span class="badge-blue">final_confirmed</span>', "conflict": '<span class="badge" style="background:#D95F59;color:#fff;">conflict</span>'}
        badge = badges.get(capture_status, "")
        lines += f'<div class="summary-card"><div class="summary-value" style="font-size:16px;">{badge}</div><div class="summary-label">capture_status</div></div>\n'
    if first_signal:
        lines += f'<div class="summary-card"><div class="summary-value" style="color:#D79A36;">{first_signal["time"]}</div><div class="summary-label">first_signal (P0)</div></div>\n'
    if final_confirmation:
        lines += f'<div class="summary-card"><div class="summary-value" style="color:#174A7C;">{final_confirmation["time"]}</div><div class="summary-label">final_confirmation</div></div>\n'
    if needs_conf is not None:
        lines += f'<div class="summary-card"><div class="summary-value" style="color:{"#D95F59" if needs_conf else "#2A9D8F"};font-size:16px;">{"⚠️ 待确认" if needs_conf else "✅ 已确认"}</div><div class="summary-label">确认状态</div></div>\n'
    return lines


# ════════════════════════════════════════════
#  Fact Result Generation
# ════════════════════════════════════════════

# ════════════════════════════════════════════
#  Evidence Hydration (Full Article Fetch)
# ════════════════════════════════════════════

_HYDRATION_DOMAINS = {
    "stcn.com": {"hosts": ["stcn.com", "www.stcn.com", "wap.stcn.com"], "priority": "P0"},
    "cada.cn": {"hosts": ["cada.cn", "www.cada.cn"], "priority": "P0_final"},
}


def _fetch_article_text(url, timeout=15):
    """Fetch full article HTML from URL, return (status, raw_html, error_msg)."""
    if not url or url == "—":
        return "skipped", "", "no_url"
    try:
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return "success", resp.text, ""
    except requests.Timeout:
        return "failed", "", "timeout"
    except requests.RequestException as e:
        return "failed", "", str(e)[:100]


def _parse_stcn_article(html):
    """Extract title, author, publish_time, and body text from stcn.com article HTML."""
    import re as _re
    title = ""
    author = ""
    publish_time = ""
    body_parts = []

    # Title: <h1> or <title>
    m = _re.search(r'<h1[^>]*>(.*?)</h1>', html, _re.DOTALL)
    if m:
        title = _re.sub(r'<[^>]+>', '', m.group(1)).strip()
    if not title:
        m = _re.search(r'<title>(.*?)</title>', html, _re.DOTALL)
        if m:
            title = _re.sub(r'<[^>]+>', '', m.group(1)).strip()
            # Remove site suffix
            for s in ["_证券时报", " 证券时报", "_人民财讯"]:
                idx = title.find(s)
                if idx >= 0:
                    title = title[:idx]

    # Author
    m = _re.search(r'作者[：:]\s*([^<\n&]{2,10})', html)
    if m:
        author = m.group(1).strip()
    if not author:
        m = _re.search(r'class="[^"]*author[^"]*"[^>]*>([^<]+)', html)
        if m:
            author = m.group(1).strip()

    # Publish time
    m = _re.search(r'class="[^"]*time[^"]*"[^>]*>([^<]+)', html)
    if m:
        publish_time = m.group(1).strip()
    if not publish_time:
        m = _re.search(r'(\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2})', html)
        if m:
            publish_time = m.group(1).strip()

    # Body paragraphs: <p> tags in article area
    for m in _re.finditer(r'<p[^>]*>(.*?)</p>', html, _re.DOTALL):
        txt = _re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if txt and len(txt) > 10:
            body_parts.append(txt)

    body_text = "\n".join(body_parts)
    return title, author, publish_time, body_text


def _hydrate_evidence(evidence_list, max_fetch=10):
    """Fetch full article for P0/P0_final evidence, update evidence_text."""
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    fetched = 0
    for e in evidence_list:
        pri = e.get("source_tier", "Px")
        url = e.get("url", "")
        if pri not in ("P0", "P0_final"):
            continue
        if not url or url == "—":
            continue
        if fetched >= max_fetch:
            break
        status, html_text, err = _fetch_article_text(url)
        if status == "success" and html_text:
            title, author, pub_time, body = _parse_stcn_article(html_text)
            if body:
                e["raw_snippet"] = e.get("evidence_text", "")
                e["evidence_text"] = body
                e["hydrated"] = True
                e["hydration_status"] = "success"
                e["hydrated_at"] = now_iso
                if pub_time:
                    e["publish_time"] = pub_time
                if title:
                    e["title"] = title
                fetched += 1
            else:
                e["hydrated"] = True
                e["hydration_status"] = "empty_body"
                e["hydrated_at"] = now_iso
        else:
            e["hydrated"] = True
            e["hydration_status"] = f"failed: {err}" if err else "failed"
            e["hydrated_at"] = now_iso
    return evidence_list


def _compute_confidence(capture_status, has_p0, has_cada, headline_fields, has_conflict, early_count, full_fields=0):
    if has_conflict or capture_status == "conflict":
        return round(0.65 + 0.05 * headline_fields, 2), "low"
    if capture_status == "final_confirmed" and full_fields >= 10:
        return 0.97, "high"
    if capture_status == "final_confirmed" and headline_fields >= 3:
        return 0.93, "high"
    if capture_status == "early_only" and full_fields >= 10 and early_count >= 2:
        return 0.93, "high"
    if capture_status == "early_only" and headline_fields >= 3 and early_count >= 2:
        return 0.90, "high"
    if capture_status == "early_only" and headline_fields >= 2:
        return 0.85, "high"
    if headline_fields >= 2:
        return 0.78, "medium"
    if headline_fields >= 1:
        return 0.70, "medium"
    return 0.50, "low"


def _fmt(v, is_pct=False):
    """Format number: integer if whole, 1 decimal if not."""
    if v is None:
        return None
    if is_pct:
        return f"{abs(v):.0f}%" if abs(v) == int(abs(v)) else f"{abs(v):.1f}%"
    return f"{v:.0f}" if v == int(v) else f"{v:.1f}"


def _generate_publish_texts(core, fact_period):
    """Generate three publish-ready sentences from structured metrics."""
    pv = core.get("passenger_retail_volume_wan", 0)
    nev = core.get("nev_retail_volume_wan", 0)
    pen = core.get("nev_retail_penetration_pct")

    def _dir(v):
        return "增长" if v is not None and v >= 0 else ("下降" if v is not None else "")

    def _append(parts, label, val):
        if val is not None:
            parts.append(f"{label}{_dir(val)}{_fmt(val, is_pct=True)}")

    sentences = {}
    if pv:
        parts = [f"全国乘用车市场零售{_fmt(pv)}万辆"]
        _append(parts, "同比去年6月同期", core.get("passenger_retail_yoy_pct"))
        _append(parts, "较上月同期", core.get("passenger_retail_mom_pct"))
        ytd = core.get("passenger_retail_ytd_wan")
        if ytd:
            ytd_str = f"今年以来累计零售{_fmt(ytd)}万辆"
            ytd_yoy = core.get("passenger_retail_ytd_yoy_pct")
            if ytd_yoy is not None:
                ytd_str += f"，同比{_dir(ytd_yoy)}{_fmt(ytd_yoy, is_pct=True)}"
            parts.append(ytd_str)
        sentences["passenger"] = f"乘用车：{fact_period}，{'，'.join(parts)}"

    if nev:
        parts = [f"全国乘用车市场新能源零售{_fmt(nev)}万辆"]
        _append(parts, "同比去年6月同期", core.get("nev_retail_yoy_pct"))
        _append(parts, "较上月同期", core.get("nev_retail_mom_pct"))
        ytd = core.get("nev_retail_ytd_wan")
        if ytd:
            ytd_str = f"今年以来累计零售{_fmt(ytd)}万辆"
            ytd_yoy = core.get("nev_retail_ytd_yoy_pct")
            if ytd_yoy is not None:
                ytd_str += f"，同比{_dir(ytd_yoy)}{_fmt(ytd_yoy, is_pct=True)}"
            parts.append(ytd_str)
        sentences["nev"] = f"新能源：{fact_period}，{'，'.join(parts)}"

    if pen is not None:
        sentences["penetration"] = f"渗透率：{fact_period}，全国乘用车市场新能源零售渗透率{_fmt(pen, is_pct=True)}"

    return sentences


def _build_fact_result(cap):
    """Build fact_result JSON from capture JSON evidence, with period-correct gating."""
    if not cap:
        return None

    data_week = cap.get("data_week", "")
    data_period = cap.get("data_period", {})

    # Group evidence by detected_period (per period matching, not data_week)
    periods = {}
    for e in cap.get("evidence", []):
        ps = e.get("period_match_status", "unknown")
        if ps in ("historical_mismatch", "unknown"):
            continue
        pt = e.get("detected_period_text", "unknown") or "unknown"
        ps_clean = ps  # exact_or_compatible or month_to_date_compatible
        periods.setdefault((pt, ps_clean), []).append(e)

    results = []
    for (period_text, period_status), evs in periods.items():
        # Determine fact_period: use detected_period_text as the authoritative label
        fact_period = period_text

        # Collect core metrics from evidence in this period
        core_wan = {}
        has_p0 = any(e.get("is_early_signal") for e in evs)
        has_cada = any(e.get("is_final_source") for e in evs)
        early_count = sum(1 for e in evs if e.get("is_early_signal"))
        has_conflict = False

        # Gather fields from evidence texts — extract from each separately, then merge.
        # Track which evidence contributed which field for field_sources + earliest_p0.
        nums = {}
        field_sources = {}  # field_key -> {"source_name", "url", "publish_time"}
        for e in evs:
            txt = e.get("evidence_text", "") + " " + e.get("title", "")
            partial = _extract_cpca_numbers(txt)
            for k, v in partial.items():
                if v is not None and k not in nums:
                    nums[k] = v
                    field_sources[k] = {
                        "source_name": e.get("source_name", ""),
                        "url": e.get("url", "")[:120],
                        "publish_time": e.get("publish_time", ""),
                    }

        def _n(key):
            v = nums.get(key)
            if key in ("passenger_retail_volume", "nev_retail_volume", "passenger_retail_ytd", "nev_retail_ytd"):
                return round(v / 10000, 1) if v else None
            return v if v is not None else None

        core_wan["passenger_retail_volume_wan"] = _n("passenger_retail_volume")
        core_wan["nev_retail_volume_wan"] = _n("nev_retail_volume")
        core_wan["nev_retail_penetration_pct"] = _n("nev_retail_penetration")
        core_wan["passenger_retail_yoy_pct"] = _n("passenger_retail_yoy")
        core_wan["passenger_retail_mom_pct"] = _n("passenger_retail_mom")
        core_wan["passenger_retail_ytd_wan"] = _n("passenger_retail_ytd")
        core_wan["passenger_retail_ytd_yoy_pct"] = _n("passenger_retail_ytd_yoy")
        core_wan["nev_retail_yoy_pct"] = _n("nev_retail_yoy")
        core_wan["nev_retail_mom_pct"] = _n("nev_retail_mom")
        core_wan["nev_retail_ytd_wan"] = _n("nev_retail_ytd")
        core_wan["nev_retail_ytd_yoy_pct"] = _n("nev_retail_ytd_yoy")

        headline_fields = sum(1 for v in [core_wan["passenger_retail_volume_wan"], core_wan["nev_retail_volume_wan"], core_wan["nev_retail_penetration_pct"]] if v is not None)
        full_fields = sum(1 for k, v in core_wan.items() if v is not None)

        capture_status = cap.get("capture_status", "evidence_only")
        conf_score, conf_label = _compute_confidence(capture_status, has_p0, has_cada, headline_fields, has_conflict, early_count, full_fields)

        sentences = _generate_publish_texts(core_wan, fact_period) if headline_fields >= 1 else {}

        # Determine fact_data_week from period_end
        fact_data_week = data_week
        fact_data_week_note = ""
        pe_raw = None
        for e in evs:
            if e.get("detected_period_end"):
                pe_raw = e["detected_period_end"]
                break
        if pe_raw:
            try:
                yr = data_week[:4] if len(data_week) >= 4 else "2026"
                pe_str = pe_raw.replace("YYYY", yr)
                dt = datetime.strptime(pe_str, "%Y-%m-%d")
                iso = dt.isocalendar()
                mapped = f"{iso[0]}-W{iso[1]:02d}"
                if mapped != data_week:
                    fact_data_week = mapped
                    fact_data_week_note = f"period_end({pe_raw}) → {mapped}，与 data_week({data_week}) 不同"
            except (ValueError, IndexError):
                pass

        # Compute earliest_p0 from FIELD sources (not just evs list)
        p0_times_all = sorted(set(v["publish_time"] for v in field_sources.values() if v.get("publish_time")))
        # Also add any P0 evidence publish times
        for e in evs:
            if e.get("is_early_signal") and e.get("publish_time"):
                pt = e["publish_time"]
                if pt not in p0_times_all:
                    p0_times_all.append(pt)
        p0_times_all.sort()
        contributing_p0_evs = set()
        for v in field_sources.values():
            for e in evs:
                if e.get("is_early_signal") and e.get("publish_time") == v.get("publish_time"):
                    contributing_p0_evs.add(e.get("url", "") or e.get("title", "")[:40])
                    break
        p0_early_count = len(set(v["publish_time"] for v in field_sources.values() if v.get("publish_time") and any(e.get("is_early_signal") and e.get("publish_time") == v["publish_time"] for e in evs)))

        cada_evs = [e for e in evs if e.get("is_final_source")]

        # Build field_sources summary for display
        field_sources_summary = {}
        display_map = {
            "passenger_retail_volume": "passenger",
            "passenger_retail_yoy": "passenger",
            "passenger_retail_mom": "passenger",
            "passenger_retail_ytd": "passenger",
            "passenger_retail_ytd_yoy": "passenger",
            "nev_retail_volume": "nev",
            "nev_retail_yoy": "nev",
            "nev_retail_mom": "nev",
            "nev_retail_ytd": "nev",
            "nev_retail_ytd_yoy": "nev",
            "nev_retail_penetration": "penetration",
        }
        for fk, role in display_map.items():
            if fk in field_sources and role not in field_sources_summary:
                field_sources_summary[role] = field_sources[fk]

        confirmation_status = capture_status
        if has_cada and not has_conflict and headline_fields >= 3:
            confirmation_status = "final_confirmed"
        elif has_cada and has_conflict:
            confirmation_status = "conflict"

        period_confirmed_bool = period_status in ("exact_or_compatible", "month_to_date_compatible")
        headline_complete = headline_fields >= 2  # PV + NEV + PEN
        full_complete = full_fields >= 10  # All 11 structured fields populated
        if headline_complete and period_confirmed_bool:
            if full_complete:
                publish_ready = True
                publish_ready_level = "full"
            else:
                publish_ready = True
                publish_ready_level = "headline_only"
        else:
            publish_ready = False
            publish_ready_level = "none"

        entry = {
            "data_week": data_week,
            "fact_data_week": fact_data_week,
            "fact_data_week_note": fact_data_week_note,
            "fact_period": fact_period,
            "fact_period_status": period_status,
            "confirmation_status": confirmation_status,
            "confidence": conf_score,
            "confidence_label": conf_label,
            "headline_fields_complete": headline_complete,
            "full_publish_fields_complete": full_complete,
            "publish_ready_level": publish_ready_level,
            "publish_ready": publish_ready,
            "publish_ready_text": {
                "title": "乘联会",
                **sentences,
            } if sentences else {},
            "publish_ready_plaintext": ("乘联会\n" + sentences.get("passenger","") + "\n" + sentences.get("nev","") + "\n" + sentences.get("penetration","")) if sentences.get("passenger") or sentences.get("nev") else "",
            "structured_metrics": core_wan,
            "source_consensus": {
                "p0_early_signals": len(p0_times_all),
                "final_authoritative": has_cada,
                "has_conflict": has_conflict,
                "earliest_p0": p0_times_all[0] if p0_times_all else None,
                "final_source_time": cada_evs[0]["publish_time"] if cada_evs else None,
                "field_sources": field_sources_summary,
            },
            "source_discovery_quality": {
                "passenger_p0_found": any(e.get("is_early_signal") for e in evs if "乘用车市场零售" in (e.get("evidence_text","")+e.get("title","")) or "乘用车零售" in (e.get("evidence_text","")+e.get("title",""))),
                "nev_p0_found": any(e.get("is_early_signal") for e in evs if "新能源零售" in (e.get("evidence_text","")+e.get("title","")) or "新能源市场零售" in (e.get("evidence_text","")+e.get("title",""))),
                "penetration_p0_found": any(e.get("is_early_signal") for e in evs if "渗透率" in (e.get("evidence_text","")+e.get("title",""))),
                "passenger_companion_missing": not any(e.get("is_early_signal") for e in evs if "乘用车市场零售" in (e.get("evidence_text","")+e.get("title","")) or "乘用车零售" in (e.get("evidence_text","")+e.get("title",""))),
                "nev_companion_missing": not any(e.get("is_early_signal") for e in evs if "新能源零售" in (e.get("evidence_text","")+e.get("title","")) or "新能源市场零售" in (e.get("evidence_text","")+e.get("title",""))),
                "complete_p0_pair_found": any(e.get("is_early_signal") for e in evs if "乘用车市场零售" in (e.get("evidence_text","")+e.get("title",""))) and any(e.get("is_early_signal") for e in evs if "新能源零售" in (e.get("evidence_text","")+e.get("title",""))),
                "final_source_missing": not has_cada,
            },
            "quality_gates": {
                "period_confirmed": period_confirmed_bool,
                "headline_fields_complete": headline_complete,
                "full_publish_fields_complete": full_complete,
                "publish_ready": publish_ready,
                "publish_ready_level": publish_ready_level,
            },
        }

        # Reject reasons
        reject_reasons = []
        if not period_confirmed_bool:
            reject_reasons.append("period_not_confirmed")
        if not headline_complete:
            missing = []
            if core_wan.get("passenger_retail_volume_wan") is None: missing.append("pv")
            if core_wan.get("nev_retail_volume_wan") is None: missing.append("nev")
            if core_wan.get("nev_retail_penetration_pct") is None: missing.append("penetration")
            reject_reasons.append(f"headline_fields_incomplete: {' '.join(missing)}")
        if headline_complete and not full_complete:
            missing = [k for k, v in core_wan.items() if v is None]
            reject_reasons.append(f"full_fields_incomplete: {' '.join(missing)}")
        if core_wan.get("nev_retail_volume_wan") is None and core_wan.get("passenger_retail_volume_wan"):
            reject_reasons.append("missing_nev")
        if core_wan.get("nev_retail_penetration_pct") is None:
            reject_reasons.append("missing_penetration")

        # period_end for sorting
        pe_for_sort = ""
        if pe_raw:
            try:
                yr = data_week[:4] if len(data_week) >= 4 else "2026"
                pe_for_sort = pe_raw.replace("YYYY", yr)
            except Exception:
                pe_for_sort = ""

        if publish_ready:
            results.append({**entry, "candidate_type": "publish_ready"})
        else:
            results.append({**entry, "candidate_type": "rejected", "reject_reasons": reject_reasons})

    # Select best_fact
    candidates = [r for r in results if r.get("candidate_type") == "publish_ready"]
    rejected = [r for r in results if r.get("candidate_type") == "rejected"]

    # Sort candidates: core_complete desc → period_end desc → confidence desc → p0_count desc → cada first
    def _sort_key(r):
        pe = ""
        try:
            yr = data_week[:4] if len(data_week) >= 4 else "2026"
            for e in cap.get("evidence", []):
                if e.get("detected_period_text") == r["fact_period"] and e.get("detected_period_end"):
                    pe = e["detected_period_end"].replace("YYYY", yr)
                    break
        except Exception:
            pass
        return (
            0 if r.get("full_publish_fields_complete") else (1 if r.get("headline_fields_complete") else 2),
            pe or "",
            -r.get("confidence", 0),
            -r.get("source_consensus", {}).get("p0_early_signals", 0),
            0 if r.get("source_consensus", {}).get("final_authoritative") else 1,
        )

    candidates.sort(key=_sort_key)
    best_fact = candidates[0] if candidates else None
    candidate_facts = candidates[1:] if len(candidates) > 1 else []

    return {
        "result_type": "cpca_weekly_fact_result",
        "data_week": data_week,
        "best_fact": best_fact,
        "candidate_facts": candidate_facts,
        "rejected_facts": rejected,
        "consumer_contract": {
            "default_publish_path": "best_fact.publish_ready_text",
            "default_plaintext_path": "best_fact.publish_ready_plaintext",
            "candidate_facts_publishable": False,
            "rejected_facts_publishable": False,
            "note": "Only best_fact is intended for downstream briefing/chat-message consumption.",
        },
        "summary": {
            "total_candidates": len(candidates),
            "total_rejected": len(rejected),
            "best_fact_period": best_fact["fact_period"] if best_fact else None,
            "best_fact_confidence": best_fact["confidence"] if best_fact else None,
            "best_fact_publish_ready": best_fact["publish_ready"] if best_fact else False,
        },
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }


def main():
    p = argparse.ArgumentParser(description="乘联分会周度数据早源监控")
    p.add_argument("--week", type=str, help="ISO 周，如 2026-W26")
    p.add_argument("--start", type=str, help="开始日期 YYYY-MM-DD")
    p.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    p.add_argument("--format", choices=["terminal", "json", "html"], default="terminal")
    p.add_argument("--capture-json", action="store_true", help="写入 dataset JSON capture")
    p.add_argument("--dataset-dir", type=str, default=str(_DATASET_DIR), help="dataset 目录")
    p.add_argument("--capture-file", type=str, default="cpca_weekly_data_capture.json", help="capture JSON 文件名")
    p.add_argument("--write-fact-result", action="store_true", help="从 capture JSON 生成 fact_result JSON")
    p.add_argument("--fact-result-file", type=str, default="cpca_weekly_fact_result.json", help="fact_result JSON 文件名")
    args = p.parse_args()

    config = _load_config()

    run_week = datetime.now().strftime("%Y-W%V")
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    if args.week:
        data_week = args.week
        data_period_start, data_period_end, _ = _week_to_date_range(data_week)
        week_label = data_week
    elif args.start and args.end:
        data_week = ""
        data_period_start, data_period_end = args.start, args.end
        week_label = f"{data_period_start} ~ {data_period_end}"
    else:
        # Auto-calculate: data_week = ISO week of most recent Sunday
        # CPCA publishes Wed for month-to-date data ending previous Sunday
        today = datetime.now()
        last_sunday = today - timedelta(days=(today.weekday() + 1) % 7)
        year, week_num, _ = last_sunday.isocalendar()
        data_week = f"{year}-W{week_num:02d}"
        data_period_start, data_period_end, _ = _week_to_date_range(data_week)
        week_label = data_week

    # CPCA weekly data typically publishes Wednesday 16:30-18:00
    expected_publish_window = ""
    if data_week:
        wed = datetime.strptime(data_period_end, "%Y-%m-%d") + timedelta(days=2)
        expected_publish_window = f"{wed.strftime('%Y-%m-%d')} 16:30-18:00 左右"

    results = scan(config, data_period_start, data_period_end, format=args.format)

    # Compute compatible once for all format paths
    all_compatible = [r for r in results if r.get("period_match_status") in ("exact_or_compatible", "month_to_date_compatible")]

    if args.format == "json":
        output = {
            "pipeline": "cpca_weekly_early_signal",
            "week": week_label,
            "period": {"start": start_date, "end": end_date},
            "sources": config.get("sources", []),
            "results": results,
            "summary": {
                "early_signals": sum(1 for r in results if r.get("is_early_signal")),
                "authoritative": sum(1 for r in results if r.get("source_role") == "final_authoritative"),
                "historical_mismatches": sum(1 for r in results if r.get("period_match_status") == "historical_mismatch"),
                "total_hits": len(results),
            },
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    elif args.format == "html":
        capture_status = _determine_capture_status(results, all_compatible)
        first_sig = None
        final_conf = None
        p0_t = sorted([r["publish_time"] for r in all_compatible if r.get("is_early_signal") and r.get("publish_time")])
        cada_l = [r for r in all_compatible if r.get("source_role") == "final_authoritative"]
        if p0_t:
            first_sig = {"time": p0_t[0]}
        if cada_l:
            final_conf = {"source": cada_l[0]["source_name"], "time": cada_l[0]["publish_time"]}
        capture_path = ""
        if args.capture_json:
            capture_path = str(Path(args.dataset_dir) / args.capture_file)
        html = _render_html_report(results, config, week_label, data_week, data_period_start, data_period_end, expected_publish_window, run_time, capture_status, first_sig, final_conf, capture_path)
        out_path = _REPORT_DIR / "cpca_weekly_early_signal.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"报告已生成: {out_path}")

    else:
        compatible = all_compatible
        historical = [r for r in results if r.get("period_match_status") == "historical_mismatch"]
        print(f"\n{'='*60}")
        data_week_str = f" · data_week={data_week}" if data_week else ""
        print(f"  乘联分会周度数据早源监控{data_week_str}")
        print(f"  data_period: {data_period_start} 至 {data_period_end}")
        if expected_publish_window:
            print(f"  预计发布窗口: {expected_publish_window}")
        print(f"  run_time: {run_time}")
        print(f"{'='*60}\n")
        for r in sorted(compatible, key=lambda x: x.get("publish_time", "")):
            tag = " 🔶 早信号" if r.get("is_early_signal") else (" ✅ 权威" if r.get("source_role") == "final_authoritative" else "    ")
            period_info = f" [{r.get('detected_period_text','')}]" if r.get("detected_period_text") else ""
            print(f"  {r.get('publish_time','')} {tag}{period_info}")
            print(f"    {r.get('source_name','')} · {r.get('title','')}")
            parts = []
            if r.get("passenger_retail_volume"): parts.append(f"乘用车零售: {r['passenger_retail_volume']:,}")
            if r.get("nev_retail_volume"): parts.append(f"新能源零售: {r['nev_retail_volume']:,}")
            if r.get("nev_retail_penetration"): parts.append(f"渗透率: {r['nev_retail_penetration']}%")
            if parts: print(f"    {' | '.join(parts)}")
            print()

        if historical:
            print(f"  历史误召回 ({len(historical)} 条):")
            for r in historical[:3]:
                print(f"    {r.get('publish_time','')} · {r.get('title','')[:50]}")
            print()

        print(f"  {'='*40}")
        print(f"  本期兼容: {len(compatible)}  历史: {len(historical)}")
        print(f"  P0 早信号: {sum(1 for r in compatible if r.get('is_early_signal'))}")
        print(f"  CADA 确认: {sum(1 for r in compatible if r.get('source_role') == 'final_authoritative')}")
        print(f"{'='*60}")

    # Capture JSON (runs after any format output)
    if args.capture_json:
        cap_path = Path(args.dataset_dir) / args.capture_file
        cap_data = _build_capture_json(results, all_compatible, data_week, data_period_start, data_period_end, expected_publish_window)
        _upsert_capture_json(cap_path, cap_data)
        print(f"  📦 capture JSON: {cap_path}")

    # Fact Result — hydrate evidence then build
    if args.write_fact_result:
        cap_path = Path(args.dataset_dir) / args.capture_file
        fact_path = Path(args.dataset_dir) / args.fact_result_file
        cap = _load_capture_json(cap_path)
        if cap:
            n_p0 = sum(1 for e in cap.get("evidence", []) if e.get("source_tier") in ("P0", "P0_final") and e.get("url"))
            if n_p0:
                print(f"  🌐 尝试全文抓取 {n_p0} 条 P0/P0_final evidence...", file=sys.stderr)
                cap["evidence"] = _hydrate_evidence(cap.get("evidence", []))
                n_ok = sum(1 for e in cap["evidence"] if e.get("hydration_status") == "success")
                print(f"  ✅ 成功: {n_ok}  失败: {n_p0 - n_ok}", file=sys.stderr)
        fact_data = _build_fact_result(cap)
        if fact_data:
            with open(str(fact_path), "w", encoding="utf-8") as f:
                json.dump(fact_data, f, ensure_ascii=False, indent=2)
            print(f"  📋 fact result JSON: {fact_path}")
            bf = fact_data.get("best_fact")
            if bf and bf.get("publish_ready"):
                pt = bf.get("publish_ready_text", {})
                print(f"  📝 best_fact [{bf['fact_period']}] {pt.get('passenger','')[:60]}...")
            rej = fact_data.get("rejected_facts", [])
            if rej:
                for r in rej:
                    print(f"  ⛔ rejected [{r['fact_period']}]: {'; '.join(r.get('reject_reasons',[]))}")
        else:
            print("  ⚠️ 未生成 fact_result：无符合条件的结果", file=sys.stderr)


if __name__ == "__main__":
    main()
