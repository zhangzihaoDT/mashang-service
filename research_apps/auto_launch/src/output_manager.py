"""Layer: Intelligence Utilities — 输出管理与维护

Output paths managed by output_paths.py.
Inspects runs/ hierarchy, facts, search_cache, demo.
Does not inspect deprecated paths (briefs/, owned_brand_daily/, top-level search/).
"""

import json
from pathlib import Path
from datetime import datetime, timedelta

from auto_launch.src import output_paths

RUN_REQUIRED_FILES = [
    "manifest.json",
    "facts/facts_audit.json",
    "reports/source_audit.json",
    "reports/source_audit.md",
    "reports/daily_brief.md",
    "summary.md",
]

NEVER_CLEAN = ["facts/auto_launch_facts.sqlite"]
CLEAN_CANDIDATE_DIRS = ["search_cache"]


def _parse_run_date(dir_name: str) -> str | None:
    try:
        dt = datetime.strptime(dir_name, "%Y%m%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def inspect() -> dict:
    """Scan outputs/ subdirs and return a structured inspection report."""
    root = output_paths.output_root()

    # Runs inspection — scans runs/{YYYYMMDD}/{run_mode}/
    runs = []
    for date_dir in sorted(root.glob("runs/*")):
        if not date_dir.is_dir():
            continue
        date_str = _parse_run_date(date_dir.name)
        if not date_str:
            continue
        for mode_dir in sorted(date_dir.glob("*")):
            if not mode_dir.is_dir():
                continue
            present = {f.name for f in mode_dir.rglob("*") if f.is_file()}
            rel_files = {str(f.relative_to(mode_dir)) for f in mode_dir.rglob("*") if f.is_file()}
            missing = [f for f in RUN_REQUIRED_FILES if f not in rel_files]
            run_manifest = None
            mf = mode_dir / "manifest.json"
            if mf.exists():
                try:
                    run_manifest = json.loads(mf.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass
            runs.append({
                "date": date_str,
                "run_mode": mode_dir.name,
                "dir": str(mode_dir),
                "file_count": len(present),
                "complete": len(missing) == 0,
                "missing": missing,
                "has_manifest": run_manifest is not None,
                "manifest_command": run_manifest.get("command") if run_manifest else None,
                "manifest_live": run_manifest.get("live") if run_manifest else None,
            })

    # Facts
    facts_db = output_paths.fact_db_path()
    facts_exists = facts_db.exists()
    facts_size = facts_db.stat().st_size if facts_exists else 0

    # Search cache counts
    cache_dir = output_paths.cache_dir()
    if cache_dir.exists():
        cache_files = sorted(cache_dir.rglob("*"))
        cache_stats = {
            "file_count": sum(1 for f in cache_files if f.is_file()),
            "dir_count": sum(1 for f in cache_files if f.is_dir()),
        }
    else:
        cache_stats = {"file_count": 0, "dir_count": 0}

    # Demo
    demo_dir = output_paths.demo_dir()
    if demo_dir.exists():
        demo_files = sorted(demo_dir.rglob("*"))
        demo_stats = {
            "file_count": sum(1 for f in demo_files if f.is_file()),
            "dir_count": sum(1 for f in demo_files if f.is_dir()),
        }
    else:
        demo_stats = {"file_count": 0, "dir_count": 0}

    # Warnings
    warnings = []
    if not facts_exists:
        warnings.append("facts/auto_launch_facts.sqlite 不存在 — 事实库为空")
    incomplete_runs = [r for r in runs if not r["complete"]]
    if incomplete_runs:
        names = ", ".join(f"{r['date']}/{r['run_mode']}" for r in incomplete_runs[:3])
        total = len(incomplete_runs)
        warnings.append(f"不完整 run: {names} ({total} 个)")

    return {
        "outputs_root": str(root),
        "runs": {"count": len(runs), "complete": sum(1 for r in runs if r["complete"]), "list": runs},
        "facts": {"exists": facts_exists, "size_bytes": facts_size, "path": str(facts_db) if facts_exists else None},
        "search_cache": cache_stats,
        "demo": demo_stats,
        "warnings": warnings,
    }


def clean_dry_run(older_than_days: int | None = None, keep_runs: bool = True) -> dict:
    """Identify files safe to delete, grouped by category.

    Never cleaned: facts/auto_launch_facts.sqlite, runs/*/ main output files.
    """
    root = output_paths.output_root()
    now = datetime.now()
    candidates = {}
    total_size = 0
    total_files = 0

    def _should_include(mtime: datetime) -> bool:
        if older_than_days is None:
            return True
        return (now - mtime).days >= older_than_days

    # search_cache
    cache_files = []
    for f in sorted(root.glob("search_cache/**/*")):
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if _should_include(mtime):
            cache_files.append(str(f))
            total_size += f.stat().st_size
            total_files += 1
    candidates["search_cache"] = cache_files

    dry_run = {
        "mode": "dry-run",
        "older_than_days": older_than_days,
        "keep_runs": keep_runs,
        "total_candidates": total_files,
        "total_size_bytes": total_size,
        "total_size_kb": round(total_size / 1024, 1),
        "never_cleaned": ["facts/auto_launch_facts.sqlite", "runs/*/ (主运行包)"],
        "candidates": candidates,
    }
    return dry_run


def render_inspect(report: dict) -> str:
    lines = ["# Outputs Inspection Report", ""]
    lines.append(f"**Outputs root:** {report['outputs_root']}  ")
    lines.append("")

    # Runs
    lines.append(f"## Runs ({report['runs']['count']})")
    lines.append("")
    lines.append(f"{'date':<14} {'run_mode':<25} {'complete':<10} {'files':<7}")
    lines.append("-" * 56)
    for r in report["runs"]["list"]:
        status = "✓" if r["complete"] else "✗"
        lines.append(f"{r['date']:<14} {r['run_mode']:<25} {status:<10} {r['file_count']:<7}")
    lines.append("")

    # Facts
    f = report["facts"]
    status = "✓" if f["exists"] else "✗"
    size_kb = round(f["size_bytes"] / 1024, 1) if f["exists"] else 0
    lines.append(f"## Facts")
    lines.append("")
    lines.append(f"- **SQLite:** {status} ({size_kb} KB)" if f["exists"] else "- **SQLite:** ✗")
    lines.append("")

    # Cache & Demo
    for label in ["search_cache", "demo"]:
        s = report.get(label, {})
        lines.append(f"## {label}")
        lines.append("")
        lines.append(f"- {s.get('file_count', 0)} files, {s.get('dir_count', 0)} dirs")
        lines.append("")

    # Warnings
    if report["warnings"]:
        lines.append("## Warnings")
        lines.append("")
        for w in report["warnings"]:
            lines.append(f"- ⚠ {w}")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by outputs inspect*")
    lines.append("")
    return "\n".join(lines)


def render_clean_dry_run(dry: dict) -> str:
    lines = ["# Outputs Clean (dry-run)", ""]
    lines.append(f"**Mode:** {dry['mode']}  ")
    if dry["older_than_days"]:
        lines.append(f"**Older than:** {dry['older_than_days']} days  ")
    lines.append(f"**Total candidates:** {dry['total_candidates']} files  ")
    lines.append(f"**Total size:** {dry['total_size_kb']} KB  ")
    lines.append("")
    lines.append("**Never cleaned:**")
    for n in dry["never_cleaned"]:
        lines.append(f"- {n}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for category, files in dry["candidates"].items():
        if not files:
            continue
        label = category.replace("_", " ").title()
        lines.append(f"## {label} ({len(files)} files)")
        for f in files[:10]:
            lines.append(f"- {f}")
        if len(files) > 10:
            lines.append(f"  ... and {len(files) - 10} more")
        lines.append("")

    lines.append("---")
    lines.append("*Dry-run — no files were deleted*")
    lines.append("")
    return "\n".join(lines)
