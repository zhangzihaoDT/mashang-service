"""brief_renderer 测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.brief_renderer import generate_brief, brief_rank


def _fact(brand="智己", model="LS6", event_type="权益调整", title="智己 LS6 限时权益",
          source_tier="tier_1_official", source_name="immotors.com",
          source_url="https://immotors.com/news/1", event_date="2026-07-09",
          last_seen="2026-07-09T12:00:00", seen_count=3):
    return {
        "brand": brand, "model": model, "event_type": event_type,
        "title": title, "source_tier": source_tier, "source_name": source_name,
        "source_url": source_url, "event_date": event_date,
        "last_seen": last_seen, "seen_count": seen_count,
    }


def test_empty_facts_returns_friendly():
    md = generate_brief([])
    assert "无匹配数据" in md or "事实库为空" in md
    print("[PASS] test_empty_facts_returns_friendly")


def test_generate_includes_sections():
    facts = [_fact(), _fact(brand="极氪", model="7X", event_type="开启交付", title="极氪 7X 开启交付")]
    md = generate_brief(facts)
    for section in ["今日最值得关注", "按品牌", "按事件类型", "信源质量", "今日观察"]:
        assert section in md, f"Missing section: {section}"
    print(f"[PASS] test_generate_includes_sections")


def test_brief_rank_launch_before_general():
    """上市事件排名高于一般传播事件"""
    launch = _fact(event_type="上市", title="新车上市")
    general = _fact(event_type="合作", title="品牌合作")
    assert brief_rank(launch) > brief_rank(general), "上市应排在合作前"
    print("[PASS] test_brief_rank_launch_before_general")


def test_brief_rank_official_before_unverified():
    """官方源排名高于未验证"""
    official = _fact(source_tier="tier_1_official")
    unverified = _fact(source_tier="tier_5_unverified")
    assert brief_rank(official) > brief_rank(unverified)
    print("[PASS] test_brief_rank_official_before_unverified")


def test_brand_filter_in_output():
    """简报应包含按品牌聚合的板块"""
    facts = [_fact(), _fact(brand="极氪")]
    md = generate_brief(facts)
    assert "智己" in md
    assert "极氪" in md
    print("[PASS] test_brand_filter_in_output")


def test_event_type_grouping():
    """多事件类型能按分类聚合"""
    facts = [
        _fact(event_type="上市", title="新车上市"),
        _fact(event_type="权益调整", title="权益调整"),
        _fact(event_type="OTA", title="OTA 推送"),
    ]
    md = generate_brief(facts)
    assert "上市/预售" in md
    assert "价格/权益" in md or "产品/技术" in md
    print("[PASS] test_event_type_grouping")


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
    assert "官方" in md or "tier" in md
    print("[PASS] test_source_tier_section")


def test_brief_rank_missing_url_penalty():
    """缺失 source_url 降低排名"""
    with_url = _fact(source_url="https://example.com")
    without_url = _fact(source_url="")
    assert brief_rank(with_url) > brief_rank(without_url)
    print("[PASS] test_brief_rank_missing_url_penalty")


def test_brief_rank_seen_count():
    """seen_count 更高排名更高"""
    high_seen = _fact(seen_count=10)
    low_seen = _fact(seen_count=1)
    assert brief_rank(high_seen) > brief_rank(low_seen)
    print("[PASS] test_brief_rank_seen_count")


if __name__ == "__main__":
    test_empty_facts_returns_friendly()
    test_generate_includes_sections()
    test_brief_rank_launch_before_general()
    test_brief_rank_official_before_unverified()
    test_brand_filter_in_output()
    test_event_type_grouping()
    test_hot_badge_for_high_priority()
    test_source_tier_section()
    test_brief_rank_missing_url_penalty()
    test_brief_rank_seen_count()
    print("\n✅ 所有测试通过")
