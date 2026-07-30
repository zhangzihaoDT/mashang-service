"""CLI 入口 — search_agent_v2

用法:
  # dry-run（默认，不调用 API）
  python -m auto_launch.src.search_agent_v2.run --request "看看极氪最近 7 天都有什么动作"

  # live 执行
  python -m auto_launch.src.search_agent_v2.run --request "看看极氪最近 7 天都有什么动作" --live

  # 指定 profile
  python -m auto_launch.src.search_agent_v2.run --request "深入分析小米SU7最近一个月传播动作" --profile deep_scan

  # 指定输出
  python -m auto_launch.src.search_agent_v2.run --request "看看问界 M7 最近权益变化" --output outputs/agent_run.json
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
    parser.add_argument("--request", default="看看极氪最近 7 天都有什么动作",
                        help="自然语言搜索请求")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="监控日期（YYYY-MM-DD）")
    parser.add_argument("--profile", choices=["lite_scan", "standard_scan", "deep_scan"],
                        help="强制指定搜索 profile（默认根据请求自动推断）")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="dry-run 模式（默认）")
    parser.add_argument("--live", action="store_true",
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
    parser.add_argument("--output",
                        help="输出 JSON 路径（默认输出到 stdout）")
    parser.add_argument("--format", choices=["json", "text"], default="text",
                        help="输出格式（默认 text）")

    args = parser.parse_args()

    result = run_agent_loop(
        request=args.request,
        monitor_date=args.date,
        cli_profile=args.profile,
        dry_run=not args.live,
        cli_max_rounds=args.max_rounds,
        cli_max_queries=args.max_queries,
        cli_max_calls=args.max_calls,
        refresh=args.refresh,
        disable_cache=args.disable_cache,
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
