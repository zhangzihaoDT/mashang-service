"""内容转换：HTML → Markdown（Markdown 直通）。

服务端 blocks/convert 只接受单一 content_type，因此 HTML 走本地 markdownify 归一为
Markdown 后再交给服务端转换，避免个人维护 block 级渲染。
"""

from __future__ import annotations


def html_to_markdown(html: str) -> str:
    try:
        from markdownify import markdownify as _markdownify
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("HTML→Markdown 需要 markdownify（pip install markdownify）") from e
    return _markdownify(html or "", heading_style="ATX")


def to_markdown(content: str, source: str = "markdown") -> str:
    src = (source or "markdown").strip().lower()
    if src in ("markdown", "md"):
        return content or ""
    if src in ("html", "htm"):
        return html_to_markdown(content)
    raise ValueError(f"不支持的 content source: {source!r}（可选 markdown/html）")
