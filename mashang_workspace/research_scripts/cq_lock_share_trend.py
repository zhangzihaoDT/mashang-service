#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重庆 / 川渝地区锁单占比日趋势（MA7）

以「XX门店锁单数 / 全量锁单数」为日粒度指标，做 7 日移动平均平滑，
绘制占比折线图（品牌化 HTML 报告）。默认绘制两条 MA7 折线：
- 重庆（store_city 含「重庆」）
- 川渝地区 = 西区-川云 + 西区-贵渝 两个大区的组合（parent_region_name 经 utils.regions.norm_region 归一后取并集，含四川+重庆+贵州）

口径：
- 锁单 = lock_time NOT NULL（COUNTD order_number），与 daily_lock_count 一致
- 重庆门店 = store_city 含「重庆」，等价于店名以「重庆」开头（含换铺/分销店）
- 川渝地区 = parent_region_name 旧架构（一区/二区/三区-*）归一到新架构后，取「西区-川云」+「西区-贵渝」的组合
- 时间窗口：近 365 天（默认），至数据最新日

用法:
    python research_scripts/cq_lock_share_trend.py
    python research_scripts/cq_lock_share_trend.py --days 365 --output outputs/reports/cq_share.html
    python research_scripts/cq_lock_share_trend.py --cq-only   # 只画重庆一条
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(_WS_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from utils.plotly_theme import ZH, apply_zh_theme  # noqa: E402
from utils.regions import norm_region  # noqa: E402

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
DEFAULT_OUT = _WS_ROOT / "outputs" / "reports" / "cq_lock_share_trend.html"


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description="重庆 / 川渝地区锁单占比日趋势（MA7）折线图")
    p.add_argument("--days", type=int, default=365, help="回溯天数（默认 365）")
    p.add_argument("--output", default=str(DEFAULT_OUT), help="输出 HTML 路径")
    p.add_argument("--cq-only", action="store_true", help="只画重庆一条折线（不含川渝地区）")
    return p.parse_args(argv)


def load_locks() -> pd.DataFrame:
    df = pd.read_parquet(str(ORDER_PARQUET),
                         columns=["order_number", "store_city", "parent_region_name", "lock_time"])
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = df[df["lock_time"].notna()].copy()
    df["date"] = df["lock_time"].dt.normalize()
    df["is_cq"] = df["store_city"].astype(str).str.contains("重庆", na=False)
    df["region"] = df["parent_region_name"].map(norm_region)
    df["is_cqcy"] = df["region"].isin({"西区-川云", "西区-贵渝"})
    return df


def daily_share(df: pd.DataFrame, days: int) -> pd.DataFrame:
    latest = df["lock_time"].max().normalize()
    start = latest - pd.Timedelta(days=days - 1)
    d = df[df["date"] >= start]
    total = d.groupby("date")["order_number"].nunique().rename("total")
    cq = d[d["is_cq"]].groupby("date")["order_number"].nunique().rename("cq")
    cy = d[d["is_cqcy"]].groupby("date")["order_number"].nunique().rename("cy")
    out = pd.concat([total, cq, cy], axis=1).fillna(0)
    out["share_pct"] = out["cq"] / out["total"] * 100.0
    out["share_ma7"] = out["share_pct"].rolling(7, min_periods=7).mean()
    out["cy_share_pct"] = out["cy"] / out["total"] * 100.0
    out["cy_share_ma7"] = out["cy_share_pct"].rolling(7, min_periods=7).mean()
    return out


def make_figure(daily: pd.DataFrame, days: int, cq_only: bool = False) -> go.Figure:
    x = daily.index
    fig = go.Figure()
    # 重庆 日比值（浅色底层，参考趋势毛刺）
    fig.add_trace(go.Scatter(
        x=x, y=daily["share_pct"].tolist(), mode="lines", name="重庆·每日占比",
        line=dict(color="rgba(122,139,118,0.45)", width=1),
        hovertemplate="%{x|%Y-%m-%d}<br>重庆每日占比：%{y:.2f}%<extra></extra>",
    ))
    # 重庆 MA7 主线
    fig.add_trace(go.Scatter(
        x=x, y=daily["share_ma7"].tolist(), mode="lines", name="重庆·7日移动平均",
        line=dict(color=ZH["own"], width=2.5),
        hovertemplate="%{x|%Y-%m-%d}<br>重庆 MA7：%{y:.2f}%<extra></extra>",
    ))
    if not cq_only:
        # 川渝地区 日比值
        fig.add_trace(go.Scatter(
            x=x, y=daily["cy_share_pct"].tolist(), mode="lines", name="川渝地区·每日占比",
            line=dict(color="rgba(215,154,54,0.40)", width=1),
            hovertemplate="%{x|%Y-%m-%d}<br>川渝每日占比：%{y:.2f}%<extra></extra>",
        ))
        # 川渝地区 MA7 主线
        fig.add_trace(go.Scatter(
            x=x, y=daily["cy_share_ma7"].tolist(), mode="lines", name="川渝地区·7日移动平均",
            line=dict(color=ZH["event"], width=2.5),
            hovertemplate="%{x|%Y-%m-%d}<br>川渝 MA7：%{y:.2f}%<extra></extra>",
        ))
    apply_zh_theme(fig)
    fig.update_xaxes(title_text=f"日期（近 {days} 天）")
    fig.update_yaxes(title_text="占比（%）", ticksuffix="%")
    fig.update_layout(
        height=520, margin=dict(l=60, r=24, t=20, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                    font=dict(size=11)),
        hovermode="x unified",
    )
    return fig


def render_html(fig: go.Figure, daily: pd.DataFrame, cq_only: bool = False) -> str:
    static = "../.."
    latest = daily.index.max()
    latest_row = daily.loc[latest]
    n_days = len(daily)
    cq_sum = int(daily["cq"].sum())
    cy_sum = int(daily["cy"].sum())
    tot_sum = int(daily["total"].sum())
    cy_ma7_now = float(daily["cy_share_ma7"].iloc[-1]) if not cq_only else float("nan")
    cards = "\n".join([
        f'<div class="summary-card"><div class="summary-value" style="color:{ZH["own"]}">{float(daily["share_ma7"].iloc[-1]):.2f}%</div>'
        f'<div class="summary-label">最新 MA7 占比</div><div class="summary-hint">{latest.strftime("%Y-%m-%d")} 重庆锁单 {int(latest_row["cq"])} / {int(latest_row["total"])}</div></div>',
        f'<div class="summary-card"><div class="summary-value" style="color:{ZH["ash"]}">{n_days}</div>'
        f'<div class="summary-label">统计天数</div><div class="summary-hint">{latest.strftime("%Y-%m-%d")} 往前回溯</div></div>',
        f'<div class="summary-card"><div class="summary-value" style="color:{ZH["ash"]}">{cq_sum:,}</div>'
        f'<div class="summary-label">重庆锁单合计</div><div class="summary-hint">区间内 占总量 {cq_sum/tot_sum*100:.2f}%</div></div>',
        f'<div class="summary-card"><div class="summary-value" style="color:{ZH["event"]}">{cy_ma7_now:.2f}%</div>'
        f'<div class="summary-label">川渝地区最新 MA7</div><div class="summary-hint">{latest.strftime("%Y-%m-%d")} 区间合计 {cy_sum:,}（{cy_sum/tot_sum*100:.2f}%）</div></div>',
    ])
    chart = fig.to_html(full_html=False, include_plotlyjs=False, div_id="share",
                        config={"displayModeBar": False, "responsive": True})
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>重庆 / 川渝地区锁单占比日趋势 | Raccoon Research</title>
<link rel="stylesheet" href="{static}/templates/report_style.css" />
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
</head>
<body class="report-page">
<header>
  <div class="container">
    <div class="brand">
      <img class="brand-avatar" src="{static}/assets/brand/raccoon_avatar_light.png" alt="" />
      <span class="brand-name">Raccoon Research</span>
    </div>
    <span class="header-meta">门店经营观察 | 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
  </div>
</header>
<main class="container">
  <section class="hero">
    <h1>重庆 / 川渝地区锁单占比日趋势（MA7）</h1>
    <p>数据源：<code>dataset/order_data.parquet</code> · 锁单 = order_number 且 lock_time 非空 · 重庆门店 = store_city 含「重庆」· 川渝地区 = 「西区-川云」+「西区-贵渝」两个大区的组合（parent_region_name 归一后取并集，含四川+重庆+贵州）· 日占比 + 7 日移动平均</p>
  </section>
  <section class="summary-grid">
    {cards}
  </section>
  <section class="report-section">
    <h2 class="section-title">占比折线</h2>
    <div class="chart-box">{chart}</div>
    <p class="section-note">细线为每日占比，粗线为各自 MA7（深蓝=重庆，金色=川渝地区）。占比 = 该范围锁单 / 全量锁单。</p>
  </section>
</main>
<footer>
  <img class="brand-sig" src="{static}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />
  <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>
</body>
</html>"""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    df = load_locks()
    daily = daily_share(df, args.days)
    fig = make_figure(daily, args.days, cq_only=args.cq_only)
    html = render_html(fig, daily, cq_only=args.cq_only)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    ma7_now = float(daily["share_ma7"].iloc[-1])
    cy_ma7_now = float(daily["cy_share_ma7"].iloc[-1])
    print(f"✅ 已生成: {out}")
    print(f"   窗口 {daily.index.min().strftime('%Y-%m-%d')} → {daily.index.max().strftime('%Y-%m-%d')}（{len(daily)} 天）")
    print(f"   重庆锁单共 {int(daily['cq'].sum()):,} / 总量 {int(daily['total'].sum()):,}（{daily['cq'].sum()/daily['total'].sum()*100:.2f}%）")
    print(f"   川渝地区锁单共 {int(daily['cy'].sum()):,} / 总量（{daily['cy'].sum()/daily['total'].sum()*100:.2f}%）")
    print(f"   最新 MA7 占比 重庆 {ma7_now:.2f}%  | 川渝地区 {cy_ma7_now:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())