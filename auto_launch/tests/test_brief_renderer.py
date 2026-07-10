"""brief_renderer 测试（新：dedup + cluster + 过滤）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.brief_renderer import generate_brief, clean_facts


def _fact(brand="智己", model="LS6", event_type="权益调整", title="智己 LS6 限时权益",
          source_tier="tier_1_official", source_name="immotors.com",
          source_url="https://immotors.com/news/1", event_date="2026-07-09",
          last_seen="2026-07-09T12:00:00", seen_count=3,
          is_test=0, quality_status="valid"):
    return {
        "brand": brand, "model": model, "event_type": event_type,
        "title": title, "source_tier": source_tier, "source_name": source_name,
        "source_url": source_url, "event_date": event_date,
        "last_seen": last_seen, "seen_count": seen_count,
        "is_test": is_test, "quality_status": quality_status,
    }


def test_empty_facts_returns_empty_brief():
    md = generate_brief([])
    assert "无匹配有效事实" in md or "事实库为空" in md
    print("[PASS] test_empty_facts_returns_empty_brief")


def test_generate_includes_new_sections():
    facts = [_fact(), _fact(brand="极氪", model="7X", event_type="开启交付", title="极氪 7X 开启交付")]
    md = generate_brief(facts)
    for section in ["今日重点", "品牌动作速览", "事件类型分布", "信源质量", "今日观察"]:
        assert section in md, f"Missing section: {section}"
    print(f"[PASS] test_generate_includes_new_sections")


def test_launch_before_general():
    """上市事件排名高于一般传播事件"""
    facts = [
        _fact(event_type="上市", title="新车上市"),
        _fact(event_type="合作", title="品牌合作"),
    ]
    md = generate_brief(facts)
    # 上市事件应出现在品牌动作速览的第一条
    assert "上市" in md.split("品牌动作速览")[1].split("合作")[0]
    print("[PASS] test_launch_before_general")


def test_brand_filter_in_output():
    """简报应包含按品牌聚合的板块"""
    facts = [_fact(), _fact(brand="极氪")]
    md = generate_brief(facts)
    assert "智己" in md
    assert "极氪" in md
    print("[PASS] test_brand_filter_in_output")


def test_dedup_duplicate_events():
    """同一事实写入多次，简报只展示 1 条，显示 source_count"""
    facts = [
        _fact(title="智己 LS6 限时权益调整"),
        _fact(title="智己 LS6 限时权益调整"),
        _fact(title="智己 LS6 限时权益调整"),
    ]
    md = generate_brief(facts)
    # 3 个来源应合并为一条
    assert "3 个来源" in md or "3）" in md
    print("[PASS] test_dedup_duplicate_events")


def test_filter_test_data():
    """is_test=1 的数据不应出现在简报中"""
    facts = [
        _fact(brand="A", title="Test", is_test=1, quality_status="test"),
        _fact(),
    ]
    cleaned = clean_facts(facts)
    assert len(cleaned) == 1
    md = generate_brief(facts)
    assert "品牌 A" not in md and "[A]" not in md
    print("[PASS] test_filter_test_data")


def test_filter_brand_abcd():
    """品牌 A/B/C/D 不应出现在简报中"""
    facts = [
        _fact(brand="A", model="X", event_type="上市", title="Test", is_test=1, quality_status="test"),
        _fact(brand="B", model="Y", event_type="预售", title="Test", is_test=1, quality_status="test"),
        _fact(),
    ]
    md = generate_brief(facts)
    assert "品牌 A" not in md and "[A]" not in md
    assert "品牌 B" not in md and "[B]" not in md
    assert "智己" in md
    print("[PASS] test_filter_brand_abcd")


def test_hot_badge_for_high_priority():
    """上市/预售/价格/权益/交付 事件获得 HOT badge"""
    facts = [
        _fact(event_type="上市", title="新车"),
        _fact(event_type="合作", title="品牌合作"),
    ]
    md = generate_brief(facts)
    assert "HOT" in md
    print("[PASS] test_hot_badge_for_high_priority")


def test_source_tier_section():
    """简报包含信源质量分布"""
    facts = [_fact(), _fact(event_type="交付", title="交付")]
    md = generate_brief(facts)
    assert "官方" in md
    print("[PASS] test_source_tier_section")


def test_empty_state_with_filtered_count():
    """全部被过滤时，空状态报告说明已过滤条数"""
    facts = [
        _fact(brand="A", title="Test", is_test=1, quality_status="test"),
        _fact(brand="B", title="Test", is_test=1, quality_status="test"),
    ]
    md = generate_brief(facts)
    assert "无匹配有效事实" in md
    assert "已过滤" in md
    print("[PASS] test_empty_state_with_filtered_count")


def test_observation_mentions_filtered():
    """观察模块说明已过滤的 test 数据量"""
    facts = [
        _fact(),  # 1 valid
        _fact(brand="A", title="Test", is_test=1, quality_status="test"),
    ]
    md = generate_brief(facts)
    assert "已自动过滤" in md
    print("[PASS] test_observation_mentions_filtered")


if __name__ == "__main__":
    test_empty_facts_returns_empty_brief()
    test_generate_includes_new_sections()
    test_launch_before_general()
    test_brand_filter_in_output()
    test_dedup_duplicate_events()
    test_filter_test_data()
    test_filter_brand_abcd()
    test_hot_badge_for_high_priority()
    test_source_tier_section()
    test_empty_state_with_filtered_count()
    test_observation_mentions_filtered()
    print("\n✅ 所有测试通过")
