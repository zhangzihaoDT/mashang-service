"""search_task_config_builder 测试"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_scripts.auto_launch.search_intent_compiler import compile_intent
from research_scripts.auto_launch.search_task_config_builder import build_task_config


def test_task_config_has_target_enrichment():
    """task_config 应包含 enriched target aliases"""
    intent = compile_intent("看看极氪最近 7 天都有什么动作", "2026-07-02")
    config = build_task_config(intent)
    assert config["target_count"] >= 1
    t = config["targets"][0]
    assert "aliases" in t
    assert len(t["aliases"]) > 0
    assert t["brand"] == "极氪"
    print("[PASS] test_task_config_has_target_enrichment")


def test_task_config_source_strategy():
    """task_config 的 source_strategy 应展开为 tier 级别"""
    intent = compile_intent("看看问界 M7 最近 7 天权益和价格有什么变化", "2026-07-02")
    config = build_task_config(intent)
    ss = config.get("source_strategy", {})
    assert len(ss) > 0, "source_strategy should have tier-level entries"
    print("[PASS] test_task_config_source_strategy")


def test_task_config_event_type_ids():
    """task_config 应包含 intent 中的 event_type_ids"""
    intent = compile_intent("看看理想 i6 最近有没有价格和权益变化", "2026-07-02")
    config = build_task_config(intent)
    eids = config.get("event_type_ids", [])
    assert "benefit_adjustment" in eids
    assert "official_price_change" in eids
    print("[PASS] test_task_config_event_type_ids")


def test_task_config_official_only():
    """只看官方 → source_strategy 的 tier_2 应 disabled"""
    intent = compile_intent("只看官方，看看蔚来 ES8 今天有没有新权益", "2026-07-02")
    config = build_task_config(intent)
    for tier_key, tier_cfg in config.get("source_strategy", {}).items():
        if "官方一手" in tier_key:
            assert tier_cfg["enabled"] == True
    print("[PASS] test_task_config_official_only")


if __name__ == "__main__":
    test_task_config_has_target_enrichment()
    test_task_config_source_strategy()
    test_task_config_event_type_ids()
    test_task_config_official_only()
    print("\n✅ 所有 task_config 测试通过")
