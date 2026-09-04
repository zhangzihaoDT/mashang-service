from typing import Optional
from capabilities.notify.schemas import NotifyResult, NotifyRequest


class BaseNotifyProvider:
    name: str = "base"
    channel: str = "notify"

    def send(self, request: NotifyRequest) -> NotifyResult:
        raise NotImplementedError


def get_provider(name: str) -> BaseNotifyProvider:
    if name == "feishu_webhook":
        from capabilities.notify.providers.feishu_webhook_provider import FeishuWebhookProvider
        return FeishuWebhookProvider()
    elif name == "mock":
        from capabilities.notify.providers.mock_provider import MockNotifyProvider
        return MockNotifyProvider()
    else:
        raise ValueError(f"Unknown notify provider: {name}")
