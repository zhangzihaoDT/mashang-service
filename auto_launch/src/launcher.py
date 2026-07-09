"""Layer: Demo — Terminal Launcher（交互式编排，仅编排已有模块）"""

import json
from pathlib import Path
from datetime import datetime

from auto_launch.src import output_paths


def _write_run_package(date: str, summary: dict, brief: str):
    """Write a lightweight run package after processing a daily run.

    All outputs go to: runs/{YYYYMMDD}/{run_mode}/reports/ and runs/{YYYYMMDD}/{run_mode}/manifest.json
    Run mode for launcher daily run: "launcher_daily_run".
    """
    run_mode = "launcher_daily_run"
    rd = output_paths.run_dir(date, run_mode)
    log = []

    # daily_brief.md → reports/
    brief_path = output_paths.daily_brief_md_path(date, run_mode)
    brief_path.write_text(brief, encoding="utf-8")
    log.append(("brief", "ok", f"{summary['kept']} facts"))

    # manifest.json
    manifest = {
        "command": "launcher_daily_run",
        "monitor_date": date,
        "run_mode": run_mode,
        "input_channel": "launcher_daily_run",
        "raw": summary["total_raw_items"],
        "kept": summary["kept"],
        "discarded": summary["discarded"],
        "inserted": sum(1 for fr in summary.get("fact_results", []) if fr.get("action") == "inserted"),
        "updated": sum(1 for fr in summary.get("fact_results", []) if fr.get("action") == "updated"),
        "log": [{"step": s, "status": st, "detail": d, "time": datetime.now().isoformat()}
                for s, st, d in log],
        "outputs": {
            "run_dir": str(rd),
            "brief": str(brief_path),
            "manifest": str(output_paths.run_manifest_path(date, run_mode)),
            "summary": str(output_paths.run_summary_path(date, run_mode)),
        },
        "created_at": datetime.now().isoformat(),
    }
    output_paths.run_manifest_path(date, run_mode).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # summary.md
    lines = [
        f"# Run Summary — Launcher Daily Run — {date}",
        "",
        f"**Input channel:** launcher_daily_run",
        f"**Raw items:** {summary['total_raw_items']}",
        f"**Kept:** {summary['kept']}",
        f"**Discarded:** {summary['discarded']}",
        f"**Inserted:** {manifest['inserted']}",
        f"**Updated:** {manifest['updated']}",
        "",
        "## Pipeline",
        "",
    ]
    for entry in manifest["log"]:
        lines.append(f"- **{entry['step']}** ({entry['status']}) — {entry['detail']}")
    lines += [
        "",
        "## Outputs",
        "",
    ]
    for k, v in manifest["outputs"].items():
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        "---",
        f"*Generated: {manifest['created_at']}*",
        "",
    ]
    output_paths.run_summary_path(date, run_mode).write_text("\n".join(lines), encoding="utf-8")


def run_launcher():
    """Main interactive launcher loop."""
    from auto_launch.src.inbox_runner import run_text, _print_summary
    from auto_launch.src.fact_store import FactStore
    from auto_launch.src.brief_renderer import generate_brief
    from auto_launch.src.output_manager import inspect, render_inspect

    while True:
        print()
        print("=" * 50)
        print("  Auto Launch")
        print("=" * 50)
        print()
        print("  1. 处理 ChatGPT Daily Run")
        print("  2. 定向搜索并写入事实库")
        print("  3. 查看事实库")
        print("  4. 生成今日简报")
        print("  5. 查看 outputs 状态")
        print("  6. 退出")
        print()

        try:
            choice = input("请选择 [1-6]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        # ── 6. 退出 ─────────────────────────────────────
        if choice in ("6", "q", "quit", "exit"):
            print("[launcher] 再见")
            break

        # ── 1. 处理 ChatGPT Daily Run ────────────────────
        elif choice == "1":
            try:
                date_raw = input("日期 (默认今天): ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            date = date_raw if date_raw else datetime.now().strftime("%Y-%m-%d")
            print()
            print("粘贴 daily run 文本，输入 /done 结束：")
            lines = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line.strip() == "/done":
                    break
                if line.strip() == "/cancel":
                    print("[launcher] 已取消")
                    lines = []
                    break
                lines.append(line)
            raw_text = "\n".join(lines)
            if not raw_text.strip():
                print("[launcher] 未输入内容")
                continue

            summary = run_text(raw_text, date=date, write_facts=True)
            _print_summary(summary)

            if summary["kept"] > 0:
                print()
                try:
                    resp = input("生成并显示简报？(Y/n): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    resp = "n"
                if resp in ("", "y", "yes"):
                    facts = summary["kept_items"]
                    brief = generate_brief(facts, brief_date=date)
                    print()
                    print("=" * 60)
                    print("  每日简报")
                    print("=" * 60)
                    print(brief)

                    # Write run package (brief goes into runs/{date}/{run_mode}/reports/)
                    _write_run_package(date, summary, brief)
                    run_mode = "launcher_daily_run"
                    brief_path = output_paths.daily_brief_md_path(date, run_mode)

                    print(f"\n  简报已写入: {brief_path}")
                    print(f"  运行包: {brief_path.parent}")

        # ── 2. 定向搜索 ──────────────────────────────────
        elif choice == "2":
            try:
                request = input("搜索请求: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not request:
                print("[launcher] 搜索请求不能为空")
                continue
            try:
                date_raw = input("日期 (默认今天): ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            date = date_raw if date_raw else datetime.now().strftime("%Y-%m-%d")
            try:
                live = input("执行真实搜索？(y/N): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                live = "n"
            if live == "y":
                print("[launcher] 开始搜索...")
                from auto_launch.src.volc_search_daily import run_pipeline
                from auto_launch.cli import _search_to_facts
                result = run_pipeline(
                    request=request, monitor_date=date,
                    dry_run=False,
                )
                _search_to_facts(result)
                print("[launcher] 搜索完成")
            else:
                print("[launcher] dry-run: 模拟搜索，不调用 API")
                print(f"  请求: {request}")
                print(f"  日期: {date}")

        # ── 3. 查看事实库 ────────────────────────────────
        elif choice == "3":
            try:
                days_raw = input("最近 N 天 (默认 7): ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            days = int(days_raw) if days_raw.isdigit() else 7
            try:
                brand = input("品牌筛选 (可选，回车跳过): ").strip()
            except (EOFError, KeyboardInterrupt):
                brand = ""
            store = FactStore()
            if brand:
                facts = store.query(days=days, brand=brand, limit=50)
                stats = store.stats_by("brand")
                brand_stats = {k: v for k, v in stats.items() if brand.lower() in k.lower()}
                print(f"\n  {brand} 相关 facts: {len(facts)}")
                if brand_stats:
                    for k, v in brand_stats.items():
                        print(f"    {k}: {v}")
            else:
                facts = store.query(days=days, limit=50)
                stats = store.get_stats()
                print(f"\n  Total facts: {stats['total_facts']}")
                for label, data in [("Brand", "by_brand"), ("Event Type", "by_event_type")]:
                    if stats.get(data):
                        print(f"  By {label}:")
                        for k, v in list(stats[data].items())[:8]:
                            print(f"    {k or '(空)':<20} {v}")
            if facts:
                print()
                print(f"  {'id':<5} {'brand':<12} {'model':<12} {'event_type':<18} {'tier':<20} {'title':<40}")
                print("  " + "-" * 107)
                for f in facts[:15]:
                    title = (f["title"] or "")[:38]
                    tier = (f["source_tier"] or "-")[:18]
                    b = (f["brand"] or "-")[:10]
                    m = (f["model"] or "-")[:10]
                    et = (f["event_type"] or "-")[:16]
                    print(f"  {f['fact_id']:<5} {b:<12} {m:<12} {et:<18} {tier:<20} {title:<40}")

        # ── 4. 生成简报 ──────────────────────────────────
        elif choice == "4":
            try:
                days_raw = input("最近 N 天 (默认 1): ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            days = int(days_raw) if days_raw.isdigit() else 1
            try:
                brand = input("品牌筛选 (可选，回车跳过): ").strip()
            except (EOFError, KeyboardInterrupt):
                brand = ""
            store = FactStore()
            if brand:
                facts = store.query(days=days, brand=brand, limit=100)
            else:
                facts = store.query(days=days, limit=100)
            if not facts:
                print("[launcher] 无 facts，无法生成简报")
                continue
            brief = generate_brief(facts)
            print()
            print("=" * 60)
            print("  每日简报")
            print("=" * 60)
            print(brief)
            try:
                resp = input("\n写入文件？(y/N): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                resp = "n"
            if resp == "y":
                try:
                    date_raw = input("日期 (默认今天): ").strip()
                except (EOFError, KeyboardInterrupt):
                    date_raw = ""
                date = date_raw if date_raw else datetime.now().strftime("%Y-%m-%d")
                run_mode = "launcher_daily_run"
                brief_path = output_paths.daily_brief_md_path(date, run_mode)
                brief_path.write_text(brief, encoding="utf-8")
                print(f"\n  简报已写入: {brief_path}")

        # ── 5. 查看 outputs 状态 ─────────────────────────
        elif choice == "5":
            report = inspect()
            print(render_inspect(report))

        else:
            print("[launcher] 无效选择，请输入 1-6")
