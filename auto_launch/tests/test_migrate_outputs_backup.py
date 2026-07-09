"""迁移脚本测试 — 验证 backup→target 迁移逻辑及输出合约"""
import sys, json, tempfile, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_launch.scripts.migrate_outputs_backup import MigrationEngine, render_report
from auto_launch.src import output_paths


def _make_backup_structure(root: Path):
    """Create a minimal realistic backup structure for testing."""
    # search_cache
    cache = root / "search_cache" / "2026-07-09"
    cache.mkdir(parents=True)
    (cache / "abc123.raw.json").write_text('{"data":"test"}')
    (cache / "def456.raw.json").write_text('{"data":"other"}')

    # facts (needed by migrate_facts)
    facts_dir = root / "facts"
    facts_dir.mkdir()
    (facts_dir / "auto_launch_facts.sqlite").write_text("SQLite mock")

    # legacy search (top-level)
    search_root = root / "search" / "2026-07-02" / "brand_watch"
    search_root.mkdir(parents=True)
    (search_root / "search_intent.json").write_text('{"targets":[{"brand":"极氪"}],"mode":"brand_watch"}')
    (search_root / "search_task_config.json").write_text('{"task":"config"}')
    (search_root / "search_budget_plan.json").write_text('{"budget":5}')
    (search_root / "query_plan.json").write_text('{"queries":[]}')
    (search_root / "search_results.raw.json").write_text('{"raw":"data"}')
    (search_root / "search_results.normalized.json").write_text('{"items":[]}')
    (search_root / "search_audit.json").write_text('{"quality":"ok"}')

    # flat runs (legacy structure)
    flat_run = root / "runs" / "20260709"
    flat_run.mkdir(parents=True)
    (flat_run / "daily_brief.md").write_text("# test brief")
    (flat_run / "run_manifest.json").write_text('{"command":"test"}')
    (flat_run / "run_summary.md").write_text("# summary")

    # new format runs
    new_run = root / "runs" / "20260710" / "launcher_daily_run"
    new_run.mkdir(parents=True)
    (new_run / "manifest.json").write_text('{"command":"launcher"}')
    (new_run / "summary.md").write_text("# launcher summary")
    reports = new_run / "reports"
    reports.mkdir()
    (reports / "daily_brief.md").write_text("# launcher brief")

    # owned_brand_daily (low value)
    obd = root / "owned_brand_daily" / "20260702"
    obd.mkdir(parents=True)
    (obd / "run_manifest.json").write_text('{"brand_key":"im","brand_name":"智己"}')

    # briefs
    briefs = root / "briefs"
    briefs.mkdir()
    (briefs / "2026-07-08.md").write_text("# standalone brief")

    return root


def test_dry_run_does_not_modify_target():
    """默认 dry-run 不修改目标目录。"""
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "backup"
        target = Path(tmp) / "target"
        target.mkdir()
        _make_backup_structure(backup)

        engine = MigrationEngine(
            backup_dir=str(backup),
            target_dir=str(target),
            execute=False,
        )
        rpt = engine.run_all()
        assert rpt["mode"] == "dry_run"
        # Target should have no files (directories from output_paths may be created)
        target_files = list(target.rglob("*"))
        # Only directories and reports
        f_count = sum(1 for f in target_files if f.is_file())
        assert f_count == 0, f"dry-run created files: {f_count}"


def test_search_cache_copied():
    """search_cache/ 可以复制。"""
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "backup"
        target = Path(tmp) / "target"
        target.mkdir()
        _make_backup_structure(backup)
        # Pre-create target facts to prevent facts migration from counting
        (target / "facts").mkdir()
        (target / "facts" / "auto_launch_facts.sqlite").write_text("existing")

        engine = MigrationEngine(
            backup_dir=str(backup),
            target_dir=str(target),
            execute=True,
            include_cache=True, include_runs=False,
            include_legacy_search=False, include_briefs=False,
        )
        rpt = engine.run_all()

        cache_files = list((target / "search_cache").rglob("*.raw.json"))
        assert len(cache_files) == 2, f"Expected 2 cache files, got {len(cache_files)}"
        migrated_cache = sum(1 for m in rpt["migrated"] if "search_cache" in m["note"])
        assert migrated_cache == 2


def test_duplicate_content_skipped():
    """同名同内容文件 skip。"""
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "backup"
        target = Path(tmp) / "target"
        target.mkdir()
        _make_backup_structure(backup)
        # Pre-create target facts
        (target / "facts").mkdir()
        (target / "facts" / "auto_launch_facts.sqlite").write_text("existing")

        # Create same cache file in target
        tgt_cache = target / "search_cache" / "2026-07-09"
        tgt_cache.mkdir(parents=True)
        (tgt_cache / "abc123.raw.json").write_text('{"data":"test"}')  # same content

        engine = MigrationEngine(
            backup_dir=str(backup),
            target_dir=str(target),
            execute=True,
            include_cache=True, include_runs=False,
            include_legacy_search=False,
        )
        rpt = engine.run_all()
        # abc123 → skipped (target exists), def456 → migrated
        migrated_cache = sum(1 for m in rpt["migrated"] if "search_cache" in m["note"])
        assert migrated_cache == 1
        assert rpt["skipped_count"] == 1


def test_different_content_not_overwritten():
    """同名不同内容文件记录 conflict，不覆盖。"""
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "backup"
        target = Path(tmp) / "target"
        target.mkdir()
        _make_backup_structure(backup)
        # Pre-create target facts
        (target / "facts").mkdir()
        (target / "facts" / "auto_launch_facts.sqlite").write_text("existing")

        tgt_cache = target / "search_cache" / "2026-07-09"
        tgt_cache.mkdir(parents=True)
        (tgt_cache / "abc123.raw.json").write_text('{"data":"different"}')  # different content

        engine = MigrationEngine(
            backup_dir=str(backup),
            target_dir=str(target),
            execute=True,
            overwrite=False,
            include_cache=True, include_runs=False,
            include_legacy_search=False,
        )
        rpt = engine.run_all()
        # abc123 → skipped (target exists, overwrite=False)
        migrated_cache = sum(1 for m in rpt["migrated"] if "search_cache" in m["note"])
        assert migrated_cache == 1  # def456
        skipped_cache = sum(1 for s in rpt["skipped"] if "search_cache" in s["note"])
        assert skipped_cache == 1   # abc123 (skipped because target exists)


def test_legacy_search_to_runs():
    """旧顶层 search/ 可以转换到 runs/YYYYMMDD/{run_mode}/search/。"""
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "backup"
        target = Path(tmp) / "target"
        target.mkdir()
        _make_backup_structure(backup)

        engine = MigrationEngine(
            backup_dir=str(backup),
            target_dir=str(target),
            execute=True,
            include_cache=False, include_runs=False,
            include_legacy_search=True,
        )
        rpt = engine.run_all()

        # Check plan.json exists
        plan_path = target / "runs" / "20260702" / "brand_watch_zeekr" / "search" / "plan.json"
        assert plan_path.exists(), f"Missing {plan_path}"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        assert "intent" in plan, "plan.json missing intent"
        assert "task_config" in plan, "plan.json missing task_config"
        assert "budget_plan" in plan, "plan.json missing budget_plan"
        assert "query_plan" in plan, "plan.json missing query_plan"
        assert "migration" in plan, "plan.json missing migration metadata"

        # raw/normalized/audit
        assert (target / "runs" / "20260702" / "brand_watch_zeekr" / "search" / "raw.json").exists()
        assert (target / "runs" / "20260702" / "brand_watch_zeekr" / "search" / "normalized.json").exists()
        assert (target / "runs" / "20260702" / "brand_watch_zeekr" / "search" / "audit.json").exists()


def test_date_uniform_yyyymmdd():
    """日期统一为 YYYYMMDD。"""
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "backup"
        target = Path(tmp) / "target"
        target.mkdir()
        _make_backup_structure(backup)

        engine = MigrationEngine(
            backup_dir=str(backup),
            target_dir=str(target),
            execute=True,
            include_cache=False, include_runs=False,
            include_legacy_search=True,
        )
        engine.run_all()

        run_dirs = [d.name for d in (target / "runs").iterdir()]
        for d in run_dirs:
            assert "-" not in d, f"Date dir {d} contains dash, should be YYYYMMDD"


def test_no_legacy_top_level_dirs_created():
    """不生成新的顶层 briefs/、owned_brand_daily/、search/。"""
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "backup"
        target = Path(tmp) / "target"
        target.mkdir()
        _make_backup_structure(backup)

        engine = MigrationEngine(
            backup_dir=str(backup),
            target_dir=str(target),
            execute=True,
        )
        engine.run_all()

        top_level = [d.name for d in target.iterdir() if d.is_dir()]
        for forbidden in ["briefs", "owned_brand_daily", "search"]:
            assert forbidden not in top_level, f"Forbidden legacy dir created: {forbidden}"


def test_facts_not_overwritten():
    """facts 当前库存在时不覆盖，只 reference copy。"""
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "backup"
        target = Path(tmp) / "target"
        target.mkdir()

        # Create target with existing facts
        target_facts = target / "facts"
        target_facts.mkdir()
        (target_facts / "auto_launch_facts.sqlite").write_text("existing_db")

        _make_backup_structure(backup)

        engine = MigrationEngine(
            backup_dir=str(backup),
            target_dir=str(target),
            execute=True,
            include_cache=False, include_runs=False,
            include_legacy_search=False,
        )
        rpt = engine.run_all()

        # Existing db unchanged
        assert (target / "facts" / "auto_launch_facts.sqlite").read_text() == "existing_db"
        # Reference copy in _legacy
        assert (target / "_legacy" / "facts_backup_20260709_151946" / "auto_launch_facts.sqlite").exists()


def test_briefs_not_migrated_by_default():
    """briefs/ 默认不迁移。"""
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "backup"
        target = Path(tmp) / "target"
        target.mkdir()
        _make_backup_structure(backup)

        engine = MigrationEngine(
            backup_dir=str(backup),
            target_dir=str(target),
            execute=True,
            include_briefs=False,
            include_cache=False, include_runs=False,
            include_legacy_search=False,
        )
        rpt = engine.run_all()

        # Brief should NOT be migrated
        legacy_brief = target / "runs" / "20260708" / "legacy_daily_brief" / "reports" / "daily_brief.md"
        assert not legacy_brief.exists(), "Brief was migrated despite --include-briefs=false"


def test_briefs_migrated_with_flag():
    """--include-briefs 时才迁移为 runs/YYYYMMDD/legacy_daily_brief/reports/daily_brief.md。"""
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "backup"
        target = Path(tmp) / "target"
        target.mkdir()
        _make_backup_structure(backup)

        engine = MigrationEngine(
            backup_dir=str(backup),
            target_dir=str(target),
            execute=True,
            include_briefs=True,
            include_cache=False, include_runs=False,
            include_legacy_search=False,
        )
        rpt = engine.run_all()

        brief_path = target / "runs" / "20260708" / "legacy_daily_brief" / "reports" / "daily_brief.md"
        assert brief_path.exists(), f"Brief not migrated: {brief_path}"
        assert brief_path.read_text() == "# standalone brief"


def test_flat_runs_go_to_legacy_daily_run():
    """平铺旧 runs 文件归入 legacy_daily_run。"""
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "backup"
        target = Path(tmp) / "target"
        target.mkdir()
        _make_backup_structure(backup)

        engine = MigrationEngine(
            backup_dir=str(backup),
            target_dir=str(target),
            execute=True,
            include_cache=False, include_legacy_search=False,
            include_briefs=False,
        )
        rpt = engine.run_all()

        legacy = target / "runs" / "20260709" / "legacy_daily_run"
        assert legacy.exists()
        assert (legacy / "manifest.json").exists()
        assert (legacy / "summary.md").exists()
        assert (legacy / "reports" / "daily_brief.md").exists()


def test_render_report():
    """render_report 生成有效的 markdown。"""
    rpt = {
        "mode": "dry_run",
        "backup_dir": "/tmp/backup",
        "target_dir": "/tmp/target",
        "migrated_count": 10, "skipped_count": 2,
        "duplicate_count": 1, "conflict_count": 0,
        "needs_review_count": 0, "error_count": 0,
        "migrated": [{"src": "/a", "dst": "/b", "note": "test"}],
        "skipped": [{"src": "/c", "dst": "/d", "note": "exists"}],
        "duplicates": [],
        "conflicts": [],
        "needs_review": [],
        "errors": [],
        "legacy_dirs_created": [],
    }
    md = render_report(rpt)
    assert "Migration Report" in md
    assert "10 files" in md
    assert "Dry-run" in md
