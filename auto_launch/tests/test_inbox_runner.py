"""inbox_runner 集成测试 — Planner 日报"""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.inbox_runner import run_file, run_text
from auto_launch.src.fact_store import FactStore

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "planner_daily_report.md"


def test_run_file_returns_summary():
    summary = run_file(str(FIXTURE), date="2026-07-27", write_facts=False)
    assert summary["source_type"] == "planner_daily_report"
    assert summary["total_items"] == 27
    assert summary["confirmed_facts"] == 1
    assert summary["review_signals"] == 2
    assert summary["brand_statuses"] == 22
    assert summary["brand_volumes"] == 2
    print(f"[PASS] test_run_file_returns_summary: {summary['total_items']} items")


def test_run_file_writes_facts():
    db_path = tempfile.mktemp(suffix=".sqlite")
    import auto_launch.src.fact_store as fs
    original = fs.DEFAULT_DB_PATH
    fs.DEFAULT_DB_PATH = Path(db_path)
    try:
        summary = run_file(str(FIXTURE), date="2026-07-27", write_facts=True)
        store = FactStore(db_path)
        stats = store.get_stats()
        assert stats["total_facts"] == 1
        assert stats["signals"] == 2
        assert stats["brand_statuses"] == 22
        assert stats["brand_volumes"] == 2
        store.close()
    finally:
        fs.DEFAULT_DB_PATH = original
        if os.path.exists(db_path):
            os.unlink(db_path)
    print(f"[PASS] test_run_file_writes_facts: 1 fact + 2 signals + 22 status + 2 volume")


def test_duplicate_run_does_not_duplicate():
    db_path = tempfile.mktemp(suffix=".sqlite")
    import auto_launch.src.fact_store as fs
    original = fs.DEFAULT_DB_PATH
    fs.DEFAULT_DB_PATH = Path(db_path)
    try:
        run_file(str(FIXTURE), date="2026-07-27", write_facts=True)
        run_file(str(FIXTURE), date="2026-07-27", write_facts=True)
        store = FactStore(db_path)
        stats = store.get_stats()
        assert stats["total_facts"] == 1
        assert stats["signals"] == 2
        assert stats["brand_statuses"] == 22
        assert stats["brand_volumes"] == 2
        all_facts = store.query(days=30, exclude_test=False)
        for f in all_facts:
            assert f["seen_count"] == 2
        store.close()
    finally:
        fs.DEFAULT_DB_PATH = original
        if os.path.exists(db_path):
            os.unlink(db_path)
    print(f"[PASS] test_duplicate_run_does_not_duplicate")


def test_planner_p0_acceptance():
    summary = run_file(str(FIXTURE), date="2026-07-27", write_facts=False)
    assert summary["confirmed_facts"] == 1
    assert summary["review_signals"] == 2
    assert summary["brand_statuses"] == 22
    assert summary["brand_volumes"] == 2
    assert summary["total_items"] == 27
    print(f"[PASS] P0 验收: 1+2+22+2={summary['total_items']}")


if __name__ == "__main__":
    test_run_file_returns_summary()
    test_run_file_writes_facts()
    test_duplicate_run_does_not_duplicate()
    test_planner_p0_acceptance()
    print("\n✅ 所有测试通过")
