"""飞书云文档（Docx）写入子能力。

    from capabilities.feishu.docx import FeishuDocxClient
"""

from capabilities.feishu.docx.client import FeishuDocxClient
from capabilities.feishu.docx.converter import html_to_markdown, to_markdown

__all__ = ["FeishuDocxClient", "html_to_markdown", "to_markdown"]
