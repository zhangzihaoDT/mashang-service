"""Layer: Orchestration — 日更运行、回放（run-day shortcut）"""

import json, shutil
from pathlib import Path
from datetime import datetime, timedelta

from auto_launch.src import output_paths


def run_day(monitor_date: str, brand: str = "zhiji", brand_name: str = "智己",
            window_hours: int = 24, query_profile: str = "balanced",
            live: bool = False, refresh: bool = False,
            write_facts: bool = True, brief_output: str = None) -> dict:
    """
    [编排] run-day shortcut: search → facts → report.

    1. search (_run: 搜索 pipeline → normalized)
    2. 写入 facts（live 模式）
    3. report (run_brand_daily_report: 从 facts 读 → 生成品牌日报)
    4. facts audit + source audit

    Output paths managed by output_paths.py. Run mode: brand_daily_{brand}.
    不是三层核心能力，仅为编排 shortcut。
    """
    from auto_launch.src.brand_daily_marketing_watch import _run, run_brand_daily_report
    from auto_launch.src.fact_store import FactStore
    from auto_launch.src.inbox_filter import classify
    from auto_launch.src import source_auditor

    run_mode = output_paths.run_mode_brand_daily(brand)
    rd = output_paths.run_dir(monitor_date, run_mode)
    log = []

    # Step 1: search (_run = 搜索 pipeline)
    _run(brand=brand, brand_name=brand_name, monitor_date=monitor_date,
         window_hours=window_hours, query_profile=query_profile,
         dry_run=not live, refresh=refresh)
    log.append(("search", "dry_run" if not live else "live",
                f"{brand_name} {monitor_date} window={window_hours}h"))

    # Step 2: to-facts (live only)
    kept = 0
    if live and write_facts:
        norm_file = output_paths.search_normalized_path(monitor_date, run_mode)
        if norm_file.exists():
            data = json.loads(norm_file.read_text(encoding="utf-8"))
            items = data.get("items", [])
            if items:
                store = FactStore()
                for item in items:
                    inbox_item = {
                        "brand": brand_name, "model": "",
                        "event_type": (item.get("matched_event_type_ids") or [None])[0]
                                      if item.get("matched_event_type_ids") else None,
                        "title": (item.get("title") or "")[:200],
                        "claim": (item.get("snippet") or "")[:500],
                        "source_name": item.get("source_name", ""),
                        "source_url": item.get("url", ""),
                        "source_tier": item.get("source_tier_guess", ""),
                        "input_channel": "search_to_facts",
                    }
                    if classify(inbox_item)["decision"] == "keep":
                        store.insert(inbox_item)
                        kept += 1
                log.append(("to-facts", "ok", f"{kept} keep from {len(items)} items"))
        else:
            log.append(("to-facts", "skipped", "no normalized file"))

    # Step 3: facts audit
    store = FactStore()
    audit = store.audit()
    audit_path = output_paths.facts_audit_path(monitor_date, run_mode)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    log.append(("audit", "ok", f"{audit['total']} facts, {len(audit['warnings'])} warnings"))

    # Step 3.5: source audit
    facts = store.query(days=1, limit=200)
    sa_report = source_auditor.audit(facts)
    sa_md = source_auditor.render_markdown(sa_report)
    sa_json_path = output_paths.source_audit_json_path(monitor_date, run_mode)
    sa_md_path = output_paths.source_audit_md_path(monitor_date, run_mode)
    sa_json_path.write_text(json.dumps(sa_report, ensure_ascii=False, indent=2), encoding="utf-8")
    sa_md_path.write_text(sa_md, encoding="utf-8")
    sa_flags = len(sa_report.get("expected_flags", []))
    log.append(("source-audit", "ok",
                f"{sa_report['official_rate']}% official, {sa_report['media_rate']}% media, {sa_flags} gaps"))

    # Step 4: report = run_brand_daily_report (复用 report 的 facts-to-report 逻辑)
    facts = store.query(brand=brand_name, days=max(1, window_hours // 24 + 1), limit=100)
    report_manifest = run_brand_daily_report(
        facts=facts, brand_slug=brand, brand_name=brand_name,
        monitor_date=monitor_date, window_hours=window_hours,
    )
    log.append(("report", "ok", f"{len(facts)} facts -> brand_daily report"))

    # Step 5: manifest.json
    manifest = {
        "command": "run-day",
        "note": "编排 shortcut: search → facts → report（非三层核心能力）",
        "monitor_date": monitor_date,
        "run_mode": run_mode,
        "brand": brand, "brand_name": brand_name,
        "window_hours": window_hours, "live": live,
        "kept": kept, "brief_facts": len(facts),
        "audit_summary": {
            "total": audit["total"],
            "warnings": audit["warnings"],
            "no_brand": audit["quality_flags"]["no_brand"],
            "no_event_type": audit["quality_flags"]["no_event_type"],
        },
        "source_audit_summary": {
            "official_rate": sa_report["official_rate"],
            "media_rate": sa_report["media_rate"],
            "social_count": sa_report.get("social_count", 0),
            "weak_count": sa_report.get("weak_count", 0),
            "missing_url": sa_report.get("missing_url", 0),
            "missing_event_date": sa_report.get("missing_event_date", 0),
            "expected_gaps": len(sa_report.get("expected_flags", [])),
            "low_quality": sa_report.get("low_quality_count", 0),
        },
        "outputs": {
            "run_dir": str(rd),
            "manifest": str(output_paths.run_manifest_path(monitor_date, run_mode)),
            "audit": str(audit_path),
            "source_audit_json": str(sa_json_path),
            "source_audit_md": str(sa_md_path),
            "report_manifest": report_manifest.get("outputs", {}).get("report", ""),
            "summary": str(output_paths.run_summary_path(monitor_date, run_mode)),
        },
        "log": [{"step": s, "status": st, "detail": d, "time": datetime.now().isoformat()}
                for s, st, d in log],
        "created_at": datetime.now().isoformat(),
    }
    manifest_path = output_paths.run_manifest_path(monitor_date, run_mode)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 6: summary.md
    summary_md = _render_summary(manifest, audit, sa_report)
    output_paths.run_summary_path(monitor_date, run_mode).write_text(summary_md, encoding="utf-8")
    log.append(("summary", "ok", str(manifest_path)))

    return manifest


def _render_summary(manifest: dict, audit: dict, sa_report: dict = None) -> str:
    date_str = manifest["monitor_date"]
    brand_name = manifest["brand_name"]
    lines = [
        f"# Run Summary — {date_str} {brand_name}",
        "",
        f"**Mode:** {'live' if manifest['live'] else 'dry-run'}",
        f"**Window:** {manifest['window_hours']}h",
        "",
        "## Pipeline",
        "",
    ]
    for entry in manifest["log"]:
        lines.append(f"- **{entry['step']}** ({entry['status']}) — {entry['detail']}")
    lines += [
        "",
        "## Facts Audit",
        "",
        f"- Total facts: {audit['total']}",
        f"- No brand: {audit['quality_flags']['no_brand']}",
        f"- No event type: {audit['quality_flags']['no_event_type']}",
        f"- Warnings: {len(audit['warnings'])}",
    ]
    for w in audit["warnings"]:
        lines.append(f"  - {w}")
    if sa_report:
        lines += [
            "",
            "## Source Audit",
            "",
            f"- Official rate: {sa_report['official_rate']}% ({sa_report['official_count']}/{sa_report['total']})",
            f"- Media rate: {sa_report['media_rate']}% ({sa_report['auto_media_count']}/{sa_report['total']})",
            f"- Social/weak: {sa_report.get('social_count', 0)} / {sa_report.get('weak_count', 0)}",
            f"- Missing source_url: {sa_report.get('missing_url', 0)}",
            f"- Missing event_date: {sa_report.get('missing_event_date', 0)}",
            f"- Expected gaps: {len(sa_report.get('expected_flags', []))}",
            f"- Low quality facts: {sa_report.get('low_quality_count', 0)}",
        ]
        if sa_report.get("expected_flags"):
            lines.append("")
            for ef in sa_report["expected_flags"][:3]:
                lines.append(f"  - {ef['brand']}: {ef['flag']}")
            if len(sa_report["expected_flags"]) > 3:
                lines.append(f"  - ... and {len(sa_report['expected_flags']) - 3} more")
        if sa_report.get("suggestions"):
            lines.append("")
            for s in sa_report["suggestions"][:3]:
                lines.append(f"  - {s}")
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
    return "\n".join(lines)


def replay_from_fixtures(fixtures_dir: str, reset_store: bool = False) -> dict:
    """
    从 inbox fixtures 回放多天数据。
    每个 fixture 文件作为一天的 daily 输入处理。
    """
    from auto_launch.src.fact_store import FactStore
    from auto_launch.src.inbox_runner import run_text

    fp = Path(fixtures_dir)
    md_files = sorted(fp.glob("*.md"))
    if not md_files:
        return {"error": f"No .md files in {fixtures_dir}"}

    if reset_store:
        store = FactStore()
        store.close()
        Path(store.db_path).unlink(missing_ok=True)

    results = []
    total_raw = 0
    total_keep = 0
    total_inserted = 0
    total_updated = 0

    for i, mf in enumerate(md_files, 1):
        date_str = mf.stem.replace("day", "").replace("_", "-")
        if len(date_str) < 8:
            date_str = f"2026-07-{int(date_str):02d}" if date_str.isdigit() else "2026-07-09"
        text = mf.read_text(encoding="utf-8")
        summary = run_text(text, date=date_str, write_facts=True)
        total_raw += summary["total_raw_items"]
        total_keep += summary["kept"]
        for fr in summary.get("fact_results", []):
            if fr["action"] == "inserted":
                total_inserted += 1
            else:
                total_updated += 1
        results.append({
            "day": i, "file": mf.name, "date": date_str,
            "raw": summary["total_raw_items"],
            "keep": summary["kept"],
            "discard": summary["discarded"],
        })

    store = FactStore()
    stats = store.get_stats()
    total_facts = stats["total_facts"]

    return {
        "days": len(md_files),
        "total_raw": total_raw,
        "total_keep": total_keep,
        "total_inserted": total_inserted,
        "total_updated": total_updated,
        "total_facts": total_facts,
        "duplicate_rate": round((total_updated / (total_inserted + total_updated)) * 100, 1)
                         if (total_inserted + total_updated) > 0 else 0,
        "top_brands": dict(list(stats["by_brand"].items())[:5]),
        "per_day": results,
    }
