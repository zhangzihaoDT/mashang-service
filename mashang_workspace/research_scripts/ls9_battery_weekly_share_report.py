#!/usr/bin/env python3
"""
LS9 上市以来 52 Ultra / 66 Ultra 周度占比走势报告
- 52 Ultra（标准电池）vs 66 Ultra（大电池）双线对比
- 输出品牌化 HTML 报告

用法:
    python research_scripts/ls9_battery_weekly_share_report.py
    python research_scripts/ls9_battery_weekly_share_report.py --output outputs/reports/ls9_battery_share.html
"""

import sys, json
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = REPO_ROOT / "mashang_workspace"
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
import plotly.graph_objects as go
from utils.plotly_theme import ZH, apply_zh_theme, GRID_COLOR, ZERO_LINE, AXIS_LINE, AXIS_TEXT, AXIS_TITLE

HERE = REPO_ROOT / "mashang_workspace"
ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
CONFIG_PARQUET = REPO_ROOT / "dataset" / "config_attribute.parquet"
BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
AVATAR = HERE / "assets" / "brand" / "raccoon_avatar_light.png"
SIGNATURE = HERE / "assets" / "brand" / "zihao_signature_transparent.png"

SERIES = "LS9"
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
        return "2025-11-01"


def assign_battery(pname: str) -> str:
    if "52" in pname:
        return "52 Ultra"
    if "66" in pname:
        return "66 Ultra"
    return "其他"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LS9 52/66 周度占比报告")
    parser.add_argument("--output", "-o", type=str, default=None, help="输出 HTML 路径")
    args = parser.parse_args()

    launch_date = load_launch_date()
    t_start = pd.Timestamp(launch_date)
    t_end = pd.Timestamp(datetime.now().date()) + pd.Timedelta(days=1)

    df = pd.read_parquet(str(ORDER_PARQUET))
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = df[df["lock_time"].notna()].copy()

    df_ls9 = df[df["series"] == SERIES].copy()
    df_ls9 = df_ls9[(df_ls9["lock_time"] >= t_start) & (df_ls9["lock_time"] < t_end)]

    # Non-staff only
    config = pd.read_parquet(str(CONFIG_PARQUET))
    non_staff = set(config[config["is_staff"] == 0]["Order Number"].unique())
    df_ls9 = df_ls9[df_ls9["order_number"].isin(non_staff)]

    iso = df_ls9["lock_time"].dt.isocalendar()
    df_ls9["week_year"] = iso["year"].astype(int)
    df_ls9["week_num"] = iso["week"].astype(int)
    df_ls9["week_label"] = df_ls9["week_year"].astype(str) + "-W" + df_ls9["week_num"].astype(str).str.zfill(2)
    df_ls9.sort_values("lock_time", inplace=True)

    df_ls9["battery_group"] = df_ls9["product_name"].apply(assign_battery)

    all_weeks = sorted(df_ls9["week_label"].unique())
    weeks_display = [w.replace("-W", " 第") + " 周" for w in all_weeks]

    weekly_total = df_ls9.groupby("week_label")["order_number"].nunique()
    weekly_bat = df_ls9.groupby(["week_label", "battery_group"])["order_number"].nunique().unstack(fill_value=0)

    pct_52 = []
    pct_66 = []
    for w in all_weeks:
        wt = int(weekly_total.get(w, 1))
        c52 = int(weekly_bat.loc[w, "52 Ultra"]) if w in weekly_bat.index and "52 Ultra" in weekly_bat.columns else 0
        c66 = int(weekly_bat.loc[w, "66 Ultra"]) if w in weekly_bat.index and "66 Ultra" in weekly_bat.columns else 0
        pct_52.append(round(c52 / wt * 100, 1))
        pct_66.append(round(c66 / wt * 100, 1))

    # Chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=weeks_display, y=pct_52, mode='lines+markers',
        name='52 Ultra',
        line=dict(color=ZH['own'], width=3),
        marker=dict(size=8, color=ZH['own']),
        hovertemplate='<b>%{x}</b><br>52 Ultra: %{y:.1f}%<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=weeks_display, y=pct_66, mode='lines+markers',
        name='66 Ultra',
        line=dict(color=ZH['event'], width=3),
        marker=dict(size=8, color=ZH['event']),
        hovertemplate='<b>%{x}</b><br>66 Ultra: %{y:.1f}%<extra></extra>',
    ))
    fig.update_layout(
        title=dict(text='52 Ultra vs 66 Ultra 周度占比', font=dict(size=16, color=COLOR_DEEP_BLUE), x=0.5),
        xaxis=dict(title=dict(text='', font=dict(color=AXIS_TITLE)), tickangle=-45, tickfont=dict(size=11, color=AXIS_TEXT)),
        yaxis=dict(title=dict(text='占 LS9 总锁单比重', font=dict(color=AXIS_TITLE)), ticksuffix='%', range=[0, 100],
                   tickfont=dict(size=11, color=AXIS_TEXT)),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5,
                    font=dict(size=12, color=COLOR_TEXT)),
        margin=dict(l=40, r=20, t=60, b=50), hovermode='x unified', height=400,
    )
    apply_zh_theme(fig)
    chart_html = fig.to_html(include_plotlyjs="cdn", full_html=False, div_id="chart-ratio")

    # Detail table
    detail_rows = ""
    for i, w in enumerate(all_weeks):
        wt = int(weekly_total.get(w, 1))
        c52 = pct_52[i]
        c66 = pct_66[i]
        abs52 = int(weekly_bat.loc[w, "52 Ultra"]) if w in weekly_bat.index and "52 Ultra" in weekly_bat.columns else 0
        abs66 = int(weekly_bat.loc[w, "66 Ultra"]) if w in weekly_bat.index and "66 Ultra" in weekly_bat.columns else 0
        detail_rows += f"<tr><td>{weeks_display[i]}</td><td>{wt:,}</td><td>{abs52:,} ({c52}%)</td><td>{abs66:,} ({c66}%)</td></tr>"

    total_lock = int(df_ls9["order_number"].nunique())
    total_52 = int(df_ls9[df_ls9["battery_group"] == "52 Ultra"]["order_number"].nunique())
    total_66 = int(df_ls9[df_ls9["battery_group"] == "66 Ultra"]["order_number"].nunique())
    week_count = len(all_weeks)
    latest_52 = pct_52[-1] if pct_52 else 0
    latest_66 = pct_66[-1] if pct_66 else 0

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    avatar_b64 = _img_b64(AVATAR) if AVATAR.exists() else ""
    sig_b64 = _img_b64(SIGNATURE) if SIGNATURE.exists() else ""

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LS9 52/66 周度占比走势</title>
  <style>
    :root {{
      --zh-blue: #174A7C; --zh-blue-700: #123B63; --zh-blue-500: #2D6FA3;
      --zh-deep-blue: #06213D; --zh-cyan: #7ECDEB; --zh-cyan-100: #E8F8FD;
      --zh-cream: #FFF9EF; --zh-raccoon-gold: #D79A36; --zh-gold-700: #A96F1F; --zh-gold-100: #FFF0D6;
      --zh-brown: #7A4A24; --zh-text: #1F2D3D; --zh-muted: #6B7280; --zh-card: #FFFFFF;
      --zh-border: #E5EAF0; --zh-bg: #FAFBFC; --zh-panel: #F6F8FA; --zh-row-alt: #FAFAFA;
      --zh-grid: #EEF2F6; --zh-axis-line: #8A94A3; --zh-axis-text: #5F6B7A; --zh-axis-title: #374151;
      --status-positive: #2A9D8F; --status-negative: #D95F59;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
      background: var(--zh-bg); color: var(--zh-text); line-height: 1.6;
    }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 0 24px; }}
    header {{ background: var(--zh-card); border-bottom: 1px solid var(--zh-border); padding: 16px 0; }}
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
    .table-wrap {{ overflow-x: auto; }}
    table.data-table {{ width: 100%; border-collapse: collapse; }}
    table.data-table th {{
      text-align: left; font-size: 12px; font-weight: 600; color: var(--zh-muted);
      text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 12px;
      border-bottom: 2px solid var(--zh-border);
    }}
    table.data-table td {{
      padding: 10px 12px; border-bottom: 1px solid var(--zh-border); font-size: 14px;
    }}
    table.data-table tr:last-child td {{ border-bottom: none; }}
    table.data-table tbody tr:nth-child(even) {{ background: var(--zh-row-alt); }}
    table.data-table tbody tr:hover {{ background: var(--zh-panel); }}
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
      <h1>LS9 52 Ultra / 66 Ultra 周度占比走势</h1>
      <p>上市（{launch_date}）以来 {week_count} 周 · 累计锁单 {total_lock:,} 单 · 仅用户车</p>
    </section>

    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="label">累计锁单</div>
        <div class="value">{total_lock:,}</div>
        <div class="sub">上市以来 {week_count} 周</div>
      </div>
      <div class="kpi-card">
        <div class="label">52 Ultra 累计</div>
        <div class="value">{total_52:,}</div>
        <div class="sub" style="color:var(--zh-blue);">标准电池组别</div>
      </div>
      <div class="kpi-card">
        <div class="label">66 Ultra 累计</div>
        <div class="value">{total_66:,}</div>
        <div class="sub" style="color:var(--zh-raccoon-gold);">大电池组别</div>
      </div>
      <div class="kpi-card">
        <div class="label">最新周 52 占比</div>
        <div class="value" style="font-size:22px;">{latest_52}%</div>
        <div class="sub">vs 66: {latest_66}%</div>
      </div>
    </div>

    <div class="card">
      <div class="chart-wrap">
        {chart_html}
      </div>
    </div>

    <div class="card">
      <h2>周度明细</h2>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>周</th>
              <th>总锁单</th>
              <th>52 Ultra</th>
              <th>66 Ultra</th>
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
          <strong>52 Ultra</strong> 整体占 LS9 锁单比重约 <strong>37-69%</strong>，走势呈 U 型：
          上市初期 67%，经历 1-2 月低谷（37-41%）后持续回升，最新周回归 <strong>{latest_52}%</strong>。
        </p>
      </div>
      <div class="insight-card">
        <p>
          <strong>66 Ultra</strong> 整体占 LS9 锁单比重约 <strong>31-63%</strong>，与 52 Ultra 呈镜像走势。
          上市第 3-4 个月（1-2 月）一度成为主力（59-63%），之后持续收窄至最新周 <strong>{latest_66}%</strong>。
        </p>
      </div>
      <div class="insight-card">
        <p>
          <strong>与 LS8 对比</strong>：LS9 的趋势晚于 LS8 约 4-5 个月进入"52 主导"阶段。
          两款车型最新周 52 占比接近（LS8 ~70%、LS9 ~69%），说明标准电池版本在各车型中均成为绝对主力。
        </p>
      </div>
    </div>

    <div class="card">
      <h2>数据说明</h2>
      <table class="scope-table">
        <tr><td>数据源</td><td>{ORDER_PARQUET} + {CONFIG_PARQUET}</td></tr>
        <tr><td>车系</td><td>{SERIES}</td></tr>
        <tr><td>时间窗口</td><td>{launch_date} ~ {datetime.now().strftime('%Y-%m-%d')}</td></tr>
        <tr><td>组别口径</td><td>52 Ultra = product_name 含 "52"（标准电池）；66 Ultra = product_name 含 "66"（大电池）</td></tr>
        <tr><td>占比口径</td><td>各版本锁单 / 当周 LS9 总锁单</td></tr>
        <tr><td>指标</td><td>lock_count = COUNTD(order_number)，仅用户车（is_staff=0）</td></tr>
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

    out_path = Path(args.output) if args.output else HERE / "outputs" / "reports" / "ls9_battery_weekly_share.html"
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
