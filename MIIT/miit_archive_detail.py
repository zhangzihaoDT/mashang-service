#!/usr/bin/env python3
"""
MIIT Pipeline 2: 车型详情归档

从搜索结果中的 detail_url 抓取车型详情页，
提取参数、下载照片，归档为 409-品牌/ 文件夹。

用法:
  python3 miit_archive_detail.py --brand 小鹏        # 归档指定品牌
  python3 miit_archive_detail.py --brand 小鹏 --dry-run  # 预览
  python3 miit_archive_detail.py --all-missing      # 归档所有未归档品牌
"""

import argparse
import json
import re
import sys
from pathlib import Path

import requests

HERE = Path(__file__).parent
MIIT_BASE = "https://www.miit.gov.cn"

# 共享 Session（与 miit_search.py 保持一致）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/150.0.0.0 Safari/537.36",
    "Referer": "https://www.miit.gov.cn/datainfo/dljdclscqyjcpgg/"
               "xcpgs409dwdwe233/index.html",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Warm up
try:
    SESSION.get(
        "https://www.miit.gov.cn/datainfo/dljdclscqyjcpgg/"
        "xcpgs409dwdwe233/index.html",
        timeout=15,
    )
except Exception:
    pass


def load_scan(batch: str = "409") -> dict:
    path = HERE / f"scan_batch_{batch}.md"
    text = path.read_text(encoding="utf-8")
    m = re.search(r'```json\n(.+?)\n```', text, re.DOTALL)
    if not m:
        print(f"错误: {path} 中未找到 JSON 数据块", file=sys.stderr)
        sys.exit(1)
    return json.loads(m.group(1))


def fetch_detail_page(detail_url: str) -> str:
    full_url = MIIT_BASE + detail_url
    resp = SESSION.get(full_url, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_tables(html: str) -> list[dict]:
    """Parse all <table> in the MIIT detail page into structured dicts.

    Two table layouts occur:
      A) Interleaved <th>/<td> pairs per row (Tables 0, 1):
         <tr><th>key1:</th><td>val1</td><th>key2:</th><td>val2</td></tr>
      B) Header row (<th>...) + data row(s) (<td>...) (Tables 2, 3).
    """
    S = requests.Session()
    S.headers.update(HEADERS)
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


def download_photo(url: str, dest: Path):
    full_url = MIIT_BASE + url
    resp = SESSION.get(full_url, timeout=60, headers={
        "Referer": "https://www.miit.gov.cn/datainfo/dljdclscqyjcpgg/"
                   "xcpgs409dwdwe233/index.html",
    })
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def tables_to_md(tables: list[dict], model_id: str, product_name: str,
                 cpsb: str, qymc: str, detail_url: str, photos: list[dict]) -> str:
    brand_display = cpsb.replace("牌", "").strip()
    title = f"工信部第409批新车公示 — {cpsb}{product_name}"

    lines = [f"# {title}", "", "> 数据来源：工信部道路机动车辆生产企业及产品公告",
             "> 公示时间：2026-07-07", ""]

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
    lines.append(f"> 存档时间：2026-07-13")
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


def archive_model(model: dict, brand_dir: Path, dry_run: bool = False) -> bool:
    model_id = model["cpxh"]
    product_name = model["cpmc"]
    cpsb = model["cpsb"]
    qymc = model["qymc"]
    detail_url = model.get("detail_url", "")

    if not detail_url:
        print(f"  ⚠ {model_id}: 无 detail_url，跳过")
        return False

    md_filename = f"{model_id}-{product_name}.md"
    image_dir = brand_dir / model_id
    md_path = brand_dir / md_filename

    if md_path.exists():
        print(f"  - {model_id}: 已存在，跳过")
        return False

    print(f"  → {model_id} ({product_name})")
    if dry_run:
        return True

    # Fetch detail page
    try:
        html = fetch_detail_page(detail_url)
    except Exception as e:
        print(f"    ✗ 抓取失败: {e}")
        return False

    # Parse tables
    tables = parse_tables(html)
    if not tables:
        print(f"    ✗ 未解析到表格数据")
        return False

    # Extract photos (links only, for the .md)
    photos = extract_photos(html)

    # Generate .md
    md_content = tables_to_md(tables, model_id, product_name, cpsb, qymc,
                               detail_url, photos)
    image_dir.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_content, encoding="utf-8")

    # Download photos
    view_names = ["左-右部照片.jpg", "后部照片.jpg", "选装照片1.jpg"]
    for i, photo in enumerate(photos[:3]):
        if i >= 3:
            break
        dest = image_dir / view_names[i]
        if not dest.exists():
            try:
                download_photo(photo["url"], dest)
                print(f"    📷 {view_names[i]}")
            except Exception as e:
                print(f"    ⚠ 照片{i+1}下载失败: {e}")

    print(f"    ✓ 归档完成")
    return True


def main():
    parser = argparse.ArgumentParser(description="MIIT Pipeline 2: 车型详情归档")
    parser.add_argument("--brand", help="归档指定品牌 (如 小鹏)")
    parser.add_argument("--batch", default="409")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不执行")
    parser.add_argument("--all-missing", action="store_true",
                        help="归档所有有搜索结果但未归档的品牌")
    args = parser.parse_args()

    data = load_scan(args.batch)
    brands = data["brands"]

    if not args.all_missing and not args.brand:
        print("请指定 --brand 或 --all-missing", file=sys.stderr)
        sys.exit(1)

    # 确定目标品牌
    if args.all_missing:
        # 找到所有有数据但无对应 409-xxx 目录的品牌
        existing_dirs = {d.name for d in HERE.glob("409-*") if d.is_dir()}
        target_brands = []
        for b in brands:
            if b["total_count"] == 0:
                continue
            dir_name = f"409-{b['catalog']}"
            if dir_name not in existing_dirs:
                target_brands.append(b)
        target_brands = [b for b in target_brands if b["total_count"] > 0]
    else:
        target_brands = [b for b in brands if b["catalog"] == args.brand]
        if not target_brands:
            print(f"未找到品牌: {args.brand}", file=sys.stderr)
            sys.exit(1)

    mode = "[DRY RUN]" if args.dry_run else ""
    for b in target_brands:
        brand_dir = HERE / f"409-{b['catalog']}"
        print(f"\n=== {b['catalog']} ({b['total_count']}款) {mode}===")
        for model in b["all_rows"]:
            archive_model(model, brand_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
