#!/usr/bin/env python3
"""
watchlist 品牌 12 个月销量趋势脚本。

展示大盘与 watchlist 品牌最近 12 个月的销量走势（含基准月），配合品牌月报
做月度环比/同比快照之外的持续走势观察。

用法:
    python mashang_workspace/research_scripts/watchlist_brand_trend.py
    python mashang_workspace/research_scripts/watchlist_brand_trend.py --month 2026-07
    python mashang_workspace/research_scripts/watchlist_brand_trend.py --brands 智界,方程豹
    python mashang_workspace/research_scripts/watchlist_brand_trend.py --format csv

输出:
    outputs/reports/watchlist_brand_trend_{month}.html
    outputs/tables/watchlist_brand_trend_{month}.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[2]
WS_ROOT = ROOT / "mashang_workspace"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WS_ROOT))

from utils.plotly_theme import apply_zh_theme, get_series_color
from utils.watchlist_brand_common import (
    DEFAULT_OWN_BRAND,
    load_brand_sales,
    load_market_sales,
    load_watchlist,
    trend_months,
    fmt_pct,
    safe_int,
)

TREND_MONTHS = 12
DEFAULT_ANOMALY_THRESHOLD = 0.20


def default_month() -> str:
    now = datetime.now()
    prev = date(now.year, now.month, 1) - timedelta(days=1)
    return f"{prev.year}-{prev.month:02d}"


def pivot_brand(df: pd.DataFrame, months: list[str]) -> pd.DataFrame:
    df = df[df.date_month.isin(months)]
    return df.pivot_table(index="brand", columns="date_month", values="sales", aggfunc="sum")


def pick_trend_brands(piv: pd.DataFrame, months: list[str], cur, prev,
                      own: str, explicit: list[str] | None) -> list[str]:
    """默认折线图品牌 = 本品 + 环比异动品牌；--brands 指定时仅用指定。"""
    if explicit:
        return [b for b in explicit if b in piv.index]
    brands = [own] if own in piv.index else []
    for b in piv.index:
        if b == own:
            continue
        c, p = piv.loc[b, cur], piv.loc[b, prev]
        if p > 0 and abs((c - p) / p) >= DEFAULT_ANOMALY_THRESHOLD:
            brands.append(b)
    return brands


def build_figs(market: pd.DataFrame, piv: pd.DataFrame, months: list[str],
               trend_brands: list[str], own: str, month_label: str) -> str:
    labels = [m[:7] for m in months]
    figs = []

    # 图 1：大盘 12 月
    fig1 = go.Figure()
    fig1.add_bar(x=labels, y=[int(x) for x in market["sales"]], name="大盘",
                 marker_color=get_series_color("ash"))
    fig1.add_trace(go.Scatter(
        x=labels, y=[int(x) for x in market["sales"]],
        mode="lines+markers", name="大盘",
        line=dict(color=get_series_color("own"), width=2)))
    fig1.update_layout(title=f"{month_label} 大盘 12 个月销量（{TREND_MONTHS} 个月）",
                       yaxis_title="销量（台）", showlegend=False)
    apply_zh_theme(fig1)
    figs.append(fig1.to_html(full_html=False, include_plotlyjs=False,
                             config={"displayModeBar": False}))

    # 图 2：重点品牌 12 月
    if trend_brands:
        fig2 = go.Figure()
        for i, b in enumerate(trend_brands):
            y = [safe_int(piv.loc[b, m]) for m in months]
            role = "own" if b == own else "competitor"
            color = get_series_color(role, i if role != "own" else 0)
            fig2.add_trace(go.Scatter(
                x=labels, y=y, mode="lines+markers", name=b,
                line=dict(color=color, width=3 if b == own else 1.5)))
        fig2.update_layout(title=f"重点品牌 12 个月销量（本品 {own} + 环比异动）",
                           yaxis_title="销量（台）", legend=dict(orientation="h",
                                                               yanchor="bottom", y=1.02))
        apply_zh_theme(fig2)
        figs.append(fig2.to_html(full_html=False, include_plotlyjs=False,
                                 config={"displayModeBar": False}))

    return "\n".join(f'<div class="chart-box">{f}</div>' for f in figs)


def build_html(market, piv, months, trend_brands, own, month_label) -> str:
    labels = [m[:7] for m in months]
    figs = build_figs(market, piv, months, trend_brands, own, month_label)

    # 全量 watchlist 品牌 × 12 月表格
    watch = load_watchlist()
    all_brands = [b for group in watch.values() for b in group]
    rows_html = []
    for b in all_brands:
        if b not in piv.index:
            rows_html.append(
                f'<tr><td class="label">{b}</td>'
                + '<td class="num" style="color:var(--zh-muted)" colspan="12">数据集无此品牌</td></tr>')
            continue
        vals = "".join(f'<td class="num">{safe_int(piv.loc[b, m]):,}</td>' for m in months)
        rows_html.append(f'<tr><td class="label">{b}</td>{vals}</tr>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{month_label} watchlist 品牌 12 个月销量趋势</title>
<link rel="stylesheet" href="../../templates/report_style.css">
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
  .report-page {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }}
  .report-section {{ margin-bottom: 28px; }}
  .chart-box {{ background: #fff; border: 1px solid var(--zh-border); border-radius: 12px; padding: 12px; }}
  .scope-box {{ background: var(--zh-panel); border: 1px solid var(--zh-border); border-radius: 12px; padding: 16px 20px; }}
  .table-wrap {{ overflow-x: auto; }}
  td.label {{ font-weight: 600; color: var(--zh-text); }}
</style>
</head>
<body class="report-page">
<div class="report-container">

<h1 class="report-title">{month_label} watchlist 品牌 12 个月销量趋势</h1>
<p class="report-subtitle">
  窗口 {labels[0]} ~ {labels[-1]} · 配合品牌月报做持续走势观察 · 品牌经 brand_alias_map.yaml 归一化
</p>

<div class="report-section">{figs}</div>

<div class="report-section">
  <h2 class="section-title">watchlist 品牌 · {TREND_MONTHS} 个月销量矩阵</h2>
  <div class="table-wrap"><table class="report-table">
    <thead><tr><th>品牌</th>{''.join(f'<th>{l}</th>' for l in labels)}</tr></thead>
    <tbody>{''.join(rows_html)}</tbody>
  </table></div>
</div>

<div class="report-section">
  <h2 class="section-title">口径说明</h2>
  <div class="scope-box"><ul style="margin:0;padding-left:18px;color:var(--zh-muted);font-size:13px;line-height:1.9;">
    <li>数据源：dataset/TP&MIX-ways/parquet/brand_monthly.parquet、market_energy_monthly.parquet（经 shared/loaders/tp_and_mix_ways_loader 读取）</li>
    <li>时间窗口：{month_label} 往前共 {TREND_MONTHS} 个月（{labels[0]} ~ {labels[-1]}）</li>
    <li>指标口径：品牌/大盘维度销量合计（sales，含全燃料类型）；折线图默认本品 {own} + 环比异动品牌（|环比| ≥ {DEFAULT_ANOMALY_THRESHOLD:.0%}），可用 --brands 指定</li>
    <li>品牌映射：utils/brand_mapping.py + configs/brand_alias_map.yaml</li>
  </ul></div>
</div>

</div>
</body>
</html>"""


def write_csv(piv, months, path):
    labels = [m[:7] for m in months]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["品牌"] + labels)
        for b in piv.index:
            w.writerow([b] + [safe_int(piv.loc[b, m]) for m in months])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="watchlist 品牌 12 个月销量趋势")
    parser.add_argument("--month", default=default_month(), help="基准月 YYYY-MM（默认上月）")
    parser.add_argument("--brands", default="", help="折线图品牌，逗号分隔（默认本品+环比异动）")
    parser.add_argument("--format", choices=["html", "csv", "all"], default="all")
    parser.add_argument("--output", default="outputs", help="输出目录（workspace 下，默认 outputs）")
    args = parser.parse_args(argv)

    months = trend_months(args.month, TREND_MONTHS)
    cur, prev = months[-1], months[-2]
    brand_df = load_brand_sales()
    piv = pivot_brand(brand_df, months)
    market = load_market_sales(months)
    own = DEFAULT_OWN_BRAND
    explicit = [b.strip() for b in args.brands.split(",") if b.strip()] or None
    trend_brands = pick_trend_brands(piv, months, cur, prev, own, explicit)

    month_label = f"{int(args.month[:4])}年{int(args.month[5:7])}月"
    reports_dir = WS_ROOT / args.output / "reports"
    tables_dir = WS_ROOT / args.output / "tables"
    reports_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    if args.format in ("html", "all"):
        out_html = reports_dir / f"watchlist_brand_trend_{args.month}.html"
        out_html.write_text(build_html(market, piv, months, trend_brands, own, month_label),
                            encoding="utf-8")
        print(f"[HTML] {out_html}")
    if args.format in ("csv", "all"):
        out_csv = tables_dir / f"watchlist_brand_trend_{args.month}.csv"
        write_csv(piv, months, out_csv)
        print(f"[CSV ] {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
