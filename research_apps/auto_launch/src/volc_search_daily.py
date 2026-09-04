"""Layer: Search Pipeline — 完整搜索管线编排"""
"""
volc_search_daily.py — Auto Launch 搜索意图转译与执行主脚本 v0.4。

完整链路:
  user_request → search_intent → search_task_config → search_budget_plan
  → query_plan → Volc Search API (cached) → raw → normalized → audit

输出路径统一由 output_paths.py 管理，产物写入:
  runs/{YYYYMMDD}/{run_mode}/search/{plan,raw,normalized,audit}.json

用法:
  # dry-run (default, no API calls)
  python volc_search_daily.py --request "看看极氪最近 7 天都有什么动作"

  # live with cache
  python volc_search_daily.py --request "看看极氪最近 7 天都有什么动作" --live

  # refresh cache
  python volc_search_daily.py --request "看看极氪最近 7 天都有什么动作" --live --refresh
"""

import json, sys, os, argparse
from pathlib import Path
from datetime import datetime

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent
PROJECT_ROOT = SERVICE_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from auto_launch.src.search_intent_compiler import compile_intent
from auto_launch.src.search_task_config_builder import build_task_config
from auto_launch.src.search_budget_manager import build_budget_plan
from auto_launch.src.volc_search_query_builder import build_query_plan
from auto_launch.src.volc_search_client import VolcSearchClient, VolcSearchError
from auto_launch.src.normalize_search_results import normalize_results, build_audit
from auto_launch.src.search_cache import search_with_cache
from auto_launch.src import output_paths


def _count_queries(query_plan: dict) -> int:
    return sum(len(t.get("queries", [])) for t in query_plan.get("targets", []))


def run_pipeline(request: str, monitor_date: str, force_mode: str = None,
                 dry_run: bool = True, query_profile: str = None,
                 max_queries: int = None, result_limit: int = None,
                 refresh: bool = False, disable_cache: bool = False,
                 stage: str = None):
    """
    执行完整的搜索意图转译与搜索链路（v2）。
    """

    # ── 1. search_intent ─────────────────────────────
    intent = compile_intent(request, monitor_date, None)
    if force_mode:
        intent["mode"] = force_mode

    mode = intent["mode"]

    # Determine run_mode from intent targets
    if mode == "brand_watch" and intent.get("targets"):
        label = intent["targets"][0].get("brand", intent["targets"][0].get("target_id", "unknown"))
        run_mode = output_paths.run_mode_brand_watch(label)
    elif mode == "model_watch" and intent.get("targets"):
        label = intent["targets"][0].get("model", intent["targets"][0].get("target_id", "unknown"))
        run_mode = output_paths.run_mode_model_watch(label)
    else:
        run_mode = mode

    # All outputs go under runs/{YYYYMMDD}/{run_mode}/search/
    outdir = output_paths.search_dir(monitor_date, run_mode)

    # ── 2. search_task_config ────────────────────────
    task_config = build_task_config(intent)

    # ── 3. search_budget_plan ─────────────────────────
    budget_plan = build_budget_plan(
        intent, cli_profile=query_profile,
        cli_max_queries=max_queries, cli_result_limit=result_limit,
        refresh=refresh, disable_cache=disable_cache,
        cli_stage=stage,
    )
    print(f"[budget] profile={budget_plan['profile']}, budget={budget_plan['query_budget_per_target']}")

    # ── 4. query_plan (staged) ───────────────────────
    query_plan = build_query_plan(task_config, budget_plan)

    # ── 5. Write merged plan.json ────────────────────
    plan = {
        "intent": intent,
        "task_config": task_config,
        "budget_plan": budget_plan,
        "query_plan": query_plan,
    }
    plan_path = output_paths.search_plan_path(monitor_date, run_mode)
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"[plan] 已写入: {plan_path}")

    is_dry = "dry_run" if dry_run else "live"
    planned_count = _count_queries(query_plan)
    print(f"        planned queries: {planned_count} ({budget_plan['stage']})")

    if dry_run:
        print(f"[dry-run] 搜索计划已完成。使用 --live 执行实际搜索。")
        summary = {
            "user_request": request, "monitor_date": monitor_date, "mode": mode,
            "profile": budget_plan["profile"],
            "targets": [{"brand": t["brand"], "type": t["target_type"],
                          "in_watchlist": t.get("is_in_watchlist", False)}
                        for t in intent["targets"]],
            "time_window": intent["time_window"],
            "stage": budget_plan["stage"],
            "query_budget": budget_plan["query_budget_per_target"],
            "query_count": planned_count,
            "output_dir": str(outdir),
            "run_mode": run_mode,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return intent, task_config, budget_plan, query_plan, None, None, None

    # ── 5. Volc Search API (with cache) ──────────────
    try:
        client = VolcSearchClient()
    except VolcSearchError as e:
        print(f"[error] {e}", file=sys.stderr)
        return intent, task_config, budget_plan, query_plan, None, None, None

    all_queries = []
    for t in query_plan.get("targets", []):
        for q in t.get("queries", []):
            q["target_id"] = t["target_id"]
            all_queries.append(q)

    budget_result_limit = budget_plan.get("result_limit_per_query", 8)
    cache_cfg = budget_plan.get("cache", {})

    print(f"[search] 开始搜索: {len(all_queries)} 条 query, profile={budget_plan['profile']}, cache={'on' if cache_cfg.get('enabled') else 'off'}")
    search_results_list = []
    errors = []
    api_call_count = 0
    cache_hit_count = 0
    cache_miss_count = 0

    for i, q_item in enumerate(all_queries, 1):
        query_text = q_item["query"]
        fmt = f"  [{q_item.get('stage','?')}] [{i}/{len(all_queries)}] {query_text}"
        print(fmt)
        try:
            result = search_with_cache(
                client, query_text, budget_result_limit,
                cache_cfg, monitor_date, mode, q_item.get("target_id", ""),
                provider="doubao_search",
            )
            if result.get("api_called"):
                api_call_count += 1
            if result.get("cache_status") == "hit":
                cache_hit_count += 1
            elif result.get("cache_status") == "miss":
                cache_miss_count += 1
        except Exception as e:
            result = {"query": query_text, "status": "error", "error": str(e),
                      "result_count": 0, "results": [], "api_called": True, "cache_status": "error"}
            api_call_count += 1
        result["meta"] = q_item
        search_results_list.append(result)
        if result.get("status") == "error":
            errors.append({"query": query_text, "error": result.get("error", "unknown")})
            print(f"    ⚠ 失败: {result.get('error', 'unknown')}")
        elif result.get("cache_status") == "hit":
            print(f"    （cache hit）")

    scout_queries = [r for r in search_results_list if r.get("meta", {}).get("stage") == "scout"]
    refine_queries = [r for r in search_results_list if r.get("meta", {}).get("stage") == "refine"]

    raw_envelope = {
        "task_name": "auto_launch_volc_search",
        "mode": mode,
        "monitor_date": monitor_date,
        "user_request": request,
        "run_mode": "live",
        "is_mock": False,
        "profile": budget_plan["profile"],
        "query_count": len(all_queries),
        "api_call_count": api_call_count,
        "cache_hit_count": cache_hit_count,
        "cache_miss_count": cache_miss_count,
        "results": search_results_list,
        "errors": errors,
    }
    raw_path = output_paths.search_raw_path(monitor_date, run_mode)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_envelope, f, ensure_ascii=False, indent=2)
    print(f"[search] 原始结果已写入: {raw_path}")
    success_count = sum(1 for r in search_results_list if r.get("status") == "success")
    total_results = sum(r.get("result_count", 0) for r in search_results_list)
    print(f"         {success_count}/{len(all_queries)} 成功, {total_results} 结果, "
          f"API={api_call_count}, cache_hit={cache_hit_count}")

    # ── 6. Normalize + Audit ─────────────────────────
    normalized = normalize_results(search_results_list, query_plan, run_mode="live")
    norm_path = output_paths.search_normalized_path(monitor_date, run_mode)
    with open(norm_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    print(f"[normalized] {norm_path} ({normalized['total']} 条)")

    audit = build_audit(request, monitor_date, mode, query_plan, search_results_list, normalized,
                        run_mode="live", budget_plan=budget_plan,
                        api_call_count=api_call_count, cache_hit_count=cache_hit_count,
                        cache_miss_count=cache_miss_count,
                        scout_results=scout_queries, refine_results=refine_queries)
    audit_path = output_paths.search_audit_path(monitor_date, run_mode)
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(f"[audit] 已写入: {audit_path}")

    print(f"\n✅ 搜索链路完成。输出目录: {outdir}")
    print(f"   {budget_plan['profile']} | {planned_count} queries | API={api_call_count} | cache_hit={cache_hit_count} | {normalized['total']} items")

    return intent, task_config, budget_plan, query_plan, search_results_list, normalized, audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto Launch 搜索意图转译与执行 v2")
    parser.add_argument("--request", default="看看极氪最近 7 天都有什么动作")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--mode", choices=["brand_watch", "model_watch"])
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--query-profile", choices=["lite_scan", "standard_scan", "deep_scan"])
    parser.add_argument("--max-queries", type=int)
    parser.add_argument("--result-limit", type=int)
    parser.add_argument("--refresh", action="store_true", help="忽略 cache 强制请求 API")
    parser.add_argument("--disable-cache", action="store_true")
    parser.add_argument("--stage", choices=["scout", "refine", "all"], default="all")
    args = parser.parse_args()

    run_pipeline(
        request=args.request, monitor_date=args.date,
        force_mode=args.mode, dry_run=not args.live,
        query_profile=args.query_profile,
        max_queries=args.max_queries, result_limit=args.result_limit,
        refresh=args.refresh, disable_cache=args.disable_cache,
        stage=args.stage,
    )
