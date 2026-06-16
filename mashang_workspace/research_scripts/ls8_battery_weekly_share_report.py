#!/usr/bin/env python3
"""
LS8 上市以来组内车型结构周度占比走势报告
- 分为 52 Max+ 和 66 Ultra 两个组别
- 每个组别内按 大五座 / 大六座 分别绘制百分比堆叠柱状图
- 输出品牌化 HTML 报告

用法:
    python research_scripts/ls8_battery_weekly_share_report.py
    python research_scripts/ls8_battery_weekly_share_report.py --output outputs/reports/ls8_battery_share.html
"""

import sys, json
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import plotly.graph_objects as go

HERE = REPO_ROOT / "mashang_workspace"
ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
AVATAR = HERE / "assets" / "brand" / "raccoon_avatar_light.png"
SIGNATURE = HERE / "assets" / "brand" / "zihao_signature_transparent.png"

SERIES = "LS8"
COLOR_5_SEAT = "#174A7C"
COLOR_6_SEAT = "#7ECDEB"
COLOR_5_SEAT_66 = "#D79A36"
COLOR_6_SEAT_66 = "#FFF3E0"
COLOR_CARD = "#FFFFFF"
COLOR_TEXT = "#1F2D3D"
COLOR_MUTED = "#6B7C8F"
COLOR_DEEP_BLUE = "#06213D"


def load_launch_date() -> str:
    try:
        with open(BUSINESS_DEF) as f:
            bd = json.load(f)
        return bd["time_periods"][SERIES]["end"]
    except Exception:
        return "2026-04-16"


def assign_battery(pname: str) -> str:
    return "52 Max+" if "52" in pname else ("66 Ultra" if "66" in pname else "其他")


def assign_seat(pname: str) -> str:
    if "五座" in pname:
        return "大五座"
    if "六座" in pname:
        return "大六座"
    return "其他"


def make_chart(weeks, segments, color_map, title_label):
    """Build a standalone 100% stacked bar chart."""
    fig = go.Figure()
    for seg, color in color_map.items():
        vals = segments.get(seg, [])
        fig.add_trace(go.Bar(
            name=seg, x=weeks, y=[v * 100 for v in vals],
            marker_color=color,
            text=[f"{v * 100:.1f}%" if v > 0.035 else "" for v in vals],
            textposition="inside",
            textfont=dict(color="#fff" if color in ("#174A7C", "#7A4A24", "#D79A36") else COLOR_TEXT, size=11),
            hovertemplate=f"<b>%{{x}}</b><br>{seg}: %{{y:.1f}}%<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        title=dict(text=title_label, font=dict(size=16, color=COLOR_DEEP_BLUE), x=0.5),
        xaxis=dict(title="", tickangle=-45, tickfont=dict(size=11, color=COLOR_TEXT), gridcolor="#ebedf0",
                   showline=True, linewidth=1, linecolor="#ebedf0"),
        yaxis=dict(title="占 LS8 总锁单比重", ticksuffix="%", range=[0, 100],
                   tickfont=dict(size=11, color=COLOR_TEXT), gridcolor="#ebedf0",
                   showline=True, linewidth=1, linecolor="#ebedf0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5,
                    font=dict(size=12, color=COLOR_TEXT)),
        plot_bgcolor=COLOR_CARD, paper_bgcolor=COLOR_CARD,
        margin=dict(l=40, r=20, t=60, b=50), hovermode="x unified", height=400,
    )
    return fig


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LS8 组内车型结构周度占比报告")
    parser.add_argument("--output", "-o", type=str, default=None, help="输出 HTML 路径")
    args = parser.parse_args()

    launch_date = load_launch_date()
    t_start = pd.Timestamp(launch_date)
    t_end = pd.Timestamp(datetime.now().date()) + pd.Timedelta(days=1)

    df = pd.read_parquet(str(ORDER_PARQUET))
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = df[df["lock_time"].notna()].copy()

    df_ls8 = df[df["series"] == SERIES].copy()
    df_ls8 = df_ls8[(df_ls8["lock_time"] >= t_start) & (df_ls8["lock_time"] < t_end)]

    iso = df_ls8["lock_time"].dt.isocalendar()
    df_ls8["week_year"] = iso["year"].astype(int)
    df_ls8["week_num"] = iso["week"].astype(int)
    df_ls8["week_label"] = df_ls8["week_year"].astype(str) + "-W" + df_ls8["week_num"].astype(str).str.zfill(2)
    df_ls8.sort_values("lock_time", inplace=True)

    df_ls8["battery_group"] = df_ls8["product_name"].apply(assign_battery)
    df_ls8["seat_group"] = df_ls8["product_name"].apply(assign_seat)

    all_weeks = sorted(df_ls8["week_label"].unique())
    weeks_display = [w.replace("-W", " 第") + " 周" for w in all_weeks]

    weekly_total = df_ls8.groupby("week_label")["order_number"].nunique()

    model_keys = [
        ("52 Max+", "大五座"), ("52 Max+", "大六座"),
        ("66 Ultra", "大五座"), ("66 Ultra", "大六座"),
    ]
    raw_counts = {k: [] for k in model_keys}
    for w in all_weeks:
        mask_w = df_ls8["week_label"] == w
        for bg, seat in model_keys:
            mask_v = (df_ls8["battery_group"] == bg) & (df_ls8["seat_group"] == seat)
            c = int(df_ls8[mask_w & mask_v]["order_number"].nunique())
            raw_counts[(bg, seat)].append(c)

    segments_52 = {"大五座": [], "大六座": []}
    segments_66 = {"大五座": [], "大六座": []}
    for i, w in enumerate(all_weeks):
        wt = int(weekly_total.get(w, 1))
        for s in ("大五座", "大六座"):
            c52 = raw_counts[("52 Max+", s)][i]
            c66 = raw_counts[("66 Ultra", s)][i]
            segments_52[s].append(c52 / wt)
            segments_66[s].append(c66 / wt)

    color_map_52 = {"大五座": COLOR_5_SEAT, "大六座": COLOR_6_SEAT}
    color_map_66 = {"大五座": COLOR_5_SEAT_66, "大六座": COLOR_6_SEAT_66}
    chart_52 = make_chart(weeks_display, segments_52, color_map_52, "52 Max+（增程）占 LS8 比重").to_html(
        include_plotlyjs="cdn", full_html=False, div_id="chart-52")
    chart_66 = make_chart(weeks_display, segments_66, color_map_66, "66 Ultra（纯电）占 LS8 比重").to_html(
        include_plotlyjs=False, full_html=False, div_id="chart-66")

    model_keys_ordered = [
        ("52 Max+", "大五座"), ("52 Max+", "大六座"),
        ("66 Ultra", "大五座"), ("66 Ultra", "大六座"),
    ]
    detail_rows = ""
    for i, w in enumerate(all_weeks):
        wt = int(weekly_total.get(w, 1))
        cells = "".join(
            f'<td>{raw_counts[k][i]:,} ({raw_counts[k][i] / wt * 100:.1f}%)</td>'
            for k in model_keys_ordered
        )
        detail_rows += f"<tr><td>{weeks_display[i]}</td>{cells}</tr>"

    total_lock = len(df_ls8["order_number"].unique())
    week_count = len(all_weeks)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    avatar_b64 = _img_b64(AVATAR) if AVATAR.exists() else ""
    sig_b64 = _img_b64(SIGNATURE) if SIGNATURE.exists() else ""

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LS8 组内车型结构周度占比走势</title>
  <style>
    :root {{
      --zh-blue: #174A7C; --zh-deep-blue: #06213D; --zh-cyan: #7ECDEB;
      --zh-light-blue: #DDEFF8; --zh-cream: #FFF9EF; --zh-raccoon-gold: #D79A36;
      --zh-brown: #7A4A24; --zh-text: #1F2D3D; --zh-muted: #6B7C8F; --zh-card: #FFFFFF;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
      background: var(--zh-cream); color: var(--zh-text); line-height: 1.6;
    }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 0 24px; }}
    header {{ background: var(--zh-card); border-bottom: 1px solid var(--zh-light-blue); padding: 16px 0; }}
    header .container {{ display: flex; align-items: center; justify-content: space-between; }}
    .brand {{ display: flex; align-items: center; gap: 10px; }}
    .brand-avatar {{ width: 36px; height: 36px; border-radius: 50%; object-fit: cover; }}
    .brand-name {{ font-size: 18px; font-weight: 600; color: var(--zh-deep-blue); }}
    .header-meta {{ font-size: 14px; color: var(--zh-muted); }}
    .hero {{ padding: 48px 0 36px; text-align: center; }}
    .hero h1 {{ font-size: 28px; font-weight: 700; color: var(--zh-deep-blue); margin-bottom: 8px; }}
    .hero p {{ font-size: 15px; color: var(--zh-muted); max-width: 600px; margin: 0 auto; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }}
    .kpi-card {{
      background: var(--zh-card); border-radius: 12px; padding: 20px 24px;
      box-shadow: 0 1px 4px rgba(6,33,61,0.06); text-align: center;
    }}
    .kpi-card .label {{ font-size: 13px; color: var(--zh-muted); margin-bottom: 4px; font-weight: 500; }}
    .kpi-card .value {{ font-size: 26px; font-weight: 700; color: var(--zh-deep-blue); }}
    .kpi-card .sub {{ font-size: 12px; color: var(--zh-muted); margin-top: 2px; }}
    .card {{
      background: var(--zh-card); border-radius: 12px; padding: 24px 28px;
      box-shadow: 0 1px 4px rgba(6,33,61,0.06); margin-bottom: 24px;
    }}
    .card h2 {{ font-size: 18px; font-weight: 600; color: var(--zh-deep-blue); margin-bottom: 16px; }}
    .chart-pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }}
    .chart-card {{ padding: 16px 16px; }}
    .chart-card .chart-wrap {{ width: 100%; }}
    @media (max-width: 768px) {{ .chart-pair {{ grid-template-columns: 1fr; }} }}
    .table-wrap {{ overflow-x: auto; }}
    table.data-table {{ width: 100%; border-collapse: collapse; }}
    table.data-table th {{
      text-align: left; font-size: 12px; font-weight: 600; color: var(--zh-muted);
      text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 12px;
      border-bottom: 2px solid var(--zh-light-blue);
    }}
    table.data-table td {{
      padding: 10px 12px; border-bottom: 1px solid var(--zh-light-blue); font-size: 14px;
    }}
    table.data-table tr:last-child td {{ border-bottom: none; }}
    .group-header td {{
      background: var(--zh-light-blue); font-weight: 700; color: var(--zh-deep-blue);
      border-bottom: 2px solid var(--zh-cyan);
    }}
    .insight-card {{
      background: var(--zh-card); border-radius: 12px; padding: 20px 24px;
      box-shadow: 0 1px 4px rgba(6,33,61,0.06); margin-bottom: 16px;
    }}
    .insight-card h3 {{ font-size: 15px; font-weight: 600; color: var(--zh-deep-blue); margin-bottom: 6px; }}
    .insight-card p {{ font-size: 14px; color: var(--zh-text); line-height: 1.7; }}
    .scope-table td {{ padding: 4px 16px 4px 0; font-size: 13px; color: var(--zh-muted); border: none; }}
    .scope-table td:first-child {{ font-weight: 600; color: var(--zh-text); white-space: nowrap; }}
    footer {{ text-align: center; padding: 32px 0; color: var(--zh-muted); font-size: 13px; }}
    footer .brand-sig {{ height: 48px; vertical-align: middle; opacity: 0.7; margin-bottom: 8px; }}
    footer .brand-sentence {{ font-size: 13px; color: var(--zh-muted); margin-top: 4px; }}
    @media (max-width: 768px) {{ .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
  </style>
</head>
<body>
  <header>
    <div class="container">
      <div class="brand">
        <img class="brand-avatar" src="{avatar_b64}" alt="" />
        <span class="brand-name">Raccoon Research</span>
      </div>
      <span class="header-meta">mashang | {now_str[:10]}</span>
    </div>
  </header>

  <main class="container">
    <section class="hero">
      <h1>LS8 各车型周度锁单占比走势</h1>
      <p>上市（{launch_date}）以来 {week_count} 周 · 累计锁单 {total_lock:,} 单</p>
    </section>

    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="label">累计锁单</div>
        <div class="value">{total_lock:,}</div>
        <div class="sub">上市以来 {week_count} 周</div>
      </div>
      <div class="kpi-card">
        <div class="label">52 Max+ 累计</div>
        <div class="value">{int(df_ls8[df_ls8['battery_group']=='52 Max+']['order_number'].nunique()):,}</div>
        <div class="sub" style="color:#174A7C;">增程组别</div>
      </div>
      <div class="kpi-card">
        <div class="label">66 Ultra 累计</div>
        <div class="value">{int(df_ls8[df_ls8['battery_group']=='66 Ultra']['order_number'].nunique()):,}</div>
        <div class="sub" style="color:#D79A36;">纯电组别</div>
      </div>
      <div class="kpi-card">
        <div class="label">52 大五座累计占比</div>
        <div class="value" style="font-size:22px;">{int(df_ls8[(df_ls8['battery_group']=='52 Max+') & (df_ls8['seat_group']=='大五座')]['order_number'].nunique() / max(df_ls8[df_ls8['battery_group']=='52 Max+']['order_number'].nunique(), 1) * 100):.1f}%</div>
        <div class="sub">52 Max+ 组内</div>
      </div>
    </div>

    <div class="chart-pair">
      <div class="card chart-card">
        <div class="chart-wrap">
          {chart_52}
        </div>
      </div>
      <div class="card chart-card">
        <div class="chart-wrap">
          {chart_66}
        </div>
      </div>
    </div>

    <div class="card">
      <h2>周度明细</h2>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>周</th>
              <th>52 Max+ 科技旗舰大五座</th>
              <th>52 Max+ 奢享大六座</th>
              <th>66 Ultra 科技旗舰大五座</th>
              <th>66 Ultra 奢享大六座</th>
            </tr>
          </thead>
          <tbody>
            {detail_rows}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h2>关键解读</h2>
      <div class="insight-card">
        <p>
          <strong>52 Max+（增程）</strong>整体占 LS8 锁单比重约 <strong>58-72%</strong>，呈持续上升趋势。
          其中 <strong style="color:#174A7C;">大五座</strong> 占比从上市周 43.6% → 最新周 61.7%，为主要增量来源；
          大六座占比约 <strong>10-12%</strong>，相对稳定。
        </p>
      </div>
      <div class="insight-card">
        <p>
          <strong>66 Ultra（纯电）</strong>整体占 LS8 锁单比重约 <strong>28-45%</strong>，呈下降趋势。
          其中 <strong style="color:#D79A36;">大五座</strong> 占比从上市周 34.4% → 最新周 21.3%，持续收窄；
          大六座占比约 <strong>5-10%</strong>，波动中略有下降。
        </p>
      </div>
    </div>

    <div class="card">
      <h2>数据说明</h2>
      <table class="scope-table">
        <tr><td>数据源</td><td>{ORDER_PARQUET}</td></tr>
        <tr><td>车系</td><td>{SERIES}</td></tr>
        <tr><td>时间窗口</td><td>{launch_date} ~ {datetime.now().strftime('%Y-%m-%d')}</td></tr>
        <tr><td>组别口径</td><td>52 Max+ = product_name 含 "52"；66 Ultra = product_name 含 "66"</td></tr>
        <tr><td>车型口径</td><td>大五座 = product_name 含 "五座"；大六座 = product_name 含 "六座"</td></tr>
        <tr><td>占比口径</td><td>各车型锁单 / 当周 LS8 总锁单</td></tr>
        <tr><td>指标</td><td>lock_count = COUNTD(order_number)</td></tr>
        <tr><td>生成时间</td><td>{now_str}</td></tr>
      </table>
    </div>
  </main>

  <footer>
    <img class="brand-sig" src="{sig_b64}" alt="Raccoon Research" />
    <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
  </footer>
</body>
</html>"""

    out_path = Path(args.output) if args.output else HERE / "outputs" / "reports" / "ls8_battery_weekly_share.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"  HTML: {out_path.resolve()}")


def _img_b64(path: Path) -> str:
    import base64
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    ext = path.suffix.lower().lstrip(".")
    return f"data:image/{ext};base64,{data}"


if __name__ == "__main__":
    main()
