from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class OcrQuality:
    mean_confidence: Optional[float] = None
    low_confidence_blocks: int = 0
    needs_manual_review: bool = False


@dataclass
class OcrBlock:
    text: str
    confidence: float = 0.0
    bounding_box: Optional[list[float]] = None
    line_num: int = 0


@dataclass
class OcrProviderConfig:
    name: str
    mode: str
    extra: dict = field(default_factory=dict)


@dataclass
class OcrRequest:
    source_image_path: str
    provider: str = "volcengine"
    mode: str = "general_ocr"
    force_refresh: bool = False
    output_root: Optional[str] = None


@dataclass
class OcrResult:
    source_image_path: str
    provider: str
    mode: str
    status: str = "pending"
    raw_text: str = ""
    markdown: str = ""
    blocks: list[OcrBlock] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    raw_response: Optional[dict] = None
    raw_response_path: str = ""
    error: Optional[str] = None
    image_sha256: str = ""
    ocr_result_id: str = ""
    created_at: str = ""
    quality: OcrQuality = field(default_factory=OcrQuality)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw_response", None)
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def compute_image_sha256(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def build_ocr_result_id(image_sha256: str, provider: str, mode: str) -> str:
    raw = f"{image_sha256}:{provider}:{mode}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def make_ocr_result_id(image_bytes: bytes, provider: str, mode: str) -> str:
    sha = compute_image_sha256(image_bytes)
    return build_ocr_result_id(sha, provider, mode)
