#!/usr/bin/env python3
"""
MIIT Pipeline P5: 分类车型对比报告

按 watchlist 分类生成单一 HTML，包含该分类下所有品牌的车型对比。

用法:
  python3 scripts/06_generate_category_report.py --category 一线新能源
  python3 scripts/06_generate_category_report.py --category 一线新能源 --tax-json 车型清单_第88批车船税.json
  python3 scripts/06_generate_category_report.py --all

输入：workflow/brand_watchlist.yaml + data/vehicle_details/ + data/vehicle_tax/。
输出：reports/batch_{batch}/（相对 --output-dir 落在 reports 下）。

命令示例：
  python3 scripts/06_generate_category_report.py --batch 410 --all --output-dir batch_410/category_report
"""

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

import yaml

from miit_paths import (  # noqa: E402
    WATCHLIST_PATH,
    REPORTS_DIR,
    VEHICLE_TAX_DIR,
    tax_json_path,
    load_batches,
    DEFAULT_BATCH,
    ensure_dir,
)
from report_common import (  # noqa: E402
    IMAGE_VIEWS,
    load_tax_index,
    load_name_map,
    group_models,
    img_to_b64,
    _build_inline,
    _build_comparison_table,
    discover_models,
)

BATCH = "第409批"
BATCH_DIR_PREFIX = "409"          # 归档批次号
ARCHIVE_DATE = "2026-07-13"       # 报告页脚存档时间

CSS_MEDIA = """
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
html { scroll-behavior: smooth; }
body {
  font-family: -apple-system, "PingFang SC", "Noto Sans SC", "Helvetica Neue", sans-serif;
  background: var(--zh-bg);
  color: var(--zh-text);
  line-height: 1.6;
  padding: 40px 20px;
}
.container { max-width: 1280px; margin: 0 auto; }
.header { text-align: center; margin-bottom: 28px; padding-bottom: 24px; border-bottom: 2px solid var(--zh-border); }
.header h1 { font-size: 28px; font-weight: 700; color: var(--zh-blue); letter-spacing: 1px; }
.header .subtitle { font-size: 14px; color: var(--zh-muted); margin-top: 6px; }
/* Brand nav */
.brand-nav { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; margin-bottom: 32px; }
.brand-nav a {
  display: inline-block; padding: 8px 16px; border-radius: 8px;
  background: var(--zh-card); border: 1px solid var(--zh-border);
  text-decoration: none; font-size: 14px; font-weight: 500; color: var(--zh-blue);
  transition: box-shadow 0.15s;
}
.brand-nav a:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
/* Brand section */
.brand-section { margin-bottom: 40px; }
.brand-section-title {
  font-size: 22px; font-weight: 700; color: var(--zh-deep-blue);
  padding: 12px 0; margin-bottom: 20px;
  border-bottom: 3px solid var(--zh-blue); position: relative;
}
.brand-section-title .brand-count { font-size: 14px; font-weight: 400; color: var(--zh-muted); margin-left: 10px; }
/* Model group card */
.model-group { background: var(--zh-card); border-radius: 12px; border: 1px solid var(--zh-border); overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.06); margin-bottom: 20px; }
.model-group-header { padding: 14px 24px; font-size: 16px; font-weight: 600; color: var(--zh-blue); background: var(--zh-light-blue); border-bottom: 1px solid var(--zh-border); display: flex; align-items: center; gap: 12px; }
.model-group-header .variant-badge { font-size: 12px; font-weight: 400; color: var(--zh-muted); background: var(--zh-card); padding: 2px 10px; border-radius: 999px; }
.model-group-header .model-ids { font-size: 11px; font-weight: 400; color: var(--zh-muted); font-family: "SF Mono", Menlo, monospace; margin-left: auto; }
.photo-section { display: flex; gap: 16px; padding: 20px 24px; flex-wrap: wrap; }
.photo-card { flex: 1; min-width: 200px; max-width: 50%; border-radius: 8px; overflow: hidden; border: 1px solid var(--zh-border); }
.photo { aspect-ratio: 16 / 10; background: #e9eef2; }
.photo img { width: 100%; height: 100%; object-fit: contain; display: block; }
.photo-card .label { padding: 6px 12px; font-size: 12px; color: var(--zh-muted); background: var(--zh-group-bg); border-top: 1px solid var(--zh-border); }
.params-card { border-top: 1px solid var(--zh-border); }
.params-card + .params-card { border-top: 1px solid var(--zh-border); }
.group-header { padding: 10px 24px; font-size: 13px; font-weight: 600; color: var(--zh-blue); background: #f5f7fb; letter-spacing: 0.5px; }
.params-table { width: 100%; border-collapse: collapse; }
.params-table tr { border-bottom: 1px solid #f0ede8; }
.params-table tr:last-child { border-bottom: none; }
.params-table td { padding: 10px 24px; font-size: 14px; vertical-align: top; }
.params-table .key { width: 160px; font-weight: 500; color: var(--zh-muted); white-space: nowrap; }
.params-table .value { color: var(--zh-text); }
.inline-params { padding: 12px 24px; font-size: 14px; color: var(--zh-text); }
.compare-table { width: 100%; border-collapse: collapse; }
.compare-table { width: 100%; table-layout: fixed; border-collapse: collapse; }
.compare-table th { padding: 8px 12px; font-size: 12px; font-weight: 600; color: var(--zh-muted); background: var(--zh-group-bg); border-bottom: 1px solid var(--zh-border); text-align: left; word-break: break-all; }
.compare-table th:first-child { padding-left: 20px; width: 180px; }
.compare-table td { padding: 8px 12px; font-size: 13px; border-bottom: 1px solid #f0ede8; vertical-align: top; word-break: break-all; }
.compare-table td:first-child { padding-left: 20px; font-weight: 500; color: var(--zh-muted); white-space: nowrap; }
.compare-table tr.diff td { background: var(--diff-bg); }
.compare-table tr:last-child td { border-bottom: none; }
.label-tag { display: inline-block; font-size: 11px; padding: 1px 8px; border-radius: 4px; background: var(--zh-light-blue); color: var(--zh-blue); margin-left: 4px; }
.no-data { padding: 20px; text-align: center; color: var(--zh-muted); font-size: 14px; background: var(--zh-card); border-radius: 12px; border: 1px dashed var(--zh-border); }
.footer { text-align: center; margin-top: 32px; padding-top: 20px; border-top: 1px solid var(--zh-border); font-size: 12px; color: var(--zh-muted); }
"""


def load_category_brands(category: str) -> list[str]:
    with open(WATCHLIST_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return raw.get(category, [])


def load_brand_models(brand: str, tax_index: dict, batch: str = BATCH_DIR_PREFIX) -> list[dict]:
    """Load all model infos for a brand from data/vehicle_details/."""
    return discover_models(brand=brand, tax_index=tax_index, batch=batch)


def generate_brand_section_html(brand_name: str, tax_index: dict, name_map: dict | None = None, batch: str = BATCH_DIR_PREFIX) -> str:
    """Generate HTML for a single brand's section within a category page."""
    model_infos = load_brand_models(brand_name, tax_index, batch=batch)
    if not model_infos:
        return f"""
    <div class="brand-section">
      <div class="brand-section-title" id="{brand_name}">{brand_name} <span class="brand-count">无归档数据</span></div>
      <div class="no-data">第 {BATCH} 批无该品牌新车申报，或尚未归档。</div>
    </div>"""

    groups = group_models(model_infos, tax_index, name_map)
    total_models = len(model_infos)

    groups_html = ""
    for g in groups:
        members = g["members"]
        all_params = [m["params"] for m in members]

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

        # Photos: 2 from primary variant
        primary = members[0]
        img_rows = ""
        for view in IMAGE_VIEWS:
            p = primary["photo_dir"] / view
            if p.exists():
                img_rows += f"""
          <div class="photo-card">
            <div class="photo"><img src="{img_to_b64(p)}" alt="{view}"></div>
            <div class="label">{view.replace('.jpg','')}</div>
          </div>"""

        model_ids_list = ", ".join(m["model_id"] for m in members)
        groups_html += f"""
    <div class="model-group">
      <div class="model-group-header">
        {g['group_name']}
        <span class="variant-badge">{g['variant_count']} 款配置</span>
        <span class="model-ids">{model_ids_list}</span>
      </div>
      <div class="photo-section">{img_rows}</div>
      {sections}
    </div>"""

    return f"""
    <div class="brand-section">
      <div class="brand-section-title" id="{brand_name}">
        {brand_name}
        <span class="brand-count">{total_models} 款车型 · {len(groups)} 个车型组</span>
      </div>
      {groups_html}
    </div>"""


def generate_category_html(category: str, tax_path: Path, output_dir: Path, dry_run: bool = False) -> str:
    brands = load_category_brands(category)
    tax_index = load_tax_index(str(tax_path))
    name_map = load_name_map()

    nav_links = ""
    sections = ""
    total_models = 0
    total_groups = 0
    active_brands = 0

    for brand_name in brands:
        models = load_brand_models(brand_name, tax_index, batch=BATCH_DIR_PREFIX)
        if not models:
            continue
        groups = group_models(models, tax_index, name_map)
        total_models += len(models)
        total_groups += len(groups)
        active_brands += 1

        nav_links += f"""<a href="#{brand_name}">{brand_name}</a>"""
        sections += generate_brand_section_html(brand_name, tax_index, name_map, batch=BATCH_DIR_PREFIX)

    if dry_run:
        return ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{category} — {BATCH} MIIT 新车公示</title>
<style>{CSS_MEDIA}</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{category}</h1>
    <div class="subtitle">{BATCH} · 共 {active_brands} 个品牌 · {total_models} 款车型 · {total_groups} 个车型组</div>
  </div>
  <div class="brand-nav">{nav_links}</div>
  {sections}
  <div class="footer">
    <p>数据来源：工信部道路机动车辆生产企业及产品公告（{BATCH}）· 存档时间：{ARCHIVE_DATE}</p>
    <p style="margin-top:4px;">MIIT New Car Report · Generated by mashang-service</p>
  </div>
</div>
</body>
</html>"""


def _apply_batch(batch: str) -> Path:
    """根据批次号覆盖 BATCH / BATCH_DIR_PREFIX / ARCHIVE_DATE，返回默认车船税 JSON 路径。"""
    global BATCH, BATCH_DIR_PREFIX, ARCHIVE_DATE
    BATCH = f"第{batch}批"
    BATCH_DIR_PREFIX = batch
    cfg = load_batches().get(batch)
    if cfg:
        ARCHIVE_DATE = cfg.get("archive_date", ARCHIVE_DATE)
    return tax_json_path(batch)


def main():
    parser = argparse.ArgumentParser(description="MIIT Pipeline 4: 分类车型对比报告")
    parser.add_argument("--category", help="分类名称（如 一线新能源）")
    parser.add_argument("--all", action="store_true", help="生成全部分类报告")
    parser.add_argument("--batch", default="", help="公告批次号（如 410）；空则默认 409 配置")
    parser.add_argument("--tax-json", default="", help="车船税 JSON 路径（默认按批次自动匹配）")
    parser.add_argument("--output-dir", default="miit_category_reports",
                        help="HTML 输出目录（相对路径落在 reports/ 下，默认 miit_category_reports）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不生成 HTML")
    args = parser.parse_args()

    if not args.category and not args.all:
        print("请指定 --category 或 --all", file=sys.stderr)
        sys.exit(1)

    default_tax = tax_json_path("409")
    if args.batch:
        default_tax = _apply_batch(args.batch)

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPORTS_DIR / output_dir
    tax_path = Path(args.tax_json) if args.tax_json else default_tax
    if not tax_path.is_absolute() and not tax_path.exists():
        tax_path = VEHICLE_TAX_DIR / tax_path

    if args.all:
        with open(WATCHLIST_PATH, encoding="utf-8") as f:
            categories = list(yaml.safe_load(f).keys())
    else:
        categories = [args.category]

    for cat in categories:
        print(f"\n=== {cat} ===", file=sys.stderr)
        html = generate_category_html(cat, tax_path, output_dir, dry_run=args.dry_run)
        if args.dry_run:
            continue
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{cat}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"  ✓ {out_path}", file=sys.stderr)

    if not args.dry_run and len(categories) > 1:
        # Generate index
        links = "".join(
            f'<a href="{cat}.html" class="card"><div class="card-title">{cat}</div></a>'
            for cat in categories
        )
        index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{BATCH} MIIT 分类报告</title>
<style>
:root {{ --zh-blue:#174A7C; --zh-bg:#EFF2F5; --zh-card:#FFF; --zh-border:#DCE0E5; --zh-text:#1F2D3D; --zh-muted:#6B7C8F; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font:15px/1.6 -apple-system,"PingFang SC","Noto Sans SC",sans-serif; background:var(--zh-bg); color:var(--zh-text); padding:40px 20px; }}
.container {{ max-width:600px; margin:0 auto; }}
h1 {{ font-size:26px; color:var(--zh-blue); margin-bottom:8px; }}
.subtitle {{ color:var(--zh-muted); font-size:14px; margin-bottom:28px; }}
.grid {{ display:flex; flex-direction:column; gap:12px; }}
.card {{ display:block; padding:18px 22px; background:var(--zh-card); border-radius:12px; border:1px solid var(--zh-border); text-decoration:none; color:var(--zh-text); font-size:17px; font-weight:600; color:var(--zh-blue); }}
.card:hover {{ box-shadow:0 2px 10px rgba(0,0,0,0.06); }}
.footer {{ margin-top:32px; text-align:center; font-size:12px; color:var(--zh-muted); }}
</style>
</head>
<body><div class="container">
<h1>{BATCH} MIIT 新车公示</h1>
<div class="subtitle">按品牌分类聚合</div>
<div class="grid">{links}</div>
<div class="footer"><p>数据来源：工信部道路机动车辆生产企业及产品公告（{BATCH}）</p></div>
</div></body></html>"""
        output_dir.joinpath("index.html").write_text(index_html, encoding="utf-8")
        print(f"\n  ✓ index.html", file=sys.stderr)
        print(f"\n输出目录: {output_dir.resolve()}", file=sys.stderr)


if __name__ == "__main__":
    main()
