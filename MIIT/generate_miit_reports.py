#!/usr/bin/env python3
"""
MIIT 车型归档 HTML 报告生成器

步骤：
  1. 读取归档 + 车船税数据
  2. 按通用名称分组合并（识别同一车型的不同配置/变体）
  3. 每组生成一个对比报告：公共参数 + 差异分列

用法:
  python3 generate_miit_reports.py \
    --archive-dir 409-小米 \
    --tax-json 车型清单_第88批车船税.json \
    --brand "小米" \
    --output-dir xiaomi_reports \
    --batch "第409批"
"""

import argparse
import base64
import json
import re
from pathlib import Path
from collections import OrderedDict

IMAGE_VIEWS = ["左-右部照片.jpg", "后部照片.jpg"]

CSS = """
:root {
  --zh-blue: #174A7C;
  --zh-deep-blue: #06213D;
  --zh-cyan: #7ECDEB;
  --zh-light-blue: #DDEFF8;
  --zh-accent: #D79A36;
  --zh-text: #1F2D3D;
  --zh-muted: #6B7C8F;
  --zh-card: #FFFFFF;
  --zh-bg: #EFF2F5;
  --zh-border: #DCE0E5;
  --zh-group-bg: #F5F7FA;
  --diff-bg: #FFFCF0;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, "PingFang SC", "Noto Sans SC", "Helvetica Neue", sans-serif;
  background: var(--zh-bg);
  color: var(--zh-text);
  line-height: 1.6;
  padding: 40px 20px;
}
.container { max-width: 1060px; margin: 0 auto; }
.header {
  text-align: center; margin-bottom: 32px; padding-bottom: 24px;
  border-bottom: 2px solid var(--zh-border);
}
.header h1 { font-size: 28px; font-weight: 700; color: var(--zh-blue); letter-spacing: 1px; }
.header .subtitle { font-size: 14px; color: var(--zh-muted); margin-top: 6px; }
.header .model-id { font-size: 12px; color: var(--zh-muted); font-family: "SF Mono", Menlo, monospace; margin-top: 4px; }
.photo-section { display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap; }
.photo-card {
  flex: 1; min-width: 280px; background: var(--zh-card); border-radius: 12px;
  overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.06); border: 1px solid var(--zh-border);
}
.photo {
  aspect-ratio: 16 / 10;
  background: #e9eef2;
}
.photo img { width: 100%; height: 100%; object-fit: contain; display: block; }
.photo-card .label { padding: 8px 14px; font-size: 12px; color: var(--zh-muted); background: var(--zh-group-bg); border-top: 1px solid var(--zh-border); }
.params-card { background: var(--zh-card); border-radius: 12px; border: 1px solid var(--zh-border); overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.params-card + .params-card { margin-top: 16px; }
.group-header { padding: 12px 24px; font-size: 13px; font-weight: 600; color: var(--zh-blue); background: var(--zh-light-blue); border-bottom: 1px solid var(--zh-border); letter-spacing: 0.5px; }
.params-table { width: 100%; border-collapse: collapse; }
.params-table tr { border-bottom: 1px solid #f0ede8; }
.params-table tr:last-child { border-bottom: none; }
.params-table td { padding: 12px 24px; font-size: 14px; vertical-align: top; }
.params-table .key { width: 160px; font-weight: 500; color: var(--zh-muted); white-space: nowrap; }
.params-table .value { color: var(--zh-text); }
.inline-params { padding: 14px 24px; font-size: 14px; color: var(--zh-text); }
.compare-table { width: 100%; border-collapse: collapse; }
.compare-table th { padding: 10px 18px; font-size: 12px; font-weight: 600; color: var(--zh-muted); background: var(--zh-group-bg); border-bottom: 1px solid var(--zh-border); text-align: left; white-space: nowrap; }
.compare-table th:first-child { padding-left: 24px; width: 140px; }
.compare-table td { padding: 10px 18px; font-size: 14px; border-bottom: 1px solid #f0ede8; vertical-align: top; }
.compare-table td:first-child { padding-left: 24px; font-weight: 500; color: var(--zh-muted); white-space: nowrap; }
.compare-table tr.diff td { background: var(--diff-bg); }
.compare-table tr:last-child td { border-bottom: none; }
.label-tag { display: inline-block; font-size: 11px; padding: 1px 8px; border-radius: 4px; background: var(--zh-light-blue); color: var(--zh-blue); margin-left: 4px; }
.footer { text-align: center; margin-top: 32px; padding-top: 20px; border-top: 1px solid var(--zh-border); font-size: 12px; color: var(--zh-muted); }
"""


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


# ── Grouping ─────────────────────────────────────────────────────

def _model_base_id(mid: str) -> str:
    """Strip trailing variant suffix (BEV/PHEV/HEV/REEV + digits)."""
    base = re.sub(r'(BEV|PHEV|HEV|REEV)\w*$', '', mid)
    base = re.sub(r'\d+$', '', base)
    return base


def group_models(
    model_infos: list[dict], tax_index: dict
) -> list[dict]:
    """Group model variants by 通用名称, with smart fallback.

    1. Use 通用名称 from 车船税 (normalized: take first name if comma-separated)
    2. If missing, compute a model base ID (strip variant suffix) and check
       if any model sharing that base has a 通用名称 — if so, share it.
    3. Final fallback: model base ID.
    """
    # First pass: determine raw group key
    for info in model_infos:
        model_id = info["model_id"]
        tax_rec = tax_index.get(model_id, {})
        raw = tax_rec.get("通用名称", "")
        common_name = raw.split(",")[0].strip() if raw else ""
        info["_group_key"] = common_name or ""
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


# ── HTML Generation ──────────────────────────────────────────────

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


def generate_group_html(
    group: dict, brand: str, batch: str
) -> str:
    members = group["members"]
    group_name = group["group_name"]
    variant_count = group["variant_count"]

    all_params: list[OrderedDict] = [m["params"] for m in members]

    # ── Category definitions with their param keys ──
    categories = [
        ("整车尺寸", ["长(mm)", "宽(mm)", "高(mm)", "轴距(mm)"], "inline"),
        ("动力与底盘", ["申报动力形式", "增程器", "驱动电机", "座位数", "整备质量"], "table"),
        ("电池与续航", ["电池类型", "电池容量", "纯电续航（WLTC）", "电芯及电池总成"], "table"),
    ]

    sections = ""
    for cat_name, cat_keys, cat_type in categories:
        present_keys = [k for k in cat_keys if any(p.get(k) for p in all_params)]
        if not present_keys:
            continue

        if cat_type == "inline":
            sections += f"""
  <div class="params-card">
    <div class="group-header">{cat_name}</div>
    <div class="inline-params">{_build_inline(present_keys, all_params)}</div>
  </div>"""
        else:
            sections += f"""
  <div class="params-card">
    <div class="group-header">{cat_name}</div>
    {_build_comparison_table(present_keys, all_params, members)}
  </div>"""

    # ── Photos: exactly 2 (左-右部 + 后部) from primary variant ──
    primary = members[0]
    model_dir = primary["model_dir"]
    img_rows = ""
    for view in IMAGE_VIEWS:
        p = model_dir / view
        if p.exists():
            img_rows += f"""
    <div class="photo-card">
      <div class="photo"><img src="{img_to_b64(p)}" alt="{view}"></div>
      <div class="label">{view.replace('.jpg','')}</div>
    </div>"""

    display_name = f"{brand} | {group_name}"
    variant_info = f"{variant_count} 款配置"
    model_ids_list = ", ".join(m["model_id"] for m in members)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{display_name} — MIIT 新车公示</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{display_name}</h1>
    <div class="subtitle">{variant_info}</div>
    <div class="model-id">{model_ids_list}</div>
  </div>
  <div class="photo-section">{img_rows}</div>
  {sections}
  <div class="footer">
    <p>数据来源：工信部道路机动车辆生产企业及产品公告（{batch}）· 存档时间：2026-07-10</p>
    <p style="margin-top:4px;">MIIT New Car Report · Generated by mashang-service</p>
  </div>
</div>
</body>
</html>"""


def generate_index(entries: list[tuple[str, str, int, str]], brand: str, batch: str) -> str:
    cards = ""
    for group_name, variant_info, count, path in entries:
        cards += f"""
    <a href="{path}" class="card">
      <div class="card-title">{brand} {group_name}</div>
      <div class="card-sub">{variant_info}</div>
      <div class="card-model">{count} 款配置</div>
    </a>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{brand} — {batch} MIIT 新车公示</title>
<style>
:root {{ --zh-blue: #174A7C; --zh-deep-blue: #06213D; --zh-cyan: #7ECDEB; --zh-light-blue: #DDEFF8; --zh-accent: #D79A36; --zh-text: #1F2D3D; --zh-muted: #6B7C8F; --zh-bg: #EFF2F5; --zh-card: #FFF; --zh-border: #DCE0E5; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, "PingFang SC","Noto Sans SC",sans-serif; background: var(--zh-bg); color: var(--zh-text); padding: 40px 20px; }}
.container {{ max-width: 720px; margin: 0 auto; }}
h1 {{ font-size: 26px; color: var(--zh-blue); margin-bottom: 8px; }}
.subtitle {{ color: var(--zh-muted); font-size: 14px; margin-bottom: 28px; }}
.grid {{ display: flex; flex-direction: column; gap: 12px; }}
.card {{ display: block; padding: 18px 22px; background: var(--zh-card); border-radius: 12px; border: 1px solid var(--zh-border); text-decoration: none; color: var(--zh-text); transition: box-shadow 0.15s; }}
.card:hover {{ box-shadow: 0 2px 10px rgba(0,0,0,0.06); }}
.card-title {{ font-size: 17px; font-weight: 600; color: var(--zh-blue); }}
.card-sub {{ font-size: 13px; color: var(--zh-muted); margin-top: 2px; }}
.card-model {{ font-size: 12px; color: var(--zh-muted); font-family: Menlo, monospace; margin-top: 4px; }}
.footer {{ margin-top: 32px; text-align: center; font-size: 12px; color: var(--zh-muted); }}
</style>
</head>
<body>
<div class="container">
  <h1>{brand} · {batch} MIIT 新车公示</h1>
  <div class="subtitle">共 {len(entries)} 款车型（含 {sum(e[2] for e in entries)} 个配置）</div>
  <div class="grid">{cards}</div>
  <div class="footer"><p>数据来源：工信部道路机动车辆生产企业及产品公告（{batch}）</p></div>
</div>
</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MIIT 车型归档 HTML 报告生成器")
    parser.add_argument("--archive-dir", required=True, help="品牌归档目录，如 409-小米")
    parser.add_argument("--tax-json", required=True, help="车船税 JSON 文件路径")
    parser.add_argument("--brand", default="", help="品牌名称，如 小米、理想")
    parser.add_argument("--output-dir", required=True, help="HTML 输出目录")
    parser.add_argument("--batch", default="第409批", help="公告批次")
    args = parser.parse_args()

    archive_dir = Path(args.archive_dir)
    tax_index = load_tax_index(args.tax_json)
    brand = args.brand or archive_dir.name.split("-", 1)[1] if "-" in archive_dir.name else ""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Load all model info
    model_dirs = sorted(archive_dir.glob("[A-Z]*"))
    model_infos = []
    for model_dir in model_dirs:
        if not model_dir.is_dir():
            continue
        model_id = model_dir.name
        md_files = list(archive_dir.glob(f"{model_id}*.md"))
        if not md_files:
            print(f"  ⚠ {model_id}: 无 .md 文件")
            continue
        md_data = read_md(md_files[0])
        params = extract_all_params(md_data, model_id, tax_index)
        tax_rec = tax_index.get(model_id, {})
        product_name = md_data.get("产品名称", "")
        model_infos.append({
            "model_id": model_id,
            "model_dir": model_dir,
            "md_data": md_data,
            "params": params,
            "product_name": product_name,
            "product_short": product_name.replace("插电式增程混合动力", "").replace("插电式混合动力", "") if product_name else "",
            "tax_rec": tax_rec,
        })

    # Step 2: Group by 通用名称
    groups = group_models(model_infos, tax_index)
    entries = []

    for g in groups:
        html = generate_group_html(g, brand, args.batch)
        safe_name = g["group_name"].replace(" ", "_").replace("/", "_")
        out_name = f"{safe_name}.html"
        output_dir.joinpath(out_name).write_text(html, encoding="utf-8")

        member_ids = ", ".join(m["model_id"] for m in g["members"])
        entries.append((g["group_name"], member_ids, g["variant_count"], out_name))
        print(f"  ✓ {g['group_name']} ({g['variant_count']}款) → {out_name}")

    if entries:
        index_html = generate_index(entries, brand, args.batch)
        output_dir.joinpath("index.html").write_text(index_html, encoding="utf-8")
        print(f"\n  ✓ index.html (共 {len(entries)} 个车型组)")
        print(f"\n输出目录: {output_dir.resolve()}")
    else:
        print("未找到任何车型")


if __name__ == "__main__":
    main()
