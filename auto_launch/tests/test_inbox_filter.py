"""inbox_filter 测试 — Planner 日报路由"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.inbox_filter import route


def _item(brand=None, section_type=None, event_type=None, claim="", model=None):
    return {"brand": brand, "section_type": section_type,
            "event_type": event_type, "claim": claim, "model": model}


def test_route_brand_event_to_confirmed_fact():
    r = route(_item(brand="理想", section_type="brand_events", event_type="partnership"))
    assert r["decision"] == "route"
    assert r["route_to"] == "confirmed_fact"


def test_route_review_signal():
    r = route(_item(brand="极氪", section_type="review_signals", claim="境外锁车争议"))
    assert r["decision"] == "route"
    assert r["route_to"] == "review_signal"


def test_route_brand_status():
    r = route(_item(brand="问界", section_type="brand_status"))
    assert r["decision"] == "route"
    assert r["route_to"] == "brand_status"


def test_route_brand_volume():
    r = route(_item(brand="小米", section_type="brand_volume"))
    assert r["decision"] == "route"
    assert r["route_to"] == "brand_volume"


def test_route_unknown_section():
    r = route(_item(brand="智己", section_type="unknown"))
    assert r["decision"] == "route"
    assert r["route_to"] == "other"


def test_route_no_section_type():
    r = route(_item(brand="智己"))
    assert r["decision"] == "route"
    assert r["route_to"] == "other"


if __name__ == "__main__":
    test_route_brand_event_to_confirmed_fact()
    test_route_review_signal()
    test_route_brand_status()
    test_route_brand_volume()
    test_route_unknown_section()
    test_route_no_section_type()
    print("\n✅ 所有测试通过")
