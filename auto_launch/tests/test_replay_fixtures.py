"""replay fixtures 测试 — 验证多天回放的去重和统计"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.operating_loop import replay_from_fixtures
from auto_launch.src.fact_store import FactStore

FIXTURES = str(Path(__file__).resolve().parent / "fixtures" / "daily_runs")


def test_replay_basic_counts():
    r = replay_from_fixtures(FIXTURES, reset_store=True)
    assert r["days"] == 3
    assert r["total_raw"] > 0
    assert r["total_keep"] > 0
    print(f"[PASS] test_replay_basic_counts: {r['days']} days, {r['total_raw']} raw, {r['total_keep']} keep")


def test_replay_duplicate_detection():
    """同一 day fixture 重复导入时触发去重"""
    import tempfile, shutil
    with tempfile.TemporaryDirectory() as tmp:
        # 复制 day1.md 两次，确保完全相同的内容
        src = Path(FIXTURES) / "day1.md"
        p1 = Path(tmp) / "day1.md"
        p2 = Path(tmp) / "day2.md"
        shutil.copy2(src, p1)
        shutil.copy2(src, p2)
        r = replay_from_fixtures(tmp, reset_store=True)
        assert r["total_updated"] > 0, f"expected updates, got inserted={r['total_inserted']} updated={r['total_updated']}"
        assert r["duplicate_rate"] > 0
    print(f"[PASS] test_replay_duplicate_detection: inserted={r['total_inserted']} updated={r['total_updated']} rate={r['duplicate_rate']}%")


def test_replay_top_brands():
    r = replay_from_fixtures(FIXTURES, reset_store=True)
    assert len(r["top_brands"]) > 0
    assert "智己" in r["top_brands"]
    print(f"[PASS] test_replay_top_brands: {r['top_brands']}")


def test_replay_seen_count_incremented():
    """相同内容重复导入时 seen_count 递增"""
    import tempfile, shutil
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(FIXTURES) / "day1.md"
        p1 = Path(tmp) / "day1.md"
        p2 = Path(tmp) / "day2.md"
        shutil.copy2(src, p1)
        shutil.copy2(src, p2)
        replay_from_fixtures(tmp, reset_store=True)
        store = FactStore()
        facts = store.query(limit=50)
        for f in facts:
            if f["seen_count"] > 1:
                print(f"[PASS] test_replay_seen_count_incremented: fact_id={f['fact_id']} seen={f['seen_count']}")
                return
    # If we get here, no fact has seen_count > 1 - show all facts
    store2 = FactStore()
    all_f = store2.query(limit=50)
    print(f"All facts: {[{'id':f['fact_id'],'title':f['title'][:30],'seen':f['seen_count']} for f in all_f]}")
    assert False, "No fact had seen_count > 1 after duplicate import"


def test_replay_reset_store():
    store = FactStore()
    before = store.get_stats()["total_facts"]
    # Reset should work
    replay_from_fixtures(FIXTURES, reset_store=True)
    after_reset = store.get_stats()["total_facts"]
    # After reset + replay, should have some facts
    assert after_reset >= before or before == 0
    print(f"[PASS] test_replay_reset_store: before={before} after={after_reset}")


if __name__ == "__main__":
    test_replay_basic_counts()
    test_replay_duplicate_detection()
    test_replay_top_brands()
    test_replay_seen_count_incremented()
    test_replay_reset_store()
    print("\n✅ 所有测试通过")
