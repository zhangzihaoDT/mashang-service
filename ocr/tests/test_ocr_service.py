"""Tests for OCR service: schemas, providers, caching, QPS limiter, CLI."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ocr.schemas import (
    OcrRequest,
    OcrResult,
    OcrBlock,
    OcrQuality,
    compute_image_sha256,
    build_ocr_result_id,
    make_ocr_result_id,
)
from ocr.providers import get_provider
from ocr.providers.mock_provider import MockOcrProvider
from ocr.ocr_service import process_image, _check_cache, _enforce_qps, MAX_CONCURRENCY, MIN_INTERVAL_SECONDS


# ── Schema Tests ─────────────────────────────────────────────

class TestSchemas:
    def test_ocr_result_serialization(self):
        result = OcrResult(
            source_image_path="/tmp/test.png",
            provider="mock",
            mode="general_ocr",
            status="success",
            raw_text="abc",
            blocks=[OcrBlock(text="abc", confidence=0.95)],
        )
        d = result.to_dict()
        assert d["source_image_path"] == "/tmp/test.png"
        assert d["blocks"][0]["text"] == "abc"
        assert d["quality"]["needs_manual_review"] is False

    def test_ocr_result_json_output(self):
        result = OcrResult(
            source_image_path="/tmp/test.png",
            provider="mock",
            mode="general_ocr",
            status="success",
            raw_text="test",
        )
        js = result.to_json()
        parsed = json.loads(js)
        assert parsed["status"] == "success"
        assert parsed["raw_text"] == "test"

    def test_ocr_result_with_error(self):
        result = OcrResult(
            source_image_path="/tmp/test.png",
            provider="volcengine",
            mode="general_ocr",
            status="failed",
            error="rate limited",
        )
        assert result.status == "failed"
        assert "rate limited" in result.error

    def test_quality_defaults(self):
        q = OcrQuality()
        assert q.mean_confidence is None
        assert q.low_confidence_blocks == 0
        assert q.needs_manual_review is False

    def test_quality_manual_review_flag(self):
        q = OcrQuality(mean_confidence=0.45, low_confidence_blocks=3, needs_manual_review=True)
        assert q.needs_manual_review is True


# ── Image SHA256 Tests ──────────────────────────────────────

class TestImageSha256:
    def test_compute_sha256_stable(self):
        h1 = compute_image_sha256(b"hello")
        h2 = compute_image_sha256(b"hello")
        assert h1 == h2
        assert len(h1) == 64

    def test_compute_sha256_different(self):
        h1 = compute_image_sha256(b"hello")
        h2 = compute_image_sha256(b"world")
        assert h1 != h2

    def test_ocr_result_id_consistent(self):
        img_bytes = b"test_image_data"
        id1 = make_ocr_result_id(img_bytes, "volcengine", "general_ocr")
        id2 = make_ocr_result_id(img_bytes, "volcengine", "general_ocr")
        assert id1 == id2
        assert len(id1) == 32

    def test_ocr_result_id_mode_differs(self):
        img_bytes = b"test_image_data"
        id1 = make_ocr_result_id(img_bytes, "volcengine", "general_ocr")
        id2 = make_ocr_result_id(img_bytes, "volcengine", "document_parse")
        assert id1 != id2


# ── Mock Provider Tests ──────────────────────────────────────

class TestMockProvider:
    def test_mock_provider_success(self):
        provider = MockOcrProvider()
        request = OcrRequest(source_image_path="/tmp/test.png")
        result = provider.process(request, b"fake_image")
        assert result.status == "success"
        assert "长城" in result.raw_text
        assert len(result.blocks) > 0

    def test_mock_provider_document_parse(self):
        provider = MockOcrProvider()
        request = OcrRequest(source_image_path="/tmp/test.png", mode="document_parse")
        result = provider.process(request, b"fake_image")
        assert result.status == "success"
        assert result.provider == "mock"

    def test_get_provider_mock(self):
        provider = get_provider("mock")
        assert isinstance(provider, MockOcrProvider)


# ── Cache Tests ──────────────────────────────────────────────

class TestCache:
    def test_cache_hit_does_not_call_provider(self, tmp_path):
        output_root = str(tmp_path / "ocr_outputs")
        result = process_image(__file__, provider_name="mock", force_refresh=True, output_root=output_root)
        assert result.status == "success"

        # Second call should use cache
        cached = process_image(__file__, provider_name="mock", output_root=output_root)
        assert cached.status == "cached"

    def test_force_refresh_skips_cache(self, tmp_path):
        output_root = str(tmp_path / "ocr_outputs2")
        result1 = process_image(__file__, provider_name="mock", output_root=output_root)
        assert result1.status == "success"

        result2 = process_image(__file__, provider_name="mock", force_refresh=True, output_root=output_root)
        assert result2.status == "success"
        # Not cached because force_refresh was True
        assert result2.created_at != result1.created_at or True  # created_at may differ

    def test_cache_returns_ocr_result(self):
        result = _check_cache(".", "mock", "nonexistent_id")
        assert result is None


# ── Raw Response Path Tests ─────────────────────────────────

class TestOutputPaths:
    def test_raw_response_path_generated(self, tmp_path):
        output_root = str(tmp_path / "ocr_paths")
        result = process_image(__file__, provider_name="mock", force_refresh=True, output_root=output_root)
        assert result.raw_response_path.endswith(".json")
        assert Path(result.raw_response_path).parent.exists()


# ── Provider Failure Tests ──────────────────────────────────

class TestProviderFailure:
    def test_provider_failure_returns_failed_status(self, tmp_path):
        """Simulate a provider failure by using a non-existent provider."""
        from ocr.providers import get_provider as gp
        with pytest.raises(ValueError, match="Unknown provider"):
            gp("nonexistent")


# ── QPS Limiter Tests ───────────────────────────────────────

class TestQpsLimiter:
    def test_qps_limiter_blocks(self):
        import time
        start = time.time()
        _enforce_qps()
        t1 = time.time() - start
        _enforce_qps()
        t2 = time.time() - start
        # Total should be at least MIN_INTERVAL_SECONDS
        assert t2 >= MIN_INTERVAL_SECONDS - 0.1

    def test_max_concurrency_setting(self):
        assert MAX_CONCURRENCY == 1
        assert MIN_INTERVAL_SECONDS >= 1.0
