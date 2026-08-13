#!/usr/bin/env python3
"""
MIIT Pipeline P1: Gov 品牌搜索 + 简报

用法:
  python3 scripts/01_scan_gov_batch.py              # 搜索 + 生成简报 + 保存扫描
  python3 scripts/01_scan_gov_batch.py --batch 410  # 指定批次
  python3 scripts/01_scan_gov_batch.py --from-scan  # 从已有扫描 MD 生成简报（跳过搜索）
  python3 scripts/01_scan_gov_batch.py --open       # 生成后自动打开浏览器
"""

import argparse
import json
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import yaml

from miit_paths import (  # noqa: E402
    WATCHLIST_PATH,
    SCRIPTS_DIR,
    scan_path,
    batch_reports_dir,
    BATCH_INDEX_DOC,
    DEFAULT_BATCH,
    ensure_dir,
)

BRAND_DISPLAY = {
    "小米":     { "name": "小米",     "icon": "📱" },
    "蔚来":     { "name": "蔚来",     "icon": "🔵" },
    "理想":     { "name": "理想",     "icon": "🏠" },
    "小鹏":     { "name": "小鹏",     "icon": "🛸" },
    "极氪":     { "name": "极氪",     "icon": "⚡" },
    "特斯拉":   { "name": "特斯拉",   "icon": "🔋" },
    "零跑":     { "name": "零跑",     "icon": "🏃" },
    "乐道":     { "name": "乐道",     "icon": "🔵" },
    "阿维塔":   { "name": "阿维塔",   "icon": "🔺" },
    "岚图":     { "name": "岚图",     "icon": "⛰️" },
    "腾势":     { "name": "腾势",     "icon": "🔷" },
    "领克":     { "name": "领克",     "icon": "🛡️" },
    "魏牌":     { "name": "魏牌",     "icon": "🏴" },
    "问界":     { "name": "问界",     "icon": "🚀" },
    "享界":     { "name": "享界",     "icon": "⭐" },
    "智界":     { "name": "智界",     "icon": "💡" },
    "尊界":     { "name": "尊界",     "icon": "👑" },
    "尚界":     { "name": "尚界",     "icon": "🌄" },
    "奕境":     { "name": "奕境",     "icon": "✨" },
    "华境":     { "name": "华境",     "icon": "🏯" },
    "启境":     { "name": "启境",     "icon": "🚩" },
    "坦克":     { "name": "坦克",     "icon": "🛡️" },
    "爱咖":     { "name": "爱咖",     "icon": "☕" },
    "猛士":     { "name": "猛士",     "icon": "💪" },
    "捷途":     { "name": "捷途",     "icon": "🛣️" },
    "方程豹":   { "name": "方程豹",   "icon": "🐆" },
}


def load_watchlist_categories() -> tuple[OrderedDict, dict]:
    with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    categories = OrderedDict()
    brand_to_category = {}
    for cat, brands in raw.items():
        categories[cat] = brands
        for b in brands:
            brand_to_category[b] = cat
    return categories, brand_to_category


def run_search(batch: str) -> dict:
    script = SCRIPTS_DIR / "miit_gov_search.py"
    result = subprocess.run(
        [sys.executable, str(script), "--batch", batch, "--format", "json"],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        print(f"搜索失败: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def save_scan_md(data: dict, batch: str) -> Path:
    brands = data["brands"]
    has_data = [b for b in brands if b["total_count"] > 0]
    no_data = [b for b in brands if b["total_count"] == 0]
    total_models = sum(b["total_count"] for b in brands)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    summary_rows = ""
    for b in has_data:
        ways = ", ".join(f'{s["field"]}={s["term"]}({s["count"]}条)' for s in b.get("searches", []))
        summary_rows += f"| {b['catalog']} | {ways} | {b['total_count']} |\n"

    md = f"""# 第 {batch} 批 MIIT 品牌扫描报告

| 指标 | 数值 |
|------|------|
| 扫描时间 | {now} |
| 扫描品牌 | {len(brands)} |
| 命中品牌 | {len(has_data)} |
| 新车总数 | {total_models} |

## 品牌搜索结果摘要

| 品牌 | 搜索方式 | 条数 |
|------|----------|------|
{summary_rows}
## 无新品品牌

{', '.join(b['catalog'] for b in no_data) if no_data else '无'}

## 原始数据

```json
{json.dumps(data, ensure_ascii=False, indent=2)}
```
"""
    path = scan_path(batch)
    ensure_dir(path.parent)
    path.write_text(md, encoding="utf-8")
    return path


def load_scan_md(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.search(r'```json\n(.+?)\n```', text, re.DOTALL)
    if not m:
        print(f"错误: {path} 中未找到 JSON 数据块", file=sys.stderr)
        sys.exit(1)
    return json.loads(m.group(1))


def classify_energy(cpmc: str) -> str:
    if "纯电动" in cpmc or "纯电" in cpmc:
        return "纯电"
    if "插电式增程混合" in cpmc or "增程" in cpmc:
        return "增程"
    if "插电式混合" in cpmc:
        return "插混"
    if "燃料" in cpmc:
        return "燃料电池"
    return "其他"


def build_brand_card(b: dict) -> str:
    info = BRAND_DISPLAY.get(b["catalog"], {})
    name = info.get("name", b["catalog"])
    icon = info.get("icon", "🚗")

    by_energy = {}
    for row in b["all_rows"]:
        energy = classify_energy(row["cpmc"])
        by_energy.setdefault(energy, []).append(row)

    models_html = ""
    for energy, rows in sorted(by_energy.items()):
        models_html += f"""
          <div class="energy-group">
            <div class="energy-tag {energy}">{energy} {len(rows)}</div>
            <table class="model-table">
              <thead><tr><th>企业名称</th><th>产品名称</th><th>产品型号</th></tr></thead>
              <tbody>"""
        for row in rows:
            models_html += f"""
                <tr>
                  <td>{row['qymc']}</td>
                  <td>{row['cpmc']}</td>
                  <td class="mono">{row['cpxh']}</td>
                </tr>"""
        models_html += "</tbody></table></div>"

    return f"""
      <div class="brand-card">
        <div class="brand-header">
          <span class="brand-icon">{icon}</span>
          <span class="brand-name">{name}</span>
          <span class="brand-count">{b['total_count']} 款</span>
        </div>
        {models_html}
      </div>"""


def generate_html(data: dict, categories: OrderedDict, brand_to_category: dict, batch: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    brands: list[dict] = data["brands"]

    has_data = [b for b in brands if b["total_count"] > 0]
    total_models = sum(b["total_count"] for b in brands)
    brand_map = {b["catalog"]: b for b in brands}

    cat_totals: list[tuple[str, int]] = []
    sections_html = ""
    cats_with_data = 0
    for cat_name, cat_brands in categories.items():
        has = [brand_map[b] for b in cat_brands if b in brand_map and brand_map[b]["total_count"] > 0]
        none_of = [brand_map[b] for b in cat_brands if b in brand_map and brand_map[b]["total_count"] == 0]
        if not has:
            continue
        cat_total = sum(b["total_count"] for b in has)
        cat_totals.append((cat_name, cat_total))
        cats_with_data += 1
        cards = "".join(build_brand_card(b) for b in has)
        missing = ", ".join(
            BRAND_DISPLAY.get(b["catalog"], {}).get("name", b["catalog"])
            for b in none_of
        )
        missing_html = f'<div class="no-data-cat">本分类无新品：{missing}</div>' if missing else ""
        sections_html += f"""
    <div class="category-section">
      <div class="category-header">{cat_name}</div>
      {cards}
      {missing_html}
    </div>"""

    known_brands = set()
    for brands_list in categories.values():
        known_brands.update(brands_list)
    leftover = [b for b in brands if b["catalog"] not in known_brands and b["total_count"] > 0]
    if leftover:
        cards = "".join(build_brand_card(b) for b in leftover)
        sections_html += f"""
    <div class="category-section">
      <div class="category-header">其他品牌</div>
      {cards}
    </div>"""

    all_none = [b for b in brands if b["total_count"] == 0]
    no_data_names = ", ".join(
        BRAND_DISPLAY.get(b["catalog"], {}).get("name", b["catalog"])
        for b in all_none
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>第{batch}批 MIIT 品牌搜索简报</title>
<style>
:root {{
  --bg: #f5f5f0;
  --card: #ffffff;
  --text: #1a1a18;
  --muted: #666560;
  --line: #e0dfd8;
  --accent: #174A7C;
  --accent-light: #DDEFF8;
  --cat-bg: #EDF1F5;
  --green: #4a7c4a;
  --blue: #3a6b9f;
  --orange: #c47a2e;
  --radius: 12px;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font: 15px/1.6 -apple-system, "PingFang SC", "Noto Sans SC", sans-serif;
  background: var(--bg); color: var(--text); padding: 32px 16px;
}}
.container {{ max-width: 960px; margin: 0 auto; }}
.header {{ margin-bottom: 28px; }}
.header h1 {{ font-size: 24px; font-weight: 600; color: var(--accent); margin-bottom: 6px; }}
.header .meta {{ color: var(--muted); font-size: 13px; }}
.summary {{
  display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 28px;
}}
.stat-card {{
  flex: 1; min-width: 120px; padding: 18px 20px;
  background: var(--card); border-radius: var(--radius);
  border: 1px solid var(--line);
}}
.stat-card .num {{ font-size: 28px; font-weight: 700; color: var(--accent); }}
.stat-card .label {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
.cat-breakdown {{
  display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px;
}}
.cat-chip {{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; border-radius: 999px;
  background: var(--card); border: 1px solid var(--line);
  font-size: 13px;
}}
.cat-chip-name {{ color: var(--accent); }}
.cat-chip-count {{
  font-weight: 600; color: var(--accent);
  background: var(--accent-light); padding: 0 7px; border-radius: 999px;
  font-size: 12px; line-height: 1.6;
}}
.category-section {{ margin-bottom: 28px; }}
.category-header {{
  font-size: 15px; font-weight: 600; color: var(--accent);
  padding: 10px 18px; margin-bottom: 12px;
  background: var(--cat-bg); border-radius: 8px;
  letter-spacing: 0.5px;
}}
.brand-card {{
  background: var(--card); border-radius: var(--radius);
  border: 1px solid var(--line); margin-bottom: 12px; overflow: hidden;
}}
.brand-header {{
  display: flex; align-items: center; gap: 10px;
  padding: 14px 20px; border-bottom: 1px solid var(--line);
  background: #fafaf7;
}}
.brand-icon {{ font-size: 20px; }}
.brand-name {{ font-size: 17px; font-weight: 600; flex: 1; }}
.brand-count {{ font-size: 13px; background: var(--accent-light); color: var(--accent); padding: 3px 10px; border-radius: 999px; }}
.energy-group {{ padding: 14px 20px; }}
.energy-group + .energy-group {{ border-top: 1px solid var(--line); }}
.energy-tag {{ display: inline-block; font-size: 11px; padding: 3px 9px; border-radius: 999px; margin-bottom: 10px; }}
.energy-tag.纯电 {{ background: #e5f0fa; color: var(--blue); }}
.energy-tag.增程 {{ background: #fef0e0; color: var(--orange); }}
.energy-tag.插混 {{ background: #eaf5ea; color: var(--green); }}
.model-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.model-table th {{ text-align: left; padding: 6px 8px; color: var(--muted); font-weight: 500; border-bottom: 1px solid var(--line); }}
.model-table td {{ padding: 6px 8px; border-bottom: 1px solid #f0efe8; }}
.model-table .mono {{ font-family: Menlo, monospace; font-size: 12px; }}
.no-data-cat {{
  padding: 14px 20px; background: var(--card); border-radius: var(--radius);
  border: 1px dashed var(--line); margin-bottom: 12px;
  color: var(--muted); font-size: 13px;
}}
.no-data {{
  padding: 20px; background: var(--card); border-radius: var(--radius);
  border: 1px solid var(--line); color: var(--muted); font-size: 13px;
}}
.footer {{ margin-top: 32px; text-align: center; color: var(--muted); font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>第 {batch} 批 MIIT 品牌搜索简报</h1>
    <div class="meta">来源: <a href="https://www.miit.gov.cn/datainfo/cpgg/art/2026/art_55c31979bd934c1dac88e3976bc7570a.html">工信部公告页</a> · 生成时间: {now}</div>
  </div>

    <div class="summary">
    <div class="stat-card">
      <div class="num">{total_models}</div>
      <div class="label">关注品牌新车总数</div>
    </div>
    <div class="stat-card">
      <div class="num">{len(has_data)} / {len(brands)}</div>
      <div class="label">有新品申报的品牌</div>
    </div>
    <div class="stat-card">
      <div class="num">{cats_with_data} / {len(categories)}</div>
      <div class="label">有新品分类</div>
    </div>
  </div>

  <div class="cat-breakdown">
    {"".join(f'<span class="cat-chip"><span class="cat-chip-name">{n}</span><span class="cat-chip-count">{c}</span></span>' for n, c in cat_totals)}
  </div>

  {sections_html}

  <div class="no-data">
    <strong>以下品牌本批无新品申报：</strong> {no_data_names}
  </div>

  <div class="footer">
    MIIT Brand Search · Powered by miit_gov_search.py · 按 {WATCHLIST_PATH.name} 分类输出
  </div>
</div>
</body>
</html>"""


def update_batch_index(batch: str):
    path = BATCH_INDEX_DOC
    lines = path.read_text(encoding="utf-8").splitlines()
    if any(f"| {batch} " in line for line in lines):
        return
    new_row = f"| {batch} | 2026-07-07 | [公告页](https://www.miit.gov.cn/datainfo/cpgg/art/2026/art_55c31979bd934c1dac88e3976bc7570a.html) | 见简报 |"
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().startswith("|"):
            lines.insert(i + 1, new_row)
            break
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="MIIT 品牌搜索简报生成器")
    parser.add_argument("--batch", default=DEFAULT_BATCH, help=f"公告批次 (默认 {DEFAULT_BATCH})")
    parser.add_argument("--open", action="store_true", help="生成后自动打开 HTML")
    parser.add_argument("--from-scan", type=str, nargs="?", const=None,
                        help="从已有扫描 MD 生成简报（跳过搜索），默认 scan_batch_{batch}.md")
    args = parser.parse_args()

    categories, brand_to_category = load_watchlist_categories()

    from_scan = args.from_scan
    if from_scan is None:
        default_scan = scan_path(args.batch)
        if default_scan.exists():
            from_scan = str(default_scan)

    if from_scan:
        scan_file = Path(from_scan)
        if not scan_file.exists():
            print(f"错误: 扫描文件不存在 {scan_file}", file=sys.stderr)
            sys.exit(1)
        print(f"从扫描文件读取: {scan_file}", file=sys.stderr)
        data = load_scan_md(scan_file)
    else:
        print(f"搜索第 {args.batch} 批品牌数据...", file=sys.stderr)
        data = run_search(args.batch)
        scan_file = save_scan_md(data, args.batch)
        print(f"扫描已保存: {scan_file}", file=sys.stderr)

    html = generate_html(data, categories, brand_to_category, args.batch)
    out_path = batch_reports_dir(args.batch) / "scan_report.html"
    ensure_dir(out_path.parent)
    out_path.write_text(html, encoding="utf-8")
    print(f"简报已生成: {out_path}", file=sys.stderr)

    update_batch_index(args.batch)

    if args.open:
        import webbrowser
        webbrowser.open(f"file://{out_path}")


if __name__ == "__main__":
    main()
