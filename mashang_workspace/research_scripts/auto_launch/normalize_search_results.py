"""
normalize_search_results.py — 将 Volc Search 原始搜索结果标准化为统一格式。

用法:
  python normalize_search_results.py \
    --raw outputs/auto_launch/search/2026-07-02/brand_watch/search_results.raw.json
"""

import json, sys, re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT))

from research_scripts.auto_launch.source_domain_resolver import SourceDomainResolver

import yaml

# ── 全局 SourceDomainResolver 实例 ──────────────────
_RESOLVER = None


def _get_resolver() -> SourceDomainResolver:
    global _RESOLVER
    if _RESOLVER is None:
        _RESOLVER = SourceDomainResolver()
    return _RESOLVER


def _canonicalize_url(url: str) -> str:
    """归一化 URL：去除 fragment 和常见 tracking 参数"""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        clean = parsed._replace(fragment="")
        qs = clean.query
        if qs:
            keep = []
            for param in qs.split("&"):
                key = param.split("=")[0] if "=" in param else param
                if key not in ("utm_source", "utm_medium", "utm_campaign", "utm_term",
                               "utm_content", "fbclid", "gclid", "from", "spm"):
                    keep.append(param)
            clean = clean._replace(query="&".join(keep))
        return urlunparse(clean)
    except Exception:
        return url


def _parse_publish_time(pub: str) -> tuple[datetime | None, str]:
    """尝试解析 publish_time，返回 (datetime, parse_status)"""
    if not pub:
        return None, "empty"
    pub = pub.strip()
    # try ISO format
    for fmt in [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S+08:00",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]:
        try:
            dt = datetime.strptime(pub.rstrip("Z"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt, "parsed"
        except ValueError:
            continue
    return None, "unparseable"


def _check_time_window(publish_time: str, tw: dict) -> dict:
    """
    判断单条 item 的时间窗口状态。
    返回: {time_window_status, is_out_of_window, publish_time_parsed, out_of_window_reason}
    """
    start_str = tw.get("start_date", "")
    end_str = tw.get("end_date", "")
    if not start_str or not end_str:
        return {"time_window_status": "no_window_configured", "is_out_of_window": None}

    dt, status = _parse_publish_time(publish_time)
    if dt is None:
        return {"time_window_status": f"unknown_publish_time", "is_out_of_window": None,
                "publish_time_parsed": status}

    start = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).replace(hour=23, minute=59, second=59)

    if dt < start:
        return {"time_window_status": "out_of_window", "is_out_of_window": True,
                "publish_time_parsed": dt.isoformat(),
                "out_of_window_reason": f"publish_time {dt.date()} before window start {start.date()}"}
    if dt > end:
        return {"time_window_status": "out_of_window", "is_out_of_window": True,
                "publish_time_parsed": dt.isoformat(),
                "out_of_window_reason": f"publish_time {dt.date()} after window end {end.date()}"}

    return {"time_window_status": "in_window", "is_out_of_window": False,
            "publish_time_parsed": dt.isoformat()}


def normalize_results(raw_results: list[dict], query_plan: dict, run_mode: str = "mock") -> dict:
    """标准化所有搜索结果，含 URL 去重"""
    mode = query_plan.get("mode", "brand_watch")

    # build query->target_id mapping
    query_meta = {}
    for t in query_plan.get("targets", []):
        for q in t.get("queries", []):
            query_meta[q["query"]] = {
                "query": q["query"],
                "target_id": t["target_id"],
                "mode": mode,
                "event_type_ids": q.get("event_type_ids", []),
                "source_tier_focus": q.get("source_tier_focus", []),
                "query_role": q.get("query_role", "specific"),
                "query_window_role": q.get("query_window_role", "discovery"),
                "query_window_hours": q.get("query_window_hours"),
                "query_window_days": q.get("query_window_days", 7 if q.get("query_window_role") == "discovery" else None),
                "stage": q.get("stage", "discovery"),
                "is_official_direct": q.get("is_official_direct", False),
                "official_domain_target": q.get("official_domain_target"),
                "official_account_target": q.get("official_account_target"),
            }

    resolver = _get_resolver()
    time_window = query_plan.get("time_window", {})
    tw_config = {"start_date": time_window.get("start_date", ""),
                 "end_date": time_window.get("end_date", "")}

    # collect all items
    raw_items_by_url = {}
    for batch in raw_results:
        q = batch.get("query", "")
        meta = query_meta.get(q, {"query": q, "target_id": "", "event_type_ids": [],
                                   "source_tier_focus": [], "query_role": "unknown"})
        for rank, result in enumerate(batch.get("results", []), 1):
            url = result.get("url", result.get("link", ""))
            canonical = _canonicalize_url(url)
            source_name = result.get("source", result.get("site_name", ""))
            title = result.get("title", result.get("name", ""))
            snippet = result.get("snippet", result.get("abstract", result.get("description", "")))
            publish_time = result.get("publish_time", result.get("date", result.get("published_at", "")))

            # domain/source resolution
            resolved = resolver.resolve(url, source_name, title, snippet)

            # time window check
            tw_check = _check_time_window(publish_time, tw_config)

            item = {
                "query": q,
                "target_id": meta["target_id"],
                "mode": mode,
                "event_type_ids": meta.get("event_type_ids", []),
                "source_tier_focus": meta.get("source_tier_focus", []),
                "query_role": meta.get("query_role", "specific"),
                "query_window_role": meta.get("query_window_role", "discovery"),
                "query_window_hours": meta.get("query_window_hours"),
                "query_window_days": meta.get("query_window_days"),
                "stage": meta.get("stage", "discovery"),
                "is_official_direct": meta.get("is_official_direct", False),
                "official_domain_target": meta.get("official_domain_target"),
                "official_account_target": meta.get("official_account_target"),
                "title": title,
                "url": url,
                "canonical_url": canonical,
                "snippet": snippet,
                "source_name": source_name,
                "source_type_guess": resolved["source_type_guess"],
                "source_tier_guess": resolved["source_tier_guess"],
                "source_resolution_reason": resolved["source_resolution_reason"],
                "domain": resolved["domain"],
                "claim_source_hint": resolved.get("claim_source_hint"),
                "claim_source_hint_reason": resolved.get("claim_source_hint_reason"),
                "publish_time": publish_time,
                "time_window_status": tw_check["time_window_status"],
                "is_out_of_window": tw_check["is_out_of_window"],
                "retrieved_at": datetime.now().isoformat(),
                "raw_rank": rank,
                "routing_bucket": None,
                "candidate_gate_status": None,
                "candidate_gate_reasons": [],
                "eligible_for_event_cluster": True,
            }

            # ── Task 2: official_direct routing ──
            stage = item.get("stage", "")
            tws = item.get("time_window_status", "")
            st = item.get("source_type_guess", "")
            if stage == "official_direct" and tws != "in_window":
                item["routing_bucket"] = "context_only"
                item["candidate_gate_status"] = "rejected"
                item["candidate_gate_reasons"].append("official_direct_not_in_confirmed_window")
                item["eligible_for_event_cluster"] = False
            if st == "official_product_page" and tws == "unknown_publish_time":
                item["routing_bucket"] = "context_only"
                item["candidate_gate_status"] = "rejected"
                item["candidate_gate_reasons"].append("official_static_page_without_publish_time")
                item["eligible_for_event_cluster"] = False
            if st == "official_owned_platform" and stage == "official_direct" and tws != "in_window":
                item["routing_bucket"] = "context_only"
                item["candidate_gate_status"] = "rejected"
                item["candidate_gate_reasons"].append("official_owned_platform_not_in_confirmed_window")
                item["eligible_for_event_cluster"] = False

            if canonical not in raw_items_by_url:
                raw_items_by_url[canonical] = item
                raw_items_by_url[canonical]["matched_queries"] = []
                raw_items_by_url[canonical]["matched_event_type_ids"] = []
                raw_items_by_url[canonical]["matched_source_tier_focus"] = []
                raw_items_by_url[canonical]["raw_ranks"] = []
                raw_items_by_url[canonical]["dedupe_hit_count"] = 0

            existing = raw_items_by_url[canonical]
            existing["dedupe_hit_count"] += 1
            if q not in existing["matched_queries"]:
                existing["matched_queries"].append(q)
            for eid in meta.get("event_type_ids", []):
                if eid not in existing["matched_event_type_ids"]:
                    existing["matched_event_type_ids"].append(eid)
            for stf in meta.get("source_tier_focus", []):
                if stf not in existing["matched_source_tier_focus"]:
                    existing["matched_source_tier_focus"].append(stf)
            if rank not in existing["raw_ranks"]:
                existing["raw_ranks"].append(rank)

    items = list(raw_items_by_url.values())
    items.sort(key=lambda x: min(x["raw_ranks"]) if x["raw_ranks"] else 999)

    return {
        "items": items,
        "total": len(items),
        "run_mode": run_mode,
        "is_mock": run_mode == "mock",
        "dedupe": {
            "raw_item_count": sum(len(b.get("results", [])) for b in raw_results),
            "normalized_item_count": len(items),
        },
    }


def build_audit(user_request: str, monitor_date: str, mode: str,
                query_plan: dict, raw_results: list[dict],
                normalized: dict, run_mode: str = "mock",
                budget_plan: dict = None,
                api_call_count: int = 0, cache_hit_count: int = 0, cache_miss_count: int = 0,
                scout_results: list = None, refine_results: list = None) -> dict:
    """生成搜索审计报告"""
    queries = []
    for t in query_plan.get("targets", []):
        for q in t.get("queries", []):
            queries.append(q)

    zero_result = []
    failed = []
    for batch in raw_results:
        if batch.get("result_count", 0) == 0 and batch.get("status") == "success":
            zero_result.append(batch["query"])
        if batch.get("status") == "error":
            failed.append(batch.get("query", ""))

    # source tier distribution (after dedupe)
    tier_dist = {}
    event_coverage = {}
    target_coverage = {}
    dedupe_info = normalized.get("dedupe", {})
    for item in normalized.get("items", []):
        tier = item.get("source_tier_guess", "unknown")
        tier_dist[tier] = tier_dist.get(tier, 0) + 1
        for eid in item.get("matched_event_type_ids", item.get("event_type_ids", [])):
            event_coverage[eid] = event_coverage.get(eid, 0) + 1

    query_texts = {q["query"] for q in queries}
    for t in query_plan.get("targets", []):
        tid = t["target_id"]
        tq_texts = {qq["query"] for qq in t.get("queries", [])}
        t_query_count = len(tq_texts & query_texts) or len(t.get("queries", []))
        tid_results = [i for i in normalized.get("items", []) if i.get("target_id") == tid]
        official_count = sum(1 for i in tid_results if "tier_1" in i.get("source_tier_guess", ""))
        weak_count = sum(1 for i in tid_results if "tier_4" in i.get("source_tier_guess", "") or "tier_5" in i.get("source_tier_guess", ""))
        target_coverage[tid] = {
            "query_count": t_query_count,
            "normalized_result_count": len(tid_results),
            "official_source_count": official_count,
            "weak_signal_count": weak_count,
        }

    source_quality = {
        "unknown_source_count": tier_dist.get("tier_5_unverified", 0),
    }
    for tier_key in ["tier_1_official", "tier_3_industry_media", "tier_4_social_signal", "tier_5_unverified"]:
        count = tier_dist.get(tier_key, 0)
        label = tier_key.replace(".", "_").replace("-", "_")
        source_quality[f"{label}_count"] = count

    raw_count = dedupe_info.get("raw_item_count", 0)
    norm_count = dedupe_info.get("normalized_item_count", 0)
    dupes = raw_count - norm_count
    dedupe_ratio = round(dupes / raw_count, 3) if raw_count > 0 else 0

    # ── time_window_quality ─────────────────────────
    items = normalized.get("items", [])
    in_window = sum(1 for i in items if i.get("time_window_status") == "in_window")
    out_window = sum(1 for i in items if i.get("is_out_of_window") is True)
    unknown_pub = sum(1 for i in items if i.get("time_window_status", "").startswith("unknown"))
    tw_quality = {
        "in_window_count": in_window,
        "out_of_window_count": out_window,
        "unknown_publish_time_count": unknown_pub,
        "out_of_window_ratio": round(out_window / len(items), 3) if items else 0,
    }

    # ── source_resolution_quality ────────────────────
    src_res = {}
    for item in items:
        st = item.get("source_type_guess", "unknown")
        src_res[st] = src_res.get(st, 0) + 1

    # ── event_extraction_readiness ────────────────────
    ready = 0
    blocked_time = 0
    blocked_source = 0
    cross_check = 0
    for item in items:
        st = item.get("source_type_guess", "unknown")
        stier = item.get("source_tier_guess", "tier_5_unverified")
        oow = item.get("is_out_of_window")

        if oow is True:
            blocked_time += 1
            continue

        if st in ("portal_or_aggregator", "unknown") or stier == "tier_5_unverified":
            blocked_source += 1
            continue

        if st in ("dealer_page", "social_platform") or stier in ("tier_4_social_signal", "tier_5_unverified"):
            cross_check += 1
            continue

        if stier in ("tier_1_official", "tier_3_industry_media"):
            ready += 1

    readiness = {
        "ready_item_count": ready,
        "blocked_by_time_window_count": blocked_time,
        "blocked_by_source_quality_count": blocked_source,
        "requires_cross_check_count": cross_check,
    }

    # ── routing stats (Tasks 2,5) ─────────────────────
    routing_cnt = {"candidate_eligible": 0, "context_only": 0, "needs_review": 0}
    od_total = od_in = od_out = od_unknown = od_routed = 0
    for item in items:
        rb = item.get("routing_bucket")
        if rb == "context_only":
            routing_cnt["context_only"] += 1
        else:
            routing_cnt["candidate_eligible"] += 1

        if item.get("is_official_direct"):
            od_total += 1
            tws = item.get("time_window_status", "")
            if tws == "in_window":
                od_in += 1
            elif tws == "out_of_window":
                od_out += 1
            else:
                od_unknown += 1
            if rb == "context_only":
                od_routed += 1

    routing_stats = {
        "routing_counts": routing_cnt,
        "official_direct_counts": {
            "total": od_total, "in_window": od_in,
            "out_of_window": od_out, "unknown_publish_time": od_unknown,
            "routed_to_context_only": od_routed,
        },
    }

    audit = {
        "mode": mode,
        "monitor_date": monitor_date,
        "user_request": user_request,
        "run_mode": run_mode,
        "is_mock": run_mode == "mock",
        "query_count": len(queries),
        "target_count": len(query_plan.get("targets", [])),
        "result_count_raw": sum(b.get("result_count", 0) for b in raw_results),
        "result_count_normalized": normalized.get("total", 0),
        "zero_result_queries": zero_result,
        "failed_queries": failed,
        "dedupe": {
            "raw_item_count": raw_count,
            "normalized_item_count": norm_count,
            "duplicate_url_count": dupes,
            "dedupe_ratio": dedupe_ratio,
        },
        "time_window_quality": tw_quality,
        "source_tier_distribution": tier_dist,
        "source_quality": source_quality,
        "source_resolution_quality": src_res,
        "event_extraction_readiness": readiness,
        "routing_stats": routing_stats,
        "coverage_by_event_type": event_coverage,
        "coverage_by_target": target_coverage,
    }

    # ── budget info ─────────────────────────────────
    if budget_plan:
        bp = budget_plan
        audit["budget"] = {
            "profile": bp.get("profile", "standard_scan"),
            "query_budget_per_target": bp.get("query_budget_per_target", 5),
            "query_count_planned": len(queries),
            "query_count_executed": len(queries),
            "result_limit_per_query": bp.get("result_limit_per_query", 8),
            "api_call_count": api_call_count,
            "cache_hit_count": cache_hit_count,
            "cache_miss_count": cache_miss_count,
            "cache_disabled": not bp.get("cache", {}).get("enabled", True),
            "refresh": bp.get("cache", {}).get("refresh", False),
        }

    # ── stage info ──────────────────────────────────
    staged = {"scout": {"planned_query_count": 0, "executed_query_count": 0,
                        "normalized_item_count": 0, "ready_item_count": 0},
              "refine": {"planned_query_count": 0, "executed_query_count": 0,
                         "normalized_item_count": 0, "ready_item_count": 0}}

    for q in queries:
        stg = q.get("stage", "scout")
        if stg in staged:
            staged[stg]["planned_query_count"] += 1

    for r in (scout_results or []):
        staged["scout"]["executed_query_count"] += 1
    for r in (refine_results or []):
        staged["refine"]["executed_query_count"] += 1

    for item in items:
        stg = "scout"
        # find which stage this item came from
        src_q = item.get("query", "")
        for sq in (scout_results or []):
            if sq.get("query") == src_q:
                stg = "scout"
                break
        for rq in (refine_results or []):
            if rq.get("query") == src_q:
                stg = "refine"
                break
        if item.get("is_out_of_window") is not True:
            staged[stg]["normalized_item_count"] += 1
            if item.get("source_tier_guess") in ("tier_1_official", "tier_3_industry_media"):
                staged[stg]["ready_item_count"] += 1

    audit["stages"] = staged

    if run_mode == "mock":
        audit["mock_warning"] = "This output was generated from mock search results and must not be used as real market intelligence."

    return audit


def _unpack_raw(raw_data) -> tuple[list[dict], str, str]:
    """从 raw.json 中解出 results 列表和元信息"""
    if isinstance(raw_data, dict) and "results" in raw_data:
        return raw_data["results"], raw_data.get("user_request", ""), raw_data.get("run_mode", "mock")
    if isinstance(raw_data, list):
        return raw_data, "", "mock"
    return [], "", "mock"


def process(raw_path: str, query_plan_path: str, output_prefix: str = None):
    with open(raw_path) as f:
        raw_data = json.load(f)
    with open(query_plan_path) as f:
        query_plan = json.load(f)

    raw_results, req_fallback, fallback_mode = _unpack_raw(raw_data)
    run_mode = raw_data.get("run_mode", fallback_mode) if isinstance(raw_data, dict) else fallback_mode
    normalized = normalize_results(raw_results, query_plan, run_mode)
    user_request = raw_data.get("user_request", req_fallback) if isinstance(raw_data, dict) else req_fallback
    audit = build_audit(
        user_request=user_request,
        monitor_date=query_plan.get("monitor_date", ""),
        mode=query_plan.get("mode", "brand_watch"),
        query_plan=query_plan,
        raw_results=raw_results,
        normalized=normalized,
        run_mode=run_mode,
    )

    if output_prefix:
        out_dir = Path(output_prefix).parent
        out_dir.mkdir(parents=True, exist_ok=True)

        norm_path = out_dir / "search_results.normalized.json"
        with open(norm_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        print(f"[normalized] 已写入: {norm_path}")

        audit_path = out_dir / "search_audit.json"
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)
        print(f"[audit] 已写入: {audit_path}")

    return normalized, audit


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="搜索结果标准化")
    parser.add_argument("--raw", required=True, help="原始搜索结果 JSON 路径")
    parser.add_argument("--query-plan", required=True, help="query_plan JSON 路径")
    parser.add_argument("--output-prefix", help="输出前缀目录")
    args = parser.parse_args()

    normalized, audit = process(args.raw, args.query_plan, args.output_prefix)
    print(json.dumps({"normalized_count": normalized["total"], "audit_query_count": audit["query_count"]},
                     ensure_ascii=False, indent=2))
