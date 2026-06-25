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

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_REPORT_DIR = _ROOT / "outputs" / "reports"
_REPORT_DIR.mkdir(parents=True, exist_ok=True)
_CONFIG_PATH = _ROOT / "configs" / "cpca_weekly_sources.json"


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
    for k in ("HUOSANFANGZHOU_API_KEY", "HUOSHANFANGZHOU_API_KEY", "VOLCENGINE_API_KEY"):
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
    """Generate period hint strings based on data_week (the week data belongs to)."""
    start = datetime.strptime(data_period_start, "%Y-%m-%d")
    end = datetime.strptime(data_period_end, "%Y-%m-%d")
    year_s = start.year
    month_s = start.month
    day_s = start.day
    day_e = end.day

    hints = [
        f"{month_s}月{day_s}-{day_e}日",
        f"{month_s}月{day_s}日-{month_s}月{day_e}日",
        f"{year_s}年{month_s}月{day_s}日-{month_s}月{day_e}日",
        f"{month_s}月1-{day_e}日",
        f"{year_s}年{month_s}月1日-{month_s}月{day_e}日",
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
        for hint in period_hints[:2]:  # Top 2 period hints
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


def _extract_cpca_numbers(text):
    result = {}
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
    }
    for key, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, text)
            if m:
                val = float(m.group(1))
                if key == "nev_retail_penetration":
                    result[key] = val
                else:
                    result[key] = int(val * 10000)
                break
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
        print("  ⚠️ API Key 未设置，使用样例数据。设置 HUOSANFANGZHOU_API_KEY。", file=sys.stderr)
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

def _render_html_report(results, config, week_label, data_week="", data_period_start="", data_period_end="", expected_publish_window="", run_time=""):
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


def main():
    p = argparse.ArgumentParser(description="乘联分会周度数据早源监控")
    p.add_argument("--week", type=str, help="ISO 周，如 2026-W26")
    p.add_argument("--start", type=str, help="开始日期 YYYY-MM-DD")
    p.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    p.add_argument("--format", choices=["terminal", "json", "html"], default="terminal")
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
        data_week = ""
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        data_period_start = monday.strftime("%Y-%m-%d")
        data_period_end = sunday.strftime("%Y-%m-%d")
        week_label = f"{data_period_start} ~ {data_period_end}"

    # CPCA weekly data typically publishes Wednesday 16:30-18:00
    expected_publish_window = ""
    if data_week:
        wed = datetime.strptime(data_period_end, "%Y-%m-%d") + timedelta(days=2)
        expected_publish_window = f"{wed.strftime('%Y-%m-%d')} 16:30-18:00 左右"

    results = scan(config, data_period_start, data_period_end, format=args.format)

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
        html = _render_html_report(results, config, week_label, data_week, data_period_start, data_period_end, expected_publish_window, run_time)
        out_path = _REPORT_DIR / "cpca_weekly_early_signal.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"报告已生成: {out_path}")

    else:
        compatible = [r for r in results if r.get("period_match_status") in ("exact_or_compatible", "month_to_date_compatible")]
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


if __name__ == "__main__":
    main()
