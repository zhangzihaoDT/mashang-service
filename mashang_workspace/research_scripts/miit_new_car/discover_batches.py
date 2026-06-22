#!/usr/bin/env python
"""
发现工信部装备工业发展中心「公告发布」栏目的最新批次。

信息源:
  API: https://www.miit-eidc.org.cn/module/web/jpage/dataproxy.jsp (XML, 直接返回数据)

用法:
  python mashang_workspace/research_scripts/miit_new_car/discover_batches.py
  python mashang_workspace/research_scripts/miit_new_car/discover_batches.py --limit 5
  python mashang_workspace/research_scripts/miit_new_car/discover_batches.py --format json
"""

import sys, re, json, argparse
from pathlib import Path
from html.parser import HTMLParser
from xml.parsers.expat import ParserCreate
from urllib.request import Request, urlopen
from urllib.error import URLError

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT))

JPAGE_API = (
    "https://www.miit-eidc.org.cn/module/web/jpage/dataproxy.jsp"
    "?page=1&webid=12&columnid=1691&unitid=4638"
    "&path=https://www.miit-eidc.org.cn/"
    "&webname={webname}"
    "&permissiontype=0"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30

RE_BATCH = re.compile(r"[第](\d+)[批]")
RE_PUBLICITY = re.compile(r"(拟发布|公示)")
RE_OFFICIAL = re.compile(r"^《道路机动车辆生产企业及产品》")


def _fetch(url: str, timeout: int = REQUEST_TIMEOUT) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            encoding = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(encoding, errors="replace")
    except URLError as e:
        raise RuntimeError(f"请求失败 (URLError) {url}: {e}")
    except TimeoutError as e:
        raise RuntimeError(f"连接超时 {url}: {e}")
    except OSError as e:
        raise RuntimeError(f"网络错误 {url}: {e}")
    except Exception as e:
        raise RuntimeError(f"未知错误 {url}: {type(e).__name__}: {e}")


def _fetch_jpage(page: int = 1) -> str:
    """获取 jpage dataproxy XML。"""
    from urllib.parse import quote
    webname = quote("工业和信息化部装备工业发展中心", safe="")
    url = JPAGE_API.format(webname=webname)
    if page > 1:
        url += f"&page={page}"
    return _fetch(url)


class _RecordExtractor:
    """用 Expat 解析 jpage XML，提取 <record> CDATA 内容。"""

    def __init__(self):
        self.records: list[str] = []
        self._in_record = False
        self._cdata = ""

    def _start_element(self, name, attrs):
        if name == "record":
            self._in_record = True
            self._cdata = ""

    def _end_element(self, name):
        if name == "record" and self._in_record:
            self.records.append(self._cdata)
            self._in_record = False

    def _cdata_handler(self, data):
        if self._in_record:
            self._cdata += data

    def parse(self, xml: str) -> list[str]:
        parser = ParserCreate()
        parser.StartElementHandler = self._start_element
        parser.EndElementHandler = self._end_element
        parser.CharacterDataHandler = self._cdata_handler
        parser.Parse(xml, True)
        return self.records


class _ArticleParser(HTMLParser):
    """解析 record 中的 <li><a> 内容，提取 title/url/date。"""

    def __init__(self):
        super().__init__()
        self.pairs: list[dict] = []
        self._in_li = False
        self._current: dict = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "li":
            self._in_li = True
            self._current = {}
        if self._in_li and tag == "a" and "title" in a:
            href = a.get("href", "")
            if "/art/" in href:
                full_url = href if href.startswith("http") else f"https://www.miit-eidc.org.cn{href}"
                self._current["title_full"] = a.get("title", "")
                self._current["detail_url"] = full_url

    def handle_endtag(self, tag):
        if tag == "li" and self._in_li:
            if self._current.get("title_full") and self._current.get("detail_url"):
                self.pairs.append(self._current)
            self._in_li = False

    def handle_data(self, data):
        if self._in_li:
            # Removes [ ] brackets around dates
            stripped = data.strip().strip("[]").strip()
            if re.match(r"\d{4}-\d{2}-\d{2}", stripped):
                self._current["publish_date"] = stripped


def _parse_batch_from_title(title: str) -> int | None:
    m = RE_BATCH.search(title)
    if m:
        return int(m.group(1))
    return None


def _detect_status(title: str) -> str:
    if RE_PUBLICITY.search(title):
        return "publicity"
    if RE_OFFICIAL.match(title):
        return "official"
    if title.startswith("关于"):
        return "publicity"
    return "official"


def discover_batches(limit: int = 10) -> list[dict]:
    try:
        xml = _fetch_jpage(page=1)
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        print(f"[HINT] 请确认网络可达 https://www.miit-eidc.org.cn（工信部网站可能需 China 网络）", file=sys.stderr)
        return []

    extractor = _RecordExtractor()
    records = extractor.parse(xml)

    if not records:
        print(f"[ERROR] API 返回空数据（可能接口地址已变更）", file=sys.stderr)
        debug_path = Path(WORKSPACE_ROOT / "outputs" / "miit_new_car" / "raw" / "_debug_jpage_response.xml")
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(xml[:5000], encoding="utf-8")
        print(f"[DEBUG] 已保存前 5KB 响应到 {debug_path}", file=sys.stderr)
        return []

    results = []
    for cdata in records:
        parser = _ArticleParser()
        parser.feed(cdata)
        for item in parser.pairs:
            title = item.get("title_full", "")
            batch_no = _parse_batch_from_title(title)
            if batch_no is None:
                continue
            results.append({
                "batch_no": batch_no,
                "status": _detect_status(title),
                "title": title.strip(),
                "publish_date": item.get("publish_date", ""),
                "detail_url": item.get("detail_url", ""),
                "source": "miit-eidc",
            })

    results.sort(key=lambda x: x["batch_no"], reverse=True)
    return results[:limit]


def main():
    p = argparse.ArgumentParser(description="发现 MIIT 新车公告最新批次")
    p.add_argument("--limit", type=int, default=10, help="返回条数")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    try:
        batches = discover_batches(limit=args.limit)
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        print(json.dumps(batches, ensure_ascii=False, indent=2))
        return

    if not batches:
        print("[WARN] 未发现任何公告批次", file=sys.stderr)
        return

    print(f"[Summary] 发现 {len(batches)} 批公告")
    print()
    for b in batches:
        status_label = "公示" if b["status"] == "publicity" else "正式发布"
        print(f"  第 {b['batch_no']} 批 [{status_label}]  {b['publish_date']}")
        print(f"    {b['title'][:80]}...")
        print(f"    {b['detail_url']}")
        print()


if __name__ == "__main__":
    main()
