"""output_manager 测试"""
import sys, os, tempfile, json
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Patch OUTPUTS_ROOT before importing
from auto_launch.src import output_manager
from auto_launch.src.output_manager import (
    inspect, clean_dry_run, render_inspect, render_clean_dry_run,
    RUN_REQUIRED_FILES, NEVER_CLEAN, OUTPUTS_ROOT,
)


# ── Helpers ───────────────────────────────────────────────────────

def _make_run(runs_dir: Path, date_str: str, complete: bool = True):
    """Create a simulated run directory with required files."""
    d = runs_dir / date_str.replace("-", "")
    d.mkdir(parents=True, exist_ok=True)
    files = RUN_REQUIRED_FILES if complete else ["run_manifest.json"]
    for fname in files:
        (d / fname).write_text("{}" if fname.endswith(".json") else "# test", encoding="utf-8")
    # write a real manifest
    manifest = {
        "command": "run-day", "monitor_date": date_str,
        "brand": "im", "brand_name": "智己",
        "live": False, "window_hours": 24,
        "brief_facts": 3, "kept": 1,
        "outputs": {"run_dir": str(d)},
        "log": [], "created_at": datetime.now().isoformat(),
    }
    (d / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def _make_brief(briefs_dir: Path, date_str: str):
    """Create a standalone brief."""
    briefs_dir.mkdir(parents=True, exist_ok=True)
    (briefs_dir / f"{date_str}.md").write_text("# brief", encoding="utf-8")


# ── Tests ─────────────────────────────────────────────────────────

def test_inspect_empty_outputs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            (root / "runs").mkdir(parents=True)
            (root / "facts").mkdir()
            report = inspect()
            assert report["runs"]["count"] == 0
            assert report["facts"]["exists"] is False
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


def test_inspect_complete_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            _make_run(root / "runs", "2026-07-09", complete=True)
            report = inspect()
            assert report["runs"]["count"] == 1
            assert report["runs"]["list"][0]["complete"] is True
            assert report["runs"]["list"][0]["date"] == "2026-07-09"
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


def test_inspect_incomplete_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            _make_run(root / "runs", "2026-07-09", complete=False)
            report = inspect()
            assert report["runs"]["count"] == 1
            assert report["runs"]["list"][0]["complete"] is False
            assert "facts_audit.json" in report["runs"]["list"][0]["missing"]
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


def test_inspect_facts_sqlite():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            (root / "facts").mkdir(parents=True)
            facts_db = root / "facts" / "auto_launch_facts.sqlite"
            facts_db.write_text("SQLite format 3", encoding="utf-8")
            report = inspect()
            assert report["facts"]["exists"] is True
            assert report["facts"]["size_bytes"] > 0
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


def test_inspect_duplicate_brief():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            _make_run(root / "runs", "2026-07-09", complete=True)
            _make_brief(root / "briefs", "2026-07-09")
            report = inspect()
            assert report["briefs"]["duplicate_count"] == 1
            assert report["briefs"]["list"][0]["duplicate_brief"] is True
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


def test_inspect_warnings_on_missing_facts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            (root / "runs").mkdir(parents=True)
            (root / "facts").mkdir()
            report = inspect()
            assert any("facts" in w for w in report["warnings"])
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


def test_clean_dry_run_never_includes_facts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            (root / "facts").mkdir(parents=True)
            facts_db = root / "facts" / "auto_launch_facts.sqlite"
            facts_db.write_text("data")
            (root / "search_cache").mkdir(parents=True)
            (root / "search_cache" / "cache.json").write_text("{}")
            dry = clean_dry_run()
            all_candidates = []
            for cat_files in dry["candidates"].values():
                if isinstance(cat_files, list):
                    for f in cat_files:
                        all_candidates.append(f if isinstance(f, str) else f.get("path", ""))
            assert not any("facts" in c for c in all_candidates)
            assert not any("auto_launch_facts.sqlite" in c for c in all_candidates)
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


def test_clean_dry_run_never_includes_runs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            _make_run(root / "runs", "2026-07-09", complete=True)
            dry = clean_dry_run()
            all_candidates = []
            for cat_files in dry["candidates"].values():
                if isinstance(cat_files, list):
                    for f in cat_files:
                        all_candidates.append(f if isinstance(f, str) else f.get("path", ""))
            assert not any("runs" in c for c in all_candidates)
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


def test_clean_dry_run_lists_search_cache():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            (root / "search_cache" / "2026-07-02").mkdir(parents=True)
            (root / "search_cache" / "2026-07-02" / "cache.raw.json").write_text("{}")
            dry = clean_dry_run()
            assert len(dry["candidates"]["search_cache"]) == 1
            assert "cache.raw.json" in dry["candidates"]["search_cache"][0]
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


def test_clean_dry_run_does_not_delete():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            (root / "search_cache" / "2026-07-02").mkdir(parents=True)
            cache_f = root / "search_cache" / "2026-07-02" / "c.raw.json"
            cache_f.write_text("{}")
            dry = clean_dry_run()
            assert cache_f.exists()
            assert dry["mode"] == "dry-run"
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


def test_clean_dry_run_older_than_filter():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            (root / "search_cache" / "2026-07-02").mkdir(parents=True)
            old_f = root / "search_cache" / "2026-07-02" / "old.raw.json"
            old_f.write_text("{}")
            # touch to 100 days ago
            old_mtime = datetime.now() - timedelta(days=100)
            os.utime(str(old_f), (old_mtime.timestamp(), old_mtime.timestamp()))
            dry = clean_dry_run(older_than_days=30)
            assert len(dry["candidates"]["search_cache"]) == 1
            # A fresh file should not appear
            (root / "search_cache" / "2026-07-02" / "fresh.raw.json").write_text("{}")
            dry2 = clean_dry_run(older_than_days=30)
            assert len(dry2["candidates"]["search_cache"]) == 1
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


def test_render_inspect_has_sections():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            (root / "runs").mkdir(parents=True)
            (root / "facts").mkdir()
            report = inspect()
            md = render_inspect(report)
            assert "Outputs Inspection Report" in md
            assert "Runs" in md
            assert "Facts" in md
            assert "Warnings" in md or "search" in md
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


def test_render_clean_dry_run_has_summary():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_manager.OUTPUTS_ROOT
        try:
            output_manager.OUTPUTS_ROOT = root
            dry = clean_dry_run()
            md = render_clean_dry_run(dry)
            assert "dry-run" in md
            assert "Never cleaned" in md
        finally:
            output_manager.OUTPUTS_ROOT = orig_root


if __name__ == "__main__":
    test_inspect_empty_outputs()
    test_inspect_complete_run()
    test_inspect_incomplete_run()
    test_inspect_facts_sqlite()
    test_inspect_duplicate_brief()
    test_inspect_warnings_on_missing_facts()
    test_clean_dry_run_never_includes_facts()
    test_clean_dry_run_never_includes_runs()
    test_clean_dry_run_lists_search_cache()
    test_clean_dry_run_does_not_delete()
    test_clean_dry_run_older_than_filter()
    test_render_inspect_has_sections()
    test_render_clean_dry_run_has_summary()
    print("\n✅ 所有 output_manager 测试通过")
