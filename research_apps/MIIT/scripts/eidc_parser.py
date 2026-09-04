#!/usr/bin/env python3
"""
MIIT EIDC Parser 层（只理解 EIDC 自己的数据结构）

把 EIDC 正式公告附件（.doc → .txt）解析为稳定、明确的 EIDC source record。

当前支持：
  parse_road_products(text)      —— 道路机动车辆生产企业及产品（附件1）
  parse_vehicle_tax(text)        —— 车船税目录（附件2，委托给 03 parser 的 schema 逻辑）
  parse_purchase_tax(text)       —— 购置税目录（附件3，见 05_parse_purchase_tax.py）

road 附件真实列结构（textutil 导出，\x07 分隔）：
  每行 = [序号, 商标, 产品名称, 产品型号]（表头 4 列）
       + 重复组 [企业名称, 目录序号, 商标, 产品名称, 产品型号]（5 列/组）

legacy workspace 的字段错位根源：它假设 head_len=6 再按 5 列分组，导致错位。
本解析器按真实 head=4 + 5 列组解析。

输出 source record（保留 EIDC 原字段语义，不做 canonical 推断）：
  {
    batch_no,
    manufacturer_raw,     企业名称
    catalog_no_raw,      目录序号
    brand_raw,            商标（含"牌"）
    product_name_raw,     产品名称
    model_code_raw,       产品型号（可能含"、"多型号）
    vehicle_type_raw,     产品名称即车辆类型
  }
"""

import json
import re

SEP = "\x07"

# 表头 4 列（road 附件真实结构）
ROAD_HEAD = ["序号", "商标", "产品名称", "产品型号"]
# 表头行判定：恰好 4 列表头
ROAD_HEAD_ROW = tuple(ROAD_HEAD)

RE_ENTERPRISE_SUFFIX = re.compile(r"(公司|厂|集团|有限)$")


def _split_models(model_raw: str) -> list[str]:
    """拆分多型号（'CA4250、CA4185' → ['CA4250','CA4185']），去空。"""
    parts = re.split(r"[、，,;；\s]+", model_raw)
    return [p.strip() for p in parts if p.strip()]


def _is_header_row(head: list[str]) -> bool:
    return head[:4] == ROAD_HEAD and len(head) <= 5


# 官方分节标题识别（第一部分 新产品 下的子标题，无 SEP 的短行）
RE_SECTION_HEADER = re.compile(
    r'^(第[一二三四五六七八九十]+部分|[一二三四五六七八九十]+、|[（(][一二三四五六七八九十]+[）)]|民用改装车生产企业|汽车起重机生产企业|汽车生产企业及产品|摩托车生产企业及产品)')
# 目录序号格式信号：带地区前缀（改装车/专用车） vs 纯数字（整车企业）
RE_CATALOG_REGION_PREFIX = re.compile(r'^[（(][一二三四五六七八九十]+[）)]')
RE_CATALOG_PURE_NUM = re.compile(r'^\d+$')


def _detect_section(line: str) -> str | None:
    """若该行是官方分节标题，返回规范化的 section 名；否则 None。"""
    s = line.strip()
    if not s or "\x07" in s or len(s) > 24:
        return None
    # 第一部分子标题：一、汽车生产企业 / 民用改装车生产企业 / 汽车起重机生产企业
    m = re.match(r'^[一二三四五六七八九十]+、(.+?)$', s)
    if m and "生产企业" in m.group(1):
        return f"一、{m.group(1)}"
    if s in ("民用改装车生产企业", "汽车起重机生产企业"):
        return f"民用改装车生产企业" if s == "民用改装车生产企业" else "汽车起重机生产企业"
    if re.match(r'^第[一二三四五六七八九十]+部分', s):
        return s
    return None


def parse_road_products(text: str, batch_no: str = "") -> list[dict]:
    """解析道路机动车辆生产企业及产品（附件1）。

    每行含 4 列表头 + 多个 5 列组（企业/目录序号/商标/产品名称/产品型号）。
    多型号记录（'、' 分隔）拆分为多个 source record（每型号一行）。

    每条记录附加官方分节上下文：
      source_section  —— 记录所在官方分节（一、汽车生产企业 / 民用改装车生产企业 /
                           汽车起重机生产企业 / 第二部分 变更扩展产品 …）

    ⚠ source_section 可靠性限制（第一部分混排）：
      第一部分"新产品"仅"一、汽车生产企业"一个一级标题，其下混排乘用车/商用车/
      底盘/起重机/摩托车全部产品表，摩托车表无独立子标题（textutil 导出丢失）。
      故 source_section 仅表示"最近捕获的官方标题"，对第一部分产品**不可作为分类依据**。
      分类请使用 vehicle_category（产品名强规则优先，见 vehicle_record_builder）。
      本字段仅作 evidence（记录在文档中的位置），可靠性见上。
    """
    records = []
    lines = text.replace("\r\n", "\n").split("\n")
    seen: set[str] = set()
    current_section = ""

    for line in lines:
        raw = line.strip()
        # 捕获官方分节标题（无 SEP 的短行）
        sec = _detect_section(raw)
        if sec:
            current_section = sec
        if not raw or SEP not in raw:
            continue
        parts = [p.strip() for p in raw.split(SEP)]

        head = parts[:4]
        if _is_header_row(head):
            # 表头行，无数据组
            if len(parts) <= 6:
                continue
            rest = parts[4:]
        else:
            # 无表头前缀（数据行直接开始），全部按组解析
            rest = parts

        j = 0
        n = len(rest)
        while j + 4 < n:
            ent = rest[j]
            # 跳过空分隔符（Word 合并单元格余留）
            if not ent and j + 5 < n:
                j += 1
                continue
            catalog = rest[j + 1] if j + 1 < n else ""
            brand = rest[j + 2] if j + 2 < n else ""
            pname = rest[j + 3] if j + 3 < n else ""
            model = rest[j + 4] if j + 4 < n else ""
            j += 5

            if not ent and not model:
                continue
            # 跳过段标题行（无企业名也无型号）
            if not ent and not RE_ENTERPRISE_SUFFIX.search(ent or ""):
                continue

            models = _split_models(model)
            if not models:
                # 单条空型号记录仍保留（供质量统计），model_code_raw=''
                key = f"{ent}|{brand}|{pname}|{model}"
                if key not in seen:
                    seen.add(key)
                    records.append({
                        "batch_no": str(batch_no),
                        "manufacturer_raw": ent,
                        "catalog_no_raw": catalog,
                        "brand_raw": brand,
                        "product_name_raw": pname,
                        "model_code_raw": model,
                        "vehicle_type_raw": pname,
                        "source_section": current_section,
                    })
                continue

            for m in models:
                key = f"{ent}|{brand}|{pname}|{m}"
                if key in seen:
                    continue
                seen.add(key)
                records.append({
                    "batch_no": str(batch_no),
                    "manufacturer_raw": ent,
                    "catalog_no_raw": catalog,
                    "brand_raw": brand,
                    "product_name_raw": pname,
                    "model_code_raw": m,
                    "vehicle_type_raw": pname,
                    "source_section": current_section,
                })

    return records


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="EIDC source parser (road products)")
    parser.add_argument("--input", required=True, help="附件1 .txt 路径")
    parser.add_argument("--batch", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    text = open(args.input).read()
    recs = parse_road_products(text, args.batch)
    if args.json:
        print(json.dumps(recs, ensure_ascii=False, indent=2))
    else:
        print(f"parsed {len(recs)} records")
        for r in recs[:5]:
            print(" ", r)
