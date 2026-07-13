#!/usr/bin/env python3
"""
MIIT 车船税目录解析器

功能：将 textutil 转换后的车船税 .txt 解析为结构化 JSON + Markdown。

数据格式说明：
- textutil 将 Word 表格导出为 \x07 分隔的扁平文本
- 每个表格 = 一行，以"序号"开头，包含 header + 所有数据行
- 字段用 \x07 分隔，记录间无显式分隔符
- 空单元格为连续两个 \x07
- 尾部空列：每个表格右侧有一列空单元格（Word 导出残余）

用法:
  python3 parse_车船税.py --input 车型清单.txt --output 车型清单
  python3 parse_车船税.py --input 车型清单.txt --output outputs/tables/车型清单
"""

import argparse
import json
import re
import sys
from pathlib import Path
from collections import OrderedDict

SEP = '\x07'

# ── 各分类的字段 schema ──────────────────────────────────────────

SECTION_SCHEMAS = OrderedDict([
    ("节能乘用车", {
        "header": "（一）乘用车",
        "schema": [
            "序号", "企业名称", "通用名称", "车辆型号", "排量_ml",
            "额定载客人数", "型式", "档位数", "整车整备质量_kg",
            "排放标准", "综合燃料消耗量_L_per_100km"
        ]
    }),
    ("天然气轻型商用车", {
        "header": "1.天然气轻型商用车",
        "schema": [
            "序号", "企业名称", "商标", "车辆型号", "产品名称",
            "排放标准", "燃料种类"
        ]
    }),
    ("天然气重型商用车", {
        "header": "1.天然气重型商用车",
        "schema": [
            "序号", "企业名称", "商标", "车辆型号", "产品名称",
            "排放标准", "燃料种类"
        ]
    }),
    ("汽柴油重型货车", {
        "header": "（1）货车",
        "schema": [
            "序号", "企业名称", "商标", "车辆型号", "产品名称",
            "最大设计总质量_kg", "整车整备质量_kg", "排放标准",
            "燃料种类", "综合工况燃料消耗量_L_per_100km"
        ]
    }),
    ("插电式混合动力乘用车", {
        "header": "（一）插电式混合动力乘用车",
        "schema": [
            "序号", "企业名称", "商标", "产品型号", "通用名称",
            "纯电动续驶里程_km", "燃料消耗量_L_per_100km", "发动机排量_ml",
            "整车整备质量_kg", "动力蓄电池总质量_kg", "动力蓄电池总能量_kWh", "备注"
        ]
    }),
    ("纯电动商用车", {
        "header": "2.纯电动商用车",
        "schema": [
            "序号", "企业名称", "商标", "产品型号", "产品名称",
            "纯电动续驶里程_km", "整车整备质量_kg", "动力蓄电池组总质量_kg",
            "动力蓄电池组总能量_kWh", "备注"
        ]
    }),
    ("插电式混合动力商用车", {
        "header": "（三）插电式混合动力商用车",
        "schema": [
            "序号", "企业名称", "商标", "产品型号", "产品名称",
            "纯电动续驶里程_km", "燃料消耗量_L_per_100km", "发动机排量_mL",
            "整车整备质量_kg", "动力蓄电池总质量_kg", "动力蓄电池总能量_kWh", "备注"
        ]
    }),
    ("燃料电池汽车", {
        "header": "（四）燃料电池汽车",
        "schema": [
            "序号", "企业名称", "商标", "产品型号", "产品名称",
            "纯电动续驶里程_km", "整车整备质量_kg", "燃料电池系统额定功率_kW",
            "驱动电机额定功率_kW", "备注"
        ]
    }),
])


def parse_txt(input_path: str) -> dict:
    """Main parse function: reads txt → structured dict"""
    raw = Path(input_path).read_text(encoding="utf-8")
    lines = raw.split('\n')

    section_names = list(SECTION_SCHEMAS.keys())

    data_line_indices = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("序号"):
            data_line_indices.append(i)

    result = {
        "title": "《享受车船税减免优惠的节约能源 使用新能源汽车车型目录》",
        "batch": "",
        "date": "",
        "section_order": section_names,
        "sections": {},
        "by_brand": {},
        "stats": {},
        "brands": [],
    }

    known_brands = set()

    for idx, section_name in enumerate(section_names):
        if idx >= len(data_line_indices):
            result["stats"][section_name] = 0
            result["sections"][section_name] = {
                "records": [], "count": 0,
                "schema": SECTION_SCHEMAS[section_name]["schema"]
            }
            continue

        line_idx = data_line_indices[idx]
        line = lines[line_idx]
        schema = SECTION_SCHEMAS[section_name]["schema"]
        records = _parse_data_line(line, schema)

        result["sections"][section_name] = {
            "records": records,
            "count": len(records),
            "schema": schema,
        }
        result["stats"][section_name] = len(records)

        for rec in records:
            brand = rec.get("企业名称", "")
            if brand:
                brand = brand.strip()
                known_brands.add(brand)
                result["by_brand"].setdefault(brand, {})
                result["by_brand"][brand].setdefault(section_name, [])
                result["by_brand"][brand][section_name].append(rec)

    result["brands"] = sorted(known_brands)
    result["stats"]["total_brands"] = len(known_brands)
    result["stats"]["total_records"] = sum(
        v for k, v in result["stats"].items() if not k.startswith("total_")
    )
    return result


def _parse_data_line(line: str, schema: list[str]) -> list[OrderedDict]:
    """Parse one data line (header + all rows) into structured records."""
    cells = [c.strip() for c in line.strip().split(SEP)]
    row_width = len(schema) + 1

    if len(cells) <= row_width:
        return []

    data_cells = cells[row_width:]
    rows = _group_into_rows(data_cells, row_width)
    rows = _apply_inheritance(rows)

    records = []
    for row in rows:
        clean_row = row[:len(schema)]
        record = OrderedDict()
        for i, key in enumerate(schema):
            record[key] = clean_row[i] if i < len(clean_row) and clean_row[i] else None
        records.append(record)
    return records


def _group_into_rows(data_cells: list[str], row_width: int) -> list[list[str]]:
    rows, current = [], []
    for cell in data_cells:
        current.append(cell)
        if len(current) == row_width:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    return rows


def _apply_inheritance(rows: list[list[str]]) -> list[list[str]]:
    """Word-style: empty cell inherits from previous row."""
    if not rows:
        return rows
    max_cols = max(len(r) for r in rows)
    for col_idx in range(max_cols):
        last_value = None
        for row in rows:
            if col_idx < len(row) and row[col_idx]:
                last_value = row[col_idx]
            elif col_idx < len(row) and last_value is not None:
                row[col_idx] = last_value
    return rows


# ── Markdown Generator ───────────────────────────────────────────

FIELD_DISPLAY = {
    "序号": "#", "企业名称": "企业", "商标": "商标",
    "通用名称": "通用名称", "产品名称": "产品名称",
    "车辆型号": "型号", "产品型号": "产品型号",
    "排量_ml": "排量(ml)", "发动机排量_ml": "排量(ml)", "发动机排量_mL": "排量(mL)",
    "额定载客人数": "载客", "型式": "型式", "档位数": "档位",
    "整车整备质量_kg": "整备(kg)", "排放标准": "排放标准",
    "综合燃料消耗量_L_per_100km": "油耗(L/100km)",
    "燃料消耗量_L_per_100km": "油耗(L/100km)",
    "综合工况燃料消耗量_L_per_100km": "油耗(L/100km)",
    "纯电动续驶里程_km": "纯电续航(km)",
    "动力蓄电池总质量_kg": "电池质量(kg)",
    "动力蓄电池组总质量_kg": "电池质量(kg)",
    "动力蓄电池总能量_kWh": "电池能量(kWh)",
    "动力蓄电池组总能量_kWh": "电池能量(kWh)",
    "最大设计总质量_kg": "最大总质量(kg)",
    "燃料电池系统额定功率_kW": "FC功率(kW)",
    "驱动电机额定功率_kW": "电机功率(kW)",
    "燃料种类": "燃料", "备注": "备注",
}

FIELD_PREFERRED = [
    "序号", "企业名称", "商标", "通用名称", "产品名称", "车辆型号", "产品型号",
    "纯电动续驶里程_km",
    "排量_ml", "发动机排量_ml", "发动机排量_mL",
    "燃料消耗量_L_per_100km", "综合燃料消耗量_L_per_100km",
    "整车整备质量_kg",
    "动力蓄电池总能量_kWh", "动力蓄电池组总能量_kWh",
    "动力蓄电池总质量_kg", "动力蓄电池组总质量_kg",
    "燃料电池系统额定功率_kW", "驱动电机额定功率_kW",
    "额定载客人数", "排放标准", "燃料种类",
    "最大设计总质量_kg", "综合工况燃料消耗量_L_per_100km", "备注",
]

KEY_FIELDS_FOR_BRAND = [
    "通用名称", "产品名称", "产品型号", "商标",
    "纯电动续驶里程_km", "燃料消耗量_L_per_100km",
    "发动机排量_ml", "整车整备质量_kg",
    "动力蓄电池总能量_kWh", "动力蓄电池总质量_kg",
    "动力蓄电池组总能量_kWh", "动力蓄电池组总质量_kg",
    "燃料电池系统额定功率_kW", "驱动电机额定功率_kW",
    "排量_ml", "综合燃料消耗量_L_per_100km",
]


def generate_markdown(data: dict) -> str:
    lines = []
    lines.append(f"# {data['title']}")
    lines.append("")
    lines.append(f"**批次**: {data['batch']}  |  **公示日期**: {data['date']}")
    lines.append("")

    lines.append("## 数据概览")
    lines.append("")
    lines.append("| 类别 | 车型数 |")
    lines.append("|------|-------|")
    for sec_name in data["section_order"]:
        cnt = data["stats"].get(sec_name, 0)
        if cnt > 0:
            lines.append(f"| {sec_name} | {cnt} |")
    lines.append(f"| **合计** | **{data['stats'].get('total_records', 0)}** |")
    lines.append("")
    lines.append(f"涉及品牌/企业: **{data['stats'].get('total_brands', 0)}** 家")
    lines.append("")
    lines.append(f"**品牌/企业列表**: {'、'.join(data.get('brands', []))}")
    lines.append("")

    lines.append("## 按品牌/企业索引")
    lines.append("")
    for brand in sorted(data["by_brand"].keys()):
        brand_data = data["by_brand"][brand]
        total_for_brand = sum(len(v) for v in brand_data.values())
        lines.append(f"### {brand}（共 {total_for_brand} 款）")
        lines.append("")
        for sec_name, records in brand_data.items():
            lines.append(f"**{sec_name}**: {len(records)} 款")
            lines.append("")
            sample = records[0]
            available = [f for f in KEY_FIELDS_FOR_BRAND if f in sample]
            if available:
                headers = [FIELD_DISPLAY.get(f, f) for f in available]
                lines.append(f"| {' | '.join(headers)} |")
                lines.append(f"|{'|'.join('---' for _ in available)}|")
                for rec in records:
                    vals = [str(rec.get(f, "") or "-") for f in available]
                    lines.append(f"| {' | '.join(vals)} |")
                lines.append("")

    lines.append("---")
    lines.append("## 完整数据（按分类）")
    lines.append("")
    for sec_name in data["section_order"]:
        sec = data["sections"].get(sec_name, {})
        records = sec.get("records", [])
        if not records:
            continue
        schema = sec.get("schema", [])
        lines.append(f"### {sec_name}（{len(records)} 条）")
        lines.append("")
        table_fields = [f for f in FIELD_PREFERRED if f in schema]
        if table_fields:
            headers = [FIELD_DISPLAY.get(f, f) for f in table_fields]
            lines.append(f"| {' | '.join(headers)} |")
            lines.append(f"|{'|'.join('---' for _ in table_fields)}|")
            for rec in records:
                vals = [str(rec.get(f, "") or "-") for f in table_fields]
                lines.append(f"| {' | '.join(vals)} |")
        lines.append("")

    lines.append("---")
    lines.append("> 来源: 工信部装备工业一司")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description="MIIT 车船税目录解析器")
    parser.add_argument("--input", required=True,
                        help="textutil 转换后的 .txt 文件路径")
    parser.add_argument("--output", required=True,
                        help="输出文件前缀（不含后缀），如 outputs/tables/车型清单")
    parser.add_argument("--batch", default="",
                        help="批次号，如 第八十八批")
    parser.add_argument("--date", default="",
                        help="公示日期，如 2026-07-10")
    args = parser.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    data = parse_txt(args.input)
    if args.batch:
        data["batch"] = args.batch
    if args.date:
        data["date"] = args.date

    json_path = out.with_suffix(".json")
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON → {json_path}")

    md = generate_markdown(data)
    md_path = out.with_suffix(".md")
    md_path.write_text(md, encoding="utf-8")
    print(f"MD   → {md_path}")

    print(f"\n总记录数: {data['stats'].get('total_records', 0)}")
    print(f"品牌/企业数: {data['stats'].get('total_brands', 0)}")
    for sec_name in data["section_order"]:
        cnt = data["stats"].get(sec_name, 0)
        if cnt > 0:
            print(f"  {sec_name}: {cnt}")


if __name__ == "__main__":
    main()
