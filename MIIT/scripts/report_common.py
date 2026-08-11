#!/usr/bin/env python3
"""
MIIT 报告公共逻辑（P5 共享）—— 05_generate_brand_report 与 06_generate_category_report 共用。

包含：详情 .md 读取、车船税索引、名称映射、参数提取、车型分组、对比表格渲染、车型发现。
"""

import base64
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

from miit_paths import (  # noqa: E402
    NAME_MAP_PATH,
    VEHICLE_DETAILS_DIR,
    photo_dir,
    DEFAULT_BATCH,
)

IMAGE_VIEWS = ["左-右部照片.jpg", "后部照片.jpg"]


def read_md(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    data = {"raw_text": text}

    pairs = re.findall(r'\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|', text)
    for key, val in pairs:
        k, v = key.strip(), val.strip()
        if k in ("字段", "数值", "内容", "视角", "链接"):
            continue
        data[k] = v

    def _clean(v: str) -> str:
        v = re.sub(r'\*\*(.+?)\*\*', r'\1', v)
        v = re.sub(r'\*(.+?)\*', r'\1', v)
        return v.strip()

    for pattern, key in [
        (r'发动机型号\s*\|\s*(.+?)\s*\|', "发动机型号"),
        (r'发动机企业\s*\|\s*(.+?)\s*\|', "发动机企业"),
        (r'排量\(ml\)\s*\|\s*(.+?)\s*\|', "排量_ml"),
        (r'发动机最大净功率\(kW\)\s*\|\s*(.+?)\s*\|', "发动机最大净功率_kW"),
        (r'驱动电机峰值功率\(kW\)\s*\|\s*(.+?)\s*\|', "驱动电机峰值功率_kW"),
        (r'功率\(kw\)\s*\|\s*(.+?)\s*\|', "功率_kw"),
        (r'储能装置种类\s*\|\s*(.+?)\s*\|', "储能装置种类"),
        (r'电池单体/总成企业\s*\|\s*(.+?)\s*\|', "电池单体_总成企业"),
        (r'新能源类型\s*\|\s*(.+?)\s*\|', "新能源类型"),
        (r'额定载客\(人\)\s*\|\s*(.+?)\s*\|', "额定载客_人"),
        (r'额定载客（含驾驶员）（座位数）\s*\|\s*(.+?)\s*\|', "额定载客_人"),
        (r'WLTC燃料消耗量\s*\|\s*(.+?)\s*\|', "WLTC燃料消耗量"),
    ]:
        m = re.search(pattern, text)
        if m:
            data[key] = _clean(m.group(1))

    return data


def load_tax_index(tax_path: str) -> dict:
    """Index 车船税 JSON records by 产品型号"""
    data = json.loads(Path(tax_path).read_text(encoding="utf-8"))
    indexed = {}
    for sec_name in data.get("section_order", []):
        for rec in data["sections"].get(sec_name, {}).get("records", []):
            model = rec.get("产品型号", "")
            if model:
                indexed[model] = rec
    return indexed


def load_name_map() -> dict:
    """Load 车型通用名称映射（workflow/model_name_map.json），车船税缺失车型的名称补充。"""
    path = NAME_MAP_PATH
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: v["name"] for k, v in data.get("models", {}).items() if v.get("name")}
    except (json.JSONDecodeError, TypeError, AttributeError):
        return {}


def img_to_b64(path: Path) -> str:
    raw = path.read_bytes()
    ext = path.suffix.lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext.lstrip("."), "image/jpeg")
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def _parse_dims(dim_str: str) -> dict[str, str]:
    result = {}
    for part in re.split(r'[\s　]+', dim_str.strip()):
        m = re.match(r'(长|宽|高|轴距)[：:]\s*(\d+)', part)
        if m:
            result[m.group(1)] = m.group(2)
    return result


# ── Params extraction ────────────────────────────────────────────

PARAM_ORDER = [
    "长(mm)", "宽(mm)", "高(mm)", "轴距(mm)",
    "申报动力形式", "增程器", "驱动电机",
    "电池类型", "电池容量", "纯电续航（WLTC）", "电芯及电池总成",
    "座位数", "整备质量",
]

GROUP_INLINE = {"长(mm)", "宽(mm)", "高(mm)", "轴距(mm)"}
GROUP_TABLE = {
    "申报动力形式", "增程器", "驱动电机",
    "电池类型", "电池容量", "纯电续航（WLTC）", "电芯及电池总成",
    "座位数", "整备质量",
}


def extract_all_params(md_data: dict, model_id: str, tax_index: dict) -> OrderedDict:
    """Extract flat param dict for one model variant"""
    tax_rec = tax_index.get(model_id, {})
    p = OrderedDict()

    dim_raw = md_data.get("外形尺寸(mm)", "") or md_data.get("外形尺寸", "")
    if dim_raw:
        dims = _parse_dims(dim_raw)
        for label in ["长", "宽", "高"]:
            v = dims.get(label, "")
            if v:
                p[f"{label}(mm)"] = v
    wb = md_data.get("轴距(mm)", "") or md_data.get("轴距", "")
    if wb:
        m = re.search(r'\d+', wb)
        if m:
            p["轴距(mm)"] = m.group()

    energy = md_data.get("新能源类型", "")
    if energy:
        p["申报动力形式"] = energy
    elif "纯电动" in md_data.get("燃料种类", ""):
        p["申报动力形式"] = "纯电动"
    elif "增程" in md_data.get("产品名称", ""):
        p["申报动力形式"] = "插电式增程混合动力"
    elif "混合" in md_data.get("燃料种类", ""):
        p["申报动力形式"] = "插电式混合动力"

    if p.get("申报动力形式", "") != "纯电动":
        parts = []
        for field, suffix in [("发动机型号", ""), ("排量_ml", "ml"), ("发动机最大净功率_kW", "kW")]:
            v = md_data.get(field, "")
            if v and v != "-":
                parts.append(f"{v}{suffix}" if suffix else v)
        eng_co = md_data.get("发动机企业", "")
        if eng_co and parts:
            parts.append(eng_co)
        if parts:
            p["增程器"] = " / ".join(parts)

    motor = md_data.get("驱动电机峰值功率_kW", "") or md_data.get("功率_kw", "")
    if motor:
        p["驱动电机"] = motor if not re.match(r'^[\d/\s.]+$', motor) else f"{motor}kW"

    batt_type = md_data.get("储能装置种类", "")
    if not batt_type:
        other = md_data.get("其它", "")
        if other:
            m = re.search(r'储能装置种类[：:]([^，,;。\d]+)', other)
            if m:
                batt_type = m.group(1).strip()
    if batt_type:
        p["电池类型"] = batt_type

    supplier = md_data.get("电池单体_总成企业", "")
    if not supplier:
        other = md_data.get("其它", "")
        if other:
            m = re.search(r'(?:储能装置)?单体生产企业[：:]([^，,;。\d]+)', other)
            if not m:
                m = re.search(r'(?:储能装置)?总成生产企业[：:]([^，,;。\d]+)', other)
            if m:
                supplier = m.group(1).strip()
    if supplier:
        p["电芯及电池总成"] = supplier

    be = tax_rec.get("动力蓄电池总能量_kWh", "") or tax_rec.get("动力蓄电池组总能量_kWh", "")
    if be:
        p["电池容量"] = f"{be}kWh"

    wltc = tax_rec.get("纯电动续驶里程_km", "")
    if wltc:
        p["纯电续航（WLTC）"] = f"{wltc}km"

    passengers = md_data.get("额定载客_人", "")
    if not passengers:
        for key in md_data:
            if "额定载客" in key or "座位" in key:
                v = md_data[key]
                m = re.search(r'\d+', v)
                if m:
                    passengers = m.group()
                    break
    if passengers:
        p["座位数"] = passengers

    curb = tax_rec.get("整车整备质量_kg", "") or md_data.get("整备质量(kg)", "") or md_data.get("整备质量", "")
    if curb:
        p["整备质量"] = f"{curb}kg"

    return p


# ── Model discovery（data/vehicle_details/）────────────────────────

def discover_models(brand: str = "", tax_index: dict | None = None,
                    batch: str = DEFAULT_BATCH) -> list[dict]:
    """从 data/vehicle_details/ 发现某批车型，构建 model_infos。

    - 文件名 `{batch}_{model_id}-{产品名}.md`（身份 = batch:model_code），只扫本批
    - 若给 brand，则按 md 中"产品商标"过滤（如 零跑牌）
    - 照片目录为 data/vehicle_photos/{batch}_{model_id}/
    """
    tax_index = tax_index or {}
    model_infos = []
    for md_file in sorted(VEHICLE_DETAILS_DIR.glob(f"{batch}_*.md")):
        md_data = read_md(md_file)
        cpsb = md_data.get("产品商标", "")
        if brand and cpsb and brand not in cpsb.replace("牌", ""):
            continue
        stem = md_file.name.split("-", 1)[0]          # "{batch}_{model_id}"
        model_id = stem.split("_", 1)[1]
        params = extract_all_params(md_data, model_id, tax_index)
        tax_rec = tax_index.get(model_id, {})
        product_name = md_data.get("产品名称", "")
        model_infos.append({
            "model_id": model_id,
            "photo_dir": photo_dir(batch, model_id),
            "md_data": md_data,
            "params": params,
            "product_name": product_name,
            "product_short": product_name.replace("插电式增程混合动力", "").replace("插电式混合动力", "") if product_name else "",
            "tax_rec": tax_rec,
        })
    return model_infos


# ── Grouping ─────────────────────────────────────────────────────

def _model_base_id(mid: str) -> str:
    """Strip trailing variant suffix (BEV/PHEV/HEV/REEV + digits)."""
    base = re.sub(r'(BEV|PHEV|HEV|REEV)\w*$', '', mid)
    base = re.sub(r'\d+$', '', base)
    return base


def group_models(
    model_infos: list[dict], tax_index: dict, name_map: dict | None = None
) -> list[dict]:
    """Group model variants by 通用名称, with smart fallback.

    优先级：
    1. 车船税 通用名称 (normalized: take first name if comma-separated)
    2. model_name_map.json 本地映射（车船税缺失车型的名称补充）
    3. If missing, compute a model base ID (strip variant suffix) and check
       if any model sharing that base has a 通用名称 — if so, share it.
    4. Final fallback: model base ID.
    """
    name_map = name_map or {}
    # First pass: determine raw group key
    for info in model_infos:
        model_id = info["model_id"]
        tax_rec = tax_index.get(model_id, {})
        raw = tax_rec.get("通用名称", "")
        common_name = raw.split(",")[0].strip() if raw else ""
        info["_group_key"] = common_name or name_map.get(model_id, "") or ""
        info["_base_id"] = _model_base_id(model_id)

    # Second pass: build base_id → 通用名称 map; share across variants
    base_to_name: dict[str, str] = {}
    for info in model_infos:
        if info["_group_key"]:
            base = info["_base_id"]
            if base not in base_to_name:
                base_to_name[base] = info["_group_key"]

    for info in model_infos:
        if not info["_group_key"]:
            base = info["_base_id"]
            if base in base_to_name:
                info["_group_key"] = base_to_name[base]

    # Third pass: final fallback to base_id
    for info in model_infos:
        if not info["_group_key"]:
            info["_group_key"] = info["_base_id"]

    # Group
    groups: dict[str, list[dict]] = {}
    for info in model_infos:
        groups.setdefault(info["_group_key"], []).append(info)

    result = []
    for group_key, members in groups.items():
        result.append({
            "group_name": group_key,
            "members": sorted(members, key=lambda x: x["model_id"]),
            "variant_count": len(members),
        })
    return result


# ── HTML helpers ──────────────────────────────────────────────────

def _compare_class(val: str, common_val: str) -> str:
    """Return 'diff' if value differs from common"""
    return "diff" if val != common_val else ""


def _any_diff(all_params: list[OrderedDict], keys: list[str]) -> bool:
    """Check if any of the given keys differ across variants"""
    for key in keys:
        vals = [str(p.get(key, "")) for p in all_params]
        if len(set(vals)) > 1:
            return True
    return False


def _build_inline(keys: list[str], all_params: list[OrderedDict]) -> str:
    """Build inline param line with / separator for diffs"""
    parts = []
    for key in keys:
        vals = [str(p.get(key, "")) for p in all_params]
        if len(set(vals)) <= 1:
            parts.append(f"{key}: {vals[0]}")
        else:
            parts.append(f"{key}: {' / '.join(vals)}")
    return " \xa0｜ ".join(parts)


def _build_comparison_table(keys: list[str], all_params: list[OrderedDict], members: list[dict]) -> str:
    """Build table with side-by-side comparison when values differ.
    Common rows render as single-row, diff rows render with variant columns."""
    # Check if any key differs
    if not _any_diff(all_params, keys):
        # All same: single-value table
        trs = "".join(
            f'\n        <tr><td class="key">{k}</td><td class="value">{all_params[0].get(k, "-")}</td></tr>'
            for k in keys if any(p.get(k) for p in all_params)
        )
        return f'<table class="params-table">{trs}\n        </table>'

    # Some keys differ: side-by-side comparison
    ths = "".join(
        f'<th>{m["model_id"]} <span class="label-tag">{m.get("product_short","")}</span></th>'
        for m in members
    )
    trs = ""
    for key in keys:
        vals = [str(p.get(key, "-")) for p in all_params]
        if len(set(vals)) <= 1:
            # Common: merged row
            trs += f'\n        <tr><td>{key}</td><td colspan="{len(vals)}">{vals[0]}</td></tr>'
        else:
            # Diff: side-by-side
            tds = "".join(
                f'<td{" class=\"diff\"" if v != vals[0] else ""}>{v}</td>' for v in vals
            )
            trs += f'\n        <tr><td>{key}</td>{tds}</tr>'
    return f"""
    <table class="compare-table">
      <tr><th>参数</th>{ths}</tr>{trs}
    </table>"""
