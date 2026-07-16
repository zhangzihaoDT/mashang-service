#!/usr/bin/env python
"""
基准转化率趋势 — Benchmark Conversion Rate Trend

对每个历史时间点，计算成熟 cohort（age ≥ 30d）在 24 个月窗口内的
基准转化率 (r0, r7, avg_30d_rate)，展示基准随时间的演变。

用法:
    python research_scripts/benchmark_conversion_trend.py
    python research_scripts/benchmark_conversion_trend.py --step month
    python research_scripts/benchmark_conversion_trend.py --format json
"""

import sys, argparse, json
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

from utils.plotly_theme import ZH, apply_zh_theme
from utils.result_contract import build_partial_contract, save_contract_json


def _parse_cn_date(s: pd.Series) -> pd.Series:
    s = s.astype(str)
    parts = s.str.extract(r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日")
    dt = pd.to_datetime(parts["y"] + "-" + parts["m"] + "-" + parts["d"], errors="coerce").dt.normalize()
    if dt.notna().any():
        return dt
    return pd.to_datetime(s, errors="coerce").dt.normalize()

ASSIGN_CSV = REPO_ROOT / "dataset" / "assign_data.csv"
OUTPUT_HTML = _WS_ROOT / "outputs" / "reports" / "benchmark_conversion_trend.html"
MONTH_WINDOW = 24

BRAND = {
    "own": ZH["own"], "event": ZH["event"], "ash": ZH["ash"],
    "positive": ZH["positive"], "negative": ZH["negative"],
    "sky_muted": ZH["sky_muted"], "neutral": ZH["neutral"],
    "bg": "#FFF9EF", "card": "#FFFFFF", "border": "#D8E3EA",
    "light": "#DDEFF8", "deep": "#06213D", "muted": "#6B7280",
}

BLUE = "\033[38;2;23;74;124m"
DEEP = "\033[38;2;6;33;61m"
GOLD = "\033[38;2;215;154;54m"
CYAN = "\033[38;2;126;205;235m"
MUTED = "\033[38;2;107;124;143m"
BOLD = "\033[1m"
RST = "\033[0m"


def parse_args():
    p = argparse.ArgumentParser(description="基准转化率趋势")
    p.add_argument("--step", choices=["week", "month"], default="month",
                    help="采样步长（默认 month）")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    p.add_argument("--output", type=str, default=None,
                    help="JSON 输出目录")
    return p.parse_args()


def load_data():
    df = pd.read_csv(str(ASSIGN_CSV))
    df["_date"] = _parse_cn_date(df.get("Assign Time 年/月/日", pd.Series(dtype="object")))
    df = df[df["_date"].notna()].copy()
    df["_leads"] = df.get("下发线索数", 0).fillna(0).astype(float)
    df["_lock0"] = df.get("下发线索当日锁单数 (门店)", 0).fillna(0).astype(float)
    df["_lock7"] = df.get("下发线索 7 日锁单数", 0).fillna(0).astype(float)
    df["_lock30"] = df.get("下发线索 30 日锁单数", 0).fillna(0).astype(float)
    df = df.sort_values("_date").reset_index(drop=True)
    print(f"  {CYAN}数据加载: {ASSIGN_CSV.name}, {len(df)} 行{RST}")
    print(f"  {CYAN}数据范围: {df['_date'].min().date()} ~ {df['_date'].max().date()}{RST}")
    return df


def compute_benchmark(df, snapshot_date):
    """计算 snapshot_date 时的基准转化率（24 个月窗口）。"""
    window_start = snapshot_date - pd.DateOffset(months=MONTH_WINDOW)
    mature = df[(df["_date"] <= snapshot_date - pd.Timedelta(days=30))
                & (df["_date"] >= window_start)]
    if mature.empty or mature["_leads"].sum() <= 0:
        return None
    total_leads = float(mature["_leads"].sum())
    total_lock0 = float(mature["_lock0"].sum())
    total_lock7 = float(mature["_lock7"].sum())
    total_lock30 = float(mature["_lock30"].sum())
    if total_lock30 <= 0:
        return None
    return {
        "snapshot": snapshot_date,
        "mature_cohorts": len(mature),
        "total_leads": int(total_leads),
        "total_lock30": int(total_lock30),
        "avg_30d_rate": total_lock30 / total_leads,
        "r7": total_lock7 / total_lock30,
        "r0": total_lock0 / total_lock30,
    }


def compute_trend(df, step="month"):
    first_date = df["_date"].min() + pd.Timedelta(days=30)
    last_date = df["_date"].max()
    freq_map = {"week": "W", "month": "MS"}
    snapshots = pd.date_range(first_date, last_date, freq=freq_map.get(step, "MS"))
    rows = []
    for s in snapshots:
        bm = compute_benchmark(df, s)
        if bm is not None:
            rows.append(bm)
    return pd.DataFrame(rows)


def generate_html(trend_df, step):
    from plotly import graph_objects as go
    from plotly.subplots import make_subplots

    dates = trend_df["snapshot"].tolist()
    avg_rate = trend_df["avg_30d_rate"].tolist()
    r7_vals = trend_df["r7"].tolist()
    r0_vals = trend_df["r0"].tolist()
    n_cohorts = trend_df["mature_cohorts"].tolist()

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=("30日锁单率 (avg_30d_rate)", "7日占30日比例 (r7)",
                        "当日占30日比例 (r0)"),
    )

    fig.add_trace(go.Scatter(
        x=dates, y=avg_rate, mode="lines+markers",
        name="avg_30d_rate",
        line=dict(color=BRAND["own"], width=2),
        marker=dict(size=4, color=BRAND["own"]),
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=dates, y=r7_vals, mode="lines+markers",
        name="r7",
        line=dict(color=BRAND["event"], width=2),
        marker=dict(size=4, color=BRAND["event"]),
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=dates, y=r0_vals, mode="lines+markers",
        name="r0",
        line=dict(color=BRAND["sky_muted"], width=2),
        marker=dict(size=4, color=BRAND["sky_muted"]),
    ), row=3, col=1)

    window_start_x = (trend_df["snapshot"].max() - pd.DateOffset(months=MONTH_WINDOW)).timestamp()
    fig.add_vline(
        x=window_start_x * 1000,
        line=dict(color=BRAND["negative"], width=1.5, dash="dash"),
        annotation_text="24mo 窗口起点",
        annotation=dict(font=dict(color=BRAND["negative"], size=10)),
        row="all",
    )

    apply_zh_theme(fig)
    fig.update_layout(
        height=620,
        margin=dict(l=60, r=30, t=40, b=40),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08, x=0),
        title=dict(
            text=f"基准转化率趋势 (24 个月窗口 · {step}采样)",
            font=dict(size=16, color=BRAND["deep"]),
            x=0.5,
        ),
    )
    fig.update_annotations(font=dict(size=11, color=BRAND["deep"]))

    final_date = trend_df["snapshot"].max()
    latest = trend_df[trend_df["snapshot"] == final_date].iloc[0]

    table_rows = ""
    for _, r in trend_df.tail(24).iterrows():
        table_rows += f"""<tr>
<td>{r['snapshot'].strftime('%Y-%m')}</td>
<td>{r['mature_cohorts']}</td>
<td>{r['total_leads']:,}</td>
<td>{r['total_lock30']:,}</td>
<td>{r['avg_30d_rate']:.4f}</td>
<td>{r['r7']:.4f}</td>
<td>{r['r0']:.4f}</td>
</tr>\n"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>基准转化率趋势</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root {{
    --bg: #FFF9EF; --card: #FFFFFF;
    --deep: #06213D; --blue: #174A7C; --muted: #6B7280;
    --border: #D8E3EA; --light: #DDEFF8; --panel: #F5F8FB;
    --row-alt: #F8FAFC; --pos: #2A9D8F; --neg: #D95F59;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
        background: var(--bg); color: #1F2D3D; line-height: 1.5; }}
.header {{ background: linear-gradient(135deg, var(--deep) 0%, #0A3A5C 100%);
          color: #fff; padding: 30px 32px 22px; }}
.header h1 {{ font-size: 22px; font-weight: 600; letter-spacing: 0.5px; }}
.header p {{ font-size: 13px; opacity: 0.75; margin-top: 6px; }}
.stats {{ display: flex; gap: 12px; padding: 18px 24px; flex-wrap: wrap; }}
.stat-card {{ background: var(--card); border-radius: 10px; padding: 14px 20px;
             min-width: 120px; box-shadow: 0 1px 4px rgba(6,33,61,.06); }}
.stat-card .num {{ font-size: 24px; font-weight: 700; }}
.stat-card .label {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
.chart-section {{ padding: 0 24px 24px; }}
.chart-box {{ background: var(--card); border-radius: 12px; padding: 20px;
             margin-bottom: 20px; box-shadow: 0 1px 4px rgba(6,33,61,.06); }}
.chart-box h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 14px;
                color: var(--deep); padding-bottom: 8px; border-bottom: 2px solid var(--light); }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: var(--deep); color: #fff; padding: 10px 12px; text-align: left; font-weight: 500; }}
td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); }}
tbody tr:nth-child(even) td {{ background: var(--row-alt); }}
tbody tr:hover td {{ background: var(--panel); }}
.footer {{ text-align: center; padding: 24px; font-size: 12px; color: var(--muted);
          border-top: 1px solid var(--border); margin-top: 8px; }}
</style>
</head>
<body>
<div class="header">
  <h1>基准转化率趋势</h1>
  <p>{trend_df['snapshot'].min().date()} ~ {trend_df['snapshot'].max().date()} | {step}采样 |
     数据截止 {ASSIGN_CSV.name}</p>
</div>
<div class="stats">
  <div class="stat-card"><div class="num" style="color:{BRAND['own']}">{latest['avg_30d_rate']:.4f}</div><div class="label">avg_30d_rate</div></div>
  <div class="stat-card"><div class="num" style="color:{BRAND['event']}">{latest['r7']:.4f}</div><div class="label">r7</div></div>
  <div class="stat-card"><div class="num" style="color:{BRAND['sky_muted']}">{latest['r0']:.4f}</div><div class="label">r0</div></div>
  <div class="stat-card"><div class="num" style="color:var(--blue)">{latest['mature_cohorts']}</div><div class="label">成熟 cohort 数</div></div>
  <div class="stat-card"><div class="num" style="color:var(--blue)">{latest['total_leads']:,}</div><div class="label">总线索数</div></div>
  <div class="stat-card"><div class="num" style="color:var(--blue)">{latest['total_lock30']:,}</div><div class="label">总锁单数</div></div>
</div>
<div class="chart-section">
<div class="chart-box">
  <h2>基准转化率变化</h2>
  <div id="chart-benchmark"></div>
</div>
<div class="chart-box">
  <h2>近 24 期明细</h2>
  <div style="overflow-x:auto;">
  <table>
  <thead><tr><th>日期</th><th>成熟 cohort</th><th>总线索数</th><th>总锁单数</th><th>avg_30d_rate</th><th>r7</th><th>r0</th></tr></thead>
  <tbody>{table_rows}</tbody>
  </table>
  </div>
</div>
</div>
<div class="footer">
  <img src="../../assets/brand/raccoon_avatar_light.png" style="height:28px;opacity:.5;margin-bottom:6px" /><br/>
  Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Raccoon Research
</div>
<script>
var fig = {fig.to_json()};
Plotly.newPlot('chart-benchmark', fig.data, fig.layout, {{displayModeBar: false}});
</script>
</body>
</html>"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    return OUTPUT_HTML


def main():
    args = parse_args()
    cmd = "python " + " ".join(sys.argv)
    contract = None
    trend = None

    try:
        df = load_data()
        trend = compute_trend(df, step=args.step)
        if trend.empty:
            print(f"  {GOLD}⚠ 无法计算趋势（数据不足）{RST}")
            return

        if args.format == "terminal":
            print(f"\n  {CYAN}{'━' * 64}{RST}")
            print(f"  {DEEP}{BOLD}基准转化率趋势 · {MONTH_WINDOW} 个月窗口{RST:^20}")
            print(f"  {CYAN}{'━' * 64}{RST}")
            print(f"  {GOLD}■{RST} {DEEP}{BOLD}当前基准{RST}")
            latest = trend.iloc[-1]
            print(f"    {BOLD}avg_30d_rate{RST}: {BLUE}{latest['avg_30d_rate']:.4f}{RST}  {MUTED}历史成熟 cohort 平均 30 日锁单率{RST}")
            print(f"    {BOLD}r7{RST}:           {BLUE}{latest['r7']:.4f}{RST}  {MUTED}7 日占 30 日比例{RST}")
            print(f"    {BOLD}r0{RST}:           {BLUE}{latest['r0']:.4f}{RST}  {MUTED}当日占 30 日比例{RST}")
            print(f"    {BOLD}成熟 cohort 数{RST}:  {BLUE}{latest['mature_cohorts']}{RST}")
            print(f"    {BOLD}总线索数{RST}:       {BLUE}{latest['total_leads']:,}{RST}")
            print(f"    {BOLD}总锁单数{RST}:       {BLUE}{latest['total_lock30']:,}{RST}")

            print(f"\n  {GOLD}■{RST} {DEEP}{BOLD}历年 avg_30d_rate{RST}")
            trend["year"] = trend["snapshot"].dt.year
            for yr, grp in trend.groupby("year"):
                avg_yr = grp["avg_30d_rate"].mean()
                last_yr = grp["avg_30d_rate"].iloc[-1]
                print(f"    {yr}: 均值 {avg_yr:.4f}  期末 {last_yr:.4f}")

            print(f"\n  {GOLD}■{RST} {DEEP}{BOLD}趋势变化率{RST}")
            half = len(trend) // 2
            early_avg = trend["avg_30d_rate"].iloc[:half].mean()
            late_avg = trend["avg_30d_rate"].iloc[half:].mean()
            change = (late_avg - early_avg) / early_avg * 100
            print(f"    前后半程变化: {change:+.1f}% ({early_avg:.4f} → {late_avg:.4f})")

        html_path = generate_html(trend, args.step)
        if args.format == "terminal":
            print(f"\n  {GOLD}■{RST} {DEEP}{BOLD}输出{RST}")
            print(f"    HTML: {html_path}")
            print(f"  {CYAN}{'━' * 64}{RST}\n")

        scope = {
            "data_source": str(ASSIGN_CSV),
            "time_window": {"start": str(trend["snapshot"].min().date()), "end": str(trend["snapshot"].max().date())},
            "filters": {"mature_cohort_window_months": MONTH_WINDOW},
            "metric_definition": "r0=lock0/lock30, r7=lock7/lock30, avg_30d_rate=lock30/leads (age>=30, window=24mo)",
        }
        result = {
            "summary": f"基准转化率趋势计算完成: avg_30d_rate={trend.iloc[-1]['avg_30d_rate']:.4f}, r7={trend.iloc[-1]['r7']:.4f}, r0={trend.iloc[-1]['r0']:.4f}",
            "metrics": {
                "avg_30d_rate": round(trend.iloc[-1]["avg_30d_rate"], 4),
                "r7": round(trend.iloc[-1]["r7"], 4),
                "r0": round(trend.iloc[-1]["r0"], 4),
            },
        }
        contract = build_partial_contract(
            script="research_scripts/benchmark_conversion_trend.py", command=cmd,
            scope=scope, result=result, warnings=[],
            followup_context={"metric": "benchmark_conversion_trend"},
        )

    except Exception as e:
        contract = build_partial_contract(
            script="research_scripts/benchmark_conversion_trend.py", command=cmd,
            scope={"data_source": str(ASSIGN_CSV)},
            result={"summary": f"执行异常: {e}"},
            warnings=[str(e)],
        )
        if args.format == "terminal":
            print(f"\n  {GOLD}⚠ 异常: {e}{RST}")
    if args.format == "json":
        if args.output:
            save_contract_json(contract, Path(args.output) / "benchmark_conversion_trend.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))

    if args.format == "terminal" and contract:
        print(f"  {CYAN}{'━' * 64}{RST}")
        print(f"  {GOLD}■{RST} {DEEP}{BOLD}数据信息{RST}")
        print(f"    {BOLD}数据源{RST}:  {contract['scope'].get('data_source', 'N/A')}")
        if trend is not None:
            print(f"    {BOLD}时间{RST}:    {trend['snapshot'].min().date()} ~ {trend['snapshot'].max().date()}")


if __name__ == "__main__":
    main()
