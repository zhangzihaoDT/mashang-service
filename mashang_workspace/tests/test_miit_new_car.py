"""
Tests for MIIT 新车公告批次监控模块。

优先覆盖纯函数：批次号解析、状态识别、附件链接解析、watchlist keyword 匹配、diff 输出结构。
"""

import sys, json, re
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_WS_DIR))

from research_scripts.miit_new_car.discover_batches import (
    _parse_batch_from_title,
    _detect_status,
)
from research_scripts.miit_new_car.diff_watchlist import (
    _keyword_match,
    _load_watchlist,
    diff_batch,
)
from research_scripts.miit_new_car.fetch_batch import (
    _extract_batch_no,
)


# ── Batch number extraction ──

def test_parse_batch_from_title_publicity():
    title = "关于《道路机动车辆生产企业及产品公告》（第408批）和...拟发布内容的公示"
    assert _parse_batch_from_title(title) == 408


def test_parse_batch_from_title_official():
    title = "《道路机动车辆生产企业及产品》（第407批）、《享受车船税..."
    assert _parse_batch_from_title(title) == 407


def test_parse_batch_from_title_no_match():
    assert _parse_batch_from_title("关于其他事项的通知") is None


def test_parse_batch_from_title_large():
    title = "关于《道路机动车辆生产企业及产品公告》（第409批）拟发布内容的公示"
    assert _parse_batch_from_title(title) == 409


def test_parse_batch_from_title_double():
    title = "关于《道路机动车辆生产企业及产品公告》（第408批）和《享受车船税减免优惠...》（第八十七批）"
    assert _parse_batch_from_title(title) == 408


def test_extract_batch_no_from_title():
    assert _extract_batch_no("关于第408批的公示", "http://example.com") == 408


def test_extract_batch_no_from_title():
    assert _extract_batch_no("关于第408批的公示", "http://example.com") == 408


# ── Status detection ──

def test_detect_status_publicity():
    assert _detect_status("关于...第408批...拟发布内容的公示") == "publicity"
    assert _detect_status("关于...第408批...公示") == "publicity"


def test_detect_status_official():
    assert _detect_status("《道路机动车辆生产企业及产品》（第407批）") == "official"
    assert _detect_status("《道路机动车辆生产企业及产品》（第406批）") == "official"


def test_detect_status_default():
    assert _detect_status("中华人民共和国工业和信息化部公告2026年第14号") == "official"


# ── Watchlist keyword matching ──

def test_keyword_match_brand_name():
    assert _keyword_match("上汽集团", "", "", "", "智己;IM;上汽集团") is True


def test_keyword_match_brand():
    assert _keyword_match("比亚迪汽车有限公司", "", "", "", "比亚迪") is True


def test_keyword_match_model():
    assert _keyword_match("", "理想", "L9", "", "理想") is True


def test_keyword_match_no_match():
    assert _keyword_match("某企业", "", "ABC", "", "智己;IM") is False


def test_keyword_match_partial():
    assert _keyword_match("上汽集团", "荣威", "ABC", "", "上汽集团") is True


def test_keyword_match_separator():
    assert _keyword_match("赛力斯汽车有限公司", "问界", "M9", "", "问界;赛力斯") is True


# ── Watchlist loading ──

def test_load_watchlist(tmp_path, monkeypatch):
    csv_path = tmp_path / "test_watchlist.csv"
    csv_path.write_text("brand,keywords\n智己,智己;IM\n理想,理想\n", encoding="utf-8-sig")
    entries = _load_watchlist(csv_path)
    assert len(entries) == 2
    assert entries[0]["brand"] == "智己"
    assert entries[0]["keywords"] == "智己;IM"


def test_load_watchlist_not_exists(capsys):
    entries = _load_watchlist(Path("/nonexistent/watchlist.csv"))
    assert entries == []


def test_load_watchlist_with_bom(tmp_path):
    csv_path = tmp_path / "bom_watchlist.csv"
    csv_path.write_bytes("\ufeffbrand,keywords\nXiaomi,小米\n".encode("utf-8"))
    entries = _load_watchlist(csv_path)
    assert len(entries) == 1
    assert entries[0]["brand"] == "Xiaomi"


# ── Diff output structure ──

def test_diff_structure_transforms(tmp_path, monkeypatch):
    """Test that diff_batch produces the correct output structure with mock data."""
    parsed_dir = tmp_path / "parsed"
    diff_dir = tmp_path / "diff"
    state_dir = tmp_path / "state"
    parsed_dir.mkdir(parents=True)
    diff_dir.mkdir(parents=True)
    state_dir.mkdir(parents=True)

    # Create mock current batch data
    current = [
        {
            "batch_no": 408, "batch_status": "publicity", "publish_date": "2026-06-10",
            "enterprise_name": "上海汽车集团股份有限公司", "brand": "智己",
            "product_model": "L6", "vehicle_name": "纯电动轿车",
        },
        {
            "batch_no": 408, "batch_status": "publicity", "publish_date": "2026-06-10",
            "enterprise_name": "比亚迪汽车有限公司", "brand": "比亚迪",
            "product_model": "海豚", "vehicle_name": "纯电动轿车",
        },
    ]
    (parsed_dir / "batch_408_products.json").write_text(json.dumps(current), encoding="utf-8")

    # Create mock previous batch data
    prev = [
        {
            "batch_no": 407, "batch_status": "official", "publish_date": "2026-06-12",
            "enterprise_name": "比亚迪汽车有限公司", "brand": "比亚迪",
            "product_model": "海豚", "vehicle_name": "纯电动轿车",
        },
    ]
    (parsed_dir / "batch_407_products.json").write_text(json.dumps(prev), encoding="utf-8")

    monkeypatch.setattr(
        "research_scripts.miit_new_car.diff_watchlist.PARSED_BASE",
        parsed_dir,
    )
    monkeypatch.setattr(
        "research_scripts.miit_new_car.diff_watchlist.DIFF_BASE",
        diff_dir,
    )
    monkeypatch.setattr(
        "research_scripts.miit_new_car.diff_watchlist.STATE_FILE",
        state_dir / "latest_processed_batch.json",
    )

    result = diff_batch(
        batch_no=408,
        previous_batch=407,
        watchlist_path=Path("/nonexistent"),
        output_dir=diff_dir,
        state_update=True,
    )

    assert result["batch_no"] == 408
    assert result["previous_batch"] == 407
    assert result["total_products"] == 2
    assert result["new_products"] == 1  # Only "智己 L6" is new
    assert result["watchlist_matched"] == 0  # No watchlist given

    # Check state file was written
    assert (state_dir / "latest_processed_batch.json").exists()
    state = json.loads((state_dir / "latest_processed_batch.json").read_text())
    assert state["latest_batch_no"] == 408

    # Check diff files
    assert (diff_dir / "batch_408_watchlist_diff.json").exists()
    assert (diff_dir / "batch_408_watchlist_diff.md").exists()


# ── Error robustness ──

def test_discover_batches_network_error(monkeypatch, capsys):
    """Simulate network error and ensure graceful handling - returns empty list."""
    def mock_fetch(*args, **kwargs):
        raise RuntimeError("模拟网络错误")
    monkeypatch.setattr(
        "research_scripts.miit_new_car.discover_batches._fetch_jpage",
        mock_fetch,
    )
    from research_scripts.miit_new_car.discover_batches import discover_batches
    result = discover_batches()
    assert result == []
    captured = capsys.readouterr()
    assert "模拟网络错误" in captured.err or "网络" in captured.err


def test_parse_batch_no_raw_dir(monkeypatch):
    from research_scripts.miit_new_car.parse_products import parse_batch
    import pytest
    with pytest.raises(FileNotFoundError, match="原始数据目录"):
        parse_batch(batch_no=99999)
