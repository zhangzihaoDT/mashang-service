#!/usr/bin/env python
"""
公告产品清单主表结构化。

从 HTML 表格、DOC 抽取文本、DOCX 抽取文本中解析产品清单。
目标是抽取"有哪些企业、哪些产品、哪些型号进入该批公告"。

用法:
  python parse_product_list.py --batch 407
  python parse_product_list.py --batch 407 --format json
"""

import sys, json, csv, re, argparse
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime, timezone
from typing import Optional

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

RAW_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "raw"
EXTRACTED_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "extracted"
PRODUCT_LIST_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "product_list"

PRODUCT_LIST_FIELDS = [
    "batch_no", "batch_status", "publish_date",
    "enterprise_name", "brand", "product_name", "product_model",
    "product_category", "announcement_type",
    "source_attachment", "source_attachment_title",
    "source_text_path", "source_text_snippet",
    "parse_method", "parse_confidence", "ingested_at",
]

RE_TAX_KEYWORDS = re.compile(r"(购置税|车船税|减免|免税|税收)", re.IGNORECASE)
RE_TABLE_ROW = re.compile(r"^\s*\d+\s+", re.MULTILINE)


class _HtmlTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell = ""
        self._in_td = False
        self._in_th = False
        self._in_table = False
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._in_table = True
            self._depth += 1
        if self._in_table and tag in ("td", "th"):
            self._in_td = tag == "td"
            self._in_th = tag == "th"
            self._cell = ""

    def handle_endtag(self, tag):
        if tag == "table":
            self._depth -= 1
            if self._depth == 0:
                self._in_table = False
        if tag in ("td", "th") and self._in_table:
            val = self._cell.strip().replace("\xa0", " ").replace("\u3000", " ")
            self._row.append(val)
            self._in_td = False
            self._in_th = False
        if tag == "tr" and self._in_table and self._row:
            self.rows.append(self._row)
            self._row = []

    def handle_data(self, data):
        if self._in_td or self._in_th:
            self._cell += data


KNOWN_BRANDS = {
    "智己", "理想", "问界", "小米", "蔚来", "小鹏", "极氪", "阿维塔",
    "深蓝", "零跑", "腾势", "方程豹", "比亚迪", "特斯拉",
    "宝马", "奔驰", "奥迪", "大众", "丰田", "本田", "日产",
    "吉利", "长城", "长安", "奇瑞", "广汽", "上汽", "一汽", "东风",
    "红旗", "领克", "极狐", "岚图", "哪吒", "高合", "飞凡",
    "北京", "福田", "江淮", "江铃", "庆铃", "重汽", "陕汽",
    "宇通", "金龙", "中通", "安凯", "申沃",
}


def _detect_announcement_type(title: str, filename: str, text_snippet: str) -> str:
    combined = f"{title} {filename} {text_snippet[:200]}"
    if RE_TAX_KEYWORDS.search(combined):
        return "tax_exemption"
    if "变更" in combined or "扩展" in combined:
        return "change_extension"
    if "新产品" in combined or "新车" in combined:
        return "new_product"
    return "unknown"


def _guess_brand(enterprise: str, product_name: str) -> str:
    for b in KNOWN_BRANDS:
        if b in enterprise or b in product_name:
            return b
    return ""


def _parse_text_table(text: str) -> list[dict]:
    """从纯文本中尝试按行解析产品记录。"""
    records = []
    lines = text.split("\n")
    header_keywords = {"企业名称", "产品商标", "产品名称", "产品型号", "车辆型号", "产品类别"}
    header_indices: dict[str, int] = {}
    started = False

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        if not started:
            matches = [kw for kw in header_keywords if kw in line]
            if len(matches) >= 2:
                started = True
                fields = re.split(r"\s{2,}|\t", line)
                for j, f in enumerate(fields):
                    for kw in header_keywords:
                        if kw in f:
                            header_indices[kw] = j
                            break
            continue

        if line.startswith("---") or line.startswith("=="):
            continue

        fields = re.split(r"\s{2,}|\t", line)
        if len(fields) < 2:
            continue

        enterprise = fields[header_indices.get("企业名称", 0)] if "企业名称" in header_indices else ""
        product_name = fields[header_indices.get("产品名称", 1)] if "产品名称" in header_indices else ""
        product_model = fields[header_indices.get("产品型号", 2)] if "产品型号" in header_indices else ""
        product_category = fields[header_indices.get("产品类别", 3)] if "产品类别" in header_indices else ""

        if enterprise or product_name or product_model:
            records.append({
                "enterprise_name": enterprise,
                "brand": _guess_brand(enterprise, product_name),
                "product_name": product_name,
                "product_model": product_model,
                "product_category": product_category,
            })

    return records


def _parse_html_rows(rows: list[list[str]]) -> list[dict]:
    records = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        enterprise = row[0] if len(row) > 0 else ""
        product_name = row[2] if len(row) > 2 else ""
        product_model = row[1] if len(row) > 1 else ""
        product_category = row[3] if len(row) > 3 else ""
        records.append({
            "enterprise_name": enterprise,
            "brand": _guess_brand(enterprise, product_name),
            "product_name": product_name,
            "product_model": product_model,
            "product_category": product_category,
        })
    return records


def parse_product_list(
    batch_no: int,
    output_dir: Optional[Path] = None,
) -> list[dict]:
    raw_dir = RAW_BASE / f"batch_{batch_no}"
    if not raw_dir.exists():
        raise FileNotFoundError(f"批次原始数据目录不存在: {raw_dir}")

    meta_path = raw_dir / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata 不存在: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    ingested_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text_dir = EXTRACTED_BASE / "text" / f"batch_{batch_no}"
    att_dir = raw_dir / "attachments"

    products: list[dict] = []
    seen_keys: set[str] = set()

    # Parse attachments
    if att_dir.exists():
        for fpath in sorted(att_dir.iterdir()):
            if not fpath.is_file():
                continue

            ann_type = _detect_announcement_type("", fpath.name, "")
            if ann_type == "tax_exemption":
                continue

            text_snippet = ""
            text_path_candidate = None
            records = []

            if fpath.suffix in (".html", ".htm"):
                html = fpath.read_text("utf-8", errors="replace")
                parser = _HtmlTableParser()
                try:
                    parser.feed(html)
                except Exception:
                    pass
                if parser.rows:
                    records = _parse_html_rows(parser.rows)
                    parse_method = "html_table"
                else:
                    parse_method = "html_fallback"

            elif fpath.suffix == ".txt":
                text = fpath.read_text("utf-8", errors="replace")
                text_snippet = text[:200]
                records = _parse_text_table(text)
                parse_method = "text_parse"

            elif fpath.suffix == ".docx":
                text = _read_docx_text(fpath)
                text_snippet = text[:200]
                records = _parse_text_table(text)
                parse_method = "docx_text_parse"

            elif fpath.suffix == ".doc":
                text_path_candidate = text_dir / f"{fpath.stem}.txt"
                if text_path_candidate.exists():
                    text = text_path_candidate.read_text("utf-8", errors="replace")
                    text_snippet = text[:200]
                    records = _parse_text_table(text)
                    parse_method = "doc_text_parse"
                else:
                    parse_method = "no_text"

            else:
                parse_method = "skipped"

            if records:
                for rec in records:
                    key = f"{batch_no}|{rec['enterprise_name']}|{rec['product_model']}|{rec['product_name']}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    products.append({
                        "batch_no": batch_no,
                        "batch_status": meta.get("status", ""),
                        "publish_date": meta.get("publish_date", ""),
                        "enterprise_name": rec["enterprise_name"],
                        "brand": rec["brand"],
                        "product_name": rec["product_name"],
                        "product_model": rec["product_model"],
                        "product_category": rec["product_category"],
                        "announcement_type": _detect_announcement_type("", fpath.name, text_snippet),
                        "source_attachment": fpath.name,
                        "source_attachment_title": "",
                        "source_text_path": str(text_path_candidate) if text_path_candidate else "",
                        "source_text_snippet": text_snippet[:300],
                        "parse_method": parse_method,
                        "parse_confidence": "high" if parse_method in ("html_table",) else "medium",
                        "ingested_at": ingested_at,
                    })
            else:
                # Record as unsourced row
                key = f"{batch_no}||{fpath.name}|"
                if key not in seen_keys:
                    seen_keys.add(key)
                    products.append({
                        "batch_no": batch_no,
                        "batch_status": meta.get("status", ""),
                        "publish_date": meta.get("publish_date", ""),
                        "enterprise_name": "",
                        "brand": "",
                        "product_name": "",
                        "product_model": "",
                        "product_category": "",
                        "announcement_type": _detect_announcement_type("", fpath.name, text_snippet),
                        "source_attachment": fpath.name,
                        "source_attachment_title": "",
                        "source_text_path": str(text_path_candidate) if text_path_candidate else "",
                        "source_text_snippet": text_snippet[:300],
                        "parse_method": parse_method,
                        "parse_confidence": "low",
                        "ingested_at": ingested_at,
                    })

    out_dir = output_dir or PRODUCT_LIST_BASE
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"batch_{batch_no}_product_list"

    csv_path = out_dir / f"{prefix}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=PRODUCT_LIST_FIELDS)
        w.writeheader()
        w.writerows(products)
    print(f"  CSV: {csv_path} ({len(products)} 行)")

    json_path = out_dir / f"{prefix}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {json_path}")

    md_path = out_dir / f"{prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 第 {batch_no} 批产品清单\n\n")
        f.write(f"- 状态: {meta.get('status', '')}\n")
        f.write(f"- 发布日期: {meta.get('publish_date', '')}\n")
        f.write(f"- 记录数: {len(products)}\n\n")
        f.write(f"| 企业名称 | 品牌 | 产品名称 | 产品型号 | 来源 |\n")
        f.write(f"|---------|------|---------|--------|------|\n")
        for p in products:
            src = p.get("source_attachment", "")[:15]
            f.write(f"| {p['enterprise_name'][:20]} | {p['brand']} | {p['product_name'][:20]} | {p['product_model'][:20]} | {src} |\n")
    print(f"  Markdown: {md_path}")

    return products


def _read_docx_text(fpath: Path) -> str:
    import zipfile
    from xml.parsers.expat import ParserCreate
    try:
        with zipfile.ZipFile(fpath, "r") as z:
            if "word/document.xml" not in z.namelist():
                return ""
            xml_bytes = z.read("word/document.xml")
            xml_text = xml_bytes.decode("utf-8", errors="replace")
    except Exception:
        return ""

    texts: list[str] = []
    in_text = False
    buf = ""

    def start(name, attrs):
        nonlocal in_text, buf
        if name == "w:t":
            in_text = True
            buf = ""

    def end(name):
        nonlocal in_text, buf
        if name == "w:t" and in_text:
            texts.append(buf)
            in_text = False
        if name == "w:p":
            texts.append("\n")

    def char_data(data):
        nonlocal buf
        if in_text:
            buf += data

    try:
        parser = ParserCreate()
        parser.StartElementHandler = start
        parser.EndElementHandler = end
        parser.CharacterDataHandler = char_data
        parser.Parse(xml_text, True)
    except Exception:
        pass

    return "".join(texts).strip()


def main():
    p = argparse.ArgumentParser(description="解析 MIIT 公告产品清单主表")
    p.add_argument("--batch", type=int, required=True, help="批次号")
    p.add_argument("--output-dir", type=str, help="输出目录")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    try:
        products = parse_product_list(
            batch_no=args.batch,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        print(json.dumps(products, ensure_ascii=False, indent=2))
        return

    print(f"\n[Summary] 第 {args.batch} 批产品清单")
    print(f"  记录数: {len(products)}")
    enterprises = set(p["enterprise_name"] for p in products if p["enterprise_name"])
    print(f"  企业数: {len(enterprises)}")


if __name__ == "__main__":
    main()
