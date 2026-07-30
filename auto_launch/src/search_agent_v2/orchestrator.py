"""orchestrator — Agent 搜索主循环

架构:
  ┌──────────────────────────────────────────────────┐
  │  Orchestrator Loop                               │
  │                                                  │
  │  1. initial_queries → search → evaluate          │
  │  2. evaluate → gap_analyze → rewrite → search    │
  │  3. repeat until stop_condition or hard_limit     │
  │                                                  │
  │  每轮输出: search_results + evidence + gap        │
  │  最终输出: conclusion_status + stop_reason         │
  └──────────────────────────────────────────────────┘
"""

import json, sys, yaml, io, contextlib
from pathlib import Path
from datetime import datetime

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent.parent
PROJECT_ROOT = SERVICE_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from auto_launch.src.volc_search_client import VolcSearchClient, VolcSearchError
from auto_launch.src.volc_search_daily import run_pipeline as v1_intent_compile
from auto_launch.src.search_cache import search_with_cache
from auto_launch.src import output_paths
from auto_launch.src.search_agent_v2.evidencer import evaluate_evidence
from auto_launch.src.search_agent_v2.gap_analyzer import analyze_gaps
from auto_launch.src.search_agent_v2.query_rewriter import rewrite_queries

CONFIG_PATH = SERVICE_ROOT / "configs" / "search_agent_v2.yaml"


def _load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _load_initial_queries(mode: str, brand: str, days: int) -> list[dict]:
    config = _load_config()
    initial = config.get("initial_queries", {}).get(mode, [])
    queries = []
    for tmpl in initial:
        q_text = tmpl["pattern"].replace("{brand}", brand).replace("{days}", str(days))
        queries.append({
            "query": q_text,
            "purpose": tmpl.get("purpose", ""),
            "source_tier_focus": tmpl.get("source_tier_focus", []),
            "gap_driven": False,
            "gap_field": None,
            "round": 1,
        })
    return queries


def _select_profile(request: str, config: dict, cli_profile: str = None) -> tuple[str, dict]:
    if cli_profile:
        name = cli_profile
    else:
        if any(kw in request for kw in ["深入", "全面", "复盘", "详细", "deep"]):
            name = "deep_scan"
        else:
            name = "standard_scan"
    profiles = config.get("query_profiles", {})
    return name, profiles.get(name, profiles.get("standard_scan", {}))


def run_agent_loop(request: str, monitor_date: str = None,
                   cli_profile: str = None, dry_run: bool = True,
                   cli_max_rounds: int = None, cli_max_queries: int = None,
                   cli_max_calls: int = None,
                   refresh: bool = False, disable_cache: bool = False):
    """执行 Agent 搜索闭环

    Returns:
        final: {
            "user_request": str,
            "monitor_date": str,
            "profile": str,
            "rounds": list[dict],       # 每轮详情
            "final_evidence": dict,
            "final_gap": dict,
            "conclusion_status": str | None,
            "stop_reason": str | None,
            "condition_met": str | None,
            "total_queries": int,
            "total_api_calls": int,
        }
    """
    if monitor_date is None:
        monitor_date = datetime.now().strftime("%Y-%m-%d")

    # ── 1. 编译意图（复用 V1 的意图编译器）───────────────
    with contextlib.redirect_stdout(io.StringIO()):
        intent, task_config, _, query_plan = v1_intent_compile(
            request, monitor_date, dry_run=True
        )[:4]

    mode = task_config.get("mode", "brand_watch")
    targets = task_config.get("targets", [])
    brand = targets[0].get("brand", "") if targets else ""
    time_window = task_config.get("time_window", {})
    days = time_window.get("days", 7)

    # ── 2. 加载配置 ─────────────────────────────────────
    config = _load_config()
    profile_name, profile = _select_profile(request, config, cli_profile)

    hard_limits = config.get("search_stop_policy", {}).get("hard_limits", {})
    max_rounds = cli_max_rounds or profile.get("max_rounds", hard_limits.get("max_rounds", 3))
    max_queries = cli_max_queries or profile.get("max_queries", hard_limits.get("max_queries", 10))
    max_calls = cli_max_calls or profile.get("max_provider_calls", hard_limits.get("max_provider_calls", 15))
    acceptable_evidence = profile.get("acceptable_evidence", ["confirmed"])

    field_defs = config.get("field_definitions", {})

    print(f"[agent] profile={profile_name}, max_rounds={max_rounds}, max_queries={max_queries}, max_calls={max_calls}")
    print(f"[agent] acceptable_evidence={acceptable_evidence}")

    # ── 3. 初始化 ───────────────────────────────────────
    all_results = []
    all_queries = []
    round_num = 0
    total_api_calls = 0
    rounds_log = []
    final_evidence = {"condition_met": None, "conclusion_status": None, "stop_reason": None, "metrics": {"independent_sources": 0, "official_sources": 0, "fields_coverage": 0.0}}
    final_gap = {"missing_fields": [], "next_search_objectives": []}

    if dry_run:
        print(f"[agent] DRY-RUN: 不执行实际搜索")

    # ── 4. Agent Loop ───────────────────────────────────
    while True:
        round_num += 1
        print(f"\n{'='*60}")
        print(f"[agent] Round {round_num}")

        if round_num == 1:
            # 初始搜索
            new_queries = _load_initial_queries(mode, brand, days)
        else:
            # 缺口驱动改写
            query_budget = max(1, max_queries - len(all_queries))
            new_queries = rewrite_queries(gap, task_config, all_queries, round_num, query_budget)

        if not new_queries:
            print(f"[agent] 无新查询生成，停止")
            if not dry_run:
                final_evidence = evaluate_evidence(
                    all_results, config, field_defs, mode, round_num, total_api_calls
                )
                final_gap = analyze_gaps(
                    all_results, task_config,
                    set(final_evidence["covered_fields"]), set(final_evidence["missing_fields"]),
                    final_evidence["metrics"],
                )
            break

        # 硬限制检查
        if len(all_queries) + len(new_queries) > max_queries:
            new_queries = new_queries[:max_queries - len(all_queries)]
        if total_api_calls >= max_calls:
            print(f"[agent] 达到 API 调用上限 ({max_calls})")
            break

        print(f"[agent] 本轮 {len(new_queries)} 条查询")
        for idx, q in enumerate(new_queries):
            gap_mark = " [gap]" if q.get("gap_driven") else ""
            print(f"  Q{len(all_queries)+idx+1}: {q['query']}{gap_mark}")

        if dry_run:
            all_queries.extend(new_queries)
            all_results.extend([{
                "query": q["query"],
                "status": "dry_run",
                "result_count": 0,
                "results": [],
                "api_called": False,
            } for q in new_queries])
            round_log = {
                "round": round_num,
                "new_queries": new_queries,
                "mode": "dry_run",
            }
            rounds_log.append(round_log)

            # 模拟证据评估以便输出计划
            mock_evidence = evaluate_evidence(
                all_results, config, field_defs, mode, round_num, total_api_calls
            )
            gap = analyze_gaps(
                all_results, task_config,
                set(mock_evidence["covered_fields"]),
                set(mock_evidence["missing_fields"]),
                mock_evidence["metrics"],
            )
            final_evidence = mock_evidence
            final_gap = gap

            print(f"[agent] evidence: {mock_evidence['condition_met'] or 'pending'}")
            print(f"[agent] missing_fields: {gap['missing_fields']}")
            print(f"[agent] objectives: {gap['next_search_objectives'][:3]}")

            if final_evidence["should_stop"]:
                print(f"\n[agent] 停止条件满足: {final_evidence['condition_met']}")
                print(f"  conclusion_status: {final_evidence['conclusion_status']}")
                print(f"  stop_reason: {final_evidence['stop_reason']}")
                break

            if round_num >= max_rounds:
                print(f"\n[agent] 达到最大轮次 ({max_rounds})")
                break

            continue

        # ── LIVE: 执行搜索 ────────────────────────────────
        try:
            client = VolcSearchClient()
        except VolcSearchError as e:
            print(f"[error] {e}", file=sys.stderr)
            break

        cache_cfg = {
            "enabled": not disable_cache,
            "ttl_hours": 24,
            "refresh": refresh,
            "root_dir": str(output_paths.cache_dir()),
        }

        round_results = []
        for q_item in new_queries:
            if total_api_calls >= max_calls:
                print(f"[agent] 达到 API 调用上限，停止搜索")
                break
            query_text = q_item["query"]
            result_limit = 8
            try:
                result = search_with_cache(
                    client, query_text, result_limit,
                    cache_cfg, monitor_date, mode, targets[0].get("target_id", ""),
                    provider="doubao_search",
                )
                if result.get("api_called"):
                    total_api_calls += 1
                cache_status = result.get("cache_status", "?")
                api_mark = " [API]" if result.get("api_called") else " [cache]"
                print(f"  {query_text}{api_mark} ({cache_status}, {result.get('result_count', 0)} results)")
            except Exception as e:
                result = {"query": query_text, "status": "error", "error": str(e),
                          "result_count": 0, "results": [], "api_called": True}
                total_api_calls += 1
                print(f"  {query_text} ⚠ {e}")
            result["meta"] = q_item
            round_results.append(result)

        all_results.extend(round_results)
        all_queries.extend(new_queries)

        round_log = {
            "round": round_num,
            "new_queries": new_queries,
            "results": round_results,
            "mode": "live",
        }
        rounds_log.append(round_log)

        # ── 5. 证据评估 ──────────────────────────────────
        evidence = evaluate_evidence(
            all_results, config, field_defs, mode, round_num, total_api_calls
        )
        print(f"\n[evidence] independent_sources={evidence['metrics']['independent_sources']}, "
              f"official_sources={evidence['metrics']['official_sources']}, "
              f"fields_coverage={evidence['metrics']['fields_coverage']}")
        print(f"[evidence] condition_met={evidence['condition_met'] or 'pending'}")
        print(f"[evidence] covered_fields={evidence['covered_fields']}")
        print(f"[evidence] missing_fields={evidence['missing_fields']}")

        if evidence["should_stop"]:
            print(f"\n[agent] ✅ 停止条件满足: {evidence['condition_met']}")
            print(f"  conclusion_status: {evidence['conclusion_status']}")
            print(f"  stop_reason: {evidence['stop_reason']}")
            final_evidence = evidence
            final_gap = gap if round_num > 1 else analyze_gaps(
                all_results, task_config,
                set(evidence["covered_fields"]), set(evidence["missing_fields"]),
                evidence["metrics"],
            )
            break

        # 硬限制深度检查（如果有剩余 API）
        if round_num >= max_rounds:
            print(f"\n[agent] 达到最大轮次 ({max_rounds})")
            evidence = evaluate_evidence(
                all_results, config, field_defs, mode, round_num, total_api_calls
            )
            final_evidence = evidence
            final_gap = analyze_gaps(
                all_results, task_config,
                set(evidence["covered_fields"]), set(evidence["missing_fields"]),
                evidence["metrics"],
            )
            break

        # ── 6. 缺口分析（为下一轮做准备）───────────────────
        gap = analyze_gaps(
            all_results, task_config,
            set(evidence["covered_fields"]), set(evidence["missing_fields"]),
            evidence["metrics"],
        )
        print(f"[gap] objectives: {gap['next_search_objectives'][:3]}")

    # ── 7. 汇总 ──────────────────────────────────────────
    final = {
        "user_request": request,
        "monitor_date": monitor_date,
        "profile": profile_name,
        "rounds": rounds_log,
        "total_rounds": round_num,
        "total_queries": len(all_queries),
        "total_api_calls": total_api_calls,
        "final_evidence": final_evidence,
        "final_gap": final_gap,
        "conclusion_status": final_evidence.get("conclusion_status"),
        "stop_reason": final_evidence.get("stop_reason"),
        "condition_met": final_evidence.get("condition_met"),
        "metrics": final_evidence.get("metrics", {}),
    }

    # 打印摘要
    mode_label = "(dry-run)" if dry_run else "(live)"
    print(f"\n{'='*60}")
    print(f"[agent] 搜索闭环完成 {mode_label}")
    print(f"  profile:          {profile_name}")
    print(f"  轮次:             {round_num}")
    print(f"  总查询数:         {len(all_queries)}")
    print(f"  API 调用:         {total_api_calls}")
    print(f"  停止条件:         {final_evidence.get('condition_met', 'N/A')}")
    print(f"  结论状态:         {final_evidence.get('conclusion_status', 'N/A')}")
    print(f"  停止原因:         {final_evidence.get('stop_reason', 'N/A')}")
    print(f"  独立来源:         {final_evidence['metrics'].get('independent_sources', 0)}")
    print(f"  官方来源:         {final_evidence['metrics'].get('official_sources', 0)}")
    print(f"  字段覆盖率:       {final_evidence['metrics'].get('fields_coverage', 0.0):.0%}")

    return final
