"""
OCR Service — CLI interface for OCR processing with caching, QPS limiting, and output archiving.

Usage:
    python -m capabilities.ocr.ocr_service --image <path> --provider volcengine --mode general_ocr
    python -m capabilities.ocr.ocr_service --image <path> --provider volcengine --mode document_parse
    python -m capabilities.ocr.ocr_service --image <path> --provider mock
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from capabilities.ocr.schemas import (
    OcrRequest,
    OcrResult,
    compute_image_sha256,
    build_ocr_result_id,
    make_ocr_result_id,
)
from capabilities.ocr.providers import get_provider, BaseOcrProvider


# ── QPS Limiter ─────────────────────────────────────────────

MAX_CONCURRENCY = 1
MIN_INTERVAL_SECONDS = 1.2
RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = [2, 5, 10]

_last_call_time: float = 0
_lock = Lock()


def _enforce_qps():
    global _last_call_time
    with _lock:
        now = time.time()
        elapsed = now - _last_call_time
        if elapsed < MIN_INTERVAL_SECONDS:
            sleep_time = MIN_INTERVAL_SECONDS - elapsed
            time.sleep(sleep_time)
        _last_call_time = time.time()


# ── Output Paths ─────────────────────────────────────────────

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
DEFAULT_OUTPUT_ROOT = os.path.join(_REPO_ROOT, "outputs", "ocr")


def _ensure_output_dirs(output_root: str, provider: str) -> dict[str, Path]:
    base = Path(output_root)
    dirs = {
        "raw": base / "raw" / provider,
        "results": base / "results",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


# ── Caching ──────────────────────────────────────────────────

def _check_cache(output_root: str, provider: str, ocr_result_id: str) -> Optional[OcrResult]:
    dirs = _ensure_output_dirs(output_root, provider)
    result_path = dirs["results"] / f"{ocr_result_id}.json"
    if result_path.exists():
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return OcrResult(**data)
    return None


def _save_results(output_root: str, provider: str, result: OcrResult):
    dirs = _ensure_output_dirs(output_root, provider)
    result_id = result.ocr_result_id

    raw_path = dirs["raw"] / f"{result_id}.json"
    result_path = dirs["results"] / f"{result_id}.json"

    result.raw_response_path = str(raw_path)

    if result.status == "success" and result.raw_response is not None:
        raw_path.write_text(json.dumps(result.raw_response, ensure_ascii=False, indent=2, default=str))

    result_path.write_text(result.to_json(), encoding="utf-8")


# ── Image Loading ────────────────────────────────────────────

def _load_image(image_path: str) -> bytes:
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    return p.read_bytes()


# ── Main Processing ──────────────────────────────────────────

def process_image(
    image_path: str,
    provider_name: str = "volcengine",
    mode: str = "general_ocr",
    force_refresh: bool = False,
    output_root: Optional[str] = None,
) -> OcrResult:
    output_root = output_root or DEFAULT_OUTPUT_ROOT
    image_bytes = _load_image(image_path)
    image_sha256 = compute_image_sha256(image_bytes)
    ocr_result_id = build_ocr_result_id(image_sha256, provider_name, mode)
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Check cache
    if not force_refresh:
        cached = _check_cache(output_root, provider_name, ocr_result_id)
        if cached is not None:
            cached.status = "cached"
            return cached

    # Get provider
    provider: BaseOcrProvider = get_provider(provider_name)

    # Build request
    request = OcrRequest(
        source_image_path=image_path,
        provider=provider_name,
        mode=mode,
        force_refresh=force_refresh,
        output_root=output_root,
    )

    # QPS-limited + retry
    last_error: Optional[str] = None
    result: Optional[OcrResult] = None
    for attempt in range(RETRY_MAX_ATTEMPTS):
        if attempt > 0:
            backoff = RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
            time.sleep(backoff)

        _enforce_qps()

        result = provider.process(request, image_bytes)
        if result.status == "success":
            break
        last_error = result.error

    # RETRY_MAX_ATTEMPTS >= 1, so the loop body always runs at least once.
    assert result is not None

    # Fill metadata
    result.source_image_path = image_path
    result.image_sha256 = image_sha256
    result.ocr_result_id = ocr_result_id
    result.created_at = created_at

    # Save & return
    _save_results(output_root, provider_name, result)
    return result


# ── CLI ──────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="OCR Service — image text extraction")
    p.add_argument("--image", required=True, help="Path to image file")
    p.add_argument("--provider", default="volcengine", choices=["volcengine", "mock"], help="OCR provider")
    p.add_argument("--mode", default="general_ocr", choices=["general_ocr", "document_parse"], help="OCR mode")
    p.add_argument("--force-refresh", action="store_true", help="Skip cache, force re-run OCR")
    p.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, help="Output root directory")
    return p


def main():
    parser = _build_parser()
    args = parser.parse_args()

    result = process_image(
        image_path=args.image,
        provider_name=args.provider,
        mode=args.mode,
        force_refresh=args.force_refresh,
        output_root=args.output_root,
    )

    print(result.to_json(indent=2))


if __name__ == "__main__":
    main()
