"""inbox_filter 测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.inbox_filter import classify


def _item(brand=None, model=None, event_type=None, title="", claim="", source_name=None, category=None):
    return {
        "brand": brand, "model": model, "event_type": event_type,
        "title": title, "claim": claim, "source_name": source_name,
        "category": category,
    }


def test_keep_brand_model_event_type():
    """明确品牌/车型/事件类型 → keep"""
    r = classify(_item(brand="智己", model="LS6", event_type="权益调整",
                        title="智己 LS6 权益调整", claim="限时权益", source_name="immotors.com"))
    assert r["decision"] == "keep"
    print(f"[PASS] test_keep_brand_model_event_type")


def test_keep_brand_with_action_keyword():
    """品牌 + 营销动作关键词 → keep"""
    r = classify(_item(brand="极氪", title="极氪 7X 开启交付", claim="首批交付"))
    assert r["decision"] == "keep"
    print(f"[PASS] test_keep_brand_with_action_keyword")


def test_keep_watchlist_event():
    """品牌 + 上市/交付/权益 → keep"""
    r = classify(_item(brand="智己", model="L6", title="智己 L6 正式上市"))
    assert r["decision"] == "keep"
    print(f"[PASS] test_keep_watchlist_event")


def test_discard_no_brand():
    """无品牌无车型 → discard"""
    r = classify(_item(title="宁德时代发布第三代换电方案", event_type="技术发布"))
    assert r["decision"] == "discard"
    assert "no_brand_or_model" in r["reason"]
    print(f"[PASS] test_discard_no_brand")


def test_discard_opinion():
    """主观评论/预测 → discard"""
    r = classify(_item(brand="智己", title="我觉得智己下半年会卖得很好", claim="预计销量翻倍"))
    assert r["decision"] == "discard"
    assert "opinion_or_prediction" in r["reason"]
    print(f"[PASS] test_discard_opinion")


def test_discard_no_event():
    """无事件类型也无动作关键词 → discard"""
    r = classify(_item(brand="宝马", title="宝马今年感觉不错", claim="看起来很好"))
    assert r["decision"] == "discard"
    print(f"[PASS] test_discard_no_event")


def test_discard_no_structured_fact():
    """无法形成结构化事实 → discard"""
    r = classify(_item(brand="特斯拉", title="特斯拉", claim="一些消息"))
    assert r["decision"] == "discard"
    print(f"[PASS] test_discard_no_structured_fact")


if __name__ == "__main__":
    test_keep_brand_model_event_type()
    test_keep_brand_with_action_keyword()
    test_keep_watchlist_event()
    test_discard_no_brand()
    test_discard_opinion()
    test_discard_no_event()
    test_discard_no_structured_fact()
    print("\n✅ 所有测试通过")
