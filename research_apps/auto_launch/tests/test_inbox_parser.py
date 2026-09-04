"""inbox_parser 测试 — Planner 日报"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.inbox_parser import parse_text, parse_contract

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "planner_daily_report.md"
PLANNER_TEXT = FIXTURE.read_text(encoding="utf-8")


def test_parse_sample_returns_items():
    items = parse_text(PLANNER_TEXT)
    assert len(items) == 27
    print(f"[PASS] parse_sample_returns_items: {len(items)} items")


def test_parse_brand_extraction():
    items = parse_text(PLANNER_TEXT)
    brands = {i.get("brand") for i in items if i.get("brand")}
    assert "智己" in brands
    assert "极氪" in brands
    print(f"[PASS] parse_brand_extraction: {len(brands)} brands")


def test_parse_event_type_extraction():
    items = parse_text(PLANNER_TEXT)
    types = {i.get("event_type") for i in items if i.get("event_type")}
    assert "权益调整" in types
    print(f"[PASS] parse_event_type_extraction: {types}")


def test_parse_section_type_present():
    items = parse_text(PLANNER_TEXT)
    for item in items:
        assert item.get("section_type") is not None
    print(f"[PASS] parse_section_type_present")


def test_parse_handles_empty_input():
    items = parse_text("")
    assert items == []
    print(f"[PASS] parse_handles_empty_input")


def test_parse_contract_structure():
    contract = parse_contract(PLANNER_TEXT)
    assert contract["source_type"] == "planner_daily_report"
    assert len(contract["sections"]) == 4
    assert len(contract["items"]) == 27
    print(f"[PASS] parse_contract_structure: {len(contract['sections'])} sections")


def test_parse_handles_simple_planner():
    md = """## 一、可入库确认事件

| brand | event_type | claim |
|------|-----------|-------|
| 智己 | 权益调整 | 限时权益 |
"""
    items = parse_text(md)
    assert len(items) == 1
    assert items[0]["brand"] == "智己"
    assert items[0]["event_type"] == "权益调整"
    assert items[0]["section_type"] == "brand_events"
    print(f"[PASS] parse_handles_simple_planner")


if __name__ == "__main__":
    test_parse_sample_returns_items()
    test_parse_brand_extraction()
    test_parse_event_type_extraction()
    test_parse_section_type_present()
    test_parse_handles_empty_input()
    test_parse_contract_structure()
    test_parse_handles_simple_planner()
    print("\n✅ 所有测试通过")
