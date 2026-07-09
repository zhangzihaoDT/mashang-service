"""search_cache 测试"""
import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.search_cache import get_cache_key, is_cache_valid, load_cache, save_cache


def test_cache_key_consistent():
    k1 = get_cache_key("p", "极氪 权益", "2026-06-25", "2026-07-02", 10, "brand_watch", "zeekr")
    k2 = get_cache_key("p", "极氪 权益", "2026-06-25", "2026-07-02", 10, "brand_watch", "zeekr")
    assert k1 == k2
    print("[PASS] test_cache_key_consistent")


def test_cache_key_differs_by_date():
    k1 = get_cache_key("p", "极氪 权益", "2026-06-25", "2026-07-02", 10, "brand_watch", "zeekr")
    k2 = get_cache_key("p", "极氪 权益", "2026-06-01", "2026-07-02", 10, "brand_watch", "zeekr")
    assert k1 != k2
    print("[PASS] test_cache_key_differs_by_date")


def test_cache_key_differs_by_query():
    k1 = get_cache_key("p", "极氪 权益", "2026-06-25", "2026-07-02", 10, "brand_watch", "zeekr")
    k2 = get_cache_key("p", "极氪 交付", "2026-06-25", "2026-07-02", 10, "brand_watch", "zeekr")
    assert k1 != k2
    print("[PASS] test_cache_key_differs_by_query")


def test_save_and_load():
    with tempfile.TemporaryDirectory() as tmp:
        cp = Path(tmp) / "test_cache.json"
        data = {"status": "success", "results": [{"title": "test"}]}
        save_cache(data, cp)
        assert cp.exists()
        loaded = load_cache(cp, ttl_hours=24)
        assert loaded is not None
        assert loaded["status"] == "success"
    print("[PASS] test_save_and_load")


def test_cache_expired():
    with tempfile.TemporaryDirectory() as tmp:
        cp = Path(tmp) / "expired.json"
        save_cache({"status": "ok"}, cp)
        # ttl=0 forces expiry
        loaded = load_cache(cp, ttl_hours=0)
        assert loaded is None
    print("[PASS] test_cache_expired")


def test_cache_missing():
    with tempfile.TemporaryDirectory() as tmp:
        cp = Path(tmp) / "nonexistent.json"
        assert load_cache(cp) is None
    print("[PASS] test_cache_missing")
