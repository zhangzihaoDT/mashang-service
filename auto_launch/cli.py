"""
Auto Launch CLI — 统一命令行入口。

用法:
  python -m auto_launch.cli daily --brand im --brand-name 智己
  python -m auto_launch.cli daily --brand im --brand-name 智己 --live
  python -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作"
  python -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作" --live
  python -m auto_launch.cli normalize --raw <path> --query-plan <path>
"""

import sys, argparse
from pathlib import Path
from datetime import datetime

# Ensure project root is on path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def cmd_daily(args):
    from auto_launch.src.brand_daily_marketing_watch import _run, DEFAULT_OUTPUT_BASE
    _run(
        brand=args.brand, brand_name=args.brand_name,
        monitor_date=args.date, window_hours=args.window_hours,
        query_profile=args.query_profile, out_dir=str(DEFAULT_OUTPUT_BASE),
        dry_run=not args.live, refresh=args.refresh,
    )


def cmd_search(args):
    from auto_launch.src.volc_search_daily import run_pipeline
    run_pipeline(
        request=args.request, monitor_date=args.date,
        force_mode=args.mode, dry_run=not args.live,
        query_profile=args.query_profile,
        max_queries=args.max_queries, result_limit=args.result_limit,
        refresh=args.refresh, disable_cache=args.disable_cache,
        stage=args.stage,
    )


def cmd_normalize(args):
    from auto_launch.src.normalize_search_results import process
    normalized, audit = process(args.raw, args.query_plan, args.output_prefix)
    print(f"Normalized: {normalized['total']} items | Audit: {audit['query_count']} queries")


def main():
    parser = argparse.ArgumentParser(description="Auto Launch Service CLI")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # daily
    p_daily = sub.add_parser("daily", help="自有品牌每日营销监控")
    p_daily.add_argument("--brand", default="im")
    p_daily.add_argument("--brand-name", default="智己")
    p_daily.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    p_daily.add_argument("--window-hours", type=int, default=24)
    p_daily.add_argument("--query-profile", default="balanced")
    p_daily.add_argument("--live", action="store_true")
    p_daily.add_argument("--refresh", action="store_true")

    # search
    p_search = sub.add_parser("search", help="搜索意图转译与执行")
    p_search.add_argument("--request", default="看看极氪最近 7 天都有什么动作")
    p_search.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    p_search.add_argument("--mode", choices=["brand_watch", "model_watch"])
    p_search.add_argument("--live", action="store_true")
    p_search.add_argument("--query-profile", choices=["lite_scan", "standard_scan", "deep_scan"])
    p_search.add_argument("--max-queries", type=int)
    p_search.add_argument("--result-limit", type=int)
    p_search.add_argument("--refresh", action="store_true")
    p_search.add_argument("--disable-cache", action="store_true")
    p_search.add_argument("--stage", choices=["scout", "refine", "all"], default="all")

    # normalize
    p_norm = sub.add_parser("normalize", help="标准化搜索结果")
    p_norm.add_argument("--raw", required=True)
    p_norm.add_argument("--query-plan", required=True)
    p_norm.add_argument("--output-prefix")

    args = parser.parse_args()
    if args.command == "daily":
        cmd_daily(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "normalize":
        cmd_normalize(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
