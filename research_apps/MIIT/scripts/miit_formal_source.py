#!/usr/bin/env python3
"""
MIIT Gov 正式公告 Source 层（网络 / source discovery）

只负责从 miit.gov.cn 获取「道路机动车辆生产企业及产品」正式公告（confirmed 层）：
  - discover formal announcement 列表（装备工业一司 → 文件发布 /jgsj/zbys/wjfb/）
  - fetch announcement detail 页（标题/发文字号/发布日期/附件清单）
  - parse formal metadata + 附件发现（.doc）
  - download attachment（复用 eidc_source.download_attachment / doc_to_txt）

禁止做 canonical 字段推断。正式公告页提供什么由本层回答；
字段在 MIIT 车型模型里意味着什么，由 vehicle_record_builder / 06 回答。

定位：MIIT 正式公告（第 N 批）是最终确认源（source=miit_gov, stage=confirmed）；
EIDC（miit-eidc.org.cn）为同批正式公告的镜像/历史 fallback。
附件实际托管在 miit.gov.cn 的 cms_files，与 EIDC 附件同构（eidc_parser 可复用）。
"""

import json
import re

import requests

import eidc_source as eidc  # noqa: E402  (doc / sha256 复用)

# ── 官方站点 ─────────────────────────────────────────────────────
MIIT_WJFB_COLUMN = "https://www.miit.gov.cn/jgsj/zbys/wjfb/index.html"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")

# 列表 API（装备工业一司 → 文件发布 栏目）
WJFB_WEBID = "8d828e408d90447786ddbe128d495e9e"
WJFB_PAGEID = "28ac65269a12494f81b5a832bce5f51c"
WJFB_TPLSETID = "209741b2109044b5b7695700b2bec37e"
WJFB_UNITID = "edd197089bfc46ad95a7c75eb28ddf4d"
UNIT_API = "https://www.miit.gov.cn/api-gateway/jpaas-publish-server/front/page/build/unit"

# 附件链接模式：官方正文 <a href=".../*.doc">N.title.doc</a>（gov 页为相对路径）
RE_ATTACH_LINK = re.compile(
    r'<a[^>]+href="([^"]+\.doc)"[^>]*>([^<]+?)</a>', re.IGNORECASE)
RE_TITLE = re.compile(r'name="ArticleTitle"\s+content="([^"]+)"')
RE_PUBDATE = re.compile(r'name="PubDate"\s+content="([^"]+)"')
# 正文发文字号行（如 发文字号：中华人民共和国工业和信息化部公告2026年第21号 成文日期：…）
RE_DOC_NO = re.compile(r'发文字号[：:]\s*(.{4,70}?)(?=成文日期|发布日期|发布机构|$)')
RE_NO_IN_TEXT = re.compile(r'公告(20\d{2})年第([0-9一二三四五六七八九十]+)号')
RE_BATCH_IN_TITLE = eidc.RE_BATCH_IN_TITLE
RE_TAX_BATCH = eidc.RE_TAX_BATCH
RE_PURCHASE_BATCH = eidc.RE_PURCHASE_BATCH
_to_arabic = eidc._to_arabic


def _http_get(url: str, referer: str = "", timeout: int = 60) -> requests.Response:
    resp = requests.get(url, headers={
        "User-Agent": UA,
        "Referer": referer or MIIT_WJFB_COLUMN,
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        "X-Requested-With": "XMLHttpRequest",
    }, timeout=timeout)
    resp.raise_for_status()
    return resp


# ── 栏目列表：定位指定批次的正式公告 ─────────────────────────────

def discover_formal_notice(batch: str, page_size: int = 60) -> dict | None:
    """在 文件发布 栏目搜索第 {batch} 批《道路机动车辆生产企业及产品》正式公告。

    返回首个匹配公告详情页 URL / title / publish_date；未找到返回 None。
    （不做 CMS 栏目级 reconcile：只按标题「道路机动车辆生产企业及产品（第N批）」精确匹配。）
    """
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    try:
        session.get(MIIT_WJFB_COLUMN, timeout=20)
    except Exception:
        pass  # cookie priming 非致命

    params = {
        "webId": WJFB_WEBID, "parseType": "buildstatic", "pageType": "column",
        "tagId": "当前栏目_list", "tplSetId": WJFB_TPLSETID,
        "pageId": WJFB_PAGEID, "unitId": WJFB_UNITID,
        "pageNo": "1", "pageSize": str(page_size), "loadEnabled": True,
    }
    resp = session.get(UNIT_API, params=params, timeout=30)
    resp.raise_for_status()
    html = resp.json().get("data", {}).get("html", "")

    # 每行 = <a href>title</a> + 日期 span
    pattern = re.compile(
        r'<a[^>]*href="(/jgsj/zbys/wjfb/art/[^"]+)"[^>]*>(.*?)</a>\s*'
        r'(?:<[^>]*span[^>]*>([^<]{6,14})</span>)?', re.DOTALL)
    for m in pattern.finditer(html):
        title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if "道路机动车辆生产企业及产品" not in title:
            continue
        # 标题形如《道路机动车辆生产企业及产品》（第409批）…
        bm = re.search(r'第\s*([0-9０-９]+)\s*批', title)
        if bm and _to_arabic(bm.group(1)) == str(batch):
            pub = m.group(3).strip() if m.group(3) else ""
            return {
                "batch_no": str(batch),
                "title": title,
                "source_url": "https://www.miit.gov.cn" + m.group(1),
                "publish_date": pub or "",
                "discover_url": MIIT_WJFB_COLUMN,
            }
    return None


# ── 公告详情页：metadata + 附件清单 ─────────────────────────────

def fetch_formal_detail(detail_url: str) -> str:
    """抓取正式公告详情页，返回 HTML 文本。"""
    resp = _http_get(detail_url)
    return resp.text


def parse_formal_metadata(html: str, detail_url: str) -> dict:
    """从正式公告页解析批次元数据 + 附件清单。

    meta key 风格与 EIDC 页略有差异（PubDate / ArticleTitle），本函数只读 gov 页。
    """
    meta: dict = {"source_url": detail_url}
    m = RE_TITLE.search(html)
    if m:
        meta["title"] = m.group(1).strip()
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

    text_body = re.sub(r'<[^>]+>', ' ', html)
    text_body = re.sub(r'\s+', ' ', text_body)
    m = RE_DOC_NO.search(text_body)
    if m:
        mm = RE_NO_IN_TEXT.search(m.group(1))
        if mm:
            meta["announcement_no"] = (f"{mm.group(0)}"
                                       if mm.group(0).startswith("公告") else
                                       f"公告{mm.group(1)}年第{_to_arabic(mm.group(2))}号")
    # 若仍无法定位，回退按标题中的年号
    if "announcement_no" not in meta and "title" in meta:
        mm = RE_NO_IN_TEXT.search(meta["title"])
        if mm:
            meta["announcement_no"] = f"{mm.group(1)}年第{_to_arabic(mm.group(2))}号"

    # 附件清单（.doc；href 可能为相对路径 → 补全 https://www.miit.gov.cn）
    attachments = []
    seen = set()
    for href, title in RE_ATTACH_LINK.findall(html):
        if href in seen:
            continue
        seen.add(href)
        if href.startswith("/"):
            href = "https://www.miit.gov.cn" + href
        attachments.append({
            "title": title.strip(),
            "url": href,
            "filename": href.rsplit("/", 1)[-1],
        })
    meta["attachments"] = attachments
    return meta


# ── doc → txt（复用 eidc_source / eidc_doc_extract）──────────────

def doc_to_txt(doc_path, txt_path, force=False) -> dict:
    """textutil .doc → .txt；超大 doc 由 03 脚本回退 eidc_doc_extract。"""
    return eidc.doc_to_txt(doc_path, txt_path, force=force)


def download_attachment(url: str, target, force: bool = False) -> dict:
    """下载附件到 target；幂等（sha256 校验）。Referer 指向 wjfb。"""
    return eidc.download_attachment(url, target, force=force)


if __name__ == "__main__":
    import sys
    import argparse
    parser = argparse.ArgumentParser(description="MIIT 正式公告 source 调试")
    parser.add_argument("--batch", default="409")
    args = parser.parse_args()
    found = discover_formal_notice(args.batch)
    if not found:
        print(f"batch {args.batch} 未在文件发布栏目发现正式公告")
        sys.exit(1)
    print(json.dumps(found, ensure_ascii=False, indent=2))
    html = fetch_formal_detail(found["source_url"])
    meta = parse_formal_metadata(html, found["source_url"])
    print(json.dumps(meta, ensure_ascii=False, indent=2))
