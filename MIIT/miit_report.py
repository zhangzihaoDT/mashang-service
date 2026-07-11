#!/usr/bin/env python3
"""
MIIT 公告品牌搜索简报生成器

用法:
  python3 miit_report.py                           # 搜索 + 生成简报
  python3 miit_report.py --batch 410               # 指定批次
  python3 miit_report.py --open                    # 生成后自动打开浏览器
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent

BRAND_DISPLAY = {
    "鸿蒙智行": { "name": "鸿蒙智行", "icon": "⚡" },
    "智己":     { "name": "智己",     "icon": "🧠" },
    "理想":     { "name": "理想",     "icon": "🏠" },
    "小米":     { "name": "小米",     "icon": "📱" },
    "蔚来汽车": { "name": "蔚来",     "icon": "🔵" },
    "小鹏":     { "name": "小鹏",     "icon": "🛸" },
    "阿维塔":   { "name": "阿维塔",   "icon": "🔺" },
    "深蓝":     { "name": "深蓝",     "icon": "🌊" },
    "零跑":     { "name": "零跑",     "icon": "🏃" },
    "腾势":     { "name": "腾势",     "icon": "🔷" },
    "方程豹":   { "name": "方程豹",   "icon": "🐆" },
    "比亚迪":   { "name": "比亚迪",   "icon": "🛡️" },
    "特斯拉":   { "name": "特斯拉",   "icon": "🔋" },
    "极氪科技": { "name": "极氪",     "icon": "⚡" },
    "埃安":     { "name": "埃安",     "icon": "🌱" },
    "岚图":     { "name": "岚图",     "icon": "⛰️" },
}


def run_search(batch: str) -> dict:
    """调用 miit_search.py 搜索所有品牌"""
    script = HERE / "miit_search.py"
    result = subprocess.run(
        [sys.executable, str(script), "--batch", batch, "--format", "json"],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        print(f"搜索失败: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


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


def generate_html(data: dict, batch: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    brands = data["brands"]

    # 统计
    has_data = [b for b in brands if b["total_count"] > 0]
    no_data = [b for b in brands if b["total_count"] == 0]
    total_models = sum(b["total_count"] for b in brands)

    cards_html = ""
    for b in has_data:
        info = BRAND_DISPLAY.get(b["catalog"], {})
        name = info.get("name", b["catalog"])
        icon = info.get("icon", "🚗")

        # 按能源类型分类
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

        cards_html += f"""
      <div class="brand-card">
        <div class="brand-header">
          <span class="brand-icon">{icon}</span>
          <span class="brand-name">{name}</span>
          <span class="brand-count">{b['total_count']} 款</span>
        </div>
        {models_html}
      </div>"""

    no_data_names = ", ".join(
        BRAND_DISPLAY.get(b["catalog"], {}).get("name", b["catalog"])
        for b in no_data
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
.brand-card {{
  background: var(--card); border-radius: var(--radius);
  border: 1px solid var(--line); margin-bottom: 16px; overflow: hidden;
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
.no-data {{
  padding: 20px; background: var(--card); border-radius: var(--radius);
  border: 1px solid var(--line); margin-bottom: 16px;
  color: var(--muted); font-size: 13px;
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
  </div>

  {cards_html}

  <div class="no-data">
    <strong>以下品牌本批无新品申报：</strong> {no_data_names}
  </div>

  <div class="footer">
    MIIT Brand Search · Powered by miit_search.py
  </div>
</div>
</body>
</html>"""


def update_batch_index(batch: str):
    """自动更新 公告批次.md"""
    path = HERE / "公告批次.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    # 检查是否已有该批次
    if any(f"| {batch} " in line for line in lines):
        return  # 已存在，跳过
    # 找最后一条数据行，在其后插入
    new_row = f"| {batch} | 2026-07-07 | [公告页](https://www.miit.gov.cn/datainfo/cpgg/art/2026/art_55c31979bd934c1dac88e3976bc7570a.html) | 见简报 |"
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().startswith("|"):
            lines.insert(i + 1, new_row)
            break
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="MIIT 品牌搜索简报生成器")
    parser.add_argument("--batch", default="409", help="公告批次 (默认 409)")
    parser.add_argument("--open", action="store_true", help="生成后自动打开 HTML")
    args = parser.parse_args()

    print(f"搜索第 {args.batch} 批品牌数据...", file=sys.stderr)
    data = run_search(args.batch)

    html = generate_html(data, args.batch)
    out_path = HERE / f"report_batch_{args.batch}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"简报已生成: {out_path}", file=sys.stderr)

    # 更新公告批次索引
    update_batch_index(args.batch)
    print(f"公告批次.md 已更新", file=sys.stderr)

    if args.open:
        import webbrowser
        webbrowser.open(f"file://{out_path}")


if __name__ == "__main__":
    main()
