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
    status, method, text = _extract_doc_text(doc_path)
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

    evidence = _write_evidence(408, meta, diff_result, att_statuses, ext_results, products, diagnostics=[], product_list=[], discovery_source="cache")
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


# ═══════════════════════════════════════════════════════════════════
# V0.3.1: Attachment diagnostics
# ═══════════════════════════════════════════════════════════════════

def test_diagnose_url_normalize_relative():
    """Relative URL → absolute URL."""
    from research_scripts.miit_new_car.diagnose_attachment_urls import _normalize_url
    detail = "https://www.miit-eidc.org.cn/art/2026/6/10/art_1691_12455.html"
    result = _normalize_url("./attachments/abc.doc", detail)
    assert result.startswith("https://")
    assert "abc.doc" in result


def test_diagnose_url_normalize_already_absolute():
    from research_scripts.miit_new_car.diagnose_attachment_urls import _normalize_url
    url = "https://www.miit.gov.cn/datainfo/file.html"
    result = _normalize_url(url, "http://example.com")
    assert result == url


def test_diagnose_url_normalize_spaces():
    from research_scripts.miit_new_car.diagnose_attachment_urls import _normalize_url
    result = _normalize_url("https://example.com/a b c.doc", "http://x.com")
    assert " " not in result
    assert "a%20b%20c" in result or "abc" in result


def test_diagnose_url_normalize_entity():
    from research_scripts.miit_new_car.diagnose_attachment_urls import _normalize_url
    detail = "https://www.miit-eidc.org.cn/art/2026/6/10/art_1691_12455.html"
    result = _normalize_url("attachment&amp;file.doc", detail)
    assert result.startswith("https://")


def test_diagnose_url_javascript_skipped():
    from research_scripts.miit_new_car.diagnose_attachment_urls import _diagnose_single
    att = {"title": "bad link", "url": "javascript:void(0)"}
    result = _diagnose_single(att, 408, "http://x.com", "http://x.com")
    assert result["download_status"] == "failed"
    assert result["failure_type"] == "invalid_url"


def test_diagnose_url_unsupported_scheme():
    from research_scripts.miit_new_car.diagnose_attachment_urls import _diagnose_single
    att = {"title": "ftp link", "url": "ftp://files.example.com/doc.doc"}
    result = _diagnose_single(att, 408, "http://x.com", "http://x.com")
    assert result["download_status"] == "failed"
    assert result["failure_type"] == "unsupported_scheme"


def test_diagnose_failure_type_404(monkeypatch):
    from research_scripts.miit_new_car.diagnose_attachment_urls import _diagnose_single
    from research_scripts.miit_new_car.http_utils import NetworkError

    def mock_http_get(url, **kw):
        raise NetworkError("HTTP 404 Not Found", url=url)
    monkeypatch.setattr("research_scripts.miit_new_car.diagnose_attachment_urls.http_get", mock_http_get)

    att = {"title": "404 doc", "url": "https://example.com/404.doc"}
    result = _diagnose_single(att, 408, "http://x.com", "http://x.com")
    assert result["download_status"] == "failed"
    assert result["failure_type"] == "http_404"


def test_diagnose_failure_type_timeout(monkeypatch):
    from research_scripts.miit_new_car.diagnose_attachment_urls import _diagnose_single
    from research_scripts.miit_new_car.http_utils import NetworkError

    def mock_http_get(url, **kw):
        raise NetworkError("timed out", url=url)
    monkeypatch.setattr("research_scripts.miit_new_car.diagnose_attachment_urls.http_get", mock_http_get)

    att = {"title": "timeout", "url": "https://example.com/slow.doc"}
    result = _diagnose_single(att, 408, "http://x.com", "http://x.com")
    assert result["download_status"] == "failed"
    assert result["failure_type"] == "timeout"


def test_diagnose_empty_response(monkeypatch):
    from research_scripts.miit_new_car.diagnose_attachment_urls import _diagnose_single

    def mock_http_get(url, **kw):
        return b"", 200
    monkeypatch.setattr("research_scripts.miit_new_car.diagnose_attachment_urls.http_get", mock_http_get)

    att = {"title": "empty", "url": "https://example.com/empty.doc"}
    result = _diagnose_single(att, 408, "http://x.com", "http://x.com")
    assert result["download_status"] == "failed"
    assert result["failure_type"] == "content_too_small"


def test_diagnose_success_fields(monkeypatch):
    from research_scripts.miit_new_car.diagnose_attachment_urls import _diagnose_single

    def mock_http_get(url, **kw):
        return b"real content here", 200
    monkeypatch.setattr("research_scripts.miit_new_car.diagnose_attachment_urls.http_get", mock_http_get)

    att = {"title": "正常附件", "url": "https://example.com/doc.doc"}
    result = _diagnose_single(att, 408, "http://x.com", "http://x.com")
    assert result["download_status"] == "downloaded"
    assert result["http_status"] == 200
    assert result["content_length"] == 17
    assert result["domain"] == "example.com"
    assert result["strategy_used"] == "original_url"


# ═══════════════════════════════════════════════════════════════════
# V0.3.1: Check text extractors
# ═══════════════════════════════════════════════════════════════════

def test_check_text_extractors_structure(monkeypatch):
    from research_scripts.miit_new_car.check_text_extractors import check_extractors
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/textutil" if cmd == "textutil" else None)
    info = check_extractors()
    assert "platform" in info
    assert "extractors" in info
    assert "preferred_doc_extractor" in info
    assert info["extractors"]["textutil"]["available"] is True
    assert info["extractors"]["textutil"]["path"] == "/usr/bin/textutil"
    assert ".doc" in info["extractors"]["textutil"]["supports"]


def test_check_text_extractors_all_unavailable(monkeypatch):
    from research_scripts.miit_new_car.check_text_extractors import check_extractors
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    # Also mock Path.exists to disable macOS built-in textutil path check
    original_exists = Path.exists
    monkeypatch.setattr("pathlib.Path.exists", lambda self: False if "textutil" in str(self) else original_exists(self))
    info = check_extractors()
    assert info["preferred_doc_extractor"] is None
    for name, e in info["extractors"].items():
        assert e["available"] is False


# ═══════════════════════════════════════════════════════════════════
# V0.3.1: DOC text extraction with textutil mock
# ═══════════════════════════════════════════════════════════════════

def test_doc_extract_with_textutil(monkeypatch, tmp_path):
    """Mock textutil available and returns text successfully."""
    doc_path = tmp_path / "test.doc"
    doc_path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" * 10)

    import subprocess
    def mock_run(cmd, **kw):
        class Result:
            returncode = 0
            stdout = "智己 L6 纯电动轿车\n型号: ABC7000BEV"
            stderr = ""
        return Result()

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/textutil" if cmd == "textutil" else None)
    monkeypatch.setattr("subprocess.run", mock_run)

    from research_scripts.miit_new_car.extract_attachment_text import _extract_doc_text
    status, method, text = _extract_doc_text(doc_path)
    assert status == "success"
    assert method == "textutil"
    assert "智己" in text
    assert "ABC7000BEV" in text


# ═══════════════════════════════════════════════════════════════════
# V0.3.1: Extraction full text dumping
# ═══════════════════════════════════════════════════════════════════

def test_extraction_text_dump_html(tmp_path, monkeypatch):
    """Full text is written to extracted/text/batch_N/*.txt."""
    from research_scripts.miit_new_car.extract_attachment_text import extract_attachment_text

    raw_dir = tmp_path / "raw" / "batch_999"
    raw_dir.mkdir(parents=True)
    meta = {"batch_no": 999, "status": "publicity", "publish_date": "2026-06-10", "detail_url": "http://x"}
    (raw_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    att_dir = raw_dir / "attachments"
    att_dir.mkdir()
    (att_dir / "test.html").write_text("<html><body><p>产品列表</p><p>智己L6</p></body></html>", encoding="utf-8")

    monkeypatch.setattr("research_scripts.miit_new_car.extract_attachment_text.RAW_BASE", tmp_path / "raw")

    results = extract_attachment_text(batch_no=999)
    assert len(results) == 1
    r = results[0]
    assert r["extract_status"] == "success"
    assert r["extract_method"] == "html_strip"
    assert r["text_length"] > 0
    assert r["text_path"] != ""
    # JSON should NOT contain full text (only preview/path/length)
    assert len(r.get("text_preview", "")) <= 500

    txt_file = Path(r["text_path"])
    assert txt_file.exists()
    assert "智己L6" in txt_file.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════
# V0.3.1: Product list parser
# ═══════════════════════════════════════════════════════════════════

def test_product_list_from_html(tmp_path, monkeypatch):
    """HTML table → multiple product records."""
    from research_scripts.miit_new_car.parse_product_list import parse_product_list

    raw_dir = tmp_path / "raw" / "batch_888"
    raw_dir.mkdir(parents=True)
    meta = {"batch_no": 888, "status": "official", "publish_date": "2026-06-12", "detail_url": "http://x"}
    (raw_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    att_dir = raw_dir / "attachments"
    att_dir.mkdir()
    # _parse_html_rows uses fixed positions: [0]=enterprise, [1]=product_model, [2]=product_name
    html = """<html><body><h1>道路机动车辆生产企业及产品（第888批）</h1><table>
    <tr><th>企业名称</th><th>产品型号</th><th>产品名称</th><th>产品类别</th></tr>
    <tr><td>智己汽车科技有限公司</td><td>ABC7000BEV</td><td>纯电动多用途乘用车</td><td>新能源乘用车</td></tr>
    <tr><td>小米汽车科技有限公司</td><td>XMA7000BEV</td><td>纯电动轿车</td><td>新能源乘用车</td></tr>
    </table></body></html>"""
    (att_dir / "products.html").write_text(html, encoding="utf-8")

    monkeypatch.setattr("research_scripts.miit_new_car.parse_product_list.RAW_BASE", tmp_path / "raw")
    monkeypatch.setattr("research_scripts.miit_new_car.parse_product_list.EXTRACTED_BASE", tmp_path / "extracted")

    products = parse_product_list(batch_no=888)
    assert len(products) == 2

    zhiji = [p for p in products if "智己" in p["enterprise_name"]]
    assert len(zhiji) == 1
    assert zhiji[0]["product_model"] == "ABC7000BEV"
    assert zhiji[0]["brand"] == "智己"
    assert zhiji[0]["parse_confidence"] in ("high", "medium")

    xiaomi = [p for p in products if "小米" in p["enterprise_name"]]
    assert len(xiaomi) == 1
    assert xiaomi[0]["product_model"] == "XMA7000BEV"


def test_product_list_from_doc_text(tmp_path, monkeypatch):
    """Simulated DOC text → multiple product records via _parse_text_table."""
    from research_scripts.miit_new_car.parse_product_list import _parse_text_table

    text = (
        "企业名称    产品商标    产品名称        产品型号     产品类别\n"
        "智己汽车科技  智己     纯电动多用途乘用车  ABC7000BEV  新能源\n"
        "蔚来汽车    蔚来     纯电动轿车        ET7000      新能源\n"
    )
    records = _parse_text_table(text)
    assert len(records) == 2
    assert records[0]["enterprise_name"] == "智己汽车科技"
    assert records[0]["product_model"] == "ABC7000BEV"
    assert records[1]["enterprise_name"] == "蔚来汽车"
    assert records[1]["product_model"] == "ET7000"


def test_product_list_dedup(tmp_path, monkeypatch):
    """Duplicate records based on batch_no+enterprise+model+name are deduped."""
    from research_scripts.miit_new_car.parse_product_list import parse_product_list

    raw_dir = tmp_path / "raw" / "batch_777"
    raw_dir.mkdir(parents=True)
    meta = {"batch_no": 777, "status": "official", "publish_date": "2026-06-12", "detail_url": "http://x"}
    (raw_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    att_dir = raw_dir / "attachments"
    att_dir.mkdir()
    html = """<html><body><h1>道路机动车辆生产企业及产品（第777批）</h1><table>
    <tr><th>企业名称</th><th>产品名称</th><th>产品型号</th></tr>
    <tr><td>智己</td><td>纯电动轿车</td><td>L6</td></tr>
    <tr><td>智己</td><td>纯电动轿车</td><td>L6</td></tr>
    </table></body></html>"""
    (att_dir / "dup.html").write_text(html, encoding="utf-8")

    monkeypatch.setattr("research_scripts.miit_new_car.parse_product_list.RAW_BASE", tmp_path / "raw")
    monkeypatch.setattr("research_scripts.miit_new_car.parse_product_list.EXTRACTED_BASE", tmp_path / "extracted")

    products = parse_product_list(batch_no=777)
    assert len(products) == 1


def test_product_list_tax_exclusion(tmp_path, monkeypatch):
    """Tax directory attachments are excluded from product list."""
    from research_scripts.miit_new_car.parse_product_list import parse_product_list

    raw_dir = tmp_path / "raw" / "batch_666"
    raw_dir.mkdir(parents=True)
    meta = {"batch_no": 666, "status": "official", "publish_date": "2026-06-12", "detail_url": "http://x"}
    (raw_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    att_dir = raw_dir / "attachments"
    att_dir.mkdir()
    (att_dir / "normal.html").write_text("<html><body><h1>道路机动车辆生产企业及产品（第666批）</h1><table><tr><td>A</td><td>B</td></tr></table></body></html>", encoding="utf-8")
    (att_dir / "减免车辆购置税.html").write_text("减免车辆购置税\n税收目录内容", encoding="utf-8")
    (att_dir / "车船税优惠.html").write_text("车船税\n车船税内容", encoding="utf-8")

    monkeypatch.setattr("research_scripts.miit_new_car.parse_product_list.RAW_BASE", tmp_path / "raw")
    monkeypatch.setattr("research_scripts.miit_new_car.parse_product_list.EXTRACTED_BASE", tmp_path / "extracted")

    products = parse_product_list(batch_no=666)
    # Normal.html may or may not parse (minimal table), but tax files should be excluded
    tax_sources = [p for p in products if "购置税" in p.get("source_attachment", "")]
    assert len(tax_sources) == 0
    tax_sources2 = [p for p in products if "车船税" in p.get("source_attachment", "")]
    assert len(tax_sources2) == 0
    # All sources should be normal.html
    for p in products:
        assert p.get("source_attachment") == "normal.html"


def test_product_list_low_confidence(tmp_path, monkeypatch):
    """Fallback for unparseable content keeps low confidence."""
    from research_scripts.miit_new_car.parse_product_list import parse_product_list

    raw_dir = tmp_path / "raw" / "batch_555"
    raw_dir.mkdir(parents=True)
    meta = {"batch_no": 555, "status": "official", "publish_date": "2026-06-12", "detail_url": "http://x"}
    (raw_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    att_dir = raw_dir / "attachments"
    att_dir.mkdir()
    (att_dir / "no_table.txt").write_text("道路机动车辆生产企业及产品（第555批）\n无法解析的纯文本内容，没有表格结构", encoding="utf-8")

    monkeypatch.setattr("research_scripts.miit_new_car.parse_product_list.RAW_BASE", tmp_path / "raw")
    monkeypatch.setattr("research_scripts.miit_new_car.parse_product_list.EXTRACTED_BASE", tmp_path / "extracted")

    products = parse_product_list(batch_no=555)
    for p in products:
        assert p["parse_confidence"] == "low" or p["parse_confidence"] == "medium"


# ═══════════════════════════════════════════════════════════════════
# V0.3.1: Evidence layers
# ═══════════════════════════════════════════════════════════════════

def test_evidence_layers_three_tiers(tmp_path, monkeypatch):
    """Evidence JSON contains all three layers with correct counts."""
    from research_scripts.miit_new_car.monitor import _write_evidence

    EVIDENCE_BASE = tmp_path / "evidence"
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.EVIDENCE_BASE", EVIDENCE_BASE)

    meta = {
        "batch_no": 407, "status": "official", "publish_date": "2026-06-12",
        "detail_url": "http://example.com", "fetched_at": "2026-06-22T00:00:00Z",
        "detail_source": "remote",
    }
    diff_result = {"matched_products": [], "watchlist_matched": 0, "new_products": 0, "new_watchlist_matched": 0}
    att_statuses = [{"status": "downloaded"}] * 3
    ext_results = [{"extract_status": "success", "text_length": 100, "text_preview": "abc", "filename": "a.doc"}]
    products = [{"enterprise_name": "上汽集团"}]

    diagnostics = [
        {"download_status": "downloaded", "failure_type": None},
        {"download_status": "downloaded", "failure_type": None},
    ]
    product_list = [
        {"enterprise_name": "智己汽车", "brand": "智己", "product_model": "L6", "product_name": "纯电动轿车"},
        {"enterprise_name": "小米汽车", "brand": "小米", "product_model": "SU7", "product_name": "纯电动轿车"},
    ]

    evidence = _write_evidence(
        407, meta, diff_result, att_statuses, ext_results, products,
        diagnostics=diagnostics, product_list=product_list, discovery_source="remote",
    )

    layers = evidence.get("evidence_layers", {})
    assert "official_batch_evidence" in layers
    assert "official_attachment_evidence" in layers
    assert "official_product_list_evidence" in layers

    assert layers["official_batch_evidence"]["available"] is True
    assert layers["official_batch_evidence"]["batch_no"] == 407

    assert layers["official_attachment_evidence"]["downloaded_count"] == 2
    assert layers["official_attachment_evidence"]["failed_count"] == 0

    assert layers["official_product_list_evidence"]["available"] is True
    assert layers["official_product_list_evidence"]["record_count"] == 2


def test_evidence_layers_empty_product_list(tmp_path, monkeypatch):
    """When product_list is empty, official_product_list_evidence is unavailable."""
    from research_scripts.miit_new_car.monitor import _write_evidence

    EVIDENCE_BASE = tmp_path / "evidence"
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.EVIDENCE_BASE", EVIDENCE_BASE)

    meta = {"batch_no": 406, "status": "official", "publish_date": "2026-05-09",
            "detail_url": "http://x", "fetched_at": "", "detail_source": "remote"}
    diff_result = {"matched_products": [], "watchlist_matched": 0, "new_products": 0, "new_watchlist_matched": 0}
    att_statuses = []
    ext_results = []
    products = []

    evidence = _write_evidence(
        406, meta, diff_result, att_statuses, ext_results, products,
        diagnostics=[], product_list=[], discovery_source="cache",
    )
    layers = evidence.get("evidence_layers", {})
    assert layers["official_product_list_evidence"]["available"] is False
    assert layers["official_product_list_evidence"]["record_count"] == 0


# ═══════════════════════════════════════════════════════════════════
# V0.3.1: Monitor summary V0.3 fields
# ═══════════════════════════════════════════════════════════════════

def test_run_monitor_summary_v03_fields(monkeypatch):
    """Verify that run_monitor output has V0.3 fields (evidence_layers, product_list, diagnostics)."""
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
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.diagnose_attachments", lambda **kw: [])
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.parse_product_list", lambda **kw: [])
    monkeypatch.setattr("research_scripts.miit_new_car.monitor._write_evidence", lambda **kw: {"source_type": "official", "evidence_layers": {"official_batch_evidence": {"available": True}, "official_attachment_evidence": {"available": False}, "official_product_list_evidence": {"available": False}}})

    result = run_monitor(batch_no=408, download=False, state_update=False, discovery_source="remote")
    assert "diagnostics_total" in result
    assert "diagnostics_failed" in result
    assert "product_list_count" in result
    assert "evidence_layers" in result
    assert "structured_records" in result
    # Ensure no old "product_count" key remains
    assert "product_count" not in result
    # V0.3.2 fields
    assert "attachments_skipped" in result
    assert "product_list_quality" in result
    assert "product_list_enterprise_count" in result
    assert "product_list_model_count" in result


# ═══════════════════════════════════════════════════════════════════
# V0.3.2: Evidence schema/version guard
# ═══════════════════════════════════════════════════════════════════

def test_evidence_schema_validation_valid(tmp_path, monkeypatch):
    """Schema-valid evidence → reuse allowed."""
    from research_scripts.miit_new_car.monitor import _validate_evidence_schema

    evidence = {
        "schema_version": "miit_official_evidence.v0.3",
        "evidence_layers": {
            "official_batch_evidence": {"available": True},
            "official_attachment_evidence": {"available": True},
            "official_product_list_evidence": {"available": False},
        },
    }
    valid, reason = _validate_evidence_schema(evidence)
    assert valid is True
    assert reason == ""


def test_evidence_schema_validation_missing_version():
    from research_scripts.miit_new_car.monitor import _validate_evidence_schema

    evidence = {"batch_no": 408, "status": "official"}
    valid, reason = _validate_evidence_schema(evidence)
    assert valid is False
    assert "schema_version" in reason


def test_evidence_schema_validation_wrong_version():
    from research_scripts.miit_new_car.monitor import _validate_evidence_schema

    evidence = {
        "schema_version": "miit_official_evidence.v0.2",
        "evidence_layers": {"official_batch_evidence": {"available": True}},
    }
    valid, reason = _validate_evidence_schema(evidence)
    assert valid is False
    assert "v0.3" in reason


def test_evidence_schema_validation_missing_layers():
    from research_scripts.miit_new_car.monitor import _validate_evidence_schema

    evidence = {
        "schema_version": "miit_official_evidence.v0.3",
        "evidence_layers": {"official_batch_evidence": {"available": True}},
    }
    valid, reason = _validate_evidence_schema(evidence)
    assert valid is False
    assert "缺少" in reason


# ═══════════════════════════════════════════════════════════════════
# V0.3.2: Product list quality gate
# ═══════════════════════════════════════════════════════════════════

def test_product_list_quality_usable(tmp_path, monkeypatch):
    """product_list with enterprises and models → quality=usable."""
    from research_scripts.miit_new_car.monitor import _compute_product_list_quality

    pl = [
        {"enterprise_name": "智己", "product_model": "L6"},
        {"enterprise_name": "小米", "product_model": "SU7"},
    ]
    q = _compute_product_list_quality(pl)
    assert q["quality"] == "usable"
    assert q["enterprise_count"] == 2
    assert q["product_model_count"] == 2


def test_product_list_quality_enterprise_empty():
    from research_scripts.miit_new_car.monitor import _compute_product_list_quality

    pl = [
        {"enterprise_name": "", "product_model": "L6"},
        {"enterprise_name": "", "product_model": "SU7"},
    ]
    q = _compute_product_list_quality(pl)
    assert q["quality"] == "unusable"
    assert q["quality_reason"] == "enterprise_name_empty"
    assert q["enterprise_count"] == 0


def test_product_list_quality_model_empty():
    from research_scripts.miit_new_car.monitor import _compute_product_list_quality

    pl = [
        {"enterprise_name": "智己", "product_model": ""},
        {"enterprise_name": "小米", "product_model": ""},
    ]
    q = _compute_product_list_quality(pl)
    assert q["quality"] == "low_quality"
    assert q["quality_reason"] == "product_model_empty"


def test_product_list_quality_empty_list():
    from research_scripts.miit_new_car.monitor import _compute_product_list_quality

    q = _compute_product_list_quality([])
    assert q["quality"] == "empty"
    assert q["record_count"] == 0


# ═══════════════════════════════════════════════════════════════════
# V0.3.2: Evidence uses quality gate
# ═══════════════════════════════════════════════════════════════════

def test_evidence_layers_quality_gate(tmp_path, monkeypatch):
    """Low-quality product_list → official_product_list_evidence.available=False."""
    from research_scripts.miit_new_car.monitor import _write_evidence

    EVIDENCE_BASE = tmp_path / "evidence"
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.EVIDENCE_BASE", EVIDENCE_BASE)

    meta = {"batch_no": 407, "status": "official", "publish_date": "2026-06-12",
            "detail_url": "http://x", "fetched_at": "", "detail_source": "remote"}
    diff_result = {"matched_products": [], "watchlist_matched": 0, "new_products": 0, "new_watchlist_matched": 0}
    att_statuses = [{"status": "downloaded"}]
    ext_results = [{"extract_status": "success", "text_length": 100, "text_preview": "abc", "filename": "a.doc"}]
    products = [{"enterprise_name": "上汽集团"}]
    diagnostics = [{"download_status": "downloaded"}]
    # Low-quality product_list: enterprise empty
    product_list = [{"enterprise_name": "", "product_model": "L6"}]

    evidence = _write_evidence(407, meta, diff_result, att_statuses, ext_results, products,
                                diagnostics=diagnostics, product_list=product_list, discovery_source="remote")
    layers = evidence.get("evidence_layers", {})
    pl_layer = layers.get("official_product_list_evidence", {})
    assert pl_layer["available"] is False
    assert pl_layer["quality"] == "unusable"
    assert pl_layer["quality_reason"] == "enterprise_name_empty"
    assert pl_layer["record_count"] == 1


# ═══════════════════════════════════════════════════════════════════
# V0.3.2: Evidence schema version written
# ═══════════════════════════════════════════════════════════════════

def test_evidence_has_schema_version(tmp_path, monkeypatch):
    """Evidence JSON contains schema_version and generator_version."""
    from research_scripts.miit_new_car.monitor import _write_evidence

    EVIDENCE_BASE = tmp_path / "evidence"
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.EVIDENCE_BASE", EVIDENCE_BASE)

    meta = {"batch_no": 407, "status": "official", "publish_date": "2026-06-12",
            "detail_url": "http://x", "fetched_at": "", "detail_source": "remote"}
    diff_result = {"matched_products": [], "watchlist_matched": 0, "new_products": 0, "new_watchlist_matched": 0}
    att_statuses = [{"status": "downloaded"}]
    ext_results = [{"extract_status": "success", "text_length": 100, "text_preview": "abc", "filename": "a.doc"}]
    products = []
    diagnostics = []
    product_list = [{"enterprise_name": "智己", "product_model": "L6"}]

    evidence = _write_evidence(407, meta, diff_result, att_statuses, ext_results, products,
                                diagnostics=diagnostics, product_list=product_list, discovery_source="remote")
    assert evidence.get("schema_version") == "miit_official_evidence.v0.3"
    assert evidence.get("generator_version") == "miit_new_car_monitor.v0.3.2"


# ═══════════════════════════════════════════════════════════════════
# V0.3.3: Attachment type classification
# ═══════════════════════════════════════════════════════════════════

def test_classify_attachment_type_road():
    from research_scripts.miit_new_car.parse_product_list import classify_attachment_type
    assert classify_attachment_type("道路机动车辆生产企业及产品（第407批）", "") == "road_product_announcement"
    assert classify_attachment_type("附件1 道路机动车辆生产企业及产品", "") == "road_product_announcement"


def test_classify_attachment_type_vessel_tax():
    from research_scripts.miit_new_car.parse_product_list import classify_attachment_type
    assert classify_attachment_type("享受车船税减免优惠的节约能源 使用新能源汽车车型目录", "") == "vehicle_vessel_tax_catalog"
    assert classify_attachment_type("车船税优惠", "") == "vehicle_vessel_tax_catalog"


def test_classify_attachment_type_purchase_tax():
    from research_scripts.miit_new_car.parse_product_list import classify_attachment_type
    assert classify_attachment_type("减免车辆购置税的新能源汽车车型目录", "") == "purchase_tax_catalog"
    assert classify_attachment_type("车辆购置税", "") == "purchase_tax_catalog"


def test_classify_attachment_type_unknown():
    from research_scripts.miit_new_car.parse_product_list import classify_attachment_type
    assert classify_attachment_type("普通文档", "") == "unknown"


# ═══════════════════════════════════════════════════════════════════
# V0.3.3: Road product announcement state machine parser
# ═══════════════════════════════════════════════════════════════════

SEP07 = "\x07"


def test_road_state_machine_basic():
    """State machine parses 0x07-separated road announcement rows."""
    from research_scripts.miit_new_car.parse_product_list import _parse_road_product_announcement_text

    text = (
        f"序号{SEP07}商标{SEP07}产品名称{SEP07}产品型号{SEP07}{SEP07}{SEP07}上海汽车集团股份有限公司{SEP07}122{SEP07}智己牌{SEP07}纯电动轿车{SEP07}CSA7005\n"
        f"{SEP07}{SEP07}{SEP07}{SEP07}{SEP07}{SEP07}北京现代汽车有限公司{SEP07}11{SEP07}北京现代牌{SEP07}纯电动轿车{SEP07}BH7002\n"
    )
    records = _parse_road_product_announcement_text(text)
    saic = [r for r in records if "上海汽车" in r["enterprise_name"]]
    assert len(saic) >= 1
    assert saic[0]["enterprise_name"] == "上海汽车集团股份有限公司"
    assert "CSA7005" in saic[0]["product_model"]
    assert saic[0]["brand"] == "智己"

    bj = [r for r in records if "北京现代" in r["enterprise_name"]]
    assert len(bj) >= 1
    assert bj[0]["product_model"] == "BH7002"


def test_road_state_machine_multiple_models():
    """Multiple models separated by 、 are split into separate records."""
    from research_scripts.miit_new_car.parse_product_list import _parse_road_product_announcement_text

    text = (
        f"序号{SEP07}商标{SEP07}产品名称{SEP07}产品型号{SEP07}{SEP07}{SEP07}岚图汽车{SEP07}18{SEP07}岚图牌{SEP07}纯电动多用途乘用车{SEP07}EQ6501、EQ6522、EQ6521\n"
    )
    records = _parse_road_product_announcement_text(text)
    models = [r["product_model"] for r in records if r["product_model"]]
    assert len(models) >= 3
    assert "EQ6501" in models
    assert "EQ6522" in models
    assert "EQ6521" in models


def test_road_state_machine_enterprise_and_model_count():
    """Multi-enterprise, multi-model sample → enterprise_count > 0, model_count > 0."""
    from research_scripts.miit_new_car.parse_product_list import _parse_road_product_announcement_text

    text = (
        f"序号{SEP07}商标{SEP07}产品名称{SEP07}产品型号{SEP07}{SEP07}{SEP07}"
        f"北京现代汽车有限公司{SEP07}11{SEP07}北京现代牌{SEP07}纯电动轿车{SEP07}BH7002、BH7001、BH7000、BH7003"
        f"{SEP07}{SEP07}{SEP07}{SEP07}{SEP07}{SEP07}上海汽车集团股份有限公司{SEP07}122{SEP07}智己牌{SEP07}纯电动运动型乘用车{SEP07}CSA6492"
        f"{SEP07}{SEP07}{SEP07}{SEP07}{SEP07}{SEP07}肇庆小鹏新能源投资有限公司{SEP07}91{SEP07}小鹏牌{SEP07}纯电动多用途乘用车{SEP07}NHQ6490、NHQ6510\n"
    )
    records = _parse_road_product_announcement_text(text)
    enterprises = set(r["enterprise_name"] for r in records if r["enterprise_name"])
    models = set(r["product_model"] for r in records if r["product_model"])
    assert len(enterprises) >= 3
    assert len(models) >= 6
    assert "BH7002" in models
    assert "NHQ6490" in models


def test_road_state_machine_handles_product_name_wrap():
    """Product names are parsed correctly with trailing-char heuristic."""
    from research_scripts.miit_new_car.parse_product_list import _parse_road_product_announcement_text

    text = (
        f"序号{SEP07}商标{SEP07}产品名称{SEP07}产品型号{SEP07}{SEP07}{SEP07}金华青年{SEP07}01{SEP07}青年牌{SEP07}纯电动低地板城市客{SEP07}XMQ6106\n"
    )
    records = _parse_road_product_announcement_text(text)
    rec = [r for r in records if "金华" in r["enterprise_name"]]
    assert len(rec) >= 1
    assert "XMQ6106" in rec[0]["product_model"]


# ═══════════════════════════════════════════════════════════════════
# V1.0: HTML Image Attachment / Enterprise Admission Change
# ═══════════════════════════════════════════════════════════════════

# ── 1. Detail parser detects .html datainfo as html_image_attachment ──

def test_detail_parser_detects_html_datainfo_attachment():
    """Parent page detail parser recognizes datainfo/... .html as html_image_attachment."""
    from research_scripts.miit_new_car.fetch_batch import _DetailParser

    html = '''<html>
    <div class="_nk_wz_tit">第408批公示</div>
    <div id="zoom">
      附件1：
      <a href="https://www.miit.gov.cn/datainfo/dljdclscqyjcpggnfbdxzrclscqyjyzrqybgxxqd/art/2026/art_193720c0ad2b4e3990193efd73132d34.html"
         title="《道路机动车辆生产企业及产品公告》（第408批）拟发布的新准入车辆生产企业及已准入企业变更信息清单">
        附件1：道路机动车辆生产企业及产品公告
      </a>
    </div></html>'''

    parser = _DetailParser()
    parser.feed(html)

    assert len(parser.attachments) >= 1
    att = parser.attachments[0]
    assert att["source_format"] == "html_image_attachment"
    assert "/datainfo/" in att["url"]
    assert att["filename"].endswith(".html")


def test_detail_parser_keeps_doc_as_document_format():
    """Regular .doc/.docx attachments are still classified as document format."""
    from research_scripts.miit_new_car.fetch_batch import _DetailParser

    html = '''<html>
    <div class="_nk_wz_tit">第408批公示</div>
    <div id="zoom">
      <a href="https://example.com/file.doc">正常附件1</a>
      <a href="https://example.com/file.xlsx">正常附件2</a>
    </div></html>'''

    parser = _DetailParser()
    parser.feed(html)

    for att in parser.attachments:
        assert att["source_format"] == "document"


# ── 2. HTML datainfo URL not filtered out ──

def test_html_attachment_url_is_not_filtered():
    """.html URL in datainfo path should be kept as attachment, not filtered out."""
    from research_scripts.miit_new_car.fetch_batch import _DetailParser

    html = '''<html>
    <div class="_nk_wz_tit">第408批公示</div>
    <div id="zoom">
      <a href="https://www.miit.gov.cn/datainfo/xxx/art/2026/art_xxx.html"
         title="拟发布的新准入车辆生产企业及已准入企业变更信息清单">
        Test Attachment
      </a>
    </div></html>'''

    parser = _DetailParser()
    parser.feed(html)

    assert len(parser.attachments) == 1
    assert parser.attachments[0]["source_format"] == "html_image_attachment"


# ── 3. Source type detection from title keywords ──

def test_attachment_source_type_enterprise_admission():
    """Attachment title with enterprise admission keywords gets correct source_type."""
    from research_scripts.miit_new_car.fetch_batch import _DetailParser

    html = '''<html>
    <div class="_nk_wz_tit">第408批公示</div>
    <div id="zoom">
      <a href="https://www.miit.gov.cn/datainfo/xxx/art/2026/art_xxx.html"
         title="《道路机动车辆生产企业及产品公告》（第408批）拟发布的新准入车辆生产企业及已准入企业变更信息清单">
        附件1
      </a>
    </div></html>'''

    parser = _DetailParser()
    parser.feed(html)

    # Simulate what fetch_batch does after parsing
    from research_scripts.miit_new_car.fetch_batch import RE_ENTERPRISE_ADMISSION
    att = parser.attachments[0]
    title = att["title"]
    assert RE_ENTERPRISE_ADMISSION.search(title) is not None


# ── 4. Enterprise admission parser: HTML page with image content ──

def test_enterprise_admission_parse_image_page():
    """Parse an image-backed enterprise admission HTML page → partial parse_status."""
    from research_scripts.miit_new_car.enterprise_admission_parser import parse_enterprise_admission_page

    html = '''<html>
    <head><title>拟发布新准入车辆生产企业及已准入企业变更信息清单</title></head>
    <body>
    <h1>拟发布新准入车辆生产企业</h1>
    <p><img src="/cms_files/2026/06/enterprise_list.png" alt="企业名单"></p>
    <h2>已准入企业变更信息</h2>
    <p><img src="https://www.miit.gov.cn/cms_files/2026/06/change_info.jpg" alt="变更信息"></p>
    </body></html>'''

    result = parse_enterprise_admission_page(
        html=html,
        page_url="https://www.miit.gov.cn/datainfo/xxx/art/2026/art_xxx.html",
        parent_notice_url="https://www.miit-eidc.org.cn/art/2026/6/10/art_1691_12455.html",
        parent_notice_title="关于《道路机动车辆生产企业及产品公告》（第408批）拟发布内容的公示",
    )

    assert result["source_type"] == "enterprise_admission_change"
    assert result["source_format"] == "html_image_attachment"
    assert result["parse_status"] == "partial"
    assert result["quality"] == "low_quality"
    assert "image" in result["quality_reason"].lower()
    assert result["detail_asset_type"] == "image"
    assert len(result["detail_asset_urls"]) >= 2


def test_enterprise_admission_parse_text_page():
    """Parse a text-based (non-image) enterprise admission page → success parse_status."""
    from research_scripts.miit_new_car.enterprise_admission_parser import parse_enterprise_admission_page

    html = '''<html>
    <head><title>拟发布新准入车辆生产企业</title></head>
    <body>
    <h1>拟发布新准入车辆生产企业</h1>
    <p>上海汽车集团股份有限公司</p>
    <p>北京现代汽车有限公司</p>
    </body></html>'''

    result = parse_enterprise_admission_page(
        html=html,
        page_url="https://www.miit.gov.cn/datainfo/xxx",
    )

    assert result["parse_status"] == "success"
    assert result["quality"] == "usable"
    assert result["detail_asset_type"] == "text"


def test_enterprise_admission_parse_section_headings():
    """Section headings are correctly identified from the page."""
    from research_scripts.miit_new_car.enterprise_admission_parser import parse_enterprise_admission_page

    html = '''<html>
    <head><title>拟发布新准入车辆生产企业</title></head>
    <body>
    <h1>拟发布新准入车辆生产企业</h1>
    <h2>汽车生产企业</h2>
    <h2>摩托车生产企业</h2>
    <h3>已准入企业变更信息</h3>
    </body></html>'''

    result = parse_enterprise_admission_page(html=html)

    assert "拟发布新准入车辆生产企业" in result["section_headings_found"]
    assert "汽车生产企业" in result["section_headings_found"]
    assert "摩托车生产企业" in result["section_headings_found"]
    assert "已准入企业变更信息" in result["section_headings_found"]


def test_enterprise_admission_no_images_found():
    """Page with image indicators but no extractable URLs still reports partial status."""
    from research_scripts.miit_new_car.enterprise_admission_parser import parse_enterprise_admission_page

    html = '''<html>
    <head><title>拟发布新准入车辆生产企业</title></head>
    <body>
    <h1>企业准入</h1>
    <p>Image 详细信息请参见附件</p>
    </body></html>'''

    result = parse_enterprise_admission_page(html=html)

    assert result["parse_status"] == "partial"
    assert result["quality"] == "low_quality"


def test_enterprise_admission_has_image_content_detection():
    """has_image_content detects image-backed pages correctly."""
    from research_scripts.miit_new_car.enterprise_admission_parser import has_image_content

    assert has_image_content('<html><img src="test.png"></html>') is True
    assert has_image_content('<html><body>text only</body></html>') is False
    assert has_image_content('<html><a href="/cms_files/2026/file.jpg">pic</a></html>') is True
    assert has_image_content('<html>Image 详细信息</html>') is True


# ── 5. Enterprise admission excluded from product list ──

def test_classify_attachment_type_enterprise_admission_change():
    """Enterprise admission change text is classified correctly and excluded."""
    from research_scripts.miit_new_car.parse_product_list import classify_attachment_type

    assert classify_attachment_type("拟发布的新准入车辆生产企业及已准入企业变更信息清单") == "enterprise_admission_change"
    assert classify_attachment_type("新准入车辆生产企业") == "enterprise_admission_change"
    assert classify_attachment_type("已准入企业变更信息清单") == "enterprise_admission_change"
    assert classify_attachment_type("新增车辆生产企业") == "enterprise_admission_change"


def test_enterprise_admission_excluded_from_product_list(tmp_path, monkeypatch):
    """Enterprise admission attachment is excluded from product list parsing."""
    from research_scripts.miit_new_car.parse_product_list import parse_product_list

    raw_dir = tmp_path / "raw" / "batch_408"
    raw_dir.mkdir(parents=True)
    meta = {"batch_no": 408, "status": "publicity", "publish_date": "2026-06-10", "detail_url": "http://x"}
    (raw_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    att_dir = raw_dir / "attachments"
    att_dir.mkdir()
    (att_dir / "enterprise_admission.html").write_text(
        "<html><body><h1>拟发布的新准入车辆生产企业及已准入企业变更信息清单</h1></body></html>",
        encoding="utf-8",
    )
    (att_dir / "normal_products.html").write_text(
        '<html><body><h1>道路机动车辆生产企业及产品（第408批）</h1>'
        '<table><tr><th>企业名称</th><th>产品型号</th></tr>'
        '<tr><td>智己汽车</td><td>L6</td></tr></table></body></html>',
        encoding="utf-8",
    )

    monkeypatch.setattr("research_scripts.miit_new_car.parse_product_list.RAW_BASE", tmp_path / "raw")
    monkeypatch.setattr("research_scripts.miit_new_car.parse_product_list.EXTRACTED_BASE", tmp_path / "extracted")

    products = parse_product_list(batch_no=408)
    # Enterprise admission attachment should NOT produce any product records
    for p in products:
        assert "enterprise_admission" not in p.get("source_attachment", ""), \
            f"Enterprise admission attachment should not appear in product list: {p['source_attachment']}"
    # Normal products should still be parsed
    normal = [p for p in products if "智己" in p.get("enterprise_name", "")]
    assert len(normal) >= 1


# ── 6. Direct access failure preserves evidence ──

def test_fetch_html_datainfo_attachment_tracks_status(tmp_path, monkeypatch):
    """Fetching a datainfo HTML attachment should capture status correctly."""
    from research_scripts.miit_new_car.fetch_batch import fetch_batch

    def mock_http_get(url, **kw):
        if "datainfo" in url:
            return b"<html><body>Enterprise data</body></html>", 200
        if "detail" in url:
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
                {"url": "https://www.miit.gov.cn/datainfo/xxx/art/2026/art_xxx.html",
                 "title": "拟发布的新准入车辆生产企业及已准入企业变更信息清单",
                 "filename": "art_xxx.html",
                 "source_format": "html_image_attachment"},
            ]
        def feed(self, html): pass

    monkeypatch.setattr("research_scripts.miit_new_car.fetch_batch._DetailParser", MockDetailParser)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr("research_scripts.miit_new_car.fetch_batch.OUTPUT_BASE", Path(td))
        result = fetch_batch(batch_no=408, download=True)
        statuses = result.get("attachment_statuses", [])
        assert len(statuses) >= 1
        att = statuses[0]
        assert att["source_format"] == "html_image_attachment"
        assert att["source_type"] == "enterprise_admission_change"
        assert att["status"] == "downloaded" or att["status"] == "failed"


# ── 7. Fallback: partial parse when no OCR available ──

def test_enterprise_admission_partial_no_ocr():
    """Without OCR, image-backed content reports parse_status=partial."""
    from research_scripts.miit_new_car.enterprise_admission_parser import parse_enterprise_admission_page

    html = '''<html>
    <head><title>拟发布新准入车辆生产企业及已准入企业变更信息清单</title></head>
    <body>
    <h1>拟发布新准入车辆生产企业</h1>
    <img src="/cms_files/2026/enterprise_list.png" alt="">
    </body></html>'''

    result = parse_enterprise_admission_page(html=html)
    assert result["parse_status"] == "partial"
    assert result["quality"] == "low_quality"
    assert result["detail_asset_type"] == "image"
    assert len(result["detail_asset_urls"]) >= 1


# ── 8. Canonical section / metadata output ──

def test_enterprise_admission_canonical_section():
    """Canonical section is correctly identified from title."""
    from research_scripts.miit_new_car.enterprise_admission_parser import parse_enterprise_admission_page

    html = '''<html><head><title>拟发布新准入车辆生产企业及已准入企业变更信息清单</title></head><body>内容</body></html>'''

    result = parse_enterprise_admission_page(html=html)
    # Both appear in title; first in SECTION_CANDIDATES list wins
    assert result["canonical_section"] in ("拟发布新准入车辆生产企业", "已准入企业变更信息")
    assert "section_candidates" in result
    assert len(result["section_candidates"]) >= 5


# ── 9. Enterprise admission evidence layer in monitor ──

def test_evidence_layers_includes_enterprise_admission(tmp_path, monkeypatch):
    """Evidence JSON includes enterprise_admission_evidence layer when available."""
    from research_scripts.miit_new_car.monitor import _write_evidence

    EVIDENCE_BASE = tmp_path / "evidence"
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.EVIDENCE_BASE", EVIDENCE_BASE)

    meta = {"batch_no": 408, "status": "publicity", "publish_date": "2026-06-10",
            "detail_url": "http://example.com", "fetched_at": "", "detail_source": "remote"}
    diff_result = {"matched_products": [], "watchlist_matched": 0, "new_products": 0, "new_watchlist_matched": 0}
    att_statuses = [{"status": "downloaded"}]
    ext_results = []
    products = []
    diagnostics = []
    product_list = []

    ea_result = {
        "batch_no": 408,
        "source_type": "enterprise_admission_change",
        "source_format": "html_image_attachment",
        "parse_status": "partial",
        "quality": "low_quality",
        "canonical_section": "拟发布新准入车辆生产企业",
        "detail_asset_type": "image",
        "detail_asset_urls": ["https://www.miit.gov.cn/cms_files/2026/img.png"],
    }

    evidence = _write_evidence(
        408, meta, diff_result, att_statuses, ext_results, products,
        diagnostics=diagnostics, product_list=product_list,
        discovery_source="remote", enterprise_admission_result=ea_result,
    )

    layers = evidence.get("evidence_layers", {})
    assert "enterprise_admission_evidence" in layers
    ea_layer = layers["enterprise_admission_evidence"]
    assert ea_layer["available"] is True
    assert ea_layer["parse_status"] == "partial"
    assert ea_layer["quality"] == "low_quality"
    assert ea_layer["canonical_section"] == "拟发布新准入车辆生产企业"
    assert len(ea_layer["detail_asset_urls"]) == 1

    # enterprise_admission should also appear at top level
    assert "enterprise_admission" in evidence
    assert evidence["enterprise_admission"]["source_type"] == "enterprise_admission_change"


def test_evidence_layers_enterprise_admission_not_required(tmp_path, monkeypatch):
    """enterprise_admission_evidence layer is optional; schema is valid without it."""
    from research_scripts.miit_new_car.monitor import _write_evidence, _validate_evidence_schema

    EVIDENCE_BASE = tmp_path / "evidence"
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.EVIDENCE_BASE", EVIDENCE_BASE)

    meta = {"batch_no": 407, "status": "official", "publish_date": "2026-06-12",
            "detail_url": "http://x", "fetched_at": "", "detail_source": "remote"}
    diff_result = {"matched_products": [], "watchlist_matched": 0, "new_products": 0, "new_watchlist_matched": 0}
    att_statuses = [{"status": "downloaded"}]
    ext_results = []
    products = []
    diagnostics = []
    product_list = [{"enterprise_name": "智己", "product_model": "L6"}]

    evidence = _write_evidence(
        407, meta, diff_result, att_statuses, ext_results, products,
        diagnostics=diagnostics, product_list=product_list,
        discovery_source="remote",
    )

    valid, reason = _validate_evidence_schema(evidence)
    assert valid is True, f"Schema should be valid without enterprise_admission_evidence: {reason}"


# ── 10. Monitor summary includes enterprise admission info ──

def test_run_monitor_with_enterprise_admission(monkeypatch):
    """run_monitor processes enterprise admission attachments when present."""
    from research_scripts.miit_new_car.monitor import run_monitor

    def mock_fetch(*a, **kw):
        return {
            "batch_no": 408, "status": "publicity", "title": "关于第408批公示",
            "publish_date": "2026-06-10", "detail_url": "http://a",
            "fetched_at": "2026-06-22T00:00:00Z",
            "detail_source": "remote",
            "attachment_statuses": [
                {"status": "downloaded", "source_type": "enterprise_admission_change",
                 "source_format": "html_image_attachment",
                 "url": "http://mock/datainfo/art.html",
                 "local_path": "/tmp/mock/enterprise.html"},
            ],
        }
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.fetch_batch", mock_fetch)
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.parse_batch", lambda **kw: [])
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.diff_batch",
                        lambda **kw: {"watchlist_matched": 0, "new_products": 0, "new_watchlist_matched": 0, "matched_products": []})
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.extract_attachment_text", lambda **kw: [])
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.diagnose_attachments", lambda **kw: [])
    monkeypatch.setattr("research_scripts.miit_new_car.monitor.parse_product_list", lambda **kw: [])

    # Mock enterprise admission processing to avoid file I/O
    def mock_process(*a, **kw):
        return {
            "batch_no": 408,
            "source_type": "enterprise_admission_change",
            "source_format": "html_image_attachment",
            "parse_status": "partial",
            "quality": "low_quality",
            "canonical_section": "拟发布新准入车辆生产企业",
            "detail_asset_type": "image",
            "detail_asset_urls": ["http://mock/cms_files/img.png"],
            "section_headings_found": ["拟发布新准入车辆生产企业"],
        }
    monkeypatch.setattr(
        "research_scripts.miit_new_car.monitor.process_enterprise_admission",
        mock_process,
    )

    # Mock _write_evidence to return expected structure
    def mock_write_evidence(**kw):
        ea = kw.get("enterprise_admission_result")
        return {
            "source_type": "official",
            "evidence_layers": {
                "official_batch_evidence": {"available": True},
                "official_attachment_evidence": {"available": True},
                "official_product_list_evidence": {"available": False},
                "enterprise_admission_evidence": {
                    "available": True,
                    "parse_status": ea.get("parse_status") if ea else "",
                    "quality": ea.get("quality") if ea else "",
                    "canonical_section": ea.get("canonical_section") if ea else "",
                },
            },
            "enterprise_admission": ea or {},
        }
    monkeypatch.setattr("research_scripts.miit_new_car.monitor._write_evidence", mock_write_evidence)

    result = run_monitor(batch_no=408, download=False, state_update=False, discovery_source="remote")
    # Should not crash; summary should include enterprise_admission info
    assert result["batch_no"] == 408


# ═══════════════════════════════════════════════════════════════════
# V1.1: datainfo_resource_extractor
# ═══════════════════════════════════════════════════════════════════

MIIT_BASE = "https://www.miit.gov.cn"


def test_extractor_img_src():
    """<img src='/cms_files/xxx.png'> should be extracted as image_asset_url."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '<html><body><img src="/cms_files/2026/06/test_image.png"></body></html>'
    result = datainfo_resource_extractor(html, MIIT_BASE)

    assert len(result["image_asset_urls"]) >= 1
    urls = [u["url"] for u in result["image_asset_urls"]]
    assert any("test_image.png" in u for u in urls)
    assert any("cms_files/2026/06/test_image.png" in u for u in urls)
    # Source should be recorded
    assert any(u["source"] == "img.src" for u in result["image_asset_urls"])


def test_extractor_data_src():
    """<img data-src='...'> should be extracted as image_asset_url."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '<html><body><img data-src="/cms_files/2026/lazy_load.png"></body></html>'
    result = datainfo_resource_extractor(html, MIIT_BASE)

    assert len(result["image_asset_urls"]) >= 1
    urls = [u["url"] for u in result["image_asset_urls"]]
    assert any("lazy_load.png" in u for u in urls)
    # Source tracking
    assert any(u["source"] == "img.data-src" for u in result["image_asset_urls"])


def test_extractor_data_original():
    """<img data-original='...'> should be extracted as image_asset_url."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '<html><body><img data-original="/cms_files/2026/original_img.jpg"></body></html>'
    result = datainfo_resource_extractor(html, MIIT_BASE)

    assert len(result["image_asset_urls"]) >= 1
    sources = [u["source"] for u in result["image_asset_urls"]]
    assert "img.data-original" in sources


def test_extractor_data_url():
    """Elements with data-url should be extracted as image_asset_url."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '<html><body><div data-url="/cms_files/2026/data_url_img.jpg">content</div></body></html>'
    result = datainfo_resource_extractor(html, MIIT_BASE)

    assert len(result["image_asset_urls"]) >= 1
    sources = [u["source"] for u in result["image_asset_urls"]]
    assert "div.data-url" in sources


def test_extractor_js_embedded_url():
    """JS script content with /cms_files/xxx.jpg should be extracted via regex."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '''<html><head>
<script>
var imgUrl = "/cms_files/2026/js_embedded_image.jpg";
var fileUrl = "/cms_files/filemanager/1226/attachments/doc.pdf";
</script>
</head><body></body></html>'''
    result = datainfo_resource_extractor(html, MIIT_BASE)

    # script_asset_urls should contain both URLs
    script_urls = [u["url"] for u in result["script_asset_urls"]]
    assert any("js_embedded_image.jpg" in u for u in script_urls)
    assert any("doc.pdf" in u for u in script_urls)

    # cms_file_urls should also contain them
    cms_urls = [u["url"] for u in result["cms_file_urls"]]
    assert any("js_embedded_image.jpg" in u for u in cms_urls)
    assert any("doc.pdf" in u for u in cms_urls)


def test_extractor_iframe():
    """<iframe src='...'> should be extracted as iframe_urls."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '<html><body><iframe src="https://example.com/viewer/page.html"></iframe></body></html>'
    result = datainfo_resource_extractor(html, MIIT_BASE)

    assert len(result["iframe_urls"]) >= 1
    urls = [u["url"] for u in result["iframe_urls"]]
    assert "https://example.com/viewer/page.html" in urls
    assert any(u["source"] == "iframe.src" for u in result["iframe_urls"])


def test_extractor_image_marker_no_urls():
    """'Image 详细信息' with no URLs → extraction_status='needs_browser_network_trace'."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '<html><head><title>Test</title></head><body><p>Image 详细信息请参见附件</p></body></html>'
    result = datainfo_resource_extractor(html, MIIT_BASE)

    assert result["extraction_status"] == "needs_browser_network_trace"
    assert "Image detail marker" in result["extraction_reason"]
    # No URLs should be found
    assert len(result["image_asset_urls"]) == 0
    assert len(result["linked_asset_urls"]) == 0
    assert len(result["iframe_urls"]) == 0
    assert len(result["cms_file_urls"]) == 0


def test_extractor_empty_html():
    """Empty HTML → extraction_status='needs_browser_network_trace'."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    result = datainfo_resource_extractor("", MIIT_BASE)

    assert result["extraction_status"] == "needs_browser_network_trace"
    assert "empty" in result["extraction_reason"]


def test_extractor_relative_url_resolution():
    """Relative URLs should resolve to absolute using base_url."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '<html><body><img src="/cms_files/test.png"></body></html>'
    result = datainfo_resource_extractor(html, "https://www.miit.gov.cn")

    assert len(result["image_asset_urls"]) >= 1
    url = result["image_asset_urls"][0]["url"]
    assert url == "https://www.miit.gov.cn/cms_files/test.png"


def test_extractor_linked_assets():
    """<a href='...'> should be extracted as linked_asset_urls."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '''<html><body>
<a href="https://www.miit.gov.cn/datainfo/other/page.html">Related Page</a>
<a href="/cms_files/2026/doc.pdf">PDF Document</a>
</body></html>'''
    result = datainfo_resource_extractor(html, MIIT_BASE)

    assert len(result["linked_asset_urls"]) >= 2
    urls = [u["url"] for u in result["linked_asset_urls"]]
    assert any("datainfo/other/page.html" in u for u in urls)
    assert any("doc.pdf" in u for u in urls)
    # All should have source a.href
    assert all(u["source"] == "a.href" for u in result["linked_asset_urls"])


def test_extractor_script_webfile():
    """Script with webfile/upload references should be extracted."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '''<html><head><script>
var f1 = "/webfile/2026/data.json";
var f2 = "/upload/images/photo.png";
</script></head><body></body></html>'''
    result = datainfo_resource_extractor(html, MIIT_BASE)

    script_urls = [u["url"] for u in result["script_asset_urls"]]
    assert any("webfile/2026/data.json" in u for u in script_urls)
    assert any("upload/images/photo.png" in u for u in script_urls)


def test_extractor_api_candidate():
    """JSON API URLs in script should be extracted as api_candidate_urls."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '''<html><head><script>
var api = "https://api.miit.gov.cn/v1/data/2026/batch.json";
</script></head><body></body></html>'''
    result = datainfo_resource_extractor(html, MIIT_BASE)

    api_urls = [u["url"] for u in result["api_candidate_urls"]]
    assert any("batch.json" in u for u in api_urls)


def test_extractor_section_candidates():
    """Section candidates should be extracted from HTML content."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '<html><body><p>拟发布新准入车辆生产企业</p><p>汽车生产企业</p></body></html>'
    result = datainfo_resource_extractor(html, MIIT_BASE)

    assert "拟发布新准入车辆生产企业" in result["section_candidates"]
    assert "汽车生产企业" in result["section_candidates"]


def test_extractor_source_title():
    """Page title should be extracted from <title> tag."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '<html><head><title>拟发布新准入车辆生产企业及已准入企业变更信息清单</title></head><body></body></html>'
    result = datainfo_resource_extractor(html, MIIT_BASE)

    assert "拟发布新准入车辆生产企业" in result["source_title"]
    assert "已准入企业变更信息清单" in result["source_title"]


def test_extractor_dedup():
    """Duplicate URLs should be deduplicated."""
    from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor

    html = '''<html><body>
<img src="/cms_files/2026/same.png">
<img data-src="/cms_files/2026/same.png">
<a href="https://www.miit.gov.cn/cms_files/2026/same.png">link</a>
</body></html>'''
    result = datainfo_resource_extractor(html, MIIT_BASE)

    # image_asset_urls should dedup the same URL from src and data-src
    urls = [u["url"] for u in result["image_asset_urls"] if "same.png" in u["url"]]
    assert len(urls) == 1, "Duplicate image URLs should be deduplicated"


def test_extractor_parse_enterprise_admission_integration():
    """parse_enterprise_admission_page should include V1.1 extraction fields."""
    from research_scripts.miit_new_car.enterprise_admission_parser import parse_enterprise_admission_page

    html = '''<html>
<head><title>拟发布新准入车辆生产企业</title></head>
<body>
<h1>拟发布新准入车辆生产企业</h1>
<img src="/cms_files/2026/img1.png" alt="pic1">
<img data-src="/cms_files/2026/img2.png" alt="pic2">
<a href="https://www.miit.gov.cn/datainfo/other/page.html">Link</a>
<script>var x = "/cms_files/2026/embedded.jpg";</script>
</body></html>'''
    result = parse_enterprise_admission_page(html, page_url=MIIT_BASE)

    # V1.1 fields should exist
    assert "image_asset_urls" in result
    assert "linked_asset_urls" in result
    assert "script_asset_urls" in result
    assert "cms_file_urls" in result
    assert "extraction_status" in result
    assert "extraction_reason" in result

    # image_asset_urls should have both src and data-src
    assert len(result["image_asset_urls"]) >= 2
    sources = set(u["source"] for u in result["image_asset_urls"])
    assert "img.src" in sources
    assert "img.data-src" in sources

    # linked_asset_urls should have the anchor
    assert len(result["linked_asset_urls"]) >= 1

    # script_asset_urls should have the embedded image
    assert len(result["script_asset_urls"]) >= 1
    script_urls = [u["url"] for u in result["script_asset_urls"]]
    assert any("embedded.jpg" in u for u in script_urls)

    # Backward-compatible fields should still exist
    assert result["source_type"] == "enterprise_admission_change"
    assert "detail_asset_urls" in result
    assert "section_candidates" in result
    assert "parse_status" in result
    assert "quality" in result


def test_extractor_resolve_url_helper():
    """_resolve_url should handle various URL formats."""
    from research_scripts.miit_new_car.enterprise_admission_parser import _resolve_url

    base = "https://www.miit.gov.cn"

    # Absolute URL unchanged
    assert _resolve_url("https://other.com/file.jpg", base) == "https://other.com/file.jpg"

    # Protocol-relative URL
    assert _resolve_url("//cdn.miit.gov.cn/file.jpg", base) == "https://cdn.miit.gov.cn/file.jpg"

    # Root-relative URL
    assert _resolve_url("/cms_files/img.png", base) == "https://www.miit.gov.cn/cms_files/img.png"

    # Relative URL
    result = _resolve_url("img.png", "https://www.miit.gov.cn/datainfo/page.html")
    assert result.endswith("/img.png")

    # Empty URL
    assert _resolve_url("", base) == ""

    # No base URL
    assert _resolve_url("/cms_files/img.png", "") == "/cms_files/img.png"
