"""Feishu group webhook provider.

Posts a Feishu interactive-card / text payload to a group robot webhook.

Env vars:
  FS_WEBHOOK_URL    Feishu group robot webhook URL (used when request.webhook_url is unset)
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from capabilities.notify.schemas import NotifyResult, NotifyRequest
from capabilities.notify.providers import BaseNotifyProvider

_WEBHOOK_URL_ENV = "FS_WEBHOOK_URL"
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = [2, 4, 8]


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


class FeishuWebhookProvider(BaseNotifyProvider):
    name = "feishu_webhook"
    channel = "feishu_webhook"

    def send(self, request: NotifyRequest) -> NotifyResult:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = request.payload()

        if request.dry_run:
            return NotifyResult(
                provider=self.name,
                channel=self.channel,
                status="dry_run",
                ok=True,
                payload=payload,
                created_at=now,
            )

        url = request.webhook_url or _env(_WEBHOOK_URL_ENV)
        if not url:
            return NotifyResult(
                provider=self.name,
                channel=self.channel,
                status="failed",
                ok=False,
                error=f"{_WEBHOOK_URL_ENV} not set (and no webhook_url provided)",
                payload=payload,
                created_at=now,
            )

        last_error: Optional[str] = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = httpx.post(url, json=payload, timeout=15)
                if resp.status_code == 429:
                    wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                    print(f"[notify] 频率限制(429)，{wait}s 后重试", file=sys.stderr)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                code = data.get("StatusCode") or data.get("code", 0)
                if code == 0:
                    return NotifyResult(
                        provider=self.name,
                        channel=self.channel,
                        status="sent",
                        ok=True,
                        payload=payload,
                        created_at=now,
                    )
                if str(code) == "11232":
                    wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                    print(f"[notify] 频率限制({code})，{wait}s 后重试", file=sys.stderr)
                    time.sleep(wait)
                    continue
                last_error = f"feishu API error code={code}: {data.get('msg', '')}"
                print(f"[notify] {last_error}", file=sys.stderr)
                return NotifyResult(
                    provider=self.name,
                    channel=self.channel,
                    status="failed",
                    ok=False,
                    error=last_error,
                    payload=payload,
                    created_at=now,
                )
            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}"
                print(f"[notify] HTTP 错误: {e}", file=sys.stderr)
                break
            except (httpx.RequestError, ValueError) as e:
                last_error = str(e)
                wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                print(f"[notify] 请求失败: {e}，{wait}s 后重试", file=sys.stderr)
                time.sleep(wait)

        return NotifyResult(
            provider=self.name,
            channel=self.channel,
            status="failed",
            ok=False,
            error=last_error or "unknown error",
            payload=payload,
            created_at=now,
        )
