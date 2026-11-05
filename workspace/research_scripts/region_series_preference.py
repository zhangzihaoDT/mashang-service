#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
智己品牌 大区 × 车系 分布与区域偏好分析（近窗口，默认 90 天）

以「锁单数」为口径做 大区(归一后) × 车系 交叉分析，用 位置商（LQ=区域占比/全局占比）
识别哪些地区对某车系存在结构性偏好或弱偏好。

口径：
- 锁单 = lock_time NOT NULL（COUNTD order_number），与 daily_lock_count 一致
- 大区 = parent_region_name 经 utils.regions.norm_region 归一到新架构（旧一/二/三区-* → 东/西/北区-*）
- 车系 = series，取智己正式车系（LS6/L6/L8/L9/LS7/L7），LS7/L7 近窗口近零会被过滤
- LQ = (该大区该车系锁单 / 该大区锁单) / (该车系全部锁单 / 全部锁单)；LQ>1 偏高、<1 偏低
- 强偏好/弱偏好阈值：|LQ-1| ≥ 0.25 且该格锁单数 ≥ min_count（默认 30），过滤小样本噪声

用法:
    python research_scripts/region_series_preference.py
    python research_scripts/region_series_preference.py --days 90 --output outputs/reports/region_series_preference.html
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
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
DEFAULT_OUT = _WS_ROOT / "outputs" / "reports" / "region_series_preference.html"

SERIES_ORDER = ["LS6", "L6", "LS8", "LS9", "LS7", "L7"]
SPECIAL_REGIONS = {"虚拟大区", "未知"}


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description="智己品牌 大区 × 车系 分布与区域偏好（LQ 位置商）")
    p.add_argument("--days", type=int, default=90, help="回溯天数（默认 90）")
    p.add_argument("--output", default=str(DEFAULT_OUT), help="输出 HTML 路径")
    p.add_argument("--min-count", type=int, default=30, help="偏好判定最小锁单数（默认 30）")
    p.add_argument("--lq-threshold", type=float, default=0.25, help="|LQ-1| 阈值（默认 0.25）")
    return p.parse_args(argv)


def load_locks() -> pd.DataFrame:
    df = pd.read_parquet(str(ORDER_PARQUET),
                         columns=["order_number", "parent_region_name", "series", "lock_time"])
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = df[df["lock_time"].notna()].copy()
    df["date"] = df["lock_time"].dt.normalize()
    return df


def analyze(df: pd.DataFrame, days: int, min_count: int, lq_threshold: float) -> dict:
    latest = df["lock_time"].max()
    start = latest - pd.Timedelta(days=days - 1)
    d = df[df["date"] >= start]
    d = d[d["series"].isin(SERIES_ORDER)]
    d["region"] = d["parent_region_name"].map(norm_region)

    ct = pd.crosstab(d["region"], d["series"])
    keep_series = [c for c in SERIES_ORDER if ct[c].sum() >= min_count]
    ct = ct[keep_series]
    row_total = ct.sum(axis=1)
    col_total = ct.sum(axis=0)
    global_share = col_total / col_total.sum()
    row_share = ct.div(row_total, axis=0)
    lq = row_share.div(global_share, axis=1)

    regions_ordered = row_total.sort_values(ascending=False).index.tolist()
    special = [r for r in regions_ordered if r in SPECIAL_REGIONS]
    regions_ordered = [r for r in regions_ordered if r not in SPECIAL_REGIONS] + special
    ct = ct.loc[regions_ordered]
    row_share = row_share.loc[regions_ordered]
    lq = lq.loc[regions_ordered]

    strong, weak = [], []
    for r in lq.index:
        for c in lq.columns:
            n = int(ct.loc[r, c])
            if n < min_count:
                continue
            v = float(lq.loc[r, c])
            if v >= 1 + lq_threshold:
                strong.append({"lq": v, "region": r, "series": c, "count": n,
                               "row_share": float(row_share.loc[r, c]) * 100,
                               "global_share": float(global_share[c]) * 100})
            elif v <= 1 - lq_threshold:
                weak.append({"lq": v, "region": r, "series": c, "count": n,
                             "row_share": float(row_share.loc[r, c]) * 100,
                             "global_share": float(global_share[c]) * 100})
    strong.sort(key=lambda x: x["lq"], reverse=True)
    weak.sort(key=lambda x: x["lq"])

    return {
        "window_start": start.normalize(), "window_end": latest.normalize(),
        "total": int(col_total.sum()), "n_regions": len(ct), "n_series": len(keep_series),
        "ct": ct, "row_share": row_share, "global_share": global_share, "lq": lq,
        "row_total": row_total, "strong": strong, "weak": weak,
    }


def _clamp_lq(v: float) -> float:
    return max(0.5, min(1.5, v))


def make_figure(res: dict, min_count: int) -> go.Figure:
    ct, lq, row_share, global_share = res["ct"], res["lq"], res["row_share"], res["global_share"]
    x, y = list(lq.columns), list(lq.index)
    z = [[_clamp_lq(float(lq.loc[r, c])) for c in x] for r in y]
    text = [[f"{int(ct.loc[r, c]):,}" for c in x] for r in y]
    hover = [[f"{row_share.loc[r, c]*100:.1f}% · 全局 {global_share[c]*100:.1f}% · LQ {lq.loc[r, c]:.2f}"
              for c in x] for r in y]
    fig = go.Figure(go.Heatmap(
        z=z, x=x, y=y, text=text, customdata=hover,
        texttemplate="%{text}", textfont=dict(size=12, color="#1F2D3D"),
        hovertemplate="%{y} · %{x}<br>锁单 %{text}<br>区域占比 · 全局占比（LQ）%{customdata}<extra></extra>",
        colorscale=[[0.0, "#6A93B8"], [0.5, "#FFFFFF"], [1.0, "#D79A36"]],
        zmin=0.5, zmax=1.5, colorbar=dict(title="LQ", thickness=14, len=0.8),
    ))
    apply_zh_theme(fig)
    fig.update_yaxes(autorange="reversed", title_text="大区（归一后）")
    fig.update_xaxes(title_text="车系")
    fig.update_layout(
        height=660, margin=dict(l=70, r=30, t=30, b=40),
        title=dict(text="按 LQ 着色：白=无偏好，蓝=低于均线，金=高于均线（>1.25 或 <0.75 视为强弱偏好）",
                   font=dict(size=12), y=0.985),
    )
    return fig


def render_html(fig: go.Figure, res: dict, days: int, min_count: int, lq_threshold: float) -> str:
    static = "../.."
    total = f"{res['total']:,}"
    strong, weak = res["strong"], res["weak"]

    def pref_tr(p):
        lq_cls = "delta-positive" if p["lq"] >= 1 else "delta-negative"
        share_q = "bg-gold" if p["lq"] >= 1 else ""
        return (f'<tr><td class="num">{p["region"]}</td><td>{p["series"]}</td>'
                f'<td class="num">{p["count"]:,}</td>'
                f'<td class="num">{p["row_share"]:.1f}%</td>'
                f'<td class="num">{p["global_share"]:.1f}%</td>'
                f'<td class="num {lq_cls}">{p["lq"]:.2f}</td></tr>')

    strong_rows = "".join(pref_tr(p) for p in strong)
    weak_rows = "".join(pref_tr(p) for p in weak)

    chart = fig.to_html(full_html=False, include_plotlyjs=False, div_id="lq",
                        config={"displayModeBar": False, "responsive": True})

    noted = ("虚拟大区" if any(r["region"] == "虚拟大区" for r in strong + weak) else "")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>大区 × 车系 偏好分析 | Raccoon Research</title>
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
    <span class="header-meta">区域 × 车系偏好 | 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
  </div>
</header>
<main class="container">
  <section class="hero">
    <h1>智己品牌 大区 × 车系 分布与区域偏好（近 {days} 天）</h1>
    <p>数据源：<code>dataset/order_data.parquet</code> · 锁单 = order_number 且 lock_time 非空 · 大区 = parent_region_name 归一到新架构 · 窗口 {res['window_start'].strftime('%Y-%m-%d')} → {res['window_end'].strftime('%Y-%m-%d')}</p>
  </section>
  <section class="summary-grid">
    <div class="summary-card"><div class="summary-value" style="color:{ZH['own']}">{total}</div>
      <div class="summary-label">窗口锁单合计</div><div class="summary-hint">近 {days} 天 全车系</div></div>
    <div class="summary-card"><div class="summary-value" style="color:{ZH['ash']}">{res['n_regions']}</div>
      <div class="summary-label">大区数（归一后）</div><div class="summary-hint">含 虚拟大区 / 未知</div></div>
    <div class="summary-card"><div class="summary-value" style="color:{ZH['ash']}">{res['n_series']}</div>
      <div class="summary-label">有效车系</div><div class="summary-hint">LS7/L7 近窗口近零已滤除</div></div>
    <div class="summary-card"><div class="summary-value" style="color:{ZH['event']}">{len(strong)}</div>
      <div class="summary-label">强偏好格（LQ≥{1 + lq_threshold:.2f}）</div><div class="summary-hint">锁单 ≥ {min_count}</div></div>
  </section>
  <section class="report-section">
    <h2 class="section-title">大区 × 车系 偏好热力（LQ）</h2>
    <div class="chart-box">{chart}</div>
    <p class="section-note">LQ = 区域占比 / 全局占比：&gt;1 该地区该车系偏好高于平均，&lt;1 低于平均。格子数字为锁单数。{'注：' + noted + '样本量小，参考为宜。' if noted else ''}</p>
  </section>
  <section class="report-section">
    <h2 class="section-title">强偏好组合（LQ ≥ {1 + lq_threshold:.2f}、锁单 ≥ {min_count}）</h2>
    <table class="report-table">
      <thead><tr><th>大区</th><th>车系</th><th>锁单</th><th>区域占比</th><th>全局占比</th><th>LQ</th></tr></thead>
      <tbody>{strong_rows or '<tr><td colspan="6" class="section-note">无</td></tr>'}</tbody>
    </table>
  </section>
  <section class="report-section">
    <h2 class="section-title">弱偏好组合（LQ ≤ {1 - lq_threshold:.2f}、锁单 ≥ {min_count}）</h2>
    <table class="report-table">
      <thead><tr><th>大区</th><th>车系</th><th>锁单</th><th>区域占比</th><th>全局占比</th><th>LQ</th></tr></thead>
      <tbody>{weak_rows or '<tr><td colspan="6" class="section-note">无</td></tr>'}</tbody>
    </table>
    <p class="section-note">弱偏好 = 该地区该车系占比显著低于全局，提示结构性冷区（如上海区对 LS9、北方对 L6、华东对 LS9）。</p>
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
    res = analyze(df, args.days, args.min_count, args.lq_threshold)
    fig = make_figure(res, args.min_count)
    html = render_html(fig, res, args.days, args.min_count, args.lq_threshold)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    print(f"✅ 已生成: {out}")
    print(f"   窗口 {res['window_start'].strftime('%Y-%m-%d')} → {res['window_end'].strftime('%Y-%m-%d')} | 锁单 {res['total']:,} | 大区 {res['n_regions']} | 车系 {res['n_series']}")
    top = res["strong"][0] if res["strong"] else None
    if top:
        print(f"   最强偏好: {top['region']} × {top['series']}  LQ={top['lq']:.2f}（区域占比 {top['row_share']:.1f}% vs 全局 {top['global_share']:.1f}%，{top['count']:,} 单）")
    else:
        print("   未发现达到阈值的强偏好组合")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())