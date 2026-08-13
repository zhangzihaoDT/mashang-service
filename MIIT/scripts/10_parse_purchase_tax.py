#!/usr/bin/env python3
"""
MIIT 购置税目录解析器（Pipeline P3 同族的 regulatory source parser）

解析《减免车辆购置税的新能源汽车车型目录》附件（.doc → .txt）。
与 03_parse_vehicle_tax.py 同属 regulatory source parser。

实际结构（textutil 导出，\x07 扁平表格）：
  每行 = 表头（序号/汽车生产企业名称/车辆型号/通用名称/产品名称/续航/整备/电池...）
       + 重复数据组（企业名称/车辆型号/通用名称/产品名称/续航/整备/电池质量/电池能量/备注）

三种 schema（按表头签名识别，不按位置）：
  - 纯电动:      动力蓄电池组总质量（8 列组）
  - 插电混动:    发动机排量(mL)（9 列组）
  - 燃料电池:    燃料电池系统额定功率（7 列组）

关键字段（供 canonical enrichment）：
  车辆型号 → model_code；通用名称 → common_name
  纯电动续驶里程 / 整车整备质量 / 动力蓄电池组总质量 / 动力蓄电池组总能量

用法:
  python3 scripts/10_parse_purchase_tax.py --input 购置税.txt --output 车型清单_第32批购置税
  python3 scripts/10_parse_purchase_tax.py --input ... --output ... --batch "第三十二批" --date 2026-07-17
"""

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path

from miit_paths import VEHICLE_TAX_DIR  # noqa: E402

SEP = "\x07"

# 购置税目录 schema 定义（表头签名 → 组内字段名序列，组首为企业名）
# 组内字段相对偏移由表头行动态建立（见 _group_layout）
_PURCHASE_SECTIONS = OrderedDict([
    ("插电式混合动力汽车", {
        "signature": "发动机排量(mL)",
    }),
    ("燃料电池汽车", {
        "signature": "燃料电池系统额定功率",
    }),
    ("纯电动汽车", {
        "signature": "动力蓄电池组总质量",
    }),
])

# 表头字段名 → 组内语义字段名（用于输出记录的统一字段命名）
HEADER_FIELD_MAP = {
    "汽车生产企业名称": "汽车生产企业名称",
    "车辆型号": "车辆型号",
    "通用名称": "通用名称",
    "产品名称": "产品名称",
    "纯电动续驶里程(km)": "纯电动续驶里程_km",
    "燃料消耗量(L/100km)": "燃料消耗量_L_per_100km",
    "发动机排量(mL)": "发动机排量_mL",
    "整车整备质量(kg)": "整车整备质量_kg",
    "动力蓄电池组总质量(kg)": "动力蓄电池组总质量_kg",
    "动力蓄电池组总能量（kWh）": "动力蓄电池组总能量_kWh",
    "燃料电池系统额定功率(kW)": "燃料电池系统额定功率_kW",
    "驱动电机额定功率(kW)": "驱动电机额定功率_kW",
    "备注": "备注",
}

RE_ENTERPRISE = re.compile(r"(公司|厂|集团|有限)")


def _detect_section(header_cells: list[str]) -> str | None:
    head = "\t".join(header_cells[:24])
    for name, cfg in _PURCHASE_SECTIONS.items():
        if cfg["signature"] in head:
            return name
    return None


def _group_layout(header_cells: list[str]) -> tuple[int, list[tuple[int, str]]]:
    """返回 (企业名在组内的相对偏移, [(字段相对偏移, 输出字段名)...])。

    企业名列 = 组起始（偏移 0）；其余字段相对企业名偏移 = 表头索引 - 企业名表头索引。
    """
    ent_idx = None
    for i, c in enumerate(header_cells[:15]):
        if c == "汽车生产企业名称":
            ent_idx = i
            break
    if ent_idx is None:
        return 0, []
    layout = []
    for i, c in enumerate(header_cells[:15]):
        if c in HEADER_FIELD_MAP and c != "汽车生产企业名称":
            layout.append((i - ent_idx, HEADER_FIELD_MAP[c]))
    return 0, layout


def parse_txt(input_path: str) -> dict:
    raw = Path(input_path).read_text(encoding="utf-8")
    lines = raw.replace("\r\n", "\n").split("\n")

    result = {
        "title": "《减免车辆购置税的新能源汽车车型目录》",
        "batch": "",
        "date": "",
        "section_order": list(_PURCHASE_SECTIONS.keys()),
        "sections": {},
        "stats": {},
    }
    for name in _PURCHASE_SECTIONS:
        result["sections"][name] = {"records": []}

    for line in lines:
        s = line.strip()
        m = re.search(r"（第([一二三四五六七八九十\d]+)批）", s)
        if m and "购置税" in s:
            result["batch"] = m.group(1)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
        if m and not result["date"]:
            result["date"] = m.group(1)

    for line in lines:
        raw_line = line.strip()
        if not raw_line or SEP not in raw_line:
            continue
        cells = [c.strip() for c in raw_line.split(SEP)]
        if not cells or cells[0] != "序号":
            continue

        section = _detect_section(cells)
        if not section:
            continue
        ent_rel, layout = _group_layout(cells)
        if not layout:
            continue

        # 组起始：找第一个企业名位置（表头行内 "序号" 之后）
        # 表头字段数 = 序号 + 所有列名 + 尾部空列；数据组紧跟表头
        # 动态组间距：找前两个企业名出现位置之差
        ent_positions = [i for i, c in enumerate(cells) if c and RE_ENTERPRISE.search(c) and i > 3]
        if len(ent_positions) < 1:
            continue
        start = ent_positions[0]
        stride = (ent_positions[1] - start) if len(ent_positions) > 1 else (len(cells) - start)

        for base in range(start, len(cells), stride):
            if base >= len(cells):
                break
            rec = {}
            for rel, fname in layout:
                pos = base + rel
                if pos < len(cells):
                    rec[fname] = cells[pos]
            if rec.get("车辆型号"):
                result["sections"][section]["records"].append(rec)

    for name in _PURCHASE_SECTIONS:
        result["stats"][name] = len(result["sections"][name]["records"])
    result["stats"]["total"] = sum(result["stats"].values())
    return result


def write_outputs(data: dict, output_prefix: str, out_dir: Path):
    json_path = out_dir / f"{output_prefix}.json"
    md_path = out_dir / f"{output_prefix}.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    md_lines = [f"# {data['title']}\n", f"**批次**: {data['batch']} | **日期**: {data['date']}\n"]
    for name in data["section_order"]:
        recs = data["sections"][name]["records"]
        md_lines.append(f"\n## {name}（{len(recs)} 条）\n")
        if recs:
            cols = list(recs[0].keys())
            md_lines.append("| " + " | ".join(cols) + " |")
            md_lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
            for r in recs[:50]:
                md_lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="MIIT 购置税目录解析器")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch", default="")
    parser.add_argument("--date", default="")
    args = parser.parse_args()

    data = parse_txt(args.input)
    if args.batch:
        data["batch"] = args.batch
    if args.date:
        data["date"] = args.date

    out_dir = Path(args.output).parent if "/" in args.output else VEHICLE_TAX_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = args.output if "/" not in args.output else Path(args.output).name
    write_outputs(data, output_prefix, out_dir)
    print(json.dumps(data["stats"], ensure_ascii=False, indent=2))
    print(f"输出: {out_dir}/{output_prefix}.json")


if __name__ == "__main__":
    main()
