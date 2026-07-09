"""Layer: Demo — 一键演示编排（仅编排已有能力，不新增业务逻辑）"""

import json
from pathlib import Path
from datetime import datetime

DEMO_DIR = Path(__file__).resolve().parent.parent / "outputs" / "demo"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "daily_runs"


def run_demo(reset_store: bool = False) -> dict:
    """
    一键演示编排：
    1. replay fixtures (day1.md, day2.md, day3.md)
    2. facts audit
    3. source-audit (priority)
    4. brief
    5. timeline
    6. outputs inspect
    7. demo_manifest.json + demo_summary.md
    """
    from auto_launch.src.operating_loop import replay_from_fixtures
    from auto_launch.src.fact_store import FactStore
    from auto_launch.src import source_auditor
    from auto_launch.src.brief_renderer import generate_brief
    from auto_launch.src.timeline_renderer import generate_timeline
    from auto_launch.src.output_manager import inspect, render_inspect

    demo_dir = DEMO_DIR
    demo_dir.mkdir(parents=True, exist_ok=True)
    log = []
    artifacts = {}

    # Step 1: replay
    replay_result = replay_from_fixtures(str(FIXTURES_DIR), reset_store=reset_store)
    log.append(("replay", "ok",
                f"{replay_result['days']} days, {replay_result['total_facts']} facts, "
                f"dup_rate={replay_result['duplicate_rate']}%"))
    artifacts["replay_result"] = replay_result

    # Step 2: facts audit
    store = FactStore()
    audit = store.audit()
    (demo_dir / "facts_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    log.append(("facts-audit", "ok", f"{audit['total']} facts, {len(audit['warnings'])} warnings"))

    # Step 3: source-audit
    facts = store.query(days=90, limit=500)
    sa_report = source_auditor.audit(facts, watchlist="priority")
    (demo_dir / "source_audit.json").write_text(
        json.dumps(sa_report, ensure_ascii=False, indent=2), encoding="utf-8")
    sa_md = source_auditor.render_markdown(sa_report)
    (demo_dir / "source_audit.md").write_text(sa_md, encoding="utf-8")
    sa_flags = len(sa_report.get("expected_flags", []))
    log.append(("source-audit", "ok",
                f"{sa_report['official_rate']}% official, {sa_report['media_rate']}% media, {sa_flags} gaps"))

    # Step 4: brief
    brief_md = generate_brief(facts)
    (demo_dir / "daily_brief.md").write_text(brief_md, encoding="utf-8")
    log.append(("brief", "ok", f"{len(facts)} facts"))

    # Step 5: timeline
    timeline_md = generate_timeline(facts)
    (demo_dir / "timeline.md").write_text(timeline_md, encoding="utf-8")
    log.append(("timeline", "ok", f"{sum(1 for f in facts if f.get('event_date'))} dated facts"))

    # Step 6: outputs inspect
    inspect_report = inspect()
    inspect_md = render_inspect(inspect_report)
    (demo_dir / "outputs_inspect.md").write_text(inspect_md, encoding="utf-8")
    log.append(("outputs-inspect", "ok", f"{inspect_report['runs']['count']} runs"))

    # Step 7: demo_manifest.json
    manifest = {
        "command": "demo",
        "reset_store": reset_store,
        "fixtures_dir": str(FIXTURES_DIR),
        "replay_summary": {
            "days": replay_result["days"],
            "total_facts": replay_result["total_facts"],
            "total_keep": replay_result["total_keep"],
            "duplicate_rate": replay_result["duplicate_rate"],
        },
        "facts_audit_summary": {
            "total": audit["total"],
            "warnings_count": len(audit["warnings"]),
        },
        "source_audit_summary": {
            "official_rate": sa_report["official_rate"],
            "media_rate": sa_report["media_rate"],
            "expected_gaps": sa_flags,
        },
        "outputs": {
            "demo_dir": str(demo_dir),
            "manifest": str(demo_dir / "demo_manifest.json"),
            "facts_audit": str(demo_dir / "facts_audit.json"),
            "source_audit_json": str(demo_dir / "source_audit.json"),
            "source_audit_md": str(demo_dir / "source_audit.md"),
            "brief": str(demo_dir / "daily_brief.md"),
            "timeline": str(demo_dir / "timeline.md"),
            "outputs_inspect": str(demo_dir / "outputs_inspect.md"),
        },
        "demo_summary": str(demo_dir / "demo_summary.md"),
        "log": [{"step": s, "status": st, "detail": d, "time": datetime.now().isoformat()}
                for s, st, d in log],
        "created_at": datetime.now().isoformat(),
    }
    (demo_dir / "demo_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # demo_summary.md
    summary = _render_demo_summary(manifest)
    (demo_dir / "demo_summary.md").write_text(summary, encoding="utf-8")

    return manifest


def _render_demo_summary(manifest: dict) -> str:
    lines = [
        "# Auto Launch Demo Summary",
        "",
        f"**Mode:** {'reset-store' if manifest['reset_store'] else 'append'}  ",
        f"**Fixtures:** {manifest['fixtures_dir']}  ",
        "",
        "## Pipeline",
        "",
    ]
    for entry in manifest["log"]:
        lines.append(f"- **{entry['step']}** ({entry['status']}) — {entry['detail']}")
    lines += [
        "",
        "## Replay Summary",
        "",
        f"- Days: {manifest['replay_summary']['days']}",
        f"- Total facts: {manifest['replay_summary']['total_facts']}",
        f"- Kept items: {manifest['replay_summary']['total_keep']}",
        f"- Duplicate rate: {manifest['replay_summary']['duplicate_rate']}%",
        "",
        "## Facts Audit",
        "",
        f"- Total facts: {manifest['facts_audit_summary']['total']}",
        f"- Warnings: {manifest['facts_audit_summary']['warnings_count']}",
        "",
        "## Source Audit",
        "",
        f"- Official rate: {manifest['source_audit_summary']['official_rate']}%",
        f"- Media rate: {manifest['source_audit_summary']['media_rate']}%",
        f"- Expected gaps: {manifest['source_audit_summary']['expected_gaps']}",
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
