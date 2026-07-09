"""output_manager 测试 — 验证 inspect / clean 在新路径结构下的行为"""
import sys, os, tempfile, json
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_launch.src import output_manager
from auto_launch.src.output_manager import (
    inspect, clean_dry_run, render_inspect, render_clean_dry_run,
    RUN_REQUIRED_FILES, NEVER_CLEAN,
)
from auto_launch.src import output_paths


# ── Helpers ───────────────────────────────────────────────────────

def _make_run(root: Path, date_str: str, run_mode: str, complete: bool = True):
    """Create a simulated run directory with required files under the new structure."""
    rd = root / "runs" / date_str.replace("-", "") / run_mode
    rd.mkdir(parents=True, exist_ok=True)

    # Create required files using the standard structure
    def _write(path: Path, content: str = "{}"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    if complete:
        _write(rd / "manifest.json", json.dumps({
            "command": "run-day", "monitor_date": date_str,
            "brand": "im", "brand_name": "智己",
            "live": False, "window_hours": 24,
        }))
        _write(rd / "facts" / "facts_audit.json")
        _write(rd / "reports" / "source_audit.json")
        _write(rd / "reports" / "source_audit.md", "# test")
        _write(rd / "reports" / "daily_brief.md", "# test")
        _write(rd / "summary.md", "# test")
    else:
        _write(rd / "manifest.json", json.dumps({
            "command": "run-day", "monitor_date": date_str,
        }))


# ── Tests ─────────────────────────────────────────────────────────

def test_inspect_empty_outputs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_paths._OUTPUT_ROOT
        output_paths._OUTPUT_ROOT = root
        output_manager.CLEAN_CANDIDATE_DIRS = ["search_cache"]
        try:
            (root / "runs").mkdir(parents=True)
            (root / "facts").mkdir()
            report = inspect()
            assert report["runs"]["count"] == 0
            assert report["facts"]["exists"] is False
        finally:
            output_paths._OUTPUT_ROOT = orig_root


def test_inspect_complete_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_paths._OUTPUT_ROOT
        output_paths._OUTPUT_ROOT = root
        try:
            _make_run(root, "2026-07-09", "brand_daily_zhiji", complete=True)
            report = inspect()
            assert report["runs"]["count"] == 1
            assert report["runs"]["list"][0]["complete"] is True
            assert report["runs"]["list"][0]["date"] == "2026-07-09"
        finally:
            output_paths._OUTPUT_ROOT = orig_root


def test_inspect_incomplete_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_paths._OUTPUT_ROOT
        output_paths._OUTPUT_ROOT = root
        try:
            _make_run(root, "2026-07-09", "brand_daily_zhiji", complete=False)
            report = inspect()
            assert report["runs"]["count"] == 1
            assert report["runs"]["list"][0]["complete"] is False
            assert "facts/facts_audit.json" in report["runs"]["list"][0]["missing"]
        finally:
            output_paths._OUTPUT_ROOT = orig_root


def test_inspect_facts_sqlite():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_paths._OUTPUT_ROOT
        output_paths._OUTPUT_ROOT = root
        try:
            (root / "facts").mkdir(parents=True)
            facts_db = root / "facts" / "auto_launch_facts.sqlite"
            facts_db.write_text("SQLite format 3", encoding="utf-8")
            report = inspect()
            assert report["facts"]["exists"] is True
            assert report["facts"]["size_bytes"] > 0
        finally:
            output_paths._OUTPUT_ROOT = orig_root


def test_inspect_warnings_on_missing_facts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_paths._OUTPUT_ROOT
        output_paths._OUTPUT_ROOT = root
        try:
            (root / "runs").mkdir(parents=True)
            (root / "facts").mkdir()
            report = inspect()
            assert any("facts" in w for w in report["warnings"])
        finally:
            output_paths._OUTPUT_ROOT = orig_root


def test_clean_dry_run_never_includes_facts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_paths._OUTPUT_ROOT
        output_paths._OUTPUT_ROOT = root
        try:
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
            output_paths._OUTPUT_ROOT = orig_root


def test_clean_dry_run_never_includes_runs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_paths._OUTPUT_ROOT
        output_paths._OUTPUT_ROOT = root
        try:
            _make_run(root, "2026-07-09", "brand_daily_zhiji", complete=True)
            dry = clean_dry_run()
            all_candidates = []
            for cat_files in dry["candidates"].values():
                if isinstance(cat_files, list):
                    for f in cat_files:
                        all_candidates.append(f if isinstance(f, str) else f.get("path", ""))
            assert not any("runs" in c for c in all_candidates)
        finally:
            output_paths._OUTPUT_ROOT = orig_root


def test_clean_dry_run_lists_search_cache():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_paths._OUTPUT_ROOT
        output_paths._OUTPUT_ROOT = root
        try:
            (root / "search_cache").mkdir(parents=True)
            (root / "search_cache" / "cache.raw.json").write_text("{}")
            dry = clean_dry_run()
            assert len(dry["candidates"]["search_cache"]) == 1
            assert "cache.raw.json" in dry["candidates"]["search_cache"][0]
        finally:
            output_paths._OUTPUT_ROOT = orig_root


def test_clean_dry_run_does_not_delete():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_paths._OUTPUT_ROOT
        output_paths._OUTPUT_ROOT = root
        try:
            (root / "search_cache").mkdir(parents=True)
            cache_f = root / "search_cache" / "c.raw.json"
            cache_f.write_text("{}")
            dry = clean_dry_run()
            assert cache_f.exists()
            assert dry["mode"] == "dry-run"
        finally:
            output_paths._OUTPUT_ROOT = orig_root


def test_clean_dry_run_older_than_filter():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_paths._OUTPUT_ROOT
        output_paths._OUTPUT_ROOT = root
        try:
            (root / "search_cache").mkdir(parents=True)
            old_f = root / "search_cache" / "old.raw.json"
            old_f.write_text("{}")
            old_mtime = datetime.now() - timedelta(days=100)
            os.utime(str(old_f), (old_mtime.timestamp(), old_mtime.timestamp()))
            dry = clean_dry_run(older_than_days=30)
            assert len(dry["candidates"]["search_cache"]) == 1
            (root / "search_cache" / "fresh.raw.json").write_text("{}")
            dry2 = clean_dry_run(older_than_days=30)
            assert len(dry2["candidates"]["search_cache"]) == 1
        finally:
            output_paths._OUTPUT_ROOT = orig_root


def test_render_inspect_has_sections():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_paths._OUTPUT_ROOT
        output_paths._OUTPUT_ROOT = root
        try:
            (root / "runs").mkdir(parents=True)
            (root / "facts").mkdir()
            report = inspect()
            md = render_inspect(report)
            assert "Outputs Inspection Report" in md
            assert "Runs" in md
            assert "Facts" in md
        finally:
            output_paths._OUTPUT_ROOT = orig_root


def test_render_clean_dry_run_has_summary():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        orig_root = output_paths._OUTPUT_ROOT
        output_paths._OUTPUT_ROOT = root
        try:
            dry = clean_dry_run()
            md = render_clean_dry_run(dry)
            assert "dry-run" in md
            assert "Never cleaned" in md
        finally:
            output_paths._OUTPUT_ROOT = orig_root


def test_top_level_whitelist():
    """顶层目录白名单只允许 runs/ facts/ search_cache/ demo/ _legacy/。"""
    ALLOWED = {"runs", "facts", "search_cache", "demo", "_legacy"}
    root = output_paths.output_root()
    for d in root.iterdir():
        if d.is_dir() and not d.name.startswith("."):
            assert d.name in ALLOWED, f"顶层目录不在白名单中: {d.name}"


def test_no_legacy_top_level():
    """确保没有重建 legacy 顶层目录。"""
    root = output_paths.output_root()
    for forbidden in ["briefs", "owned_brand_daily", "search", "_migration"]:
        assert not (root / forbidden).exists(), f"Legacy 目录不应存在: {forbidden}"
