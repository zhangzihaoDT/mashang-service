#!/usr/bin/env python3
"""
MIIT EIDC Source 层（网络 / source discovery）

只负责从 EIDC 官方源获取数据：
  - fetch announcement page（正式公告详情页）
  - discover attachments（公告号 / 日期 / 附件清单）
  - download attachment（.doc）
  - convert .doc → .txt（textutil）
  - cache / raw evidence 落盘

禁止做 canonical 字段推断。EIDC 页面长什么样、附件怎么下载，由本层回答；
字段在 MIIT 车型模型里意味着什么，由 vehicle_record_builder 回答。

EIDC 正式公告页：https://www.miit-eidc.org.cn/art/YYYY/M/D/art_1691_{articleid}.html
附件实际托管在 miit.gov.cn 的 cms_files。
"""

import json
import re
import hashlib
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

# ── 官方站点 ─────────────────────────────────────────────────────
EIDC_BASE = "https://www.miit-eidc.org.cn"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 附件链接模式：官方正文 <a href="https://www.miit.gov.cn/cms_files/.../*.doc">N.title.doc</a>
RE_ATTACH_LINK = re.compile(
    r'<a[^>]+href="(https?://[^"]+\.doc)"[^>]*>([^<]+?)</a>', re.IGNORECASE)
RE_META_ARTICLEID = re.compile(r'name="i_articleid"\s+content="(\d+)"')
RE_META_GUID = re.compile(r'name="guid"\s+content="(\d+)"')
RE_TITLE = re.compile(r'name="ArticleTitle"\s+content="([^"]+)"')
RE_PUBDATE = re.compile(r'name="pubdate"\s+content="([^"]+)"')
RE_ANNOUNCEMENT_NO = re.compile(r'(\d{4})年[第]?(\d+)号')
RE_BATCH_IN_TITLE = re.compile(r'（第([0-9０-９一二三四五六七八九十]+)批）')
RE_TAX_BATCH = re.compile(r'车船税[^（]*（第([0-9０-９一二三四五六七八九十]+)批）')
RE_PURCHASE_BATCH = re.compile(r'购置税[^（]*（第([0-9０-９一二三四五六七八九十]+)批）')


def _to_arabic(s: str) -> str:
    """全角/中文数字 → 阿拉伯数字（批次号，如 '八十七'→'87'）。"""
    table = {"零": "0", "一": "1", "二": "2", "三": "3", "四": "4",
             "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "十": ""}
    if s.isdigit():
        return s
    if s and all("０" <= c <= "９" for c in s):
        return "".join(str(ord(c) - ord("０")) for c in s)
    if "十" in s:
        a, _, b = s.partition("十")
        return (table.get(a, "") or "1") + table.get(b, "0")
    return "".join(table.get(c, c) for c in s)


def _http_get(url: str, timeout: int = 60) -> requests.Response:
    resp = requests.get(url, headers={
        "User-Agent": UA,
        "Referer": EIDC_BASE,
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    }, timeout=timeout)
    resp.raise_for_status()
    return resp


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_announcement_page(detail_url: str) -> str:
    """抓取正式公告详情页，返回 HTML 文本。"""
    resp = _http_get(detail_url)
    return resp.text


def parse_announcement_metadata(html: str, detail_url: str) -> dict:
    """从正式公告页解析批次元数据 + 附件清单。"""
    meta = {"source_url": detail_url}
    m = RE_META_ARTICLEID.search(html)
    if m:
        meta["article_id"] = m.group(1)
    m = RE_META_GUID.search(html)
    if m:
        meta["guid"] = m.group(1)
    m = RE_TITLE.search(html)
    if m:
        meta["title"] = m.group(1)
        mm = RE_BATCH_IN_TITLE.search(m.group(1))
        if mm:
            meta["batch_no"] = _to_arabic(mm.group(1))
        mm = RE_TAX_BATCH.search(m.group(1))
        if mm:
            meta["vehicle_tax_batch"] = _to_arabic(mm.group(1))
        mm = RE_PURCHASE_BATCH.search(m.group(1))
        if mm:
            meta["purchase_tax_batch"] = _to_arabic(mm.group(1))
    m = RE_PUBDATE.search(html)
    if m:
        meta["publish_date"] = m.group(1).strip()
    m = RE_ANNOUNCEMENT_NO.search(html)
    if m:
        meta["announcement_no"] = f"{m.group(1)}年第{m.group(2)}号"

    # 附件清单
    attachments = []
    seen = set()
    for href, title in RE_ATTACH_LINK.findall(html):
        if href in seen:
            continue
        seen.add(href)
        fname = Path(urlparse(href).path).name
        attachments.append({
            "title": title.strip(),
            "url": href,
            "filename": fname,
        })
    meta["attachments"] = attachments
    return meta


def download_attachment(url: str, target: Path, force: bool = False) -> dict:
    """下载附件到 target；已存在且 sha256 相同则跳过（幂等）。

    返回 {filename, status, sha256, size, downloaded_at}
    """
    result = {"filename": target.name, "status": "skipped"}
    if target.exists() and not force:
        result["sha256"] = sha256_file(target)
        result["size"] = target.stat().st_size
        result["status"] = "cached"
        return result

    target.parent.mkdir(parents=True, exist_ok=True)
    resp = _http_get(url, timeout=120)
    resp.raise_for_status()
    target.write_bytes(resp.content)
    result["status"] = "downloaded"
    result["sha256"] = sha256_file(target)
    result["size"] = len(resp.content)
    return result


def doc_to_txt(doc_path: Path, txt_path: Path, force: bool = False) -> dict:
    """macOS textutil .doc → .txt；已存在且非 force 则跳过。"""
    result = {"status": "skipped", "method": "textutil"}
    if txt_path.exists() and not force:
        result["status"] = "cached"
        return result
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["textutil", "-convert", "txt", "-output", str(txt_path), str(doc_path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"textutil failed: {r.stderr[:300]}")
    result["status"] = "converted"
    return result


if __name__ == "__main__":
    # 调试：解析给定公告页元数据
    url = sys.argv[1] if len(sys.argv) > 1 else \
        "https://www.miit-eidc.org.cn/art/2026/7/17/art_1691_12598.html"
    html = fetch_announcement_page(url)
    meta = parse_announcement_metadata(html, url)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
