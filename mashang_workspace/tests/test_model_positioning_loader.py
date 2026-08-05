"""Smoke test: model_positioning.yaml 唯一事实源 + loader 可读性。"""

import pytest

from shared.loaders.model_positioning_loader import (
    get_archetype_definition,
    get_competitor_models,
    get_competitors,
    get_competitors_by_tier,
    get_model_archetype,
    get_model_positioning,
    get_models_by_archetype,
    get_models_by_priority,
    get_models_by_segment,
    get_models_by_tag,
    list_models,
    list_segments,
    load_archetype_definitions,
    load_model_positioning,
    load_product_archetypes,
)

ARCHETYPES = {
    "intelligent_sport_sedan",
    "intelligent_sport_suv",
    "family_large_5seat_suv",
    "luxury_flagship_6seat_suv",
}
OWN_MODELS = ("LS6", "LS8", "LS9", "L6")


def test_models_present():
    models = list_models()
    for m in OWN_MODELS:
        assert m in models


def test_segment_and_priority():
    assert get_model_positioning("LS9")["segment"] == "fullsize_suv"
    assert get_model_positioning("LS9")["priority"] == "flagship"
    assert get_model_positioning("L6")["position"] == "运动科技轿车"
    assert get_model_positioning("LS8")["seats"] == "五座（可选六座）"


def test_grouping():
    assert get_models_by_segment("midsize_suv") == ["LS6"]
    assert get_models_by_priority("volume") == ["LS6"]
    assert list_segments() == ["fullsize_suv", "large_suv", "midsize_sedan", "midsize_suv"]


def test_tag_lookup():
    assert "LS6" in get_models_by_tag("运动")
    assert "LS9" in get_models_by_tag("商务")
    assert "LS8" in get_models_by_tag("家庭")


def test_full_load_has_required_fields():
    data = load_model_positioning()
    for info in data.values():
        for field in ("position", "body_type", "seats", "segment", "priority", "archetype"):
            assert field in info, f"missing {field}"


def test_archetype_assignment():
    assert get_model_archetype("LS6") == "intelligent_sport_suv"
    assert get_model_archetype("LS8") == "family_large_5seat_suv"
    assert get_model_archetype("LS9") == "luxury_flagship_6seat_suv"
    assert get_model_archetype("L6") == "intelligent_sport_sedan"
    assert get_model_archetype("Tesla Model Y") == "intelligent_sport_suv"
    assert get_model_archetype("AITO M9") == "luxury_flagship_6seat_suv"


def test_archetype_grouping_and_competitors():
    assert set(get_models_by_archetype("luxury_flagship_6seat_suv")) == {
        "LS9", "Li Auto L9", "AITO M9", "XPeng GX", "Xiaomi Pengcheng N90",
        "Denza N9", "NIO ES8", "Lynk & Co 900",
    }
    assert set(get_competitor_models("LS9")) == {
        "Li Auto L9", "AITO M9", "XPeng GX", "Xiaomi Pengcheng N90",
        "Denza N9", "NIO ES8", "Lynk & Co 900",
    }


def test_archetype_definitions():
    defs = load_archetype_definitions()
    assert set(defs.keys()) == ARCHETYPES
    assert get_archetype_definition("luxury_flagship_6seat_suv")["label"] == "豪华旗舰大六座 SUV"
    assert "空间" in get_archetype_definition("family_large_5seat_suv")["needs"]
    assert "智能" in get_archetype_definition("intelligent_sport_suv")["needs"]


def test_suv_competitors():
    assert set(get_competitors_by_tier("LS6")["tier1"]) == {
        "Tesla Model Y", "XPeng G6", "Zeekr 7X", "Onvo L60"
    }
    assert set(get_competitors_by_tier("LS6")["tier2"]) == {"Xiaomi YU7", "AITO M5", "NIO ES6"}
    assert set(get_competitors_by_tier("LS8")["tier1"]) == {
        "XPeng G9L", "Xiaomi Pengcheng N70", "Li Auto L7", "AITO M8"
    }
    assert set(get_competitors_by_tier("LS8")["tier2"]) == {"Li Auto L8", "Denza N8L", "Wey Lanshan"}
    assert set(get_competitors_by_tier("LS9")["tier1"]) == {
        "Li Auto L9", "AITO M9", "XPeng GX", "Xiaomi Pengcheng N90"
    }
    assert set(get_competitors_by_tier("LS9")["tier2"]) == {"Denza N9", "NIO ES8", "Lynk & Co 900"}


def test_l6_tiered_competitors():
    by_tier = get_competitors_by_tier("L6")
    assert set(by_tier["tier1"]) == {"Xiaomi SU7", "Tesla Model 3", "Zeekr 007", "NIO ET5"}
    assert set(by_tier["tier2"]) == {"XPeng P7+", "Smart #6"}
    assert get_competitors("L6", tier="tier1") == by_tier["tier1"]
    assert len(get_competitors("L6")) == 6
    assert "L6" not in get_competitor_models("L6")


def test_archetype_registered_competitors():
    assert set(get_models_by_archetype("family_large_5seat_suv")) == {
        "LS8", "XPeng G9L", "Xiaomi Pengcheng N70", "Li Auto L7",
        "AITO M8", "Li Auto L8", "Denza N8L", "Wey Lanshan",
    }
    assert "AITO M9" in get_models_by_archetype("luxury_flagship_6seat_suv")
    assert "Tesla Model Y" in get_models_by_archetype("intelligent_sport_suv")
    assert set(get_competitor_models("LS8")) == {
        "XPeng G9L", "Xiaomi Pengcheng N70", "Li Auto L7",
        "AITO M8", "Li Auto L8", "Denza N8L", "Wey Lanshan",
    }


def test_no_duplicate_competitor_in_multiple_tiers():
    """同一竞品不得同时出现在同一车型的 tier1 与 tier2。"""
    for m in OWN_MODELS:
        by_tier = get_competitors_by_tier(m)
        overlap = set(by_tier.get("tier1", [])) & set(by_tier.get("tier2", []))
        assert not overlap, f"{m}: 竞品重复出现在多层级: {overlap}"


def test_competitors_share_or_neighbor_archetype():
    """tier1 竞品必须与车型同产品赛道；全部竞品必须已登记赛道（不允许悬空）。"""
    mappings = load_product_archetypes()
    for m in OWN_MODELS:
        own_archetype = get_model_archetype(m)
        by_tier = get_competitors_by_tier(m)
        for comp in by_tier.get("tier1", []):
            assert get_model_archetype(comp) == own_archetype, (
                f"{m} tier1 竞品 {comp} 赛道不一致: {get_model_archetype(comp)} != {own_archetype}"
            )
        for comp in by_tier.get("tier1", []) + by_tier.get("tier2", []):
            assert comp in mappings, f"{m} 竞品 {comp} 未登记到 product_archetype 映射"
