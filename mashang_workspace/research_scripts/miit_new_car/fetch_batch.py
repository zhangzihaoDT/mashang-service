#!/usr/bin/env python
"""
抓取指定批次的公告详情页和附件。

用法:
  python mashang_workspace/research_scripts/miit_new_car/fetch_batch.py --batch 408
  python mashang_workspace/research_scripts/miit_new_car/fetch_batch.py --detail-url https://...
  python mashang_workspace/research_scripts/miit_new_car/fetch_batch.py --batch 408 --no-download
"""

import sys, re, json, argparse
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser
from datetime import datetime, timezone
from typing import Optional

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 60
OUTPUT_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "raw"

RE_BATCH = re.compile(r"[第](\d+)[批]")
RE_PUBLICITY = re.compile(r"(拟发布|公示)")


def _fetch(url: str, timeout: int = REQUEST_TIMEOUT) -> tuple[bytes, int]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.status


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

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div" and a.get("class") == "_nk_wz_tit":
            self._in_title = True
        if tag == "div" and a.get("id") == "zoom":
            self._in_zoom = True
        if self._in_zoom:
            if tag == "a" and "href" in a:
                href = a["href"]
                if any(ext in href for ext in [".doc", ".docx", ".xls", ".xlsx", ".pdf", "/datainfo/"]):
                    self.attachments.append({
                        "url": href,
                        "title": a.get("title", a.get("alt", "")).strip(),
                        "filename": href.rstrip("/").split("/")[-1] or "attachment",
                    })

    def handle_endtag(self, tag):
        if tag == "div" and self._in_title:
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()


def fetch_batch(
    batch_no: Optional[int] = None,
    detail_url: Optional[str] = None,
    download: bool = True,
    timeout: int = REQUEST_TIMEOUT,
) -> dict:
    if not detail_url and batch_no is None:
        raise ValueError("必须提供 batch_no 或 detail_url")

    if not detail_url:
        from discover_batches import discover_batches
        batches = discover_batches(limit=5)
        target = [b for b in batches if b["batch_no"] == batch_no]
        if not target:
            raise ValueError(f"未找到第 {batch_no} 批的详情页 URL")
        detail_url = target[0]["detail_url"]

    raw_bytes = _fetch(detail_url, timeout=timeout)[0]
    html = raw_bytes.decode("utf-8", errors="replace")

    parser = _DetailParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    title = parser.title or f"第{batch_no}批公告详情"
    pub_date = parser.publish_date or ""

    if batch_no is None:
        batch_no = _extract_batch_no(title, detail_url)

    status = "publicity" if RE_PUBLICITY.search(title) else "official"

    attachments = []
    for a in parser.attachments:
        att_title = a["title"] or a["filename"]
        attachments.append({
            "url": a["url"],
            "title": att_title,
            "filename": a["filename"],
        })

    result = {
        "batch_no": batch_no,
        "status": status,
        "title": title.strip(),
        "publish_date": pub_date,
        "detail_url": detail_url,
        "source": "miit-eidc",
        "attachments": attachments,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    batch_dir = OUTPUT_BASE / f"batch_{batch_no}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    (batch_dir / "detail.html").write_text(html, encoding="utf-8")

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
            "status": "skipped",
            "http_status": None,
            "local_path": str(dest) if download else None,
            "error": None,
            "retried": 0,
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

        try:
            data, http_code = _fetch(url, timeout=timeout)
            dest.write_bytes(data)
            entry["status"] = "downloaded"
            entry["http_status"] = http_code
            entry["local_path"] = str(dest)
            print(f"  下载: {dest.name} ({len(data)} bytes)")
        except HTTPError as e:
            entry["status"] = "failed"
            entry["http_status"] = e.code
            entry["error"] = str(e)
            print(f"  [WARN] 附件下载失败 [{e.code}] {url}")
        except URLError as e:
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
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    if not args.batch and not args.detail_url:
        p.error("请提供 --batch 或 --detail-url")

    try:
        result = fetch_batch(
            batch_no=args.batch,
            detail_url=args.detail_url,
            download=not args.no_download,
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

    print(f"\n[Summary] 第 {result['batch_no']} 批公告")
    status_label = "公示" if result["status"] == "publicity" else "正式发布"
    print(f"  状态: {status_label}")
    print(f"  标题: {result['title'][:100]}")
    print(f"  日期: {result['publish_date']}")
    print(f"  附件: {len(statuses)} 个 (下载 {downloaded}, 失败 {failed})")


if __name__ == "__main__":
    main()
