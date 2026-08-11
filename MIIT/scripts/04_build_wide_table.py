#!/usr/bin/env python3
"""
MIIT Pipeline P4: 参数宽表构建器

Parse 新车 models from batch scan and generate a wide table
by merging 附件1 (brand .md detail pages) and 附件2 (车船税 JSON).

Outputs: data/wide_tables/wide_table_{batch}.csv + .md

输入统一来自 data/search_results + data/vehicle_tax + data/vehicle_details。
批次配置（scan/tax 文件名）统一读取 workflow/batches.yaml。

Derived metrics:
  - 百公里电耗近似值 (kWh/100km): battery_energy / range * 100 (BEV only)
  - 电池包能量密度 (Wh/kg): battery_energy_kWh / battery_mass_kg * 1000
  - 单位电量续航 (km/kWh): range / battery_energy
  - 整车电池质量占比: battery_mass / curb_weight
  - 电池供应商装机结构: supplier count per brand (summary output)

用法:
  python3 scripts/04_build_wide_table.py --batch 410
  python3 scripts/04_build_wide_table.py --batch 410 --output-dir 自定义目录
"""

import json
import re
import csv
import argparse
import sys
from pathlib import Path

from miit_paths import (  # noqa: E402
    DEFAULT_BATCH,
    load_batches,
    scan_path,
    tax_json_path,
    wide_table_path,
    VEHICLE_DETAILS_DIR,
    WIDE_TABLES_DIR,
    ensure_dir,
)

# ── Battery chemistry normalization ──

_BATT_CHEM_MAP = [
    (r'磷酸铁锂', 'LFP', '磷酸铁锂'),
    (r'镍钴锰', 'NCM', '三元锂'),
    (r'三元', 'NCM', '三元锂'),
]


def normalize_battery_chemistry(raw: str) -> tuple[str, str, bool]:
    """Return (chemistry_code, chemistry_cn, ncm_explicit_flag)."""
    if not raw:
        return '', '', False
    for pat, code, cn in _BATT_CHEM_MAP:
        if re.search(pat, raw):
            return code, cn, bool(re.search(r'镍钴锰', raw))
    return 'OTHER', '其他', False


# ── Motor power parsing ──

def parse_motor_power(raw: str) -> tuple[int, list[float], float]:
    """Return (motor_count, power_list, total_peak_kw)."""
    if not raw:
        return 0, [], 0.0
    # Strip 'kW' suffix and extract all numbers
    cleaned = raw.replace('kW', '').strip()
    nums = re.findall(r'(\d+(?:\.\d+)?)', cleaned)
    powers = [float(n) for n in nums if float(n) > 1]  # filter out stray small nums
    if not powers:
        return 0, [], 0.0
    return len(powers), powers, round(sum(powers), 1)


# ── Supplier grouping ──

_SUPPLIER_GROUP = [
    # BYD / 弗迪系
    (r'绍兴弗迪|西安弗迪|无为弗迪|温州弗迪|广西东盟弗迪|汕尾弗迪|青海弗迪|重庆弗迪', 'BYD', '弗迪系'),
    (r'合肥比亚迪|深圳比亚迪|西咸新区比亚迪', 'BYD', '比亚迪汽车'),
    # CATL / 宁德时代系
    (r'宁德时代|江苏时代|四川时代|宜宾三江时代|中州时代|广东瑞庆时代|川渝时代|时代[一汽广汽长安]', 'CATL', '宁德时代系'),
    (r'科新动力', 'CATL', '宁德时代系（合资）'),
    # Others
    (r'中创新航', 'CALB', '中创新航'),
    (r'蜂巢能源', 'SVOLT', '蜂巢能源'),
    (r'国轩高科', 'GOTION', '国轩高科'),
    (r'欣旺达', 'SUNWODA', '欣旺达'),
    (r'爱尔集新能源', 'LG', 'LG新能源'),
    (r'南昌欣旺达', 'SUNWODA', '欣旺达'),
    (r'浙江理想汽车电池', 'LIXIANG', '理想汽车电池'),
]


def resolve_supplier_group(name: str) -> tuple[str, str]:
    """Return (group_code, group_name)."""
    if not name:
        return ('', '')
    for pat, code, gname in _SUPPLIER_GROUP:
        if re.search(pat, name):
            return (code, gname)
    return ('OTHER', '其他')


def vertical_integration(cell_supplier: str, pack_supplier: str) -> str:
    """Classify: same_company / same_group / cross_group"""
    cell_code, _ = resolve_supplier_group(cell_supplier)
    pack_code, _ = resolve_supplier_group(pack_supplier)
    if not cell_code or not pack_code:
        return ''
    if cell_supplier == pack_supplier:
        return 'same_company'
    if cell_code == pack_code:
        return 'same_group'
    return 'cross_group'


def parse_scan_md(path: Path) -> list[dict]:
    """Extract model info list from scan_batch_409.md's embedded JSON."""
    text = path.read_text()
    m = re.search(r'```json\n(.+?)\n```', text, re.DOTALL)
    if not m:
        raise ValueError("No JSON block found in scan file")
    data = json.loads(m.group(1))
    models = []
    for brand_entry in data["brands"]:
        brand = brand_entry["catalog"]
        for row in brand_entry["all_rows"]:
            models.append({
                "brand": brand,
                "enterprise_name": row["qymc"],
                "brand_sign": row["cpsb"],
                "product_name": row["cpmc"],
                "model_id": row["cpxh"],
            })
    return models


def load_tax_index(path: Path) -> dict:
    """Build {产品型号: record} index from 车船税 JSON sections."""
    data = json.loads(path.read_text())
    index = {}
    for sec_name, sec in data.get("sections", {}).items():
        for rec in sec.get("records", []):
            mid = rec.get("产品型号", "") or rec.get("车辆型号", "")
            if mid:
                if mid not in index:
                    index[mid] = {}
                index[mid].update(rec)
                index[mid]["_tax_section"] = sec_name
    return index


def read_brand_md(brand: str, model_id: str, batch: str = DEFAULT_BATCH) -> dict | None:
    """Read the .md detail file for a model from data/vehicle_details/ directory.

    文件名按 `{batch}_{model_id}-{产品名}.md`（身份 = batch:model_code），
    型号不假设全局唯一。
    """
    matches = list(VEHICLE_DETAILS_DIR.glob(f"{batch}_{model_id}-*.md"))
    if not matches:
        return None
    return _parse_md_file(matches[0])


def _parse_md_file(path: Path) -> dict:
    """Parse a brand .md file into a flat key-value dict."""
    text = path.read_text()
    data = {}

    # Parse table sections: | key | value |
    for m in re.finditer(r'^\| ([^|]+) \| ([^|]+) \|', text, re.MULTILINE):
        key = m.group(1).strip()
        val = m.group(2).strip()
        if key and val and key not in ("字段", "内容", "字段", "数值", "视角", "链接", "------"):
            data[key] = val

    # Parse 外形尺寸(mm) extended format: 长：... 宽：... 高：...
    dim_key = "外形尺寸(mm)"
    if dim_key not in data:
        for k in data:
            if "外形尺寸" in k:
                dim_key = k
                break
    dim_raw = data.get(dim_key, "")
    if dim_raw:
        dims = {}
        for label in ["长", "宽", "高"]:
            m2 = re.search(rf'{label}[：:]\s*(\d+)', dim_raw)
            if m2:
                dims[label] = m2.group(1)
        if dims:
            data["外形尺寸(mm)_parsed"] = json.dumps(dims, ensure_ascii=False)

    # Parse 其它 field for battery info
    other = data.get("其它", "")
    if other:
        # Common: regex to match values up to delimiter
        _VAL = r'[^，,;。；.\n]+'

        # ── Battery type extraction (multiple formats) ──
        # Format B1: 储能装置种类:XXX
        m_batt = re.search(r'储能装置种类[：:](%s)' % _VAL, other)
        if not m_batt:
            # Format B2: 储能装置种类为XXX  [智界]
            m_batt = re.search(r'储能装置种类为(%s)' % _VAL, other)
        if m_batt:
            data.setdefault("储能装置种类", m_batt.group(1).strip())

        # ── Cell/Supplier extraction (most specific format first!) ──
        # Format B: 储能装置种类/单体生产企业/总成生产企业:A/B/C  [问界/享界]
        m_combo = re.search(r'储能装置种类/单体生产企业/总成生产企业[：:](%s)' % _VAL, other)
        if m_combo:
            parts = [p.strip() for p in m_combo.group(1).split("/")]
            if len(parts) >= 1:
                data.setdefault("储能装置种类", parts[0])
            if len(parts) >= 2:
                data.setdefault("电池单体企业", parts[1])
            if len(parts) >= 3:
                data.setdefault("电池总成企业", parts[2])

        # Format D: 储能装置(单体的/单体)生产企业:YYY, 总成同样格式 [腾势/比亚迪/猛士/智界]
        if not data.get("电池单体企业"):
            for pat in [
                r'储能装置单体的生产企业[：:](%s)' % _VAL,
                r'储能装置单体生产企业[：:](%s)' % _VAL,
                r'储能装置单体厂家为(%s)' % _VAL,
                r'单体生产企业[：:](%s)' % _VAL,
            ]:
                m_c = re.search(pat, other)
                if m_c:
                    data.setdefault("电池单体企业", m_c.group(1).strip())
                    break
        if not data.get("电池总成企业"):
            for pat in [
                r'储能装置总成的生产企业[：:](%s)' % _VAL,
                r'储能装置总成生产企业[：:](%s)' % _VAL,
                r'储能装置总成厂家为(%s)' % _VAL,
                r'总成生产企业[：:](%s)' % _VAL,
            ]:
                m_p = re.search(pat, other)
                if m_p:
                    data.setdefault("电池总成企业", m_p.group(1).strip())
                    break

        # Format A (last resort): 生产企业: XXX(单体)/YYY(总成) or standalone 生产企业:YYY  [启境/广汽]
        # Only use if no supplier found yet, to avoid matching ABS/other non-battery 生产企业
        if not data.get("电池单体企业") and not data.get("电池总成企业"):
            m_cell_a = re.search(r'生产企业[：:](%s)' % _VAL, other)
            if m_cell_a:
                raw = m_cell_a.group(1)
                if "(单体)" in raw or "(总成)" in raw:
                    for part in raw.split("/"):
                        part = part.strip()
                        m_c = re.match(r'([^，,;。]+?)\(单体\)', part)
                        if m_c:
                            data.setdefault("电池单体企业", m_c.group(1).strip())
                        m_p = re.match(r'([^，,;。]+?)\(总成\)', part)
                        if m_p:
                            data.setdefault("电池总成企业", m_p.group(1).strip())
                else:
                    # Standalone: treat the single value as pack supplier (启境 BEV case)
                    data.setdefault("电池总成企业", raw.strip())

    data["_md_file"] = path.name
    return data


def parse_num(s: str) -> float | None:
    """Extract the nominal (first) number from a string."""
    s = s.strip()
    s = s.split("/")[0].split("±")[0].split("（")[0].split("(")[0].strip()
    if not s:
        return None
    s = s.split("（")[0].split("(")[0].strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_tolerance(s: str) -> tuple[float | None, float | None, float | None]:
    """Parse a string like '400±12' → (nominal, low, high).

    Returns (nominal, low, high). For non-tolerance values, low=high=nominal.
    """
    s = s.strip()
    s = s.split("/")[0].split("（")[0].split("(")[0].strip()
    m = re.match(r'([\d.]+)\s*[±]\s*([\d.]+)', s)
    if m:
        nominal = float(m.group(1))
        tol = float(m.group(2))
        return nominal, nominal - tol, nominal + tol
    try:
        v = float(s)
        return v, v, v
    except ValueError:
        return None, None, None


def parse_dims(text: str) -> dict:
    """Parse 外形尺寸(mm) -> {长, 宽, 高}."""
    result = {}
    for label in ["长", "宽", "高"]:
        m = re.search(rf'{label}[：:]\s*(\d+)', text)
        if m:
            result[label] = m.group(1)
    return result


def build_record(model: dict, md: dict | None, tax: dict) -> dict:
    """Merge one model into a wide record with all fields + derived metrics."""
    r = {}

    # ── Identity ──
    r["品牌"] = model["brand"]
    r["企业名称"] = model["enterprise_name"]
    r["产品型号"] = model["model_id"]
    r["产品名称"] = model["product_name"]

    # ── Tax/battery metrics availability flag ──
    mid = model["model_id"]
    tax_available = bool(tax and tax.get("动力蓄电池总能量_kWh", "") or tax.get("动力蓄电池组总能量_kWh", ""))
    r["tax_catalog_match_flag"] = "1" if tax_available else "0"
    r["battery_metrics_available_flag"] = "1" if tax_available else "0"

    # ── 动力形式 (from md) ──
    power = ""
    if md:
        power = md.get("新能源类型", "") or ""
        if not power:
            fuel = md.get("燃料种类", "")
            name = md.get("产品名称", "")
            if "纯电动" in fuel or ("纯电动" in name and "混合" not in name):
                power = "纯电动"
            elif "增程" in name:
                power = "插电式增程混合动力"
            elif "混合" in fuel or "混合" in name:
                power = "插电式混合动力"
            elif "燃料电池" in name:
                power = "燃料电池"
    # Normalize: if model code has REEV or product name has 增程, classify as 增程
    mid = model["model_id"]
    pname = model["product_name"]
    if "REEV" in mid.upper() or "增程" in pname:
        power = "插电式增程混合动力"
    r["动力形式"] = power

    # ── 电池类型 (from md) ──
    batt_type = ""
    if md:
        batt_type = md.get("储能装置种类", "")
    r["电池类型"] = batt_type
    chem_code, chem_cn, ncm_flag = normalize_battery_chemistry(batt_type)
    r["battery_chemistry"] = chem_code
    r["battery_chemistry_cn"] = chem_cn
    r["battery_ncm_explicit_flag"] = "1" if ncm_flag else "0"

    # ── Motor power (must be after power type determination) ──
    _is_bev_power = ("纯电动" in power) and ("混合" not in power)
    motor = ""
    if md:
        motor_raw = ""
        for mk in ["驱动电机峰值功率(kW)", "驱动电机峰值功率_kW"]:
            motor_raw = md.get(mk, "")
            if motor_raw:
                break
        if not motor_raw and _is_bev_power:
            for mk in ["功率(kw)", "功率_kw", "功率", "功率(kW)"]:
                motor_raw = md.get(mk, "")
                if motor_raw:
                    break
        if motor_raw:
            # Clean up: extract digits and add kW suffix
            # Handle "驱动电机：前：160/后：227" → "160/227kW"
            # Extract all numbers separated by /
            nums = re.findall(r'(\d+)\s*kW', motor_raw)
            if not nums:
                # Try "前：160/后：227" or "160/227"
                nums = re.findall(r'(?<![\d.])(\d+)(?![\d.])', motor_raw.replace("kW", "").replace("kw", ""))
            if nums:
                motor = "/".join(nums) + "kW"
            else:
                motor = motor_raw.replace("\n", " ")[:60]
        # Fallback: extract motor peak power from 其它 field
        if not motor:
            other = md.get("其它", "")
            if other:
                m_pk = re.search(r'峰值功率[（(][^）)]*[）)]\s*[：:]\s*(\d+)\s*kW', other)
                if not m_pk:
                    m_pk = re.search(r'峰值功率[：:]\s*(\d+)\s*kW', other)
                if m_pk:
                    motor = m_pk.group(1) + "kW"
    r["电机功率(kW)"] = motor
    m_count, m_list, m_total = parse_motor_power(motor)
    r["motor_count"] = m_count
    r["motor_power_list"] = " / ".join(str(p) for p in m_list) if m_list else ""
    r["motor_total_peak_kw"] = m_total
    r["single_multi_motor"] = "单电机" if m_count == 1 else f"{m_count}电机" if m_count > 1 else ""

    # ── 电芯/总成供应商 (from md) ──
    supplier = ""
    cell_sup = ""
    pack_sup = ""
    if md:
        supplier = md.get("电池单体_总成企业", "") or md.get("电池单体/总成企业", "") or ""
        if not supplier:
            cell_sup = md.get("电池单体企业", "")
            pack_sup = md.get("电池总成企业", "")
            parts = [x for x in [cell_sup, pack_sup] if x]
            if parts:
                supplier = " / ".join(parts)
        else:
            # Try to split combined field
            if " / " in supplier:
                sp = supplier.split(" / ", 1)
                cell_sup = sp[0].strip()
                pack_sup = sp[1].strip() if len(sp) > 1 else ""
            else:
                cell_sup = supplier
                pack_sup = supplier
    r["电芯/总成供应商"] = supplier
    r["cell_supplier"] = cell_sup
    r["pack_supplier"] = pack_sup
    cell_grp_code, cell_grp_name = resolve_supplier_group(cell_sup)
    pack_grp_code, pack_grp_name = resolve_supplier_group(pack_sup)
    r["cell_supplier_group"] = cell_grp_name
    r["pack_supplier_group"] = pack_grp_name
    r["vertical_integration_flag"] = vertical_integration(cell_sup, pack_sup)

    # ── 附件2 fields (from tax) ──
    bat_energy_str = tax.get("动力蓄电池总能量_kWh", "") or tax.get("动力蓄电池组总能量_kWh", "")
    bat_mass_str = tax.get("动力蓄电池总质量_kg", "") or tax.get("动力蓄电池组总质量_kg", "")
    range_str = tax.get("纯电动续驶里程_km", "")
    curb_str = tax.get("整车整备质量_kg", "")

    bat_energy = parse_num(bat_energy_str)
    bat_mass = parse_num(bat_mass_str)
    elec_range = parse_num(range_str)
    curb_weight = parse_num(curb_str)

    # Fallback: 整备质量 from md if not in tax
    if curb_weight is None and md:
        cw = md.get("整备质量(kg)", "")
        if not cw:
            cw = md.get("整备质量", "")
        if cw:
            curb_weight = parse_num(cw)

    r["电池容量(kWh)"] = bat_energy_str
    r["电池容量_num"] = bat_energy
    r["电池质量(kg)"] = bat_mass_str
    r["电池质量_num"] = bat_mass
    r["纯电续航(km)"] = range_str
    r["纯电续航_num"] = elec_range
    r["整备质量(kg)"] = curb_str
    r["整备质量_num"] = curb_weight

    # ── 外形尺寸 (from md) ──
    length = width = height = ""
    if md:
        for dk in ["外形尺寸(mm)", "外形尺寸"]:
            dv = md.get(dk, "")
            if dv:
                dims = parse_dims(dv)
                length = dims.get("长", "")
                width = dims.get("宽", "")
                height = dims.get("高", "")
                break
    r["长(mm)"] = length
    r["宽(mm)"] = width
    r["高(mm)"] = height

    # ── 增程器 (from md, only for non-BEV / PHEV/EREV) ──
    engine_parts = []
    if md and ("混合" in power or "增程" in power or "燃料电池" in power):
        eng_model = md.get("发动机型号", "")
        eng_disp = md.get("排量(ml)", "")
        eng_power = md.get("发动机最大净功率(kW)", "") or md.get("发动机最大净功率_kW", "")
        eng_co = md.get("发动机企业", "")
        if eng_model:
            engine_parts.append(eng_model)
        if eng_disp:
            engine_parts.append(f"{eng_disp}ml")
        if eng_power:
            engine_parts.append(f"{eng_power}kW")
        if eng_co:
            engine_parts.append(eng_co)
    r["增程器"] = " / ".join(engine_parts)

    r["_bat_energy_num"] = bat_energy
    r["_bat_mass_num"] = bat_mass
    # Parse tolerance for battery mass
    _bm_nom, _bm_lo, _bm_hi = parse_tolerance(bat_mass_str)
    r["_bat_mass_lo"] = _bm_lo
    r["_bat_mass_hi"] = _bm_hi
    r["_range_num"] = elec_range
    r["_curb_num"] = curb_weight
    # Missing data reason
    if not tax_available:
        r["missing_reason"] = "来源未覆盖（附件2车船税未收录该车型）"
    else:
        r["missing_reason"] = ""
    power_type = r.get("动力形式", "")
    if tax_available:
        r["metric_scope"] = "全数据"
    elif "纯电动" in power_type and "混合" not in power_type:
        r["metric_scope"] = "仅增程/插混（纯电车型附件2未覆盖）"
    else:
        r["metric_scope"] = "数据缺失"

    return r


def _split_variant_values(values: list[str]) -> list[list[float | None]]:
    """Parse multi-value fields (e.g. '380/375') and align variants.

    Returns list of variants, each being a list of floats aligned across fields.
    """
    parsed = []
    max_parts = 1
    for v in values:
        if not v or not v.strip():
            parsed.append([None])
            continue
        v = v.strip()
        # Handle "2561/2610" → ["2561", "2610"]
        parts = [p.strip() for p in v.split("/")]
        # Filter to numeric-like parts
        nums = []
        for p in parts:
            # Handle "400±12" → "400"
            p = p.split("±")[0].split("（")[0].split("(")[0].strip()
            try:
                nums.append(float(p))
            except ValueError:
                nums.append(None)
        if not nums:
            nums = [None]
        parsed.append(nums)
        max_parts = max(max_parts, len(nums))

    # Align: each variant gets position i from each field
    variants = []
    for i in range(max_parts):
        variant = []
        for nums in parsed:
            if i < len(nums):
                variant.append(nums[i])
            else:
                # If a single value applies to all variants, repeat it
                variant.append(nums[0] if nums else None)
        variants.append(variant)
    return variants


def expand_variants(records: list[dict]) -> tuple[list[dict], set[str]]:
    """Expand records with multi-value fields (range/curb weight) into variants.

    Returns (expanded_records, original_model_ids).
    Fields split: 电池容量(kWh), 电池质量(kg), 纯电续航(km), 整备质量(kg)
    Derived metrics re-computed per variant.
    """
    original_ids: set[str] = set()
    expanded = []
    for r in records:
        original_ids.add(r.get("产品型号", ""))
        raw_range = r.get("电池容量(kWh)", "")
        raw_mass = r.get("电池质量(kg)", "")
        raw_elec = r.get("纯电续航(km)", "")
        raw_curb = r.get("整备质量(kg)", "")

        # Check if any field has "/" → multi-variant
        has_multi = any("/" in v for v in [raw_range, raw_mass, raw_elec, raw_curb] if v)

        if not has_multi:
            # Single variant: compute derived metrics directly
            be = r.get("_bat_energy_num")
            bm = r.get("_bat_mass_num")
            er = r.get("_range_num")
            cw = r.get("_curb_num")
            _compute_derived(r, be, bm, er, cw)
            expanded.append(r)
        else:
            # Multiple variants: split and create one row per variant
            variants = _split_variant_values([
                raw_range, raw_mass, raw_elec, raw_curb
            ])
            for i, (be_val, bm_val, er_val, cw_val) in enumerate(variants):
                vr = dict(r)  # shallow copy
                tag = f"#{i+1}" if len(variants) > 1 else ""
                if tag:
                    vr["产品型号"] = r["产品型号"] + tag
                # Update display strings
                vr["电池容量(kWh)"] = str(be_val) if be_val is not None else r.get("电池容量(kWh)", "")
                vr["电池质量(kg)"] = str(bm_val) if bm_val is not None else r.get("电池质量(kg)", "")
                vr["纯电续航(km)"] = str(er_val) if er_val is not None else r.get("纯电续航(km)", "")
                vr["整备质量(kg)"] = str(cw_val) if cw_val is not None else r.get("整备质量(kg)", "")
                _compute_derived(vr, be_val, bm_val, er_val, cw_val)
                expanded.append(vr)
    return expanded, original_ids


def _fmt_range(lo: float, hi: float, decimals: int = 1) -> str:
    """Format a range like '163.0~173.1'. If lo == hi, return single value."""
    if abs(hi - lo) < 0.01:
        return str(round(lo, decimals))
    return f"{round(lo, decimals)}~{round(hi, decimals)}"


def _compute_derived(r: dict, bat_energy: float | None, bat_mass: float | None,
                     elec_range: float | None, curb_weight: float | None):
    """Compute and set derived metrics on record r.

    If the record has tolerance info on battery mass (_bat_mass_lo/_bat_mass_hi),
    derived metrics that depend on mass will be displayed as a range.
    """
    bat_mass_lo = r.get("_bat_mass_lo") or bat_mass
    bat_mass_hi = r.get("_bat_mass_hi") or bat_mass
    has_tolerance = bat_mass_lo is not None and bat_mass_hi is not None and abs(bat_mass_hi - bat_mass_lo) > 0.01

    # 近似电耗: 电池容量 / 续航 * 100 (筛选/对比用，非官方能耗)
    ed = None
    if bat_energy and elec_range and elec_range > 0:
        ed = round(bat_energy / elec_range * 100, 1)
    r["总电量口径近似电耗(kWh/100km)"] = ed if ed is not None else ""

    # 电池包能量密度 (Wh/kg) — 支持公差区间
    if bat_energy and bat_mass_lo and bat_mass_hi and bat_mass_lo > 0:
        ed_lo = round(bat_energy / bat_mass_hi * 1000, 1)
        ed_hi = round(bat_energy / bat_mass_lo * 1000, 1)
        r["电池包能量密度(Wh/kg)"] = _fmt_range(ed_lo, ed_hi)
    else:
        r["电池包能量密度(Wh/kg)"] = ""

    # 单位电量续航 (km/kWh)
    km_per_kwh = None
    if bat_energy and elec_range and bat_energy > 0:
        km_per_kwh = round(elec_range / bat_energy, 2)
    r["单位电量续航(km/kWh)"] = km_per_kwh if km_per_kwh is not None else ""

    # 整车电池质量占比 — 支持公差区间
    if bat_mass_lo and bat_mass_hi and curb_weight and curb_weight > 0:
        mr_lo = round(bat_mass_lo / curb_weight * 100, 1)
        mr_hi = round(bat_mass_hi / curb_weight * 100, 1)
        r["电池质量占整备质量比(%)"] = _fmt_range(mr_lo, mr_hi)
    else:
        r["电池质量占整备质量比(%)"] = ""


def _dedup_by_model(records: list[dict]) -> list[dict]:
    """Deduplicate expanded records: keep first row per original model_id (strip #1/#2)."""
    seen: set[str] = set()
    deduped = []
    for r in records:
        mid = r.get("产品型号", "").split("#")[0]
        if mid not in seen:
            seen.add(mid)
            deduped.append(r)
    return deduped


def supplier_summary(records: list[dict], by_model: bool = True, by_group: bool = False) -> str:
    """Generate supplier installation structure summary.

    Args:
        records: expanded record list
        by_model: if True, deduplicate by original product model
        by_group: if True, aggregate by cell_supplier_group level
    """
    from collections import Counter
    if by_model:
        recs = _dedup_by_model(records)
        label = "车型"
    else:
        recs = records
        label = "配置"
    suppliers = Counter()
    for r in recs:
        if by_group:
            s = r.get("cell_supplier_group", "")
        else:
            s = r.get("电芯/总成供应商", "")
        if s:
            suppliers[s] += 1
    if not suppliers:
        return "无数据"
    lines = [f"(统计口径: {len(recs)} 个原始{label})"]
    for s, cnt in suppliers.most_common():
        lines.append(f"  - {s}: {cnt}款")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="MIIT 新车参数宽表生成器")
    parser.add_argument("--batch", default=DEFAULT_BATCH,
                        help=f"公告批次号（默认 {DEFAULT_BATCH}），如 410")
    parser.add_argument("--output-dir", default="",
                        help="输出目录（默认 MIIT/{batch}-Parameter/）")
    args = parser.parse_args()

    batch = args.batch
    cfg = load_batches().get(batch, load_batches()[DEFAULT_BATCH])
    SCAN_PATH = scan_path(batch)
    TAX_PATH = tax_json_path(batch)
    out_dir = Path(args.output_dir) if args.output_dir else WIDE_TABLES_DIR
    ensure_dir(out_dir)
    csv_path = out_dir / ("wide_table_" + batch + ".csv")
    md_path = out_dir / ("wide_table_" + batch + ".md")
    out_dir.mkdir(parents=True, exist_ok=True)

    models = parse_scan_md(SCAN_PATH)
    print(f"Found {len(models)} models in scan file")

    tax_index = load_tax_index(TAX_PATH)
    print(f"Tax index has {len(tax_index)} entries")

    records = []
    missing_md = []
    missing_tax = []
    missing_both = []

    for m in models:
        mid = m["model_id"]
        brand = m["brand"]

        md_data = read_brand_md(brand, mid, batch)
        tax_data = tax_index.get(mid, {})

        if md_data is None:
            missing_md.append(mid)
        if not tax_data:
            missing_tax.append(mid)

        rec = build_record(m, md_data, tax_data)
        records.append(rec)

    # ── Expand multi-value variants and compute derived metrics ──
    records, original_model_ids = expand_variants(records)
    n_original = len(original_model_ids)
    n_expanded = len(records)
    print(f"Original models: {n_original}, after variant expansion: {n_expanded} rows")

    # ── Output CSV ──
    field_names = [
        "品牌", "企业名称", "产品型号", "产品名称",
        "动力形式",
        # Motor
        "电机功率(kW)", "motor_count", "motor_total_peak_kw", "single_multi_motor",
        # Battery chemistry
        "电池类型", "battery_chemistry", "battery_chemistry_cn", "battery_ncm_explicit_flag",
        # Core metrics
        "电池容量(kWh)", "电池质量(kg)", "纯电续航(km)", "整备质量(kg)",
        # Suppliers (split)
        "cell_supplier", "pack_supplier",
        "cell_supplier_group", "pack_supplier_group", "vertical_integration_flag",
        # Legacy combined
        "电芯/总成供应商",
        # Engine
        "增程器",
        # Dimensions
        "长(mm)", "宽(mm)", "高(mm)",
        # Derived
        "总电量口径近似电耗(kWh/100km)", "电池包能量密度(Wh/kg)",
        "单位电量续航(km/kWh)", "电池质量占整备质量比(%)",
        # Data quality
        "tax_catalog_match_flag", "battery_metrics_available_flag",
        "missing_reason", "metric_scope",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=field_names, extrasaction="ignore")
        w.writeheader()
        for rec in records:
            w.writerow(rec)
    print(f"CSV written: {csv_path}")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 第{batch}批 MIIT 新车参数宽表\n\n")
        f.write(f"**数据来源**: 附件1 企业申报详情页 + 附件2 车船税目录\n\n")
        f.write(f"**行数(含配置展开)**: {len(records)} 行 | ")
        f.write(f"**原始车型数**: {n_original} | ")
        f.write(f"附件1缺失: {len(missing_md)} | ")
        f.write(f"附件2缺失: {len(missing_tax)}\n\n")
        f.write("> 备注：含 `/` 的续航/质量字段已按配置版本展开为独立行。电机功率中 `/` 表前/后双电机，不做拆分。\n\n")

        # Table
        table_fields = [
            "品牌", "产品型号", "产品名称", "动力形式",
            "电机功率(kW)", "single_multi_motor",
            "电池类型", "battery_chemistry_cn",
            "电池容量(kWh)", "电池质量(kg)", "纯电续航(km)", "整备质量(kg)",
            "总电量口径近似电耗(kWh/100km)", "电池包能量密度(Wh/kg)",
            "单位电量续航(km/kWh)", "电池质量占整备质量比(%)",
            "cell_supplier", "pack_supplier", "vertical_integration_flag",
            "metric_scope",
        ]
        header = "| " + " | ".join(table_fields) + " |"
        sep = "| " + " | ".join(["---"] * len(table_fields)) + " |"
        f.write(header + "\n")
        f.write(sep + "\n")
        for rec in records:
            row = []
            for k in table_fields:
                v = str(rec.get(k, "") or "")
                # Shorten long supplier names — keep only first supplier
                if k == "电芯/总成供应商" and len(v) > 40:
                    v = v[:40] + "…"
                row.append(v)
            f.write("| " + " | ".join(row) + " |\n")

        # Summary
        f.write("\n---\n\n")
        f.write("## 数据质量\n\n")
        f.write(f"- 附件1详情页缺失的型号: {', '.join(missing_md) if missing_md else '无'}\n")
        f.write(f"- 附件2车船税缺失的型号: {', '.join(missing_tax) if missing_tax else '无'}\n\n")

        # Per-brand breakdown (deduplicated by original model)
        f.write("## 各品牌车型数量\n\n")
        f.write("> 统计口径：按原始产品型号去重（去除#1/#2配置后缀），下同。\n\n")
        from collections import defaultdict
        brand_counts: dict[str, set[str]] = defaultdict(set)
        for r in records:
            mid = r.get("产品型号", "").split("#")[0]
            brand_counts[r["品牌"]].add(mid)
        f.write(f"| 品牌 | 原始车型数 | 配置行数 |\n|------|:--------:|:-------:|\n")
        for b in sorted(brand_counts, key=lambda x: len(brand_counts[x]), reverse=True):
            models_in_brand = len(brand_counts[b])
            configs_in_brand = sum(1 for r in records if r.get("品牌") == b)
            f.write(f"| {b} | {models_in_brand} | {configs_in_brand} |\n")
        f.write(f"| **合计** | **{n_original}** | **{n_expanded}** |\n")

        # Supplier coverage
        f.write("\n## 电池供应商覆盖结构\n\n")
        f.write("**电芯集团级覆盖（车型去重）**:\n\n")
        f.write(f"```\n{supplier_summary(records, by_model=True, by_group=True)}\n```\n")
        f.write("**电芯/总成组合级**:\n\n")
        f.write(f"```\n{supplier_summary(records, by_model=True, by_group=False)}\n```\n")
        f.write(f"**配置展开视角（{n_expanded}行）**:\n\n")
        f.write(f"```\n{supplier_summary(records, by_model=False, by_group=False)}\n```\n")

        f.write("**垂直整合分类**:\n\n")
        from collections import Counter
        vi_counts = Counter()
        for r in _dedup_by_model(records):
            vi = r.get("vertical_integration_flag", "")
            if vi:
                vi_counts[vi] += 1
        for vi, cnt in vi_counts.most_common():
            label_map = {"same_company": "同一企业", "same_group": "同集团不同主体", "cross_group": "跨企业合作"}
            f.write(f"- {label_map.get(vi, vi)}: {cnt}款\n")

        # Derived metric summary — dual perspective with explicit scope
        f.write("\n## 衍生指标汇总\n\n")
        covered = sum(1 for r in _dedup_by_model(records) if r.get("tax_catalog_match_flag") == "1")
        f.write("> **以下容量、续航、电池质量及近似电耗统计，仅覆盖附件2（车船税目录）成功匹配的"
                f"{covered}款增程/插混车型，不包含{len(original_model_ids)-covered}款纯电车型。**\n\n")
        f.write("> 电耗指标为\u201c总电量口径近似电耗\u201d，即电池总能量\u00f7纯电续航\u00d7100，为非官方口径"
                "（总电量≠可用电量，续航工况未统一），适用于**异常值筛查、同平台配置对比、同类车型粗略排序**，"
                "不宜直接认定为产品官方电耗。\n\n")

        # Deduplicate for model-level averages
        deduped = _dedup_by_model(records)

        eds_model = [r["总电量口径近似电耗(kWh/100km)"] for r in deduped
                     if isinstance(r.get("总电量口径近似电耗(kWh/100km)"), (int, float))]
        eds_config = [r["总电量口径近似电耗(kWh/100km)"] for r in records
                      if isinstance(r.get("总电量口径近似电耗(kWh/100km)"), (int, float))]
        if eds_model:
            f.write(f"- **按车型等权**（{len(eds_model)}个原始车型）平均近似电耗: {round(sum(eds_model)/len(eds_model), 1)} kWh/100km\n")
            f.write(f"  - 最低: {min(eds_model)} kWh/100km | 最高: {max(eds_model)} kWh/100km\n")
        if eds_config and len(eds_config) != len(eds_model):
            f.write(f"- **按配置行**（{len(eds_config)}行）平均近似电耗: {round(sum(eds_config)/len(eds_config), 1)} kWh/100km\n")

        ev_deduped = [r for r in deduped if r.get("动力形式") == "纯电动"]
        ev_all = [r for r in records if r.get("动力形式") == "纯电动"]
        phev_deduped = [r for r in deduped if "混合" in (r.get("动力形式") or "")]
        phev_all = [r for r in records if "混合" in (r.get("动力形式") or "")]

        if ev_deduped:
            ev_eds = [r["总电量口径近似电耗(kWh/100km)"] for r in ev_deduped
                      if isinstance(r.get("总电量口径近似电耗(kWh/100km)"), (int, float))]
            if ev_eds:
                f.write(f"- 纯电动（车型等权 {len(ev_deduped)}个）平均近似电耗: {round(sum(ev_eds)/len(ev_eds), 1)} kWh/100km\n")
        if phev_deduped:
            phev_ranges_model = [r["_range_num"] for r in phev_deduped if isinstance(r.get("_range_num"), (int, float))]
            phev_ranges_config = [r["_range_num"] for r in phev_all if isinstance(r.get("_range_num"), (int, float))]
            if phev_ranges_model:
                f.write(f"- PHEV/增程（车型等权 {len(phev_ranges_model)}个）平均纯电续航: {round(sum(phev_ranges_model)/len(phev_ranges_model))} km\n")
                if len(phev_ranges_config) != len(phev_ranges_model):
                    f.write(f"- PHEV/增程（配置行 {len(phev_ranges_config)}行）平均纯电续航: {round(sum(phev_ranges_config)/len(phev_ranges_config))} km\n")

    print(f"MD written: {md_path}")
    print(f"附件1缺失: {len(missing_md)}, 附件2缺失: {len(missing_tax)}")


if __name__ == "__main__":
    main()
