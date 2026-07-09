"""Layer: Inbox Core — 日更运行、回放"""

import json, shutil
from pathlib import Path
from datetime import datetime, timedelta


def _run_dir(date_str: str) -> Path:
    SERVICE_ROOT = Path(__file__).resolve().parent.parent
    d = SERVICE_ROOT / "outputs" / "runs" / date_str.replace("-", "")
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_day(monitor_date: str, brand: str = "im", brand_name: str = "智己",
            window_hours: int = 24, query_profile: str = "balanced",
            live: bool = False, refresh: bool = False,
            write_facts: bool = True, brief_output: str = None) -> dict:
    """
    一键日更：
    1. daily 监控
    2. 写入 facts（live 模式）
    3. facts audit
    4. 生成 brief
    5. 写出 run_manifest.json / facts_audit.json / daily_brief.md / run_summary.md
    """
    from auto_launch.src.brand_daily_marketing_watch import _run, DEFAULT_OUTPUT_BASE
    from auto_launch.src.fact_store import FactStore
    from auto_launch.src.brief_renderer import generate_brief
    from auto_launch.src.inbox_filter import classify
    from auto_launch.src import source_auditor

    run_dir = _run_dir(monitor_date)
    log = []

    # Step 1: daily
    _run(brand=brand, brand_name=brand_name, monitor_date=monitor_date,
         window_hours=window_hours, query_profile=query_profile,
         out_dir=str(DEFAULT_OUTPUT_BASE), dry_run=not live, refresh=refresh)
    log.append(("daily", "dry_run" if not live else "live",
                f"{brand_name} {monitor_date} window={window_hours}h"))

    # Step 2: to-facts (live only)
    kept = 0
    if live and write_facts:
        out_dir = DEFAULT_OUTPUT_BASE / monitor_date.replace("-", "")
        norm_file = out_dir / "normalized_search_results.json"
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
                        "input_channel": "daily_to_facts",
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
    audit_path = run_dir / "facts_audit.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    log.append(("audit", "ok", f"{audit['total']} facts, {len(audit['warnings'])} warnings"))

    # Step 3.5: source audit
    facts = store.query(days=1, limit=200)
    sa_report = source_auditor.audit(facts)
    sa_md = source_auditor.render_markdown(sa_report)
    (run_dir / "source_audit.json").write_text(
        json.dumps(sa_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "source_audit.md").write_text(sa_md, encoding="utf-8")
    sa_flags = len(sa_report.get("expected_flags", []))
    log.append(("source-audit", "ok",
                f"{sa_report['official_rate']}% official, {sa_report['media_rate']}% media, {sa_flags} gaps"))

    # Step 4: brief
    facts = store.query(days=1, limit=50)
    brief_md = generate_brief(facts)
    brief_path = Path(brief_output) if brief_output else run_dir / "daily_brief.md"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(brief_md, encoding="utf-8")
    log.append(("brief", "ok", f"{len(facts)} facts -> {brief_path}"))

    # Step 5: run_manifest.json
    manifest = {
        "command": "run-day",
        "monitor_date": monitor_date,
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
            "run_dir": str(run_dir),
            "manifest": str(run_dir / "run_manifest.json"),
            "audit": str(audit_path),
            "source_audit_json": str(run_dir / "source_audit.json"),
            "source_audit_md": str(run_dir / "source_audit.md"),
            "brief": str(brief_path),
            "summary": str(run_dir / "run_summary.md"),
        },
        "log": [{"step": s, "status": st, "detail": d, "time": datetime.now().isoformat()}
                for s, st, d in log],
        "created_at": datetime.now().isoformat(),
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 6: run_summary.md
    summary_md = _render_summary(manifest, audit, sa_report)
    (run_dir / "run_summary.md").write_text(summary_md, encoding="utf-8")
    log.append(("summary", "ok", str(run_dir / "run_summary.md")))

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
    每个 fixture 文件作为一天的 inbox 输入处理。
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
