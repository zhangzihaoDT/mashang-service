"""
MIIT Vehicle Comparison Report — 6-Key-Signal Framework

Follows the methodology defined in:
  docs/miit_product_param_key_signals_framework.md

Usage:
    python -m mashang_workspace.promptbuilders.miit_new_car.vehicle_compare \\
        --record-a <records/a.json> --record-b <records/b.json> \\
        --format html --output <path>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


# ── 6-Key-Signal Framework ──────────────────────────────────

SIGNAL_DEFS = [
    {
        "id": "energy_type",
        "title": "能源类型",
        "question": "用户买的是补能自由，还是纯电体验？",
        "fields": ["fuel_type", "has_external_charging", "battery_type", "has_edr"],
        "judge_cols": ["产品身份", "用户心智", "典型用户问题"],
    },
    {
        "id": "seats",
        "title": "座位数 / 载客数",
        "question": "车辆进入的是个人、家庭，还是多人出行场景？",
        "fields": ["rated_passenger_count", "product_name"],
        "judge_cols": ["座位数", "场景倾向", "产品含义"],
    },
    {
        "id": "body_posture",
        "title": "车身姿态与通过性",
        "question": "车辆是公路舒适取向，还是越野 / 户外能力取向？",
        "fields": ["height_mm", "approach_departure_angle", "front_overhang_mm",
                    "rear_overhang_mm", "tire_spec", "front_track_mm", "rear_track_mm",
                    "chassis_category"],
        "judge_cols": ["信号", "产品含义"],
    },
    {
        "id": "space_envelope",
        "title": "车长 / 轴距 / 空间包络",
        "question": "车辆是否具备家庭大空间、二三排体验基础？",
        "fields": ["length_mm", "width_mm", "height_mm", "wheelbase_mm",
                    "front_overhang_mm", "rear_overhang_mm"],
        "judge_cols": ["参数组合", "产品含义"],
    },
    {
        "id": "towing_tool",
        "title": "拖挂 / 载重 / 工具属性",
        "question": "车辆是否具备生活方式、户外、工具化能力？",
        "fields": ["trailer_mass_kg", "gross_mass_kg", "curb_weight_kg",
                    "has_towing_device"],
        "judge_cols": ["信号", "产品含义"],
    },
    {
        "id": "intelligence",
        "title": "智能化 / 感知硬件信号",
        "question": "车辆是否进入智能电动车叙事？",
        "fields": ["has_edr", "has_external_charging", "has_optional_equipment",
                    "power_kw", "battery_type", "battery_cell_supplier"],
        "judge_cols": ["信号", "产品含义"],
    },
]


def _val(fields: dict, key: str) -> any:
    f = fields.get(key)
    return f.get("value") if f else None


def _fmt(v: any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "✅" if v else "❌"
    return str(v)


def _car_type_signals(fields: dict) -> dict:
    """Classify the vehicle into a type based on 6-signal framework."""
    fuel = _val(fields, "fuel_type")
    seats = _val(fields, "rated_passenger_count")
    height = _val(fields, "height_mm")
    angle = _val(fields, "approach_departure_angle")
    length = _val(fields, "length_mm")
    wheelbase = _val(fields, "wheelbase_mm")
    trailer = _val(fields, "trailer_mass_kg")
    has_tow = _val(fields, "has_towing_device")
    cat = _val(fields, "chassis_category")
    power = _val(fields, "power_kw")

    signals = {
        "is_phev": fuel and ("混合" in str(fuel) or "汽油" in str(fuel)),
        "is_ev": fuel and ("纯电动" in str(fuel)),
        "is_high_body": height and height >= 1850,
        "has_large_angle": bool(angle),
        "is_6_plus_seats": seats and seats >= 6,
        "is_5_seats": seats and seats == 5,
        "has_towing": trailer is not None or has_tow,
        "is_long": length and length >= 4900,
        "is_long_wheelbase": wheelbase and wheelbase >= 2950,
        "is_monocoque": cat and "承载" in str(cat),
        "high_power": power and power >= 200,
    }

    # Determine vehicle type
    if signals["is_ev"]:
        if signals["is_6_plus_seats"] and signals["is_long"]:
            return "家庭智能车 / 大六座纯电 SUV", signals
        elif signals["high_power"]:
            return "性能取向纯电 SUV", signals
        return "纯电 SUV", signals
    elif signals["is_phev"]:
        if signals["has_towing"] and signals["is_high_body"]:
            return "能力车 / 越野生活方式车", signals
        elif signals["is_6_plus_seats"] and signals["is_long"]:
            return "家庭智能车 / 插混大六座", signals
        return "插电混动 SUV", signals
    else:
        return "燃油 SUV", signals


# ── Report Helpers ──────────────────────────────────────────

def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _status_class(st: str) -> str:
    return {"success": "success", "partial": "partial", "failed": "failed"}.get(st, "")


def _build_head(name_a, name_b, type_a, type_b, st_a, st_b, tr_a, tr_b):
    sc_a, sc_b = _status_class(st_a), _status_class(st_b)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MIIT 双车对比报告</title>
<style>
:root {{ --blue: #174A7C; --deep: #06213D; --cyan: #7ECDEB; --lblue: #DDEFF8; --cream: #FFF9EF; --gold: #D79A36; --text: #1F2D3D; --muted: #6B7C8F; --card: #FFFFFF; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif; background:var(--cream); color:var(--text); line-height:1.6; padding:2rem; }}
.wrapper {{ max-width:1100px; margin:0 auto; }}
.header {{ text-align:center; padding:2rem 0 1.5rem; border-bottom:3px solid var(--cyan); margin-bottom:2rem; }}
.header h1 {{ font-size:1.6rem; color:var(--deep); letter-spacing:0.05em; }}
.header .subtitle {{ font-size:0.85rem; color:var(--muted); margin-top:0.4rem; }}
.card {{ background:var(--card); border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,0.06); padding:1.2rem 1.5rem; margin-bottom:1.2rem; }}
.card h2 {{ font-size:1rem; color:var(--blue); border-left:4px solid var(--cyan); padding-left:0.6rem; margin-bottom:0.8rem; }}
.card h3 {{ font-size:0.9rem; color:var(--deep); margin:0.8rem 0 0.4rem; }}
table {{ width:100%; border-collapse:collapse; font-size:0.85rem; }}
th, td {{ padding:0.45rem 0.6rem; text-align:left; border-bottom:1px solid #eee; }}
th {{ background:var(--lblue); color:var(--deep); font-weight:600; white-space:nowrap; }}
tr:last-child td {{ border-bottom:none; }}
td:first-child {{ font-weight:500; white-space:nowrap; }}
td.mono {{ font-family:"SF Mono","JetBrains Mono",monospace; font-size:0.8rem; }}
.badge {{ display:inline-block; padding:0.15rem 0.5rem; border-radius:4px; font-size:0.75rem; font-weight:600; }}
.badge-success {{ background:#e8f5e9; color:#2e7d32; }}
.badge-partial {{ background:#fff3e0; color:#e65100; }}
.badge-failed {{ background:#ffebee; color:#c62828; }}
.signal-q {{ font-size:0.8rem; color:var(--muted); font-style:italic; margin-bottom:0.6rem; }}
.judge {{ color:var(--gold); font-weight:500; }}
.footer {{ text-align:center; padding:1.5rem 0; font-size:0.8rem; color:var(--muted); border-top:1px solid #e0e0e0; margin-top:2rem; }}
hr {{ border:none; border-top:1px solid #eee; margin:1rem 0; }}
</style>
</head>
<body>
<div class=wrapper>
<div class=header><h1>MIIT 双车对比报告</h1><div class=subtitle>6 个关键信号框架 · 产品经理解读</div></div>
<div class=card>
<h2>产品身份总览</h2>
<table>
<tr><th></th><th>{name_a}</th><th>{name_b}</th></tr>
<tr><td>产品类型判定</td><td><strong>{type_a}</strong></td><td><strong>{type_b}</strong></td></tr>
<tr><td>parse_status</td><td><span class="badge badge-{sc_a}">{st_a}</span></td><td><span class="badge badge-{sc_b}">{st_b}</span></td></tr>
<tr><td>来源图片</td><td class=mono>{tr_a}</td><td class=mono>{tr_b}</td></tr>
</table>
</div>
"""


def _build_signal_card(signal: dict, fa: dict, fb: dict, diff_count: dict, total_count: dict) -> str:
    sid = signal["id"]
    fields = signal["fields"]
    title = signal["title"]
    question = signal["question"]

    html = f'<div class=card><h2>{title}</h2><div class=signal-q>❓ {question}</div><table><thead><tr>'
    html += "<th>参数</th><th>车辆A</th><th>车辆B</th></tr></thead><tbody>"

    for key in fields:
        va, vb = _val(fa, key), _val(fb, key)
        da, db = _fmt(va), _fmt(vb)
        total_count[sid] = total_count.get(sid, 0) + 1
        if str(va) != str(vb):
            diff_count[sid] = diff_count.get(sid, 0) + 1
        html += f"<tr><td>{key}</td><td class=mono>{_html_escape(da)}</td><td class=mono>{_html_escape(db)}</td></tr>"

    html += "</tbody></table></div>"
    return html


def build_html_report(record_a: dict, record_b: dict) -> str:
    fa, fb = record_a.get("fields", {}), record_b.get("fields", {})

    name_a = _val(fa, "product_name") or _val(fa, "product_model") or "车辆A"
    name_b = _val(fb, "product_name") or _val(fb, "product_model") or "车辆B"
    type_a, sig_a = _car_type_signals(fa)
    type_b, sig_b = _car_type_signals(fb)

    st_a, st_b = record_a.get("parse_status", ""), record_b.get("parse_status", "")
    tr_a = _html_escape(record_a.get("source_trace", {}).get("source_image_path", ""))
    tr_b = _html_escape(record_b.get("source_trace", {}).get("source_image_path", ""))

    html = _build_head(name_a, name_b, type_a, type_b, st_a, st_b, tr_a, tr_b)

    # ── 6 Key Signals ──
    diff_count = {}
    total_count = {}
    for sig in SIGNAL_DEFS:
        html += _build_signal_card(sig, fa, fb, diff_count, total_count)

    # ── 主矛盾 ──
    html += '<div class=card><h2>主矛盾</h2>'
    html += f'<p>这不是"谁参数更大"的对比，而是 <strong>{type_a}</strong> 与 <strong>{type_b}</strong> 的对比。</p>'
    html += '<table><thead><tr><th></th><th>车辆A</th><th>车辆B</th></tr></thead><tbody>'

    # Energy type judgment
    fuel_a, fuel_b = _fmt(_val(fa, "fuel_type")), _fmt(_val(fb, "fuel_type"))
    html += f"<tr><td>卖的是什么确定性</td><td class=judge>{'长途无焦虑 + 补能自由' if sig_a.get('is_phev') else '纯电智能体验'}</td>"
    html += f"<td class=judge>{'长途无焦虑 + 补能自由' if sig_b.get('is_phev') else '纯电智能体验'}</td></tr>"

    html += f"<tr><td>核心用户场景</td><td class=judge>{'户外 / 越野 / 远行' if sig_a.get('has_towing') else '城市 / 家庭'}</td>"
    html += f"<td class=judge>{'户外 / 越野 / 远行' if sig_b.get('has_towing') else '城市 / 家庭'}</td></tr>"

    html += f"<tr><td>空间定位</td><td class=judge>{'家庭多人' if sig_a.get('is_6_plus_seats') else '个人/小家庭'}</td>"
    html += f"<td class=judge>{'家庭多人' if sig_b.get('is_6_plus_seats') else '个人/小家庭'}</td></tr>"

    html += "</tbody></table></div>"

    # ── 产品经理关注点 ──
    html += '<div class=card><h2>产品经理应关注的关键信息</h2><ol>'
    items = []

    # Compare energy
    if sig_a.get("is_ev") and sig_b.get("is_phev"):
        items.append(f"能源类型差异显著：A 是纯电，B 是插混——两者的用户心智入口完全不同，A 应主打纯电智能体验，B 应主打长途无焦虑")
    elif sig_a.get("is_phev") and sig_b.get("is_ev"):
        items.append(f"能源类型差异显著：A 是插混，B 是纯电——两者的用户心智入口完全不同")

    # Compare seats
    sa, sb = _val(fa, "rated_passenger_count"), _val(fb, "rated_passenger_count")
    if sa and sb and sa != sb:
        items.append(f"座位数不同（{sa} vs {sb}座）——两车进入的用户场景不同，{sa}座更偏{'家庭多人' if sa >= 6 else '个人/小家庭'}，"
                      f"{sb}座更偏{'家庭多人' if sb >= 6 else '个人/小家庭'}")
    elif sa and sb:
        items.append(f"座位数相同（{sa}座），在用户场景上处于同一战场")

    # Compare body posture
    ha, hb = _val(fa, "height_mm"), _val(fb, "height_mm")
    if ha and hb and abs(ha - hb) > 50:
        taller = "A" if ha > hb else "B"
        items.append(f"车身高度差异明显（{ha} vs {hb}mm）——车辆{taller}更偏{'高姿态 / 越野' if max(ha, hb) > 1850 else '城市舒适'}取向")

    # Compare towing
    if sig_a.get("has_towing") and not sig_b.get("has_towing"):
        items.append(f"A 有明确拖挂能力而 B 没有——A 进入生活方式 / 户外战场，B 更偏城市家庭使用")
    elif sig_b.get("has_towing") and not sig_a.get("has_towing"):
        items.append(f"B 有明确拖挂能力而 A 没有——B 进入生活方式 / 户外战场，A 更偏城市家庭使用")

    # Compare length/wheelbase
    la, lb = _val(fa, "length_mm"), _val(fb, "length_mm")
    if la and lb:
        items.append(f"车长差异（{la} vs {lb}mm），两车在{'同一尺寸级别' if abs(la - lb) < 150 else '不同尺寸级别'}")

    for item in items:
        html += f"<li>{item}</li>"
    if not items:
        html += "<li>两车关键信号接近，需进一步结合详细配置判断</li>"
    html += "</ol></div>"

    # ── Summary ──
    total = sum(total_count.values())
    diff = sum(diff_count.values())
    html += f'<div class=card><h2>对比概要</h2>'
    html += f'<p class=signal-q>对比参数: {total} 项 | 存在差异: {diff} 项</p>'

    qa, qb = record_a.get("quality", {}), record_b.get("quality", {})
    html += "<table><thead><tr><th>指标</th><th>车辆A</th><th>车辆B</th></tr></thead><tbody>"
    html += f"<tr><td>解析字段数</td><td>{qa.get('parsed_field_count','')}</td><td>{qb.get('parsed_field_count','')}</td></tr>"
    ma = ', '.join(qa.get('required_field_missing', [])) or '无'
    mb = ', '.join(qb.get('required_field_missing', [])) or '无'
    html += f"<tr><td>缺失关键字段</td><td>{ma}</td><td>{mb}</td></tr>"
    html += f"<tr><td>需人工审查</td><td>{qa.get('needs_manual_review','')}</td><td>{qb.get('needs_manual_review','')}</td></tr>"
    html += "</tbody></table></div>"

    html += '<div class=footer>mashang-service · MIIT 6-Key-Signal Framework · 报告由 AI 自动生成</div>'
    html += "</div></body></html>"
    return html


def load_record(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    p = argparse.ArgumentParser(description="MIIT Vehicle Comparison Report (6-Key-Signal)")
    p.add_argument("--record-a", required=True)
    p.add_argument("--record-b", required=True)
    p.add_argument("--output", help="Output HTML file path (default: stdout)")
    args = p.parse_args()

    ra, rb = load_record(args.record_a), load_record(args.record_b)
    report = build_html_report(ra, rb)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"[OK] {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
