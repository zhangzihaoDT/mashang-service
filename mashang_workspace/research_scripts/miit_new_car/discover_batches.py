#!/usr/bin/env python
"""
发现工信部装备工业发展中心「公告发布」栏目的最新批次。

信息源:
  API: https://www.miit-eidc.org.cn/module/web/jpage/dataproxy.jsp (XML, 直接返回数据)

V0.2.1:
  - 网络重试与 backoff
  - discovery cache fallback（远端失败时使用本地缓存）
  - 网络失败返回明确标记，不再输出"未发现任何批次"

用法:
  python mashang_workspace/research_scripts/miit_new_car/discover_batches.py
  python mashang_workspace/research_scripts/miit_new_car/discover_batches.py --limit 5
  python mashang_workspace/research_scripts/miit_new_car/discover_batches.py --pages 3
  python mashang_workspace/research_scripts/miit_new_car/discover_batches.py --publicity
  python mashang_workspace/research_scripts/miit_new_car/discover_batches.py --official
  python mashang_workspace/research_scripts/miit_new_car/discover_batches.py --format json
"""

import sys, re, json, argparse, time
from pathlib import Path
from html.parser import HTMLParser
from xml.parsers.expat import ParserCreate

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from research_scripts.miit_new_car.http_utils import NetworkError, http_get_text, DEFAULT_TIMEOUT

JPAGE_BASE = (
    "https://www.miit-eidc.org.cn/module/web/jpage/dataproxy.jsp"
    "?webid=12&columnid=1691&unitid=4638"
    "&path=https://www.miit-eidc.org.cn/"
    "&webname={webname}"
    "&permissiontype=0"
)

RE_BATCH = re.compile(r"[第](\d+)[批]")
RE_PUBLICITY = re.compile(r"(拟发布|公示)")
RE_OFFICIAL = re.compile(r"^《道路机动车辆生产企业及产品》")

DISCOVERY_OUTPUT_DIR = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "discovery"
DISCOVERY_CACHE_FILE = DISCOVERY_OUTPUT_DIR / "discovered_batches.json"


def _fetch_jpage(page: int = 1) -> str:
    from urllib.parse import quote
    webname = quote("工业和信息化部装备工业发展中心", safe="")
    url = JPAGE_BASE.format(webname=webname) + f"&page={page}"
    return http_get_text(url)


class _RecordExtractor:
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


def _dedup(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for item in items:
        key = f"{item['batch_no']}|{item['status']}|{item['detail_url']}"
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _parse_records_to_batches(xml: str) -> list[dict]:
    """解析 jpage XML 并返回批次列表。"""
    extractor = _RecordExtractor()
    records = extractor.parse(xml)
    results = []

    if not records:
        return results

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

    return _dedup(results)


def discover_batches(
    limit: int = 10,
    pages: int = 1,
    status_filter: str | None = None,
    force_refresh: bool = False,
) -> tuple[list[dict], str]:
    """
    发现公告批次。

    返回:
        (batches, source)
        source: "remote" | "cache" | "network_unavailable"
    """
    all_items = []
    network_warnings = 0
    remote_ok = False

    # Try remote
    if not force_refresh:
        try:
            for page in range(1, pages + 1):
                xml = _fetch_jpage(page=page)
                items = _parse_records_to_batches(xml)
                if items:
                    all_items.extend(items)
                    if len(items) < 15:
                        break
                else:
                    if page == 1:
                        break
                remote_ok = True
        except NetworkError:
            network_warnings += 1
            pass
    else:
        try:
            for page in range(1, pages + 1):
                xml = _fetch_jpage(page=page)
                items = _parse_records_to_batches(xml)
                if items:
                    all_items.extend(items)
                    if len(items) < 15:
                        break
                else:
                    if page == 1:
                        break
                remote_ok = True
        except NetworkError:
            network_warnings += 1
            pass

    if remote_ok:
        all_items = _dedup(all_items)
        all_items.sort(key=lambda x: x["batch_no"], reverse=True)
        if status_filter:
            all_items = [b for b in all_items if b["status"] == status_filter]
        all_items = all_items[:limit]

        # Save to cache
        DISCOVERY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(DISCOVERY_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(all_items, f, ensure_ascii=False, indent=2)

        return all_items, "remote"

    # Remote failed — try cache
    if DISCOVERY_CACHE_FILE.exists():
        try:
            cached = json.loads(DISCOVERY_CACHE_FILE.read_text(encoding="utf-8"))
            if status_filter:
                cached = [b for b in cached if b["status"] == status_filter]
            print(f"[WARN] 远端请求失败，使用本地 discovery cache ({len(cached)} 条)", file=sys.stderr)
            return cached[:limit], "cache"
        except (json.JSONDecodeError, Exception) as e:
            print(f"[WARN] discovery cache 读取失败: {e}", file=sys.stderr)

    # No remote, no cache
    return [], "network_unavailable"


def discover_latest_by_status(status: str) -> tuple[dict | None, str]:
    batches, source = discover_batches(limit=1, status_filter=status)
    return (batches[0] if batches else None), source


def main():
    p = argparse.ArgumentParser(description="发现 MIIT 新车公告最新批次")
    p.add_argument("--limit", type=int, default=10, help="返回条数")
    p.add_argument("--pages", type=int, default=1, help="jpage 分页页数（默认 1）")
    p.add_argument("--publicity", action="store_true", help="仅筛选公示批次")
    p.add_argument("--official", action="store_true", help="仅筛选正式公告批次")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    p.add_argument("--output-dir", type=str, help="输出目录（默认 outputs/miit_new_car/discovery）")
    p.add_argument("--refresh", action="store_true", help="刷新远端数据（仍允许 cache fallback）")
    p.add_argument("--force-refresh", action="store_true", help="强制远端请求，失败则失败")
    args = p.parse_args()

    status_filter = None
    if args.publicity:
        status_filter = "publicity"
    if args.official:
        status_filter = "official"

    force = "force" if args.force_refresh else ("refresh" if args.refresh else False)

    try:
        batches, source = discover_batches(
            limit=args.limit,
            pages=args.pages,
            status_filter=status_filter,
            force_refresh=args.force_refresh,
        )
    except NetworkError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if source == "network_unavailable":
        print("[ERROR] network_unavailable: 无法连接工信部 EIDC 网站，且本地无 discovery cache", file=sys.stderr)
        sys.exit(1)

    # Save discovery output (only for remote source)
    if source == "remote":
        out_dir = Path(args.output_dir) if args.output_dir else DISCOVERY_OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "discovered_batches.json").write_text(
            json.dumps(batches, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        md_lines = ["# 已发现的 MIIT 公告批次\n"]
        md_lines.append(f"| 批次 | 状态 | 发布日期 |\n|------|------|---------|\n")
        for b in batches:
            label = "公示" if b["status"] == "publicity" else "正式发布"
            md_lines.append(f"| {b['batch_no']} | {label} | {b['publish_date']} |\n")
        (out_dir / "discovered_batches.md").write_text("".join(md_lines), encoding="utf-8")

    if args.format == "json":
        output = {"source": source, "batches": batches}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if not batches:
        print(f"[WARN] 未发现任何公告批次 (source={source})", file=sys.stderr)
        return

    label = "公示" if status_filter == "publicity" else ("正式发布" if status_filter == "official" else "全部")
    cache_tag = " [CACHE]" if source == "cache" else ""
    print(f"[Summary] 发现 {len(batches)} 批道路机动车辆公告 [{label}] (pages={args.pages}){cache_tag}")
    print()
    for b in batches:
        status_label = "公示" if b["status"] == "publicity" else "正式发布"
        print(f"  第 {b['batch_no']} 批 [{status_label}]  {b['publish_date']}")
        print(f"    {b['title'][:80]}...")
        print(f"    {b['detail_url']}")
        print()


if __name__ == "__main__":
    main()
