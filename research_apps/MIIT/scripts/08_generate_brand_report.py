#!/usr/bin/env python3
"""
MIIT Pipeline P5: 单品牌车型对比报告

步骤：
  1. 从 data/vehicle_details/ 读取某品牌车型 + data/vehicle_tax/ 车船税
  2. 按通用名称分组合并（识别同一车型的不同配置/变体）
  3. 每组生成一个对比报告：公共参数 + 差异分列

用法:
  python3 scripts/08_generate_brand_report.py \
    --batch 409 --brand 小米 \
    --tax-json 车型清单_第88批车船税.json \
    --output-dir batch_409/brand_report \
    --batch-label "第409批"

相对路径的 --tax-json / --output-dir 将落在 data/vehicle_tax / reports 下。
"""

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from collections import OrderedDict

from miit_paths import (  # noqa: E402
    NAME_MAP_PATH,
    REPORTS_DIR,
    VEHICLE_TAX_DIR,
    tax_json_path,
    DEFAULT_BATCH,
    ensure_dir,
)
from report_common import (  # noqa: E402
    IMAGE_VIEWS,
    read_md,
    load_tax_index,
    load_name_map,
    img_to_b64,
    discover_models,
    group_models,
    _build_inline,
    _build_comparison_table,
)

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
.compare-table th:first-child { padding-left: 20px; width: 180px; }
.compare-table td { padding: 10px 18px; font-size: 14px; border-bottom: 1px solid #f0ede8; vertical-align: top; }
.compare-table td:first-child { padding-left: 24px; font-weight: 500; color: var(--zh-muted); white-space: nowrap; }
.compare-table tr.diff td { background: var(--diff-bg); }
.compare-table tr:last-child td { border-bottom: none; }
.label-tag { display: inline-block; font-size: 11px; padding: 1px 8px; border-radius: 4px; background: var(--zh-light-blue); color: var(--zh-blue); margin-left: 4px; }
.footer { text-align: center; margin-top: 32px; padding-top: 20px; border-top: 1px solid var(--zh-border); font-size: 12px; color: var(--zh-muted); }
"""


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
    model_dir = primary["photo_dir"]
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
    parser = argparse.ArgumentParser(description="MIIT 单品牌车型对比报告生成器")
    parser.add_argument("--batch", default=DEFAULT_BATCH, help=f"公告批次号（默认 {DEFAULT_BATCH}）")
    parser.add_argument("--brand", required=True, help="品牌名称，如 小米、理想")
    parser.add_argument("--tax-json", default="", help="车船税 JSON 文件名（默认按批次自动匹配）")
    parser.add_argument("--output-dir", required=True, help="HTML 输出目录（相对路径落在 reports/ 下）")
    parser.add_argument("--batch-label", default="", help="报告展示的批次文案，如 第409批")
    args = parser.parse_args()

    batch = args.batch
    batch_label = args.batch_label or f"第{batch}批"

    tax_json = Path(args.tax_json) if args.tax_json else None
    if tax_json is None:
        tax_json = tax_json_path(batch)
    elif not tax_json.is_absolute() and not tax_json.exists():
        tax_json = VEHICLE_TAX_DIR / tax_json
    tax_index = load_tax_index(str(tax_json))
    brand = args.brand
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPORTS_DIR / output_dir
    ensure_dir(output_dir)

    # Step 1: Load all model info
    model_infos = discover_models(brand, tax_index, batch=batch)
    if not model_infos:
        print(f"⚠ {brand} 在 data/vehicle_details/ 无车型详情")
        return

    # Step 2: Group by 通用名称
    name_map = load_name_map()
    groups = group_models(model_infos, tax_index, name_map)
    entries = []

    for g in groups:
        html = generate_group_html(g, brand, batch_label)
        safe_name = g["group_name"].replace(" ", "_").replace("/", "_")
        out_name = f"{safe_name}.html"
        output_dir.joinpath(out_name).write_text(html, encoding="utf-8")

        member_ids = ", ".join(m["model_id"] for m in g["members"])
        entries.append((g["group_name"], member_ids, g["variant_count"], out_name))
        print(f"  ✓ {g['group_name']} ({g['variant_count']}款) → {out_name}")

    if entries:
        index_html = generate_index(entries, brand, batch_label)
        output_dir.joinpath("index.html").write_text(index_html, encoding="utf-8")
        print(f"\n  ✓ index.html (共 {len(entries)} 个车型组)")
        print(f"\n输出目录: {output_dir.resolve()}")
    else:
        print("未找到任何车型")


if __name__ == "__main__":
    main()
