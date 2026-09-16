"""飞书应用身份鉴权 — tenant_access_token 获取与进程内缓存。

env:
  FEISHU_APP_ID      应用 App ID
  FEISHU_APP_SECRET  应用 App Secret
  FEISHU_API_BASE    Open API base（默认 https://open.feishu.cn/open-apis）
"""

from __future__ import annotations

import os
import time
from typing import Optional

import httpx

DEFAULT_API_BASE = "https://open.feishu.cn/open-apis"

_TOKEN_CACHE: dict = {"token": None, "expire_at": 0.0}

_PERMISSION_HINTS = {
    99991672: "应用缺少所需权限 scope，请在飞书开放平台申请并发布新版本",
    1770040: "无文件夹权限：tenant 身份只能写应用自建文件夹，或需把应用加为该文件夹协作者",
    1770032: "无该文档权限：请把应用加为文档/文件夹协作者",
}


class FeishuAPIError(RuntimeError):
    """飞书 Open API 返回 code != 0，或本地缺失配置。"""

    def __init__(self, code: int | str, msg: str, endpoint: str = "", http_status: int | None = None):
        self.code = code
        self.msg = msg
        self.endpoint = endpoint
        self.http_status = http_status
        try:
            hint = _PERMISSION_HINTS.get(int(code))
        except (TypeError, ValueError):
            hint = None
        text = f"Feishu API error code={code} msg={msg}"
        if endpoint:
            text += f" endpoint={endpoint}"
        if http_status:
            text += f" http={http_status}"
        if hint:
            text += f" → {hint}"
        super().__init__(text)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


def api_base(base: str | None = None) -> str:
    return (base or _env("FEISHU_API_BASE", DEFAULT_API_BASE)).rstrip("/")


def tenant_access_token(
    app_id: Optional[str] = None,
    app_secret: Optional[str] = None,
    *,
    http=None,
    base: str | None = None,
    timeout: float = 20.0,
) -> str:
    """获取 tenant_access_token（带缓存，提前 60s 过期刷新）。"""
    app_id = app_id or _env("FEISHU_APP_ID")
    app_secret = app_secret or _env("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        raise FeishuAPIError(-1, "FEISHU_APP_ID / FEISHU_APP_SECRET 未设置")

    now = time.time()
    if _TOKEN_CACHE["token"] and now + 60 < float(_TOKEN_CACHE["expire_at"]):
        return str(_TOKEN_CACHE["token"])

    client = http or httpx
    url = f"{api_base(base)}/auth/v3/tenant_access_token/internal"
    resp = client.request("POST", url, json={"app_id": app_id, "app_secret": app_secret}, timeout=timeout)
    data = _json_or_raise(resp, "tenant_access_token")
    if int(data.get("code", -1)) != 0:
        raise FeishuAPIError(data.get("code", -1), data.get("msg", ""), "tenant_access_token", resp.status_code)
    token = data.get("tenant_access_token")
    if not token:
        raise FeishuAPIError(-1, "响应缺少 tenant_access_token", "tenant_access_token", resp.status_code)
    expire = float(data.get("expire") or data.get("expires_in") or 0)
    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expire_at"] = now + max(expire, 0.0)
    return str(token)


def _json_or_raise(resp, endpoint: str) -> dict:
    try:
        return resp.json() if resp.content else {}
    except Exception:
        raise FeishuAPIError(resp.status_code, (getattr(resp, "text", "") or "")[:300], endpoint, resp.status_code)
