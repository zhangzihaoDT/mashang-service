"""
Tests for MIIT 新车公告批次监控模块 V0.2.1.

V0.2.1 新增覆盖:
  - discovery cache fallback（远端超时 + 缓存存在 → 可用）
  - discovery cache fallback（远端超时 + 无缓存 → network_unavailable）
  - detail.html cache fallback
  - 已处理批次幂等复用 evidence
  - --refresh 重新处理（允许缓存）
  - --force-refresh 重新处理（不允许缓存）
  - summary 包含 discovery/detail/evidence_source + network_warnings_count
  - http_utils 重试机制
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
from research_scripts.miit_new_car.http_utils import (
    NetworkError,
    http_get,
    http_get_text,
)
from research_scripts.miit_new_car.discover_batches import _fetch_jpage as _db_fetch_jpage


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
    assert _parse_batch_from_title("关于《道路机动车辆生产企业及产品公告》（第408批）和《享受车船税...》（第八十七批）") == 408


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

def test_discover_latest_by_status_publicity(monkeypatch):
    mock_all = [
        {"batch_no": 408, "status": "publicity", "title": "关于第408批公示", "publish_date": "2026-06-10", "detail_url": "http://a"},
        {"batch_no": 407, "status": "official", "title": "第407批正式公告", "publish_date": "2026-06-12", "detail_url": "http://b"},
        {"batch_no": 406, "status": "official", "title": "第406批正式公告", "publish_date": "2026-05-09", "detail_url": "http://c"},
    ]
    monkeypatch.setattr(
        "research_scripts.miit_new_car.discover_batches.discover_batches",
        lambda limit=10, pages=1, status_filter=None, force_refresh=False: (
            [b for b in mock_all if b["status"] == status_filter][:limit] if status_filter else mock_all[:limit],
            "remote",
        ),
    )
    result, source = discover_latest_by_status("publicity")
    assert result is not None
    assert result["batch_no"] == 408
    assert result["status"] == "publicity"
    assert source == "remote"


def test_discover_latest_by_status_official(monkeypatch):
    mock_all = [
        {"batch_no": 408, "status": "publicity", "title": "关于第408批公示", "publish_date": "2026-06-10", "detail_url": "http://a"},
        {"batch_no": 407, "status": "official", "title": "第407批正式公告", "publish_date": "2026-06-12", "detail_url": "http://b"},
    ]
    monkeypatch.setattr(
        "research_scripts.miit_new_car.discover_batches.discover_batches",
        lambda limit=10, pages=1, status_filter=None, force_refresh=False: (
            [b for b in mock_all if b["status"] == status_filter][:limit] if status_filter else mock_all[:limit],
            "remote",
        ),
    )
    result, source = discover_latest_by_status("official")
    assert result is not None
    assert result["batch_no"] == 407
    assert result["status"] == "official"


# ── V0.2.1: Discovery cache fallback ──

def test_discover_cache_fallback_remote_fails_cache_exists(tmp_path, monkeypatch):
    """Remote fails but cache exists → returns cache + source='cache'."""
    cached = [
        {"batch_no": 408, "status": "publicity", "title": "第408批", "publish_date": "2026-06-10", "detail_url": "http://a", "source": "miit-eidc"},
    ]
    cache_file = tmp_path / "discovered_batches.json"
    cache_file.write_text(json.dumps(cached), encoding="utf-8")
    monkeypatch.setattr("research_scripts.miit_new_car.discover_batches.DISCOVERY_CACHE_FILE", cache_file)

    def mock_fetch_jpage(page=1):
        raise NetworkError("超时模拟")
    monkeypatch.setattr("research_scripts.miit_new_car.discover_batches._fetch_jpage", mock_fetch_jpage)

    batches, source = discover_batches(limit=5)
    assert len(batches) == 1
    assert source == "cache"
    assert batches[0]["batch_no"] == 408


def test_discover_cache_fallback_no_cache(tmp_path, monkeypatch):
    """Remote fails and no cache → returns ([], 'network_unavailable')."""
    cache_file = tmp_path / "discovered_batches.json"
    monkeypatch.setattr("research_scripts.miit_new_car.discover_batches.DISCOVERY_CACHE_FILE", cache_file)
    assert not cache_file.exists()

    def mock_fetch_jpage(page=1):
        raise NetworkError("超时模拟")
    monkeypatch.setattr("research_scripts.miit_new_car.discover_batches._fetch_jpage", mock_fetch_jpage)

    batches, source = discover_batches(limit=5)
    assert batches == []
    assert source == "network_unavailable"


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
    assert result["new_products"] == 1
    assert (diff_dir / "batch_408_watchlist_diff.json").exists()


# ── V0.2.1: Detail page cache fallback ──

def test_fetch_detail_cache_fallback(tmp_path, monkeypatch):
    """Detail page fetch fails but detail.html exists locally → uses cached HTML."""
    batch_dir = tmp_path / "batch_408"
    batch_dir.mkdir(parents=True)
    detail_html = batch_dir / "detail.html"
    detail_html.write_text(
        '<html><div class="_nk_wz_tit">第408批公示测试</div></html>',
        encoding="utf-8",
    )

    monkeypatch.setattr("research_scripts.miit_new_car.fetch_batch.OUTPUT_BASE", tmp_path)

    def mock_http_get(url, **kw):
        raise NetworkError("超时模拟")
    monkeypatch.setattr("research_scripts.miit_new_car.fetch_batch.http_get", mock_http_get)

    def mock_discover(*a, **kw):
        return [{"batch_no": 408, "detail_url": "http://mock/detail", "status": "publicity"}], "remote"
    monkeypatch.setattr("research_scripts.miit_new_car.discover_batches.discover_batches", mock_discover)

    from research_scripts.miit_new_car.fetch_batch import fetch_batch
    result = fetch_batch(batch_no=408, download=False)
    assert result["batch_no"] == 408
    assert result.get("detail_source") == "cache"


def test_fetch_detail_cache_not_found_fails(monkeypatch):
    """Detail page fetch fails and no local cache → raises RuntimeError."""
    def mock_http_get(url, **kw):
        raise NetworkError("超时模拟")
    monkeypatch.setattr("research_scripts.miit_new_car.fetch_batch.http_get", mock_http_get)

    def mock_discover(*a, **kw):
        return [{"batch_no": 408, "detail_url": "http://mock/detail", "status": "publicity"}], "remote"
    monkeypatch.setattr("research_scripts.miit_new_car.discover_batches.discover_batches", mock_discover)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr("research_scripts.miit_new_car.fetch_batch.OUTPUT_BASE", Path(td))
        from research_scripts.miit_new_car.fetch_batch import fetch_batch
        import pytest
        with pytest.raises(RuntimeError, match="详情页请求失败且本地无缓存"):
            fetch_batch(batch_no=408, download=False)


# ── V0.2.1: Idempotent evidence reuse ──

def test_monitor_evidence_idempotent(tmp_path, monkeypatch):
    """Evidence exists and no --refresh → reuse existing."""
    evidence_file = tmp_path / "evidence" / "batch_408_official_source_evidence.json"
    evidence_file.parent.mkdir(parents=True)
    evidence_data = {
        "source_type": "official", "source_name": "MIIT New Car Announcement",
        "batch_no": 408, "batch_status": "publicity", "publish_date": "2026-06-10",
        "detail_url": "http://mock", "discovery_source": "cache",
        "detail_source": "cache", "evidence_source": "existing",
        "parsed_product_count": 5,
        "watchlist_hits": [{"brand": "智己", "matched_keyword": "智己", "matched_text": "上汽集团", "confidence": "high", "evidence_type": "official_announcement_publicity"}],
    }
    evidence_file.write_text(json.dumps(evidence_data), encoding="utf-8")

    monkeypatch.setattr("research_scripts.miit_new_car.monitor.EVIDENCE_BASE", tmp_path / "evidence")
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.OUTPUT_BASE", tmp_path)

    from research_scripts.miit_new_car.monitor import _is_already_processed, _load_existing_evidence, _build_summary_from_evidence
    assert _is_already_processed(408) is True
    ev = _load_existing_evidence(408)
    assert ev is not None
    summary = _build_summary_from_evidence(ev)
    assert summary["batch_no"] == 408
    assert summary["evidence_source"] == "existing"
    assert summary["discovery_source"] == "skipped_existing"
    assert summary["detail_source"] == "skipped_existing"
    assert summary["structured_records"] == 5


# ── V0.2.1: Summary cache markers ──

def test_run_monitor_summary_cache_markers(monkeypatch):
    """Verify that run_monitor output contains discovery/detail/evidence_source + network_warnings_count."""
    from research_scripts.miit_new_car.monitor import run_monitor

    def mock_fetch(*a, **kw):
        return {
            "batch_no": 408, "status": "publicity", "title": "测试",
            "publish_date": "2026-06-10", "detail_url": "http://a",
            "fetched_at": "2026-06-22T00:00:00Z",
            "detail_source": "remote",
            "attachment_statuses": [{"status": "downloaded"}],
        }
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.fetch_batch", mock_fetch)
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.parse_batch", lambda **kw: [{"enterprise_name": "上汽集团"}])
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.diff_batch",
                        lambda **kw: {"watchlist_matched": 1, "new_products": 1, "new_watchlist_matched": 1, "matched_products": []})
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.extract_attachment_text", lambda **kw: [])
    monkeypatch.setattr("research_scripts.miit_new_car.monitor._write_evidence", lambda **kw: {"source_type": "official"})

    result = run_monitor(batch_no=408, download=False, state_update=False, discovery_source="remote")
    assert result["discovery_source"] == "remote"
    assert result["detail_source"] == "remote"
    assert result["evidence_source"] == "generated"
    assert "network_warnings_count" in result
    assert "network_retry_count" in result


# ── V0.2.1: http_utils retry mechanism ──

def test_http_network_error_class():
    err = NetworkError("测试错误", url="http://mock", cause=ValueError("内部错误"))
    assert str(err) == "测试错误"
    assert err.url == "http://mock"
    assert isinstance(err.cause, ValueError)
    assert isinstance(err, RuntimeError)


# ── Attachment 404 should not crash fetch ──

def test_fetch_attachment_404_no_crash(monkeypatch):
    from research_scripts.miit_new_car.fetch_batch import fetch_batch

    def mock_http_get(url, **kw):
        from urllib.error import HTTPError
        if "nodata" in url:
            raise __import__("research_scripts.miit_new_car.http_utils", fromlist=["NetworkError"]).NetworkError("404模拟")
        if "detail" in url or "/art/" in url:
            return b"<html><body>Mock</body></html>", 200
        return b"mock", 200

    monkeypatch.setattr("research_scripts.miit_new_car.fetch_batch.http_get", mock_http_get)
    monkeypatch.setattr(
        "research_scripts.miit_new_car.discover_batches.discover_batches",
        lambda limit=5, pages=1, status_filter=None, force_refresh=False: (
            [{"batch_no": 408, "detail_url": "http://mock/detail", "status": "publicity", "title": "test"}],
            "remote",
        ),
    )

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
        assert len(failed) >= 1


# ── DOCX text extraction ──

def test_docx_text_extraction(tmp_path):
    docx_path = tmp_path / "test.docx"
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        '<w:p><w:r><w:t>小米SU7</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>纯电动轿车</w:t></w:r></w:p>'
        '</w:body></w:document>'
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


# ── HTML text extraction ──

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


# ── DOC unsupported ──

def test_doc_extract_unsupported(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    doc_path = tmp_path / "test.doc"
    doc_path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    from research_scripts.miit_new_car.extract_attachment_text import _extract_doc_text
    status, text = _extract_doc_text(doc_path)
    assert status == "unsupported"
    assert text == ""


# ── Evidence structure ──

def test_evidence_structure(tmp_path, monkeypatch):
    from research_scripts.miit_new_car.monitor import _write_evidence

    EVIDENCE_BASE = tmp_path / "evidence"
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.EVIDENCE_BASE", EVIDENCE_BASE)

    meta = {
        "batch_no": 408, "status": "publicity", "publish_date": "2026-06-10",
        "detail_url": "http://example.com", "fetched_at": "2026-06-22T00:00:00Z",
        "detail_source": "remote",
    }
    diff_result = {
        "matched_products": [{"brand": "智己", "matched_keyword": "智己", "matched_text": "上汽集团 智己 L6"}],
        "watchlist_matched": 1, "new_products": 1, "new_watchlist_matched": 1,
    }
    att_statuses = [{"status": "downloaded"}, {"status": "failed", "error": "404"}]
    ext_results = [
        {"extract_status": "success", "text_length": 100, "text_preview": "abc", "filename": "a.html"},
        {"extract_status": "unsupported", "text_length": 0, "text_preview": "", "filename": "b.doc", "error": "no tool"},
    ]
    products = [{"enterprise_name": "上汽集团", "brand": "智己"}]

    evidence = _write_evidence(408, meta, diff_result, att_statuses, ext_results, products, discovery_source="cache")
    assert evidence["source_type"] == "official"
    assert evidence["batch_no"] == 408
    assert evidence["discovery_source"] == "cache"
    assert evidence["detail_source"] == "remote"
    assert len(evidence["watchlist_hits"]) == 1
    assert evidence["watchlist_hits"][0]["brand"] == "智己"
    assert evidence["attachment_summary"]["downloaded"] == 1
    assert evidence["attachment_summary"]["failed"] == 1
    assert evidence["extraction_summary"]["success"] == 1
    assert evidence["extraction_summary"]["unsupported"] == 1

    evidence_file = EVIDENCE_BASE / "batch_408_official_source_evidence.json"
    assert evidence_file.exists()
    loaded = json.loads(evidence_file.read_text())
    assert loaded["batch_no"] == 408


# ── Error robustness ──

def test_discover_batches_network_error(monkeypatch, capsys):
    def mock_fetch(*args, **kwargs):
        raise NetworkError("模拟网络错误")
    monkeypatch.setattr("research_scripts.miit_new_car.discover_batches._fetch_jpage", mock_fetch)
    # Ensure no cache
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        cache_file = Path(td) / "discovered_batches.json"
        monkeypatch.setattr("research_scripts.miit_new_car.discover_batches.DISCOVERY_CACHE_FILE", cache_file)
        from research_scripts.miit_new_car.discover_batches import discover_batches
        result, source = discover_batches()
        assert result == []
        assert source == "network_unavailable"


def test_parse_batch_no_raw_dir():
    from research_scripts.miit_new_car.parse_products import parse_batch
    import pytest
    with pytest.raises(FileNotFoundError, match="原始数据目录"):
        parse_batch(batch_no=99999)
