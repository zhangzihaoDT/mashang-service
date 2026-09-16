"""Feishu Base Capability — 领域无关原语集合（当前：docx 云文档写入）。

namespace: `capabilities.feishu`
"""

from capabilities.feishu.auth import FeishuAPIError, tenant_access_token

__all__ = ["FeishuAPIError", "tenant_access_token"]
