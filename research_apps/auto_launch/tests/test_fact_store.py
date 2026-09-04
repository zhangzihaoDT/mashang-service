"""fact_store 测试"""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.fact_store import FactStore


def _store():
    tmp = tempfile.mktemp(suffix=".sqlite")
    return FactStore(tmp), tmp


def test_insert_new_fact():
    store, path = _store()
    r = store.insert({"brand": "智己", "model": "LS6", "event_type": "权益调整",
                       "event_date": "2026-07-09", "title": "智己 LS6 限时权益"})
    assert r["action"] == "inserted"
    assert r["seen_count"] == 1
    store.close()
    os.unlink(path)
    print(f"[PASS] test_insert_new_fact")


def test_duplicate_fact_updates_seen_count():
    store, path = _store()
    item = {"brand": "智己", "model": "LS6", "event_type": "权益调整",
            "event_date": "2026-07-09", "title": "智己 LS6 限时权益"}
    r1 = store.insert(item)
    assert r1["action"] == "inserted"
    r2 = store.insert(item)
    assert r2["action"] == "updated"
    assert r2["seen_count"] == 2
    store.close()
    os.unlink(path)
    print(f"[PASS] test_duplicate_fact_updates_seen_count")


def test_query_by_brand():
    store, path = _store()
    store.insert({"brand": "智己", "model": "LS6", "title": "权益调整"})
    store.insert({"brand": "极氪", "model": "7X", "title": "开启交付"})
    results = store.query(brand="智己")
    assert len(results) == 1
    assert results[0]["brand"] == "智己"
    store.close()
    os.unlink(path)
    print(f"[PASS] test_query_by_brand")


def test_query_by_event_type():
    store, path = _store()
    store.insert({"brand": "智己", "event_type": "权益调整", "title": "智己权益"})
    store.insert({"brand": "极氪", "event_type": "交付", "title": "极氪交付"})
    results = store.query(event_type="权益调整")
    assert len(results) == 1
    store.close()
    os.unlink(path)
    print(f"[PASS] test_query_by_event_type")


def test_get_stats():
    store, path = _store()
    store.insert({"brand": "智己", "title": "智己事件1"})
    store.insert({"brand": "智己", "title": "智己事件2"})
    store.insert({"brand": "极氪", "title": "极氪事件1"})
    stats = store.get_stats()
    assert stats["total_facts"] == 3
    assert stats["by_brand"]["智己"] == 2
    assert stats["by_brand"]["极氪"] == 1
    store.close()
    os.unlink(path)
    print(f"[PASS] test_get_stats")


def test_fingerprint_differentiates():
    """不同标题即使其他字段相同也不视为重复"""
    store, path = _store()
    r1 = store.insert({"brand": "智己", "model": "LS6", "event_type": "权益调整",
                        "event_date": "2026-07-09", "title": "智己 LS6 权益调整 A"})
    r2 = store.insert({"brand": "智己", "model": "LS6", "event_type": "权益调整",
                        "event_date": "2026-07-09", "title": "智己 LS6 权益调整 B"})
    assert r1["action"] == "inserted"
    assert r2["action"] == "inserted"
    assert r2["fact_id"] != r1["fact_id"]
    store.close()
    os.unlink(path)
    print(f"[PASS] test_fingerprint_differentiates")


if __name__ == "__main__":
    test_insert_new_fact()
    test_duplicate_fact_updates_seen_count()
    test_query_by_brand()
    test_query_by_event_type()
    test_get_stats()
    test_fingerprint_differentiates()
    print("\n✅ 所有测试通过")
