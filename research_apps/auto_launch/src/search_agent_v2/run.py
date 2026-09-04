"""CLI 入口 — search_agent_v2

用法:
  # 单车型 dry-run
  python -m auto_launch.src.search_agent_v2.run --request "看看极氪最近 7 天都有什么动作"

  # 多车型批量（dry-run，各车型独立运行，互不混入）
  python -m auto_launch.src.search_agent_v2.run --batch --targets "问界M7" "理想L6" "小鹏G6"

  # 全量 live + fresh（禁止缓存，纯新结果）
  python -m auto_launch.src.search_agent_v2.run --batch --targets "问界M7" "理想L6" "小鹏G6" --live --fresh

  # 单车型 live + 指定 profile
  python -m auto_launch.src.search_agent_v2.run --request "深入分析小米SU7最近一个月传播动作" --profile deep_scan --live
"""

import json, sys, argparse
from pathlib import Path
from datetime import datetime

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent.parent
PROJECT_ROOT = SERVICE_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from auto_launch.src.search_agent_v2.orchestrator import run_agent_loop


def main():
    parser = argparse.ArgumentParser(
        description="Auto Launch Agent 搜索闭环 v2 — 证据驱动的搜索管线"
    )
    parser.add_argument("--request", default=None,
                        help="自然语言搜索请求（单模式）")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="监控日期（YYYY-MM-DD）")
    parser.add_argument("--profile", choices=["lite_scan", "standard_scan", "deep_scan"],
                        help="强制指定搜索 profile（默认根据请求自动推断）")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="dry-run 模式（默认，--live 可取消）")
    parser.add_argument("--live", action="store_false", dest="dry_run",
                        help="实际执行搜索（取消 dry-run）")
    parser.add_argument("--max-rounds", type=int,
                        help="最大搜索轮次（覆盖 profile 设置）")
    parser.add_argument("--max-queries", type=int,
                        help="最大查询总数（覆盖 profile 设置）")
    parser.add_argument("--max-calls", type=int,
                        help="最大 API 调用次数（覆盖 profile 设置）")
    parser.add_argument("--refresh", action="store_true",
                        help="忽略缓存强制请求 API")
    parser.add_argument("--disable-cache", action="store_true",
                        help="禁用缓存")
    parser.add_argument("--fresh", action="store_true",
                        help="全新运行：强制刷新缓存 + 禁用缓存，禁止混入旧结果")
    parser.add_argument("--output",
                        help="输出 JSON 路径（默认输出到 stdout）")
    parser.add_argument("--format", choices=["json", "text"], default="text",
                        help="输出格式（默认 text）")

    # 批量模式
    parser.add_argument("--batch", action="store_true",
                        help="批量模式：为 --targets 中每个车型独立运行")
    parser.add_argument("--targets", nargs="+", default=None,
                        help="批量目标列表，如：--targets '问界M7' '理想L6' '小鹏G6'")

    args = parser.parse_args()

    # ── 批量模式 ────────────────────────────────────────
    if args.batch or args.targets:
        targets = args.targets or []
        if not targets:
            print("[error] 批量模式需要指定 --targets", file=sys.stderr)
            sys.exit(1)

        requests = []
        for t in targets:
            # 为每个车型生成自然语言请求
            requests.append(f"看看 {t} 最近 {7} 天都有什么动作")

        results = []
        for idx, req in enumerate(requests):
            target_name = targets[idx]
            print(f"\n{'#'*70}")
            print(f"# [{idx+1}/{len(requests)}] 开始运行: {target_name}")
            print(f"# 请求: {req}")
            print(f"{'#'*70}\n")

            result = run_agent_loop(
                request=req,
                monitor_date=args.date,
                cli_profile=args.profile,
                dry_run=args.dry_run,
                cli_max_rounds=args.max_rounds,
                cli_max_queries=args.max_queries,
                cli_max_calls=args.max_calls,
                refresh=args.refresh,
                disable_cache=args.disable_cache,
                fresh_run=args.fresh,
            )
            results.append({
                "target": target_name,
                "request": req,
                "result": result,
            })

        if args.format == "json" or args.output:
            output_data = {
                "status": "success",
                "pipeline": "search_agent_v2_batch",
                "monitor_date": args.date,
                "profile": args.profile or "auto",
                "batch_count": len(results),
                "targets": [
                    {
                        "target": r["target"],
                        "conclusion_status": r["result"].get("conclusion_status"),
                        "stop_reason": r["result"].get("stop_reason"),
                        "condition_met": r["result"].get("condition_met"),
                        "total_queries": r["result"].get("total_queries"),
                        "total_api_calls": r["result"].get("total_api_calls"),
                        "metrics": r["result"].get("metrics", {}),
                    }
                    for r in results
                ],
                "full_results": [r["result"] for r in results],
            }
            output_json = json.dumps(output_data, ensure_ascii=False, indent=2)
            if args.output:
                Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(output_json)
                print(f"[output] 已写入: {args.output}")
            else:
                print(output_json)

        # 打印汇总
        print(f"\n{'='*70}")
        print(f"[batch] 批量运行完成 ({len(results)} 个车型)")
        for r in results:
            m = r["result"].get("metrics", {})
            print(f"  {r['target']}: status={r['result'].get('conclusion_status','N/A')}, "
                  f"coverage={m.get('fields_coverage',0):.0%}, "
                  f"queries={r['result'].get('total_queries',0)}, "
                  f"calls={r['result'].get('total_api_calls',0)}")
        return

    # ── 单模式 ──────────────────────────────────────────
    if not args.request:
        parser.print_help()
        sys.exit(1)

    result = run_agent_loop(
        request=args.request,
        monitor_date=args.date,
        cli_profile=args.profile,
        dry_run=args.dry_run,
        cli_max_rounds=args.max_rounds,
        cli_max_queries=args.max_queries,
        cli_max_calls=args.max_calls,
        refresh=args.refresh,
        disable_cache=args.disable_cache,
        fresh_run=args.fresh,
    )

    if args.format == "json" or args.output:
        output_data = {
            "status": "success",
            "pipeline": "search_agent_v2",
            "user_request": args.request,
            "monitor_date": args.date,
            "profile": result["profile"],
            "total_rounds": result["total_rounds"],
            "total_queries": result["total_queries"],
            "total_api_calls": result["total_api_calls"],
            "conclusion_status": result.get("conclusion_status"),
            "stop_reason": result.get("stop_reason"),
            "condition_met": result.get("condition_met"),
            "final_evidence": result.get("final_evidence"),
            "final_gap": result.get("final_gap"),
        }
        output_json = json.dumps(output_data, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_json)
            print(f"[output] 已写入: {args.output}")
        else:
            print(output_json)


if __name__ == "__main__":
    main()
