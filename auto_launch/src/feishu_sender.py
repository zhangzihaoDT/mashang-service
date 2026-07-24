"""飞书 Webhook 推送（交互卡片）"""

import os, sys, time
from typing import Optional

import httpx

_WEBHOOK_URL_ENV = "FS_WEBHOOK_URL"

_CARD_TEMPLATE = {
    "msg_type": "interactive",
    "card": {
        "header": {
            "title": {"tag": "plain_text", "content": "{title}"},
            "template": "blue",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": "{body}"}},
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "Auto Launch · 品牌营销事件监控 · {date_str}",
                    }
                ],
            },
        ],
    },
}


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
    payload = _CARD_TEMPLATE.copy()
    payload["card"] = _CARD_TEMPLATE["card"].copy()
    payload["card"]["header"] = _CARD_TEMPLATE["card"]["header"].copy()
    payload["card"]["header"]["title"] = {
        "tag": "plain_text",
        "content": title,
    }
    payload["card"]["elements"] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": body}},
        {"tag": "hr"},
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"Auto Launch · 品牌营销事件监控 · {date_str}",
                }
            ],
        },
    ]

    for attempt in range(3):
        try:
            resp = httpx.post(url, json=payload, timeout=15)
            if resp.status_code == 429:
                wait = 2 * (attempt + 1)
                print(f"[feishu] 频率限制，{wait}s 后重试", file=sys.stderr)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                print(
                    f"[feishu] 飞书 API 错误: {data.get('msg', 'unknown')}",
                    file=sys.stderr,
                )
                return False
            print(f"[feishu] 已同步到飞书群")
            return True
        except httpx.HTTPStatusError as e:
            print(f"[feishu] HTTP 错误: {e}", file=sys.stderr)
            return False
        except httpx.RequestError as e:
            wait = 2 * (attempt + 1)
            print(f"[feishu] 请求失败: {e}，{wait}s 后重试", file=sys.stderr)
            time.sleep(wait)

    print("[feishu] 重试耗尽，同步失败", file=sys.stderr)
    return False
