#!/usr/bin/env python3
"""
MIIT Pipeline P2: 车型详情归档（可恢复的数据任务）

抓取策略（失败分类 + 有限重试 + checkpoint/resume）:
  - 状态分类: SUCCESS / NOT_FOUND / TRANSIENT_ERROR / BLOCKED / PARSE_ERROR
  - 瞬态失败 (timeout / 5xx / connection reset) 有限重试:
      max_retries=3, backoff = 2**n + random_jitter
  - 每次请求后保存 data/fetch_status/fetch_status_{batch}.json checkpoint
  - --retry-failed 只补抓 TRANSIENT_ERROR / BLOCKED 车型
  - 已成功数据不删除: 失败时标记 data_status=STALE + last_success
  - 原始页面缓存到 data/raw_html/，抓取失败时可从缓存恢复解析

归档产出（身份 = `{batch}:{型号}`，型号不假设全局唯一）:
  - data/vehicle_details/{batch}_{型号}-{产品名}.md   车型完整参数
  - data/vehicle_photos/{batch}_{型号}/              公告照片

用法:
  python3 scripts/02_archive_vehicle_details.py --batch 410 --all-missing   # 归档所有未归档品牌
  python3 scripts/02_archive_vehicle_details.py --batch 410 --retry-failed  # 只补抓失败车型
  python3 scripts/02_archive_vehicle_details.py --brand 零跑 --batch 410
  python3 scripts/02_archive_vehicle_details.py --brand 零跑 --dry-run      # 预览
"""

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests

from miit_paths import (  # noqa: E402
    DEFAULT_BATCH,
    get_batch_config,
    scan_path,
    fetch_status_path,
    detail_md_path,
    photo_dir,
    raw_html_path,
    ensure_dir,
)

MIIT_BASE = "https://www.miit.gov.cn"

# 网络参数（政府站点，保守设置）
TIMEOUT = (10, 60)               # connect=10s, read=60s
MAX_RETRIES = 3
REQUEST_INTERVAL = (0.8, 1.5)    # 请求间隔随机化

# 失败分类
SUCCESS = "SUCCESS"
NOT_FOUND = "NOT_FOUND"
TRANSIENT_ERROR = "TRANSIENT_ERROR"
BLOCKED = "BLOCKED"
PARSE_ERROR = "PARSE_ERROR"
SKIPPED = "SKIPPED"              # 无 detail_url 等数据问题，非抓取结果
RETRYABLE = {TRANSIENT_ERROR, BLOCKED}


class MiitError(Exception):
    pass


class TransientError(MiitError):
    """timeout / 5xx / connection reset —— 可重试"""


class BlockedError(MiitError):
    """403 / 429 / 验证码 / 风控 —— 不可重试，需人工介入"""


class NotFoundError(MiitError):
    """404 —— 明确不存在"""


def status_of_exc(e) -> str:
    if isinstance(e, NotFoundError):
        return NOT_FOUND
    if isinstance(e, BlockedError):
        return BLOCKED
    return TRANSIENT_ERROR


def short_label(e) -> str:
    if isinstance(e, NotFoundError):
        return "MIIT_NOT_FOUND"
    if isinstance(e, BlockedError):
        return "MIIT_BLOCKED"
    if isinstance(e, requests.exceptions.ReadTimeout):
        return "MIIT_TIMEOUT"
    if isinstance(e, requests.exceptions.ConnectTimeout):
        return "MIIT_CONN_TIMEOUT"
    if isinstance(e, requests.exceptions.ConnectionError):
        return "MIIT_CONN_RESET"
    return "MIIT_NETWORK"


def get_batch_date(batch: str) -> str:
    return get_batch_config(batch).get("notice_date", "")


def get_batch_cfg(batch: str) -> dict:
    return get_batch_config(batch)


def build_headers(batch: str) -> dict:
    cfg = get_batch_cfg(batch)
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/150.0.0.0 Safari/537.36",
        "Referer": f"https://www.miit.gov.cn/datainfo/dljdclscqyjcpgg/"
                   f"{cfg['index']}/index.html",
    }


SESSION = requests.Session()


def _prime_session(batch: str):
    SESSION.headers.update(build_headers(batch))
    cfg = get_batch_cfg(batch)
    try:
        SESSION.get(
            f"https://www.miit.gov.cn/datainfo/dljdclscqyjcpgg/"
            f"{cfg['index']}/index.html",
            timeout=(10, 30),
        )
    except Exception:
        pass


def load_scan(batch: str = "409") -> dict:
    path = scan_path(batch)
    text = path.read_text(encoding="utf-8")
    m = re.search(r'```json\n(.+?)\n```', text, re.DOTALL)
    if not m:
        print(f"错误: {path} 中未找到 JSON 数据块", file=sys.stderr)
        sys.exit(1)
    return json.loads(m.group(1))


def _is_block_page(text: str) -> bool:
    head = text[:2000]
    return any(kw in head for kw in ("安全验证", "访问验证", "请输入验证码"))


def fetch_detail_page(detail_url: str, model_id: str = "",
                      max_retries: int = MAX_RETRIES):
    """抓取详情页，对瞬态失败有限重试。

    Returns: (html, attempts)
    Raises: NotFoundError / BlockedError / TransientError（重试耗尽后）
    """
    full_url = MIIT_BASE + detail_url
    last_err: MiitError | None = None
    attempts = 0
    for attempt in range(1, max_retries + 1):
        attempts = attempt
        try:
            resp = SESSION.get(full_url, timeout=TIMEOUT)
            code = resp.status_code
            if code == 404:
                raise NotFoundError(f"HTTP 404 页面不存在")
            if code in (403, 429) or _is_block_page(resp.text):
                raise BlockedError(f"HTTP {code} 被拦截/风控")
            if code >= 500:
                raise TransientError(f"HTTP {code} 服务端错误")
            resp.raise_for_status()
            return resp.text, attempts
        except (NotFoundError, BlockedError) as e:
            raise e
        except requests.exceptions.ReadTimeout as e:
            last_err = TransientError("Read timed out")
        except requests.exceptions.ConnectTimeout as e:
            last_err = TransientError(f"连接超时 ({e})")
        except requests.exceptions.ConnectionError as e:
            last_err = TransientError(f"connection reset ({e})")
        except requests.exceptions.RequestException as e:
            last_err = TransientError(f"请求失败 ({e})")
        if attempt < max_retries:
            delay = 2 ** attempt + random.uniform(0, 1)
            print(f"    ⚠ {model_id or full_url} 瞬态失败，{delay:.1f}s 后重试 {attempt}/{max_retries}")
            time.sleep(delay)
    raise last_err or TransientError("未知网络错误")


def raw_cache_path(batch: str, brand: str, model_id: str) -> Path:
    return raw_html_path(batch, model_id)


class FetchState:
    """每个车型的抓取状态 checkpoint（fetch_status_{batch}.json）"""

    def __init__(self, batch: str):
        self.batch = batch
        self.path = fetch_status_path(batch)
        ensure_dir(self.path.parent)
        self.data: dict = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}

    def get(self, model_id: str, default=None):
        return self.data.get(model_id, default)

    def record(self, model_id, detail_url, status, attempts=0,
               last_error="", last_success=None, action="", code=""):
        prev = self.data.get(model_id, {})
        if status == SUCCESS:
            last_success = last_success or datetime.now().strftime("%Y-%m-%d")
            data_status = "FRESH"
        else:
            last_success = prev.get("last_success")
            data_status = "STALE" if last_success else "MISSING"
        self.data[model_id] = {
            "status": status,
            "code": code or status,
            "detail_url": detail_url,
            "attempts": attempts,
            "last_error": last_error,
            "last_success": last_success,
            "data_status": data_status,
            "action": action,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def save(self):
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self.path)

    def retry_queue(self, brands) -> list[tuple[dict, dict]]:
        """处于 TRANSIENT_ERROR / BLOCKED 且尚未归档成功的车型。"""
        queue = []
        for b in brands:
            for m in b["all_rows"]:
                rec = self.get(m["cpxh"]) or {}
                if rec.get("status") in RETRYABLE:
                    queue.append((b, m))
        return queue


def parse_tables(html: str) -> list[dict]:
    """Parse all <table> in the MIIT detail page into structured dicts.

    Two table layouts occur:
      A) Interleaved <th>/<td> pairs per row (Tables 0, 1):
         <tr><th>key1:</th><td>val1</td><th>key2:</th><td>val2</td></tr>
      B) Header row (<th>...) + data row(s) (<td>...) (Tables 2, 3).
    """
    results = []
    table_pattern = re.compile(r'<table[^>]*>(.*?)</table>', re.DOTALL)

    for table_match in table_pattern.finditer(html):
        table_html = table_match.group(1)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        if not rows:
            continue
        if '意见' in rows[0]:
            continue

        table_data = {}

        # Detect layout: if any row has both <th> and <td>, it's interleaved (Type A)
        row_tags = []
        for r in rows:
            has_th = '<th' in r
            has_td = '<td' in r
            row_tags.append((has_th, has_td))

        is_interleaved = any(ht and td for ht, td in row_tags)

        if is_interleaved:
            # Type A: interleaved <th>/<td> pairs
            for row_html in rows:
                # Extract all th/td cells preserving order
                cells = []
                for tag, content in re.findall(r'<(th|td)[^>]*>(.*?)</\1>', row_html, re.DOTALL):
                    text = re.sub(r'<[^>]+>', ' ', content).strip()
                    text = re.sub(r'\s+', ' ', text)
                    cells.append((tag, text))

                # Pair them: th→td, th→td, ...
                i = 0
                while i + 1 < len(cells):
                    tag_k, key = cells[i]
                    tag_v, val = cells[i + 1]
                    i += 2
                    if tag_k != 'th':
                        continue
                    key = key.replace("：", ":").rstrip(":")
                    if not key or key in ("查看原图",):
                        continue
                    # Skip photo row
                    if '查看原图' in val:
                        continue
                    # Handle br-separated values
                    val = re.sub(r'\s*<br\s*/?>\s*', ' / ', val)
                    val = re.sub(r'\s+', ' ', val).strip()
                    if key not in table_data:
                        table_data[key] = val
        else:
            # Type B: header row (<th>) + data rows (<td>)
            headers = []
            data_cells = []
            for row_html in rows:
                ths = re.findall(r'<th[^>]*>(.*?)</th>', row_html, re.DOTALL)
                tds = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
                if ths and not tds:
                    headers = [re.sub(r'<[^>]+>', ' ', h).strip() for h in ths]
                elif tds:
                    vals = [re.sub(r'<[^>]+>', ' ', t).strip() for t in tds]
                    data_cells.append(vals)

            if headers and data_cells:
                # Merge all data rows into one record
                for vals in data_cells:
                    for h, v in zip(headers, vals):
                        if h and v and h not in table_data:
                            table_data[h] = v

        if table_data:
            results.append(table_data)

    return results


def extract_photos(html: str) -> list[dict]:
    """Extract photo URLs from the detail page (cpgs paths in anchor hrefs).
    Each photo appears as both <a href> and (inside it) <img src>;
    We only extract unique anchor hrefs (查看原图 links)."""
    links = re.findall(
        r'<a[^>]*href="(/cms_files/filemanager/datainfo/cpgs/[^"]+)"[^>]*>\s*查看原图\s*</a>',
        html,
    )
    # Deduplicate while preserving order
    seen = set()
    return [{"url": url} for url in links if url not in seen and not seen.add(url)]


def download_photo(url: str, dest: Path, batch: str = DEFAULT_BATCH):
    full_url = MIIT_BASE + url
    cfg = get_batch_cfg(batch)
    resp = SESSION.get(full_url, timeout=TIMEOUT, headers={
        "Referer": f"https://www.miit.gov.cn/datainfo/dljdclscqyjcpgg/"
                   f"{cfg['index']}/index.html",
    })
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def tables_to_md(tables: list[dict], model_id: str, product_name: str,
                 cpsb: str, qymc: str, detail_url: str, photos: list[dict],
                 batch: str = DEFAULT_BATCH) -> str:
    brand_display = cpsb.replace("牌", "").strip()
    pub_date = get_batch_date(batch)
    title = f"工信部第{batch}批新车公示 — {cpsb}{product_name}"

    lines = [f"# {title}", "", "> 数据来源：工信部道路机动车辆生产企业及产品公告"]
    if pub_date:
        lines.append(f"> 公示时间：{pub_date}")
    lines.append("")

    for table_data in tables:
        # Determine section name
        section_keys = {
            ("产品商标", "产品型号"): "基本信息",
            ("外形尺寸", "轴距"): "尺寸参数",
            ("燃料种类", "发动机型号", "排量"): "动力系统",
            ("底盘类别",): "底盘信息",
            ("VIN",): "VIN信息",
        }
        section_name = "其他参数"
        match_score = 0
        for keys, name in section_keys.items():
            score = sum(1 for k in keys if any(k in tk for tk in table_data.keys()))
            if score > match_score:
                match_score = score
                section_name = name
        if section_name == "其他参数":
            # Check for 选装
            all_vals = " ".join(table_data.values())
            if "选装" in all_vals or "电动" in all_vals:
                section_name = "选装配置"

        lines.append(f"## {section_name}")
        lines.append("")
        lines.append("| 字段 | 内容 |")
        lines.append("|------|------|")
        for key, val in table_data.items():
            lines.append(f"| {key} | {val} |")
        lines.append("")

    # Photos section
    lines.append("## 车辆照片")
    lines.append("")
    lines.append("| 视角 | 链接 |")
    lines.append("|------|------|")
    view_names = ["左-右部照片.jpg", "后部照片.jpg", "选装照片1.jpg"]
    for i, photo in enumerate(photos[:3]):
        label = view_names[i] if i < len(view_names) else f"照片{i+1}"
        lines.append(f"| {label} | [查看原图]({photo['url']}) |")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"> 存档时间：{datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"> 来源：{MIIT_BASE}{detail_url}")

    return "\n".join(lines)


def extract_optional_config(table_data: dict) -> list[str]:
    """Extract optional/选装 config items from table rows."""
    items = []
    for key, val in table_data.items():
        if any(kw in key for kw in ["选装", "选", "可选"]):
            items.extend(re.split(r'[；;]', val))
        elif "选装" in val:
            items.append(val)
    return [i.strip() for i in items if i.strip()]


def archive_model(model: dict, state: FetchState, brand: str,
                  batch: str = DEFAULT_BATCH, dry_run: bool = False,
                  prefer_cache: bool = True) -> dict:
    """归档单个车型，返回结构化结果。

    Returns: {brand, model_id, status, code, attempts, last_error,
              last_success, action}
    """
    model_id = model["cpxh"]
    product_name = model["cpmc"]
    cpsb = model["cpsb"]
    qymc = model["qymc"]
    detail_url = model.get("detail_url", "")

    result = {
        "brand": brand, "model_id": model_id, "status": SKIPPED,
        "code": "SKIPPED", "attempts": 0, "last_error": "",
        "last_success": None, "action": "",
    }

    if not detail_url:
        print(f"  ⚠ {model_id}: 无 detail_url，跳过")
        result["action"] = "missing_url"
        return result

    md_path = detail_md_path(batch, model_id, product_name)
    image_dir = photo_dir(batch, model_id)

    if md_path.exists():
        print(f"  - {model_id}: 已归档，跳过")
        last_success = datetime.fromtimestamp(md_path.stat().st_mtime).strftime("%Y-%m-%d")
        state.record(model_id, detail_url, SUCCESS, last_success=last_success,
                     action="exists", code="EXISTS")
        result.update(status=SUCCESS, code="EXISTS", action="exists",
                      last_success=last_success)
        return result

    print(f"  → {model_id} ({product_name})")
    if dry_run:
        result.update(status=SUCCESS, action="preview")
        return result

    raw_cache = raw_cache_path(batch, brand, model_id)

    # 抓取详情页（瞬态失败有限重试 + 分类）
    html = None
    attempts = 0
    from_cache = False
    try:
        html, attempts = fetch_detail_page(detail_url, model_id=model_id)
        raw_cache.parent.mkdir(parents=True, exist_ok=True)
        raw_cache.write_text(html, encoding="utf-8")
    except (NotFoundError, BlockedError, TransientError) as e:
        if prefer_cache and raw_cache.exists():
            html = raw_cache.read_text(encoding="utf-8")
            from_cache = True
            state.record(model_id, detail_url, TRANSIENT_ERROR, attempts=attempts,
                         last_error=f"{short_label(e)}，已从缓存恢复", action="cache_restored",
                         code=short_label(e))
            print(f"    ↻ 网络失败，从缓存恢复解析: {model_id}")
        else:
            status = status_of_exc(e)
            state.record(model_id, detail_url, status, attempts=attempts,
                         last_error=str(e), action="deferred_retry",
                         code=short_label(e))
            print(f"    ✗ {short_label(e)} ({e}) attempts={attempts} action=deferred_retry")
            result.update(status=status, code=short_label(e), attempts=attempts,
                          last_error=str(e), action="deferred_retry",
                          last_success=(state.data.get(model_id) or {}).get("last_success"))
            return result

    # 解析表格
    tables = parse_tables(html)
    if not tables:
        state.record(model_id, detail_url, PARSE_ERROR, attempts=attempts,
                     last_error="未解析到表格数据", action="needs_inspection",
                     code="MIIT_PARSE_ERROR")
        print(f"    ✗ MIIT_PARSE_ERROR: 未解析到表格数据")
        result.update(status=PARSE_ERROR, code="MIIT_PARSE_ERROR", attempts=attempts,
                      last_error="未解析到表格数据", action="needs_inspection")
        return result

    # 提取照片 (links only, for the .md)
    photos = extract_photos(html)

    # 生成 .md
    md_content = tables_to_md(tables, model_id, product_name, cpsb, qymc,
                               detail_url, photos, batch=batch)
    image_dir.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_content, encoding="utf-8")

    # 下载照片
    view_names = ["左-右部照片.jpg", "后部照片.jpg", "选装照片1.jpg"]
    for i, photo in enumerate(photos[:3]):
        if i >= 3:
            break
        dest = image_dir / view_names[i]
        if not dest.exists():
            try:
                download_photo(photo["url"], dest, batch=batch)
                print(f"    📷 {view_names[i]}")
            except Exception as e:
                print(f"    ⚠ 照片{i+1}下载失败: {e}")

    action = "cache_restored" if from_cache else "archived"
    state.record(model_id, detail_url, SUCCESS, attempts=attempts,
                 action=action, code="SUCCESS")
    print(f"    ✓ 归档完成")
    result.update(status=SUCCESS, code="SUCCESS", attempts=attempts,
                  last_success=datetime.now().strftime("%Y-%m-%d"), action=action)
    return result


def print_summary(results: list[dict], batch: str):
    counts = Counter(r["status"] for r in results)
    total = len(results)
    success = counts.get(SUCCESS, 0)
    transient = counts.get(TRANSIENT_ERROR, 0)
    not_found = counts.get(NOT_FOUND, 0)
    blocked = counts.get(BLOCKED, 0)
    parse_err = counts.get(PARSE_ERROR, 0)
    skipped = counts.get(SKIPPED, 0)
    retry_queue = transient + blocked
    coverage = (success / total * 100) if total else 0.0

    print("")
    print("=" * 50)
    print(f"MIIT 抓取完成 (batch {batch})")
    print("")
    print(f"车型数        {total}")
    print(f"成功          {success}")
    print(f"暂时失败       {transient}")
    print(f"明确不存在     {not_found}")
    print(f"被拦截         {blocked}")
    print(f"解析失败       {parse_err}")
    print(f"跳过(无详情页) {skipped}")
    print("")
    print(f"coverage      {coverage:.1f}%")
    print(f"retry queue   {retry_queue}")
    print("")

    # 失败车型明细（按品牌分组）
    failures = [r for r in results if r["status"] in (RETRYABLE | {PARSE_ERROR, NOT_FOUND, BLOCKED})]
    if failures:
        print("待补抓 / 异常明细:")
        by_brand: dict[str, list] = {}
        for r in failures:
            by_brand.setdefault(r["brand"], []).append(r)
        for brand, items in by_brand.items():
            print(f"=== {brand} ===")
            for r in items:
                print(f"{r['model_id']}")
                print(f"  {r['code']}")
                print(f"  attempts: {r['attempts']}")
                print(f"  last_success: {r['last_success'] or 'none'}")
                print(f"  action: {r['action']}")
                print(f"  error: {r['last_error'] or '-'}")
                print("")


def main():
    parser = argparse.ArgumentParser(description="MIIT Pipeline 2: 车型详情归档（可恢复）")
    parser.add_argument("--brand", help="归档指定品牌 (如 零跑)")
    parser.add_argument("--batch", default=DEFAULT_BATCH)
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不执行")
    parser.add_argument("--all-missing", action="store_true",
                        help="归档所有有搜索结果但未归档的品牌")
    parser.add_argument("--retry-failed", action="store_true",
                        help="只补抓 TRANSIENT_ERROR / BLOCKED 车型（--no-cache 关闭缓存恢复）")
    parser.add_argument("--no-cache", action="store_true",
                        help="抓取失败时不要从原始页面缓存恢复")
    parser.add_argument("--retries", type=int, default=MAX_RETRIES,
                        help=f"瞬态失败最大重试次数 (默认 {MAX_RETRIES})")
    args = parser.parse_args()

    data = load_scan(args.batch)
    brands = data["brands"]
    state = FetchState(args.batch)
    _prime_session(args.batch)

    if args.retry_failed:
        targets = state.retry_queue(brands)
        if args.brand:
            targets = [(b, m) for b, m in targets if b["catalog"] == args.brand]
        if not targets:
            print("无待补抓车型 (fetch_status 中无 TRANSIENT_ERROR / BLOCKED)")
            return
    else:
        if not args.all_missing and not args.brand:
            print("请指定 --brand 或 --all-missing 或 --retry-failed", file=sys.stderr)
            sys.exit(1)
        # 确定目标品牌
        if args.all_missing:
            # 车型详情 .md 不存在即属于未归档
            target_brands = []
            for b in brands:
                if b["total_count"] == 0:
                    continue
                missing = [
                    m for m in b["all_rows"]
                    if not detail_md_path(args.batch, m["cpxh"], m["cpmc"]).exists()
                ]
                if missing:
                    target_brands.append(b)
            target_brands = [b for b in target_brands if b["total_count"] > 0]
        else:
            target_brands = [b for b in brands if b["catalog"] == args.brand]
            if not target_brands:
                print(f"未找到品牌: {args.brand}", file=sys.stderr)
                sys.exit(1)
        targets = [(b, m) for b in target_brands for m in b["all_rows"]]

    mode = "[DRY RUN]" if args.dry_run else ""
    results = []
    try:
        cur_brand = None
        for b, model in targets:
            if b["catalog"] != cur_brand:
                cur_brand = b["catalog"]
                print(f"\n=== {cur_brand} ({b['total_count']}款) {mode}===")
            res = archive_model(model, state, str(cur_brand), batch=args.batch,
                                dry_run=args.dry_run, prefer_cache=not args.no_cache)
            results.append(res)
            if not args.dry_run:
                time.sleep(random.uniform(*REQUEST_INTERVAL))
    except KeyboardInterrupt:
        state.save()
        print("\n收到中断，已保存 checkpoint，可用 --retry-failed 继续", file=sys.stderr)
        sys.exit(130)

    state.save()
    if not args.dry_run:
        print_summary(results, args.batch)


if __name__ == "__main__":
    main()
