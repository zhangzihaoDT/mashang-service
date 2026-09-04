"""Notify Service — CLI for sending notifications through a configured provider.

Usage:
    python -m capabilities.notify.notify_service --title "标题" --body "正文 markdown" [--note ...]
    python -m capabilities.notify.notify_service --body "纯文本" [--provider mock]
    python -m capabilities.notify.notify_service --raw-payload <json-file> [--dry-run]

Provider env:
    FS_WEBHOOK_URL    Feishu group robot webhook URL (feishu_webhook provider)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from capabilities.notify.schemas import NotifyRequest, NotifyResult
from capabilities.notify.providers import get_provider


def notify(
    title=None,
    body=None,
    note=None,
    provider_name: str = "feishu_webhook",
    webhook_url=None,
    raw_payload=None,
    dry_run: bool = False,
) -> NotifyResult:
    provider = get_provider(provider_name)
    request = NotifyRequest(
        title=title,
        body=body,
        note=note,
        channel=provider.channel,
        webhook_url=webhook_url,
        raw_payload=raw_payload,
        dry_run=dry_run,
    )
    return provider.send(request)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Notify Service — send text / interactive card")
    p.add_argument("--provider", default="feishu_webhook", choices=["feishu_webhook", "mock"])
    p.add_argument("--title", default=None, help="Card header title")
    p.add_argument("--body", default=None, help="Body text (lark_md when title+body card, else plain text)")
    p.add_argument("--note", default=None, help="Optional card footer note")
    p.add_argument("--raw-payload", default=None, help="Path to a full JSON payload to send as-is")
    p.add_argument("--webhook", default=None, help="Webhook URL override (default from FS_WEBHOOK_URL)")
    p.add_argument("--dry-run", action="store_true", help="Print payload, do not send")
    return p


def main():
    args = _build_parser().parse_args()

    raw_payload = None
    if args.raw_payload:
        with open(args.raw_payload, "r", encoding="utf-8") as f:
            raw_payload = json.load(f)

    result = notify(
        title=args.title,
        body=args.body,
        note=args.note,
        provider_name=args.provider,
        webhook_url=args.webhook,
        raw_payload=raw_payload,
        dry_run=args.dry_run,
    )
    print(result.to_json(indent=2))
    if result.ok:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
