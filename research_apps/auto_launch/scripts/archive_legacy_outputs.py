"""
archive_legacy_outputs.py — 将历史遗留输出目录归档到 _legacy/。

行为:
  - 默认 dry-run，显示将要归档的目录。
  - 只处理: briefs/、owned_brand_daily/、search/
  - 不处理: facts/、search_cache/、demo/
  - 归档目标: outputs/_legacy/{dirname}_{timestamp}/

用法:
  python scripts/archive_legacy_outputs.py                    # dry-run
  python scripts/archive_legacy_outputs.py --execute          # 实际执行
"""

import sys, shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auto_launch.src.output_paths import (
    LEGACY_SEARCH_ROOT, LEGACY_BRIEFS_DIR,
    LEGACY_OWNED_BRAND_DAILY, legacy_dir,
    facts_dir, cache_dir, demo_dir,
)


LEGACY_TARGETS = [
    ("search/", LEGACY_SEARCH_ROOT),
    ("briefs/", LEGACY_BRIEFS_DIR),
    ("owned_brand_daily/", LEGACY_OWNED_BRAND_DAILY),
]

PROTECTED_DIRS = [
    facts_dir(),
    cache_dir(),
    demo_dir(),
]


def archive(execute: bool = False) -> dict:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_root = legacy_dir()
    results = []
    total_size = 0

    for label, src in LEGACY_TARGETS:
        if not src.exists():
            results.append({"label": label, "status": "skipped", "reason": "not_exists", "path": str(src), "size_bytes": 0})
            continue

        # compute size
        size = sum(f.stat().st_size for f in src.rglob("*") if f.is_file()) if src.is_dir() else src.stat().st_size
        total_size += size

        dest_name = f"{src.name}_{timestamp}"
        dest = archive_root / dest_name

        if execute:
            shutil.move(str(src), str(dest))
            results.append({"label": label, "status": "archived", "path": str(src), "dest": str(dest), "size_bytes": size})
        else:
            results.append({"label": label, "status": "dry_run", "path": str(src), "dest": str(dest), "size_bytes": size})

    return {
        "mode": "execute" if execute else "dry_run",
        "timestamp": timestamp,
        "archive_root": str(archive_root),
        "total_size_bytes": total_size,
        "total_size_kb": round(total_size / 1024, 1),
        "protected_dirs": [str(p) for p in PROTECTED_DIRS],
        "results": results,
    }


def render_report(report: dict) -> str:
    lines = ["# Archive Legacy Outputs", ""]
    lines.append(f"**Mode:** {report['mode']}  ")
    lines.append(f"**Archive root:** {report['archive_root']}  ")
    lines.append(f"**Total size:** {report['total_size_kb']} KB  ")
    lines.append("")
    lines.append("**Protected (not moved):**")
    for p in report["protected_dirs"]:
        lines.append(f"  - {p}")
    lines.append("")
    lines.append("## Targets")
    lines.append("")
    for r in report["results"]:
        status_icon = {"archived": "✓", "dry_run": "→", "skipped": "−"}.get(r["status"], "?")
        size_kb = round(r["size_bytes"] / 1024, 1) if r["size_bytes"] else 0
        if r["status"] == "skipped":
            lines.append(f"  {status_icon} {r['label']:<20} — {r['reason']}")
        elif r["status"] == "dry_run":
            lines.append(f"  {status_icon} {r['label']:<20} {size_kb:>8} KB  → {r['dest']}")
        else:
            lines.append(f"  {status_icon} {r['label']:<20} {size_kb:>8} KB  → {r['dest']}")
    lines.append("")
    if report["mode"] == "dry_run":
        lines.append("---")
        lines.append("*Dry-run — 未移动任何文件。使用 --execute 实际执行。*")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    execute = "--execute" in sys.argv
    report = archive(execute=execute)
    print(render_report(report))
