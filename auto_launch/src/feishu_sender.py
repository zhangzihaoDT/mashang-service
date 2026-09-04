"""飞书 Webhook 推送（交互卡片）— 薄封装，传输收敛至 capabilities.notify。

保留 send_brief_to_feishu 对外签名与行为（返回 bool；未配置时跳过），
网络/重试/频率限制/错误语义统一由 capabilities.notify(feishu_webhook) 处理。
"""

import os
import sys
from typing import Optional

from capabilities.notify.schemas import build_interactive_card
from capabilities.notify.notify_service import notify

_WEBHOOK_URL_ENV = "FS_WEBHOOK_URL"


def _load_webhook_url() -> Optional[str]:
    return os.environ.get(_WEBHOOK_URL_ENV)


def send_brief_to_feishu(brief_text: str, date_str: str) -> bool:
    """将每日简报推送到飞书群 Webhook。返回是否成功。"""
    url = _load_webhook_url()
    if not url:
        print("[feishu] FS_WEBHOOK_URL 未设置，跳过飞书同步", file=sys.stderr)
        return False

    title = "🚗 重点新能源品牌每日营销事件监控"
    body = brief_text.strip()
    note = f"Auto Launch · 品牌营销事件监控 · {date_str}"
    payload = build_interactive_card(title, body, note=note)

    result = notify(raw_payload=payload, webhook_url=url, provider_name="feishu_webhook")
    if result.ok:
        print("[feishu] 已同步到飞书群")
        return True
    print(f"[feishu] 发送失败: {result.error}", file=sys.stderr)
    return False
