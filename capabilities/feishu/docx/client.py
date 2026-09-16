"""飞书云文档（Docx）写入客户端 — Markdown/HTML → Block Convert 路线。

流程（三步，全走服务端转换，无需手写 block/table renderer）：
  1. POST /open-apis/docx/v1/documents                        创建空文档（folder_token + title）
  2. POST /open-apis/docx/v1/documents/blocks/convert          内容 → blocks（content_type: markdown/html）
  3. POST /open-apis/docx/v1/documents/{id}/blocks/{id}/descendant  批量插入 blocks

env:
  FEISHU_APP_ID / FEISHU_APP_SECRET
  FEISHU_DOCX_FOLDER_TOKEN   默认目标文件夹
  FEISHU_TENANT_HOST         文档 URL host（默认 r4i0myjr3j.feishu.cn）
  FEISHU_API_BASE            Open API base（默认 https://open.feishu.cn/open-apis）
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Optional

import httpx

from capabilities.feishu.auth import FeishuAPIError, api_base, tenant_access_token
from capabilities.feishu.docx.converter import to_markdown

DEFAULT_TENANT_HOST = "r4i0myjr3j.feishu.cn"
IMAGE_BLOCK_TYPE = 27


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


def _sanitize_blocks(blocks: list) -> list:
    """剔除 convert 返回中的只读字段，避免 descendant create 报 1770001。

    - `parent_id`：由接口按 parent 关系推导，传入易冲突。
    - `table.property.merge_info`：只读，传入会触发 invalid param。
    """
    for b in blocks:
        if isinstance(b, dict):
            b.pop("parent_id", None)
            table = b.get("table")
            if isinstance(table, dict):
                prop = table.get("property")
                if isinstance(prop, dict):
                    prop.pop("merge_info", None)
    return blocks


class FeishuDocxClient:
    """飞书 Docx 写入客户端。`http` 可注入（测试用），默认 httpx。"""

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        folder_token: Optional[str] = None,
        host: Optional[str] = None,
        base: Optional[str] = None,
        timeout: float = 30.0,
        dry_run: bool = False,
        http=None,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.folder_token = folder_token or _env("FEISHU_DOCX_FOLDER_TOKEN")
        self.host = host or _env("FEISHU_TENANT_HOST", DEFAULT_TENANT_HOST)
        self.base = api_base(base)
        self.timeout = timeout
        self.dry_run = dry_run
        self._http = http or httpx

    # ── low level ──────────────────────────────────────────────

    def document_url(self, document_id: str) -> str:
        return f"https://{self.host}/docx/{document_id}"

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        token = tenant_access_token(self.app_id, self.app_secret, http=self._http, base=self.base, timeout=self.timeout)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        resp = self._http.request(method, f"{self.base}{path}", headers=headers, json=payload, timeout=self.timeout)
        try:
            data = resp.json() if resp.content else {}
        except Exception:
            raise FeishuAPIError(resp.status_code, (getattr(resp, "text", "") or "")[:300], path, resp.status_code)
        code = int(data.get("code", 0) or 0)
        if code != 0:
            raise FeishuAPIError(code, data.get("msg", ""), path, resp.status_code)
        return data.get("data") or {}

    def _request_multipart(self, path: str, data: dict, files: dict) -> dict:
        """multipart/form-data 请求（媒体上传用，Content-Type 由 httpx 生成）。"""
        token = tenant_access_token(self.app_id, self.app_secret, http=self._http, base=self.base, timeout=self.timeout)
        headers = {"Authorization": f"Bearer {token}"}
        resp = self._http.request("POST", f"{self.base}{path}", headers=headers, data=data, files=files, timeout=self.timeout)
        try:
            body = resp.json() if resp.content else {}
        except Exception:
            raise FeishuAPIError(resp.status_code, (getattr(resp, "text", "") or "")[:300], path, resp.status_code)
        code = int(body.get("code", 0) or 0)
        if code != 0:
            raise FeishuAPIError(code, body.get("msg", ""), path, resp.status_code)
        return body.get("data") or {}

    # ── public API ─────────────────────────────────────────────

    def create_document(self, title: str, folder_token: Optional[str] = None) -> str:
        folder = folder_token or self.folder_token
        if not folder:
            raise FeishuAPIError(-1, "未指定 folder_token（FEISHU_DOCX_FOLDER_TOKEN / --feishu-folder）")
        body: dict = {"title": title}
        if folder:
            body["folder_token"] = folder
        data = self._request("POST", "/docx/v1/documents", body)
        doc = (data.get("document") or {}) if isinstance(data, dict) else {}
        doc_id = doc.get("document_id")
        if not doc_id:
            raise FeishuAPIError(-1, "创建文档响应缺少 document_id", "/docx/v1/documents")
        return str(doc_id)

    def convert_to_blocks(self, content: str, content_type: str = "markdown") -> dict:
        data = self._request(
            "POST",
            "/docx/v1/documents/blocks/convert",
            {"content_type": content_type, "content": content},
        )
        blocks = _sanitize_blocks(data.get("blocks") or [])
        return {
            "blocks": blocks,
            "first_level_block_ids": data.get("first_level_block_ids") or [],
        }

    def insert_descendants(
        self,
        document_id: str,
        blocks: list,
        first_level_block_ids: list,
        index: int = -1,
    ) -> dict:
        if not blocks:
            return {}
        return self._request(
            "POST",
            f"/docx/v1/documents/{document_id}/blocks/{document_id}/descendant",
            {"children_id": first_level_block_ids, "index": index, "descendants": blocks},
        )

    def create_children(
        self,
        document_id: str,
        children: list,
        block_id: Optional[str] = None,
        index: int = -1,
    ) -> dict:
        """在指定父块下创建一组子块（默认根节点 document_id，index=-1 追加到末尾）。"""
        parent = block_id or document_id
        return self._request(
            "POST",
            f"/docx/v1/documents/{document_id}/blocks/{parent}/children",
            {"index": index, "children": children},
        )

    def upload_media(
        self,
        file_path: str | Path,
        parent_node: str,
        parent_type: str = "docx_image",
        file_name: Optional[str] = None,
        drive_route_token: Optional[str] = None,
    ) -> str:
        """上传媒体到指定文档（云空间不可见），返回 file_token。

        scope：`drive:drive`（或等效上传权限）。
        """
        p = Path(file_path)
        if not p.exists():
            raise FeishuAPIError(-1, f"文件不存在: {p}")
        size = p.stat().st_size
        data = {
            "file_name": file_name or p.name,
            "parent_type": parent_type,
            "parent_node": parent_node,
            "size": str(size),
        }
        if parent_type == "docx_image":
            data["extra"] = json.dumps({"drive_route_token": drive_route_token or parent_node})
        raw = self._request_multipart(
            "/drive/v1/medias/upload_all", data,
            {"file": (file_name or p.name, p.read_bytes(), "application/octet-stream")},
        )
        token = raw.get("file_token")
        if not token:
            raise FeishuAPIError(-1, "媒体上传响应缺少 file_token", "/drive/v1/medias/upload_all")
        return str(token)

    def insert_image(
        self,
        document_id: str,
        file_path: str | Path,
        block_id: Optional[str] = None,
        index: int = -1,
        file_name: Optional[str] = None,
    ) -> dict:
        """上传图片并插入为 image 块（block_type 27）。"""
        if self.dry_run:
            p = Path(file_path)
            return {"dry_run": True, "file": str(p), "file_token": None, "block": None}
        empty = self.create_children(
            document_id,
            [{"block_type": IMAGE_BLOCK_TYPE, "image": {}}],
            block_id=block_id,
            index=index,
        )
        children = empty.get("children") or []
        if not children or not children[0].get("block_id"):
            raise FeishuAPIError(-1, "创建空图片块响应缺少 block_id", "/docx/v1/documents/.../children")
        image_block_id = str(children[0]["block_id"])
        file_token = self.upload_media(
            file_path,
            parent_node=image_block_id,
            file_name=file_name,
            drive_route_token=document_id,
        )
        res = self._request(
            "PATCH",
            f"/docx/v1/documents/{document_id}/blocks/{image_block_id}",
            {"replace_image": {"token": file_token}},
        )
        return {"dry_run": False, "file_token": file_token, "block_id": image_block_id, "block": res}

    # ── high level ─────────────────────────────────────────────

    def create_document_from_content(
        self,
        title: str,
        content: str,
        content_type: str = "markdown",
        folder_token: Optional[str] = None,
    ) -> dict:
        """内容（markdown/html）→ 新建云文档；返回 {document_id, url, blocks, dry_run}。"""
        content = (content or "").strip()
        if self.dry_run:
            return {"document_id": None, "url": None, "blocks": None,
                    "dry_run": True, "title": title, "content_type": content_type,
                    "content_chars": len(content)}
        document_id = self.create_document(title, folder_token=folder_token)
        conv = self.convert_to_blocks(content, content_type=content_type)
        result = self.insert_descendants(document_id, conv["blocks"], conv["first_level_block_ids"])
        return {
            "document_id": document_id,
            "url": self.document_url(document_id),
            "blocks": len(conv["blocks"]),
            "revision_id": result.get("document_revision_id"),
            "dry_run": False,
        }

    def create_document_from_markdown(self, title: str, markdown: str, folder_token: Optional[str] = None) -> dict:
        return self.create_document_from_content(title, markdown, "markdown", folder_token)

    def create_document_from_html(self, title: str, html: str, folder_token: Optional[str] = None) -> dict:
        return self.create_document_from_content(title, to_markdown(html, source="html"), "markdown", folder_token)
