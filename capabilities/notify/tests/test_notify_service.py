"""Tests for Notify capability: schemas, envelope builders, providers, dry-run, CLI."""

import json
import os
from unittest.mock import patch

import pytest

from capabilities.notify.schemas import (
    NotifyRequest,
    NotifyResult,
    build_text,
    build_interactive_card,
)
from capabilities.notify.providers import get_provider
from capabilities.notify.providers.mock_provider import MockNotifyProvider
from capabilities.notify.notify_service import notify


# ── Envelope Builders ───────────────────────────────────────────

class TestEnvelopeBuilders:
    def test_build_text_payload(self):
        payload = build_text("hello")
        assert payload == {"msg_type": "text", "content": {"text": "hello"}}

    def test_build_interactive_card_shape(self):
        payload = build_interactive_card("标题", "**bold** body", note="来源口径")
        assert payload["msg_type"] == "interactive"
        card = payload["card"]
        assert card["header"]["title"]["content"] == "标题"
        assert card["header"]["template"] == "blue"
        elements = card["elements"]
        assert elements[0] == {"tag": "div", "text": {"tag": "lark_md", "content": "**bold** body"}}
        # hr + note appended
        assert any(e.get("tag") == "note" for e in elements)

    def test_build_interactive_card_no_note(self):
        payload = build_interactive_card("t", "body")
        assert all(e.get("tag") != "note" for e in payload["card"]["elements"])

    def test_request_payload_prefers_raw(self):
        raw = {"msg_type": "text", "content": {"text": "raw"}}
        request = NotifyRequest(title="t", body="b", raw_payload=raw)
        assert request.payload() == raw

    def test_request_payload_plain_text_when_body_only(self):
        request = NotifyRequest(body="only text")
        assert request.payload() == build_text("only text")


# ── Result Contract ─────────────────────────────────────────────

class TestNotifyResult:
    def test_to_dict(self):
        r = NotifyResult(provider="mock", channel="feishu_webhook", status="sent", ok=True)
        d = r.to_dict()
        assert d["provider"] == "mock"
        assert d["ok"] is True

    def test_to_json(self):
        r = NotifyResult(provider="mock", channel="feishu_webhook", status="failed", ok=False, error="boom")
        parsed = json.loads(r.to_json())
        assert parsed["status"] == "failed"
        assert parsed["error"] == "boom"


# ── Mock Provider ───────────────────────────────────────────────

class TestMockProvider:
    def test_mock_send(self):
        provider = MockNotifyProvider()
        result = provider.send(NotifyRequest(title="t", body="b"))
        assert result.status == "sent"
        assert result.ok is True

    def test_mock_dry_run(self):
        provider = MockNotifyProvider()
        result = provider.send(NotifyRequest(title="t", body="b", dry_run=True))
        assert result.status == "dry_run"
        assert result.ok is True
        assert result.payload is not None
        assert result.payload["msg_type"] == "interactive"

    def test_get_provider_mock(self):
        provider = get_provider("mock")
        assert isinstance(provider, MockNotifyProvider)

    def test_get_provider_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown notify provider"):
            get_provider("nonexistent")


# ── Service level ───────────────────────────────────────────────

class TestService:
    def test_notify_mock(self):
        result = notify(title="t", body="b", provider_name="mock")
        assert result.ok is True
        assert result.status == "sent"

    def test_notify_dry_run_uses_mock_default_safe(self):
        # dry_run on mock never touches network
        result = notify(title="t", body="b", provider_name="mock", dry_run=True)
        assert result.status == "dry_run"

    def test_feishu_webhook_missing_env_fails_cleanly(self, monkeypatch):
        monkeypatch.delenv("FS_WEBHOOK_URL", raising=False)
        result = notify(title="t", body="b", provider_name="feishu_webhook")
        assert result.status == "failed"
        assert result.ok is False
        assert result.error is not None
        assert "FS_WEBHOOK_URL" in result.error

    def test_feishu_webhook_dry_run_no_network(self):
        result = notify(title="t", body="b", provider_name="feishu_webhook", dry_run=True)
        assert result.status == "dry_run"
        assert result.ok is True
        assert result.payload is not None
        assert result.payload["msg_type"] == "interactive"

    def test_feishu_webhook_success(self):
        # Fake a successful webhook response through httpx
        payload = build_interactive_card("t", "b")
        with patch("httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status.return_value = None
            mock_post.return_value.json.return_value = {"code": 0}
            result = notify(title="t", body="b", provider_name="feishu_webhook", webhook_url="http://x")
        assert result.status == "sent"
        assert result.ok is True
        mock_post.assert_called_once()
        sent_payload = mock_post.call_args.kwargs["json"]
        assert sent_payload == payload


# ── CLI ─────────────────────────────────────────────────────────

class TestCli:
    def test_cli_dry_run_mock(self, capsys):
        from capabilities.notify.notify_service import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--provider", "mock", "--title", "t", "--body", "b", "--dry-run"])
        assert args.dry_run is True
