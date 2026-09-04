"""Tests for Search capability: schemas, normalization, providers, cache, multi-query, CLI."""

import json
from unittest import mock

import pytest

from capabilities.search.schemas import (
    SearchRequest,
    SearchResponse,
    snippet_text,
    cache_key,
)
from capabilities.search.providers import get_provider
from capabilities.search.providers.mock_provider import MockSearchProvider
from capabilities.search.search_service import search, search_multi


def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("DOUBAO_SEARCH_GLOBAL_API_KEY", "test-key")
    monkeypatch.setenv("VOLC_SEARCH_BASE_URL", "https://test.example.com")


def _http_response(status=200, documents=None):
    resp = mock.Mock()
    resp.status_code = status
    resp.json.return_value = {
        "Result": {
            "Documents": documents
            or [
                {
                    "Title": "doc",
                    "Url": "http://example.com",
                    "Snippet": [{"Type": "text", "Text": "snippet"}],
                    "HostInfo": {"Hostname": "example.com"},
                    "DocumentInfo": {"PublishTime": "2026-01-01"},
                }
            ]
        }
    }
    return resp


# ── Snippet normalization ────────────────────────────────────────

class TestSnippetNormalization:
    def test_snippet_array_takes_text_only(self):
        snippet = [
            {"Type": "text", "Text": "小米 电机"},
            {"Type": "image", "Text": "ignored-image"},
            {"Type": "text", "Text": "供应商"},
        ]
        assert snippet_text(snippet) == "小米 电机 供应商"

    def test_snippet_string_passthrough(self):
        assert snippet_text("plain") == "plain"

    def test_snippet_empty(self):
        assert snippet_text([]) == ""
        assert snippet_text(None) == ""


# ── Cache key ────────────────────────────────────────────────────

class TestCacheKey:
    def test_key_changes_with_params(self):
        k1 = cache_key("小米", 10, 500, "doubao_global")
        k2 = cache_key("小米", 10, 800, "doubao_global")
        k3 = cache_key("小米", 5, 500, "doubao_global")
        k4 = cache_key("小米", 10, 500, "mock")
        assert k1 != k2
        assert k1 != k3
        assert k1 != k4
        assert k1 == cache_key("小米", 10, 500, "doubao_global")


# ── Mock provider / registry ─────────────────────────────────────

class TestMockProvider:
    def test_mock_search(self):
        provider = MockSearchProvider()
        resp = provider.search(SearchRequest(query="智己 LS6 上市"))
        assert resp.status == "success"
        assert resp.result_count == 1
        assert "智己 LS6" in resp.results[0]["title"]

    def test_get_provider_mock(self):
        assert isinstance(get_provider("mock"), MockSearchProvider)

    def test_get_provider_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown search provider"):
            get_provider("nonexistent")


# ── Service: missing env fails cleanly ───────────────────────────

class TestMissingEnv:
    def test_doubao_missing_env_fails(self, monkeypatch):
        monkeypatch.delenv("DOUBAO_SEARCH_GLOBAL_API_KEY", raising=False)
        monkeypatch.delenv("VOLC_SEARCH_BASE_URL", raising=False)
        resp = search(SearchRequest(query="q", use_cache=False))
        assert resp.status == "error"
        assert "DOUBAO_SEARCH_GLOBAL_API_KEY" in (resp.error or "")

    def test_mock_ignores_env(self, monkeypatch):
        monkeypatch.delenv("DOUBAO_SEARCH_GLOBAL_API_KEY", raising=False)
        resp = search(SearchRequest(query="q", provider="mock"))
        assert resp.status == "success"


# ── Doubao provider: retry / fail-fast / parse ───────────────────

class TestDoubaoProvider:
    @pytest.fixture(autouse=True)
    def _env_ok(self, monkeypatch):
        _env(monkeypatch, None)

    def test_200_success(self):
        with mock.patch("httpx.post", return_value=_http_response()):
            resp = search(SearchRequest(query="小米 电机", use_cache=False))
        assert resp.status == "success"
        assert resp.results[0]["title"] == "doc"
        assert resp.results[0]["snippet"] == "snippet"
        assert resp.results[0]["source"] == "example.com"
        assert resp.results[0]["rank"] == 1

    def test_401_fail_fast_no_retry(self):
        calls = {"n": 0}

        def fake_post(*a, **k):
            calls["n"] += 1
            return _http_response(status=401)

        with mock.patch("httpx.post", fake_post), mock.patch("time.sleep"):
            resp = search(SearchRequest(query="secret", retries=3, use_cache=False))
        assert resp.status == "error"
        assert "HTTP 401" in (resp.error or "")
        assert calls["n"] == 1

    def test_500_retries_then_fails(self):
        calls = {"n": 0}

        def fake_post(*a, **k):
            calls["n"] += 1
            return _http_response(status=503)

        with mock.patch("httpx.post", fake_post), mock.patch("time.sleep"):
            resp = search(SearchRequest(query="flaky", retries=3, use_cache=False))
        assert resp.status == "error"
        assert calls["n"] == 3

    def test_timeout_retries_then_fails(self):
        calls = {"n": 0}

        def fake_post(*a, **k):
            calls["n"] += 1
            raise mock.Mock(side_effect=httpx_timeout())

        with mock.patch("httpx.post", fake_post), mock.patch("time.sleep"):
            resp = search(SearchRequest(query="t", retries=2, use_cache=False))
        assert resp.status == "error"
        assert calls["n"] == 2


def httpx_timeout():
    import httpx
    return httpx.TimeoutException("timed out")


# ── Caching ──────────────────────────────────────────────────────

class TestCache:
    @pytest.fixture(autouse=True)
    def _env_ok(self, monkeypatch):
        _env(monkeypatch, None)

    def test_cache_hit_and_refresh(self, tmp_path):
        with mock.patch("httpx.post", lambda *a, **k: _http_response()):
            r1 = search(SearchRequest(query="小米", cache_dir=str(tmp_path), use_cache=True))
            assert r1.status == "success" and r1.cached is False
            r2 = search(SearchRequest(query="小米", cache_dir=str(tmp_path), use_cache=True))
            assert r2.cached is True
            r3 = search(SearchRequest(query="小米", cache_dir=str(tmp_path), use_cache=True, refresh=True))
            assert r3.cached is False

    def test_use_cache_false_never_writes(self, tmp_path):
        with mock.patch("httpx.post", lambda *a, **k: _http_response()):
            for _ in range(2):
                r = search(SearchRequest(query="q", cache_dir=str(tmp_path), use_cache=False))
                assert r.cached is False


# ── Multi-query isolation / result contract ──────────────────────

class TestMultiQuery:
    @pytest.fixture(autouse=True)
    def _env_ok(self, monkeypatch):
        _env(monkeypatch, None)

    def test_single_failure_isolated(self):
        calls = {"n": 0}

        def fake_post(*a, **k):
            calls["n"] += 1
            return _http_response(status=401) if calls["n"] == 1 else _http_response()

        with mock.patch("httpx.post", fake_post):
            results = search_multi(["bad", "good"], use_cache=False, retries=2)
        assert len(results) == 2
        assert results[0].status == "error"
        assert results[1].status == "success"

    def test_response_to_dict_json(self):
        r = SearchResponse(provider="mock", query="q", status="error", error="boom")
        d = r.to_dict()
        assert d["error"] == "boom"
        parsed = json.loads(r.to_json())
        assert parsed["status"] == "error"
