#!/usr/bin/env python
"""
附件 URL 下载诊断。

对批次详情页解析出的每个附件 URL 做诊断，记录下载策略、HTTP 状态、失败原因。

用法:
  python diagnose_attachment_urls.py --batch 407
  python diagnose_attachment_urls.py --batch 407 --format json
"""

import sys, json, argparse, re
from pathlib import Path
from urllib.parse import urlparse, urljoin, unquote
from html.parser import HTMLParser

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from research_scripts.miit_new_car.http_utils import NetworkError, http_get, DEFAULT_TIMEOUT

RAW_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "raw"
DIAG_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "diagnostics"

FAILURE_TYPES = (
    "timeout", "http_404", "http_403", "http_500",
    "empty_response", "invalid_url", "network_error",
    "content_too_small", "unsupported_scheme", "unknown_error",
)


def _load_attachments(batch_no: int) -> list[dict]:
    meta_path = RAW_BASE / f"batch_{batch_no}" / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata 不存在: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    links_path = RAW_BASE / f"batch_{batch_no}" / "links.json"
    if links_path.exists():
        return json.loads(links_path.read_text(encoding="utf-8"))

    return meta.get("attachments", [])


def _normalize_url(raw_url: str, detail_url: str) -> str:
    url = raw_url.strip()
    url = unquote(url)
    url = url.replace(" ", "%20").replace("\n", "").replace("\r", "")
    parsed = urlparse(url)
    if not parsed.scheme:
        if url.startswith("//"):
            url = "https:" + url
        else:
            url = urljoin(detail_url.rstrip("/") + "/", url.lstrip("/"))
    return url


def _diagnose_single(
    att: dict,
    batch_no: int,
    detail_url: str,
    referer: str,
) -> dict:
    original_url = att.get("url", "")
    normalized_url = _normalize_url(original_url, detail_url)
    parsed = urlparse(normalized_url)
    domain = parsed.netloc or "unknown"

    entry = {
        "batch_no": batch_no,
        "title": att.get("title", ""),
        "original_url": original_url,
        "normalized_url": normalized_url,
        "domain": domain,
        "referer": referer,
        "http_status": None,
        "content_type": None,
        "content_length": 0,
        "final_url": None,
        "download_status": "pending",
        "failure_type": None,
        "strategy_used": None,
        "local_path": None,
        "error": None,
    }

    if not original_url or original_url.startswith("javascript:"):
        entry["download_status"] = "failed"
        entry["failure_type"] = "invalid_url"
        entry["error"] = "href is javascript: or empty"
        return entry

    if parsed.scheme not in ("http", "https"):
        entry["download_status"] = "failed"
        entry["failure_type"] = "unsupported_scheme"
        entry["error"] = f"unsupported scheme: {parsed.scheme}"
        return entry

    strategies = [
        ("original_url", {"Referer": referer}),
    ]

    for strategy_name, extra_headers in strategies:
        try:
            headers = {}
            if extra_headers:
                headers.update(extra_headers)
            data, http_code = http_get(normalized_url, timeout=DEFAULT_TIMEOUT * 2, headers=headers)
            entry["http_status"] = http_code
            entry["content_type"] = None
            entry["content_length"] = len(data)
            entry["final_url"] = normalized_url
            entry["strategy_used"] = strategy_name

            if http_code == 404:
                entry["download_status"] = "failed"
                entry["failure_type"] = "http_404"
                entry["error"] = "HTTP 404 Not Found"
            elif http_code == 403:
                entry["download_status"] = "failed"
                entry["failure_type"] = "http_403"
                entry["error"] = "HTTP 403 Forbidden"
            elif http_code >= 500:
                entry["download_status"] = "failed"
                entry["failure_type"] = "http_500"
                entry["error"] = f"HTTP {http_code}"
            elif len(data) < 10:
                entry["download_status"] = "failed"
                entry["failure_type"] = "content_too_small"
                entry["error"] = f"content too small: {len(data)} bytes"
            else:
                entry["download_status"] = "downloaded"
            return entry
        except NetworkError as e:
            err_msg = str(e)
            if "timed out" in err_msg.lower() or "timeout" in err_msg.lower():
                entry["failure_type"] = "timeout"
            elif "404" in err_msg:
                entry["failure_type"] = "http_404"
                entry["http_status"] = 404
            elif "403" in err_msg:
                entry["failure_type"] = "http_403"
                entry["http_status"] = 403
            else:
                entry["failure_type"] = "network_error"
            entry["error"] = err_msg
            entry["strategy_used"] = strategy_name

    if entry["download_status"] == "pending":
        entry["download_status"] = "failed"
        if not entry["failure_type"]:
            entry["failure_type"] = "unknown_error"

    return entry


def diagnose_attachments(
    batch_no: int,
    output_dir: Path | None = None,
) -> list[dict]:
    attachments = _load_attachments(batch_no)
    if not attachments:
        print(f"[WARN] 没有附件需要诊断", file=sys.stderr)
        return []

    meta_path = RAW_BASE / f"batch_{batch_no}" / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    detail_url = meta.get("detail_url", "")
    referer = detail_url or "https://www.miit-eidc.org.cn/"

    results = []
    for att in attachments:
        entry = _diagnose_single(att, batch_no, detail_url, referer)
        results.append(entry)

    out_dir = output_dir or DIAG_BASE
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"batch_{batch_no}_attachment_diagnostics.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {json_path}")

    md_path = out_dir / f"batch_{batch_no}_attachment_diagnostics.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 第 {batch_no} 批附件诊断\n\n")
        f.write(f"| 标题 | 域名 | 状态 | HTTP | 失败类型 |\n|------|------|------|------|---------|\n")
        for r in results:
            f.write(f"| {r['title'][:30]} | {r['domain']} | {r['download_status']} | {r['http_status'] or '-'} | {r['failure_type'] or '-'} |\n")
    print(f"  Markdown: {md_path}")

    downloaded = sum(1 for r in results if r["download_status"] == "downloaded")
    failed = sum(1 for r in results if r["download_status"] == "failed")
    print(f"  附件诊断: {len(results)} total / {failed} failed / {downloaded} ok")

    return results


def main():
    p = argparse.ArgumentParser(description="诊断 MIIT 附件 URL 下载状态")
    p.add_argument("--batch", type=int, required=True, help="批次号")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    try:
        results = diagnose_attachments(batch_no=args.batch)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
