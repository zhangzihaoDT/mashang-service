"""
normalize_search_results.py — 将 Volc Search 原始搜索结果标准化为统一格式。

用法:
  python normalize_search_results.py \
    --raw outputs/auto_launch/search/2026-07-02/brand_watch/search_results.raw.json
"""

import json, sys
from pathlib import Path
from datetime import datetime


def normalize_single_result(item: dict, query_meta: dict, rank: int) -> dict:
    """标准化单条搜索结果为统一格式"""
    return {
        "query": query_meta.get("query", ""),
        "target_id": query_meta.get("target_id", ""),
        "mode": query_meta.get("mode", ""),
        "event_type_ids": query_meta.get("event_type_ids", []),
        "source_tier_focus": query_meta.get("source_tier_focus", []),
        "title": item.get("title", item.get("name", "")),
        "url": item.get("url", item.get("link", "")),
        "snippet": item.get("snippet", item.get("abstract", item.get("description", ""))),
        "source_name": item.get("source", item.get("site_name", "")),
        "source_type_guess": _guess_source_type(item),
        "source_tier_guess": _guess_source_tier(item),
        "publish_time": item.get("publish_time", item.get("date", item.get("published_at", ""))),
        "retrieved_at": datetime.now().isoformat(),
        "raw_rank": rank,
    }


def _guess_source_type(item: dict) -> str:
    """启发式判断来源类型"""
    url = (item.get("url", "") or item.get("link", "") or "").lower()
    source = (item.get("source", "") or item.get("site_name", "") or "").lower()

    if any(d in url or d in source for d in ["autohome", "dongchedi", "yiche", "xchuxing", "pcauto"]):
        return "vertical_auto_media"
    if any(d in url or d in source for d in ["36kr", "huxiu", "latepost", "jiemian", "thepaper", "business"]):
        return "tech_biz_media"
    if any(d in url or d in source for d in ["gasgoo", "nevneus", "d1ev"]):
        return "vertical_industry_media"
    if any(d in url or d in source for d in ["xiaohongshu", "bilibili", "zhihu"]):
        return "social_platform"
    if any(d in url or d in source for d in ["weibo", "tieba"]):
        return "social_platform"
    if any(d in url for d in [".gov.cn", "miit", "moe"]):
        return "official_website"
    if any(d in source for d in ["app", "community"]) and any(d in source for d in ["im", "nio", "xpeng"]):
        return "official_app"

    return "unknown"


def _guess_source_tier(item: dict) -> str:
    """启发式判断信源层级"""
    st = _guess_source_type(item)
    tier_map = {
        "official_website": "tier_1_official",
        "official_app": "tier_1_official",
        "vertical_auto_media": "tier_2_authoritative_media",
        "vertical_industry_media": "tier_2_authoritative_media",
        "tech_biz_media": "tier_3_industry_media",
        "social_platform": "tier_4_social_signal",
    }
    return tier_map.get(st, "tier_5_unverified")


def normalize_results(raw_results: list[dict], query_plan: dict) -> dict:
    """标准化所有搜索结果"""
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
            }

    items = []
    for batch in raw_results:
        q = batch.get("query", "")
        meta = query_meta.get(q, {"query": q})
        for rank, result in enumerate(batch.get("results", []), 1):
            item = normalize_single_result(result, meta, rank)
            items.append(item)

    return {"items": items, "total": len(items)}


def build_audit(user_request: str, monitor_date: str, mode: str,
                query_plan: dict, raw_results: list[dict],
                normalized: dict) -> dict:
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

    # source tier distribution
    tier_dist = {}
    event_coverage = {}
    target_coverage = {}
    for item in normalized.get("items", []):
        tier = item.get("source_tier_guess", "unknown")
        tier_dist[tier] = tier_dist.get(tier, 0) + 1
        for eid in item.get("event_type_ids", []):
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

    return {
        "mode": mode,
        "monitor_date": monitor_date,
        "user_request": user_request,
        "query_count": len(queries),
        "target_count": len(query_plan.get("targets", [])),
        "result_count_raw": sum(b.get("result_count", 0) for b in raw_results),
        "result_count_normalized": normalized.get("total", 0),
        "zero_result_queries": zero_result,
        "failed_queries": failed,
        "source_tier_distribution": tier_dist,
        "coverage_by_event_type": event_coverage,
        "coverage_by_target": target_coverage,
    }


def _unpack_raw(raw_data) -> tuple[list[dict], str, str]:
    """从 raw.json 中解出 results 列表和元信息；兼容 envelope 和 flat array 两种格式"""
    if isinstance(raw_data, dict) and "results" in raw_data:
        return raw_data["results"], raw_data.get("user_request", ""), raw_data.get("monitor_date", "")
    if isinstance(raw_data, list):
        return raw_data, "", ""
    return [], "", ""


def process(raw_path: str, query_plan_path: str, output_prefix: str = None):
    with open(raw_path) as f:
        raw_data = json.load(f)
    with open(query_plan_path) as f:
        query_plan = json.load(f)

    raw_results, req_fallback, _ = _unpack_raw(raw_data)
    normalized = normalize_results(raw_results, query_plan)
    user_request = raw_data.get("user_request", req_fallback) if isinstance(raw_data, dict) else req_fallback
    audit = build_audit(
        user_request=user_request,
        monitor_date=query_plan.get("monitor_date", ""),
        mode=query_plan.get("mode", "brand_watch"),
        query_plan=query_plan,
        raw_results=raw_results,
        normalized=normalized,
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
