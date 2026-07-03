"""
MIIT Vehicle Publicity Image Parser — P0

Consumes OCR result JSON (document_parse) and extracts structured vehicle records.

Usage:
    python -m mashang_workspace.promptbuilders.miit_new_car.miit_vehicle_publicity_image_parser \\
        --ocr-result mashang_workspace/outputs/ocr/results/<id>.json \\
        [--fallback-ocr-result mashang_workspace/outputs/ocr/results/<id>.json] \\
        [--output-root mashang_workspace/outputs/miit_new_car/vehicle_publicity_detail] \\
        [--force]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "miit_vehicle_publicity_detail.v0.1"

REQUIRED_FIELDS = [
    "product_brand",
    "product_model",
    "product_name",
    "enterprise_name",
    "length_mm",
    "width_mm",
    "height_mm",
    "wheelbase_mm",
]


@dataclass
class FieldValue:
    value: any = None
    type: str = "string"
    unit: Optional[str] = None
    confidence: str = "low"
    evidence_text: str = ""
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "type": self.type,
            "unit": self.unit,
            "confidence": self.confidence,
            "evidence_text": self.evidence_text,
            "source": self.source,
        }


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _clean_markdown(text: str) -> str:
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        # skip markdown separator rows: only |, spaces, dashes, colons
        stripped = line.replace("|", "").replace(" ", "").replace("-", "").replace(":", "")
        if stripped == "" and "|" in line:
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _parse_table_rows(markdown: str) -> list[list[str]]:
    rows = []
    for line in markdown.split("\n"):
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(cells)
    return rows


def _parse_header_fields(text: str) -> dict[str, str]:
    """Parse simple label: value pairs from text."""
    fields = {}
    patterns = [
        (r"产品商标:\s*(.+?)(?:\s+企业名称:|$)", "product_brand_raw"),
        (r"产品型号:\s*(.+)", "product_model_raw"),
        (r"产品名称:\s*(.+)", "product_name_raw"),
        (r"企业名称:\s*(.+)", "enterprise_name_raw"),
        (r"注册地址:\s*(.+)", "registered_address_raw"),
        (r"生产地址:\s*(.+)", "production_address_raw"),
        (r"目录序号:\s*(.+)", "catalog_no_raw"),
    ]
    for pat, key in patterns:
        m = re.search(pat, text)
        if m:
            fields[key] = m.group(1).strip()
    return fields


def _parse_table_specs(rows: list[list[str]]) -> dict[str, str]:
    """Parse table rows into key-value pairs. Handles 2-column and 4-column tables."""
    specs: dict[str, str] = {}
    label_map = {
        "外形尺寸\\(mm\\)": "dimensions_raw",
        "货箱栏板内尺寸\\(mm\\)": "cargo_box_raw",
        "排放依据标准": "emission_standard_raw",
        "燃料种类": "fuel_type_raw",
        "最高车速\\(km/h\\)": "max_speed_raw",
        "总质量\\(kg\\)": "gross_mass_raw",
        "额定载质量\\(kg\\)": "rated_load_raw",
        "转向型式": "steering_type_raw",
        "整备质量\\(kg\\)": "curb_weight_raw",
        "轴数": "axle_count_raw",
        "准拖挂车总质量\\(kg\\)": "trailer_mass_raw",
        "轴距\\(mm\\)": "wheelbase_raw",
        "轮胎规格": "tire_spec_raw",
        "钢板弹簧片数\\(前/后\\)": "spring_leaves_raw",
        "轮胎数": "tire_count_raw",
        "驾驶室准乘人数\\(人\\)": "cab_capacity_raw",
        "额定载客\\(含驾驶员\\)\\s*\\(座位数\\)": "passenger_count_raw",
        "轮距\\(前/后\\)mm": "track_raw",
        "接近角/离去角\\(度\\)": "angle_raw",
        "反光标识生产企业": "reflect_manufacturer_raw",
        "反光标识型号": "reflect_model_raw",
        "反光标识商标": "reflect_brand_raw",
        "防抱死制动系统": "abs_raw",
        "车辆识别代号\\(VIN\\)": "vin_raw",
        "前悬/后悬\\(mm\\)": "overhang_raw",
        "其它": "other_raw",
        "说明": "notes_raw",
        "油耗申报值\\(L/100km\\)": "fuel_consumption_raw",
    }
    for row in rows:
        if not row:
            continue
        # Scan every column as a potential label (4-col table: label1|val1|label2|val2)
        for col in range(0, len(row), 2):
            cell = row[col].strip() if col < len(row) else ""
            for pattern, key in label_map.items():
                if re.match(pattern, cell):
                    value = row[col + 1].strip() if col + 1 < len(row) else ""
                    # Don't overwrite if already set (first match wins)
                    if key not in specs:
                        specs[key] = value
                    break
    return specs


def _parse_dimensions(text: str) -> dict[str, int]:
    """Parse '长:4886宽:1984高:1927' into length/width/height."""
    result = {}
    m = re.search(r"长[：:]\s*(\d+)", text)
    if m:
        result["length_mm"] = int(m.group(1))
    m = re.search(r"宽[：:]\s*(\d+)", text)
    if m:
        result["width_mm"] = int(m.group(1))
    m = re.search(r"高[：:]\s*(\d+)", text)
    if m:
        result["height_mm"] = int(m.group(1))
    return result


def _parse_track(text: str) -> dict[str, int]:
    """Parse '前轮距:1661后轮距:1675' into front/rear track."""
    result = {}
    m = re.search(r"前轮距[：:](\d+)", text)
    if m:
        result["front_track_mm"] = int(m.group(1))
    m = re.search(r"后轮距[：:](\d+)", text)
    if m:
        result["rear_track_mm"] = int(m.group(1))
    return result


def _parse_overhang(text: str) -> dict[str, Optional[int]]:
    """Parse '774/1102' into front/rear overhang."""
    result: dict[str, Optional[int]] = {}
    if not text:
        return result
    m = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if m:
        result["front_overhang_mm"] = int(m.group(1))
        result["rear_overhang_mm"] = int(m.group(2))
    return result


def _parse_angle(text: str) -> Optional[str]:
    """Keep angle as string (e.g. '38/33,38/31')."""
    if not text or text.strip() == "":
        return None
    return text.strip()


def _parse_other(text: str) -> dict[str, any]:
    """Parse the '其它' field. Retains full raw text + stable derived tags."""
    result: dict[str, any] = {}
    if not text:
        return result

    result["other_notes_raw"] = text

    if re.search(r"EDR|事件数据记录", text):
        result["has_edr"] = True

    if re.search(r"允许外接充电|许外接充电", text):
        result["has_external_charging"] = True

    if re.search(r"拖挂|牵引专用装置", text):
        result["has_towing_device"] = True

    m = re.search(r"选装描述[：:]\s*([^;。]+)", text)
    if m:
        result["has_optional_equipment"] = True

    # Stable battery extractions — kept for convenience, not quality-gated
    m = re.search(r"储能装置种类[：:]\s*([^;。]+)", text)
    if m:
        result["battery_type"] = m.group(1).strip()

    m = re.search(r"储能装置单体生产企业[：:]\s*([^;。，]+)", text)
    if m:
        result["battery_cell_supplier"] = m.group(1).strip()

    m = re.search(r"储能装置总成生产企业[：:]\s*([^;。，]+)", text)
    if m:
        result["battery_pack_supplier"] = m.group(1).strip()

    return result


def _parse_chassis_table(markdown: str) -> dict[str, str]:
    """Parse the chassis/engine info table at the bottom."""
    result: dict[str, str] = {}
    table_rows = _parse_table_rows(markdown)

    # Find header row containing both 发动机型号 and 底盘型号 columns
    header_row = None
    header_idx = -1
    for i, row in enumerate(table_rows):
        row_text = " ".join(row)
        if ("发动机型号" in row_text or "底盘型号" in row_text) and "---" not in row_text:
            header_row = row
            header_idx = i
            break

    if not header_row:
        return result

    # Find data row (skip separator rows like | --- | --- |)
    data_row = None
    for i in range(header_idx + 1, len(table_rows)):
        row_text = " ".join(table_rows[i])
        if not re.match(r"^[\s\-—]+$", row_text.strip().replace("|", "").replace(" ", "")):
            data_row = table_rows[i]
            break

    if not data_row:
        return result

    for i, h in enumerate(header_row):
        h_clean = h.strip()
        if i < len(data_row) and data_row[i].strip():
            val = data_row[i].strip()
            if "底盘型号" in h_clean:
                result["chassis_model"] = val
            elif "底盘生产企业" in h_clean:
                result["chassis_manufacturer"] = val
            elif "底盘类别" in h_clean:
                result["chassis_category"] = val
            elif "发动机型号" in h_clean:
                result["engine_model"] = val
            elif "发动机企业" in h_clean:
                result["engine_manufacturer"] = val
            elif "排量" in h_clean:
                result["displacement_ml"] = val
            elif "功率" in h_clean and "kw" in h_clean.lower():
                result["power_kw"] = val
            elif "油耗" in h_clean:
                result["fuel_consumption"] = val

    return result


def _find_in_text(text: str, label: str, key: str) -> Optional[str]:
    """Find a simple label:value pattern in raw text."""
    # Try various separator patterns
    patterns = [
        rf"{re.escape(label)}\s*[：:]\s*(.+)",
        rf"{re.escape(label)}\s+(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = m.group(1).strip()
            if val and val != label:
                return val
    return None


def _parse_fallback_raw(text: str) -> dict[str, str]:
    """Parse general_ocr raw_text (line-by-line) for field values."""
    fields: dict[str, str] = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Check for known labels
        labels = {
            "产品商标:": "product_brand_raw",
            "产品型号:": "product_model_raw",
            "产品名称:": "product_name_raw",
            "企业名称:": "enterprise_name_raw",
            "注册地址:": "registered_address_raw",
            "生产地址:": "production_address_raw",
            "目录序号:": "catalog_no_raw",
            "燃料种类:": "fuel_type_raw",
            "排放依据标准:": "emission_standard_raw",
            "最高车速(km/h):": "max_speed_raw",
            "总质量(kg):": "gross_mass_raw",
            "转向型式:": "steering_type_raw",
            "整备质量(kg):": "curb_weight_raw",
            "轴距(mm):": "wheelbase_raw",
            "轮胎规格:": "tire_spec_raw",
            "轮胎数:": "tire_count_raw",
            "轴数:": "axle_count_raw",
            "防抱死制动系统:": "abs_raw",
            "前悬/后悬(mm):": "overhang_raw",
        }
        for lbl, key in labels.items():
            if line.startswith(lbl):
                val = line[len(lbl):].strip()
                # If value is empty, look at next line
                if not val and i + 1 < len(lines):
                    val = lines[i + 1].strip()
                fields[key] = val
                break

        # Handle multi-line values like "准拖挂车总质量(kg):" followed by value on next line
        if "准拖挂车总质量" in line:
            if i + 1 < len(lines):
                fields["trailer_mass_raw"] = lines[i + 1].strip()

        # Handle dimensions
        if line.startswith("长:"):
            fields["dimensions_raw"] = line

        # Handle track
        if line.startswith("前轮距:"):
            fields["track_raw"] = line

        # Handle other field (multi-line)
        if line == "其它:":
            other_lines = []
            j = i + 1
            while j < len(lines) and lines[j].strip() and ":" not in lines[j]:
                other_lines.append(lines[j].strip())
                j += 1
            if other_lines:
                fields["other_raw"] = " ".join(other_lines)

        i += 1

    return fields





def _make_field(
    value: any,
    type: str = "string",
    unit: Optional[str] = None,
    confidence: str = "low",
    evidence_text: str = "",
    source: str = "",
) -> FieldValue:
    return FieldValue(
        value=value,
        type=type,
        unit=unit,
        confidence=confidence,
        evidence_text=evidence_text,
        source=source,
    )


def _build_record_id(image_sha256: str, product_model: Optional[str]) -> str:
    prefix = image_sha256[:8] if image_sha256 else "unknown"
    model_part = product_model if product_model else "unknown"
    model_clean = re.sub(r"[^A-Za-z0-9]", "", model_part)[:20]
    return f"miit_ocr_{prefix}_{model_clean}"


def parse_ocr_result(
    ocr_result: dict,
    fallback_result: Optional[dict] = None,
) -> dict:
    primary = ocr_result
    image_sha256 = primary.get("image_sha256", "")
    source_image = primary.get("source_image_path", "")

    markdown = primary.get("markdown", "")
    raw_text = primary.get("raw_text", "")

    fallback_raw = fallback_result.get("raw_text", "") if fallback_result else ""
    fallback_id = fallback_result.get("ocr_result_id", "") if fallback_result else ""

    # Parse primary
    cleaned = _clean_markdown(markdown)
    # If markdown is clean but raw_text has more content, use raw_text too
    if not cleaned and raw_text:
        cleaned = raw_text

    header_fields = _parse_header_fields(cleaned)
    table_rows = _parse_table_rows(markdown)
    specs = _parse_table_specs(table_rows)

    dimensions = _parse_dimensions(specs.get("dimensions_raw", ""))
    track = _parse_track(specs.get("track_raw", ""))
    overhang = _parse_overhang(specs.get("overhang_raw", ""))
    other_data = _parse_other(specs.get("other_raw", ""))
    chassis = _parse_chassis_table(markdown)

    # Parse fallback (general_ocr) for cross-check
    fallback_fields: dict[str, str] = {}
    if fallback_raw:
        fallback_fields = _parse_fallback_raw(fallback_raw)

    # Build structured fields
    fields: dict[str, FieldValue] = {}
    source_track: dict[str, str] = {}

    def _set(field_key: str, val: any, ftype: str, unit: Optional[str], evidence: str, src: str):
        fields[field_key] = _make_field(
            value=val,
            type=ftype,
            unit=unit,
            evidence_text=evidence[:200],
            source=src,
        )
        source_track[field_key] = src

    def _best(key: str, parsed: any, fallback_lbl: str, conv=None):
        """Get best value from parsed or fallback."""
        if parsed is not None:
            return parsed
        if fallback_fields.get(fallback_lbl):
            raw = fallback_fields[fallback_lbl]
            if conv:
                try:
                    return conv(raw)
                except (ValueError, TypeError):
                    return raw
            return raw
        return None

    # Identity fields
    prod_brand = header_fields.get("product_brand_raw") or _find_in_text(cleaned, "产品商标", "")
    fb_brand = fallback_fields.get("product_brand_raw", "")
    pb_val = prod_brand or fb_brand or None
    pb_src = "document_parse" if prod_brand else ("general_ocr" if fb_brand else "document_parse")
    _set("product_brand", pb_val, "string", None, f"产品商标: {pb_val}" if pb_val else "", pb_src)

    prod_model = header_fields.get("product_model_raw") or _find_in_text(cleaned, "产品型号", "")
    fb_model = fallback_fields.get("product_model_raw", "")
    pm_val = prod_model or fb_model or None
    pm_src = "document_parse" if prod_model else ("general_ocr" if fb_model else "document_parse")
    _set("product_model", pm_val, "string", None, f"产品型号: {pm_val}" if pm_val else "", pm_src)

    prod_name = header_fields.get("product_name_raw") or _find_in_text(cleaned, "产品名称", "")
    fb_name = fallback_fields.get("product_name_raw", "")
    pn_val = prod_name or fb_name or None
    pn_src = "document_parse" if prod_name else ("general_ocr" if fb_name else "document_parse")
    _set("product_name", pn_val, "string", None, f"产品名称: {pn_val}" if pn_val else "", pn_src)

    ent_name = header_fields.get("enterprise_name_raw") or _find_in_text(cleaned, "企业名称", "")
    fb_ent = fallback_fields.get("enterprise_name_raw", "")
    ent_val = ent_name or fb_ent or None
    ent_src = "document_parse" if ent_name else ("general_ocr" if fb_ent else "document_parse")
    _set("enterprise_name", ent_val, "string", None, f"企业名称: {ent_val}" if ent_val else "", ent_src)

    reg_addr = header_fields.get("registered_address_raw") or _find_in_text(cleaned, "注册地址", "")
    _set("registered_address", reg_addr, "string", None, f"注册地址: {reg_addr}" if reg_addr else "", "document_parse")

    prod_addr = header_fields.get("production_address_raw") or _find_in_text(cleaned, "生产地址", "")
    _set("production_address", prod_addr, "string", None, f"生产地址: {prod_addr}" if prod_addr else "", "document_parse")

    cat_no = header_fields.get("catalog_no_raw") or _find_in_text(cleaned, "目录序号", "")
    _set("catalog_no", cat_no, "string", None, f"目录序号: {cat_no}" if cat_no else "", "document_parse")

    # Dimensions
    lv = _best("length_mm", dimensions.get("length_mm"), "dimensions_raw")
    _set("length_mm", lv, "integer", "mm", f"长: {lv}" if lv else "", "document_parse")

    wv = _best("width_mm", dimensions.get("width_mm"), "dimensions_raw")
    _set("width_mm", wv, "integer", "mm", f"宽: {wv}" if wv else "", "document_parse")

    hv = _best("height_mm", dimensions.get("height_mm"), "dimensions_raw")
    _set("height_mm", hv, "integer", "mm", f"高: {hv}" if hv else "", "document_parse")

    wb_raw = _best("wheelbase_mm", specs.get("wheelbase_raw"), "wheelbase_raw")
    if wb_raw is not None:
        m = re.search(r"(\d+)", str(wb_raw))
        if m:
            wb_raw = int(m.group(1))
    _set("wheelbase_mm", wb_raw, "integer", "mm", f"轴距: {wb_raw}" if wb_raw else "", "document_parse")

    ft = _best("front_track_mm", track.get("front_track_mm"), "track_raw")
    _set("front_track_mm", ft, "integer", "mm", f"前轮距: {ft}" if ft else "", "document_parse")

    rt = _best("rear_track_mm", track.get("rear_track_mm"), "track_raw")
    _set("rear_track_mm", rt, "integer", "mm", f"后轮距: {rt}" if rt else "", "document_parse")

    fo = _best("front_overhang_mm", overhang.get("front_overhang_mm"), "overhang_raw", int)
    _set("front_overhang_mm", fo, "integer", "mm", f"前悬: {fo}" if fo else "", "document_parse")

    ro = _best("rear_overhang_mm", overhang.get("rear_overhang_mm"), "overhang_raw", int)
    _set("rear_overhang_mm", ro, "integer", "mm", f"后悬: {ro}" if ro else "", "document_parse")

    angle = _parse_angle(specs.get("angle_raw", ""))
    _set("approach_departure_angle", angle, "string", None, f"接近角/离去角: {angle}" if angle else "", "document_parse")

    ts = _best("tire_spec", specs.get("tire_spec_raw"), "tire_spec_raw")
    _set("tire_spec", ts, "string", None, f"轮胎规格: {ts}" if ts else "", "document_parse")

    tc_raw = _best("tire_count", specs.get("tire_count_raw"), "tire_count_raw")
    if tc_raw is not None:
        m = re.search(r"(\d+)", str(tc_raw))
        if m:
            tc_raw = int(m.group(1))
    _set("tire_count", tc_raw, "integer", None, f"轮胎数: {tc_raw}" if tc_raw else "", "document_parse")

    # Mass & capacity
    gm_raw = _best("gross_mass_kg", specs.get("gross_mass_raw"), "gross_mass_raw")
    if gm_raw is not None:
        m = re.search(r"(\d+)", str(gm_raw))
        if m:
            gm_raw = int(m.group(1))
    _set("gross_mass_kg", gm_raw, "integer", "kg", f"总质量: {gm_raw}" if gm_raw else "", "document_parse")

    cw_raw = _best("curb_weight_kg", specs.get("curb_weight_raw"), "curb_weight_raw")
    if cw_raw is not None:
        m = re.search(r"(\d+)", str(cw_raw))
        if m:
            cw_raw = int(m.group(1))
    _set("curb_weight_kg", cw_raw, "integer", "kg", f"整备质量: {cw_raw}" if cw_raw else "", "document_parse")

    pc = _best("rated_passenger_count", specs.get("passenger_count_raw"), "passenger_count_raw")
    if pc is not None:
        m = re.search(r"(\d+)", str(pc))
        if m:
            pc = int(m.group(1))
    _set("rated_passenger_count", pc, "integer", "人", f"额定载客: {pc}" if pc else "", "document_parse")

    tm = specs.get("trailer_mass_raw")
    _set("trailer_mass_kg", tm, "string", "kg", f"准拖挂车总质量: {tm}" if tm else "", "document_parse")

    # Powertrain
    ft_raw = _best("fuel_type", specs.get("fuel_type_raw"), "fuel_type_raw")
    _set("fuel_type", ft_raw, "string", None, f"燃料种类: {ft_raw}" if ft_raw else "", "document_parse")

    es = _best("emission_standard", specs.get("emission_standard_raw"), "emission_standard_raw")
    _set("emission_standard", es, "string", None, f"排放依据标准: {es}" if es else "", "document_parse")

    ms_raw = _best("max_speed_kmh", specs.get("max_speed_raw"), "max_speed_raw")
    if ms_raw is not None:
        m = re.search(r"(\d+)", str(ms_raw))
        if m:
            ms_raw = int(m.group(1))
    _set("max_speed_kmh", ms_raw, "integer", "km/h", f"最高车速: {ms_raw}" if ms_raw else "", "document_parse")

    # Engine fields: parse from general_ocr raw text (known structure)
    def _engine_val(label: str, idx: int) -> Optional[str]:
        """Get engine table value. general_ocr has labels then values as separate lines."""
        if not fallback_raw:
            return None
        lines = fallback_raw.split("\n")
        label_idx = None
        for i, line in enumerate(lines):
            if line.strip() == label:
                label_idx = i
                break
        if label_idx is None:
            return None
        # After all engine labels (排量, 发动机型号, 发动机企业, 功率, 油耗), the values follow
        # Structure: ... labels ..., then values on subsequent lines: 1998, 185, E20NB, 长城汽车股份有限公司
        engine_labels = ["排量(ml)", "发动机型号", "发动机企业", "功率(kw)", "油耗(L/100km)"]
        # Find all engine label positions
        positions = [(j, lines[j].strip()) for j in range(len(lines)) if lines[j].strip() in engine_labels]
        if len(positions) < 4:
            return None
        # Values start after the last engine label
        last_pos = positions[-1][0]
        values = []
        for j in range(last_pos + 1, min(last_pos + 10, len(lines))):
            val = lines[j].strip()
            if val and val not in engine_labels:
                values.append(val)
        # Expected order: 排量, 功率, 发动机型号, 发动机企业, 油耗
        engine_value_order = {0: "排量", 1: "功率", 2: "发动机型号", 3: "发动机企业", 4: "油耗"}
        label_to_order = {"排量(ml)": 0, "功率(kw)": 1, "发动机型号": 2, "发动机企业": 3, "油耗(L/100km)": 4}
        # Find which index this label corresponds to
        orig_idx = None
        for pos, lbl in positions:
            if lbl == label:
                orig_idx = label_to_order.get(lbl)
                break
        if orig_idx is not None and orig_idx < len(values):
            return values[orig_idx]
        return None

    em = chassis.get("engine_model") or _engine_val("发动机型号", 2)
    _set("engine_model", em, "string", None, f"发动机型号: {em}" if em else "", "document_parse")

    eman = chassis.get("engine_manufacturer") or _engine_val("发动机企业", 3)
    _set("engine_manufacturer", eman, "string", None, f"发动机企业: {eman}" if eman else "", "document_parse")

    displ = chassis.get("displacement_ml") or _engine_val("排量(ml)", 0)
    if displ:
        m = re.search(r"(\d+)", str(displ))
        if m:
            displ = int(m.group(1))
    _set("displacement_ml", displ, "integer", "ml", f"排量: {displ}" if displ else "", "document_parse")

    pwr = chassis.get("power_kw") or _engine_val("功率(kw)", 1)
    if pwr:
        m = re.search(r"(\d+)", str(pwr))
        if m:
            pwr = int(m.group(1))
    if not pwr:
        m = re.search(r"功率\s*[:：]?\s*(\d+)\s*kw", cleaned, re.IGNORECASE)
        if m:
            pwr = int(m.group(1))
    _set("power_kw", pwr, "integer", "kw", f"功率: {pwr}" if pwr else "", "document_parse")

    # Chassis: use document_parse markdown table
    _set("chassis_model", chassis.get("chassis_model"), "string", None,
         f"底盘型号: {chassis.get('chassis_model')}" if chassis.get("chassis_model") else "", "document_parse")
    _set("chassis_manufacturer", chassis.get("chassis_manufacturer"), "string", None,
         f"底盘生产企业: {chassis.get('chassis_manufacturer')}" if chassis.get("chassis_manufacturer") else "", "document_parse")
    _set("chassis_category", chassis.get("chassis_category"), "string", None,
         f"底盘类别: {chassis.get('chassis_category')}" if chassis.get("chassis_category") else "", "document_parse")

    # Compliance
    steer = _best("steering_type", specs.get("steering_type_raw"), "steering_type_raw")
    _set("steering_type", steer, "string", None, f"转向型式: {steer}" if steer else "", "document_parse")

    abs_val = _best("abs", specs.get("abs_raw"), "abs_raw")
    _set("abs", abs_val, "string", None, f"防抱死制动系统: {abs_val}" if abs_val else "", "document_parse")

    vin = _best("vin_pattern", specs.get("vin_raw"), "vin_raw")
    _set("vin_pattern", vin, "string", None, f"车辆识别代号: {vin}" if vin else "", "document_parse")

    other_raw = other_data.get("other_notes_raw", None)
    _set("other_notes_raw", other_raw, "string", None, f"其它: {other_raw[:100]}" if other_raw else "", "document_parse")

    # Derived tags from '其它' field (not quality-gated)
    _set("has_edr", other_data.get("has_edr") or False, "boolean", None,
         "EDR detected in 其它" if other_data.get("has_edr") else "", "document_parse")
    _set("has_external_charging", other_data.get("has_external_charging") or False, "boolean", None,
         "外接充电 detected in 其它" if other_data.get("has_external_charging") else "", "document_parse")
    _set("has_towing_device", other_data.get("has_towing_device") or False, "boolean", None,
         "拖挂 detected in 其它" if other_data.get("has_towing_device") else "", "document_parse")
    _set("has_optional_equipment", other_data.get("has_optional_equipment") or False, "boolean", None,
         "选装 detected in 其它" if other_data.get("has_optional_equipment") else "", "document_parse")

    # Stable battery extractions — convenient but not quality-gated
    batt = other_data.get("battery_type", None)
    if batt:
        _set("battery_type", batt, "string", None, f"储能装置种类: {batt}", "document_parse")
    bcs = other_data.get("battery_cell_supplier", None)
    if bcs:
        _set("battery_cell_supplier", bcs, "string", None, f"储能装置单体: {bcs}", "document_parse")
    bps = other_data.get("battery_pack_supplier", None)
    if bps:
        _set("battery_pack_supplier", bps, "string", None, f"储能装置总成: {bps}", "document_parse")

    # Cross-check
    cross_check: dict = {"enabled": bool(fallback_result), "matched_fields": [], "conflicts": [], "warnings": []}

    if fallback_result:
        cross_check_fields = [
            ("product_brand", "产品商标", "product_brand_raw"),
            ("product_model", "产品型号", "product_model_raw"),
            ("product_name", "产品名称", "product_name_raw"),
            ("enterprise_name", "企业名称", "enterprise_name_raw"),
            ("length_mm", "长", "dimensions_raw"),
            ("wheelbase_mm", "轴距", "wheelbase_raw"),
            ("gross_mass_kg", "总质量", "gross_mass_raw"),
            ("curb_weight_kg", "整备质量", "curb_weight_raw"),
            ("fuel_type", "燃料种类", "fuel_type_raw"),
            ("engine_model", "发动机型号", None),
        ]
        for fkey, label, fb_lbl in cross_check_fields:
            pv = fields.get(fkey)
            fv_raw = fallback_fields.get(fb_lbl) if fb_lbl else None

            if pv and pv.value:
                pv_text = str(pv.value)
                # Check if fallback has the value
                fb_val_ok = False
                if fv_raw:
                    fb_val_ok = pv_text in fv_raw or fv_raw in pv_text or pv_text == fv_raw
                elif fallback_raw and label:
                    fb_val_ok = label in fallback_raw and pv_text in fallback_raw

                if fb_val_ok:
                    cross_check["matched_fields"].append(fkey)
                elif fallback_raw:
                    # Try to find the value in raw text
                    if pv_text in fallback_raw:
                        cross_check["matched_fields"].append(fkey)

        # Check for explicit conflicts
        for fkey, fb_lbl in [("product_model", "product_model_raw"), ("enterprise_name", "enterprise_name_raw")]:
            pv = fields.get(fkey)
            fv = fallback_fields.get(fb_lbl) if fb_lbl else None
            if pv and pv.value and fv and str(pv.value) != fv:
                cross_check["conflicts"].append({
                    "field": fkey,
                    "primary_value": str(pv.value),
                    "fallback_value": fv,
                    "message": f"document_parse='{pv.value}' != general_ocr='{fv}'",
                })

        # Warnings for long text fields
        if fallback_raw and specs.get("other_raw"):
            # Check if there's significant difference in other field
            pass

    # Determine quality
    field_count = sum(1 for f in fields.values() if f.value is not None)
    missing_required = [f for f in REQUIRED_FIELDS if f not in fields or fields[f].value is None]

    if len(missing_required) >= len(REQUIRED_FIELDS):
        parse_status = "failed"
        needs_review = True
        reason = f"All required fields missing: {', '.join(missing_required)}"
    elif missing_required:
        parse_status = "partial"
        needs_review = True
        reason = f"Missing required fields: {', '.join(missing_required)}"
    else:
        parse_status = "success"
        needs_review = False
        reason = ""

    # Determine record_role
    IDENTITY_FIELDS = ["product_brand", "product_model", "product_name", "enterprise_name"]
    TECH_FIELDS = [
        "length_mm", "width_mm", "height_mm", "wheelbase_mm",
        "front_track_mm", "rear_track_mm", "front_overhang_mm", "rear_overhang_mm",
        "gross_mass_kg", "curb_weight_kg", "rated_passenger_count", "trailer_mass_kg",
        "fuel_type", "max_speed_kmh", "tire_spec", "tire_count",
        "approach_departure_angle",
        "engine_model", "engine_manufacturer", "displacement_ml", "power_kw",
        "battery_type", "abs", "vin_pattern",
        "has_edr", "has_towing_device",
    ]

    identity_ok = all(
        f in fields and fields[f].value is not None for f in IDENTITY_FIELDS
    )
    tech_count = sum(
        1 for f in TECH_FIELDS if f in fields and fields[f].value is not None
    )

    if identity_ok:
        record_role = "primary_vehicle_record"
        join_status = "not_required"
        join_candidates: list[str] = []
        if parse_status == "success" and not needs_review:
            needs_review = False
        SUPPLEMENT_REASON = ""
    elif tech_count >= 10:
        record_role = "supplement_record"
        join_status = "unlinked"
        join_candidates = []
        needs_review = True
        SUPPLEMENT_REASON = "; identity fields missing; technical fields parsed; requires linking to primary vehicle record"
        if reason:
            reason += SUPPLEMENT_REASON
        else:
            reason = SUPPLEMENT_REASON.lstrip("; ")
    else:
        record_role = "unknown_record"
        join_status = "unknown"
        join_candidates = []
        needs_review = True
        UNKNOWN_REASON = "; insufficient identity and technical fields; record role unknown"
        if reason:
            reason += UNKNOWN_REASON
        else:
            reason = UNKNOWN_REASON.lstrip("; ")

    # Build vehicle record ID
    prod_model_val = fields.get("product_model")
    model_str = str(prod_model_val.value) if prod_model_val and prod_model_val.value else None
    vehicle_record_id = _build_record_id(image_sha256, model_str)

    # Build output
    output_fields = {}
    for fk, fv in fields.items():
        output_fields[fk] = fv.to_dict()

    # Adjust confidence based on cross-check
    for fkey in cross_check["matched_fields"]:
        if fkey in output_fields:
            output_fields[fkey]["confidence"] = "high"
            if cross_check["enabled"]:
                output_fields[fkey]["source"] = "document_parse+general_ocr"

    result = {
        "schema_version": SCHEMA_VERSION,
        "vehicle_record_id": vehicle_record_id,
        "record_role": record_role,
        "join_status": join_status,
        "join_candidates": join_candidates,
        "parse_status": parse_status,
        "source_trace": {
            "source_image_path": source_image,
            "primary_ocr_result_id": primary.get("ocr_result_id", ""),
            "primary_ocr_mode": primary.get("mode", ""),
            "fallback_ocr_result_id": fallback_id,
            "fallback_ocr_mode": fallback_result.get("mode", "") if fallback_result else "",
            "image_sha256": image_sha256,
            "primary_raw_response_path": primary.get("raw_response_path", ""),
            "fallback_raw_response_path": fallback_result.get("raw_response_path", "") if fallback_result else "",
            "primary_markdown": markdown,
        },
        "fields": output_fields,
        "cross_check": cross_check,
        "quality": {
            "parsed_field_count": field_count,
            "required_field_missing": missing_required,
            "needs_manual_review": needs_review,
            "quality_reason": reason,
        },
    }

    return result


def save_record(result: dict, output_root: str, force: bool = False):
    out_dir = Path(output_root) / "records"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{result['vehicle_record_id']}.json"
    if out_path.exists() and not force:
        print(f"[SKIP] {out_path} exists (use --force to overwrite)")
        return
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {out_path}")


def main():
    p = argparse.ArgumentParser(description="MIIT Vehicle Publicity Image Parser")
    p.add_argument("--ocr-result", required=True, help="Document parse OCR result JSON path")
    p.add_argument("--fallback-ocr-result", help="General OCR result JSON path for cross-check")
    p.add_argument(
        "--output-root",
        default="mashang_workspace/outputs/miit_new_car/vehicle_publicity_detail",
        help="Output root directory",
    )
    p.add_argument("--force", action="store_true", help="Overwrite existing records")
    args = p.parse_args()

    primary = _load_json(args.ocr_result)
    fallback = _load_json(args.fallback_ocr_result) if args.fallback_ocr_result else None

    result = parse_ocr_result(primary, fallback)
    save_record(result, args.output_root, args.force)

    print(json.dumps({
        "parse_status": result["parse_status"],
        "record_role": result["record_role"],
        "fields": len(result["fields"]),
        "vehicle_record_id": result["vehicle_record_id"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
