#!/usr/bin/env python
"""
抓取指定批次的公告详情页和附件。

V0.2.1: 详情页请求超时时，如果本地 detail.html 存在，则使用缓存继续。

用法:
  python mashang_workspace/research_scripts/miit_new_car/fetch_batch.py --batch 408
  python mashang_workspace/research_scripts/miit_new_car/fetch_batch.py --detail-url https://...
  python mashang_workspace/research_scripts/miit_new_car/fetch_batch.py --batch 408 --no-download
"""

import sys, re, json, argparse
from pathlib import Path
from urllib.error import HTTPError
from html.parser import HTMLParser
from datetime import datetime, timezone
from typing import Optional

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from research_scripts.miit_new_car.http_utils import NetworkError, http_get, http_get_text, DEFAULT_TIMEOUT

REQUEST_TIMEOUT = 60
OUTPUT_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "raw"

RE_BATCH = re.compile(r"[第](\d+)[批]")
RE_PUBLICITY = re.compile(r"(拟发布|公示)")

RE_ENTERPRISE_ADMISSION = re.compile(
    r"(新准入车辆生产企业|已准入企业变更信息清单|拟发布的新准入车辆生产企业|新增车辆生产企业|拟发布新增车辆生产企业)"
)
RE_ENTERPRISE_ADMISSION_SOURCE_TYPE = "enterprise_admission_change"
RE_HTML_IMAGE_FORMAT = "html_image_attachment"
RE_DOC_FORMAT = "document"


def _extract_batch_no(title: str, url: str) -> int:
    m = RE_BATCH.search(title)
    if m:
        return int(m.group(1))
    m2 = RE_BATCH.search(url)
    if m2:
        return int(m2.group(1))
    raise ValueError(f"无法从标题或 URL 中提取批次号: {title}")


class _DetailParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title: str = ""
        self.publish_date: str = ""
        self.content_html: str = ""
        self.attachments: list[dict] = []
        self._in_title = False
        self._in_zoom = False
        self._in_anchor = False
        self._anchor_href = ""
        self._anchor_text = ""
        self._anchor_title_from_attr = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div" and (a.get("class") in ("_nk_wz_tit", "ctitle") or a.get("id") in ("con_con",)):
            self._in_title = True
        if tag == "div" and (a.get("id") in ("zoom", "con_con") or a.get("class") in ("con_con",)):
            self._in_zoom = True
            self.content_html = ""
        if self._in_zoom:
            if tag == "a" and "href" in a:
                href = a["href"]
                ext_lower = href.lower()
                is_doc = any(ext in ext_lower for ext in [".doc", ".docx", ".xls", ".xlsx", ".pdf"])
                is_datainfo = "/datainfo/" in ext_lower
                if is_doc or is_datainfo:
                    self._in_anchor = True
                    self._anchor_href = href
                    self._anchor_text = ""
                    self._anchor_title_from_attr = False
                    # Prefer title/alt attribute if present
                    att_title = a.get("title", a.get("alt", "")).strip()
                    if att_title:
                        self._anchor_text = att_title
                        self._anchor_title_from_attr = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_anchor:
            # Finalize attachment entry
            href = self._anchor_href
            ext_lower = href.lower()
            is_datainfo = "/datainfo/" in ext_lower
            if is_datainfo or any(ext in ext_lower for ext in [".doc", ".docx", ".xls", ".xlsx", ".pdf"]):
                source_format = RE_HTML_IMAGE_FORMAT if is_datainfo else RE_DOC_FORMAT
                filename = href.rstrip("/").split("/")[-1] or "attachment"
                if is_datainfo and not filename.endswith(".html"):
                    filename += ".html"
                self.attachments.append({
                    "url": href,
                    "title": self._anchor_text.strip(),
                    "filename": filename,
                    "source_format": source_format,
                })
            self._in_anchor = False
            self._anchor_href = ""
            self._anchor_text = ""
            self._anchor_title_from_attr = False
        if tag == "div" and self._in_title:
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()
        if self._in_zoom:
            self.content_html += data
        # Accumulate anchor text, unless already set from title/alt attribute
        if self._in_anchor and not self._anchor_title_from_attr:
            self._anchor_text += data


def _parse_html(html: str) -> _DetailParser:
    parser = _DetailParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser


def fetch_batch(
    batch_no: Optional[int] = None,
    detail_url: Optional[str] = None,
    download: bool = True,
    timeout: int = REQUEST_TIMEOUT,
    pages: int = 3,
) -> dict:
    if not detail_url and batch_no is None:
        raise ValueError("必须提供 batch_no 或 detail_url")

    if not detail_url:
        from discover_batches import discover_batches
        batches, _source = discover_batches(pages=pages, limit=9999)
        target = [b for b in batches if b["batch_no"] == batch_no]
        if not target:
            raise ValueError(
                f"未找到第 {batch_no} 批的详情页 URL（已搜索 pages={pages}）。\n"
                f"  建议：增加 --pages（如 --pages 20）扩大搜索范围。\n"
                f"  或使用 --detail-url 手动指定详情页 URL。"
            )
        detail_url = target[0]["detail_url"]

    batch_dir = OUTPUT_BASE / f"batch_{batch_no}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    detail_html_path = batch_dir / "detail.html"

    # Try remote detail page
    html = None
    detail_source = "remote"
    try:
        raw_bytes = http_get(detail_url, timeout=timeout)[0]
        html = raw_bytes.decode("utf-8", errors="replace")
    except NetworkError as e:
        # Fallback to local cache
        if detail_html_path.exists():
            print(f"  [WARN] 详情页请求失败，使用本地 cached detail.html: {e}", file=sys.stderr)
            html = detail_html_path.read_text(encoding="utf-8")
            detail_source = "cache"
        else:
            raise RuntimeError(f"详情页请求失败且本地无缓存: {e}") from e

    parser = _parse_html(html)
    title = parser.title or f"第{batch_no}批公告详情"
    pub_date = parser.publish_date or ""

    if batch_no is None:
        batch_no = _extract_batch_no(title, detail_url)

    status = "publicity" if RE_PUBLICITY.search(title) else "official"

    attachments = []
    from urllib.parse import urljoin
    for a in parser.attachments:
        att_title = a["title"] or a["filename"]
        source_format = a.get("source_format", RE_DOC_FORMAT)
        # Resolve relative href (e.g. /cms_files/...) against detail_url
        att_url = urljoin(detail_url, a["url"])
        # Classify source_type
        source_type = "unknown"
        if RE_ENTERPRISE_ADMISSION.search(att_title):
            source_type = RE_ENTERPRISE_ADMISSION_SOURCE_TYPE
        attachments.append({
            "url": att_url,
            "title": att_title,
            "filename": a["filename"],
            "source_format": source_format,
            "source_type": source_type,
        })

    result = {
        "batch_no": batch_no,
        "status": status,
        "title": title.strip(),
        "publish_date": pub_date,
        "detail_url": detail_url,
        "source": "miit-eidc",
        "detail_source": detail_source,
        "attachments": attachments,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Save detail HTML (only if fetched fresh)
    if detail_source == "remote":
        detail_html_path.write_text(html, encoding="utf-8")

    # Save metadata
    with open(batch_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    att_dir = batch_dir / "attachments"
    att_dir.mkdir(parents=True, exist_ok=True)

    attachment_statuses = []
    for idx, att in enumerate(attachments):
        url = att["url"]
        fname = att["filename"]
        if not fname or "." not in fname:
            ext = ".doc" if ".doc" in url else ".html"
            fname = f"attachment_{idx}{ext}"
        dest = att_dir / fname

        entry = {
            "title": att["title"],
            "url": url,
            "filename": fname,
            "source_format": att.get("source_format", "document"),
            "source_type": att.get("source_type", "unknown"),
            "status": "skipped",
            "http_status": None,
            "local_path": str(dest) if download else None,
            "error": None,
            "retried": 0,
            "final_url": None,
            "content_type": None,
            "content_length": 0,
        }

        if not download:
            if dest.exists():
                entry["status"] = "skipped"
                entry["local_path"] = str(dest)
            attachment_statuses.append(entry)
            continue

        if dest.exists():
            entry["status"] = "skipped"
            entry["local_path"] = str(dest)
            attachment_statuses.append(entry)
            print(f"  跳过已存在: {dest.name}")
            continue

        # For html_image_attachment, use parent detail_url as Referer
        extra_headers = {}
        if att.get("source_format") == "html_image_attachment":
            extra_headers["Referer"] = detail_url

        try:
            data, http_code = http_get(url, timeout=timeout, headers=extra_headers if extra_headers else None)
            dest.write_bytes(data)
            entry["status"] = "downloaded"
            entry["http_status"] = http_code
            entry["local_path"] = str(dest)
            entry["final_url"] = url
            entry["content_length"] = len(data)
            print(f"  下载: {dest.name} ({len(data)} bytes, format={att.get('source_format', '?')})")
        except HTTPError as e:
            entry["status"] = "failed"
            entry["http_status"] = e.code
            entry["error"] = str(e)
            print(f"  [WARN] 附件下载失败 [{e.code}] {url}")
        except NetworkError as e:
            entry["status"] = "failed"
            entry["error"] = str(e)
            print(f"  [WARN] 附件网络错误 {url}: {e}")
        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = f"{type(e).__name__}: {e}"
            print(f"  [WARN] 附件下载异常 {url}: {e}")
        attachment_statuses.append(entry)

    result["attachment_statuses"] = attachment_statuses

    with open(batch_dir / "links.json", "w", encoding="utf-8") as f:
        json.dump(attachments, f, ensure_ascii=False, indent=2)

    with open(batch_dir / "attachment_status.json", "w", encoding="utf-8") as f:
        json.dump(attachment_statuses, f, ensure_ascii=False, indent=2)

    with open(batch_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def main():
    p = argparse.ArgumentParser(description="抓取 MIIT 指定批次公告详情")
    p.add_argument("--batch", type=int, help="批次号")
    p.add_argument("--detail-url", type=str, help="详情页 URL（与 --batch 二选一）")
    p.add_argument("--no-download", action="store_true", help="不下载附件")
    p.add_argument("--pages", type=int, default=3, help="搜索分页页数（默认 3，搜索历史批次时需增加）")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    if not args.batch and not args.detail_url:
        p.error("请提供 --batch 或 --detail-url")

    try:
        result = fetch_batch(
            batch_no=args.batch,
            detail_url=args.detail_url,
            download=not args.no_download,
            pages=args.pages,
        )
    except (RuntimeError, ValueError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        result_out = {k: v for k, v in result.items() if k not in ("content_html",)}
        print(json.dumps(result_out, ensure_ascii=False, indent=2))
        return

    statuses = result.get("attachment_statuses", [])
    downloaded = sum(1 for s in statuses if s["status"] == "downloaded")
    failed = sum(1 for s in statuses if s["status"] == "failed")
    detail_src = result.get("detail_source", "remote")
    cache_tag = " [CACHE]" if detail_src == "cache" else ""

    print(f"\n[Summary] 第 {result['batch_no']} 批公告{cache_tag}")
    status_label = "公示" if result["status"] == "publicity" else "正式发布"
    print(f"  状态: {status_label}")
    print(f"  详情来源: {detail_src}")
    print(f"  标题: {result['title'][:100]}")
    print(f"  日期: {result['publish_date']}")
    print(f"  附件: {len(statuses)} 个 (下载 {downloaded}, 失败 {failed})")


if __name__ == "__main__":
    main()
