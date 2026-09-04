"""Notify base capability — schemas, envelope builders, and result contract.

A domain-agnostic push primitive: text / interactive card → a messaging channel
(current provider: Feishu group webhook). Business card content assembly stays
with the caller; this capability provides transport + a generic envelope builder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


# ── Envelope builders ───────────────────────────────────────────

def build_text(text: str) -> dict:
    """Feishu plain-text message payload."""
    return {"msg_type": "text", "content": {"text": text}}


def build_interactive_card(
    title: str,
    body_markdown: str,
    note: Optional[str] = None,
    header_template: str = "blue",
) -> dict:
    """Generic Feishu interactive card envelope (blue header + lark_md body + optional note).

    Content assembly beyond the generic envelope is the caller's responsibility;
    pass a fully built payload via NotifyRequest.raw_payload when needed.
    """
    elements: list[dict] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": body_markdown}},
    ]
    if note:
        elements.append({"tag": "hr"})
        elements.append(
            {"tag": "note", "elements": [{"tag": "plain_text", "content": note}]}
        )
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": header_template,
            },
            "elements": elements,
        },
    }


# ── Schemas ─────────────────────────────────────────────────────

@dataclass
class NotifyRequest:
    title: Optional[str] = None
    body: Optional[str] = None
    note: Optional[str] = None
    channel: str = "feishu_webhook"
    webhook_url: Optional[str] = None
    raw_payload: Optional[dict] = None
    dry_run: bool = False

    def payload(self) -> dict:
        """Resolve the outbound payload: raw_payload passthrough, else envelope builder."""
        if self.raw_payload is not None:
            return self.raw_payload
        if self.channel == "feishu_webhook" or self.channel == "mock":
            if self.title is not None and self.body is not None:
                return build_interactive_card(self.title, self.body, note=self.note)
            return build_text(self.body or "")
        return build_text(self.body or "")


@dataclass
class NotifyResult:
    provider: str
    channel: str
    status: str = "pending"  # sent | dry_run | failed
    ok: bool = False
    error: Optional[str] = None
    payload: Optional[dict] = None
    created_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
