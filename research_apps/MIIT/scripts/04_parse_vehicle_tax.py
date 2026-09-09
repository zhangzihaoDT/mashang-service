#!/usr/bin/env python3
"""
MIIT 车船税目录解析器（Pipeline P3）

功能：将 textutil 转换后的车船税 .txt 解析为结构化 JSON + Markdown。

数据格式说明：
- textutil 将 Word 表格导出为 \x07 分隔的扁平文本
- 每个表格 = 一行，以"序号"开头，包含 header + 所有数据行
- 字段用 \x07 分隔，记录间无显式分隔符
- 空单元格为连续两个 \x07
- 尾部空列：每个表格右侧有一列空单元格（Word 导出残余）

用法:
  python3 scripts/04_parse_vehicle_tax.py --input 车型清单.txt --output 车型清单_第89批车船税
  python3 scripts/04_parse_vehicle_tax.py --input 车型清单.txt --output 车型清单_第89批车船税 --batch "第八十九批"

相对路径的 --output 前缀将落在 data/vehicle_tax/ 下。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from collections import OrderedDict

from miit_paths import VEHICLE_TAX_DIR  # noqa: E402

SEP = '\x07'

# ── 各分类的字段 schema ──────────────────────────────────────────

SECTION_SCHEMAS: "OrderedDict[str, dict]" = OrderedDict([
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


def _detect_section(header_cells: list[str]) -> str | None:
    """根据数据行表头列判断所属分类（不依赖顺序，兼容缺省分类的批次）。

    表头列差异（从 .txt 实际导出列名归纳）：
      - 节能乘用车:  通用名称 + 车辆型号 + 排量(ml)（无 产品型号）
      - 天然气商用车: 车辆型号 + 产品名称 + 燃料种类（无 产品型号/通用名称）
      - 汽柴油货车:  最大设计总质量(kg)
      - 插混乘用车:  通用名称 + 产品型号 + 发动机排量(ml)（小写 l）
      - 纯电商用车:  动力蓄电池组总质量(kg)（带"组"）
      - 插混商用车:  产品名称 + 产品型号 + 发动机排量(mL)（大写 L）
      - 燃料电池:    燃料电池系统额定功率(kW)
    """
    head = "\t".join(header_cells[:24])
    if "燃料电池系统额定功率" in head:
        return "燃料电池汽车"
    if "动力蓄电池组总质量" in head:
        return "纯电动商用车"
    if "最大设计总质量" in head:
        return "汽柴油重型货车"
    if "通用名称" in head and "产品型号" in head:
        return "插电式混合动力乘用车"
    if "产品型号" in head and "发动机排量(mL)" in head:
        return "插电式混合动力商用车"
    if "通用名称" in head and "车辆型号" in head:
        return "节能乘用车"
    if "燃料种类" in head and "产品名称" in head:
        return "天然气"  # 轻型/重型同列名，按出现顺序解析
    return None


def _is_section_title(value: str) -> bool:
    """段标题杂项（如 '（二）重型商用车'）混在数据行尾部时识别丢弃。"""
    if not value:
        return False
    return any(ch in value for ch in "（）()一二三四五六七八九十、sectionTitle") and not value[0].isdigit()


def _extract_tables(lines: list[str]) -> list[tuple[str, list[str]]]:
    """将 txt 行流解析为 [(section, all_cells)]。

    textutil 对 Word 表格的导出有两种形态：
      - 89 批式：表头 + 全部数据挤在同一行（行以 "序号" 开头）
      - 90 批式：表头被拆成两行（"序号…" 行 + 以 "(" 开头的表头续行），
        数据全部跟在表头续行之后
    因此需要跨行累积表头，识别 section 后再由公共逻辑解析数据。

    天然气轻型/重型同列名，无法从表头区分，需要读取表格前的独立段标题
    （如 "1.天然气重型商用车"）。
    """
    tables: list[tuple[str, list[str]]] = []
    pending: dict | None = None  # {"sec": str|None, "cells": [str]}
    last_heading: str = ""

    def flush():
        nonlocal pending, last_heading
        if pending is None:
            return
        sec = pending["sec"]
        if sec is None:
            sec = _detect_section(pending["cells"])
        if sec == "天然气":
            heading = pending.get("heading", "")
            sec = ("天然气重型商用车" if "重型" in heading
                   else "天然气轻型商用车")
        if sec:
            tables.append((sec, pending["cells"]))
        pending = None

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        cells = [c.strip() for c in stripped.split(SEP)]

        if stripped.startswith("序号"):
            flush()
            pending = {
                "sec": _detect_section(cells),
                "cells": cells,
                "heading": last_heading,  # 表格开始时就快照其段标题
            }
            continue

        if pending is None:
            # 无活动表格时，独立段标题/散文行
            if SEP not in stripped:
                last_heading = stripped
            continue

        if SEP not in stripped:
            # 独立段标题（如 1.天然气重型商用车）：更新，供下一表格使用
            last_heading = stripped
            continue
        if stripped.startswith(("(", "（")):
            # 表头续行：并入 pending 表头后重试识别 section
            pending["cells"].extend(cells)
            if pending["sec"] is None:
                pending["sec"] = _detect_section(pending["cells"])
        else:
            # 数据续行（理论上 90 批应为表头续行携带全部数据）
            pending["cells"].extend(cells)

    flush()
    return tables


def parse_txt(input_path: str) -> dict:
    """Main parse function: reads txt → structured dict"""
    raw = Path(input_path).read_text(encoding="utf-8")
    lines = raw.split('\n')

    section_names = list(SECTION_SCHEMAS.keys())

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

    for section, all_cells in _extract_tables(lines):
        schema = SECTION_SCHEMAS.get(section, {}).get("schema", [])
        if not schema:
            continue
        records = _parse_data_cells(all_cells, schema)

        result["sections"][section] = {
            "records": records,
            "count": len(records),
            "schema": schema,
        }
        result["stats"][section] = len(records)

        for rec in records:
            brand = rec.get("企业名称", "")
            if brand:
                brand = brand.strip()
                known_brands.add(brand)
                result["by_brand"].setdefault(brand, {})
                result["by_brand"][brand].setdefault(section, [])
                result["by_brand"][brand][section].append(rec)

    # 未出现的分类补空结构，保持 section_order 完整
    for section_name in section_names:
        if section_name not in result["sections"]:
            result["sections"][section_name] = {
                "records": [], "count": 0,
                "schema": SECTION_SCHEMAS[section_name]["schema"],
            }
            result["stats"][section_name] = 0

    result["brands"] = sorted(known_brands)
    result["stats"]["total_brands"] = len(known_brands)
    result["stats"]["total_records"] = sum(
        v for k, v in result["stats"].items() if not k.startswith("total_")
    )
    return result


def _find_data_start(all_cells: list[str]) -> int:
    """定位第一条数据行起点。

    表头因跨行拆分宽度不固定（如 "序号…" 行 + "(…)" 续行），
    但任何表格第一条数据行都以纯整数"序号"开头，以此为可靠边界。
    """
    for i, cell in enumerate(all_cells):
        if cell and cell.isdigit():
            return i
    return len(all_cells)


def _parse_data_cells(all_cells: list[str], schema: list[str]) -> list[OrderedDict]:
    """从表格全量 cells（表头 + 数据）解析记录。

    数据区以第一个纯整数单元格（序号）作为起点，其后按固定行宽分组，
    兼顾拆行表头与合并单元格两种形态。
    """
    row_width = len(schema) + 1
    start = _find_data_start(all_cells)
    if start == 0 or len(all_cells) <= start + row_width:
        return []

    data_cells = all_cells[start:]
    rows = _group_into_rows(data_cells, row_width)
    rows = _apply_inheritance(rows)

    records: list[OrderedDict] = []
    for row in rows:
        clean_row = row[:len(schema)]
        record = OrderedDict()
        for i, key in enumerate(schema):
            record[key] = clean_row[i] if i < len(clean_row) and clean_row[i] else None
        seq = record.get("序号", "")
        if not seq or not seq[0].isdigit():
            continue  # 段标题杂项，非有效记录
        records.append(record)
    return records


def _group_into_rows(data_cells: list[str], row_width: int) -> list[list[str]]:
    rows, current = [], []
    for cell in data_cells:
        current.append(cell)
        if len(current) == row_width:
            rows.append(current)
            current = []
    # 丢弃末尾未满行：Word 导出尾部常混入下一节段标题或空单元格，
    # 继承填充后会形成读数错误的幽灵记录
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
                        help="输出文件前缀（不含后缀），如 batch_410/车型清单_第89批车船税")
    parser.add_argument("--batch", default="",
                        help="批次号，如 第八十八批")
    parser.add_argument("--date", default="",
                        help="公示日期，如 2026-07-10")
    args = parser.parse_args()

    out = Path(args.output)
    if not out.is_absolute():
        out = VEHICLE_TAX_DIR / out
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
