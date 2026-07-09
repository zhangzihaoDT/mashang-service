"""inbox_parser 测试"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.inbox_parser import parse_text

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "daily_run_sample.md"
SAMPLE = FIXTURE.read_text(encoding="utf-8")


def test_parse_sample_returns_items():
    items = parse_text(SAMPLE)
    assert len(items) >= 5
    print(f"[PASS] parse_sample_returns_items: {len(items)} items")


def test_parse_brand_extraction():
    items = parse_text(SAMPLE)
    brands = {i.get("brand") for i in items}
    assert "智己" in brands
    assert "极氪" in brands
    assert "问界" in brands
    print(f"[PASS] test_parse_brand_extraction: {brands}")


def test_parse_event_type_extraction():
    items = parse_text(SAMPLE)
    types = {i.get("event_type") for i in items if i.get("event_type")}
    assert "权益调整" in types or "改款上市" in types
    print(f"[PASS] test_parse_event_type_extraction: {types}")


def test_parse_source_tier_normalization():
    items = parse_text(SAMPLE)
    for item in items:
        if item.get("source_tier"):
            assert item["source_tier"].startswith("tier_")
    print(f"[PASS] test_parse_source_tier_normalization")


def test_parse_handles_chatgpt_markdown():
    md = """
## 智己 L6 发布新版本

- 品牌: 智己
- 车型: L6
- 事件类型: 新品发布
- 时间: 2026-07-09
"""
    items = parse_text(md)
    assert len(items) == 1
    assert items[0]["brand"] == "智己"
    assert items[0]["model"] == "L6"
    print(f"[PASS] test_parse_handles_chatgpt_markdown")


def test_parse_handles_empty_input():
    items = parse_text("")
    assert items == []
    print(f"[PASS] test_parse_handles_empty_input")


def test_parse_no_brand_fallback():
    md = "今天极氪有新的权益调整\n没有什么其他信息了"
    items = parse_text(md)
    assert len(items) >= 1
    # "极氪" 应被 _try_extract_brand_from_text 识别
    brands = [i.get("brand") for i in items]
    assert any(b == "极氪" for b in brands if b)
    print(f"[PASS] test_parse_no_brand_fallback")


if __name__ == "__main__":
    test_parse_sample_returns_items()
    test_parse_brand_extraction()
    test_parse_event_type_extraction()
    test_parse_source_tier_normalization()
    test_parse_handles_chatgpt_markdown()
    test_parse_handles_empty_input()
    test_parse_no_brand_fallback()
    print("\n✅ 所有测试通过")
