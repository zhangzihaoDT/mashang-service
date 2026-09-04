"""Mock notify provider — offline, no network, for tests and smoke runs."""

from datetime import datetime, timezone

from capabilities.notify.schemas import NotifyResult, NotifyRequest
from capabilities.notify.providers import BaseNotifyProvider


class MockNotifyProvider(BaseNotifyProvider):
    name = "mock"
    channel = "feishu_webhook"

    def send(self, request: NotifyRequest) -> NotifyResult:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if request.dry_run:
            return NotifyResult(
                provider=self.name,
                channel=self.channel,
                status="dry_run",
                ok=True,
                payload=request.payload(),
                created_at=now,
            )
        return NotifyResult(
            provider=self.name,
            channel=self.channel,
            status="sent",
            ok=True,
            payload=request.payload(),
            created_at=now,
        )
