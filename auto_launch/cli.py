"""
Auto Launch CLI — 统一命令行入口。

用法:
  python -m auto_launch.cli daily --brand im --brand-name 智己
  python -m auto_launch.cli daily --brand im --brand-name 智己 --live
  python -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作"
  python -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作" --live
  python -m auto_launch.cli normalize --raw <path> --query-plan <path>
  python -m auto_launch.cli source-audit --watchlist priority --days 7
  python -m auto_launch.cli source-audit --watchlist ls8 --days 7
"""

import sys, argparse
from pathlib import Path
from datetime import datetime, timedelta

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
    if args.to_facts and args.live:
        _daily_to_facts(args)


def _daily_to_facts(args):
    """将 daily 监控的 normalized 结果写入事实库。"""
    from auto_launch.src.inbox_filter import classify
    from auto_launch.src.fact_store import FactStore
    import json

    out_dir = Path(__file__).resolve().parent / "outputs" / "owned_brand_daily" / args.date.replace("-", "")
    norm_file = out_dir / "normalized_search_results.json"
    if not norm_file.exists():
        print("[daily --to-facts] normalized 结果不存在，跳过")
        return

    with open(norm_file) as f:
        data = json.load(f)

    items = data.get("items", [])
    if not items:
        print("[daily --to-facts] 无 items 可处理")
        return

    store = FactStore()
    kept = 0
    for item in items:
        inbox_item = {
            "brand": args.brand_name,
            "model": "",
            "event_type": (item.get("matched_event_type_ids") or [None])[0] if item.get("matched_event_type_ids") else None,
            "title": item.get("title", "")[:200],
            "claim": (item.get("snippet") or "")[:500],
            "source_name": item.get("source_name", ""),
            "source_url": item.get("url", ""),
            "source_tier": item.get("source_tier_guess", ""),
            "input_channel": "daily_to_facts",
        }
        result = classify(inbox_item)
        if result["decision"] == "keep":
            fr = store.insert(inbox_item)
            kept += 1

    print(f"[daily --to-facts] 完成: {kept} keep (from {len(items)} items)")


def cmd_search(args):
    from auto_launch.src.volc_search_daily import run_pipeline
    result = run_pipeline(
        request=args.request, monitor_date=args.date,
        force_mode=args.mode, dry_run=not args.live,
        query_profile=args.query_profile,
        max_queries=args.max_queries, result_limit=args.result_limit,
        refresh=args.refresh, disable_cache=args.disable_cache,
        stage=args.stage,
    )
    if args.to_facts and not args.live:
        print("[to-facts] dry-run 模式下不写入事实库（需 --live 执行实际搜索）")
    elif args.to_facts:
        _search_to_facts(result)


def _search_to_facts(pipeline_result):
    """将 Volc Search 的 normalized items 通过 inbox_filter 写入 fact_store。"""
    from auto_launch.src.inbox_filter import classify
    from auto_launch.src.fact_store import FactStore

    intent, task_config, budget_plan, query_plan, search_results_list, normalized, audit = pipeline_result

    if not normalized or not normalized.get("items"):
        print("[to-facts] 无 normalized items 可处理")
        return

    # Build target_id → (brand, model) mapping from query_plan
    target_map = {}
    for t in query_plan.get("targets", []):
        target_map[t["target_id"]] = {
            "brand": t.get("brand", "") or "",
            "model": t.get("model", "") or "",
        }

    store = FactStore()
    kept = 0
    discarded = 0

    for item in normalized["items"]:
        tid = item.get("target_id", "")
        tm = target_map.get(tid, {"brand": "", "model": ""})

        inbox_item = {
            "brand": tm["brand"],
            "model": tm["model"],
            "event_type": (item.get("matched_event_type_ids") or [None])[0] if item.get("matched_event_type_ids") else None,
            "title": item.get("title", "")[:200],
            "claim": (item.get("snippet") or "")[:500],
            "source_name": item.get("source_name", ""),
            "source_url": item.get("url", ""),
            "source_tier": item.get("source_tier_guess", ""),
            "input_channel": "search_to_facts",
        }

        result = classify(inbox_item)
        if result["decision"] == "keep":
            fr = store.insert(inbox_item)
            kept += 1
            action = "新增" if fr["action"] == "inserted" else "更新"
            title_short = (inbox_item["title"] or "")[:50]
            print(f"  [keep] {action} fact_id={fr['fact_id']} seen={fr['seen_count']} — {title_short}")
        else:
            discarded += 1

    print(f"\n[to-facts] 完成: {kept} keep / {discarded} discard")


def cmd_normalize(args):
    from auto_launch.src.normalize_search_results import process
    normalized, audit = process(args.raw, args.query_plan, args.output_prefix)
    print(f"Normalized: {normalized['total']} items | Audit: {audit['query_count']} queries")


def cmd_inbox(args):
    from auto_launch.src.inbox_runner import run_file, run_interactive
    if args.input:
        summary = run_file(args.input, date=args.date)
        from auto_launch.src.inbox_runner import _print_summary
        _print_summary(summary)
    else:
        run_interactive()


def cmd_facts(args):
    from auto_launch.src.fact_store import FactStore
    store = FactStore()

    if args.audit:
        report = store.audit()
        if report["total"] == 0:
            print("事实库为空。")
            return
        print(f"=== Fact Quality Audit ===")
        print(f"Total facts: {report['total']}")
        print()
        print("Field completeness:")
        for f, v in report["completeness"].items():
            bar = "█" * int(v["pct"] / 5) + "░" * (20 - int(v["pct"] / 5))
            print(f"  {f:<16} {bar} {v['pct']}% ({v['filled']}/{v['total']})")
        print()
        print(f"Source tier distribution:")
        for tier, cnt in report["source_tier_distribution"].items():
            print(f"  {tier:<30} {cnt}")
        print()
        print(f"Input channel distribution:")
        for ch, cnt in report["input_channel_distribution"].items():
            print(f"  {ch:<20} {cnt}")
        print()
        print(f"Dedup: {report['dedup']['unique_fingerprints']} unique / {report['total']} total "
              f"(dup rate: {report['dedup']['duplicate_rate_pct']}%)")
        print(f"Quality flags: {report['quality_flags']['no_brand']} no_brand, "
              f"{report['quality_flags']['no_event_type']} no_event_type")
        if report["warnings"]:
            print()
            print("Warnings:")
            for w in report["warnings"]:
                print(f"  ⚠ {w}")
        return

    if args.stats:
        stats = store.get_stats()
        print(f"Total facts: {stats['total_facts']}")
        for label, data in [("Brand", "by_brand"), ("Source Tier", "by_source_tier"),
                            ("Event Type", "by_event_type"), ("Input Channel", "by_input_channel")]:
            if stats.get(data):
                print(f"\nBy {label}:")
                for k, v in stats[data].items():
                    print(f"  {k or '(空)':<20} {v}")
        return

    if args.stats_by:
        data = store.stats_by(args.stats_by)
        print(f"By {args.stats_by}:")
        for k, v in data.items():
            print(f"  {k or '(空)':<25} {v}")
        return

    if args.export:
        results = store.query(brand=args.brand, event_type=args.event_type,
                              model=args.model, source_tier=args.source_tier,
                              days=args.days, since=args.since, until=args.until,
                              limit=args.limit)
        print(store.export_json(results))
        return

    facts = store.query(brand=args.brand, event_type=args.event_type,
                        model=args.model, source_tier=args.source_tier,
                        days=args.days, since=args.since, until=args.until,
                        limit=args.limit)
    if not facts:
        print("No facts found.")
        return
    print(f"{'id':<5} {'brand':<10} {'model':<12} {'event_type':<18} {'tier':<20} {'seen':<5} {'last_seen':<18} {'title':<45}")
    print("-" * 133)
    for f in facts:
        title = (f["title"] or "")[:43]
        tier = (f["source_tier"] or "-")[:18]
        print(f"{f['fact_id']:<5} {(f['brand'] or '-'):<10} {(f['model'] or '-'):<12} {(f['event_type'] or '-'):<18} {tier:<20} {f['seen_count']:<5} {(f['last_seen'] or '')[:17]:<18} {title:<45}")


def cmd_brief(args):
    from auto_launch.src.fact_store import FactStore
    from auto_launch.src.brief_renderer import generate_brief

    store = FactStore()
    facts = store.query(brand=args.brand, event_type=args.event_type,
                        model=args.model, days=args.days,
                        since=args.since, until=args.until,
                        limit=args.limit)

    brief_md = generate_brief(facts)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(brief_md, encoding="utf-8")
        print(f"[brief] 已写入: {args.output}")
    else:
        print(brief_md)


def cmd_run_day(args):
    from auto_launch.src.operating_loop import run_day

    brief_output = args.brief_output or None
    result = run_day(
        monitor_date=args.date, brand=args.brand, brand_name=args.brand_name,
        window_hours=args.window_hours, live=args.live,
        brief_output=brief_output,
    )
    print(f"[run-day] {result['monitor_date']} {result['brand_name']} | "
          f"live={result['live']} | brief={result['brief_facts']} facts")
    for k, v in result["outputs"].items():
        print(f"  {k}: {v}")


def cmd_replay(args):
    if args.input_dir:
        from auto_launch.src.operating_loop import replay_from_fixtures
        r = replay_from_fixtures(args.input_dir, reset_store=args.reset_store)
        if "error" in r:
            print(f"[replay] error: {r['error']}")
            return
        print(f"[replay] {r['days']} days, {r['total_raw']} raw, {r['total_keep']} keep")
        print(f"  inserted={r['total_inserted']} updated={r['total_updated']}")
        print(f"  total_facts={r['total_facts']} dup_rate={r['duplicate_rate']}%")
        print(f"  top_brands: {r['top_brands']}")
        for d in r["per_day"]:
            print(f"  Day {d['day']}: {d['file']}  raw={d['raw']} keep={d['keep']}")
        return

    from auto_launch.src.operating_loop import run_day
    from datetime import datetime as dt
    fmt = "%Y-%m-%d"
    start = dt.strptime(args.start_date, fmt)
    end = dt.strptime(args.end_date, fmt) if args.end_date else start
    if end < start:
        start, end = end, start
    results = []
    current = start
    total = (end - start).days + 1
    for i in range(total):
        ds = current.strftime(fmt)
        print(f"[replay] ({i+1}/{total}) {ds} ...")
        r = run_day(monitor_date=ds, brand=args.brand, brand_name=args.brand_name, live=args.live)
        results.append(r)
        current += timedelta(days=1)
    print(f"[replay] 完成: {total} 天")
    for r in results:
        print(f"  {r['monitor_date']}  kept={r['kept']}  brief={r['brief_facts']} facts")


def cmd_source_audit(args):
    import json
    from auto_launch.src.fact_store import FactStore
    from auto_launch.src import source_auditor

    store = FactStore()
    facts = store.query(days=args.days, limit=args.limit)
    report = source_auditor.audit(facts, watchlist=args.watchlist)

    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        if args.format == "json":
            p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            md = source_auditor.render_markdown(report)
            p.write_text(md, encoding="utf-8")
        print(f"[source-audit] 已写入: {p}")
    elif args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(source_auditor.render_markdown(report))


def cmd_timeline(args):
    from auto_launch.src.fact_store import FactStore
    from auto_launch.src.timeline_renderer import generate_timeline

    store = FactStore()
    facts = store.query(brand=args.brand, model=args.model,
                        event_type=args.event_type,
                        days=args.days, since=args.since, until=args.until,
                        limit=args.limit)
    md = generate_timeline(facts, brand=args.brand, model=args.model)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"[timeline] 已写入: {args.output}")
    else:
        print(md)


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
    p_daily.add_argument("--to-facts", action="store_true", help="将监控结果写入事实库")

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
    p_search.add_argument("--to-facts", action="store_true", help="将搜索结果写入事实库")

    # normalize
    p_norm = sub.add_parser("normalize", help="标准化搜索结果")
    p_norm.add_argument("--raw", required=True)
    p_norm.add_argument("--query-plan", required=True)
    p_norm.add_argument("--output-prefix")

    # inbox
    p_inbox = sub.add_parser("inbox", help="Inbox Intake — 解析 daily run 并写入事实库")
    p_inbox.add_argument("--input", help="ChatGPT daily run markdown 文件路径")
    p_inbox.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="事实日期")

    # facts
    p_facts = sub.add_parser("facts", help="查询事实库")
    p_facts.add_argument("--brand", help="按品牌筛选")
    p_facts.add_argument("--model", help="按车型筛选")
    p_facts.add_argument("--event-type", help="按事件类型筛选")
    p_facts.add_argument("--source-tier", help="按信源等级筛选 (e.g. tier_1_official)")
    p_facts.add_argument("--days", type=int, default=7, help="最近 N 天 (default: 7)")
    p_facts.add_argument("--since", help="起始时间 (ISO format, e.g. 2026-07-01T00:00:00)")
    p_facts.add_argument("--until", help="截止时间 (ISO format)")
    p_facts.add_argument("--limit", type=int, default=50, help="最大返回条数 (default: 50)")
    p_facts.add_argument("--stats", action="store_true", help="显示统计信息")
    p_facts.add_argument("--stats-by", help="按指定字段统计 (e.g. brand, model, event_type, source_tier)")
    p_facts.add_argument("--audit", action="store_true", help="事实库质量审计")
    p_facts.add_argument("--export", action="store_true", help="导出为 JSON")

    # brief
    p_brief = sub.add_parser("brief", help="基于 facts 生成每日简报")
    p_brief.add_argument("--brand", help="按品牌筛选")
    p_brief.add_argument("--model", help="按车型筛选")
    p_brief.add_argument("--event-type", help="按事件类型筛选")
    p_brief.add_argument("--days", type=int, default=1, help="最近 N 天 (default: 1)")
    p_brief.add_argument("--since", help="起始时间 (ISO format)")
    p_brief.add_argument("--until", help="截止时间 (ISO format)")
    p_brief.add_argument("--limit", type=int, default=50, help="最大事实数 (default: 50)")
    p_brief.add_argument("--output", help="输出 Markdown 文件路径")

    # run-day
    p_run = sub.add_parser("run-day", help="一键日更：daily → to-facts → audit → brief")
    p_run.add_argument("--brand", default="im")
    p_run.add_argument("--brand-name", default="智己")
    p_run.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    p_run.add_argument("--window-hours", type=int, default=24)
    p_run.add_argument("--live", action="store_true")
    p_run.add_argument("--brief-output", help="brief 输出路径（默认 outputs/runs/{date}/daily_brief.md）")

    # replay
    p_replay = sub.add_parser("replay", help="连续回放（支持日期范围或 inbox fixtures）")
    p_replay.add_argument("--start-date", help="起始日期 (与 --end-date 配对使用)")
    p_replay.add_argument("--end-date", help="截止日期")
    p_replay.add_argument("--brand", default="im")
    p_replay.add_argument("--brand-name", default="智己")
    p_replay.add_argument("--live", action="store_true")
    p_replay.add_argument("--input-dir", help="inbox fixtures 目录（替代日期范围）")
    p_replay.add_argument("--reset-store", action="store_true", help="回放前重置事实库")

    # source-audit
    p_sa = sub.add_parser("source-audit", help="信源覆盖审计")
    p_sa.add_argument("--watchlist", choices=["priority", "ls8"], default="priority",
                      help="期望覆盖范围: priority=24重点品牌, ls8=LS8竞品车型 (default: priority)")
    p_sa.add_argument("--days", type=int, default=7, help="最近 N 天 (default: 7)")
    p_sa.add_argument("--limit", type=int, default=500, help="最大事实数 (default: 500)")
    p_sa.add_argument("--format", choices=["text", "json"], default="text", help="输出格式 (default: text)")
    p_sa.add_argument("--output", help="输出文件路径")

    # timeline
    p_tl = sub.add_parser("timeline", help="品牌/车型事件时间线")
    p_tl.add_argument("--brand", help="按品牌筛选")
    p_tl.add_argument("--model", help="按车型筛选")
    p_tl.add_argument("--event-type", help="按事件类型筛选")
    p_tl.add_argument("--days", type=int, default=30, help="最近 N 天 (default: 30)")
    p_tl.add_argument("--since", help="起始时间")
    p_tl.add_argument("--until", help="截止时间")
    p_tl.add_argument("--limit", type=int, default=100, help="最大事实数 (default: 100)")
    p_tl.add_argument("--output", help="输出 Markdown 文件路径")

    args = parser.parse_args()
    if args.command == "daily":
        cmd_daily(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "normalize":
        cmd_normalize(args)
    elif args.command == "inbox":
        cmd_inbox(args)
    elif args.command == "facts":
        cmd_facts(args)
    elif args.command == "brief":
        cmd_brief(args)
    elif args.command == "run-day":
        cmd_run_day(args)
    elif args.command == "replay":
        cmd_replay(args)
    elif args.command == "source-audit":
        cmd_source_audit(args)
    elif args.command == "timeline":
        cmd_timeline(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
