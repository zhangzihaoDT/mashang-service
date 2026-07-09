"""
migrate_outputs_backup.py — 将旧备份 output 目录中的可复用产物安全迁移到当前 outputs 标准结构。

规则:
  1. 默认 dry-run，不修改任何文件。
  2. search_cache/ 直接复制，同名同内容 skip，不同内容 conflict。
  3. search/ 转换为 runs/{YYYYMMDD}/{run_mode}/search/{plan,raw,normalized,audit}.json。
  4. runs/ 已有新格式的补充缺失文件，平铺旧文件归入 legacy_daily_run。
  5. briefs/ 默认不迁移，仅当 --include-briefs 且有同日期无 run 日报时。
  6. facts/ 仅 reference copy 到 _legacy/，不覆盖当前库。
  7. owned_brand_daily/ 低价值，仅迁移 manifest。
  8. demo/ 跳过。

用法:
  # dry-run (default)
  python scripts/migrate_outputs_backup.py --backup-dir <path>

  # execute
  python scripts/migrate_outputs_backup.py --backup-dir <path> --execute

  # with options
  python scripts/migrate_outputs_backup.py --backup-dir <path> --execute --include-briefs --overwrite
"""

import json, sys, shutil, hashlib
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_launch.src import output_paths

# ── Helpers ─────────────────────────────────────────────────────

def _file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _date_to_yyyymmdd(date_str: str) -> str:
    return date_str.replace("-", "")


def _parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Migrate backup outputs to current standard structure")
    p.add_argument("--backup-dir", required=True, help="备份输出目录路径")
    p.add_argument("--target-dir", default=None, help="目标目录 (默认 output_paths.output_root())")
    p.add_argument("--execute", action="store_true", help="实际执行复制迁移")
    p.add_argument("--overwrite", action="store_true", help="覆盖已存在的目标文件")
    p.add_argument("--include-cache", action="store_true", default=True, help="迁移 search_cache (默认开启)")
    p.add_argument("--include-runs", action="store_true", default=True, help="迁移已有 runs (默认开启)")
    p.add_argument("--include-legacy-search", action="store_true", default=True, help="将旧顶层 search 转换到 runs/ (默认开启)")
    p.add_argument("--include-briefs", action="store_true", default=False, help="迁移旧 briefs 到 runs/ (默认关闭)")
    p.add_argument("--merge-facts", action="store_true", default=False, help="尝试安全合并历史事实库 (默认关闭)")
    return p.parse_args()


# ── Brand name helpers ──────────────────────────────────────────

# Mapping of Chinese brand names to slugs for run_mode
BRAND_SLUGS = {
    "极氪": "zeekr",
    "智己": "zhiji",
    "蔚来": "nio",
    "理想": "lixiang",
    "小米": "xiaomi",
    "小鹏": "xpeng",
    "比亚迪": "byd",
    "特斯拉": "tesla",
    "阿维塔": "avatr",
    "零跑": "leapmotor",
    "腾势": "denza",
    "方程豹": "fangchengbao",
    "问界": "aito",
    "智界": "luxeed",
    "享界": "stelato",
    "尊界": "zunjie",
    "尚界": "shangjie",
    "鸿蒙智行": "harmony",
    "乐道": "ledao",
    "萤火虫": "firefly",
    "深蓝": "deepal",
    "岚图": "voyah",
    "领克": "lynkco",
    "埃安": "aion",
    "极氪科技": "zeekr",
    "蔚来汽车": "nio",
    "小鹏汽车": "xpeng",
}


def _brand_slug(name: str) -> str:
    return BRAND_SLUGS.get(name, name)


def _resolve_brand_watch_run_mode(mode: str, fallback_brand: str = "unknown") -> str:
    if mode == "brand_watch":
        slug = _brand_slug(fallback_brand)
        return output_paths.run_mode_brand_watch(slug)
    return mode


# ── Migration Engine ────────────────────────────────────────────

class MigrationEngine:
    def __init__(self, backup_dir: str, target_dir: str | None = None,
                 execute: bool = False, overwrite: bool = False,
                 include_cache: bool = True, include_runs: bool = True,
                 include_legacy_search: bool = True,
                 include_briefs: bool = False, merge_facts: bool = False):
        self.backup = Path(backup_dir)
        self.target = Path(target_dir) if target_dir else output_paths.output_root()
        self.execute = execute
        self.overwrite = overwrite
        self.include_cache = include_cache
        self.include_runs = include_runs
        self.include_legacy_search = include_legacy_search
        self.include_briefs = include_briefs
        self.merge_facts = merge_facts

        self.migrated = []
        self.skipped = []
        self.duplicates = []
        self.conflicts = []
        self.needs_review = []
        self.errors = []

        self.legacy_dirs_created = set()

    # ── Target-aware path helpers ──────────────────────────
    # These replace output_paths.* to use self.target as root.

    def _cache_dir(self) -> Path:
        p = self.target / "search_cache"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _runs_dir(self) -> Path:
        return self.target / "runs"

    def _run_dir(self, date_str: str, run_mode: str) -> Path:
        d = self.target / "runs" / date_str.replace("-", "") / run_mode
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _search_dir(self, date_str: str, run_mode: str) -> Path:
        d = self._run_dir(date_str, run_mode) / "search"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _reports_dir(self, date_str: str, run_mode: str) -> Path:
        d = self._run_dir(date_str, run_mode) / "reports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _run_manifest_path(self, date_str: str, run_mode: str) -> Path:
        return self._run_dir(date_str, run_mode) / "manifest.json"

    def _run_summary_path(self, date_str: str, run_mode: str) -> Path:
        return self._run_dir(date_str, run_mode) / "summary.md"

    def _daily_brief_md_path(self, date_str: str, run_mode: str) -> Path:
        return self._reports_dir(date_str, run_mode) / "daily_brief.md"

    def _legacy_dir(self) -> Path:
        p = self.target / "_legacy"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ── Low-level copy helpers ─────────────────────────────

    def _copy_file(self, src: Path, dst: Path, note: str = ""):
        if dst.exists():
            if self.overwrite:
                src_hash = _file_hash(src)
                dst_hash = _file_hash(dst)
                if src_hash == dst_hash:
                    self.duplicates.append({"src": str(src), "dst": str(dst), "note": note})
                    return
                self.conflicts.append({"src": str(src), "dst": str(dst),
                                       "note": f"{note} — overwrite mode, replacing"})
                if self.execute:
                    dst.write_bytes(src.read_bytes())
                    self.migrated.append({"src": str(src), "dst": str(dst), "note": f"{note} (overwritten)"})
            else:
                self.skipped.append({"src": str(src), "dst": str(dst), "note": f"{note} — target exists"})
            return

        dst.parent.mkdir(parents=True, exist_ok=True)
        if self.execute:
            shutil.copy2(str(src), str(dst))
        self.migrated.append({"src": str(src), "dst": str(dst), "note": note})

    def _write_json(self, dst: Path, data: dict, note: str = ""):
        """Write a JSON file only if execute mode."""
        if self.execute:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.migrated.append({"src": "(merged)", "dst": str(dst), "note": note})

    def _check_legacy_dir(self, path: Path):
        """Track any new legacy top-level dirs created."""
        for legacy_name in ["briefs", "owned_brand_daily", "search"]:
            if path.parts and legacy_name in path.parts:
                idx = path.parts.index(legacy_name)
                if idx > 0 and path.parts[idx - 1] == self.target.name:
                    self.legacy_dirs_created.add(str(path.parents[len(path.parts) - idx - 1] / legacy_name))

    # ── 1. search_cache ───────────────────────────────────

    def migrate_search_cache(self):
        src_cache = self.backup / "search_cache"
        if not src_cache.exists():
            return
        dst_cache = self._cache_dir()
        for f in sorted(src_cache.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(src_cache)
            dst = dst_cache / rel
            self._copy_file(f, dst, note="search_cache")

    # ── 2. legacy top-level search/ → runs/ ──────────────

    def migrate_legacy_search(self):
        src_search = self.backup / "search"
        if not src_search.exists():
            return

        for date_dir in sorted(src_search.iterdir()):
            if not date_dir.is_dir():
                continue
            date_orig = date_dir.name  # e.g. 2026-07-02
            date_flat = _date_to_yyyymmdd(date_orig)

            for mode_dir in sorted(date_dir.iterdir()):
                if not mode_dir.is_dir():
                    continue
                mode_name = mode_dir.name  # e.g. brand_watch, model_watch

                # Determine run_mode and brand label
                files = list(mode_dir.iterdir())
                intent_file = mode_dir / "search_intent.json"
                brand_label = "unknown"
                if intent_file.exists():
                    try:
                        intent = json.loads(intent_file.read_text(encoding="utf-8"))
                        targets = intent.get("targets", [])
                        if targets:
                            brand_label = targets[0].get("brand", targets[0].get("target_id", "unknown"))
                    except (json.JSONDecodeError, OSError):
                        pass

                run_mode = _resolve_brand_watch_run_mode(mode_name, brand_label)
                if run_mode == mode_name and brand_label == "unknown":
                    self.needs_review.append(f"search/{date_orig}/{mode_name}: could not determine run_mode")

                # Build merged plan
                plan_parts = {}
                plan_sources = []
                for fname, key in [("search_intent.json", "intent"),
                                    ("search_task_config.json", "task_config"),
                                    ("search_budget_plan.json", "budget_plan"),
                                    ("query_plan.json", "query_plan")]:
                    fp = mode_dir / fname
                    if fp.exists():
                        try:
                            plan_parts[key] = json.loads(fp.read_text(encoding="utf-8"))
                            plan_sources.append(str(fp))
                        except (json.JSONDecodeError, OSError):
                            plan_parts[key] = {"migration_error": f"could not parse {fname}"}

                plan_parts["migration"] = {
                    "source_backup": str(self.backup),
                    "source_files": plan_sources,
                    "migrated_at": datetime.now(timezone.utc).isoformat(),
                    "notes": [f"Migrated from backup search/{date_orig}/{mode_name}"]
                }

                target_search_dir = self._search_dir(date_flat, run_mode)

                # Write plan.json
                if plan_parts:
                    plan_dst = target_search_dir / "plan.json"
                    if plan_dst.exists() and not self.overwrite:
                        self.skipped.append({"src": "(merged plan)", "dst": str(plan_dst),
                                            "note": f"search/{date_orig}/{mode_name} → plan.json exists"})
                    else:
                        self._write_json(plan_dst, plan_parts, note=f"search/{date_orig}/{mode_name} → plan.json")

                # Map file names: old → new
                file_map = {
                    "search_results.raw.json": "raw.json",
                    "search_results.normalized.json": "normalized.json",
                    "search_audit.json": "audit.json",
                }
                for old_name, new_name in file_map.items():
                    src_f = mode_dir / old_name
                    if not src_f.exists():
                        continue
                    dst_f = target_search_dir / new_name
                    self._copy_file(src_f, dst_f, note=f"search/{date_orig}/{mode_name}/{old_name} → {new_name}")

    # ── 3. runs/ — merge ─────────────────────────────────

    def migrate_runs(self):
        src_runs = self.backup / "runs"
        if not src_runs.exists():
            return
        dst_runs = self._runs_dir()

        for date_dir in sorted(src_runs.iterdir()):
            if not date_dir.is_dir():
                continue
            date_flat = date_dir.name  # YYYYMMDD

            for mode_dir in sorted(date_dir.iterdir()):
                if not mode_dir.is_dir():
                    continue
                run_mode = mode_dir.name
                dst_mode = dst_runs / date_flat / run_mode

                for f in mode_dir.rglob("*"):
                    if not f.is_file():
                        continue
                    rel = f.relative_to(date_dir / run_mode)
                    dst = dst_mode / rel
                    self._copy_file(f, dst, note=f"runs/{date_flat}/{run_mode}/{rel}")

            # Flat legacy files at runs/{date}/* — no run_mode subdir
            flat_files = [f for f in date_dir.iterdir() if f.is_file()]
            if flat_files:
                legacy_mode = "legacy_daily_run"
                dst_legacy = dst_runs / date_flat / legacy_mode
                for f in flat_files:
                    # Map to new structure
                    name = f.name
                    if name == "run_manifest.json":
                        dst = dst_legacy / "manifest.json"
                    elif name == "run_summary.md":
                        dst = dst_legacy / "summary.md"
                    elif name == "daily_brief.md":
                        dst = dst_legacy / "reports" / "daily_brief.md"
                    elif name == "facts_audit.json":
                        dst = dst_legacy / "facts" / "facts_audit.json"
                    elif name == "source_audit.json":
                        dst = dst_legacy / "reports" / "source_audit.json"
                    elif name == "source_audit.md":
                        dst = dst_legacy / "reports" / "source_audit.md"
                    else:
                        dst = dst_legacy / name
                    self._copy_file(f, dst, note=f"runs/{date_flat}/flat/{name} → {legacy_mode}/{dst.name}")

    # ── 4. briefs/ ───────────────────────────────────────

    def migrate_briefs(self):
        if not self.include_briefs:
            return
        src_briefs = self.backup / "briefs"
        if not src_briefs.exists():
            return

        for f in sorted(src_briefs.glob("*.md")):
            date_str = f.stem  # YYYY-MM-DD
            date_flat = _date_to_yyyymmdd(date_str)

            # Only migrate if no corresponding run has a brief
            # Check if any run_mode for this date has daily_brief.md
            has_brief = False
            run_date_dir = self._runs_dir() / date_flat
            if run_date_dir.exists():
                for mode_dir in run_date_dir.iterdir():
                    if (mode_dir / "reports" / "daily_brief.md").exists():
                        has_brief = True
                        break

            if has_brief:
                self.skipped.append({"src": str(f), "dst": "(none)",
                                    "note": f"briefs/{f.name} — skip, runs/{date_flat} has daily_brief"})
                continue

            # Migrate to legacy_daily_brief mode
            run_mode = "legacy_daily_brief"
            dst = self._daily_brief_md_path(date_flat, run_mode)
            self._copy_file(f, dst, note=f"briefs/{f.name} → legacy_daily_brief/reports/daily_brief.md")

    # ── 5. owned_brand_daily/ ────────────────────────────

    def migrate_owned_brand_daily(self):
        src_obd = self.backup / "owned_brand_daily"
        if not src_obd.exists():
            return

        for date_dir in sorted(src_obd.iterdir()):
            if not date_dir.is_dir():
                continue
            date_flat = date_dir.name  # YYYYMMDD (already)

            manifest_src = date_dir / "run_manifest.json"
            if not manifest_src.exists():
                continue

            # Try to determine brand from manifest
            brand = "unknown"
            try:
                m = json.loads(manifest_src.read_text(encoding="utf-8"))
                brand = m.get("brand_key", m.get("brand_name", brand))
            except (json.JSONDecodeError, OSError):
                pass

            run_mode = output_paths.run_mode_owned_brand_daily(brand)

            # Only migrate if target doesn't have a manifest
            dst_manifest = self._run_manifest_path(date_flat, run_mode)
            if dst_manifest.exists():
                self.skipped.append({"src": str(manifest_src), "dst": str(dst_manifest),
                                    "note": f"owned_brand_daily/{date_flat} — target manifest exists"})
                continue

            # Add migration metadata
            try:
                manifest_data = json.loads(manifest_src.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                manifest_data = {"migration_note": "could not parse original manifest"}
            manifest_data.setdefault("migration", {})
            manifest_data["migration"]["source_backup"] = str(self.backup)
            manifest_data["migration"]["migrated_at"] = datetime.now(timezone.utc).isoformat()
            manifest_data["migration"]["notes"] = ["Migrated from owned_brand_daily backup"]

            self._write_json(dst_manifest, manifest_data,
                            note=f"owned_brand_daily/{date_flat} → {run_mode}/manifest.json")

    # ── 6. facts/ — reference copy ───────────────────────

    def migrate_facts(self):
        src_facts = self.backup / "facts" / "auto_launch_facts.sqlite"
        if not src_facts.exists():
            return

        target_facts = self.target / "facts" / "auto_launch_facts.sqlite"
        if target_facts.exists() and not self.merge_facts:
            # Reference copy to _legacy
            legacy_facts_dir = self._legacy_dir() / "facts_backup_20260709_151946"
            legacy_facts_dir.mkdir(parents=True, exist_ok=True)
            dst = legacy_facts_dir / "auto_launch_facts.sqlite"
            self._copy_file(src_facts, dst,
                           note="facts reference copy (current db exists, not overwritten)")
            return

        if not target_facts.exists():
            # No current facts db — safe to copy
            self._copy_file(src_facts, target_facts, note="facts — target did not exist, copied")
            return

        # merge_facts mode — SQLite ATTACH + INSERT OR IGNORE
        if self.merge_facts and target_facts.exists():
            self._merge_facts_sqlite(src_facts, target_facts)

    def _merge_facts_sqlite(self, src: Path, dst: Path):
        """Merge facts via SQLite ATTACH."""
        import sqlite3
        try:
            conn = sqlite3.connect(str(dst))
            c = conn.cursor()
            c.execute("ATTACH DATABASE ? AS backup", (str(src),))
            # Check schema compatibility
            c.execute("SELECT sql FROM backup.sqlite_master WHERE type='table' AND name='facts'")
            backup_schema = c.fetchone()
            c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='facts'")
            current_schema = c.fetchone()
            if backup_schema and current_schema and backup_schema[0] == current_schema[0]:
                c.execute("INSERT OR IGNORE INTO facts SELECT * FROM backup.facts")
                inserted = c.rowcount
                conn.commit()
                self.migrated.append({"src": str(src), "dst": str(dst),
                                      "note": f"facts — merged {inserted} new rows via INSERT OR IGNORE"})
            else:
                self.skipped.append({"src": str(src), "dst": str(dst),
                                    "note": "facts — schema mismatch, cannot auto-merge"})
            conn.close()
        except Exception as e:
            self.errors.append({"src": str(src), "dst": str(dst), "error": str(e)})

    # ── 7. demo/ — skip ──────────────────────────────────

    def migrate_demo(self):
        pass  # Explicitly skip demo

    # ── Run all ──────────────────────────────────────────

    def run_all(self):
        if self.include_cache:
            self.migrate_search_cache()
        if self.include_legacy_search:
            self.migrate_legacy_search()
        if self.include_runs:
            self.migrate_runs()
            self.migrate_owned_brand_daily()
        self.migrate_briefs()
        self.migrate_facts()
        self.migrate_demo()
        return self.report()

    def report(self) -> dict:
        return {
            "mode": "execute" if self.execute else "dry_run",
            "backup_dir": str(self.backup),
            "target_dir": str(self.target),
            "migrated_count": len(self.migrated),
            "skipped_count": len(self.skipped),
            "duplicate_count": len(self.duplicates),
            "conflict_count": len(self.conflicts),
            "needs_review_count": len(self.needs_review),
            "error_count": len(self.errors),
            "migrated": self.migrated,
            "skipped": self.skipped,
            "duplicates": self.duplicates,
            "conflicts": self.conflicts,
            "needs_review": self.needs_review,
            "errors": self.errors,
            "legacy_dirs_created": list(self.legacy_dirs_created),
        }


# ── Render ──────────────────────────────────────────────────────

def render_report(rpt: dict) -> str:
    lines = ["# Migration Report — outputs_backup_20260709_151946", ""]
    lines.append(f"**Mode:** {rpt['mode']}  ")
    lines.append(f"**Backup:** {rpt['backup_dir']}  ")
    lines.append(f"**Target:** {rpt['target_dir']}  ")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Migrated: {rpt['migrated_count']} files")
    lines.append(f"- Skipped: {rpt['skipped_count']} files")
    lines.append(f"- Duplicates (same content): {rpt['duplicate_count']} files")
    lines.append(f"- Conflicts (different content): {rpt['conflict_count']} files")
    lines.append(f"- Needs review: {rpt['needs_review_count']} items")
    lines.append(f"- Errors: {rpt['error_count']} items")
    lines.append("")

    if rpt["legacy_dirs_created"]:
        lines.append("### ⚠ Legacy dirs would be created")
        for d in rpt["legacy_dirs_created"]:
            lines.append(f"- {d}")
        lines.append("")

    if rpt["migrated"]:
        lines.append("## Migrated Files")
        lines.append("")
        for m in rpt["migrated"]:
            lines.append(f"- {m['note']}")
            lines.append(f"  → {m['dst']}")
        lines.append("")

    if rpt["skipped"]:
        lines.append("## Skipped Files")
        lines.append("")
        for s in rpt["skipped"]:
            lines.append(f"- {s['note']}")
        lines.append("")

    if rpt["duplicates"]:
        lines.append("## Duplicates (same content, not copied)")
        lines.append("")
        for d in rpt["duplicates"]:
            lines.append(f"- {d['note']}")
        lines.append("")

    if rpt["conflicts"]:
        lines.append("## Conflicts (different content, not copied)")
        lines.append("")
        for c in rpt["conflicts"]:
            lines.append(f"- {c['note']}")
        lines.append("")

    if rpt["needs_review"]:
        lines.append("## Needs Review")
        lines.append("")
        for n in rpt["needs_review"]:
            lines.append(f"- ⚠ {n}")
        lines.append("")

    if rpt["errors"]:
        lines.append("## Errors")
        lines.append("")
        for e in rpt["errors"]:
            lines.append(f"- {e.get('error', 'unknown')}: {e['src']}")
        lines.append("")

    if rpt["mode"] == "dry_run":
        lines.append("---")
        lines.append("*Dry-run — no files were modified. Pass --execute to perform migration.*")
    lines.append("")
    return "\n".join(lines)


def save_report_json(rpt: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rpt, ensure_ascii=False, indent=2), encoding="utf-8")



if __name__ == "__main__":
    args = _parse_args()

    engine = MigrationEngine(
        backup_dir=args.backup_dir,
        target_dir=args.target_dir,
        execute=args.execute,
        overwrite=args.overwrite,
        include_cache=args.include_cache,
        include_runs=args.include_runs,
        include_legacy_search=args.include_legacy_search,
        include_briefs=args.include_briefs,
        merge_facts=args.merge_facts,
    )

    rpt = engine.run_all()

    md = render_report(rpt)
    print(md)

    # Save report
    report_dir = output_paths.legacy_dir() / "migration_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    # Also save to target if specified
    if args.target_dir:
        tgt_report_dir = Path(args.target_dir) / "_legacy" / "migration_reports"
        tgt_report_dir.mkdir(parents=True, exist_ok=True)
    md_path = report_dir / "outputs_backup_20260709_151946_migration.md"
    json_path = report_dir / "outputs_backup_20260709_151946_migration.json"

    md_path.write_text(md, encoding="utf-8")
    save_report_json(rpt, json_path)
    print(f"\nReport saved: {md_path}")
    print(f"Report saved: {json_path}")
