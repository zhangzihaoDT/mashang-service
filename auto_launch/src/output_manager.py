"""Layer: Intelligence Utilities — 输出管理与维护"""

import json
from pathlib import Path
from datetime import datetime, timedelta

OUTPUTS_ROOT = Path(__file__).resolve().parent.parent / "outputs"

RUN_DIR_GLOB = "runs/*"
RUN_REQUIRED_FILES = [
    "run_manifest.json",
    "facts_audit.json",
    "source_audit.json",
    "source_audit.md",
    "daily_brief.md",
    "run_summary.md",
]

NEVER_CLEAN = ["facts/auto_launch_facts.sqlite"]
CLEAN_CANDIDATE_DIRS = ["search_cache", "search", "owned_brand_daily"]


def _parse_run_date(dir_name: str) -> str | None:
    try:
        dt = datetime.strptime(dir_name, "%Y%m%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def inspect() -> dict:
    """Scan all outputs/ subdirs and return a structured inspection report."""
    root = OUTPUTS_ROOT

    # Runs inspection
    runs = []
    for d in sorted(root.glob("runs/*")):
        if not d.is_dir():
            continue
        date_str = _parse_run_date(d.name)
        if not date_str:
            continue
        present = {f.name for f in d.iterdir() if f.is_file()}
        missing = [f for f in RUN_REQUIRED_FILES if f not in present]
        # also check if the run has more unexpected files
        run_manifest = None
        mf = d / "run_manifest.json"
        if mf.exists():
            try:
                run_manifest = json.loads(mf.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        runs.append({
            "date": date_str,
            "dir": str(d),
            "file_count": len(present),
            "complete": len(missing) == 0,
            "missing": missing,
            "has_manifest": run_manifest is not None,
            "manifest_command": run_manifest.get("command") if run_manifest else None,
            "manifest_live": run_manifest.get("live") if run_manifest else None,
        })

    # Facts
    facts_db = root / "facts" / "auto_launch_facts.sqlite"
    facts_exists = facts_db.exists()
    facts_size = facts_db.stat().st_size if facts_exists else 0

    # Briefs (standalone, not inside runs)
    briefs_dir = root / "briefs"
    briefs_files = sorted(briefs_dir.glob("*.md")) if briefs_dir.exists() else []
    briefs_list = []
    for bf in briefs_files:
        date_key = bf.stem  # e.g. 2026-07-09
        duplicate = False
        run_dir = root / "runs" / date_key.replace("-", "")
        if run_dir.exists() and (run_dir / "daily_brief.md").exists():
            duplicate = True
        briefs_list.append({"path": str(bf), "date": date_key, "duplicate_brief": duplicate})

    # Search / owned_brand_daily / search_cache counts
    dir_stats = {}
    for sub in ["search", "owned_brand_daily", "search_cache"]:
        p = root / sub
        if p.exists():
            files = sorted(p.rglob("*"))
            dir_stats[sub] = {
                "file_count": sum(1 for f in files if f.is_file()),
                "dir_count": sum(1 for f in files if f.is_dir()),
            }
        else:
            dir_stats[sub] = {"file_count": 0, "dir_count": 0}

    # Warnings
    warnings = []
    if not facts_exists:
        warnings.append("facts/auto_launch_facts.sqlite 不存在 — 事实库为空")
    incomplete_runs = [r for r in runs if not r["complete"]]
    if incomplete_runs:
        names = ", ".join(r["date"] for r in incomplete_runs[:3])
        total = len(incomplete_runs)
        warnings.append(f"不完整 run: {names} ({total} 个)")
    duplicate_briefs = [b for b in briefs_list if b["duplicate_brief"]]
    if duplicate_briefs:
        warnings.append(f"briefs/ 中存在 {len(duplicate_briefs)} 个重复 daily_brief（与 runs/*/daily_brief.md 重复）")

    return {
        "outputs_root": str(root),
        "runs": {"count": len(runs), "complete": sum(1 for r in runs if r["complete"]), "list": runs},
        "facts": {"exists": facts_exists, "size_bytes": facts_size, "path": str(facts_db) if facts_exists else None},
        "briefs": {"count": len(briefs_list), "duplicate_count": len(duplicate_briefs), "list": briefs_list},
        "search": dir_stats["search"],
        "owned_brand_daily": dir_stats["owned_brand_daily"],
        "search_cache": dir_stats["search_cache"],
        "warnings": warnings,
    }


def clean_dry_run(older_than_days: int | None = None, keep_runs: bool = True) -> dict:
    """Identify files that are safe to delete, grouped by category.

    Never listed: facts/auto_launch_facts.sqlite, runs/*/ main output files.
    """
    root = OUTPUTS_ROOT
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

    # search
    search_files = []
    for f in sorted(root.glob("search/**/*")):
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if _should_include(mtime):
            search_files.append(str(f))
            total_size += f.stat().st_size
            total_files += 1
    candidates["search"] = search_files

    # owned_brand_daily
    obd_files = []
    for f in sorted(root.glob("owned_brand_daily/**/*")):
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if _should_include(mtime):
            obd_files.append(str(f))
            total_size += f.stat().st_size
            total_files += 1
    candidates["owned_brand_daily"] = obd_files

    # briefs (standalone) — only mark as deletable if duplicate with runs
    brief_files = []
    for f in sorted(root.glob("briefs/*.md")):
        if not f.is_file():
            continue
        date_key = f.stem
        run_dir = root / "runs" / date_key.replace("-", "")
        if run_dir.exists() and (run_dir / "daily_brief.md").exists():
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if _should_include(mtime):
                brief_files.append({
                    "path": str(f),
                    "reason": "duplicate_brief — 同日期 runs/*/daily_brief.md 已存在",
                })
                total_size += f.stat().st_size
                total_files += 1
    candidates["briefs_duplicate"] = brief_files

    # Summary
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
    lines.append(f"{'date':<14} {'complete':<10} {'files':<7} {'missing':<30}")
    lines.append("-" * 61)
    for r in report["runs"]["list"]:
        status = "✓" if r["complete"] else "✗"
        missing_str = ", ".join(r["missing"][:3]) if r["missing"] else "—"
        lines.append(f"{r['date']:<14} {status:<10} {r['file_count']:<7} {missing_str:<30}")
    lines.append("")

    # Facts
    f = report["facts"]
    status = "✓" if f["exists"] else "✗"
    size_kb = round(f["size_bytes"] / 1024, 1) if f["exists"] else 0
    lines.append(f"## Facts")
    lines.append("")
    lines.append(f"- **SQLite:** {status} ({size_kb} KB)" if f["exists"] else "- **SQLite:** ✗")
    lines.append("")

    # Briefs
    lines.append(f"## Briefs (standalone)")
    lines.append("")
    for b in report["briefs"]["list"]:
        dup = " ⚠ duplicate" if b["duplicate_brief"] else ""
        lines.append(f"- {b['date']}: {b['path']}{dup}")
    lines.append("")

    # Debug dirs
    for label in ["search", "owned_brand_daily", "search_cache"]:
        s = report[label]
        lines.append(f"## {label}")
        lines.append("")
        lines.append(f"- {s['file_count']} files, {s['dir_count']} dirs")
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
        if category == "briefs_duplicate":
            lines.append(f"## Briefs (duplicate)")
            for f in files:
                lines.append(f"- {f['path']}  ({f['reason']})")
        else:
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
