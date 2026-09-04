"""Volcengine OCR provider.

Two modes:
  - general_ocr  → VisualService.ocr_normal()  (通用文字识别, supports base64)
  - document_parse → VisualService with DocumentParse action (智能文档解析)

Env vars:
  VOLCENGINE_ACCESS_KEY_ID
  VOLCENGINE_SECRET_ACCESS_KEY
  VOLCENGINE_REGION              (default: cn-north-1)
  VOLCENGINE_OCR_SERVICE_ID      (veImageX service id for OCR)
  VOLCENGINE_DOCUMENT_PARSE_TABLE_FORMAT  (markdown | html, default: markdown)
"""

from __future__ import annotations

import base64
import os
from typing import Optional

from capabilities.ocr.schemas import OcrRequest, OcrResult, OcrBlock, OcrQuality
from capabilities.ocr.providers import BaseOcrProvider

try:
    from volcengine.visual.VisualService import VisualService
    VISUAL_SDK = True
except ImportError:
    VISUAL_SDK = False


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


DOC_PARSE_ACTION = "OCRPdf"
DOC_PARSE_VERSION = "2021-08-23"


def _unpack_ocr_normal(data: dict) -> tuple[str, list[OcrBlock], list[list[list[str]]]]:
    result = data.get("result") or data.get("data") or data
    raw_lines: list[str] = []
    blocks: list[OcrBlock] = []

    line_texts = result.get("line_texts", [])
    if isinstance(line_texts, list):
        raw_lines.extend(line_texts)

    if not raw_lines:
        chars = result.get("chars", [])
        if isinstance(chars, list):
            for line_chars in chars:
                if isinstance(line_chars, list):
                    line_text = "".join(c.get("char", "") for c in line_chars if isinstance(c, dict))
                    if line_text:
                        raw_lines.append(line_text)

    words_info = result.get("prism_wordsInfo", [])
    if isinstance(words_info, list):
        for i, w in enumerate(words_info):
            if isinstance(w, dict):
                text = w.get("word", w.get("text", ""))
                conf = float(w.get("confidence", 0.0))
                blocks.append(OcrBlock(text=text, confidence=conf, line_num=i + 1))
            elif isinstance(w, str):
                blocks.append(OcrBlock(text=w, confidence=0.0, line_num=i + 1))

    if not blocks and raw_lines:
        blocks = [OcrBlock(text=line, confidence=0.0, line_num=i + 1) for i, line in enumerate(raw_lines)]

    line_probs = result.get("line_probs", [])
    if line_probs and blocks:
        for i, prob in enumerate(line_probs):
            if i < len(blocks):
                blocks[i].confidence = float(prob)

    tables: list[list[list[str]]] = []
    table_data = result.get("tables", [])
    if isinstance(table_data, list):
        for t in table_data:
            if isinstance(t, list):
                rows = []
                for row in t:
                    if isinstance(row, list):
                        rows.append([str(c) for c in row])
                    else:
                        rows.append([str(row)])
                tables.append(rows)

    return "\n".join(raw_lines), blocks, tables


def _unpack_document_parse(data: dict, table_format: str) -> tuple[str, str, list[OcrBlock], list[list[list[str]]]]:
    code = data.get("code", 0)
    if code != 10000:
        msg = data.get("message", f"API error code={code}")
        return msg, msg, [], []

    result = data.get("data", {})

    markdown = result.get("markdown", "")
    detail = result.get("detail", [])

    raw_text = markdown
    blocks: list[OcrBlock] = []
    tables: list[list[list[str]]] = []

    if isinstance(detail, list):
        all_textblocks: list[dict] = []
        for page in detail:
            page_md = page.get("page_md", "")
            if page_md and not raw_text:
                raw_text = page_md
            textblocks = page.get("textblocks", [])
            if isinstance(textblocks, list):
                all_textblocks.extend(textblocks)

        for i, tb in enumerate(all_textblocks):
            if isinstance(tb, dict):
                text = tb.get("text", "")
                label = tb.get("label", "")
                conf = 0.0
                if text:
                    blocks.append(OcrBlock(text=text, confidence=conf, line_num=i + 1, bounding_box=[label]))

    if not raw_text and blocks:
        raw_text = "\n".join(b.text for b in blocks)

    if not markdown:
        markdown = raw_text

    return raw_text, markdown, blocks, tables


def _compute_quality(blocks: list[OcrBlock]) -> OcrQuality:
    confs = [b.confidence for b in blocks if b.confidence > 0]
    if confs:
        mean_conf = sum(confs) / len(confs)
        low_conf = sum(1 for c in confs if c < 0.6)
    else:
        mean_conf = None
        low_conf = 0
    return OcrQuality(
        mean_confidence=mean_conf,
        low_confidence_blocks=low_conf,
        needs_manual_review=(mean_conf is None or mean_conf < 0.6),
    )


class VolcengineOcrProvider(BaseOcrProvider):
    name = "volcengine"

    def __init__(self):
        self._vs: Optional[VisualService] = None
        self._table_format: str = "markdown"
        self._service_id: str = ""

    def _ensure_visual(self):
        if self._vs is not None:
            return
        if not VISUAL_SDK:
            raise RuntimeError("volcengine SDK not installed. Run: pip install volcengine")
        ak = _env("VOLCENGINE_ACCESS_KEY_ID")
        sk = _env("VOLCENGINE_SECRET_ACCESS_KEY")
        if not ak or not sk:
            raise RuntimeError("VOLCENGINE_ACCESS_KEY_ID and VOLCENGINE_SECRET_ACCESS_KEY must be set")
        self._vs = VisualService()
        self._vs.set_ak(ak)
        self._vs.set_sk(sk)
        self._table_format = _env("VOLCENGINE_DOCUMENT_PARSE_TABLE_FORMAT", "markdown")
        self._service_id = _env("VOLCENGINE_OCR_SERVICE_ID", "")

    def _handle_error(self, request: OcrRequest, error: str) -> OcrResult:
        return OcrResult(
            source_image_path=request.source_image_path,
            provider="volcengine",
            mode=request.mode,
            status="failed",
            error=error,
        )

    def process(self, request: OcrRequest, image_bytes: bytes) -> OcrResult:
        if not VISUAL_SDK:
            return self._handle_error(
                request, "volcengine SDK not installed. Run: pip install volcengine"
            )
        try:
            self._ensure_visual()
        except RuntimeError as e:
            return self._handle_error(request, str(e))

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        try:
            if request.mode == "document_parse":
                return self._do_document_parse(request, image_b64)
            else:
                return self._do_general_ocr(request, image_b64)
        except Exception as e:
            return self._handle_error(request, f"{type(e).__name__}: {e}")

    def _do_general_ocr(self, request: OcrRequest, image_b64: str) -> OcrResult:
        form = {"image_base64": image_b64}

        raw_response = self._vs.ocr_normal(form)

        raw_text, blocks, tables = _unpack_ocr_normal(raw_response)
        quality = _compute_quality(blocks)

        return OcrResult(
            source_image_path=request.source_image_path,
            provider="volcengine",
            mode="general_ocr",
            status="success",
            raw_text=raw_text,
            markdown=raw_text,
            blocks=blocks,
            tables=tables,
            quality=quality,
            raw_response=raw_response,
            error=None,
        )

    def _do_document_parse(self, request: OcrRequest, image_b64: str) -> OcrResult:
        action = _env("VOLCENGINE_DOCUMENT_PARSE_ACTION", DOC_PARSE_ACTION)
        version = _env("VOLCENGINE_DOCUMENT_PARSE_VERSION", DOC_PARSE_VERSION)

        self._vs.set_api_info(action, version)
        form = {
            "image_base64": image_b64,
            "version": "v3",
            "file_type": "image",
            "parse_mode": "auto",
            "table_mode": self._table_format,
            "filter_header": "true",
        }

        raw_response = self._vs.ocr_api(action, form)
        err = raw_response.get("ResponseMetadata", {}).get("Error", {})
        if err:
            return OcrResult(
                source_image_path=request.source_image_path,
                provider="volcengine",
                mode="document_parse",
                status="failed",
                error=f'{err.get("Code", "")}: {err.get("Message", "")}',
                raw_response=raw_response,
            )
        return self._build_doc_parse_result(request, raw_response)

    def _build_doc_parse_result(self, request: OcrRequest, raw_response: dict) -> OcrResult:
        raw_text, markdown, blocks, tables = _unpack_document_parse(raw_response, self._table_format)
        quality = _compute_quality(blocks)
        return OcrResult(
            source_image_path=request.source_image_path,
            provider="volcengine",
            mode="document_parse",
            status="success",
            raw_text=raw_text,
            markdown=markdown,
            blocks=blocks,
            tables=tables,
            quality=quality,
            raw_response=raw_response,
            error=None,
        )
