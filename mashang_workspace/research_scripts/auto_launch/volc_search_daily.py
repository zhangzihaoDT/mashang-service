"""
volc_search_daily.py — Auto Launch 搜索意图转译与执行主脚本。

完整链路:
  user_request → search_intent → search_task_config → query_plan
  → Volc Search API → raw results → normalized results → search_audit

用法:
  python volc_search_daily.py --request "看看极氪最近 7 天都有什么动作" --date 2026-07-02
  python volc_search_daily.py --request "看看极氪最近 7 天都有什么动作" --date 2026-07-02 --live
  python volc_search_daily.py --request "看看问界 M7 最近 7 天权益和价格有什么变化" --date 2026-07-02 --mode model_watch
"""

import json, sys, os, argparse
from pathlib import Path
from datetime import datetime

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT))

from research_scripts.auto_launch.search_intent_compiler import compile_intent
from research_scripts.auto_launch.search_task_config_builder import build_task_config
from research_scripts.auto_launch.volc_search_query_builder import build_query_plan
from research_scripts.auto_launch.volc_search_client import VolcSearchClient, VolcSearchError
from research_scripts.auto_launch.normalize_search_results import normalize_results, build_audit

OUTPUT_BASE = WORKSPACE_ROOT / "outputs" / "auto_launch" / "search"


def _collect_queries(query_plan: dict) -> list[dict]:
    """从 query_plan 中平铺所有 query，附上 target_id"""
    all_queries = []
    for t in query_plan.get("targets", []):
        for q in t.get("queries", []):
            q["target_id"] = t["target_id"]
            all_queries.append(q)
    return all_queries


def run_pipeline(request: str, monitor_date: str, force_mode: str = None,
                 dry_run: bool = True):
    """
    执行完整的搜索意图转译与搜索链路。

    dry_run=True (默认): 只生成 intent / config / plan，不调 API。
    dry_run=False:        全链路执行，含 API 调用、正常化、审计。
    """

    # ── 1. search_intent ─────────────────────────────
    intent = compile_intent(request, monitor_date, None)
    if force_mode:
        intent["mode"] = force_mode

    mode = intent["mode"]
    outdir = OUTPUT_BASE / monitor_date / mode
    outdir.mkdir(parents=True, exist_ok=True)

    intent_path = outdir / "search_intent.json"
    with open(intent_path, "w", encoding="utf-8") as f:
        json.dump(intent, f, ensure_ascii=False, indent=2)
    print(f"[intent] 已写入: {intent_path}")

    # ── 2. search_task_config ────────────────────────
    config_path = outdir / "search_task_config.json"
    task_config = build_task_config(intent, str(config_path))

    # ── 3. query_plan ────────────────────────────────
    plan_path = outdir / "query_plan.json"
    query_plan = build_query_plan(task_config, str(plan_path))

    if dry_run:
        print(f"[dry-run] 搜索意图转译与 query plan 已完成。使用 --live 执行实际搜索。")
        summary = {
            "user_request": request,
            "monitor_date": monitor_date,
            "mode": mode,
            "intent_type": intent["intent_type"],
            "targets": [
                {"brand": t["brand"], "model": t.get("model"),
                 "type": t["target_type"], "in_watchlist": t.get("is_in_watchlist", False)}
                for t in intent["targets"]
            ],
            "time_window": intent["time_window"],
            "event_type_count": len(intent["event_scope"]["event_type_ids"]),
            "query_count": sum(len(t.get("queries", [])) for t in query_plan["targets"]),
            "output_dir": str(outdir),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return intent, task_config, query_plan, None, None, None

    # ── 4. Volc Search API ───────────────────────────
    try:
        client = VolcSearchClient()
    except VolcSearchError as e:
        print(f"[error] {e}", file=sys.stderr)
        return intent, task_config, query_plan, None, None, None

    all_queries = _collect_queries(query_plan)
    result_limit = task_config.get("query_budget", {}).get("result_limit_per_query", 10)

    print(f"[search] 开始搜索: {len(all_queries)} 条 query, target={mode}")
    search_results_list = []
    errors = []
    for i, q_item in enumerate(all_queries, 1):
        query_text = q_item["query"]
        print(f"  [{i}/{len(all_queries)}] {query_text}")
        try:
            result = client.search(query_text, result_limit)
        except Exception as e:
            result = {"query": query_text, "status": "error", "error": str(e), "result_count": 0, "results": []}
        result["meta"] = q_item
        search_results_list.append(result)
        if result.get("status") == "error":
            errors.append({"query": query_text, "error": result.get("error", "unknown")})
            print(f"    ⚠ 失败: {result.get('error', 'unknown')}")

    raw_envelope = {
        "task_name": "auto_launch_volc_search",
        "mode": mode,
        "monitor_date": monitor_date,
        "user_request": request,
        "query_count": len(all_queries),
        "results": search_results_list,
        "errors": errors,
    }
    raw_path = outdir / "search_results.raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_envelope, f, ensure_ascii=False, indent=2)
    print(f"[search] 原始结果已写入: {raw_path}")
    success_count = sum(1 for r in search_results_list if r.get("status") == "success")
    total_results = sum(r.get("result_count", 0) for r in search_results_list)
    print(f"         {success_count}/{len(all_queries)} 查询成功, 共 {total_results} 条结果")

    # ── 5. Normalize + Audit ─────────────────────────
    normalized = normalize_results(search_results_list, query_plan)
    norm_path = outdir / "search_results.normalized.json"
    with open(norm_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    print(f"[normalized] 标准化结果已写入: {norm_path} ({normalized['total']} 条)")

    audit = build_audit(request, monitor_date, mode, query_plan, search_results_list, normalized)
    audit_path = outdir / "search_audit.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(f"[audit] 搜索审计已写入: {audit_path}")

    # ── 完成 ─────────────────────────────────────────
    print(f"\n✅ 搜索链路完成。输出目录: {outdir}")
    print(f"   意图: {intent_path.name} | 配置: {config_path.name} | 计划: {plan_path.name}")
    print(f"   原始结果: {raw_path.name} | 标准化: {norm_path.name} | 审计: {audit_path.name}")

    return intent, task_config, query_plan, search_results_list, normalized, audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto Launch 搜索意图转译与执行")
    parser.add_argument("--request", default="看看极氪最近 7 天都有什么动作", help="用户自然语言请求")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="监控日期")
    parser.add_argument("--mode", choices=["brand_watch", "model_watch"], help="强制指定监控模式")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="仅生成意图/配置/计划，不调用 API（默认开启）")
    parser.add_argument("--live", action="store_true",
                        help="实际执行搜索（覆盖 --dry-run）")
    args = parser.parse_args()

    run_pipeline(
        request=args.request,
        monitor_date=args.date,
        force_mode=args.mode,
        dry_run=not args.live,
    )
