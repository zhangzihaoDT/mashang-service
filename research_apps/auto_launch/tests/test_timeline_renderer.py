"""timeline_renderer 测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.timeline_renderer import generate_timeline


def _fact(brand="智己", model="LS6", event_type="权益调整", title="智己 LS6 限时权益",
          source_tier="tier_1_official", source_name="immotors.com",
          event_date="2026-07-09", seen_count=3):
    return {
        "brand": brand, "model": model, "event_type": event_type,
        "title": title, "source_tier": source_tier, "source_name": source_name,
        "event_date": event_date, "seen_count": seen_count,
    }


def test_empty_facts():
    md = generate_timeline([])
    assert "无匹配数据" in md
    print("[PASS] test_empty_facts")


def test_facts_without_date():
    facts = [_fact(event_date="")]
    md = generate_timeline(facts)
    assert "无日期" in md
    print("[PASS] test_facts_without_date")


def test_month_grouping():
    facts = [
        _fact(event_date="2026-07-01", title="7月事件"),
        _fact(event_date="2026-06-15", title="6月事件"),
    ]
    md = generate_timeline(facts)
    assert "2026-07" in md
    assert "2026-06" in md
    print("[PASS] test_month_grouping")


def test_chronological_order():
    facts = [
        _fact(event_date="2026-07-09", title="较新"),
        _fact(event_date="2026-07-01", title="较早"),
    ]
    md = generate_timeline(facts)
    # 两者都应出现在输出中
    assert "较新" in md
    assert "较早" in md
    print("[PASS] test_chronological_order")


def test_brand_model_title():
    facts = [_fact(brand="智己", model="LS6")]
    md = generate_timeline(facts, brand="智己", model="LS6")
    assert "智己" in md
    assert "LS6" in md
    print("[PASS] test_brand_model_title")


def test_hot_badge_in_timeline():
    facts = [_fact(event_type="上市")]
    md = generate_timeline(facts)
    assert "HOT" in md
    print("[PASS] test_hot_badge_in_timeline")


if __name__ == "__main__":
    test_empty_facts()
    test_facts_without_date()
    test_month_grouping()
    test_chronological_order()
    test_brand_model_title()
    test_hot_badge_in_timeline()
    print("\n✅ 所有测试通过")
