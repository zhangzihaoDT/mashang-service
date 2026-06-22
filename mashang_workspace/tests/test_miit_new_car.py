"""
Tests for MIIT 新车公告批次监控模块 V0.2.

覆盖：批次号解析、状态识别、watchlist 匹配、diff 结构、
latest-publicity/latest-official 筛选、多页去重、
附件 404 容错、docx 文本抽取、doc unsupported、evidence 结构。
"""

import sys, json, re, zipfile
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_WS_DIR))

from research_scripts.miit_new_car.discover_batches import (
    _parse_batch_from_title,
    _detect_status,
    discover_batches,
    discover_latest_by_status,
    _dedup,
)
from research_scripts.miit_new_car.diff_watchlist import (
    _keyword_match,
    _load_watchlist,
    diff_batch,
)
from research_scripts.miit_new_car.fetch_batch import (
    _extract_batch_no,
)
from research_scripts.miit_new_car.extract_attachment_text import (
    _extract_docx_text,
    _extract_html_text,
)


# ── Batch number extraction ──

def test_parse_batch_from_title_publicity():
    assert _parse_batch_from_title("关于《道路机动车辆生产企业及产品公告》（第408批）和...拟发布内容的公示") == 408


def test_parse_batch_from_title_official():
    assert _parse_batch_from_title("《道路机动车辆生产企业及产品》（第407批）、《享受车船税...") == 407


def test_parse_batch_from_title_no_match():
    assert _parse_batch_from_title("关于其他事项的通知") is None


def test_parse_batch_from_title_large():
    assert _parse_batch_from_title("关于《道路机动车辆生产企业及产品公告》（第409批）拟发布内容的公示") == 409


def test_parse_batch_from_title_double():
    assert _parse_batch_from_title("关于《道路机动车辆生产企业及产品公告》（第408批）和《享受车船税减免优惠...》（第八十七批）") == 408


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


# ── Status filtering (V0.2) ──

def _mock_discover_batches_all(*, limit=10, pages=1, status_filter=None, _all_batches=None):
    if _all_batches is None:
        return []
    if status_filter:
        return [b for b in _all_batches if b["status"] == status_filter][:limit]
    return _all_batches[:limit]


def test_discover_latest_by_status_publicity(monkeypatch):
    """Test that discover_latest_by_status('publicity') filters correctly."""
    mock_batches = [
        {"batch_no": 408, "status": "publicity", "title": "关于第408批公示", "publish_date": "2026-06-10", "detail_url": "http://a"},
        {"batch_no": 407, "status": "official", "title": "第407批正式公告", "publish_date": "2026-06-12", "detail_url": "http://b"},
        {"batch_no": 406, "status": "official", "title": "第406批正式公告", "publish_date": "2026-05-09", "detail_url": "http://c"},
    ]
    monkeypatch.setattr(
        "research_scripts.miit_new_car.discover_batches.discover_batches",
        lambda limit=10, pages=1, status_filter=None: _mock_discover_batches_all(limit=limit, pages=pages, status_filter=status_filter, _all_batches=mock_batches),
    )
    result = discover_latest_by_status("publicity")
    assert result is not None
    assert result["batch_no"] == 408
    assert result["status"] == "publicity"


def test_discover_latest_by_status_official(monkeypatch):
    mock_batches = [
        {"batch_no": 408, "status": "publicity", "title": "关于第408批公示", "publish_date": "2026-06-10", "detail_url": "http://a"},
        {"batch_no": 407, "status": "official", "title": "第407批正式公告", "publish_date": "2026-06-12", "detail_url": "http://b"},
    ]
    monkeypatch.setattr(
        "research_scripts.miit_new_car.discover_batches.discover_batches",
        lambda limit=10, pages=1, status_filter=None: _mock_discover_batches_all(limit=limit, pages=pages, status_filter=status_filter, _all_batches=mock_batches),
    )
    result = discover_latest_by_status("official")
    assert result is not None
    assert result["batch_no"] == 407
    assert result["status"] == "official"


def test_discover_latest_by_status_no_match(monkeypatch):
    monkeypatch.setattr("research_scripts.miit_new_car.discover_batches.discover_batches", lambda limit=10, pages=1, status_filter=None: [])
    assert discover_latest_by_status("publicity") is None


# ── Multi-page dedup (V0.2) ──

def test_dedup():
    items = [
        {"batch_no": 408, "status": "publicity", "detail_url": "http://a"},
        {"batch_no": 408, "status": "publicity", "detail_url": "http://a"},
        {"batch_no": 407, "status": "official", "detail_url": "http://b"},
    ]
    result = _dedup(items)
    assert len(result) == 2
    assert result[0]["batch_no"] == 408
    assert result[1]["batch_no"] == 407


def test_discover_batches_status_filter(monkeypatch):
    """Test discover_batches with status_filter."""
    mock_batches = [
        {"batch_no": 408, "status": "publicity", "title": "公示", "publish_date": "", "detail_url": "", "source": ""},
        {"batch_no": 407, "status": "official", "title": "正式", "publish_date": "", "detail_url": "", "source": ""},
    ]
    monkeypatch.setattr("research_scripts.miit_new_car.discover_batches._fetch_jpage", lambda page=1: "<xml/>")
    monkeypatch.setattr("research_scripts.miit_new_car.discover_batches._RecordExtractor", lambda: type("MockExtractor", (), {"parse": lambda self, xml: []})())
    result = discover_batches(limit=5, status_filter="publicity")
    # Should be empty since mock returns no records (but at least doesn't crash)
    assert isinstance(result, list)


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

def test_load_watchlist(tmp_path):
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
    """Test diff_batch produces the correct output structure with mock data."""
    parsed_dir = tmp_path / "parsed"
    diff_dir = tmp_path / "diff"
    state_dir = tmp_path / "state"
    parsed_dir.mkdir(parents=True)
    diff_dir.mkdir(parents=True)
    state_dir.mkdir(parents=True)

    current = [
        {"batch_no": 408, "batch_status": "publicity", "publish_date": "2026-06-10",
         "enterprise_name": "上汽集团", "brand": "智己", "product_model": "L6", "vehicle_name": "纯电动轿车"},
        {"batch_no": 408, "batch_status": "publicity", "publish_date": "2026-06-10",
         "enterprise_name": "比亚迪有限公司", "brand": "比亚迪", "product_model": "海豚", "vehicle_name": "纯电动轿车"},
    ]
    (parsed_dir / "batch_408_products.json").write_text(json.dumps(current), encoding="utf-8")

    prev = [
        {"batch_no": 407, "batch_status": "official", "publish_date": "2026-06-12",
         "enterprise_name": "比亚迪有限公司", "brand": "比亚迪", "product_model": "海豚", "vehicle_name": "纯电动轿车"},
    ]
    (parsed_dir / "batch_407_products.json").write_text(json.dumps(prev), encoding="utf-8")

    monkeypatch.setattr("research_scripts.miit_new_car.diff_watchlist.PARSED_BASE", parsed_dir)
    monkeypatch.setattr("research_scripts.miit_new_car.diff_watchlist.DIFF_BASE", diff_dir)
    monkeypatch.setattr("research_scripts.miit_new_car.diff_watchlist.STATE_FILE", state_dir / "latest_processed_batch.json")

    result = diff_batch(batch_no=408, previous_batch=407, watchlist_path=Path("/nonexistent"), output_dir=diff_dir, state_update=True)

    assert result["batch_no"] == 408
    assert result["previous_batch"] == 407
    assert result["total_products"] == 2
    assert result["new_products"] == 1
    assert (state_dir / "latest_processed_batch.json").exists()
    assert (diff_dir / "batch_408_watchlist_diff.json").exists()
    assert (diff_dir / "batch_408_watchlist_diff.md").exists()


# ── Attachment 404 should not crash fetch (V0.2) ──

def test_fetch_attachment_404_no_crash(monkeypatch, capsys):
    """Simulate a 404 on one attachment; verify the overall fetch doesn't crash."""
    from research_scripts.miit_new_car.fetch_batch import fetch_batch

    # Mock _fetch so the detail page returns HTML, but one attachment returns 404
    _fetch_calls = []

    def mock_fetch(url, timeout=60):
        _fetch_calls.append(url)
        from urllib.error import HTTPError
        if "nodata" in url:
            raise HTTPError(url, 404, "Not Found", {}, None)
        if "detail" in url or "/art/" in url:
            return b"<html><body>Mock detail page</body></html>", 200
        if ".doc" in url:
            return b"mock doc content", 200
        return b"mock content", 200

    monkeypatch.setattr("research_scripts.miit_new_car.fetch_batch._fetch", mock_fetch)

    # Mock discover_batches at its source module
    monkeypatch.setattr(
        "research_scripts.miit_new_car.discover_batches.discover_batches",
        lambda limit=5, pages=1, status_filter=None: [
            {"batch_no": 408, "detail_url": "http://mock/detail", "status": "publicity", "title": "test"}
        ],
    )

    # Mock _DetailParser to return attachments (one that will 404)
    class MockDetailParser:
        def __init__(self):
            self.title = "第408批公示"
            self.publish_date = "2026-06-10"
            self.content_html = ""
            self.attachments = [
                {"url": "http://mock/nodata/doc.html", "title": "失败附件", "filename": "doc.html"},
                {"url": "http://mock/ok.doc", "title": "成功附件", "filename": "ok.doc"},
            ]
        def feed(self, html): pass

    monkeypatch.setattr("research_scripts.miit_new_car.fetch_batch._DetailParser", MockDetailParser)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr("research_scripts.miit_new_car.fetch_batch.OUTPUT_BASE", Path(td))
        result = fetch_batch(batch_no=408, download=True)
        assert result["batch_no"] == 408
        statuses = result.get("attachment_statuses", [])
        assert len(statuses) == 2
        failed = [s for s in statuses if s["status"] == "failed"]
        downloaded = [s for s in statuses if s["status"] == "downloaded"]
        assert len(failed) == 1
        assert len(downloaded) == 1


# ── DOCX text extraction (V0.2) ──

def test_docx_text_extraction(tmp_path):
    """Verify _extract_docx_text can extract text from a simple docx."""
    # Build a minimal docx with zipfile
    docx_path = tmp_path / "test.docx"
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        '<w:p><w:r><w:t>小米SU7</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>纯电动轿车</w:t></w:r></w:p>'
        '</w:body>'
        '</w:document>'
    )
    with zipfile.ZipFile(docx_path, "w") as z:
        z.writestr("word/document.xml", document_xml)

    text = _extract_docx_text(docx_path)
    assert "小米SU7" in text
    assert "纯电动轿车" in text


def test_docx_text_extraction_empty(tmp_path):
    docx_path = tmp_path / "empty.docx"
    with zipfile.ZipFile(docx_path, "w") as z:
        z.writestr("word/document.xml", "<w:document/>")
    text = _extract_docx_text(docx_path)
    assert text == ""


# ── HTML text extraction (V0.2) ──

def test_html_text_extraction(tmp_path):
    html_path = tmp_path / "test.html"
    html_path.write_text("<html><body><p>智己L6</p><p>纯电动轿车</p></body></html>", encoding="utf-8")
    text = _extract_html_text(html_path)
    assert "智己L6" in text
    assert "纯电动轿车" in text


def test_html_text_extraction_skip_hidden(tmp_path):
    html_path = tmp_path / "hidden.html"
    html_path.write_text(
        '<html><body><p>可见</p><p style="display:none">隐藏</p><p>也可见</p></body></html>',
        encoding="utf-8",
    )
    text = _extract_html_text(html_path)
    assert "可见" in text
    assert "隐藏" not in text


# ── DOC unsupported (V0.2) ──

def test_doc_extract_unsupported(tmp_path, monkeypatch):
    """Verify .doc extraction returns unsupported when no system tool available."""
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    doc_path = tmp_path / "test.doc"
    doc_path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    from research_scripts.miit_new_car.extract_attachment_text import _extract_doc_text
    status, text = _extract_doc_text(doc_path)
    assert status == "unsupported"
    assert text == ""


# ── Evidence structure (V0.2) ──

def test_evidence_structure(tmp_path, monkeypatch):
    """Verify that _write_evidence produces the expected JSON structure."""
    from research_scripts.miit_new_car.monitor import _write_evidence

    EVIDENCE_BASE = tmp_path / "evidence"
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.EVIDENCE_BASE", EVIDENCE_BASE)

    meta = {
        "batch_no": 408, "status": "publicity", "publish_date": "2026-06-10",
        "detail_url": "http://example.com", "fetched_at": "2026-06-22T00:00:00Z",
    }
    diff_result = {
        "matched_products": [
            {"brand": "智己", "matched_keyword": "智己", "matched_text": "上汽集团 智己 L6 纯电动轿车"},
        ],
        "watchlist_matched": 1, "new_products": 1, "new_watchlist_matched": 1,
    }
    attachment_statuses = [
        {"status": "downloaded"}, {"status": "failed", "error": "404"},
    ]
    extraction_results = [
        {"extract_status": "success", "text_length": 100, "text_preview": "abc", "filename": "a.html"},
        {"extract_status": "unsupported", "text_length": 0, "text_preview": "", "filename": "b.doc", "error": "no tool"},
    ]
    products = [{"enterprise_name": "上汽集团", "brand": "智己"}]

    evidence = _write_evidence(
        batch_no=408, meta=meta, diff_result=diff_result,
        attachment_statuses=attachment_statuses,
        extraction_results=extraction_results, products=products,
    )

    assert evidence["source_type"] == "official"
    assert evidence["batch_no"] == 408
    assert evidence["batch_status"] == "publicity"
    assert len(evidence["watchlist_hits"]) == 1
    assert evidence["watchlist_hits"][0]["brand"] == "智己"
    assert evidence["watchlist_hits"][0]["confidence"] == "high"
    assert evidence["attachment_summary"]["downloaded"] == 1
    assert evidence["attachment_summary"]["failed"] == 1
    assert evidence["extraction_summary"]["success"] == 1
    assert evidence["extraction_summary"]["unsupported"] == 1
    assert evidence["parsed_product_count"] == 1

    # Check file was written
    evidence_file = EVIDENCE_BASE / "batch_408_official_source_evidence.json"
    assert evidence_file.exists()
    loaded = json.loads(evidence_file.read_text())
    assert loaded["batch_no"] == 408


# ── Error robustness ──

def test_discover_batches_network_error(monkeypatch, capsys):
    def mock_fetch(*args, **kwargs):
        raise RuntimeError("模拟网络错误")
    monkeypatch.setattr("research_scripts.miit_new_car.discover_batches._fetch_jpage", mock_fetch)
    from research_scripts.miit_new_car.discover_batches import discover_batches
    result = discover_batches()
    assert result == []
    captured = capsys.readouterr()
    assert "模拟网络错误" in captured.err or "网络" in captured.err


def test_parse_batch_no_raw_dir():
    from research_scripts.miit_new_car.parse_products import parse_batch
    import pytest
    with pytest.raises(FileNotFoundError, match="原始数据目录"):
        parse_batch(batch_no=99999)


# ── Default metadata output path in readme ──

def test_monitor_output_structure(monkeypatch):
    """Verify monitor's run_monitor returns expected top-level keys."""
    from research_scripts.miit_new_car.monitor import run_monitor

    def mock_fetch_batch(*a, **kw):
        return {
            "batch_no": 408, "status": "publicity", "title": "测试",
            "publish_date": "2026-06-10", "detail_url": "http://a",
            "fetched_at": "2026-06-22T00:00:00Z",
            "attachment_statuses": [{"status": "downloaded"}],
        }

    def mock_parse_batch(*a, **kw):
        return [{"enterprise_name": "上汽集团"}]

    def mock_diff_batch(*a, **kw):
        return {"watchlist_matched": 1, "new_products": 1, "new_watchlist_matched": 1,
                "matched_products": [{"brand": "智己", "matched_keyword": "", "matched_text": ""}]}

    def mock_extract_text(*a, **kw):
        return []

    def mock_write_evidence(*a, **kw):
        return {"source_type": "official"}

    monkeypatch.setattr("research_scripts.miit_new_car.monitor.fetch_batch", mock_fetch_batch)
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.parse_batch", mock_parse_batch)
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.diff_batch", mock_diff_batch)
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.extract_attachment_text", mock_extract_text)
    monkeypatch.setattr("research_scripts.miit_new_car.monitor._write_evidence", mock_write_evidence)

    result = run_monitor(batch_no=408, download=False, state_update=False)
    assert result["batch_no"] == 408
    assert "product_count" in result
    assert "attachments_downloaded" in result
    assert "extraction_success" in result
    assert "evidence" in result
