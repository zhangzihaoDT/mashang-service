"""search_intent_compiler 测试"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.search_intent_compiler import (
    compile_intent, infer_mode, identify_targets, infer_time_window,
    infer_event_scope, infer_source_strategy
)

MONITOR_DATE = "2026-07-02"


def test_brand_watch_open_scan():
    """看看极氪最近 7 天都有什么动作 → brand_watch"""
    intent = compile_intent("看看极氪最近 7 天都有什么动作", MONITOR_DATE)
    assert intent["mode"] == "brand_watch", f"Expected brand_watch, got {intent['mode']}"
    assert len(intent["targets"]) > 0
    assert intent["targets"][0]["brand"] == "极氪"
    # target_id 应为英文 slug
    assert intent["targets"][0]["target_id"] == "zeekr", f"Expected slug 'zeekr', got {intent['targets'][0]['target_id']}"
    assert intent["time_window"]["days"] == 7
    assert intent["time_window"]["start_date"] == "2026-06-25"
    assert intent["time_window"]["end_date"] == "2026-07-02"
    assert intent["event_scope"]["scope_type"] == "all_relevant_actions"
    assert len(intent["event_scope"]["event_type_ids"]) >= 10
    print("[PASS] test_brand_watch_open_scan")


def test_model_watch_specific_events():
    """看看问界 M7 最近 7 天权益和价格有什么变化 → model_watch"""
    intent = compile_intent("看看问界 M7 最近 7 天权益和价格有什么变化", MONITOR_DATE)
    assert intent["mode"] == "model_watch"
    assert len(intent["targets"]) > 0
    assert intent["targets"][0]["target_id"] == "aito_m7", f"Expected slug 'aito_m7', got {intent['targets'][0]['target_id']}"
    eids = intent["event_scope"]["event_type_ids"]
    assert "benefit_adjustment" in eids
    assert "official_price_change" in eids
    print("[PASS] test_model_watch_specific_events")


def test_official_only_source():
    """只看官方，看看蔚来 ES8 今天有没有新权益 → source_strategy 只看官方"""
    intent = compile_intent("只看官方，看看蔚来 ES8 今天有没有新权益", MONITOR_DATE)
    ss = intent["source_strategy"]
    assert ss["official_first"] == True
    assert ss["include_authoritative_media"] == False
    assert ss["include_social_signals"] == False
    eids = intent["event_scope"]["event_type_ids"]
    assert "benefit_adjustment" in eids, f"Expected benefit_adjustment in {eids}"
    print("[PASS] test_official_only_source")


def test_sales_rumor_source():
    """看看理想最近销售端有没有风声 → brand_watch, 放开 social/unverified"""
    intent = compile_intent("看看理想最近销售端有没有风声", MONITOR_DATE)
    assert intent["mode"] == "brand_watch"
    ss = intent["source_strategy"]
    assert ss["allow_unverified_as_discovery_only"] == True
    eids = intent["event_scope"]["event_type_ids"]
    assert "rumor_or_leak" in eids
    print("[PASS] test_sales_rumor_source")


def test_brand_watch_marketing():
    """看看鸿蒙智行最近有什么营销动作 → brand_watch"""
    intent = compile_intent("看看鸿蒙智行最近有什么营销动作", MONITOR_DATE)
    assert intent["mode"] == "brand_watch"
    assert len(intent["targets"]) > 0
    assert intent["targets"][0]["target_id"] == "hima", f"Expected slug 'hima', got {intent['targets'][0]['target_id']}"
    print("[PASS] test_brand_watch_marketing")


def test_model_watch_price():
    """看看理想 i6 最近有没有价格和权益变化 → model_watch"""
    intent = compile_intent("看看理想 i6 最近有没有价格和权益变化", MONITOR_DATE)
    assert intent["mode"] == "model_watch"
    eids = intent["event_scope"]["event_type_ids"]
    assert "benefit_adjustment" in eids
    assert "official_price_change" in eids
    print("[PASS] test_model_watch_price")


def test_infer_mode():
    assert infer_mode("看看极氪最近有什么动作", False) == "brand_watch"
    assert infer_mode("看看极氪最近有什么营销动作", False) == "brand_watch"
    assert infer_mode("看看问界 M7 权益价格", True) == "model_watch"
    print("[PASS] test_infer_mode")


def test_infer_time_window():
    tw = infer_time_window("看看极氪最近 7 天都有什么动作", "2026-07-02")
    assert tw["days"] == 7
    tw = infer_time_window("看看极氪今天有没有动作", "2026-07-02")
    assert tw["days"] == 0
    tw = infer_time_window("看看极氪昨天有没有动作", "2026-07-02")
    assert tw["days"] == 1
    print("[PASS] test_infer_time_window")


if __name__ == "__main__":
    test_brand_watch_open_scan()
    test_model_watch_specific_events()
    test_official_only_source()
    test_sales_rumor_source()
    test_brand_watch_marketing()
    test_model_watch_price()
    test_infer_mode()
    test_infer_time_window()
    print("\n✅ 所有测试通过")
