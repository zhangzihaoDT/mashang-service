#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
门店「线索 × 小订转化」四象限散点图

读 `outputs/tables/store_operation_observation.csv`（由 utility_scripts/store_operation_observation.py
生成），以「近7日下发线索」为 X、「小订/线索」为 Y，按中位数切四象限：
  高线索·高转化 / 高线索·低转化 / 低线索·高转化 / 低线索·低转化
输出品牌化 HTML 报告。

用法:
    python research_scripts/store_leads_intention_quadrant.py
    python research_scripts/store_leads_intention_quadrant.py --input outputs/tables/store_operation_observation.csv
    python research_scripts/store_leads_intention_quadrant.py --top-label 12
"""

from __future__ import annotations

import argparse
import csv
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

DEFAULT_INPUT = _WS_ROOT / "outputs" / "tables" / "store_operation_observation.csv"
DEFAULT_OUT = _WS_ROOT / "outputs" / "reports" / "store_leads_intention_quadrant.html"

# 四象限语义色（复用视觉体系 token）
Q_HH = ZH["own"]        # 高线索·高转化（放量且高效）
Q_HL = ZH["event"]      # 高线索·低转化（放量待提效）
Q_LH = ZH["positive"]   # 低线索·高转化（高效小而美）
Q_LL = ZH["ash"]        # 低线索·低转化（待激活）
QUADRANTS = [
    ("高线索·高转化", Q_HH),
    ("高线索·低转化", Q_HL),
    ("低线索·高转化", Q_LH),
    ("低线索·低转化", Q_LL),
]


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description="门店 线索×小订转化 四象限散点图")
    p.add_argument("--input", default=str(DEFAULT_INPUT), help="观察 CSV 路径")
    p.add_argument("--output", default=str(DEFAULT_OUT), help="输出 HTML 路径")
    p.add_argument("--top-label", type=int, default=10, help="标注门店数（按线索降序，默认 10）")
    return p.parse_args(argv)


def load_data(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"❌ 找不到 {path}\n   请先运行：python utility_scripts/store_operation_observation.py --format csv")
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df["近7日下发线索"] = pd.to_numeric(df["近7日下发线索"], errors="coerce").fillna(0).astype(int)
    df["CM3小订"] = pd.to_numeric(df["CM3小订"], errors="coerce").fillna(0).astype(int)
    df["转化率"] = df["小订/线索"].str.rstrip("%").apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return df


def classify(df: pd.DataFrame) -> tuple[pd.DataFrame, float, float]:
    """按中位数切象限。返回 (df+象限, 线索中位, 转化中位)。"""
    active = df[df["近7日下发线索"] > 0]
    x_th = float(active["近7日下发线索"].median())
    y_th = float(active["转化率"].median())

    def q(r):
        hi_x = r["近7日下发线索"] >= x_th
        hi_y = r["转化率"] >= y_th
        return ("高线索·高转化" if hi_x and hi_y else
                "高线索·低转化" if hi_x else
                "低线索·高转化" if hi_y else "低线索·低转化")

    df = df.copy()
    df["象限"] = df.apply(q, axis=1)
    return df, x_th, y_th


def make_figure(df: pd.DataFrame, x_th: float, y_th: float, top_label: int) -> go.Figure:
    fig = go.Figure()

    # 对数 X 轴范围（左边界取正的最小值）
    pos = df.loc[df["近7日下发线索"] > 0, "近7日下发线索"]
    x_lo = max(0.8, float(pos.min()) * 0.8) if not pos.empty else 0.8
    x_max = float(pos.max()) * 1.1 if not pos.empty else 1.0
    y_max = float(df["转化率"].max()) * 1.15 or 1

    # 象限底纹
    for name, color, (x0, x1, y0, y1) in [
        ("高线索·高转化", Q_HH, (x_th, x_max, y_th, y_max)),
        ("高线索·低转化", Q_HL, (x_th, x_max, 0, y_th)),
        ("低线索·高转化", Q_LH, (x_lo, x_th, y_th, y_max)),
        ("低线索·低转化", Q_LL, (x_lo, x_th, 0, y_th)),
    ]:
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      fillcolor=f"rgba({r},{g},{b},0.06)", line_width=0, layer="below")

    # 各象限散点
    for name, color in QUADRANTS:
        sub = df[df["象限"] == name]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["近7日下发线索"].tolist(), y=sub["转化率"].tolist(), mode="markers", name=f"{name}（{len(sub)}）",
            marker=dict(color=color, size=9, opacity=0.8, line=dict(width=0.5, color="#FFFFFF")),
            customdata=sub[["门店", "门店类型", "CM3小订", "小订/线索"]].values.tolist(),
            hovertemplate=("<b>%{customdata[0]}</b><br>类型：%{customdata[1]}"
                           "<br>近7日下发线索：%{x}<br>CM3小订：%{customdata[2]}"
                           "<br>小订/线索：%{customdata[3]}<extra></extra>"),
        ))

    # 中位参考线
    fig.add_vline(x=x_th, line=dict(color=ZH["ash"], width=1, dash="dash"))
    fig.add_hline(y=y_th, line=dict(color=ZH["ash"], width=1, dash="dash"))

    # 象限角标（paper 坐标，固定在四角）
    for name, color, (px, py, ha, va) in [
        ("高线索·高转化", Q_HH, (0.99, 0.985, "right", "top")),
        ("高线索·低转化", Q_HL, (0.99, 0.015, "right", "bottom")),
        ("低线索·高转化", Q_LH, (0.01, 0.985, "left", "top")),
        ("低线索·低转化", Q_LL, (0.01, 0.015, "left", "bottom")),
    ]:
        cnt = int((df["象限"] == name).sum())
        fig.add_annotation(x=px, y=py, xref="paper", yref="paper",
                           text=f"<b>{name}</b>  {cnt} 家", showarrow=False,
                           xanchor=ha, yanchor=va, font=dict(color=color, size=12),
                           bgcolor="rgba(255,255,255,0.75)")

    # 标注 top 门店（按线索降序；用 text trace 稳定渲染）
    top = df[df["近7日下发线索"] > 0].nlargest(top_label, "近7日下发线索")
    fig.add_trace(go.Scatter(
        x=top["近7日下发线索"].tolist(), y=top["转化率"].tolist(), mode="text",
        text=top["门店"].tolist(), textposition="top center",
        textfont=dict(size=9, color="#6B7C8F"), showlegend=False, hoverinfo="skip",
    ))

    apply_zh_theme(fig)
    fig.update_xaxes(type="log", title_text="近7日下发线索（条，对数轴）")
    fig.update_yaxes(title_text="小订/线索（%）", rangemode="tozero")
    fig.update_layout(
        height=680, margin=dict(l=60, r=30, t=20, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, font=dict(size=11)),
        hovermode="closest",
    )
    return fig


def _table(df: pd.DataFrame) -> str:
    rows = []
    for name, color in QUADRANTS:
        sub = df[df["象限"] == name].sort_values("近7日下发线索", ascending=False)
        ex = "、".join(sub["门店"].head(4).tolist()) if not sub.empty else "—"
        rows.append(
            f'<tr><td><span class="badge" style="border-color:{color};color:{color}">{name}</span></td>'
            f'<td class="num">{len(sub)}</td>'
            f'<td class="num">{sub["近7日下发线索"].sum():,}</td>'
            f'<td class="num">{sub["CM3小订"].sum():,}</td>'
            f'<td style="color:#6B7C8F;font-size:12px">{ex}</td></tr>'
        )
    return "\n".join(rows)


def render_html(fig: go.Figure, df: pd.DataFrame, x_th: float, y_th: float) -> str:
    static = "../.."
    chart = fig.to_html(full_html=False, include_plotlyjs=False, div_id="quad",
                        config={"displayModeBar": False, "responsive": True})
    active = df[df["近7日下发线索"] > 0]
    kpi = [
        ("全门店", f"{len(df):,}", "含 0 线索门店", ZH["own"]),
        ("有线索门店", f"{len(active):,}", f"近7日下发线索 > 0", ZH["own"]),
        ("线索中位（切分）", f"{x_th:,.0f}", "高/低线索分界", ZH["ash"]),
        ("转化中位（切分）", f"{y_th:.1f}%", "小订/线索中位", ZH["ash"]),
    ]
    cards = "\n".join(
        f'<div class="summary-card"><div class="summary-value" style="color:{c}">{v}</div>'
        f'<div class="summary-label">{k}</div><div class="summary-hint">{h}</div></div>'
        for k, v, h, c in kpi
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>门店 线索×小订转化 四象限 | Raccoon Research</title>
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
    <h1>门店「线索 × 小订转化」四象限</h1>
    <p>数据源：<code>outputs/tables/store_operation_observation.csv</code> · 近7日下发线索 / CM3 留存小订（预售开放起未退）· 按中位数切分四象限</p>
  </section>
  <section class="summary-grid">
    {cards}
  </section>
  <section class="report-section">
    <h2 class="section-title">线索量 × 转化率分布</h2>
    <div class="chart-box">{chart}</div>
    <p class="section-note">X=近7日下发线索（条），Y=小订/线索（%）。虚线为中位数（X={x_th:,.0f}，Y={y_th:.1f}%）。点按象限着色，标注线索量 Top{min(10, len(active))} 门店。</p>
  </section>
  <section class="report-section">
    <h2 class="section-title">四象限汇总</h2>
    <table class="report-table">
      <thead><tr><th>象限</th><th class="num">门店数</th><th class="num">线索合计</th><th class="num">CM3小订合计</th><th>代表门店</th></tr></thead>
      <tbody>{_table(df)}</tbody>
    </table>
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
    df = load_data(Path(args.input))
    df, x_th, y_th = classify(df)
    fig = make_figure(df, x_th, y_th, args.top_label)
    html = render_html(fig, df, x_th, y_th)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    counts = df["象限"].value_counts().to_dict()
    print(f"✅ 已生成: {out}")
    print(f"   门店 {len(df)} 家 | 切分 X中位={x_th:.0f}, Y中位={y_th:.1f}%")
    for name, _ in QUADRANTS:
        print(f"   {name}: {counts.get(name, 0)} 家")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
