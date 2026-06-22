#!/usr/bin/env python
"""
解析已下载的 MIIT 批次附件，提取结构化产品信息。

用法:
  python mashang_workspace/research_scripts/miit_new_car/parse_products.py --batch 408
  python mashang_workspace/research_scripts/miit_new_car/parse_products.py --batch 408 --format json
  python mashang_workspace/research_scripts/miit_new_car/parse_products.py --batch 408 --output-dir outputs/
"""

import sys, json, csv, re
import argparse
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Optional

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT))

RAW_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "raw"
PARSED_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "parsed"

TARGET_FIELDS = [
    "batch_no", "batch_status", "publish_date",
    "publicity_start", "publicity_end",
    "enterprise_name", "brand", "product_model", "vehicle_name",
    "product_type", "energy_type", "fuel_type", "battery_type",
    "range_km", "motor_power", "dimensions",
    "source_url", "asset_url", "ingested_at",
]


class _TableParser(HTMLParser):
    """从产品公示 HTML 中提取表格数据。"""

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: str = ""
        self._in_td = False
        self._in_th = False
        self._in_table = False
        self._table_depth = 0
        self._skip = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._in_table = True
            self._table_depth += 1
        if self._in_table and tag in ("td", "th"):
            if tag == "td":
                self._in_td = True
            else:
                self._in_th = True
            self._current_cell = ""
            cls = a.get("class", "")
            style = a.get("style", "")
            if "display:none" in style or "hidden" in cls:
                self._skip = True
            else:
                self._skip = False

    def handle_endtag(self, tag):
        if tag == "table" and self._in_table:
            self._table_depth -= 1
            if self._table_depth == 0:
                self._in_table = False
        if tag in ("td", "th") and self._in_table:
            val = self._current_cell.strip().replace("\xa0", " ").replace("\u3000", " ")
            if self._in_td or self._in_th:
                self._current_row.append(val)
            self._in_td = False
            self._in_th = False
            self._skip = False
        if tag == "tr" and self._in_table and self._current_row:
            self.rows.append(self._current_row)
            self._current_row = []

    def handle_data(self, data):
        if (self._in_td or self._in_th) and not self._skip:
            self._current_cell += data


def _parse_html_listing(filepath: Path) -> list[dict]:
    """尝试从附件 HTML 文件中解析产品表格。"""
    html = filepath.read_text("utf-8", errors="replace")
    parser = _TableParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.rows


def _normalize_enterprise(raw: str) -> dict:
    """从企业全称中提取品牌和产品名。"""
    raw = raw.strip().replace("\u3000", " ").replace("\xa0", " ")
    known_brands = [
        "智己", "理想", "问界", "小米", "蔚来", "小鹏", "极氪", "阿维塔",
        "深蓝", "零跑", "腾势", "方程豹", "比亚迪", "特斯拉",
        "宝马", "奔驰", "奥迪", "大众", "丰田", "本田", "日产",
        "吉利", "长城", "长安", "奇瑞", "广汽", "上汽", "一汽", "东风",
        "红旗", "领克", "极狐", "岚图", "哪吒", "高合", "飞凡",
    ]
    brand = ""
    for b in known_brands:
        if b in raw:
            brand = b
            break
    return {
        "enterprise_name": raw,
        "brand": brand,
    }


def parse_batch(
    batch_no: int,
    output_dir: Optional[Path] = None,
) -> list[dict]:
    """解析指定批次的附件，返回结构化产品列表。"""
    raw_dir = RAW_BASE / f"batch_{batch_no}"
    if not raw_dir.exists():
        raise FileNotFoundError(f"批次原始数据目录不存在: {raw_dir}")

    metadata_file = raw_dir / "metadata.json"
    if not metadata_file.exists():
        raise FileNotFoundError(f"批次 metadata 不存在: {metadata_file}")

    with open(metadata_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    products: list[dict] = []
    att_dir = raw_dir / "attachments"
    ingested_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if att_dir.exists():
        for fpath in sorted(att_dir.iterdir()):
            if fpath.suffix in (".html", ".htm"):
                rows = _parse_html_listing(fpath)
                if rows:
                    header = rows[0] if rows else []
                    for row in rows[1:]:
                        ent = _normalize_enterprise(row[0] if row else "")
                        prod = {
                            "batch_no": batch_no,
                            "batch_status": meta.get("status", ""),
                            "publish_date": meta.get("publish_date", ""),
                            "publicity_start": "",
                            "publicity_end": "",
                            "enterprise_name": ent["enterprise_name"],
                            "brand": ent["brand"],
                            "product_model": row[1] if len(row) > 1 else "",
                            "vehicle_name": row[2] if len(row) > 2 else "",
                            "product_type": "",
                            "energy_type": "",
                            "fuel_type": "",
                            "battery_type": "",
                            "range_km": "",
                            "motor_power": "",
                            "dimensions": "",
                            "source_url": meta.get("detail_url", ""),
                            "asset_url": fpath.name,
                            "ingested_at": ingested_at,
                        }
                        products.append(prod)
                else:
                    # Save raw text fallback
                    text = fpath.read_text("utf-8", errors="replace")[:500]
                    products.append({
                        "batch_no": batch_no,
                        "batch_status": meta.get("status", ""),
                        "publish_date": meta.get("publish_date", ""),
                        "publicity_start": "",
                        "publicity_end": "",
                        "enterprise_name": "",
                        "brand": "",
                        "product_model": "",
                        "vehicle_name": "",
                        "product_type": f"[未解析] {fpath.name}",
                        "energy_type": "",
                        "fuel_type": "",
                        "battery_type": "",
                        "range_km": "",
                        "motor_power": "",
                        "dimensions": "",
                        "source_url": meta.get("detail_url", ""),
                        "asset_url": fpath.name,
                        "ingested_at": ingested_at,
                    })

    if not products:
        products.append({
            "batch_no": batch_no,
            "batch_status": meta.get("status", ""),
            "publish_date": meta.get("publish_date", ""),
            "publicity_start": "",
            "publicity_end": "",
            "enterprise_name": "",
            "brand": "",
            "product_model": "",
            "vehicle_name": "",
            "product_type": "[未解析] 无产品数据",
            "energy_type": "",
            "fuel_type": "",
            "battery_type": "",
            "range_km": "",
            "motor_power": "",
            "dimensions": "",
            "source_url": meta.get("detail_url", ""),
            "asset_url": "",
            "ingested_at": ingested_at,
        })

    out_dir = output_dir or PARSED_BASE
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"batch_{batch_no}_products"

    # CSV
    csv_path = out_dir / f"{prefix}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=TARGET_FIELDS)
        w.writeheader()
        w.writerows(products)
    print(f"  CSV: {csv_path} ({len(products)} 行)")

    # JSON
    json_path = out_dir / f"{prefix}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {json_path}")

    # Markdown
    md_path = out_dir / f"{prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 第 {batch_no} 批 {meta.get('status', '')} 产品清单\n\n")
        status_label = "公示" if meta.get("status") == "publicity" else "正式发布"
        f.write(f"- 状态: {status_label}\n")
        f.write(f"- 发布日期: {meta.get('publish_date', '')}\n")
        f.write(f"- 来源: {meta.get('detail_url', '')}\n")
        f.write(f"- 产品数: {len(products)}\n\n")
        f.write(f"| 企业名称 | 品牌 | 产品型号 | 车辆名称 |\n")
        f.write(f"|---------|------|---------|--------|\n")
        for p in products:
            f.write(f"| {p['enterprise_name']} | {p['brand']} | {p['product_model']} | {p['vehicle_name']} |\n")
    print(f"  Markdown: {md_path}")

    return products


def main():
    p = argparse.ArgumentParser(description="解析 MIIT 批次附件为结构化产品信息")
    p.add_argument("--batch", type=int, required=True, help="批次号")
    p.add_argument("--output-dir", type=str, help="输出目录")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    try:
        products = parse_batch(
            batch_no=args.batch,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        print(json.dumps(products, ensure_ascii=False, indent=2))
        return

    brands = set(p["brand"] for p in products if p["brand"])
    print(f"\n[Summary] 第 {args.batch} 批解析结果")
    print(f"  产品数: {len(products)}")
    print(f"  涉及品牌: {', '.join(sorted(brands)) if brands else '未识别'}")
    parsed = [p for p in products if not p["product_type"].startswith("[未解析]")]
    print(f"  已解析: {len(parsed)}")
    unparsed = [p for p in products if p["product_type"].startswith("[未解析]")]
    if unparsed:
        print(f"  未解析: {len(unparsed)}")


if __name__ == "__main__":
    main()
