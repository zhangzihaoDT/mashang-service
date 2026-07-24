"""
Auto Launch CLI — 统一命令行入口。

三层产品能力:
  search  = 联网搜索 → 归一化 → 写入 facts 库（发现层）
  daily   = 处理 ChatGPT Daily Run → 写入 facts 库（摄入层）
  report  = 从 facts 库读取 → 生成目标报告（报告层）

facts 是共享中间层：
  search ─┐
          ├── facts ─── report
  daily ──┘

辅助命令:
  facts     = 查看 facts 库状态、统计、筛选、审计
  run-day   = shortcut: search + report（编排层，非核心能力）
  launch    = 交互式入口

用法:
  python -m auto_launch.cli search --request "看看极氪最近 7 天都有什么动作"
  python -m auto_launch.cli daily --input path/to/chatgpt_daily.md
  python -m auto_launch.cli report --type brand-daily --brand 智己
  python -m auto_launch.cli run-day --brand 智己
  python -m auto_launch.cli facts --stats
  python -m auto_launch.cli launch
"""

import sys, argparse, os
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Ensure project root is on path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Load .env from project root
load_dotenv(Path(_PROJECT_ROOT) / ".env")


# ── daily: ChatGPT Daily Run ingestion ────────────────────────────

def cmd_daily(args):
    """[摄入层] 处理 ChatGPT Daily Run 并写入 facts 库。
    支持 --then-report 做 ingest → report orchestration。
    """
    from auto_launch.src.inbox_runner import run_file, run_text, _print_summary

    if args.input:
        summary = run_file(args.input, date=args.date)
    elif args.text:
        summary = run_text(args.text, date=args.date)
    else:
        print("[daily] 请指定 --input <文件> 或 --text <内容>")
        print("  示例: python -m auto_launch.cli daily --input chatgpt_daily.md")
        print("  示例: python -m auto_launch.cli daily --text '...ChatGPT Daily Run 内容...'")
        return

    _print_summary(summary)

    # ── --then-report daily-brief ──
    if args.then_report == "daily-brief" and summary.get("kept", 0) > 0:
        print()
        print("─" * 50)
        print(f"[daily] 生成 daily brief...")
        from auto_launch.src.brief_renderer import generate_brief
        from pathlib import Path
        brief_md = generate_brief(summary["kept_items"], brief_date=args.date)
        output_dir = Path("auto_launch/outputs/runs") / args.date.replace("-", "") / "launcher_daily_run" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "daily_brief.md"
        output_path.write_text(brief_md, encoding="utf-8")
        print(f"  已写入: {output_path.resolve()}")


# ── search: web search ingestion ──────────────────────────────────

def cmd_search(args):
    """[发现层] 联网搜索 → 归一化 → 写入 facts 库。"""
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

        from auto_launch.src.inbox_runner import _generate_run_id
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
            "source_pipeline": "search",
            "run_id": _generate_run_id(),
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


# ── report: facts → report generation ─────────────────────────────

def cmd_report(args):
    """[报告层] 从 facts 库读取并生成目标报告。"""
    from auto_launch.src import output_paths
    from auto_launch.src.fact_store import FactStore

    report_type = args.type

    if report_type == "brand-daily":
        from auto_launch.src.brand_daily_marketing_watch import run_brand_daily_report
        brand_slug, brand_name = output_paths.resolve_brand(args.brand)
        if args.brand_name:
            brand_name = args.brand_name

        store = FactStore()
        facts = store.query(brand=brand_name, days=max(1, args.window_hours // 24 + 1),
                            limit=args.limit)

        manifest = run_brand_daily_report(
            facts=facts, brand_slug=brand_slug, brand_name=brand_name,
            monitor_date=args.date, window_hours=args.window_hours,
        )
        if not facts:
            print(f"  ⚠ {brand_name} facts 库无数据，已生成空状态报告")
            print(f"    建议: auto_launch search --request '关于{brand_name}...' --to-facts --live")

    elif report_type == "daily-brief":
        from auto_launch.src.llm_brief_renderer import generate_llm_brief
        from auto_launch.src.brief_renderer import generate_brief as _fallback_brief
        store = FactStore()
        facts = store.query(brand=args.brand, event_type=args.event_type,
                            model=args.model, days=args.days,
                            since=args.since, until=args.until, limit=args.limit,
                            source_pipeline=args.pipeline)
        if args.no_llm:
            brief_md = _fallback_brief(facts)
        else:
            brief_md = generate_llm_brief(facts, brief_date=args.date, pipeline=args.pipeline)
            if not brief_md:
                print("[report] LLM 不可用，降级到规则脚本")
                brief_md = _fallback_brief(facts)
        if not args.output:
            date_str = args.date or datetime.now().strftime("%Y-%m-%d")
            args.output = f"auto_launch/outputs/runs/{date_str.replace('-', '')}/daily_brief.md"
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(brief_md, encoding="utf-8")
        print(f"[report --type daily-brief] 已写入: {args.output}")
        print()
        print(brief_md)

        if args.sync:
            from auto_launch.src.feishu_sender import send_brief_to_feishu
            ds = args.date or datetime.now().strftime("%Y-%m-%d")
            send_brief_to_feishu(brief_md, date_str=ds)

    else:
        print(f"[report] 不支持的 report type: {report_type}")
        print(f"  支持的 type: brand-daily, daily-brief")


# ── normalize (low-level, not part of 3-layer) ────────────────────

def cmd_normalize(args):
    from auto_launch.src.normalize_search_results import process
    normalized, audit = process(args.raw, args.query_plan, args.output_prefix)
    print(f"Normalized: {normalized['total']} items | Audit: {audit['query_count']} queries")


# ── facts: inspect facts store ────────────────────────────────────

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


# ── run-day: shortcut (search + report) ───────────────────────────

def cmd_run_day(args):
    """[编排] shortcut: search → facts → report。"""
    from auto_launch.src import output_paths
    from auto_launch.src.operating_loop import run_day

    brand_slug, brand_name = output_paths.resolve_brand(args.brand)
    if args.brand_name:
        brand_name = args.brand_name

    brief_output = args.brief_output or None
    result = run_day(
        monitor_date=args.date, brand=brand_slug, brand_name=brand_name,
        window_hours=args.window_hours, live=args.live,
        refresh=args.refresh, query_profile=args.query_profile,
        brief_output=brief_output,
    )
    print(f"[run-day] {result['monitor_date']} {result['brand_name']} | "
          f"live={result['live']} | report={result['brief_facts']} facts")
    for k, v in result["outputs"].items():
        print(f"  {k}: {v}")


# ── replay ────────────────────────────────────────────────────────

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


# ── launch: interactive entry ─────────────────────────────────────

def cmd_launch(args):
    from auto_launch.src.launcher import run_launcher
    run_launcher()


# ── demo ──────────────────────────────────────────────────────────

def cmd_demo(args):
    from auto_launch.src.demo_runner import run_demo
    manifest = run_demo(reset_store=args.reset_store)
    print(f"[demo] {manifest['replay_summary']['days']} days, "
          f"{manifest['replay_summary']['total_facts']} facts, "
          f"dup_rate={manifest['replay_summary']['duplicate_rate']}%")
    print(f"  demo_dir: {manifest['outputs']['demo_dir']}")
    print(f"  manifest: {manifest['outputs']['manifest']}")
    print(f"  summary: {manifest['demo_summary']}")


# ── outputs management ────────────────────────────────────────────

def cmd_outputs(args):
    from auto_launch.src.output_manager import inspect, clean_dry_run, render_inspect, render_clean_dry_run

    if args.sub == "inspect":
        report = inspect()
        print(render_inspect(report))
    elif args.sub == "clean":
        dry = clean_dry_run(older_than_days=args.older_than, keep_runs=args.keep_runs)
        print(render_clean_dry_run(dry))


# ── source-audit ──────────────────────────────────────────────────

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


# ── timeline ──────────────────────────────────────────────────────

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


# ── main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Auto Launch Service CLI")
    sub = parser.add_subparsers(dest="command", help="能力层级")

    # ── 三层核心入口 ──

    # daily = ChatGPT Daily Run 摄入层
    p_daily = sub.add_parser("daily", help="[摄入层] 处理 ChatGPT Daily Run → 写入 facts 库")
    p_daily.add_argument("--input", help="ChatGPT Daily Run markdown 文件路径")
    p_daily.add_argument("--text", help="ChatGPT Daily Run 文本内容（替代 --input）")
    p_daily.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                         help="事实日期（默认今天）")
    p_daily.add_argument("--then-report", choices=["daily-brief"],
                         help="摄入后自动生成 report（例如 daily-brief）")

    # search = 联网搜索发现层
    p_search = sub.add_parser("search", help="[发现层] 联网搜索 → 归一化 → 写入 facts 库")
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

    # report = facts → 报告层
    p_report = sub.add_parser("report", help="[报告层] 从 facts 库生成目标报告（不搜索）")
    p_report.add_argument("--type", required=True, choices=["brand-daily", "daily-brief"],
                          help="报告类型: brand-daily=品牌日报, daily-brief=每日简报")
    p_report.add_argument("--brand", help="品牌名（--type brand-daily 必填，支持中文/slug）")
    p_report.add_argument("--brand-name", help="品牌显示名（可选，默认从 --brand 自动解析）")
    p_report.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    p_report.add_argument("--window-hours", type=int, default=24)
    p_report.add_argument("--limit", type=int, default=100, help="最大 facts 数 (default: 100)")
    p_report.add_argument("--model", help="车型筛选（--type daily-brief 可选）")
    p_report.add_argument("--event-type", help="事件类型筛选（--type daily-brief 可选）")
    p_report.add_argument("--days", type=int, default=1, help="最近 N 天（--type daily-brief）")
    p_report.add_argument("--since", help="起始时间（ISO format）")
    p_report.add_argument("--until", help="截止时间（ISO format）")
    p_report.add_argument("--pipeline", choices=["search", "daily", "manual"],
                          help="按来源过滤（search/daily/manual）")
    p_report.add_argument("--no-llm", action="store_true",
                          help="禁用 LLM，使用规则脚本生成简报（默认使用 LLM）")
    p_report.add_argument("--sync", action="store_true",
                          help="生成后同步到飞书群（仅 daily-brief）")
    p_report.add_argument("--output", help="输出文件路径")

    # ── 辅助命令 ──

    # normalize (low-level)
    p_norm = sub.add_parser("normalize", help="标准化搜索结果（底层工具）")
    p_norm.add_argument("--raw", required=True)
    p_norm.add_argument("--query-plan", required=True)
    p_norm.add_argument("--output-prefix")

    # inbox (daily 的别名，保留向后兼容)
    p_inbox = sub.add_parser("inbox", help="[别名] 同 daily --input，处理 ChatGPT Daily Run")
    p_inbox.add_argument("--input", help="ChatGPT daily run markdown 文件路径")
    p_inbox.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                         help="事实日期")

    # facts
    p_facts = sub.add_parser("facts", help="查看 facts 库状态、统计、筛选、审计")
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

    # run-day = shortcut (search + report)
    p_run = sub.add_parser("run-day",
                           help="[编排] shortcut: search + report 完整链路（非核心能力层）")
    p_run.add_argument("--brand", required=True,
                       help="品牌名（支持中文/英文 slug，如 智己/zhiji/im）")
    p_run.add_argument("--brand-name", help="品牌显示名（可选，默认从 --brand 自动解析）")
    p_run.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    p_run.add_argument("--window-hours", type=int, default=24)
    p_run.add_argument("--live", action="store_true", help="执行真实搜索（否则 dry-run）")
    p_run.add_argument("--refresh", action="store_true", help="强制刷新缓存")
    p_run.add_argument("--query-profile", default="balanced")
    p_run.add_argument("--brief-output", help="report 输出路径（默认由 output_paths.py 管理）")

    # replay
    p_replay = sub.add_parser("replay", help="连续回放（支持日期范围或 inbox fixtures）")
    p_replay.add_argument("--start-date", help="起始日期 (与 --end-date 配对使用)")
    p_replay.add_argument("--end-date", help="截止日期")
    p_replay.add_argument("--brand", default="im")
    p_replay.add_argument("--brand-name", default="智己")
    p_replay.add_argument("--live", action="store_true")
    p_replay.add_argument("--input-dir", help="inbox fixtures 目录（替代日期范围）")
    p_replay.add_argument("--reset-store", action="store_true", help="回放前重置事实库")

    # launch / start
    sub.add_parser("launch", help="交互式入口（推荐）")
    sub.add_parser("start", help="交互式入口（launch 别名）")

    # demo
    p_demo = sub.add_parser("demo", help="一键演示：replay fixtures → audit → source-audit → brief → timeline → inspect")
    p_demo.add_argument("--reset-store", action="store_true", help="演示前清空事实库")

    # outputs
    p_out = sub.add_parser("outputs", help="输出管理：inspect / clean")
    out_sub = p_out.add_subparsers(dest="sub", help="outputs 子命令")
    p_out_inspect = out_sub.add_parser("inspect", help="检查 outputs 目录结构完整性")
    p_out_clean = out_sub.add_parser("clean", help="列出可清理的调试/缓存产物（仅 dry-run）")
    p_out_clean.add_argument("--older-than", type=int, default=None,
                             help="仅列出超过 N 天的文件（如 30）")
    p_out_clean.add_argument("--keep-runs", action="store_true", default=True,
                             help="保留 runs/ 主运行包（默认开启）")
    p_out_clean.add_argument("--dry-run", action="store_true", default=True,
                             help="dry-run 模式（默认开启，不删除文件）")

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

    # ── dispatch ──
    args = parser.parse_args()

    if args.command == "daily":
        cmd_daily(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "normalize":
        cmd_normalize(args)
    elif args.command == "inbox":
        cmd_inbox(args)
    elif args.command == "facts":
        cmd_facts(args)
    elif args.command == "run-day":
        cmd_run_day(args)
    elif args.command == "replay":
        cmd_replay(args)
    elif args.command == "source-audit":
        cmd_source_audit(args)
    elif args.command == "timeline":
        cmd_timeline(args)
    elif args.command in ("launch", "start"):
        cmd_launch(args)
    elif args.command == "demo":
        cmd_demo(args)
    elif args.command == "outputs":
        cmd_outputs(args)
    else:
        parser.print_help()


def cmd_inbox(args):
    """[别名] 同 daily --input。"""
    from auto_launch.src.inbox_runner import run_file, _print_summary
    if args.input:
        summary = run_file(args.input, date=args.date)
        _print_summary(summary)
    else:
        from auto_launch.src.inbox_runner import run_interactive
        run_interactive()


if __name__ == "__main__":
    main()
