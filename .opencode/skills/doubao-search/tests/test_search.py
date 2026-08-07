#!/usr/bin/env python3
"""doubao-search 底层搜索原语测试。

覆盖：
  - Snippet 数组归一化
  - cache key 随 snippet_length 变化
  - cache 命中 / --refresh
  - multi-query 单查询失败隔离（partial results）
  - 4xx fail fast（401 不重试）
"""

import argparse
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import search as ds  # noqa: E402


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    """隔离环境变量与缓存目录，避免污染真实环境。"""
    monkeypatch.setenv("DOUBAO_SEARCH_GLOBAL_API_KEY", "test-key")
    monkeypatch.setenv("VOLC_SEARCH_BASE_URL", "https://test.example.com")
    monkeypatch.setattr(ds, "CACHE_DIR", tmp_path)
    yield


def _make_args(queries, **kwargs):
    """构造 argparse Namespace。"""
    defaults = {
        "query": queries,
        "limit": 10,
        "snippet_length": 500,
        "timeout": 30,
        "retries": 3,
        "cache_ttl": ds.DEFAULT_TTL,
        "refresh": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ── 1. Snippet 数组归一化 ─────────────────────────────────────────

def test_snippet_array_normalization():
    snippet = [
        {"Type": "text", "Text": "小米 电机"},
        {"Type": "image", "Text": "ignored-image"},
        {"Type": "text", "Text": "供应商"},
    ]
    assert ds._snippet_text(snippet) == "小米 电机 供应商"


def test_snippet_string_passthrough():
    assert ds._snippet_text("plain text") == "plain text"


def test_snippet_empty():
    assert ds._snippet_text([]) == ""
    assert ds._snippet_text(None) == ""


# ── 2. cache key 随 snippet_length 变化 ───────────────────────────

def test_cache_key_changes_with_snippet_length():
    k1 = ds.cache_key("小米", 10, 500)
    k2 = ds.cache_key("小米", 10, 800)
    k3 = ds.cache_key("小米", 5, 500)
    assert k1 != k2, "snippet_length 不同 cache key 必须不同"
    assert k1 != k3, "limit 不同 cache key 必须不同"
    assert k1 == ds.cache_key("小米", 10, 500), "同参数必须命中同 key"


# ── 3. cache 命中 / --refresh ──────────────────────────────────────

def _mock_http_response(status=200, documents=None):
    resp = mock.Mock()
    resp.status_code = status
    resp.json.return_value = {
        "Result": {
            "Documents": documents or [
                {"Title": "doc", "Url": "http://example.com",
                 "Snippet": [{"Type": "text", "Text": "snippet"}],
                 "HostInfo": {"Hostname": "example.com"},
                 "DocumentInfo": {"PublishTime": "2026-01-01"}}
            ]
        }
    }
    return resp


def test_cache_hit_and_refresh(monkeypatch):
    monkeypatch.setattr(ds.requests, "post", lambda *a, **k: _mock_http_response())

    args = _make_args(["小米"], refresh=False)
    first = ds.run_all(args)[0]
    assert first["status"] == "success"
    assert first["cached"] is False

    second = ds.run_all(args)[0]
    assert second["cached"] is True, "同参数第二次应命中缓存"

    refresh_args = _make_args(["小米"], refresh=True)
    third = ds.run_all(refresh_args)[0]
    assert third["cached"] is False, "--refresh 应绕过缓存"


# ── 4. multi-query 单查询失败隔离 ─────────────────────────────────

def test_multi_query_partial_failure(monkeypatch):
    def fake_post(*args, **kwargs):
        return _mock_http_response()

    # 第一个查询抛 4xx（fail fast），第二个正常
    call_count = {"n": 0}

    def fake_post_with_failure(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            resp = mock.Mock()
            resp.status_code = 401
            return resp
        return _mock_http_response()

    monkeypatch.setattr(ds.requests, "post", fake_post_with_failure)

    args = _make_args(["bad-query", "good-query"], refresh=True)
    results = ds.run_all(args)

    assert len(results) == 2
    assert results[0]["status"] == "error"
    assert "HTTP 401" in results[0]["error"]
    assert results[0]["results"] == []
    assert results[1]["status"] == "success"
    assert results[1]["results"][0]["title"] == "doc"
    assert call_count["n"] == 2, "失败查询与成功查询各调用一次"


# ── 5. 4xx fail fast（不重试）─────────────────────────────────────

def test_401_does_not_retry(monkeypatch):
    calls = {"n": 0}

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        resp = mock.Mock()
        resp.status_code = 401
        return resp

    monkeypatch.setattr(ds.requests, "post", fake_post)

    with pytest.raises(ds.DoubaoSearchError) as exc_info:
        ds.search("secret query", 10, 500, 30, retries=3)

    assert "HTTP 401" in str(exc_info.value)
    assert calls["n"] == 1, "4xx 必须 fail fast，不重试"


def test_500_retries_then_fails(monkeypatch):
    calls = {"n": 0}

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        resp = mock.Mock()
        resp.status_code = 503
        return resp

    monkeypatch.setattr(ds.requests, "post", fake_post)

    with pytest.raises(ds.DoubaoSearchError):
        ds.search("flaky", 10, 500, 30, retries=3)

    assert calls["n"] == 3, "5xx 应重试 retries 次后失败"


def test_200_success(monkeypatch):
    monkeypatch.setattr(ds.requests, "post",
                        lambda *a, **k: _mock_http_response())
    results = ds.search("小米 电机", 10, 500, 30, retries=3)
    assert len(results) == 1
    assert results[0]["title"] == "doc"
    assert results[0]["snippet"] == "snippet"
    assert results[0]["source"] == "example.com"
    assert results[0]["rank"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
