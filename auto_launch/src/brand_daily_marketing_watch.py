"""Layer: Intelligence Utilities — 本品品牌每日监控管线"""
"""
brand_daily_marketing_watch.py — owned brand daily marketing event monitor.

Reuses existing auto_launch Search Layer components.
Output paths managed by output_paths.py.

Usage:
  python brand_daily_marketing_watch.py --brand im --brand-name 智己
  python brand_daily_marketing_watch.py --brand im --brand-name 智己 --live
  python brand_daily_marketing_watch.py --brand im --brand-name 智己 --window-hours 48
"""

import json, sys, yaml
from pathlib import Path
from datetime import datetime, timedelta

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent
PROJECT_ROOT = SERVICE_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from auto_launch.src.search_budget_manager import build_budget_plan
from auto_launch.src.volc_search_query_builder import build_query_plan
from auto_launch.src.volc_search_client import VolcSearchClient, VolcSearchError
from auto_launch.src.normalize_search_results import normalize_results, build_audit
from auto_launch.src.search_cache import search_with_cache
from auto_launch.src.event_clusterer import cluster_items
from auto_launch.src.event_candidate_gate import gate_clusters
from auto_launch.src import output_paths


def _load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def _valid_event_types():
    """从 event_types.yaml 读取所有合法 event_type_id"""
    path = SERVICE_ROOT / "configs" / "event_types.yaml"
    if not path.exists():
        return set()
    data = _load_yaml(path)
    eids = set()
    for group in ("shared_event_types", "model_watch_only_event_types", "brand_watch_only_event_types"):
        for et in data.get(group, []):
            eids.add(et["event_type_id"])
    return eids


def _run(brand: str, brand_name: str, monitor_date: str, window_hours: int,
         query_profile: str, out_dir: str = None, dry_run: bool = False, refresh: bool = False):
    """Execute the daily marketing watch pipeline.

    out_dir is deprecated — output paths are managed by output_paths.py.
    """
    monitor_dt = datetime.strptime(monitor_date, "%Y-%m-%d")
    end_dt = monitor_dt.replace(hour=23, minute=59, second=59)
    start_dt = end_dt - timedelta(hours=window_hours)

    def _fmt(dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    tw = {
        "window_type": "relative_hours", "hours": window_hours,
        "start_date": start_dt.strftime("%Y-%m-%d"), "end_date": end_dt.strftime("%Y-%m-%d"),
        "start_datetime": _fmt(start_dt), "end_datetime": _fmt(end_dt),
        "timezone": "Asia/Shanghai", "date_inclusive": True,
    }

    # intent
    intent = {
        "user_request": f"看看{brand_name}过去{window_hours}小时有什么营销动作",
        "monitor_date": monitor_date, "intent_type": "open_ended_activity_scan",
        "mode": "brand_watch",
        "targets": [{"target_id": brand, "target_type": "brand", "brand": brand_name,
                      "brand_cn": brand_name, "model": None, "confidence": "high",
                      "is_in_watchlist": True, "target_source": "brand_watchlist"}],
        "time_window": tw,
        "event_scope": {"scope_type": "all_relevant_actions", "event_type_ids": []},
        "source_strategy": {"official_first": True, "include_authoritative_media": True,
                            "include_industry_media": True, "include_social_signals": True,
                            "social_signals_as_discovery_only": True, "allow_unverified_as_discovery_only": True},
        "query_budget": {"query_budget_per_target": 5, "result_limit_per_query": 8},
        "ambiguities": [], "notes": [f"Owned brand daily watch for {brand_name}"],
    }

    # task config
    task_config = {
        "task_name": "brand_daily_marketing_watch", "mode": "brand_watch",
        "monitor_date": monitor_date, "target_count": 1,
        "targets": [{"target_id": brand, "target_type": "brand", "brand": brand_name,
                      "aliases": [brand_name, brand.upper()], "sub_brands": [], "models": []}],
        "time_window": tw, "source_strategy": intent["source_strategy"],
        "event_type_ids": [], "query_budget": {"query_budget_per_target": 5, "result_limit_per_query": 8},
    }

    # budget plan
    budget_plan = build_budget_plan(intent, cli_profile=query_profile, refresh=refresh)
    budget_plan["cache"]["refresh"] = refresh

    # query plan
    query_plan = build_query_plan(task_config, budget_plan)

    # ── official direct search queries with absolute date window ──
    official_domain = "immotors.com"
    date_label = f"{start_dt.strftime('%Y年%m月%d日')} {end_dt.strftime('%Y年%m月%d日')}"
    official_queries = [
        {"query": f"site:{official_domain} {brand_name} {date_label} 权益 交付",
         "stage": "official_direct", "query_role": "confirmed", "query_window_role": "confirmed",
         "query_window_hours": window_hours, "query_window_days": None,
         "is_official_direct": True, "official_domain_target": official_domain,
         "event_type_ids": ["benefit_adjustment", "delivery_start"], "source_tier_focus": ["tier_1_official"]},
        {"query": f"site:{official_domain} {brand_name} {date_label} OTA 技术 发布",
         "stage": "official_direct", "query_role": "confirmed", "query_window_role": "confirmed",
         "query_window_hours": window_hours, "query_window_days": None,
         "is_official_direct": True, "official_domain_target": official_domain,
         "event_type_ids": ["technology_release", "launch_event"], "source_tier_focus": ["tier_1_official"]},
        {"query": f"site:{official_domain} {brand_name} {date_label} LS9 LS8 L6 上市 销量",
         "stage": "official_direct", "query_role": "confirmed", "query_window_role": "confirmed",
         "query_window_hours": window_hours, "query_window_days": None,
         "is_official_direct": True, "official_domain_target": official_domain,
         "event_type_ids": ["launch", "sales_milestone"], "source_tier_focus": ["tier_1_official"]},
    ]
    for t in query_plan.get("targets", []):
        if t["target_id"] == brand:
            t.setdefault("queries", [])
            # Prepend official direct queries to the target
            for oq in reversed(official_queries):
                t["queries"].insert(0, oq)
            break

    # output — use output_paths
    run_mode = output_paths.run_mode_brand_daily(brand)
    run_dir_path = output_paths.run_dir(monitor_date, run_mode)
    search_out = output_paths.search_dir(monitor_date, run_mode)
    reports_out = output_paths.reports_dir(monitor_date, run_mode)

    manifest = {
        "task_name": "brand_daily_marketing_watch",
        "brand_key": brand, "brand_name": brand_name,
        "monitor_date": monitor_date, "run_mode": run_mode,
        "time_window": {"start": _fmt(start_dt), "end": _fmt(end_dt), "window_hours": window_hours},
        "query_profile": query_profile, "output_files": [],
    }

    qc = sum(len(t.get("queries", [])) for t in query_plan.get("targets", []))
    print(f"[brand_daily] {brand_name} | {monitor_date} | 过去 {window_hours} 小时 | profile={query_profile}")
    print(f"              {qc} queries planned")
    print(f"              输出: {run_dir_path}")

    if dry_run:
        manifest_path = output_paths.run_manifest_path(monitor_date, run_mode)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"              dry-run (pass --live to execute)")
        return

    # search
    try:
        client = VolcSearchClient()
    except VolcSearchError as e:
        print(f"[error] {e}", file=sys.stderr)
        return

    all_queries = []
    for t in query_plan.get("targets", []):
        for q in t.get("queries", []):
            q["target_id"] = t["target_id"]
            all_queries.append(q)

    result_limit = budget_plan.get("result_limit_per_query", 8)
    cache_cfg = budget_plan.get("cache", {})
    print(f"[search] {len(all_queries)} queries")
    search_results_list, errors = [], []
    api_calls = cache_hits = 0

    for i, q_item in enumerate(all_queries, 1):
        q_text = q_item["query"]
        print(f"  [{q_item.get('stage','?')}] [{i}/{len(all_queries)}] {q_text}")
        try:
            result = search_with_cache(client, q_text, result_limit, cache_cfg,
                                        monitor_date, "brand_watch", brand, provider="doubao_search")
            if result.get("api_called"): api_calls += 1
            if result.get("cache_status") == "hit": cache_hits += 1
        except Exception as e:
            result = {"query": q_text, "status": "error", "error": str(e),
                      "result_count": 0, "results": [], "api_called": True, "cache_status": "error"}
            api_calls += 1
        result["meta"] = q_item
        search_results_list.append(result)
        if result.get("status") == "error":
            errors.append({"query": q_text, "error": result.get("error", "")})

    # raw
    raw_path = output_paths.search_raw_path(monitor_date, run_mode)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump({"task_name": "brand_daily_marketing_watch", "brand_key": brand,
                    "brand_name": brand_name, "monitor_date": monitor_date, "run_mode": run_mode,
                    "query_count": len(all_queries), "api_calls": api_calls,
                    "results": search_results_list, "errors": errors},
                   f, ensure_ascii=False, indent=2)

    # normalize
    normalized = normalize_results(search_results_list, query_plan, run_mode="live")
    norm_path = output_paths.search_normalized_path(monitor_date, run_mode)
    with open(norm_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    print(f"  [norm] {normalized['total']} items")

    # audit
    audit = build_audit(
        f"{brand_name}过去{window_hours}小时营销监控", monitor_date, "brand_watch",
        query_plan, search_results_list, normalized, run_mode="live",
        budget_plan=budget_plan, api_call_count=api_calls, cache_hit_count=cache_hits,
        cache_miss_count=len(all_queries) - api_calls - cache_hits,
        scout_results=[r for r in search_results_list if r.get("meta",{}).get("stage")=="scout"],
        refine_results=[r for r in search_results_list if r.get("meta",{}).get("stage")=="refine"],
    )
    audit_path = output_paths.search_audit_path(monitor_date, run_mode)
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    # --- event cluster + gate ---
    items = normalized.get("items", [])
    clustered = cluster_items(items, brand_key=brand)
    cluster_path = search_out / "clusters.json"
    with open(cluster_path, "w", encoding="utf-8") as f:
        json.dump(clustered, f, ensure_ascii=False, indent=2)
    print(f"  [clusters] {clustered['cluster_count']} clusters from {len(items)} items")

    valid_eids = _valid_event_types()
    gated = gate_clusters(clustered["clusters"], valid_event_types=valid_eids)

    cand_path = search_out / "candidates.json"
    with open(cand_path, "w", encoding="utf-8") as f:
        json.dump(gated["candidates"], f, ensure_ascii=False, indent=2)
    print(f"  [candidates] {len(gated['candidates'])} clusters (gated)")

    sig_path = search_out / "signals.json"
    with open(sig_path, "w", encoding="utf-8") as f:
        json.dump(gated["discovery_signals"], f, ensure_ascii=False, indent=2)
    print(f"  [signals] {len(gated['discovery_signals'])} clusters")

    ctx_path = search_out / "context_only.json"
    with open(ctx_path, "w", encoding="utf-8") as f:
        json.dump(gated["context_only"], f, ensure_ascii=False, indent=2)
    print(f"  [context] {len(gated['context_only'])} clusters")

    review_path = search_out / "needs_review.json"
    with open(review_path, "w", encoding="utf-8") as f:
        json.dump(gated["needs_review"], f, ensure_ascii=False, indent=2)
    print(f"  [review] {len(gated['needs_review'])} clusters")

    # --- markdown summary ---
    ready = audit.get("event_extraction_readiness", {}).get("ready_item_count", 0)
    cross = audit.get("event_extraction_readiness", {}).get("requires_cross_check_count", 0)
    srq = audit.get("source_resolution_quality", {})

    gated_candidates = gated["candidates"]
    gated_signals = gated["discovery_signals"]
    gated_context = gated["context_only"]
    gated_review = gated["needs_review"]

    if not gated_candidates and not gated_signals:
        conclusion = f"过去 {window_hours} 小时未发现 {brand_name} 明确品牌级营销事件；已检查官方源、垂媒、科技财经媒体与社交平台弱信号。"
    else:
        conclusion = f"发现 {len(gated_candidates)} 个高可信事件（cluster），{len(gated_signals)} 个待核验弱信号。"

    md = f"""# {brand_name} 品牌每日营销监控 — {monitor_date}

**监控窗口**: 过去 {window_hours} 小时 ({_fmt(start_dt)} ~ {_fmt(end_dt)})
**Profile**: {query_profile} | **API**: {api_calls} | **Cache**: {cache_hits}

## 今日结论

{conclusion}

## 已确认品牌事件

"""
    if gated_candidates:
        for c in gated_candidates:
            md += f"""- **{c.get('event_type','?')}** — {c.get('event_title','')[:70]}
  - 时间: {c.get('event_time','')} | 来源数: {c.get('source_count',0)} | best_tier: {c.get('best_source_tier','')}
  - {c.get('event_summary','')[:150]}...
"""
    else:
        md += "（无）\n"

    md += "\n## 营销弱信号\n"
    if gated_signals:
        for s in gated_signals[:8]:
            si = (s.get("source_items") or [{}])[0]
            md += f"""- {s.get('event_title','')[:60]}
  - {si.get('source_name','')} | {s.get('best_source_tier','')}
  - {', '.join(s.get('candidate_gate_reasons',[]))}
"""
    else:
        md += "（无）\n"

    md += f"""
## 官方源覆盖情况

{srq.get('official_website', 0)} 条官方域名命中 | {srq.get('official_social_account', 0)} 条官方社媒命中

## 媒体 / 社交信号覆盖情况

- 垂媒: {srq.get('vertical_auto_media', 0)} | 门户: {srq.get('portal_or_aggregator', 0)}
- 社交: {srq.get('social_platform', 0)} | 经销商: {srq.get('dealer_page', 0)}

## 待复核事项

- blocked_by_source_quality: {audit.get('event_extraction_readiness', {}).get('blocked_by_source_quality_count', 0)}
- out_of_window: {audit.get('time_window_quality', {}).get('out_of_window_count', 0)}

## 明日关注点

- 官方权益是否延续
- 是否有 OTA / 技术发布
- 高管是否有公开发声
"""
    md_path = reports_out / "marketing_watch_summary.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    # manifest
    manifest["output_files"] = [str(p) for p in [raw_path, norm_path, cluster_path, cand_path, sig_path, ctx_path, review_path, audit_path, md_path]]
    manifest_path = output_paths.run_manifest_path(monitor_date, run_mode)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {brand_name} | clusters={clustered['cluster_count']} | candidates={len(gated_candidates)} | signals={len(gated_signals)} | API={api_calls}")
    print(f"   输出: {run_dir_path}")


if __name__ == "__main__":
    ap = __import__('argparse').ArgumentParser(description="Owned brand daily marketing watch")
    ap.add_argument("--brand", default="im")
    ap.add_argument("--brand-name", default="智己")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--window-hours", type=int, default=24)
    ap.add_argument("--query-profile", default="balanced")
    ap.add_argument("--out-dir", help="(deprecated) 输出路径由 output_paths.py 统一管理")
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    _run(
        brand=args.brand, brand_name=args.brand_name, monitor_date=args.date,
        window_hours=args.window_hours, query_profile=args.query_profile,
        dry_run=not args.live, refresh=args.refresh,
    )
