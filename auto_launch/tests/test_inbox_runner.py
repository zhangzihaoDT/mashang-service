"""inbox_runner 集成测试"""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.inbox_runner import run_file, run_text
from auto_launch.src.fact_store import FactStore

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "daily_run_sample.md"


def test_run_file_returns_summary():
    summary = run_file(str(FIXTURE), date="2026-07-09", write_facts=False)
    assert summary["total_raw_items"] >= 5
    assert "kept" in summary
    assert "discarded" in summary
    print(f"[PASS] test_run_file_returns_summary: {summary['total_raw_items']} raw, {summary['kept']} keep, {summary['discarded']} discard")


def test_run_file_keeps_known_brands():
    summary = run_file(str(FIXTURE), date="2026-07-09", write_facts=False)
    kept_brands = {i.get("brand") for i in summary["kept_items"]}
    assert "智己" in kept_brands
    assert "极氪" in kept_brands
    print(f"[PASS] test_run_file_keeps_known_brands: {kept_brands}")


def test_run_file_discards_opinion():
    summary = run_file(str(FIXTURE), date="2026-07-09", write_facts=False)
    discarded_titles = [di["item"].get("title", "") for di in summary["discarded_items"]]
    has_opinion = any("行业" in t or "展望" in t for t in discarded_titles)
    assert has_opinion
    print(f"[PASS] test_run_file_discards_opinion")


def test_run_file_writes_facts():
    db_path = tempfile.mktemp(suffix=".sqlite")
    # monkey-patch FactStore default path
    import auto_launch.src.fact_store as fs
    original = fs.DEFAULT_DB_PATH
    fs.DEFAULT_DB_PATH = Path(db_path)
    try:
        summary = run_file(str(FIXTURE), date="2026-07-09", write_facts=True)
        store = FactStore(db_path)
        stats = store.get_stats()
        assert stats["total_facts"] == summary["kept"]
        store.close()
    finally:
        fs.DEFAULT_DB_PATH = original
        if os.path.exists(db_path):
            os.unlink(db_path)
    print(f"[PASS] test_run_file_writes_facts: {stats['total_facts']} facts written")


def test_duplicate_run_does_not_duplicate_facts():
    db_path = tempfile.mktemp(suffix=".sqlite")
    import auto_launch.src.fact_store as fs
    original = fs.DEFAULT_DB_PATH
    fs.DEFAULT_DB_PATH = Path(db_path)
    try:
        # Run twice
        run_file(str(FIXTURE), date="2026-07-09", write_facts=True)
        run_file(str(FIXTURE), date="2026-07-09", write_facts=True)
        store = FactStore(db_path)
        stats = store.get_stats()
        # Should have same count as unique facts, not doubled
        single_summary = run_file(str(FIXTURE), date="2026-07-09", write_facts=False)
        assert stats["total_facts"] == single_summary["kept"]
        # Verify seen_count incremented for all
        all_facts = store.query(days=30)
        for f in all_facts:
            assert f["seen_count"] == 2
        store.close()
    finally:
        fs.DEFAULT_DB_PATH = original
        if os.path.exists(db_path):
            os.unlink(db_path)
    print(f"[PASS] test_duplicate_run_does_not_duplicate_facts")


if __name__ == "__main__":
    test_run_file_returns_summary()
    test_run_file_keeps_known_brands()
    test_run_file_discards_opinion()
    test_run_file_writes_facts()
    test_duplicate_run_does_not_duplicate_facts()
    print("\n✅ 所有测试通过")
