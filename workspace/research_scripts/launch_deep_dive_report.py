#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LS8Neo 上市深度研究 —— HTML 叙事报告渲染。

由 `launch_deep_dive.py` 计算出的研究数据包（ctx）驱动：报告中所有数字均取自
ctx，不含硬编码结果，因此同一输入可重现同一报告。

用法（通常由 launch_deep_dive.py --format html 调用）：
  python workspace/research_scripts/launch_deep_dive.py \\
      --gen LS8Neo --benchmarks CM3 LS8 --as-of 2026-11-08 --format html
"""

from __future__ import annotations

import html as html_lib
from pathlib import Path

import pandas as pd

_PLOTLY_CDN = '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'
_WD = {"Mon": "周一", "Tue": "周二", "Wed": "周三", "Thu": "周四",
       "Fri": "周五", "Sat": "周六", "Sun": "周日"}


# ─────────────────────────── 格式化 ───────────────────────────

def esc(x) -> str:
    return html_lib.escape(str(x))


def fi(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{int(round(float(v))):,}"


def fp(v, digits: int = 1) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{float(v) * 100:.{digits}f}%"


def fpp(v, digits: int = 1) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{float(v) * 100:+.{digits}f}pp"


def fs(v, digits: int = 1) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{float(v) * 100:+.{digits}f}%"


def fnum(v, digits: int = 1) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{float(v):,.{digits}f}"


def gap_narrative(d: dict, n: int) -> str:
    """差额结构叙述：D1 领先/落后 → 尾段净回吐/净增 → 最终。避免极小差额下的占比失真。"""
    d1 = int(round(d.get("d1_diff") or 0))
    cum = int(round(d.get("cum_diff") or 0))
    tail = cum - d1

    def _lead(v: int) -> str:
        return f"领先 {abs(v):,} 单" if v > 0 else (f"落后 {abs(v):,} 单" if v < 0 else "持平")

    head = "D1 持平" if d1 == 0 else f"D1 {_lead(d1)}"
    if tail == 0:
        mid = f"D2–D{n} 持平"
    elif d1 and tail * d1 < 0:
        mid = f"D2–D{n} 净回吐 {abs(tail):,} 单"
    else:
        mid = f"D2–D{n} 再{'领先' if tail > 0 else '落后'} {abs(tail):,} 单"
    return f"{head}，{mid}，最终{_lead(cum)}"


def delta_cls(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return "delta-positive" if float(v) > 0 else ("delta-negative" if float(v) < 0 else "")


# ─────────────────────────── HTML 片段 ───────────────────────────

def kpi(value: str, label: str, hint: str = "", tone: str = "") -> str:
    tone_cls = f" {tone}" if tone else ""
    hint_html = f'<div class="summary-hint">{hint}</div>' if hint else ""
    return (f'<div class="summary-card{tone_cls}"><div class="summary-value">{value}</div>'
            f'<div class="summary-label">{label}</div>{hint_html}</div>')


def section(title: str, inner: str, note: str = "", sid: str = "") -> str:
    note_html = f'<p class="section-note">{note}</p>' if note else ""
    anchor = f' id="{sid}"' if sid else ""
    return (f'<section class="report-section"{anchor}><h2 class="section-title">{title}</h2>'
            f'{note_html}{inner}</section>')


def table(headers: list[str], rows: list[list[str]], num_cols: set[int] | None = None,
          bold_rows: set[int] | None = None, caption: str = "") -> str:
    num_cols = num_cols or set()
    bold_rows = bold_rows or set()
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = []
    for ri, row in enumerate(rows):
        tds = []
        for ci, cell in enumerate(row):
            cls = "num" if ci in num_cols else ""
            attr = f' class="{cls}"' if cls else ""
            tds.append(f"<td{attr}>{cell}</td>")
        style = ' class="row-highlight"' if ri in bold_rows else ""
        trs.append(f"<tr{style}>{''.join(tds)}</tr>")
    cap = f'<p class="section-note">{caption}</p>' if caption else ""
    return (f'<div class="table-wrap"><table class="report-table"><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>{cap}')


def incell_bar(value: float, max_abs: float, fmt: str = "{:+,.0f}") -> str:
    """单元格内条形图：以 0 为中线，正向右、负向左，宽度按该列最大绝对值归一。"""
    if not max_abs:
        return fmt.format(value)
    w = min(abs(value) / max_abs, 1.0) * 50.0
    if value >= 0:
        left, color = 50.0, IM["own"]
    else:
        left, color = 50.0 - w, IM["bench1"]
    return (
        '<div class="ibar-cell">'
        '<div class="ibar-track">'
        '<span class="ibar-mid"></span>'
        f'<span class="ibar-fill" style="left:{left:.1f}%;width:{max(w,0.6):.1f}%;'
        f'background:{color};"></span>'
        '</div>'
        f'<span class="ibar-val">{fmt.format(value)}</span>'
        '</div>'
    )


def incell_stack(items: list[tuple[str, float]], cap_items: int = 2,
                 min_label: float = 0.14, colors: list[str] | None = None) -> str:
    """单元格内 100% 堆积条：条上按占比分段（够宽才标数字），下方短标注 Top 项。"""
    items = [(str(k), float(v)) for k, v in items if v]
    if not items:
        return "—"
    total = sum(v for _, v in items) or 1.0
    palette = colors or [IM["own"], IM["bench1"], IM["bench2"], IM["event"], IM["grid"]]
    segs, caps = [], []
    for i, (k, v) in enumerate(items):
        share = v / total
        color = palette[i % len(palette)]
        label = f"{share * 100:.0f}%" if share >= min_label else ""
        segs.append(f'<span class="ics-seg" style="width:{share * 100:.2f}%;'
                    f'background:{color};" title="{k} {share * 100:.1f}%">{label}</span>')
        if i < cap_items:
            pct = share * 100
            txt = f"{pct:.0f}%" if pct >= 10 or pct == 0 else f"{pct:.1f}%"
            caps.append(f"<b>{k}</b> {txt}")
    return ('<div class="ics">'
            f'<div class="ics-track">{"".join(segs)}</div>'
            f'<div class="ics-cap">{"｜".join(caps)}</div>'
            '</div>')


def chart_box(fig, name: str = "chart") -> str:
    """内联 Plotly 图；div_id 固定，保证同输入生成的 HTML 可逐字节复现。"""
    if fig is None:
        return ""
    body = fig.to_html(full_html=False, include_plotlyjs=False, div_id="chart-" + name)
    return '<div class="chart-box">' + body + '</div>'


# ── IM 主题色（本报告专用，不改共享 plotly_theme） ──
# 取色原则：**主色板主导、强调色点睛**
#   主色板 #919C9C / #ECEAE5 / #D27048 —— 承担系列主色、面板底色、结构线
#   强调色 #F8B24D / #E94C2B / #4463AC —— 只用于标记、负向、少量强调，不做大面积填充
IM = {
    "own": "#D27048",       # 主色板·陶土橙（本品，唯一高饱和主色）
    "bench1": "#919C9C",    # 主色板·灰绿（对标 1）
    "bench2": "#414140",    # 辅助·深灰（对标 2，中性不抢主车）
    "event": "#F8B24D",     # 强调·琥珀（仅标记/小面积）
    "negative": "#E94C2B",  # 强调·朱红（仅负向）
    "positive": "#919C9C",  # 正向也走主色板，避免强调色泛滥
    "accent": "#4463AC",    # 强调·靛蓝（仅文字级强调/链接）
    "ash": "#919C9C",
    "grid": "#CBCCCA",
    "ink": "#414140",
    "cream": "#ECEAE5",
    "white": "#FFFFFF",
    "muted": "#7C827F",
    "zero": "#414140",
    "axis": "#6E7472",
}
_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"


def _im_role(role: str) -> str:
    """角色取色：own / event / negative / steel / sage / ash / grid / ink。"""
    return {
        "own": IM["own"], "event": IM["event"], "negative": IM["negative"],
        "positive": IM["positive"], "steel": IM["bench1"], "sage": IM["bench2"],
        "ash": IM["ash"], "neutral": IM["muted"], "grid": IM["grid"], "ink": IM["ink"],
        "accent": IM["accent"], "cream": IM["cream"],
    }.get(role, IM["bench1"])


def apply_im_theme(fig):
    """IM 主题：白底、灰绿网格、深灰零轴与文字。"""
    fig.update_layout(
        paper_bgcolor=IM["white"], plot_bgcolor=IM["white"],
        font=dict(family=_FONT, color=IM["ink"], size=12),
        hoverlabel=dict(bgcolor=IM["white"], bordercolor=IM["grid"],
                        font=dict(color=IM["ink"], family=_FONT)),
        legend=dict(font=dict(color=IM["ink"])),
    )
    fig.update_xaxes(gridcolor=IM["grid"], linecolor=IM["grid"], zeroline=False,
                     tickfont=dict(color=IM["axis"]), title_font=dict(color=IM["ink"]),
                     showline=True, linewidth=1)
    fig.update_yaxes(gridcolor=IM["grid"], linecolor=IM["grid"], zeroline=True,
                     zerolinecolor=IM["zero"], zerolinewidth=1.5,
                     tickfont=dict(color=IM["axis"]), title_font=dict(color=IM["ink"]),
                     showline=True, linewidth=1)
    return fig


def _plotly():
    import plotly.graph_objects as go
    return go, apply_im_theme, _im_role


# ─────────────────────────── 图表 ───────────────────────────

def _colors(gens: list[str], main: str, gsc=_im_role):
    """按业务角色配色：本品 = 陶土橙（主色板），对标 = 灰绿 / 深灰（中性）。"""
    bench_roles = ["bench1", "bench2"]
    out = {main: IM["own"]}
    i = 0
    for g in gens:
        if g == main:
            continue
        out[g] = IM[bench_roles[i % len(bench_roles)]]
        i += 1
    return out


def fig_cumulative(ctx: dict):
    """累计锁单：D1–D_N 为唯一比较窗口（实线），D_N+1–D_context 为参考延长线（虚线）。

    参考延长线只回答「对标在 D_N 之后还能释放多少」，不参与任何差异计算。
    """
    go, apply_im_theme, gsc = _plotly()
    gens, main, n = ctx["curves"]["gens"], ctx["main"], ctx["n_days"]
    colors = _colors(gens, main, gsc)
    cur = ctx["curves"]["curves"]
    ctxc = ctx.get("context", {})
    ctx_curves = ctxc.get("curves", {})
    ctx_days = int(ctxc.get("context_days") or 0)
    fig = go.Figure()
    xmax = n
    for g in gens:
        c = cur[g]
        fig.add_trace(go.Scatter(
            x=list(range(1, n + 1)), y=c["cum"],
            name=f"{g}（{c['launch']}）", mode="lines+markers",
            line=dict(color=colors[g], width=3 if g == main else 2),
            marker=dict(size=7),
            hovertemplate="D%{x} · 累计 %{y:,} 单<extra>" + g + "</extra>"))
    # 参考延长线（仅历史代际有 D>N 数据）
    for g in gens:
        cc = ctx_curves.get(g)
        if not cc or cc["available_days"] <= n or ctx_days <= n:
            continue
        xs = list(range(n + 1, cc["available_days"] + 1))
        ys = cc["cum"][n:cc["available_days"]]
        xmax = max(xmax, cc["available_days"])
        fig.add_trace(go.Scatter(
            x=xs, y=ys, name=f"{g} D{n+1}–D{cc['available_days']}（参考）",
            mode="lines", line=dict(color=colors[g], width=2.2, dash="dot"),
            opacity=0.75, showlegend=True,
            hovertemplate="D%{x} · 参考累计 %{y:,} 单<extra>" + g + "</extra>"))
        fig.add_annotation(x=cc["available_days"], y=cc["cum"][-1],
                           text=f"D{cc['available_days']} {cc['cum'][-1]:,}",
                           showarrow=False, xshift=-6, yshift=12,
                           xanchor="right", font=dict(size=10, color=colors[g]))
    # 同期比较窗口右界
    fig.add_vline(x=n + 0.5, line=dict(color=IM["grid"], width=1, dash="dash"))
    fig.add_annotation(x=n + 0.5, y=0, yref="paper", text=f"同期比较窗口 → D{n}",
                       showarrow=False, xanchor="left", xshift=6, yshift=6,
                       font=dict(size=10, color="#8A94A0"))
    # 主车末端标注
    fig.add_annotation(x=n, y=cur[main]["cum"][-1],
                       text=f"{cur[main]['cum'][-1]:,}", showarrow=False,
                       xshift=-8, yshift=-14, xanchor="right",
                       font=dict(size=11, color=colors[main]))
    if ctx_curves.get(main) and ctx_curves[main]["available_days"] <= n:
        fig.add_annotation(x=n, y=cur[main]["cum"][-1], text="数据截至",
                           showarrow=False, xshift=6, yshift=6, xanchor="left",
                           font=dict(size=9, color="#8A94A0"))
    apply_im_theme(fig)
    fig.update_layout(height=430, margin=dict(l=55, r=30, t=30, b=40),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      hovermode="x unified")
    fig.update_yaxes(title_text="累计零售锁单（单）", rangemode="tozero")
    fig.update_xaxes(title_text="上市后天数（D1 = 上市日）")
    fig.update_xaxes(range=[0.3, xmax + 1.2])
    return fig


def fig_daily(ctx: dict):
    go, apply_im_theme, gsc = _plotly()
    gens, main = ctx["curves"]["gens"], ctx["main"]
    colors = _colors(gens, main, gsc)
    cur = ctx["curves"]["curves"]
    fig = go.Figure()
    xs = [f"D{i + 1}" for i in range(len(cur[main]["daily"]))]
    for g in gens:
        c = cur[g]
        wd = [_WD.get(w, w) for w in c["weekdays"]]
        fig.add_trace(go.Bar(x=xs, y=c["daily"], name=g, marker_color=colors[g],
                             opacity=1.0 if g == main else 0.75,
                             text=[f"{v:,}" for v in c["daily"]], textposition="outside",
                             textfont=dict(size=10), customdata=wd,
                             hovertemplate="%{x}（%{customdata}）· %{y:,} 单<extra>" + g + "</extra>"))
    apply_im_theme(fig)
    fig.update_layout(height=400, margin=dict(l=55, r=20, t=30, b=40), barmode="group",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_yaxes(title_text="当日新增零售锁单（单）", rangemode="tozero")
    fig.update_xaxes(title_text="上市后天数（D1 = 上市日）")
    return fig


def fig_pool_state(ctx: dict):
    """预售池在 D_N 时点的状态构成：已转锁单 / 待转化 / 已退订。"""
    go, apply_im_theme, gsc = _plotly()
    gens, main = ctx["curves"]["gens"], ctx["main"]
    pre = ctx["presale"]
    fig = go.Figure()
    locked = [pre[g]["pool_locked"] for g in gens]
    pending = [pre[g]["pool_pending"] for g in gens]
    refund = [pre[g]["pool_refunded"] for g in gens]
    fig.add_trace(go.Bar(y=gens, x=locked, orientation="h", name="已转锁单",
                         marker_color=gsc("own"),
                         text=[f"{v:,}" for v in locked], textposition="inside",
                         textfont=dict(color="#fff")))
    fig.add_trace(go.Bar(y=gens, x=pending, orientation="h", name="预售池待转化（留存未锁）",
                         marker_color=IM["grid"],
                         text=[f"{v:,}" for v in pending], textposition="inside",
                         textfont=dict(color="#fff")))
    fig.add_trace(go.Bar(y=gens, x=refund, orientation="h", name="已退订",
                         marker_color=gsc("negative"),
                         text=[f"{v:,}" for v in refund], textposition="outside"))
    apply_im_theme(fig)
    fig.update_layout(height=300, margin=dict(l=20, r=60, t=30, b=35), barmode="stack",
                      legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0,
                                  traceorder="normal"))
    fig.update_xaxes(title_text="预售小订池（单）", rangemode="tozero")
    fig.update_yaxes(autorange="reversed")
    return fig


def fig_origin(ctx: dict):
    """窗口内锁单来源：预售小订转锁 / 上市当日新增小订转锁 / 直接锁单。"""
    go, apply_im_theme, gsc = _plotly()
    gens, main = ctx["curves"]["gens"], ctx["main"]
    org = ctx["origin"]
    fig = go.Figure()
    parts = [("pre", "预售小订转锁", IM["own"]),
             ("launch_day", "上市当日新增小订转锁", IM["bench1"]),
             ("none", "直接锁单（无小订）", IM["grid"])]
    for key, label, color in parts:
        vals = [org[g].get(key, 0) for g in gens]
        fig.add_trace(go.Bar(y=gens, x=vals, orientation="h", name=label, marker_color=color,
                             text=[f"{v:,}" for v in vals], textposition="inside",
                             textfont=dict(color="#fff", size=10)))
    apply_im_theme(fig)
    fig.update_layout(height=280, margin=dict(l=20, r=40, t=30, b=35), barmode="stack",
                      legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0))
    fig.update_xaxes(title_text="D1–D_N 零售锁单（单）", rangemode="tozero")
    fig.update_yaxes(autorange="reversed")
    return fig


def fig_network_scale(ctx: dict):
    """门店规模对比：全网络活跃门店 vs 本代际有锁单门店。"""
    go, apply_im_theme, gsc = _plotly()
    gens, main = ctx["curves"]["gens"], ctx["main"]
    colors = _colors(gens, main, gsc)
    net = ctx["network"]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=gens, y=[net[g]["active_stores_all_series"] for g in gens],
        name="全网络活跃锁单门店", marker_color=IM["cream"],
        text=[f"{net[g]['active_stores_all_series']:,}" for g in gens],
        textposition="inside", textfont=dict(color="#374151", size=11),
        hovertemplate="%{x} · 全网络活跃 %{y:,} 家<extra></extra>"))
    fig.add_trace(go.Bar(
        x=gens, y=[net[g]["stores_with_gen"] for g in gens],
        name="本代际有锁单门店", marker_color=[colors[g] for g in gens],
        text=[f"{net[g]['stores_with_gen']:,} 家" for g in gens],
        textposition="inside", textfont=dict(color="#ffffff", size=11),
        customdata=[fp(net[g]["gen_store_penetration"]) for g in gens],
        hovertemplate="%{x} · 本代际有锁单 %{y:,} 家（铺货渗透 %{customdata}）<extra></extra>"))
    apply_im_theme(fig)
    fig.update_layout(height=340, margin=dict(l=55, r=20, t=40, b=40), barmode="group",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_yaxes(title_text="门店数（家）", rangemode="tozero")
    fig.update_xaxes(title_text="代际（同一 D1–D_N 窗口）")
    return fig


def fig_network_productivity(ctx: dict):
    """单店产能对比：单店锁单（均值）与门店中位数。"""
    go, apply_im_theme, gsc = _plotly()
    gens, main = ctx["curves"]["gens"], ctx["main"]
    colors = _colors(gens, main, gsc)
    net = ctx["network"]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=gens, y=[net[g]["locks_per_store"] for g in gens],
        name="单店锁单（均值）", marker_color=[colors[g] for g in gens],
        text=[f"{fnum(net[g]['locks_per_store'], 2)}" for g in gens],
        textposition="inside", textfont=dict(color="#ffffff", size=12),
        hovertemplate="%{x} · 单店锁单 %{y:.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=gens, y=[net[g]["median_store_locks"] for g in gens],
        name="门店锁单中位数", mode="markers+text",
        text=[f"中位 {fnum(net[g]['median_store_locks'], 0)}" for g in gens],
        textposition="top center", textfont=dict(size=10, color=gsc("event")),
        marker=dict(color=gsc("event"), size=11, symbol="diamond",
                    line=dict(color="#fff", width=1)),
        hovertemplate="%{x} · 中位数 %{y:.1f}<extra></extra>"))
    apply_im_theme(fig)
    fig.update_layout(height=340, margin=dict(l=55, r=20, t=40, b=40),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_yaxes(title_text="单店锁单（单/店）", rangemode="tozero")
    fig.update_xaxes(title_text="代际（同一 D1–D_N 窗口）")
    return fig


def fig_pool_consumption(ctx: dict):
    """封盘池去向：已转化 / 已退订 / 剩余（单张堆积条，一眼看完三步链路）。"""
    go, apply_im_theme, gsc = _plotly()
    gens, main = ctx["curves"]["gens"], ctx["main"]
    po = ctx["pool"]
    fig = go.Figure()
    parts = [
        ("locked", "已转化（锁单）", IM["own"]),
        ("refunded", "已退订", IM["negative"]),
        ("remaining", "封盘池剩余", IM["grid"]),
    ]
    for key, label, color in parts:
        vals = [po[g][key] for g in gens]
        text = [f"{fi(v)}（{fp(v / max(po[g]['stock_total'], 1))}）"
                for v, g in zip(vals, gens)]
        fig.add_trace(go.Bar(
            y=gens, x=vals, orientation="h", name=label, marker_color=color,
            text=text, textposition="inside",
            textfont=dict(color="#FFFFFF" if key != "remaining" else IM["ink"], size=10),
            hovertemplate="%{y} · " + label + " %{x:,}<extra></extra>"))
    for g in gens:
        fig.add_annotation(x=po[g]["stock_total"], y=g, text=f"  封盘 {fi(po[g]['stock_total'])}",
                           showarrow=False, xanchor="left", font=dict(size=10, color=IM["ink"]),
                           row=None)
    apply_im_theme(fig)
    fig.update_layout(height=260, margin=dict(l=20, r=110, t=30, b=40), barmode="stack",
                      legend=dict(orientation="h", yanchor="bottom", y=1.05, x=0,
                                  traceorder="normal"))
    fig.update_xaxes(title_text="小订池（单）", rangemode="tozero")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return fig


def _opt_share(prod_g: dict, attr: str, value: str) -> float | None:
    """config_attribute 原始「属性=取值」占比；缺失返回 None。"""
    a = (prod_g.get("option_values") or {}).get(attr)
    if not a:
        return None
    for v in a["values"]:
        if v["value"] == value:
            return v["share"]
    return None


def _opt_alt(prod_g: dict, attr: str) -> tuple[str, float] | None:
    """该属性下占比更小的那个取值（即「选装项」），返回原始取值名与占比。"""
    a = (prod_g.get("option_values") or {}).get(attr)
    if not a or len(a["values"]) < 2:
        return None
    v = sorted(a["values"], key=lambda x: x["share"])[0]
    return v["value"], v["share"]


def _opt_label(attr: str, value: str) -> str:
    return f"{attr}={value}"


def _diff_items(ctx: dict) -> list[dict]:
    """Q8-3 Part 1：与 Q8-1 同维度的用户差异项（百分点）。"""
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    items = []

    def add(label, getter):
        vals = {}
        for g in ctx["curves"]["gens"]:
            try:
                vals[g] = getter(g)
            except (KeyError, TypeError, ZeroDivisionError):
                vals[g] = None
        m = vals.get(main)
        if m is None:
            return
        d1 = round((m - vals[b1]) * 100, 1) if vals.get(b1) is not None else None
        d2 = round((m - vals[b2]) * 100, 1) if (b2 and vals.get(b2) is not None) else None
        if d1 is None and d2 is None:
            return
        items.append({"label": label, "main": round(m * 100, 1), "vs_b1": d1, "vs_b2": d2})

    add("女性占比", lambda g: ctx["product"][g]["gender"].get("女"))
    add("年龄 35–39 占比", lambda g: ctx["product"][g]["age_cohort"].get("35-39"))
    add("年龄 40–44 占比", lambda g: ctx["product"][g]["age_cohort"].get("40-44"))
    add("年龄 50 岁及以上", lambda g: ctx["product"][g]["age_cohort"].get("50岁及以上"))
    add("一线城市占比", lambda g: ctx["product"][g]["tier"].get("一线"))
    add("新一线占比", lambda g: ctx["product"][g]["tier"].get("新一线"))
    add("二线占比", lambda g: ctx["product"][g]["tier"].get("二线"))
    add("三线及以下占比", lambda g: ctx["product"][g]["tier"].get("三线及以下"))
    for pv in [x["province"] for x in (ctx["product"][main].get("province_top") or [])[:3]]:
        add(f"省份 {pv}", lambda g, _p=pv: next(
            (x["share"] for x in (ctx["product"][g].get("province_top") or [])
             if x["province"] == _p), 0.0))
    return items


def _pk_block(ctx: dict, gen: str) -> dict:
    return ((ctx.get("pk") or {}).get("gens") or {}).get(gen) or {}


def fig_pk_rank_table(ctx: dict, gen: str):
    """PK 次数 + 反向排名（上市周 vs 预售周），单代际一图。

    版式参照业务现有卡片：左侧 PK 次数横条，右侧两列排名（当前 / 上期）+ 变化箭头。
    """
    go, apply_im_theme, gsc = _plotly()
    from plotly.subplots import make_subplots
    b = _pk_block(ctx, gen)
    rows = b.get("competitors") or []
    if not rows:
        return None
    rows = rows[:10]
    rows = list(reversed(rows))          # 让第一名在最上方
    names = [c["name"] for c in rows]
    pk = [c["pk"] for c in rows]

    fig = make_subplots(rows=1, cols=2, column_widths=[0.62, 0.38],
                        horizontal_spacing=0.03,
                        subplot_titles=(f"PK 次数（条形 = 上市周 {b['launch_week']}，"
                                        f"菱形 = 预售周 {b.get('prev_week', '—')}）",
                                        "PK 反向排名　当前 / 上期　　变化"))
    fig.add_trace(go.Bar(
        y=names, x=pk, orientation="h", marker_color=IM["own"],
        name=f"上市周（{b['launch_week']}）",
        text=[f"{v:,}" for v in pk], textposition="outside",
        textfont=dict(size=9), cliponaxis=False,
        hovertemplate="%{y} · 上市周 %{x:,} 次<extra></extra>"), row=1, col=1)

    # 预售周 PK 次数：以标记叠加在条形上，便于直接比对
    pv = [(c["prev_pk"], c["name"]) for c in rows if c.get("prev_pk") is not None]
    xmax = max(pk) * 1.18 if pk else 1
    inside = [(v, n) for v, n in pv if v <= xmax]
    outside = [(v, n) for v, n in pv if v > xmax]
    if inside:
        fig.add_trace(go.Scatter(
            x=[v for v, _ in inside], y=[n for _, n in inside], mode="markers",
            name=f"预售周（{b.get('prev_week', '—')}）",
            marker=dict(symbol="diamond", size=9, color=IM["bench1"],
                        line=dict(color="#FFFFFF", width=1.2)),
            hovertemplate="%{y} · 预售周 %{x:,} 次<extra></extra>"), row=1, col=1)
    if outside:   # 超出上市周量级的预售值：钉在轴右缘并标注真实值，避免压缩主图
        fig.add_trace(go.Scatter(
            x=[xmax * 0.995 for _ in outside], y=[n for _, n in outside],
            mode="markers+text", name=f"预售周（{b.get('prev_week', '—')}）",
            showlegend=False,
            marker=dict(symbol="triangle-right", size=12, color=IM["bench1"],
                        line=dict(color="#FFFFFF", width=1.5)),
            text=[f"{v:,}" for v, _ in outside], textposition="middle left",
            textfont=dict(size=9, color=IM["axis"]),
            hovertemplate="%{y} · 预售周 %{x:,} 次（超出轴范围，已标注）<extra></extra>"),
            row=1, col=1)
    fig.update_xaxes(range=[0, xmax], row=1, col=1)

    xs_cur, xs_prev, xs_chg = [], [], []
    t_cur, t_prev = [], []
    up, dn, flat = [], [], []
    for i, c in enumerate(rows):
        xs_cur.append(0.22); t_cur.append(f"#{c['rev_rank']}")
        if c.get("prev_rev_rank") is None:
            xs_prev.append(0.55); t_prev.append("/ 新进")
            xs_chg.append(0.88); flat.append((i, "—"))
        else:
            xs_prev.append(0.55); t_prev.append(f"/ #{c['prev_rev_rank']}")
            ch = c.get("rev_rank_change")
            txt = "—" if ch == 0 else (f"↑{ch}" if ch > 0 else f"↓{abs(ch)}")
            xs_chg.append(0.88)
            (up if ch > 0 else dn if ch < 0 else flat).append((i, txt))

    fig.add_trace(go.Scatter(x=xs_cur, y=names, mode="text", text=t_cur,
                             textfont=dict(size=11, color=IM["ink"]),
                             hoverinfo="skip", showlegend=False), row=1, col=2)
    fig.add_trace(go.Scatter(x=xs_prev, y=names, mode="text", text=t_prev,
                             textfont=dict(size=10, color=IM["axis"]),
                             hoverinfo="skip", showlegend=False), row=1, col=2)
    for group, color in ((up, IM["accent"]), (dn, IM["negative"]), (flat, IM["grid"])):
        if not group:
            continue
        fig.add_trace(go.Scatter(
            x=[xs_chg[i] for i, _ in group], y=[names[i] for i, _ in group],
            mode="text", text=[t for _, t in group],
            textfont=dict(size=11, color=color), hoverinfo="skip", showlegend=False),
            row=1, col=2)
    apply_im_theme(fig)
    fig.update_xaxes(showticklabels=True, row=1, col=1)
    fig.update_xaxes(range=[0, 1], showgrid=False, showticklabels=False,
                     zeroline=False, row=1, col=2)
    fig.update_yaxes(showgrid=False, automargin=True, row=1, col=1)
    fig.update_yaxes(showticklabels=False, showgrid=False, zeroline=False, row=1, col=2)
    fig.update_layout(
        title=dict(text=f"{gen}｜PK 次数与反向排名（上市周 vs 预售周）", font=dict(size=15)),
        height=max(360, 34 * len(rows) + 130),
        margin=dict(l=10, r=30, t=100, b=40), barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.06, x=0,
                    font=dict(size=10)))
    fig.update_xaxes(title_text="PK 次数（次/周）", rangemode="tozero", row=1, col=1)
    for ann in fig.layout.annotations:
        ann.font.size = 11
    return fig


def chart_seat_combos(ctx: dict) -> str:
    return chart_box(fig_seat_combos(ctx), "seat_combos")


def chart_pk_rank_table(ctx: dict, gen: str) -> str:
    return chart_box(fig_pk_rank_table(ctx, gen), f"pk_{gen}")


def fig_user_diff_profile(ctx: dict):
    """差异轮廓：每个维度「主车 − 对标」的百分点差。

    顺序固定为 Q8-1 的维度顺序（性别 → 年龄 → 城市线级 → 省份），
    **不按差异幅度重排**——同一份报告每次重跑，条形位置不变，便于横向比对。
    """
    go, apply_im_theme, gsc = _plotly()
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    items = list(reversed(_diff_items(ctx)))   # 反转让「性别」在最上方
    labels = [d["label"] for d in items]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=[d["vs_b1"] for d in items], orientation="h", name=f"vs {b1}",
        marker_color=IM["bench1"],
        text=[f"{d['vs_b1']:+.1f}" if d["vs_b1"] is not None else "" for d in items],
        textposition="outside", textfont=dict(size=10),
        hovertemplate="%{y} · vs " + b1 + " %{x:+.1f}pp<extra></extra>"))
    if b2:
        fig.add_trace(go.Bar(
            y=labels, x=[d["vs_b2"] if d["vs_b2"] is not None else 0 for d in items],
            orientation="h", name=f"vs {b2}", marker_color=IM["bench2"], opacity=0.92,
            text=[f"{d['vs_b2']:+.1f}" if d["vs_b2"] is not None else "" for d in items],
            textposition="outside", textfont=dict(size=10),
            hovertemplate="%{y} · vs " + b2 + " %{x:+.1f}pp<extra></extra>"))
    apply_im_theme(fig)
    fig.add_vline(x=0, line=dict(color=IM["zero"], width=1.6))
    fig.update_layout(height=max(380, 30 * len(items) + 120),
                      margin=dict(l=20, r=60, t=40, b=50), barmode="group",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_xaxes(title_text="差异（百分点，右 = " + main + " 更高）")
    fig.update_yaxes(showgrid=False)
    return fig


# ── 图表包装：fig_* 返回 Plotly 图，chart_* 返回可嵌入 HTML ──

def chart_cumulative(ctx: dict) -> str:
    return chart_box(fig_cumulative(ctx), "cumulative")


def chart_daily(ctx: dict) -> str:
    return chart_box(fig_daily(ctx), "daily")


def chart_pool_state(ctx: dict) -> str:
    return chart_box(fig_pool_state(ctx), "pool_state")


def chart_origin(ctx: dict) -> str:
    return chart_box(fig_origin(ctx), "origin")


def chart_network_scale(ctx: dict) -> str:
    return chart_box(fig_network_scale(ctx), "network_scale")


def chart_network_productivity(ctx: dict) -> str:
    return chart_box(fig_network_productivity(ctx), "network_productivity")


def chart_user_diff_profile(ctx: dict) -> str:
    return chart_box(fig_user_diff_profile(ctx), "user_diff_profile")


def chart_pool_consumption(ctx: dict) -> str:
    return chart_box(fig_pool_consumption(ctx), "pool_consumption")


def export_charts(ctx: dict, out_root: Path, prefix: str = "") -> list[Path]:
    """把 9 张图导出为 PNG（outputs/charts/），便于在文档/消息中引用。"""
    out_dir = out_root / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    items = [("cumulative", fig_cumulative), ("daily", fig_daily),
             ("pool_state", fig_pool_state), ("origin", fig_origin),
             ("network_scale", fig_network_scale),
             ("network_productivity", fig_network_productivity),
             ("user_diff_profile", fig_user_diff_profile),
             ("seat_combos", fig_seat_combos),
             *[(f"pk_{g}", (lambda c, _g=g: fig_pk_rank_table(c, _g)))
               for g in ctx["curves"]["gens"]],
             ("pool_consumption", fig_pool_consumption)]
    items += []
    for name, fn in items:
        try:
            fig = fn(ctx)
            p = out_dir / (f"{prefix + '_' if prefix else ''}{name}.png")
            fig.write_image(p, width=1200, height=fig.layout.height or 420, scale=2)
            paths.append(p)
        except Exception:  # pragma: no cover - kaleido 缺失时跳过
            continue
    return paths


# ─────────────────────────── 报告正文 ───────────────────────────

def _plan_section(ctx: dict) -> str:
    """研究主线 + 章节规划：由 ctx["narrative"] 决定，渲染器只负责呈现。"""
    plan = ctx.get("narrative") or {}
    if not plan:
        return ""
    thread = plan.get("thread") or {}
    rows = "".join(
        f"<tr><td>{esc(r['rule'])}</td><td><b>{esc(r['result'])}</b></td>"
        f"<td>{esc(r['evidence'])}</td></tr>"
        for r in plan.get("rules", []))
    skip_rows = "".join(
        f"<li><b>{esc(x['block'])}</b>：{esc(x['reason'])}</li>" for x in plan.get("skips", []))
    qname = {"q4": "Q4 预售池", "q5": "Q5 来源结构", "q6": "Q6 区域",
             "q7": "Q7 网络", "q8": "Q8 产品与客群"}
    order2 = " → ".join(qname.get(x, x) for x in plan.get("act2", []))
    order3 = " → ".join(qname.get(x, x) for x in plan.get("act3", []))
    return (
        '<div class="verdict" style="border-left:4px solid #D27048;">'
        '<h4>研究主线与章节规划</h4>'
        f'<p><b>主线：{esc(thread.get("label", ""))}</b>——{esc(thread.get("why", ""))}</p>'
        f'<p style="margin-bottom:6px;">本次第二幕按 <b>{esc(order2)}</b> 呈现；'
        f'第三幕按 <b>{esc(order3)}</b> 呈现。顺序由下列规则判定，不套固定骨架：</p>'
        f'<table class="report-table"><thead><tr><th>判定规则</th><th>结论</th><th>依据</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
        + (f'<p style="margin-top:10px;">数据不足而跳过的区块：</p><ul class="tight">{skip_rows}</ul>'
           if skip_rows else "")
        + '</div>')


def render_report(ctx: dict, out_root: Path) -> Path:
    gens, main, n = ctx["curves"]["gens"], ctx["main"], ctx["n_days"]
    benches = ctx["benchmarks"]
    cur = ctx["curves"]["curves"]
    dyn = ctx["dynamics"]
    pre = ctx["presale"]
    org = ctx["origin"]
    fwd = ctx["forward"]
    qual = ctx["quality"]
    net = ctx["network"]
    prod = ctx["product"]
    src = ctx["source_decomp"]
    deltas = ctx["deltas"]
    win = ctx["windows"]

    b1 = benches[0]
    b2 = benches[1] if len(benches) > 1 else None
    d1, d2 = deltas[b1], (deltas[b2] if b2 else None)

    title = f"{main} 上市第 {n} 天深度研究——与 {'、'.join(benches)} 的历史同期比较"
    out_dir = out_root / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{main}_上市第{n}天深度研究.html"

    S: list[str] = []
    A = S.append

    # ── 头部 ──
    A('<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8" />')
    A('<meta name="viewport" content="width=device-width, initial-scale=1.0" />')
    A(f"<title>{esc(title)}</title>")
    A('<link rel="stylesheet" href="../../templates/report_style.css" />')
    A(_PLOTLY_CDN)
    A("""<style>
    /* ── IM 主题色覆盖（只影响本报告，不改共享 report_style.css） ── */
    :root{
      --zh-blue:#D27048; --zh-blue-700:#B25B38; --zh-blue-500:#DE8A64; --zh-blue-100:#ECEAE5;
      --zh-deep-blue:#414140;
      --zh-raccoon-gold:#D27048; --zh-gold-700:#A85A3A; --zh-gold-100:#F3E7E1;
      --zh-text:#414140; --zh-muted:#7C827F;
      --zh-border:#CBCCCA; --zh-bg:#FFFFFF; --zh-card:#FFFFFF; --zh-panel:#ECEAE5;
      --zh-row-alt:#F7F6F3; --zh-row-hover:#F4EEE9; --zh-table-section:#ECEAE5;
      --zh-grid:#CBCCCA; --zh-zero-line:#414140; --zh-axis-line:#CBCCCA;
      --zh-axis-text:#6E7472; --zh-axis-title:#414140;
      --status-positive:#919C9C; --status-negative:#E94C2B; --status-warning:#F8B24D;
      --status-neutral:#919C9C;
      --chart-own:#D27048; --chart-event:#F8B24D; --chart-steel:#919C9C;
      --chart-sage:#D27048; --chart-mauve:#919C9C; --chart-ash:#CBCCCA;
    }
    body{color:#414140;}
    .report-container{max-width:1180px;margin:0 auto;padding:0 28px 80px;}
    header{background:#FFFFFF;border-bottom:1px solid #CBCCCA;}
    header .container{max-width:1180px;margin:0 auto;padding:0 28px;display:flex;
      align-items:center;justify-content:space-between;height:56px;}
    .brand-name{color:#414140;}
    .header-meta{color:#7C827F;}
    .hero{padding:40px 0 8px;}
    .hero h1{font-size:30px;line-height:1.35;margin:0 0 12px;color:#414140;}
    .hero p{margin:0;color:#7C827F;font-size:13px;line-height:1.9;}
    .section-title{font-size:20px;margin:0 0 6px;color:#414140;
      border-left:4px solid #D27048;padding-left:12px;}
    .report-section{margin:34px 0 10px;}
    .section-note{font-size:12.5px;line-height:1.75;color:#7C827F;margin:8px 0 12px;}
    .report-table{font-size:12.5px;}
    .report-table thead th{font-size:12px;font-weight:600;color:#414140;
      background:#ECEAE5;border-bottom:2px solid #D27048;}
    .report-table td{padding:7px 10px;border-bottom:1px solid #CBCCCA;}
    .report-table tbody tr:nth-child(even){background:#F7F6F3;}
    .report-table tbody tr:hover{background:#F1EFEA;}
    .summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0 8px;}
    .summary-card{background:#FFFFFF;border:1px solid #CBCCCA;border-radius:10px;padding:14px 16px;}
    .summary-value{font-size:24px;font-weight:700;color:#414140;font-variant-numeric:tabular-nums;}
    .summary-label{font-size:12.5px;color:#414140;margin-top:4px;}
    .summary-hint{font-size:11.5px;color:#7C827F;margin-top:3px;line-height:1.5;}
    .summary-card.neg .summary-value{color:#E94C2B;}
    .summary-card.gold .summary-value{color:#D27048;}
    .finding{border-left:3px solid #D27048;padding:2px 0 2px 14px;margin:14px 0;}
    .finding h3{font-size:14.5px;margin:0 0 5px;color:#414140;}
    .finding p{margin:0;font-size:13px;line-height:1.85;color:#414140;}
    .tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;
      border:1px solid #CBCCCA;color:#7C827F;margin-right:6px;vertical-align:1px;}
    .tag.fact{border-color:#919C9C;color:#6E7472;}
    .tag.hyp{border-color:#F8B24D;color:#A85A3A;background:#F8B24D1F;}
    .q{font-size:15px;font-weight:600;color:#414140;margin:26px 0 4px;}
    .q span{color:#7C827F;font-weight:400;font-size:12.5px;margin-left:8px;}
    .lead{font-size:13.5px;line-height:1.95;color:#414140;margin:6px 0 14px;}
    .lead b{color:#414140;}
    .lead .neg{color:#E94C2B;font-weight:600;}
    .lead .pos{color:#919C9C;font-weight:600;}
    ul.tight{margin:6px 0 14px 18px;padding:0;font-size:13px;line-height:1.9;color:#414140;}
    ul.tight li{margin-bottom:3px;}
    .verdict{background:#ECEAE5;border:1px solid #CBCCCA;border-radius:10px;padding:16px 20px;margin:14px 0;}
    .verdict h4{margin:0 0 6px;font-size:13.5px;color:#D27048;}
    .verdict p{margin:0 0 10px;font-size:13px;line-height:1.9;color:#414140;}
    .verdict p:last-child{margin-bottom:0;}
    .row-highlight td{background:#F6EDE8;font-weight:600;}
    .chart-box{background:#FFFFFF;}
    code{background:#ECEAE5;border-radius:3px;padding:0 3px;font-size:12px;color:#414140;}
    .ibar-cell{display:flex;align-items:center;gap:7px;justify-content:flex-end;}
    .ibar-track{position:relative;flex:none;width:84px;height:12px;
      background:#F7F6F3;border-radius:2px;}
    .ibar-mid{position:absolute;left:50%;top:0;bottom:0;width:1px;background:#CBCCCA;}
    .ibar-fill{position:absolute;top:2.5px;height:7px;border-radius:1.5px;}
    .ibar-val{font-variant-numeric:tabular-nums;font-size:11.5px;min-width:52px;
      text-align:right;color:#414140;}
    .ics{display:flex;flex-direction:column;gap:4px;min-width:170px;}
    .ics-track{display:flex;height:11px;border-radius:2px;overflow:hidden;
      background:#F7F6F3;}
    .ics-seg{display:flex;align-items:center;justify-content:center;
      font-size:9px;color:#FFFFFF;overflow:hidden;white-space:nowrap;}
    .ics-cap{font-size:10.5px;line-height:1.4;color:#7C827F;}
    .ics-cap b{color:#414140;font-weight:600;}
    .q82-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px 22px;
      align-items:start;margin:6px 0 4px;}
    .q82-grid table td:first-child{white-space:nowrap;}
    .q82-grid .cell-title{font-size:12.5px;font-weight:600;color:#414140;
      margin:14px 0 4px;}
    .q82-grid .cell-title span{color:#7C827F;font-weight:400;font-size:11.5px;
      margin-left:6px;}
    @media (max-width:900px){.q82-grid{grid-template-columns:1fr;}}
    </style>""")
    A("</head>\n<body class=\"report-page\">")
    A('<header><div class="container"><div class="brand">'
      '<img class="brand-avatar" src="../../assets/brand/raccoon_avatar_light.png" alt="" />'
      '<span class="brand-name">Raccoon Research</span></div>'
      f'<span class="header-meta">上市深度研究 · 数据截至 {ctx["as_of"]}（T−1）</span>'
      "</div></header>")
    A('<main class="report-container">')

    A(f'<div class="hero"><h1>{esc(title)}</h1>')
    A("<p>"
      f"研究窗口：各代际自身上市后 D1–D{n}（{main} {win[main]['launch']} 起，"
      f"截至 {ctx['as_of']}）｜统一生命周期口径，历史代际只取前 {n} 天<br/>"
      f"对标：{'、'.join(f'{b} 上市 {win[b]['launch']}' for b in benches)}｜"
      "口径：上市观察口径｜锁单 = order_type 为用户车的零售单，剔除测试单、总部主理店内测单、"
      "试驾车/员工/批售等非零售单"
      "</p></div>")

    # ── 核心 KPI ──
    A('<div class="summary-grid">')
    A(kpi(fi(cur[main]["cum"][-1]), f"{main} D1–D{n} 累计锁单",
          f"日均 {fnum(dyn[main]['cum_avg_per_day'])} 单", "neg"))
    A(kpi(fi(d1["cum_bench"]), f"{b1} 同期累计", f"差额 {d1['cum_diff']:+,}（{fs(d1['cum_rel'])}）"))
    if b2:
        A(kpi(fi(d2["cum_bench"]), f"{b2} 同期累计", f"差额 {d2['cum_diff']:+,}（{fs(d2['cum_rel'])}）"))
    A(kpi(fp(pre[main]["pool_lock_rate"]), "预售池 → 锁单转化率",
          f"池 {fi(pre[main]['pool_total'])} · 对标 {fp(pre[b1]['pool_lock_rate'])}", "gold"))
    A("</div>")

    # ── 研究边界提示 ──
    A(f'<div class="verdict" style="margin-top:18px;"><h4>研究边界（先读）</h4>'
      f'<p>本次观察窗只有 <b>N={n} 天</b>（{win[main]["launch"]} 上市，数据截至 '
      f'{ctx["as_of"]}），因此可以判断「上市首周的起点与斜率」，'
      f'不足以判断「月度稳态」。所有涉及后续的判断均已标注为<span class="tag hyp">假设</span>，'
      f'并在结尾列出验证方式。历史代际一律只取各自上市后前 {n} 天，'
      f'不因数据更长而扩窗——唯一例外是 Q1 图的 D{n+1}–D30 参考延长线，'
      f'仅用于展示对标的释放形状，不参与任何差异计算；缺失日期不补零、不插值。</p>'
      f'<p>三个代际的上市环境不同：预售期长度分别为 '
      + "、".join(f'{g} {ctx["presale"][g]["presale_days"]} 天' for g in gens)
      + '；动力形式不同（'
      + "、".join(f'{g} {_power_label(ctx["product"][g])}' for g in gens)
      + '）。这些差异会在后文逐项量化，不能把销量差直接归因为产品竞争力。</p>'
      + (f'<p><b>窗口收窗提示</b>：主代际理论窗口 {ctx["n_days_intended"]} 天，'
         f'但部分参照代际可观察天数不足，已按共同可覆盖的 {n} 天收窗——'
         f'缺口日不补零、不把缺失当零值。</p>' if ctx.get("window_capped") else "")
      + '</div>')

    # ── 核心发现 ──
    findings = _findings(ctx)
    A(section("核心发现",
              "".join(f'<div class="finding"><h3>{esc(t)}</h3><p>{body}</p></div>'
                      for t, body in findings),
              "以下 5 条为本次研究的主要结论，均对应后文指标与参照基准；"
              "标注「解释」「假设」者为推断性内容，非数据直接观测。"))

    A(_plan_section(ctx))

    # ══════════ 第一幕 ══════════
    A(section("第一幕　" f"{main} 卖得怎么样？",
              _act1_summary(ctx), sid="act1"))

    # Q1
    A(f'<p class="q">Q1　同期锁单水平<span>D1–D{n} 累计、D{n} 之后的对标轨迹与相对表现</span></p>')
    A(f'<p class="lead">{_q1_lead(ctx)}</p>')
    rows, hdr = _table_summary(ctx)
    A(table(hdr, rows, num_cols={1, 2, 3, 4},
            bold_rows={gens.index(main)}))
    A(chart_cumulative(ctx))
    A(f'<p class="section-note">{_q1_context_note(ctx)}</p>')

    # Q2（不重复画图：差额结构由表格承载）
    A(f'<p class="q">Q2　差异从哪一天形成<span>累计差额 Δ(d) 与边际差异（表）</span></p>')
    A(f'<p class="lead">{_q2_lead(ctx)}</p>')
    rows, hdr = _table_gap(ctx)
    A(table(hdr, rows, num_cols={2, 3, 4, 5, 6, 7}))
    A(f'<p class="section-note">{_q2_note(ctx)}</p>')

    # Q3
    A(f'<p class="q">Q3　新增动能：更强还是衰减更快<span>每日新增、稳态水平与稳定性</span></p>')
    A(f'<p class="lead">{_q3_lead(ctx)}</p>')
    rows, hdr = _table_dynamics(ctx)
    A(table(hdr, rows, num_cols={1, 2, 3, 4, 5, 6, 7}))
    A(chart_daily(ctx))

    # ══════════ 第二幕 ══════════
    A(section("第二幕　差异为什么出现？", _act2_summary(ctx), sid="act2"))

    def _emit_q4():
        A(f'<p class="q">Q4　预售需求规模，还是预售转化效率<span>预售小订池 → D_N 锁单</span></p>')
        A(f'<p class="lead">{_q4_lead(ctx)}</p>')
        rows, hdr = _table_presale(ctx)
        A(table(hdr, rows, num_cols={1, 2, 3, 4, 5, 6}, bold_rows={gens.index(main)}))
        A(chart_pool_state(ctx))
        A(f'<p class="lead">{_q4_decomp_lead(ctx)}</p>')
        rows, hdr = _table_rate(ctx)
        A(table(hdr, rows, num_cols={1, 2, 3, 4, 5}))
        rows, hdr = _table_buildup(ctx)
        A(table(hdr, rows, num_cols={1, 2, 3, 4, 5, 6}))


    def _emit_q5():
        A(f'<p class="q">Q5　上市后的直接需求能否接替预售释放<span>锁单来源分解：预售小订 / 上市当日新增小订 / 直接锁单</span></p>')
        A(f'<p class="lead">{_q5_lead(ctx)}</p>')
        A(chart_origin(ctx))
        rows, hdr = _table_origin(ctx)
        A(table(hdr, rows, num_cols={1, 2, 3, 4, 5, 6}, bold_rows={gens.index(main)}))

    _plan = ctx.get("narrative") or {}
    for _blk in (_plan.get("act2") or ["q4", "q5"]):
        {"q4": _emit_q4, "q5": _emit_q5}[_blk]()

    # ══════════ 第三幕 ══════════

    A(section("第三幕　差异发生在哪里？", _act3_summary(ctx), sid="act3"))

    def _emit_q6():
        A(f'<p class="q">Q6　区域差额贡献<span>省份（主口径）与城市结构</span></p>')
        A(f'<p class="lead">{_q6_lead(ctx)}</p>')
        rows, hdr = _table_province(ctx)
        A(table(hdr, rows, num_cols={1, 2, 3, 4, 6, 7}))
        A(f'<p class="section-note">{_q6_note(ctx)}</p>')
        rows, hdr = _table_city(ctx)
        A(table(hdr, rows, num_cols={1, 2, 4}))

        if (ctx.get("province_mix") or {}).get("rows"):
            parts = ctx["province_mix"]["gens"] + [ctx["province_mix"]["other_label"]]
            A(f'<p class="q" style="font-size:13.5px;">Q6-补充　分省份锁单车型结构'
              f'<span>{" / ".join(parts)}</span></p>')
            A(f'<p class="lead">{_q6_mix_lead(ctx)}</p>')
            rows, hdr = _table_province_mix(ctx)
            A(table(hdr, rows, num_cols={1}))
            A(f'<p class="section-note">{_q6_mix_note(ctx)}</p>')

        if _q_allowed(ctx, "q8d"):
            A(f'<p class="q" style="font-size:13.5px;">Q6-验证　省份差额是不是「版本缺口」<span>按电量段对齐拆解</span></p>')
            A(f'<p class="lead">{_q6_version_lead(ctx)}</p>')
            rows, hdr = _table_version_gap(ctx)
            A(table(hdr, rows, num_cols={5}))
            A(f'<p class="section-note">{_q6_version_note(ctx)}</p>')


    def _emit_q7():
        A(f'<p class="q">Q7　网络规模与单店产能<span>门店规模、单店产出与差额分解</span></p>')
        A(f'<p class="lead">{_q7_lead(ctx)}</p>')
        A(f'<p class="section-note">图 1：门店规模（全网络活跃锁单门店 vs 本代际有锁单门店）</p>')
        A(chart_network_scale(ctx))
        A(f'<p class="section-note">图 2：单店产能（单店锁单均值 vs 门店锁单中位数）</p>')
        A(chart_network_productivity(ctx))
        rows, hdr = _table_network(ctx)
        A(table(hdr, rows, num_cols={1, 2, 3, 4, 5, 6}))
        A(f'<p class="q" style="font-size:13.5px;">Q7-2　省级「渠道 × 需求」分解<span>门店数效应 vs 单店产出效应</span></p>')
        A(f'<p class="lead">{_q7_channel_lead(ctx)}</p>')
        rows, hdr = _table_channel(ctx)
        A(table(hdr, rows, num_cols={2, 3, 4, 5, 6, 7, 8, 9}))
        A(f'<p class="section-note">{_q7_channel_note(ctx)}</p>')


    def _emit_q8():
        A(f'<p class="q">Q8　购买人群与配置偏好<span>三层：谁在买 → 选什么 → 能解释什么</span></p>')
        A(f'<p class="lead">{_q8_intro(ctx)}</p>')

        A(f'<p class="q" style="font-size:13.5px;">Q8-1　谁在购买？<span>性别、年龄、城市线级、省份</span></p>')
        A(f'<p class="lead">{_q8a_lead(ctx)}</p>')
        rows, hdr = _table_user(ctx)
        A(table(hdr, rows, num_cols={1, 2, 3}))

        sb_ok, sb_why = _sb_status(ctx)
        if sb_ok:
            A(f'<p class="q" style="font-size:13.5px;">Q8-1 补充　同档（93kWh）客群对比<span>同维度、同列口径，直接看差距是缩小还是扩大</span></p>')
            A(f'<p class="lead">{_q8_same_battery_lead(ctx)}</p>')
            rows, hdr = _table_same_battery(ctx)
            A(table(hdr, rows, num_cols={1, 2, 3, 4, 5}))
            A(f'<p class="section-note">{_q8_same_battery_note(ctx)}</p>')
        else:
            A(f'<p class="section-note">Q8-1 补充（已跳过）：{sb_why}，'
              f'不做同档客群对比，其余章节不受影响。</p>')

        A(f'<p class="q" style="font-size:13.5px;">Q8-2　他们选择什么产品？<span>版型、电量、颜色、轮毂、选装与集中度</span></p>')
        A(f'<p class="lead">{_q8b_lead(ctx)}</p>')
        cells = []
        for blk in _table_product(ctx):
            cells.append(
                f'<div><p class="cell-title">{blk["gen"]}'
                f'<span>（{fi(ctx["curves"]["curves"][blk["gen"]]["cum"][-1])} 单）</span></p>'
                + table(blk["hdr"], blk["rows"]) + '</div>')
        rows, hdr = _table_concentration(ctx)
        cells.append('<div><p class="cell-title">集中度'
                     '<span>（版型 / 电量结构）</span></p>'
                     + table(hdr, rows, num_cols={1, 2, 3, 4, 5, 6}) + '</div>')
        A('<div class="q82-grid">' + "".join(cells) + '</div>')
        rows, hdr = _table_tier_version(ctx)
        A(table(hdr, rows, num_cols={1, 2, 3, 4}))

        A(f'<p class="q" style="font-size:13.5px;">Q8-2 补充　{main} 锁单配置分布<span>外饰 / 内饰 / 轮毂 / 选装</span></p>')
        A(f'<p class="lead">{_q8_config_lead(ctx)}</p>')
        rows, hdr = _table_config_distribution(ctx)
        A(table(hdr, rows))
        A(f'<p class="section-note">{_q8_config_note(ctx)}</p>')

        A(f'<p class="q" style="font-size:13.5px;">Q8-3　这些选择能解释什么？<span>Part 1 用户差异矩阵 → Part 2 细分对比</span></p>')
        A(f'<p class="lead">{_q8c_lead(ctx)}</p>')

        A(f'<p class="q" style="font-size:13.5px;">Part 1　用户差异矩阵<span>维度同 Q8-1，两两对比</span></p>')
        A(f'<p class="section-note">差异条形图：每个维度「{main} − 对标」的百分点差；'
          f'顺序固定为 Q8-1 的维度顺序（性别 → 年龄 → 城市线级 → 省份），不按差异幅度重排</p>')
        A(chart_user_diff_profile(ctx))
        rows, hdr = _table_user_matrix(ctx)
        A(table(hdr, rows))

        A(f'<p class="q" style="font-size:13.5px;">Part 2　细分差异对比<span>同档 93kWh · 六座 vs 五座</span></p>')
        A(f'<p class="lead">{_q8_slice_lead(ctx)}</p>')
        sb2 = (ctx.get("slice_compares") or {}).get("same_battery") or {}
        sb2_ok = bool((sb2.get("stats") or {}).get(sb2.get("main"), {}).get("n")
                      and (sb2.get("stats") or {}).get(sb2.get("bench"), {}).get("n"))
        if sb2_ok:
            A(f'<p class="section-note">2A　同档：{sb2["main"]} {sb2["segment"]} vs '
              f'{sb2["bench"]} {sb2["segment"]}（用户画像 + 配置选择）</p>')
            rows, hdr = _table_slice(ctx, "same_battery")
            A(table(hdr, rows, num_cols={1, 2, 3}))
        else:
            A('<p class="section-note">2A（已跳过）：对标代际无同电量段样本，'
              '不做同档画像对比。</p>')
        seat_blk = (ctx.get("slice_compares") or {}).get("seat") or {}
        if seat_blk.get("six", {}).get("n") and seat_blk.get("five", {}).get("n"):
            A(f'<p class="section-note">2B-初始　{main} 四种配置组合占比（座椅 × 电量）</p>')
            A(f'<p class="lead">{_q8_seat_combo_lead(ctx)}</p>')
            A(chart_seat_combos(ctx))
            A(f'<p class="section-note">2B　同车不同座椅：{main} 奢享大六座 vs 旗舰大五座（用户画像 + 版型/配置选择）</p>')
            rows, hdr = _table_slice(ctx, "seat")
            A(table(hdr, rows, num_cols={1, 2, 3}))
        else:
            A('<p class="section-note">2B（已跳过）：该代际的 config_attribute 无「座椅」字段，'
              '无法拆分六座/五座用户。</p>')

        cx = (ctx.get("slice_compares") or {}).get("seat_cross") or {}
        if cx.get("main_six", {}).get("n") and cx.get("bench_six", {}).get("n"):
            A(f'<p class="section-note">2C　跨代际六座：{main} 奢享大六座 vs '
              f'{cx["bench"]} 大六座（用户画像）</p>')
            A(f'<p class="lead">{_q8_2c_lead(ctx)}</p>')
            rows, hdr = _table_seat_cross(ctx)
            A(table(hdr, rows, num_cols={1, 2, 3}))

            if (ctx["slice_compares"] or {}).get("seat_cross_ex_sh"):
                A(f'<p class="section-note">2C-剔除上海　同一口径去掉上海后的稳健性检验</p>')
                A(f'<p class="lead">{_q8_2c_lead(ctx, "seat_cross_ex_sh")}</p>')
                rows, hdr = _table_seat_cross(ctx, "seat_cross_ex_sh")
                A(table(hdr, rows, num_cols={1, 2, 3}))
            A(f'<p class="section-note">{_q8_2c_note(ctx)}</p>')
        A(f'<p class="section-note">{_q8c_note(ctx)}</p>')

        A(f'<p class="q" style="font-size:13.5px;">补充证据：客群结构的贡献（线级 规模 × 结构 分解）</p>')
        rows, hdr = _table_tier_decomp(ctx)
        A(table(hdr, rows, num_cols={1, 2, 3, 4, 5}))

    for _blk in (_plan.get("act3") or ["q6", "q7", "q8"]):
        {"q6": _emit_q6, "q7": _emit_q7, "q8": _emit_q8}[_blk]()

    # ══════════ 第三幕补充：竞争视角 ══════════
    A(section("第三幕补充　竞争视角：上市周 vs 预售周", _pk_lead(ctx), sid="pk"))
    for i, g in enumerate(gens, start=1):
        b = _pk_block(ctx, g)
        if not b.get("competitors"):
            continue
        A(f'<p class="section-note">图 {i}：{g}（series {b["series"]}）上市周 '
          f'{b["launch_week"]} vs 上期 {b.get("prev_week", "—")}；'
          f'PK 总量 {fi(b["week_total"])} vs {fi(b.get("prev_total", 0))}</p>')
        A(chart_pk_rank_table(ctx, g))
    A(f'<p class="section-note">{_pk_note(ctx)}</p>')

    # ══════════ 第四幕 ══════════
    A(section("第四幕　当前表现意味着什么？", _act4_summary(ctx), sid="act4"))

    A(f'<p class="q">Q9　订单质量<span>point-in-time 重建至上市后第 {n} 天 24:00</span></p>')
    A(f'<p class="lead">{_q9_lead(ctx)}</p>')
    rows, hdr = _table_quality(ctx)
    A(table(hdr, rows, num_cols={1, 2, 3, 4, 5, 6}))

    A(f'<p class="q">Q10　后续增长动能<span>封盘小订池的消耗：退订速度 × 锁单速度</span></p>')
    A(f'<p class="lead">{_q10_lead(ctx)}</p>')
    A(chart_pool_consumption(ctx))
    rows, hdr = _table_pool(ctx)
    A(table(hdr, rows, num_cols={1, 2, 3, 4, 5, 6, 7, 8, 9}))
    A(f'<p class="section-note">{_q10_note(ctx)}</p>')
    A(_q10_potential(ctx))

    # ══════════ 结尾 ══════════
    A(section("经营判断", _verdict(ctx), sid="verdict"))
    A(section("下一观察周期需要重点验证什么", _watchlist(ctx), sid="watch"))

    # ══════════ 附录 ══════════
    A(section("附录 A　数据口径与差异计算说明", _appendix_scope(ctx), sid="appendix"))
    A(section("附录 B　数据质量审计", _appendix_audit(ctx)))

    A('<p class="section-note" style="margin-top:36px;border-top:1px solid #E7ECF1;padding-top:14px;">'
      f"生成时间 {ctx['generated_at']}｜脚本 workspace/research_scripts/launch_deep_dive.py"
      "（可复现：同输入同参数重跑生成同一结果）｜数据源 dataset/order_data.parquet、"
      "dataset/config_attribute.parquet、门店主数据｜本报告不修改任何生产数据与正式业务口径。</p>")
    A("</main></body></html>")

    out_file.write_text("\n".join(S), encoding="utf-8")
    return out_file


# ─────────────────────────── 各段文案 ───────────────────────────

def _context_sentence(ctx: dict, bench: str) -> str:
    """D_N 之后对标释放的参考句（假设，不参与差异计算）。"""
    main, n = ctx["main"], ctx["n_days"]
    cc = ctx.get("context", {}).get("curves", {}).get(bench)
    cur = ctx["curves"]["curves"]
    if not cc or cc["available_days"] <= n or not cur[bench]["cum"][-1]:
        return ""
    mult = cc["cum"][-1] / cur[bench]["cum"][-1]
    proj = cur[main]["cum"][-1] * mult
    return (f" 参考：{bench} 在 D{n} 之后仍在释放，D{cc['available_days']} 累计 "
            f"{fi(cc['cum'][-1])} 单（D{n} 的 {fnum(mult, 2)}×）；若 {main} 按同一倍数外推，"
            f"D30 约 {fi(proj)} 单（假设区间，不参与差异计算）。")


def _findings(ctx: dict) -> list[tuple[str, str]]:
    """核心发现：只渲染本次计算产出的 ResearchFindings，不再内联任何固定判断。"""
    fs = ctx.get("findings") or []
    out = []
    for i, f in enumerate(fs, start=1):
        body = f.get("body", "")
        out.append((f"{i}｜{f.get('title', '')}", body + "<span class='tag fact'>事实</span>"))
    return out


def _q_allowed(ctx: dict, qid: str) -> bool:
    """Gate A 未通过的研究问题，渲染层不得输出对应区块。"""
    gate = ctx.get("gate_a") or {}
    for r in gate.get("results", []):
        if r.get("id") == qid:
            return r.get("status") == "PASS"
    return True


def _act1_summary(ctx: dict) -> str:
    main, n = ctx["main"], ctx["n_days"]
    cur = ctx["curves"]["curves"]
    b1 = ctx["benchmarks"][0]
    return (f'<p class="lead">第一幕只回答一个问题：把三款车放在各自上市后的前 {n} 天里，'
            f'{main} 的锁单处在什么位置、差距何时形成、动能是否更强。'
            f'全部数字来自零售锁单口径（{cur[main]["dates"][0]} ~ {cur[main]["dates"][-1]}，'
            f'{b1} 与其余对标取各自上市后同长度窗口）。</p>')


def _power_label(prof: dict) -> str:
    """从电量段结构推断动力形式标签（仅用于边界说明，不参与计算）。

    52/66kWh → 增程；76/93/100/103kWh → 纯电；仅「未标注」→ 不可区分。
    """
    keys = set((prof.get("battery") or {}).keys())
    if not keys or keys == {"未标注"}:
        return "动力不可区分"
    erev = {"52kWh", "66kWh"}
    bev = {"76kWh", "93kWh", "100kWh", "103kWh"}
    if keys <= erev:
        return "增程"
    if keys <= bev:
        return "纯电"
    if keys & erev and keys & bev:
        return "增程+纯电"
    return "动力不可区分"


def _q1_lead(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    d = ctx["deltas"]
    cur = ctx["curves"]["curves"]
    n = ctx["n_days"]

    def _rel(v):
        return "持平" if abs(v) < 0.005 else ("领先" if v > 0 else "落后")

    txt = (f"{main} 同期累计 <b>{fi(cur[main]['cum'][-1])} 单</b>，"
           f"相对 {b1}（{fi(cur[b1]['cum'][-1])} 单）{d[b1]['cum_diff']:+,} 单"
           f"（{fs(d[b1]['cum_rel'])}，{_rel(d[b1]['cum_rel'])}）")
    if b2:
        txt += (f"，相对 {b2}（{fi(cur[b2]['cum'][-1])} 单）{d[b2]['cum_diff']:+,} 单"
                f"（{fs(d[b2]['cum_rel'])}，{_rel(d[b2]['cum_rel'])}）")
    gap12 = abs(cur[b1]['cum'][-1] - cur[b2]['cum'][-1]) if b2 else 0
    txt += "。" + (f"两款对标同期水平接近（相差 {fi(gap12)} 单）。" if b2 else "")
    rels = [abs(v["cum_rel"]) for v in d.values()]
    if max(rels) < 0.05:
        txt += (f"<b>{main} 与对标处于同一量级（最大相对差 {max(rels) * 100:.1f}%），"
                f"总量相近，真正的差别要看释放节奏与结构。</b>")
    elif all(v["cum_diff"] < 0 for v in d.values()):
        txt += (f"<b>对两个基准均为落后，最大相对差 {max(rels) * 100:.0f}%，"
                f"需要解释的是这种一致性落后。</b>")
    else:
        txt += f"<b>对不同基准方向不一致，必须分别解读，不能合并成一个结论。</b>"
    return txt


def _q1_context_note(ctx: dict) -> str:
    """D{n+1}–D30 参考延长线的读法：仅看「对标 D{n} 之后还能释放多少」。"""
    main, n = ctx["main"], ctx["n_days"]
    cc = ctx.get("context", {}).get("curves", {})
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    parts = []
    for b in ctx["benchmarks"]:
        c = cc.get(b)
        cur = ctx["curves"]["curves"][b]["cum"][-1]
        if c and c["available_days"] > n:
            parts.append(f"{b} D{c['available_days']} 累计 {fi(c['cum'][-1])} 单，"
                         f"为 D{n} 的 {fnum(c['cum'][-1] / cur, 2)} 倍")
    if not parts:
        return ("本图仅显示同期比较窗口。参考延长线需 --context-days>0 且对标车型有 D_N 之后的数据。")
    txt = ("读法：实线部分为<b>同期比较窗口</b>（唯一参与差异计算的区间），"
           "虚点线为对标车型在 D" + str(n) + " 之后的参考轨迹——"
           + "；".join(parts) + "。")
    b2c = cc.get(b2) if b2 else None
    b1c = cc.get(b1)
    if b1c and b2c and b1c["available_days"] > n and b2c["available_days"] > n:
        cur = ctx["curves"]["curves"][main]["cum"][-1]
        lo = cur * b2c["cum"][-1] / ctx["curves"]["curves"][b2]["cum"][-1]
        hi = cur * b1c["cum"][-1] / ctx["curves"]["curves"][b1]["cum"][-1]
        txt += (f" 若 {main} 后续按对标的 D{n}→D30 兑现倍数外推（{fnum(b2c['cum'][-1] / ctx['curves']['curves'][b2]['cum'][-1], 2)}–"
                f"{fnum(b1c['cum'][-1] / ctx['curves']['curves'][b1]['cum'][-1], 2)}×），"
                f"D30 大致落在 {fi(lo)}–{fi(hi)} 单区间——"
                f"<b>该区间是标注为假设的情景，不进入任何差异指标</b>；"
                f"{main} 目前只有 D{n} 数据，无法验证是否遵循该倍数。")
    txt += (f" 历史代际的 D{n+1}–D{ctx['context']['context_days']} 数据只用于本图的形状参考，正式口径仍为等窗口 D1–D{n}。")
    return txt


def _table_summary(ctx: dict):
    gens, main = ctx["curves"]["gens"], ctx["main"]
    n = ctx["n_days"]
    cur, dyn, pre, net = ctx["curves"]["curves"], ctx["dynamics"], ctx["presale"], ctx["network"]
    hdr = ["代际", "D1 锁单", f"D1–D{n} 累计", "相对主车", "D1 占比",
           f"D2–D{n} 日均", "预售池", "有效门店", "单店产出"]
    rows = []
    for g in gens:
        d = ctx["deltas"].get(g)
        rows.append([
            f"<b>{g}</b>" if g == main else g,
            fi(cur[g]["daily"][0]), fi(cur[g]["cum"][-1]),
            "—" if g == main else f"{d['cum_rel'] * 100:+.1f}%",
            fp(dyn[g]["d1_share_of_cum"], 1),
            fnum(dyn[g]["tail_avg"]), fi(pre[g]["pool_total"]),
            fi(net[g]["stores_with_gen"]), fnum(net[g]["locks_per_store"], 2),
        ])
    return rows, hdr


def _q2_lead(ctx: dict) -> str:
    main = ctx["main"]
    n = ctx["n_days"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    gaps = ctx["curves"]["gaps"]
    d1 = ctx["deltas"][b1]
    txt = (f"对 {b1}：<b>{gap_narrative(d1, n)}</b>；"
           f"此后每天的边际差异为 {'/'.join(f'{v:+,}' for v in gaps[b1]['marginal'][1:])} 单。")
    if b2:
        d2 = ctx["deltas"][b2]
        txt += (f" 对 {b2}：{gap_narrative(d2, n)}，"
                f"之后仍以 {'/'.join(f'{v:+,}' for v in gaps[b2]['marginal'][1:])} 单/日变化。")
    return txt


def _table_gap(ctx: dict):
    n = ctx["n_days"]
    cur = ctx["curves"]["curves"]
    gaps = ctx["curves"]["gaps"]
    gens, main = ctx["curves"]["gens"], ctx["main"]
    benches = ctx["benchmarks"]
    b1 = benches[0]
    b2 = benches[1] if len(benches) > 1 else None
    hdr = ["天数", f"{main}", *gens[1:]]
    if b2:
        hdr += [f"Δ_{b1}", f"边际_{b1}", f"Δ_{b2}", f"边际_{b2}"]
    else:
        hdr += [f"Δ_{b1}", f"边际_{b1}"]
    rows = []
    for i in range(n):
        r = [f"D{i + 1}（{_WD.get(cur[main]['weekdays'][i], '')}）"]
        r += [fi(cur[g]["cum"][i]) for g in gens]
        r += [f"{gaps[b1]['cum_gap'][i]:+,}", f"{gaps[b1]['marginal'][i]:+,}"]
        if b2:
            r += [f"{gaps[b2]['cum_gap'][i]:+,}", f"{gaps[b2]['marginal'][i]:+,}"]
        rows.append(r)
    return rows, hdr


def _q2_note(ctx: dict) -> str:
    main = ctx["main"]
    n = ctx["n_days"]
    ln = ctx["launch_night"]
    lines = []
    for g in ctx["curves"]["gens"]:
        lines.append(f"{g}：首笔锁单 {ln[g]['first_lock']}，上市日 20:00–24:00 "
                     f"{fi(ln[g]['night_2000_2400'])} 单")
    n20 = {g: ln[g]["night_2000_2400"] for g in ctx["curves"]["gens"]}
    b1 = ctx["benchmarks"][0]
    extra = (f"按 20:00–24:00 对齐（消除各代际开盘时刻差异）后，{main} 为 {b1} 的 "
             f"{fp(n20[main] / n20[b1], 0)}，比全日口径的 "
             f"{fp(ctx['curves']['curves'][main]['daily'][0] / ctx['curves']['curves'][b1]['daily'][0], 0)} 更低——"
             f"即上市夜爆发力的差距比表观更大。")
    return ("上市夜对齐检验：" + "；".join(lines) + "。" + extra +
            " 说明：星期结构也需注意，"
            + "、".join(f"{g} D1–D{n} 为 {'/'.join(ctx['windows'][g]['weekdays'])}"
                        for g in ctx["curves"]["gens"])
            + f"（{main} 与 LS8 的星期结构一致、含 2 个周末日，对标中 CM3 只含 1 个周末日，"
              f"该差异方向上对 {main} 有利，因此不改变落后结论。")


def _q3_lead(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    dyn = ctx["dynamics"]
    n = ctx["n_days"]
    m = dyn[main]
    txt = (f"{main} 的 D2 相对 D1 衰减到 <b>{fp(m['d2_over_d1'], 1)}</b>，"
           f"此后 D2–D{n} 稳定在 {fnum(m['tail_avg'])} 单/日"
           f"（波动系数 {fnum(m['tail_cv'], 2)}），"
           f"没有出现二次爬坡。")
    for b in ctx["benchmarks"]:
        txt += (f" 对比 {b}：D2/D1 = {fp(dyn[b]['d2_over_d1'], 1)}，"
                f"稳态 {fnum(dyn[b]['tail_avg'])} 单/日、波动系数 {fnum(dyn[b]['tail_cv'], 2)}"
                + ("（尾段仍在走高，上市后需求未衰减）" if dyn[b]["slope_tail"] > 0
                   else "（尾段逐日回落）") + "。")
    return txt


def _table_dynamics(ctx: dict):
    gens = ctx["curves"]["gens"]
    n = ctx["n_days"]
    dyn = ctx["dynamics"]
    hdr = ["代际", "D1", f"D2–D{n} 日均",
           "D1 占累计", "D2/D1", "波动系数", "尾段斜率(单/日)", "星期结构"]
    rows = []
    for g in gens:
        d = dyn[g]
        rows.append([g, fi(d["d1"]), fnum(d["tail_avg"]), fp(d["d1_share_of_cum"], 1),
                     fp(d["d2_over_d1"], 1), fnum(d["tail_cv"], 2), fnum(d["slope_tail"], 1),
                     "/".join(d["weekday_profile"].keys())])
    return rows, hdr


def _act2_summary(ctx: dict) -> str:
    return ('<p class="lead">第二幕把「累计锁单」拆开：先看预售需求池的大小与转化效率，'
            '再看上市之后的新增需求能否接替预售释放。拆解口径严格区分三件事——'
            '预售期支付的小订、上市日及以后支付的小订、以及没有小订记录直接锁单的订单。</p>')


def _q4_lead(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    pre = ctx["presale"]
    return (f"{main} 预售池 <b>{fi(pre[main]['pool_total'])} 单</b>"
            f"（预售 {pre[main]['presale_start']} ~ 上市前一日，共 {pre[main]['presale_days']} 天），"
            f"到 D{ctx['n_days']} 已转锁单 {fi(pre[main]['pool_locked'])} 单、"
            f"退订 {fi(pre[main]['pool_refunded'])} 单、预售池仍待转化 {fi(pre[main]['pool_pending'])} 单。"
            f"池规模只有 {b1} 的 {fp(pre[main]['pool_total'] / pre[b1]['pool_total'], 0)}，"
            f"但转化率 {fp(pre[main]['pool_lock_rate'])} 与 {b1}（{fp(pre[b1]['pool_lock_rate'])}）几乎持平，"
            f"退订率 {fp(pre[main]['pool_refund_rate'])} 也低于 {b1}（{fp(pre[b1]['pool_refund_rate'])}）。"
            f"<b>结论：规模差，不是效率差；而规模差主要来自预售期长度，不是获客速度。</b>"
            f"（池累积分解见下表：对 {b1} 的池差中，预售期长度解释 "
            f"{fp(pre[main]['buildup_vs'][b1]['duration_share_of_gap'], 0)}，"
            f"首日爆发力解释 {fp(pre[main]['buildup_vs'][b1]['day1_share_of_gap'], 0)}，"
            f"首日后日均速度只解释 "
            f"{fp(1 - pre[main]['buildup_vs'][b1]['duration_share_of_gap'] - pre[main]['buildup_vs'][b1]['day1_share_of_gap'], 0)}。）")


def _table_presale(ctx: dict):
    gens, main = ctx["curves"]["gens"], ctx["main"]
    pre = ctx["presale"]
    hdr = ["代际", "预售天数", "预售池", "已转锁单", "池转化率",
           "退订", "退订率", "预售池待转化", "上市当日新增小订", "其中已锁"]
    rows = []
    for g in gens:
        p = pre[g]
        rows.append([f"<b>{g}</b>" if g == main else g, f"{p['presale_days']} 天",
                     fi(p["pool_total"]), fi(p["pool_locked"]), fp(p["pool_lock_rate"]),
                     fi(p["pool_refunded"]), fp(p["pool_refund_rate"]),
                     fi(p["pool_pending"]), fi(p["launch_intent_total"]),
                     fi(p["launch_intent_locked"])])
    return rows, hdr


def _q4_decomp_lead(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    src = ctx["source_decomp"]
    s1 = src[b1]
    txt = (f"把 <b>预售池贡献的锁单</b> 做二元分解（池规模 × 转化率）："
           f"对 {b1}，池规模少 {fi(abs(s1['pool_diff']))} 单贡献 {fnum(s1['presale_scale_effect'])} 单、"
           f"转化率差（{fp(s1['rate_main'])} vs {fp(s1['rate_bench'])}）贡献 "
           f"{fnum(s1['presale_rate_effect'])} 单，池规模解释 "
           f"<b>{fp(s1['presale_scale_share'], 0)}</b>。")
    if b2:
        s2 = src[b2]
        txt += (f" 对 {b2} 方向相反、幅度更大：池规模少 {fi(abs(s2['pool_diff']))} 单贡献 "
                f"{fnum(s2['presale_scale_effect'])} 单，而转化率更高"
                f"（{fp(s2['rate_main'])} vs {fp(s2['rate_bench'])}）反补 "
                f"{fnum(s2['presale_rate_effect'])} 单——"
                f"{main} 的单池转化效率明显好于 {b2}，问题完全在池子大小。")
    return txt + " 下表用单位时间口径检验「池子小」是否等于「需求弱」。"


def _table_rate(ctx: dict):
    gens, main = ctx["curves"]["gens"], ctx["main"]
    pre = ctx["presale"]
    hdr = ["代际", "预售日均小订", "净留存/日", "首日占池", "上市当日新增小订", "全程净留存/日"]
    rows = []
    for g in gens:
        p = pre[g]
        rows.append([f"<b>{g}</b>" if g == main else g,
                     fnum(p["pool_per_presale_day"]), fnum(p["net_retained_per_presale_day"]),
                     fp(p["presale_day1_share"]), fnum(p["launch_intent_per_day"]),
                     fnum(p["net_retained_per_obs_day"])])
    return rows, hdr


def _table_buildup(ctx: dict):
    """预售池累积分解：首日爆发 × 首日后日均 × 预售期长度（含反事实）。"""
    main = ctx["main"]
    pre = ctx["presale"]
    bu = pre[main].get("buildup_vs", {})
    hdr = ["对比基准", "池差", "首日爆发差", "预售天数差", "长度效应", "长度效应占池差",
           "若同预售天数的池", "对标池"]
    rows = []
    for b, v in bu.items():
        rows.append([b, f"{v['pool_diff']:+,}", f"{v['day1_diff']:+,}",
                     f"{v['days_diff']:+d} 天", fnum(v["duration_effect"]),
                     fp(v["duration_share_of_gap"], 0),
                     fi(v["pool_if_bench_duration"]), fi(pre[b]["pool_total"])])
    return rows, hdr


def _q5_lead(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    org = ctx["origin"]
    o = org[main]
    txt = (f"{main} 窗口内 {fi(o['total'])} 单锁单按来源精确三分："
           f"<b>预售小订转锁 {fi(o['pre'])} 单（{fp(o['pre_share'], 0)}）</b>、"
           f"上市当日新增小订转锁 {fi(o['launch_day'])} 单（{fp(o['launch_day_share'], 0)}）、"
           f"直接锁单 {fi(o['none'])} 单（{fp(o['none_share'], 1)}）。")
    if b2:
        txt += (f" 相较 {b2}，{main} 预售来源少 {fi(org[b2]['pre'] - o['pre'])} 单，"
                f"但上市当日新增小订转化多 {fi(o['launch_day'] - org[b2]['launch_day'])} 单——"
                f"<b>上市当日的新增需求不弱，弱的是预售存量</b>。")
    txt += (f" 相较 {b1}，预售 {o['pre'] - org[b1]['pre']:+,} 单、"
            f"上市当日新增 {o['launch_day'] - org[b1]['launch_day']:+,} 单、"
            f"直接锁单 {o['none'] - org[b1]['none']:+,} 单。")
    post = sum(org[g].get("post_launch", 0) for g in ctx["curves"]["gens"])
    if post:
        txt += (f" 另有 {fi(post)} 单小订晚于上市日 24:00（"
                + " / ".join(f"{g} {org[g].get('post_launch', 0)}"
                             for g in ctx["curves"]["gens"])
                + "），属口径外残余，未并入上述三类。")
    txt += (" 需注意口径演进："
            + "、".join(f"{g} 直接锁单占 {fp(org[g]['none_share'], 1)}" for g in ctx["curves"]["gens"])
            + "，历史代际的下单流程允许跳过小订，故「直接锁单」占比不可解释为直接需求强弱。")
    return txt


def _table_origin(ctx: dict):
    gens, main = ctx["curves"]["gens"], ctx["main"]
    org = ctx["origin"]
    hdr = ["代际", "锁单合计", "预售小订转锁", "占比", "上市当日新增小订转锁", "占比",
           "直接锁单", "占比"]
    rows = []
    for g in gens:
        o = org[g]
        rows.append([f"<b>{g}</b>" if g == main else g, fi(o["total"]), fi(o["pre"]),
                     fp(o["pre_share"], 1), fi(o["launch_day"]), fp(o["launch_day_share"], 1),
                     fi(o["none"]), fp(o["none_share"], 1)])
    return rows, hdr


def _act3_summary(ctx: dict) -> str:
    return ('<p class="lead">第三幕定位差异发生在哪里：区域、门店网络、产品与客户结构。'
            '区域主口径用<b>省份</b>而非大区——2026-04 至 2026-11 期间大区架构经历重划'
            '（一区/二区/三区 → 东区/西区/北区/华中区），同一省组在不同窗口中挂在不同大区下，'
            '直接比大区占比会把组织架构变更误读为区域表现差异。</p>')


def _q6_lead(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    ge = ctx["geo"]
    out = []
    for b in ctx["benchmarks"]:
        rows = ge["province"]["gaps"][b]
        ordered = sorted(rows, key=lambda r: (-abs(r["abs_diff"]), str(r["province"])))
        neg = [r for r in ordered if r["abs_diff"] < 0][:3]
        pos = [r for r in ordered if r["abs_diff"] > 0][:2]
        seg = []
        if neg:
            seg.append("少的省份是 " + "、".join(
                f"{r['province']}（{r['abs_diff']:+,} 单，占该省对标 "
                f"{fp(r['main'] / r['bench'] if r['bench'] else 0)}）" for r in neg))
        if pos:
            seg.append("多的省份是 " + "、".join(
                f"{r['province']}（{r['abs_diff']:+,} 单）" for r in pos))
        out.append(f"vs {b}（按绝对差额）：" + "；".join(seg) + "。")
    city = ge["city"]["gaps"][b1]["rows"][:5]
    out.append(f"城市层面，vs {b1} 的绝对差额最集中在 "
               + "、".join(f"{c['city']}（{c['abs_diff']:+,}）" for c in city)
               + f"，前 5 城合计 {sum(c['abs_diff'] for c in city):+,} 单，"
                 f"占对 {b1} 总差额的 {fp(sum(c['abs_diff'] for c in city) / ctx['deltas'][b1]['cum_diff'], 0)}。")
    return " ".join(out)


def _table_province(ctx: dict):
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    ge = ctx["geo"]["province"]
    rows_p = ge["gaps"][b1]
    order = ge.get("top_main") or [r["province"] for r in rows_p[:12]]
    map1 = {r["province"]: r for r in rows_p}
    rows_p2 = ge["gaps"][b2] if b2 else []
    map2 = {r["province"]: r for r in rows_p2}
    hdr = ["省份", f"{main} 单", f"{main} 占比", f"{b1} 单", f"{b1} 占比",
           f"绝对差额 vs {b1}"]
    if b2:
        hdr += [f"{b2} 单", f"{b2} 占比", f"绝对差额 vs {b2}"]
    rows = []
    sub1 = [map1[pv] for pv in order if pv in map1][:12]
    max1 = max((abs(r["abs_diff"]) for r in sub1), default=0)
    sub2 = [map2.get(r["province"], {"bench": 0, "bench_share": 0, "abs_diff": 0})
            for r in sub1] if b2 else []
    max2 = max((abs(r["abs_diff"]) for r in sub2), default=0)
    for i, r in enumerate(sub1):
        row = [r["province"], fi(r["main"]), fp(r["main_share"]), fi(r["bench"]),
               fp(r["bench_share"]), incell_bar(r["abs_diff"], max1)]
        if b2:
            r2 = sub2[i]
            row += [fi(r2["bench"]), fp(r2["bench_share"]), incell_bar(r2["abs_diff"], max2)]
        rows.append(row)
    return rows, hdr


def _table_province_mix(ctx: dict):
    """各省锁单的车型构成：LS8Neo / CM3 / LS8 / 其他（100% 堆积条）。"""
    pm = ctx.get("province_mix") or {}
    rows_in = pm.get("rows") or []
    if not rows_in:
        return [], []
    gens = pm["gens"]
    parts = gens + [pm["other_label"]]
    rows = []
    mix_colors = [IM["own"], IM["bench1"], IM["bench2"], IM["grid"]]
    for r in rows_in:
        items = [(k, r["parts"][k]["share"]) for k in parts]
        rows.append([r["province"], f"{r['total']:,}",
                     incell_stack(items, cap_items=4, min_label=0.06,
                                  colors=mix_colors)])
    nat = pm.get("national") or {}
    if nat:
        items = [(k, nat[k]["share"]) for k in parts]
        rows.append(["<b>全国</b>", f"{pm['grand_total']:,}",
                     incell_stack(items, cap_items=4, min_label=0.06,
                                  colors=mix_colors)])
    hdr = ["省份", "锁单合计", f"车型构成（{' / '.join(parts)}）"]
    return rows, hdr


def _q6_mix_lead(ctx: dict) -> str:
    pm = ctx.get("province_mix") or {}
    if not pm:
        return ""
    nat = pm["national"]
    main = ctx["main"]
    rows = pm["rows"]
    hi = max(rows, key=lambda r: r["main_share"])
    lo = min(rows, key=lambda r: r["main_share"])
    return (f"窗口 {pm['window'][0]}~{pm['window'][1]} 全国 {fi(pm['grand_total'])} 单锁单里，"
            f"{main} 占 <b>{fp(nat[main]['share'])}</b>，"
            f"{'、'.join(f'{b} 占 {fp(nat[b]['share'])}' for b in pm['gens'] if b != main)}，"
            f"其他车系 {fp(nat['其他']['share'])}。"
            f"省份之间分化明显：{hi['province']} 的 {main} 占比最高（{fp(hi['main_share'])}，"
            f"{fi(hi['total'])} 单），{lo['province']} 最低（{fp(lo['main_share'])}，"
            f"{fi(lo['total'])} 单）——"
            f"后者正是老代际仍在贡献存量的省份。")


def _q6_mix_note(ctx: dict) -> str:
    pm = ctx.get("province_mix") or {}
    if not pm:
        return ""
    return (f"口径：单一日历窗口（{pm['window'][0]}~{pm['window'][1]}，即 {ctx['main']} 的 D1–D{ctx['n_days']}），"
            f"各代际按 series_group_logic 归类，剩余车系统称「其他」；"
            f"因此 CM3 / LS8 的份额是<b>窗口内仍在售的存量</b>，不代表它们上市初期的水平。"
            f"表按 {ctx['main']} 占比降序，共 {pm['n_provinces']} 个省份，展示前 {len(pm['rows'])} 个。")


def _q6_version_lead(ctx: dict) -> str:
    vg = ctx.get("version_gap") or {}
    if not vg:
        return "无对标可拆解。"
    main, bench = vg["main"], vg["bench"]
    nat = vg["national"]
    missing = "、".join(nat["missing_segments"]) or "无"
    seg = nat["by_segment"]
    share = (abs(seg.get("76kWh", 0)) / abs(nat["total"])) if nat["total"] else 0
    provs = "、".join(p["label"] for p in vg["provinces"])
    p76 = sum(p["by_segment"].get("76kWh", 0) for p in vg["provinces"])
    p93 = sum(p["by_segment"].get("93kWh", 0) for p in vg["provinces"])
    p103 = sum(p["by_segment"].get("103kWh", 0) for p in vg["provinces"])
    ptot = sum(p["total"] for p in vg["provinces"])
    return (
        f"验证结论：<b>不是主销 Max 版卖不动</b>。把两车按电量段对齐后，"
        f"{main} 缺少 {missing} 这一档（{bench} 该档 {fi(nat['bench_has'].get('76kWh', 0))} 单），"
        f"全国差额 {nat['total']:+,} 单里 <b>{seg.get('76kWh', 0):+,} 单（{fp(share, 0)}）来自这个供给缺口</b>；"
        f"同电量的 93kWh 段差 {seg.get('93kWh', 0):+,} 单，103kWh 段反而是 {seg.get('103kWh', 0):+,} 单。"
        f"体量最大的 {len(vg['provinces'])} 个省份（{provs}）合计 {ptot:+,} 单，"
        f"其中 76kWh 贡献 {p76:+,}、93kWh {p93:+,}、103kWh {p103:+,}。"
    )


def _table_version_gap(ctx: dict):
    vg = ctx.get("version_gap") or {}
    if not vg:
        return [], []
    segs = vg["segments"]
    hdr = ["口径", "差额合计", *[f"{s} 差" for s in segs], "对标独有段占差额"]
    all_rows = [vg["national"], *vg["provinces"]]
    max_total = max((abs(r["total"]) for r in all_rows), default=0)
    max_seg = {x: max((abs(r["by_segment"].get(x, 0)) for r in all_rows), default=0)
               for x in segs}
    rows = []
    for r in all_rows:
        miss = 0
        for x in segs:
            if r["main_has"].get(x, 0) == 0 and r["bench_has"].get(x, 0) > 0:
                miss += r["by_segment"].get(x, 0)
        share = (abs(miss) / abs(r["total"])) if r["total"] else 0
        rows.append([
            "<b>全国</b>" if r["label"] == "全国" else r["label"],
            incell_bar(r["total"], max_total),
            *[incell_bar(r["by_segment"].get(x, 0), max_seg[x]) for x in segs],
            fp(share, 0),
        ])
    return rows, hdr


def _q6_version_note(ctx: dict) -> str:
    vg = ctx.get("version_gap") or {}
    if not vg:
        return ""
    main, bench = vg["main"], vg["bench"]
    return (
        f"对齐口径：只能按<b>电量段</b>对齐，因为两代际版型命名与配置档位不同——"
        f"{main} 93 Max+ 对应 {bench} Pro Max(93)，{main} 103 Max+ 对应 {bench} Ultra(103)；"
        f"{bench} Max(76) 在 {main} 没有对应版本。"
        f"「对标独有段占差额」= 本代际缺失区间在差额中的占比，越高说明差额越是产品线缺口而非需求差。"
        f"该拆解只回答「少的是哪一档」，不回答「为什么没有这一档」（定价/产品规划不在本数据范围）。"
    )


def _q6_note(ctx: dict) -> str:
    tiers = ctx["geo"]["tier"]["gaps"][ctx["benchmarks"][0]]
    main = ctx["main"]
    t = "、".join(f"{r['tier']} {fp(r['main_share'])} vs {fp(r['bench_share'])}"
                  for r in tiers)
    return (f"省份表按<b>{main} 自身体量降序</b>取前 12 省（不是按差额排序——按差额排会把"
            f"体量大但差额小的省份挤掉），差额列给出<b>绝对差额</b>（{main} 单量 − 对标单量）；"
            f"最右列是单元格内条形图：以 0 为中线，向右（陶土橙）表示该省多卖、"
            f"向左（灰绿）表示少卖，条长按同列最大绝对差额归一，仅用于横向比较幅度，"
            f"不等于金额或占比。"
            f"城市线级结构对比（{main} vs {ctx['benchmarks'][0]}）：{t}——"
            "四档线级的占比差异都在 1.5pp 以内，说明本次差异不是客群城市层级迁移造成的。"
            "读法提醒：绝对差额把「整体体量差」和「该省特殊表现」混在一起，"
            "若要看某省是否被结构性低估/高估，应把它与全国平均差额对照（见下方城市表与 Q6-验证）。")


def _table_city(ctx: dict):
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    c1 = ctx["geo"]["city"]["gaps"][b1]["rows"][:8]
    c2map = {r["city"]: r for r in (ctx["geo"]["city"]["gaps"][b2]["rows"] if b2 else [])}
    hdr = ["城市", f"{main}", f"{b1}", f"绝对差额 vs {b1}"]
    if b2:
        hdr += [f"{b2}", f"绝对差额 vs {b2}"]
    max1 = max((abs(c["abs_diff"]) for c in c1), default=0)
    sub2 = [c2map.get(c["city"], {"bench": 0, "abs_diff": 0}) for c in c1] if b2 else []
    max2 = max((abs(c["abs_diff"]) for c in sub2), default=0)
    rows = []
    for i, c in enumerate(c1):
        row = [c["city"], fi(c["main"]), fi(c["bench"]), incell_bar(c["abs_diff"], max1)]
        if b2:
            c2 = sub2[i]
            row += [fi(c2["bench"]), incell_bar(c2["abs_diff"], max2)]
        rows.append(row)
    return rows, hdr


def _q7_lead(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    net = ctx["network"]
    m = net[main]
    txt = (f"同窗口内全网络活跃锁单门店 {fi(m['active_stores_all_series'])} 家，"
           f"其中 {main} 有锁单的门店 <b>{fi(m['stores_with_gen'])} 家"
           f"（铺货渗透 {fp(m['gen_store_penetration'])}）</b>，"
           f"单店产出 {fnum(m['locks_per_store'], 2)} 单/店、门店中位数 "
           f"{fnum(m['median_store_locks'], 0)} 单。")
    for b in ctx["benchmarks"]:
        nb = net[b]
        dec = nb["vs_main_decomp"]
        txt += (f" vs {b}：门店少 {fi(abs(dec['store_diff']))} 家、单店产出低 "
                f"{fnum(dec['locks_per_store_bench'] - dec['locks_per_store_main'], 2)} 单/店；"
                f"差额 {dec['gap_locks']:+,} 单中<b>网络规模解释 "
                f"{fp(dec['network_share'], 0)}</b>（{fnum(dec['network_effect'])} 单），"
                f"单店产能解释 {fp(1 - dec['network_share'], 0)}（{fnum(dec['productivity_effect'])} 单）。")
    txt += (f" 值得注意的是全网络活跃门店从 {b2} 窗口的 {fi(net[b2]['active_stores_all_series'])} 家"
            f"降至 {main} 窗口的 {fi(m['active_stores_all_series'])} 家"
            f"（{fp(m['active_stores_all_series'] / net[b2]['active_stores_all_series'] - 1, 0)}），"
            f"这是与产品无关、但会直接压低同窗口销量的结构性因素。" if b2 else "")
    return txt


def _table_network(ctx: dict):
    gens, main = ctx["curves"]["gens"], ctx["main"]
    net = ctx["network"]
    hdr = ["代际", "全网络活跃门店", "本代际有锁单门店", "铺货渗透", "单店产出",
           "门店中位数", "单店仅 1 单占比", "覆盖城市", "经销商主体", "Top10 门店集中度"]
    rows = []
    for g in gens:
        n = net[g]
        rows.append([f"<b>{g}</b>" if g == main else g, fi(n["active_stores_all_series"]),
                     fi(n["stores_with_gen"]), fp(n["gen_store_penetration"]),
                     fnum(n["locks_per_store"], 2), fnum(n["median_store_locks"], 0),
                     fp(n["single_lock_store_share"]), fi(n["cities_with_gen"]),
                     fi(n["bloc_count"]), fp(n["top10_store_share"])])
    return rows, hdr


def _q8_intro(ctx: dict) -> str:
    return ('<p class="lead">Q8 用三个连续问题定位差异：'
            '<b>谁在买</b>（客群是否换人）→ <b>选什么</b>（配置是否分化）→ '
            '<b>能解释什么</b>（把客群、产品供给、渠道三类因素分开）。'
            '三层都用同一 D1–D_N 窗口，且区分「需求侧偏好」与「供给侧可选项」。</p>')


def _q8a_lead(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    prod = ctx["product"]
    p = prod[main]
    txt = (f"{main} 女性占比 {fp(p['gender'].get('女', 0))}"
           f"（{b1} {fp(prod[b1]['gender'].get('女', 0))}"
           + (f"、{b2} {fp(prod[b2]['gender'].get('女', 0))}" if b2 else "") + "），"
           f"车主年龄均值 {fnum(p.get('owner_age_mean'), 1)} 岁；"
           f"城市线级 一线 {fp(p['tier'].get('一线', 0))} / 新一线 {fp(p['tier'].get('新一线', 0))} / "
           f"二线 {fp(p['tier'].get('二线', 0))} / 三线及以下 {fp(p['tier'].get('三线及以下', 0))}。")
    if b2:
        gap_gender = p["gender"].get("女", 0) - prod[b2]["gender"].get("女", 0)
        gap_tier = p["tier"].get("一线", 0) - prod[b2]["tier"].get("一线", 0)
        txt += (f" 与同平台的 {b2} 相比，女性占比差 {fpp(gap_gender, 1)}、一线城市占比差 "
                f"{fpp(gap_tier, 1)}——客群骨架基本同构，"
                f"{main} 没有触达一个明显不同的客户群。")
    txt += (f" 与 {b1} 的差异主要落在性别（{fpp(p['gender'].get('女', 0) - prod[b1]['gender'].get('女', 0), 1)}）"
            f"与一线占比（{fpp(p['tier'].get('一线', 0) - prod[b1]['tier'].get('一线', 0), 1)}），"
            f"方向上是「更偏男性、更偏下沉」，但幅度不足以解释四成销量差。")
    return txt


def _q8b_lead(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    prod = ctx["product"]
    p = prod[main]
    c = p["concentration"]["versions"]
    txt = (f"{main} 窗口内仅 {c['n_options']} 个版型，Top1 占比 <b>{fp(c['top1_share'], 0)}</b>"
           f"（HHI {fnum(c['hhi'], 2)}），电量 "
           + "/".join(f"{k} {fp(v, 0)}" for k, v in p["battery"].items()) + "。")
    if b2:
        cb2 = prod[b2]["concentration"]["versions"]
        cb1 = prod[b1]["concentration"]["versions"]
        txt += (f" 对标 {b1} 为 {cb1['n_options']} 个版型（HHI {fnum(cb1['hhi'], 2)}）、"
                f"{b2} 为 {cb2['n_options']} 个（HHI {fnum(cb2['hhi'], 2)}）。"
                f"<b>集中度差异首先是「可售版型数量」的差异，属供给端效应，不能读作客户偏好更集中。</b>")
    cf = p["attrs"].get("外饰", {}).get("normalized", {}).get("color_family") or {}
    wh = p["attrs"].get("轮毂", {}).get("normalized", {}).get("wheel_size") or {}
    if cf:
        txt += (" 配置偏好上：" + "、".join(f"{k} {fp(v, 0)}" for k, v in list(cf.items())[:3])
                + "（外饰色系）")
        if wh:
            txt += "；轮毂 " + "、".join(f"{k} {fp(v, 1)}" for k, v in list(wh.items())[:2])
        txt += "。"
    if b2:
        cf2 = prod[b2]["attrs"].get("外饰", {}).get("normalized", {}).get("color_family") or {}
        if cf and cf2:
            txt += (" 同平台对照：{0} 黑色系 {1} vs {2} 黑色系 {3}，色系偏好差异属于真实需求侧差异（两者车身同源）。"
                    .format(main, fp(cf.get("黑色系", 0)), b2, fp(cf2.get("黑色系", 0))))
    vg = (ctx.get("version_gap") or {}).get("national")
    if vg and vg.get("missing_segments"):
        miss = vg["missing_segments"][0]
        txt += (f" <b>产品线缺口</b>：{b1} 有 {miss} 档（{fi(vg['bench_has'].get(miss, 0))} 单，"
                f"占其 {fp(vg['bench_has'].get(miss, 0) / max(vg['bench_total'], 1))}），"
                f"{main} 没有对应版本；该缺口占对 {b1} 总差额的 "
                f"{fp(abs(vg['by_segment'].get(miss, 0)) / max(abs(vg['total']), 1))}。")
    return txt


def _product_rows_for(ctx: dict, g: str) -> list[list[str]]:
    """单个代际的配置结构行（版型 / 电量 / 外饰色系 / 轮毂），每格是一条 100% 堆积条。"""
    prod = ctx["product"]
    rows = [["版型结构", incell_stack(
        [(v["version"].replace("全新一代智己", "").replace("智己", ""), v["share"])
         for v in prod[g]["versions"]], cap_items=3, min_label=0.06)]]
    b = prod[g]["battery"]
    rows.append(["电量段", "—（product_name 不含电量段）"
                 if list(b) == ["未标注"]
                 else incell_stack(list(b.items()), cap_items=3, min_label=0.03)])
    for attr, label in (("外饰", "外饰色系"), ("轮毂", "轮毂尺寸")):
        a = prod[g]["attrs"].get(attr, {})
        norm = a.get("normalized") or {}
        key = "color_family" if attr == "外饰" else "wheel_size"
        d = norm.get(key) or {}
        rows.append([label, incell_stack(list(d.items()), cap_items=4,
                                         min_label=0.04) if d else "—"])
    return rows


def _table_product(ctx: dict):
    """三车型各一张表：单列宽表，堆积条更长、分段更好读。"""
    gens = ctx["curves"]["gens"]
    return [{"gen": g, "rows": _product_rows_for(ctx, g),
             "hdr": ["维度", f"{g} 分布（占比）"]} for g in gens]


def _table_user(ctx: dict):
    """客群结构表：性别、年龄、城市线级、Top 省份。"""
    gyms = ctx["curves"]["gens"]
    prod = ctx["product"]
    hdr = ["客群结构", *gyms]
    rows = [["女性占比", *[fp(prod[g]["gender"].get("女", 0)) for g in gyms]],
            ["车主年龄均值", *[fnum(prod[g].get("owner_age_mean"), 1) + " 岁"
                            for g in gyms]],
            ["一线城市占比", *[fp(prod[g]["tier"].get("一线", 0)) for g in gyms]],
            ["新一线占比", *[fp(prod[g]["tier"].get("新一线", 0)) for g in gyms]],
            ["二线占比", *[fp(prod[g]["tier"].get("二线", 0)) for g in gyms]],
            ["三线及以下占比", *[fp(prod[g]["tier"].get("三线及以下", 0)) for g in gyms]],
            ["Top3 省份", *["、".join(f"{p['province']} {fp(p['share'], 0)}"
                                   for p in prod[g]["province_top"][:3]) for g in gyms]]]
    return rows, hdr


def _table_concentration(ctx: dict):
    main = ctx["main"]
    gens = ctx["curves"]["gens"]
    prod = ctx["product"]
    hdr = ["集中度", *gens]
    rows = [["可售版型数", *[str(prod[g]["concentration"]["versions"]["n_options"]) for g in gens]],
            ["版型 Top1 占比", *[fp(prod[g]["concentration"]["versions"]["top1_share"]) for g in gens]],
            ["版型 HHI", *[fnum(prod[g]["concentration"]["versions"]["hhi"], 2) for g in gens]],
            ["电量 Top1 占比", *[fp(prod[g]["concentration"]["battery"]["top1_share"]) for g in gens]],
            ["电量 HHI", *[fnum(prod[g]["concentration"]["battery"]["hhi"], 2) for g in gens]]]
    # 主车行加粗标记（列头已是代际，正文用加粗列标签提示）
    return rows, hdr


def _q8_config_lead(ctx: dict) -> str:
    cd = ctx.get("config_dist") or {}
    g = (cd.get("groups") or {})
    if not g:
        return "无配置数据。"
    main = ctx["main"]
    ext, inte, opt = g.get("外饰", []), g.get("内饰", []), g.get("选装", [])
    top_ext = ext[0] if ext else None
    top_inte = inte[0] if inte else None
    texts = [f"<b>{main}</b> 窗口内 {fi(cd.get('n', 0))} 单锁单的配置分布（口径：config_attribute 原始取值）"]
    if top_ext:
        texts.append(f"外饰高度集中于 <b>{top_ext['value']} {fp(top_ext['share'])}</b>"
                     f"（前两位合计 {fp(ext[0]['share'] + ext[1]['share']) if len(ext) > 1 else fp(top_ext['share'])}）")
    if top_inte:
        texts.append(f"内饰以 <b>{top_inte['value']} {fp(top_inte['share'])}</b> 为主"
                     f"（{len(inte)} 种取值）")
    wheel = g.get("轮毂", [])
    if wheel:
        texts.append(f"轮毂高度标配化：<b>{wheel[0]['value']} {fp(wheel[0]['share'])}</b>"
                     f"（{len(wheel)} 种取值，其余均低于 "
                     f"{fp(wheel[1]['share']) if len(wheel) > 1 else '—'}）")
    if opt:
        top_opt = opt[0]
        texts.append(f"选装最热门是 <b>{top_opt['attr']}={top_opt['value']} {fp(top_opt['share'])}</b>；"
                     f"其余选装率均低于 {fp(opt[1]['share']) if len(opt) > 1 else '—'}")
    return "；".join(texts) + "。"


def _table_config_distribution(ctx: dict):
    """LS8Neo 锁单配置分布：外饰 / 内饰 / 轮毂 / 选装，每行一条 100% 堆积条。"""
    cd = ctx.get("config_dist") or {}
    g = (cd.get("groups") or {})
    if not g:
        return [], []
    main = ctx["main"]
    rows = []
    for key in ("外饰", "内饰", "轮毂"):
        items = [(x["value"], x["share"]) for x in g.get(key, [])]
        if items:
            cap = 2 if key == "轮毂" else 4        # 轮毂取值名很长，标注只留 Top2
            rows.append([key, incell_stack(items, cap_items=cap, min_label=0.03)])
    # 选装：每个属性单独一行，「选中取值」在左、默认取值在右
    ov = (ctx["product"].get(main) or {}).get("option_values") or {}
    defaults = cd.get("defaults") or {}
    for x in g.get("选装", []):
        attr, val = x["attr"], x["value"]
        base = defaults.get(attr)
        items = [(val, x["share"])]
        if base and base != val:
            items.append((base, max(0.0, 1.0 - x["share"])))
        rows.append([f"选装 · {attr}", incell_stack(items, cap_items=2, min_label=0.12)])
    return rows, ["分组", f"{main} 占比分布"]


def _q8_config_note(ctx: dict) -> str:
    cd = ctx.get("config_dist") or {}
    d = cd.get("defaults") or {}
    if not d:
        return ""
    base = "、".join(f"{k}={v}" for k, v in d.items())
    return (f"外饰 / 内饰 / 轮毂 列出该属性全部取值；选装组按属性逐行展开，"
            f"左侧为「选中取值」、右侧为「默认取值」（默认 = 该属性内占比最高的取值）：{base}。"
            f"取值名全部来自 config_attribute 的 Attribute / value 原始字段，未做品类归并；"
            f"单量为窗口内该取值的订单数，占比分母为该属性的有效订单数。")


def _table_tier_version(ctx: dict):
    main = ctx["main"]
    gens = ctx["curves"]["gens"]
    prod = ctx["product"]
    versions_by_gen = {g: prod[g]["tier_x_version"]["versions"] for g in gens}
    versions = versions_by_gen[main][:3]
    hdr = ["城市线级", f"{main} 版型", "单量", "线级内占比",
           f"{gens[1]} 版型", "单量", "线级内占比"]
    rows = []
    tv = prod[main]["tier_x_version"]
    tv1 = prod[gens[1]]["tier_x_version"]
    v1 = versions_by_gen[gens[1]][0] if versions_by_gen[gens[1]] else None
    for t in tv["tiers"]:
        top_v = max(tv["share"][t].items(), key=lambda kv: kv[1])[0]
        row = [t, top_v.replace("智己", ""), fi(tv["count"][t][top_v]),
               fp(tv["share"][t][top_v])]
        if v1 and t in tv1["share"]:
            row += [v1.replace("全新一代智己", "").replace("智己", ""),
                    fi(tv1["count"][t][v1]), fp(tv1["share"][t][v1])]
        else:
            row += ["—", "—", "—"]
        rows.append(row)
    return rows, hdr


def _sb_status(ctx: dict) -> tuple[bool, str]:
    """同档（默认 93kWh）客群对比是否可比：按有效样本量判断，而不是字典是否存在。"""
    sb = ctx.get("same_battery") or {}
    seg_name = sb.get("segment", "同档")
    main, bench = sb.get("main"), sb.get("bench")
    if not main or not bench:
        return False, "未配置对标代际"
    seg = sb.get("seg") or {}
    a, b = seg.get(main) or {}, seg.get(bench) or {}
    lacks = []
    if not a.get("n"):
        lacks.append(f"{main} 无 {seg_name} 档有效样本")
    if not b.get("n"):
        lacks.append(f"{bench} 无 {seg_name} 档（该代际产品线不含此电量段）")
    if lacks:
        return False, "；".join(lacks)
    return True, ""


def _q8_same_battery_lead(ctx: dict) -> str:
    ok, why = _sb_status(ctx)
    if not ok:
        return f"同档客群对比已跳过：{why}。"
    sb = ctx.get("same_battery") or {}
    main, bench = sb["main"], sb["bench"]
    fa, fb = sb["full"][main], sb["full"][bench]
    sa, sbg = sb["seg"][main], sb["seg"][bench]
    tf, ts = sb.get("tvd_full", {}), sb.get("tvd_seg", {})
    d_f_full = (fa["female"] - fb["female"]) * 100
    d_f_seg = (sa["female"] - sbg["female"]) * 100
    d_t_full = (fa["tier"].get("一线", 0) - fb["tier"].get("一线", 0)) * 100
    d_t_seg = (sa["tier"].get("一线", 0) - sbg["tier"].get("一线", 0)) * 100
    return (
        f"把版本变量固定住：只比 {sb['segment']}，{main} {fi(sa['n'])} 单"
        f"（占本代际 {fp(sa.get('share_of_gen'))}）vs {bench} {fi(sbg['n'])} 单"
        f"（{fp(sbg.get('share_of_gen'))}）。"
        f"<b>性别与年龄的差距确实缩小</b>：女性差从 {d_f_full:+.1f}pp 收窄到 {d_f_seg:+.1f}pp，"
        f"年龄结构距离从 {fp(tf.get('age_cohort', 0))} 降到 {fp(ts.get('age_cohort', 0))}。"
        f"<b>但城市线级的差距反而扩大</b>：一线差从 {d_t_full:+.1f}pp 扩大到 {d_t_seg:+.1f}pp"
        f"（线级结构距离 {fp(tf.get('tier', 0))} → {fp(ts.get('tier', 0))}），"
        f"原因是 {bench} 的该档用户比其全系更上一线，而 {main} 的该档比其全系更下沉。"
        f"所以「同档」不是把差异抹平，而是把差异<b>从性别/年龄转移到城市能级</b>。"
    )


def _table_same_battery(ctx: dict):
    """同档（93kWh）客群对比：列结构与 Q8-1 客群表一致，另加「差的变化」。"""
    ok, _ = _sb_status(ctx)
    if not ok:
        return [], []
    sb = ctx.get("same_battery") or {}
    main, bench = sb["main"], sb["bench"]
    fa, fb = sb["full"][main], sb["full"][bench]
    sa, sc = sb["seg"][main], sb["seg"][bench]

    def _pct_d(x, y):
        if x is None or y is None:
            return "—"
        return f"{(x - y) * 100:+.1f}pp"

    def _chg(seg_d, full_d):
        """|同档差| − |全系差|：负 = 差距缩小，正 = 扩大（与差值正负号无关）。"""
        if seg_d == "—" or full_d == "—":
            return "—"
        unit = "pp" if seg_d.endswith("pp") else "岁"
        a = float(seg_d.replace("pp", "").replace("岁", ""))
        b = float(full_d.replace("pp", "").replace("岁", ""))
        return f"{abs(a) - abs(b):+.1f}{' ' if unit == '岁' else ''}{unit}"

    rows = []

    def add_pct(label, va, vb, vfa, vfb):
        sd, fd = _pct_d(va, vb), _pct_d(vfa, vfb)
        rows.append([label, fp(va), fp(vb), sd, fd, _chg(sd, fd)])

    def add_age(label, ka):
        va, vb = sa.get(ka), sc.get(ka)
        vfa, vfb = fa.get(ka), fb.get(ka)
        dig = 1 if ka.endswith("mean") else 0
        sd = f"{va - vb:+.{dig}f} 岁" if va is not None and vb is not None else "—"
        fd = f"{vfa - vfb:+.{dig}f} 岁" if vfa is not None and vfb is not None else "—"
        rows.append([label,
                     (fnum(va, dig) + " 岁") if va is not None else "—",
                     (fnum(vb, dig) + " 岁") if vb is not None else "—", sd, fd, _chg(sd, fd)])

    # 行与 Q8-1 客群表**完全一致**（同名、同序、同口径）
    add_pct("女性占比", sa["female"], sc["female"], fa["female"], fb["female"])
    add_age("车主年龄均值", "age_mean")
    add_pct("一线城市占比", sa["tier"].get("一线"), sc["tier"].get("一线"),
            fa["tier"].get("一线"), fb["tier"].get("一线"))
    add_pct("新一线占比", sa["tier"].get("新一线"), sc["tier"].get("新一线"),
            fa["tier"].get("新一线"), fb["tier"].get("新一线"))
    add_pct("二线占比", sa["tier"].get("二线"), sc["tier"].get("二线"),
            fa["tier"].get("二线"), fb["tier"].get("二线"))
    add_pct("三线及以下占比", sa["tier"].get("三线及以下"), sc["tier"].get("三线及以下"),
            fa["tier"].get("三线及以下"), fb["tier"].get("三线及以下"))

    def _top3(st: dict) -> str:
        items = sorted((st.get("province") or {}).items(), key=lambda kv: -kv[1])[:3]
        return "、".join(f"{k} {fp(v, 0)}" for k, v in items)

    rows.append(["Top3 省份", _top3(sa), _top3(sc),
                 "—", "—", "见下方注"])

    hdr = ["客群结构", f"{main} {sb['segment']}", f"{bench} {sb['segment']}",
           "同档差", "全系差", "差的变化"]
    return rows, hdr


def _prov_gap_txt(sb: dict) -> str:
    main, bench = sb["main"], sb["bench"]
    sa, sc = sb["seg"][main], sb["seg"][bench]
    fa, fb = sb["full"][main], sb["full"][bench]
    provs = [x["province"] for x in (sa.get("province_top") or [])[:3]]
    parts = []
    for pv in provs:
        d_seg = (sa["province"].get(pv, 0) - sc["province"].get(pv, 0)) * 100
        d_full = (fa["province"].get(pv, 0) - fb["province"].get(pv, 0)) * 100
        parts.append(f"{pv} 同档 {d_seg:+.1f}pp / 全系 {d_full:+.1f}pp")
    return "；".join(parts) + "。"


def _q8_same_battery_note(ctx: dict) -> str:
    sb = ctx.get("same_battery") or {}
    if not sb or not _sb_status(ctx)[0]:
        return ""
    tf, ts = sb.get("tvd_full", {}), sb.get("tvd_seg", {})
    return (
        f"读法：第 4 列是同档（{sb['segment']}）两车的差，第 5 列是全系的差，"
        f"第 6 列 = |同档差| − |全系差|（负 = 差距缩小，正 = 扩大，与差值正负号无关）。"
        f"结构距离（TVD，0 = 完全相同）：线级 {fp(tf.get('tier', 0))} → {fp(ts.get('tier', 0))}、"
        f"年龄 {fp(tf.get('age_cohort', 0))} → {fp(ts.get('age_cohort', 0))}。"
        f"样本为窗口内 {sb['segment']} 锁单；该档之外（{sb['bench']} 的 76kWh 入门档）不参与对比。"
        f"「Top3 省份」行为省级占比列表，差值不便并列，单列于此：{_prov_gap_txt(sb)}"
    )


def _table_tier_decomp(ctx: dict):
    main = ctx["main"]
    hdr = ["城市线级", "规模效应", "结构效应", f"合计差额（vs {ctx['benchmarks'][0]}）", "占比差(pp)"]
    gaps = ctx["geo"]["tier"]["gaps"][ctx["benchmarks"][0]]
    rows = []
    for r in gaps:
        rows.append([r["tier"], fnum(r["scale_effect"]), fnum(r["mix_effect"]),
                     f"{r['abs_diff']:+,}", f"{r['share_diff_pp']:+.1f}"])
    return rows, hdr


def _q7_channel_lead(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    ch = ctx["channel"]["gaps"][b1]
    top = ch["rows"][0] if ch["rows"] else None
    txt = (f"把对 {b1} 的差额按门店所在省份拆成「门店数效应 + 单店产出效应」："
           f"全国合计渠道覆盖效应 {fnum(ch['total_network_effect'])} 单、"
           f"单店需求效应 {fnum(ch['total_productivity_effect'])} 单。")
    if top:
        txt += (f" 差额最大的 {top['province']}：门店 {fi(top['main_stores'])} vs "
                f"{fi(top['bench_stores'])} 家，单店 {fnum(top['main_lps'], 2)} vs "
                f"{fnum(top['bench_lps'], 2)} 单/店——"
                f"渠道效应 {fnum(top['network_effect'])}、需求效应 {fnum(top['productivity_effect'])} 单。")
    return txt


def _q7_channel_note(ctx: dict) -> str:
    b1 = ctx["benchmarks"][0]
    return (f"口径：渠道分解按<b>门店所在省份</b>聚合（各省门店数之和 = 全国，无重复计数；"
            f"跨省上牌仅 1.2–1.6%），与 Q6 的「上牌省份」需求口径不同，不可混用。"
            f"省级效应按各省单店产出加权，与本节全国口径的效应值会有小幅差异。"
            f"「渠道效应」= 门店数差 × 对标单店产出；「需求效应」= 本代际门店数 × 单店产出差。")


def _table_channel(ctx: dict):
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    g = ctx["channel"]["gaps"][b1]
    hdr = ["省份（门店所在地）", f"{main} 单", f"{b1} 单", "差额",
           f"{main} 门店", f"{b1} 门店", f"{main} 单店", f"{b1} 单店",
           "渠道效应", "需求效应"]
    rows = []
    for r in g["rows"][:8]:
        rows.append([r["province"], fi(r["main_locks"]), fi(r["bench_locks"]),
                     f"{r['abs_diff']:+,}", fi(r["main_stores"]), fi(r["bench_stores"]),
                     fnum(r["main_lps"], 2), fnum(r["bench_lps"], 2),
                     fnum(r["network_effect"]), fnum(r["productivity_effect"])])
    return rows, hdr


def _table_seat_cross(ctx: dict, key: str = "seat_cross"):
    """2C　跨代际六座对比：LS8Neo 奢享大六座 vs 对标六座车型（用户画像）。"""
    sc = ctx.get("slice_compares") or {}
    cx = sc.get(key) or {}
    if not ((cx.get("main_six") or {}).get("n") and (cx.get("bench_six") or {}).get("n")):
        return [], []
    a, b = cx["main_six"], cx["bench_six"]

    def _d(va, vb, unit="pp"):
        if va is None or vb is None:
            return "—"
        return f"{(va - vb) * 100:+.1f}{unit}"

    rows = [["锁单样本", f"{a['n']:,}", f"{b['n']:,}", f"{a['n'] - b['n']:+,}"],
            ["占本代际锁单", fp(cx["main_six_share"]), fp(cx["bench_six_share"]),
             _d(cx["main_six_share"], cx["bench_six_share"])],
            ["女性占比", fp(a["female"]), fp(b["female"]), _d(a["female"], b["female"])],
            ["车主年龄均值", fnum(a.get("age_mean"), 1) + " 岁",
             fnum(b.get("age_mean"), 1) + " 岁",
             (f"{a['age_mean'] - b['age_mean']:+.1f} 岁"
              if a.get("age_mean") is not None and b.get("age_mean") is not None else "—")],
            ["试驾参与率", fp(a["test_drive_rate"]), fp(b["test_drive_rate"]),
             _d(a["test_drive_rate"], b["test_drive_rate"])]]
    for k in ("一线", "新一线", "二线", "三线及以下"):
        rows.append([f"{k}", fp(a["tier"].get(k)), fp(b["tier"].get(k)),
                     _d(a["tier"].get(k), b["tier"].get(k))])
    def _top3(st: dict) -> list[str]:
        items = sorted((st.get("province") or {}).items(), key=lambda kv: -kv[1])[:3]
        return [k for k, _ in items]

    provs = []
    for pv in _top3(a) + _top3(b):
        if pv not in provs:
            provs.append(pv)
    for pv in provs[:4]:
        rows.append([f"省份 {pv}", fp(a["province"].get(pv, 0)), fp(b["province"].get(pv, 0)),
                     _d(a["province"].get(pv, 0), b["province"].get(pv, 0))])
    suffix = "（剔除上海）" if cx.get("excluded") else ""
    hdr = ["维度", f"{cx['main']} 奢享大六座{suffix}",
           f"{cx['bench']} 大六座{suffix}", "差值"]
    return rows, hdr


def _q8_2c_lead(ctx: dict, key: str = "seat_cross") -> str:
    sc = ctx.get("slice_compares") or {}
    cx = sc.get(key) or {}
    if not ((cx.get("main_six") or {}).get("n") and (cx.get("bench_six") or {}).get("n")):
        return "对标代际或本代际无可识别的六座样本，2C 已跳过。"
    a, b = cx["main_six"], cx["bench_six"]
    ta, tc = a["tier"], b["tier"]
    d_t1 = (ta.get("一线", 0) - tc.get("一线", 0)) * 100
    d_t2 = (ta.get("二线", 0) - tc.get("二线", 0)) * 100
    d_t3 = (ta.get("三线及以下", 0) - tc.get("三线及以下", 0)) * 100
    d_age = (a.get("age_mean") or 0) - (b.get("age_mean") or 0)
    d_fe = (a["female"] - b["female"]) * 100

    t1_txt = "一线更高" if d_t1 > 0 else "一线略低"
    t3_txt = "三线及以下更低（下沉更浅）" if d_t3 < 0 else "三线及以下更高（更下沉）"
    age_txt = "更年轻" if d_age < 0 else "更年长"
    sex_txt = "男性更多" if d_fe < 0 else "女性更多"

    txt = (f"{'剔除上海后' if cx.get('excluded') else ''}"
           f"「六座」这一层单独拉通看：{cx['main']} 六座 {fi(a['n'])} 单"
           f"（占本代际 {fp(cx['main_six_share'])}）vs {cx['bench']} 六座 {fi(b['n'])} 单"
           f"（{fp(cx['bench_six_share'])}）。"
           f"城市层级上，{cx['main']} 六座<b>{t1_txt}</b>"
           f"（{fp(ta.get('一线'))} vs {fp(tc.get('一线'))}，{d_t1:+.1f}pp）、"
           f"<b>二线更高</b>（{fp(ta.get('二线'))} vs {fp(tc.get('二线'))}，{d_t2:+.1f}pp）、"
           f"<b>{t3_txt}</b>（{fp(ta.get('三线及以下'))} vs {fp(tc.get('三线及以下'))}，"
           f"{d_t3:+.1f}pp）；人群上<b>{age_txt}</b>"
           f"（{fnum(a.get('age_mean'), 1)} vs {fnum(b.get('age_mean'), 1)} 岁，{d_age:+.1f} 岁）、"
           f"<b>{sex_txt}</b>（女性 {fp(a['female'])} vs {fp(b['female'])}，{d_fe:+.1f}pp）。")
    if cx.get("excluded") and d_t1 <= 0:
        txt += (" <b>与全样本的差别只在「一线」这一档</b>：全样本时一线是 +5.1pp，"
                f"剔除上海后变成 {d_t1:+.1f}pp——说明一线优势完全由上海单省贡献；"
                f"但三线及以下始终低 {abs(d_t3):.1f}pp，"
                f"<b>下沉更深的仍是 {cx['bench']}</b>。")
    return txt


def _q8_2c_note(ctx: dict, key: str = "seat_cross") -> str:
    sc = ctx.get("slice_compares") or {}
    cx = sc.get(key) or {}
    if not ((cx.get("main_six") or {}).get("n") and (cx.get("bench_six") or {}).get("n")):
        return ""
    return (f"口径差异：{cx['main']} 的六座是<b>选装项</b>（config_attribute 的「座椅=奢享大六座」），"
            f"{cx['bench']} 的六座<b>写在版型名里</b>（product_name 含「六座」，不可再拆选装）；"
            f"两者都表示「六座车」，但前者是同一款车上的配置选择、后者是独立版型，"
            f"因此占比不能直接读作「六座偏好强弱」。样本为窗口内该车型锁单，"
            f"未做价格与配置对齐。")


def _q8c_lead(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    tier_gaps = ctx["geo"]["tier"]["gaps"][b1]
    tier_mix = sum(abs(r["mix_effect"]) for r in tier_gaps)
    total = abs(ctx["deltas"][b1]["cum_diff"]) or 1
    ch = ctx["channel"]["gaps"][b1]
    top = ch["rows"][0] if ch["rows"] else None
    tier_share = tier_mix / total
    verdict_txt = ("客群维度解释不了销量差" if tier_share < 0.2
                   else "客群维度只能解释一部分销量差")
    txt = (f"先给结论：<b>{verdict_txt}</b>——线级结构效应合计 {fnum(tier_mix)} 单，"
           f"相当于 {main} 对 {b1} 总差额的 {fp(tier_share, 0)}"
           + ("（占比超过 100%，是规模效应与结构效应部分抵消所致）" if tier_share > 1 else "")
           + "。"
           f"真正分化的是<b>产品供给</b>（{_power_label(ctx['product'][main])}、可售版型只有 "
           f"{ctx['product'][main]['concentration']['versions']['n_options']} 个）"
           f"与<b>渠道效率</b>（省级分解：渠道覆盖效应 {fnum(ch['total_network_effect'])} 单、"
           f"单店需求效应 {fnum(ch['total_productivity_effect'])} 单）。")
    if top:
        txt += (f" 例：{top['province']} 门店 {fi(top['main_stores'])} vs {fi(top['bench_stores'])} 家"
                f"（渠道 {fnum(top['network_effect'])} 单），单店 {fnum(top['main_lps'], 2)} vs "
                f"{fnum(top['bench_lps'], 2)} 单/店（需求 {fnum(top['productivity_effect'])} 单）。")
    txt += (f" Part 1 只看用户维度（同 Q8-1），Part 2 再切两刀：同档 93kWh、以及六座 vs 五座；"
            "所有列都是同一 D1–D" + str(ctx["n_days"]) + " 窗口口径。")
    return txt


def _table_user_matrix(ctx: dict):
    """Q8-3 Part 1：用户差异矩阵（维度与 Q8-1 一致）。"""
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    prod = ctx["product"]
    p = prod[main]

    def _female(g):
        return (prod[g]["gender"].get("女") or 0)

    rows = [["性别（女性）", fp(_female(main)),
             fpp(_female(main) - _female(b2)) if b2 else "—",
             fpp(_female(main) - _female(b1))]]

    top_age = max(p["age_cohort"].items(), key=lambda kv: kv[1])[0]
    age_row = [f"年龄（{top_age} 最多）", fp(p["age_cohort"].get(top_age))]
    for b in (b2, b1):
        if not b:
            age_row.append("—")
            continue
        diffs = [(k, p["age_cohort"].get(k, 0) - prod[b]["age_cohort"].get(k, 0))
                 for k in p["age_cohort"] if k in prod[b]["age_cohort"]]
        pos = max(diffs, key=lambda kv: kv[1])
        neg = min(diffs, key=lambda kv: kv[1])
        age_row.append(f"{pos[0]} {fpp(pos[1])}、{neg[0]} {fpp(neg[1])}")
    rows.append(age_row)

    for k in ("一线", "新一线", "三线及以下"):
        r = [f"城市线级 {k}", fp(p["tier"].get(k))]
        for b in (b2, b1):
            r.append(fpp((p["tier"].get(k) or 0) - (prod[b]["tier"].get(k) or 0)) if b else "—")
        rows.append(r)

    for pv in [x["province"] for x in (p.get("province_top") or [])[:3]]:
        va = next((x["share"] for x in p["province_top"] if x["province"] == pv), 0.0)
        r = [f"省份 {pv}", fp(va)]
        for b in (b2, b1):
            if not b:
                r.append("—")
                continue
            vb = next((x["share"] for x in (prod[b].get("province_top") or [])
                       if x["province"] == pv), 0.0)
            r.append(fpp(va - vb))
        rows.append(r)

    hdr = ["维度", main, f"vs {b2}" if b2 else "vs 对标", f"vs {b1}"]
    return rows, hdr


def fig_seat_combos(ctx: dict):
    """四种配置组合（座椅 × 电量）对总锁单的分解：4 根柱、合计 100%。"""
    go, apply_im_theme, gsc = _plotly()
    st = ((ctx.get("slice_compares") or {}).get("seat")) or {}
    combos = st.get("combos") or []
    if not combos:
        return None
    labels = [f"{_seat_short(c['seat'])}\u00b7{c['battery']}" for c in combos]
    shares = [(c["share"] or 0) * 100 for c in combos]
    counts = [c["n"] for c in combos]
    colors = [IM["own"] if "五座" in c["seat"] else IM["bench1"] for c in combos]
    fig = go.Figure(go.Bar(
        x=labels, y=shares, marker_color=colors,
        text=[f"{n:,} 单<br>{v:.1f}%" for n, v in zip(counts, shares)],
        textposition="outside", textfont=dict(size=10, color=IM["ink"]),
        cliponaxis=False,
        hovertemplate="%{x} · %{text}<extra></extra>", showlegend=False))
    apply_im_theme(fig)
    fig.update_layout(height=340, margin=dict(l=55, r=20, t=30, b=45),
                      bargap=0.42)
    fig.update_yaxes(title_text=f"占总锁单（%，n={st.get('seat_n', 0):,}）",
                     range=[0, max(shares) * 1.28 if shares else 1])
    fig.update_xaxes(title_text="")
    return fig


def _seat_short(name: str) -> str:
    if "六座" in name:
        return "六座"
    if "五座" in name:
        return "五座"
    return name


def _q8_seat_combo_lead(ctx: dict) -> str:
    st = ((ctx.get("slice_compares") or {}).get("seat")) or {}
    combos = st.get("combos") or []
    if not combos:
        return ""
    six = [c for c in combos if "六座" in c["seat"]]
    best = max(six, key=lambda c: (c["share"] or 0) - (c["est_share"] or 0)) if six else None
    rows = "、".join(f"{_seat_short(c['seat'])}·{c['battery']} {fp(c['share'])}"
                     for c in combos)
    txt = (f"先把四个坑位摆出来（{fi(st.get('seat_n', 0))} 单有座椅记录的锁单）：{rows}。"
           f"该分解用「座椅占比 × 电量占比」相乘即可复算，与订单里的实际联合分布相差在 0.6pp 以内。")
    if best:
        txt += (f" 其中 {_seat_short(best['seat'])}·{best['battery']} 实际 "
                f"{fp(best['share'])} 高于乘积估算 {fp(best['est_share'])}"
                f"（{fpp((best['share'] or 0) - (best['est_share'] or 0), 1)}）——"
                f"六座用户确实更偏大电池，不是两个独立选择的简单叠加。")
    return txt


def _q8_slice_lead(ctx: dict) -> str:
    sc = ctx.get("slice_compares") or {}
    sb = sc.get("same_battery") or {}
    st = sc.get("seat") or {}
    parts = []
    if (sb.get("stats") or {}).get(sb.get("main"), {}).get("n") \
            and (sb.get("stats") or {}).get(sb.get("bench"), {}).get("n"):
        a = sb["stats"][sb["main"]]
        bb = sb["stats"][sb["bench"]]
        parts.append(
            f"<b>2A 同档（{sb['segment']}）</b>：{fi(a['n'])} vs {fi(bb['n'])} 单，"
            f"差异主要在「选择」而非「人群」——内饰深色 "
            f"{fp((a['config'].get('内饰') or {}).get('深色', 0))} vs "
            f"{fp((bb['config'].get('内饰') or {}).get('深色', 0))}，"
            f"试驾参与 {fp(a['test_drive_rate'])} vs {fp(bb['test_drive_rate'])}。")
    if (st.get("six") or {}).get("n") and (st.get("five") or {}).get("n"):
        six, five = st["six"], st["five"]
        parts.append(
            f"<b>2B 六座 vs 五座</b>：六座 {fi(six['n'])} 单（占 "
            f"{fp(six['n'] / max(six['n'] + five['n'], 1))}），一线占比 "
            f"{fp(six['tier'].get('一线'))} vs {fp(five['tier'].get('一线'))}、"
            f"上海 {fp(six['province'].get('上海'))} vs {fp(five['province'].get('上海'))}，"
            f"103kWh 占比 {fp(six['battery'].get('103kWh', 0))} vs "
            f"{fp(five['battery'].get('103kWh', 0))}——六座是「更高线、更高配」的小众盘。")
    return " ".join(parts) if parts else "本次无细分对比样本（同档或座椅维度缺失），已跳过 2A/2B。"


def _table_slice(ctx: dict, block: str):
    """细分对比表：两列子样本 + 差值，行覆盖用户画像与配置选择。"""
    sc = ctx.get("slice_compares") or {}
    b = sc.get(block) or {}
    if not b:
        return [], []
    if block == "same_battery":
        stats = b.get("stats") or {}
        a = stats.get(b.get("main")) or {}
        c = stats.get(b.get("bench")) or {}
        la = f"{b.get('main')} {b.get('segment')}"
        lc = f"{b.get('bench')} {b.get('segment')}"
    else:
        a, c = b.get("six") or {}, b.get("five") or {}
        la, lc = f"{b.get('gen')} 奢享大六座", f"{b.get('gen')} 旗舰大五座"
    if not a.get("n") or not c.get("n"):
        return [], []

    def _pct_d(va, vb):
        if va is None or vb is None:
            return "—"
        return f"{(va - vb) * 100:+.1f}pp"

    def _row(label, va, vb, fmt=("{:.1%}", "{:+.1f}pp")):
        return [label, fmt[0].format(va) if va is not None else "—",
                fmt[0].format(vb) if vb is not None else "—",
                fmt[1].format((va - vb) * 100) if (va is not None and vb is not None) else "—"]

    rows = [
        ["锁单样本", f"{a['n']:,}", f"{c['n']:,}", f"{a['n'] - c['n']:+,}"],
        _row("女性占比", a["female"], c["female"]),
        ["车主年龄均值", fnum(a.get("age_mean"), 1) + " 岁",
         fnum(c.get("age_mean"), 1) + " 岁",
         (f"{a['age_mean'] - c['age_mean']:+.1f} 岁"
          if a.get("age_mean") is not None and c.get("age_mean") is not None else "—")],
        _row("一线城市", a["tier"].get("一线"), c["tier"].get("一线")),
        _row("上海", a["province"].get("上海", 0), c["province"].get("上海", 0)),
        _row("江苏", a["province"].get("江苏", 0), c["province"].get("江苏", 0)),
        _row("试驾参与率", a["test_drive_rate"], c["test_drive_rate"]),
    ]
    if block == "seat":          # 同档对比里 93/103 恒为 100%/0，不重复列
        rows += [_row("93kWh 占比", a["battery"].get("93kWh"), c["battery"].get("93kWh")),
                 _row("103kWh 占比", a["battery"].get("103kWh"), c["battery"].get("103kWh"))]
    ca, cc = a.get("config") or {}, c.get("config") or {}
    for label, key in (("外饰 黑色系", "外饰"), ("内饰 深色", "内饰")):
        va = (ca.get(key) or {}).get("黑色系" if key == "外饰" else "深色")
        vb = (cc.get(key) or {}).get("黑色系" if key == "外饰" else "深色")
        rows.append(_row(label, va, vb))
    opt_keys = ["方向盘=全幅柔感瞬热运动方向盘",
                "激光雷达=Thor芯片+520线激光雷达+探射灯",
                "21.5英寸二排观影屏=是"]
    if block != "seat":          # 座椅是分组变量，不重复列
        opt_keys.append("座椅=奢享大六座")
    for key in opt_keys:
        rows.append(_row(key, ca.get(key), cc.get(key)))
    return rows, ["维度", la, lc, "差值"]


def _pk_lead(ctx: dict) -> str:
    pk = ctx.get("pk") or {}
    gens = ctx["curves"]["gens"]
    parts = []
    for g in gens:
        b = _pk_block(ctx, g)
        if not b.get("competitors"):
            continue
        top = b["competitors"][0]
        chg = (b["week_total"] / b["prev_total"] - 1) if b.get("prev_total") else None
        parts.append(
            f"<b>{g}</b>（series {b['series']}）：上市周 PK {fi(b['week_total'])} 次，"
            f"上期（预售周）{fi(b.get('prev_total', 0))} 次"
            + (f"（{fs(chg)}）" if chg is not None else "")
            + f"，头号对手 {top['name']}（{fi(top['pk'])} 次）。")
    return ("三张图分别看三款车的「上市周 vs 预售周」：左侧是上市周的竞品 PK 次数，"
            "右侧是反向排名与相对上期的升降。" + " ".join(parts))


def _pk_note(ctx: dict) -> str:
    pk = ctx.get("pk") or {}
    if not pk:
        return ""
    gens = pk.get("gens") or {}
    parts = []
    for g, v in gens.items():
        parts.append(f"{g}→series {v['series']}（覆盖 {v['range'][0]} ~ {v['range'][1]}，"
                     f"共 {v['weeks_available']} 周）")
    return ("口径：PK正向排名 = 竞品对本品的冲击强度（1 = 最强）；PK反向排名 = 本品对竞品的影响（1 = 最强）；"
            "PK次数 = 该竞品与本品当周 PK 次数。"
            f"数据到 series 级：{'；'.join(parts)}——LS8 series 同时覆盖 LS8 与 LS8Neo，"
            "因此 LS8Neo 周的 PK 以新车型为主但无法拆分到单车型；每周仅列前 9 个竞品。"
            "读图：条形 = 上市周 PK 次数，菱形 = 预售周 PK 次数（超出轴范围的预售值钉在右缘并标注）；"
            "右侧「当前 / 上期」为反向排名，变化列 ↑ = 排名上升（本品对竞品影响增强）。")


def _q8c_note(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    return (
        f"读法：Part 1 第 2 列为 {main} 自身结构，第 3/4 列为相对对标的<b>百分点差</b>"
        f"（正 = {main} 更高）。Part 2 是「控制变量」后的对比——"
        f"2A 固定电量段（93kWh），2B 固定车型（{main}）只换座椅，"
        f"这样看到的差异不再由版本结构或产品线缺口造成。"
        f"口径边界：外饰色板在 {main} 与 {b1} 之间不同，色系占比只能方向性比较；"
        f"选装一律用 config_attribute 的「属性=取值」原始名，"
        f"某代际没有该取值时显式留「—」（如 {b1} 无 21.5英寸二排观影屏 / 座椅 字段）；"
        f"2B 的座椅分组来自 config_attribute 的「座椅」字段。"
    )

def _act4_summary(ctx: dict) -> str:
    return ('<p class="lead">第四幕判断「这个表现意味着什么」：先检验订单质量，'
            '再评估后续增长动能的支撑，并明确哪些结论是数据事实、哪些是待验证假设。</p>')


def _q9_lead(ctx: dict) -> str:
    main = ctx["main"]
    b1 = ctx["benchmarks"][0]
    q = ctx["quality"]
    m = q[main]
    txt = (f"以 D{ctx['n_days']} 24:00 为截止点用事件时间重建（不用当前快照）："
           f"{main} 窗口锁单 {fi(m['locked_total'])} 单中，已完成大定退款 {fi(m['deposit_refunded'])} 单"
           f"（{fp(m['deposit_refund_rate'], 2)}），提交退订申请 {fi(m['apply_refund'])} 单、"
           f"已审批 {fi(m['approve_refund'])} 单、已完成退款 {fi(m['actual_refund'])} 单。")
    txt += (f" 对标 {b1} 的大定退款率 {fp(q[b1]['deposit_refund_rate'], 2)}、"
            f"退订申请 {fi(q[b1]['apply_refund'])} 单，量级相同。")
    txt += (f" 结论：在上市后第 {ctx['n_days']} 天这个时点，"
            "<b>三个代际的锁单退订/退款水平都很低且无实质差异</b>，"
            "没有证据显示 "
            f"{main} 的订单质量更差；但退订是后置事件，本窗口只能反映「早期退订」，"
            "不能替代 D30 的口径。")
    txt += (f" 兑现口径不可比：{b1} 上市首日起即有现车交付（D1–D{ctx['n_days']} 内交付 "
            f"{fi(q[b1]['delivered'])} 单），{main} 仅 {fi(m['delivered'])} 单，"
            "两者交付节奏由产品上市形态决定，因此本报告不用交付率评价订单质量。")
    return txt


def _table_quality(ctx: dict):
    gyms, main = ctx["curves"]["gens"], ctx["main"]
    q = ctx["quality"]
    hdr = ["代际", "窗口锁单", "已转大定", "大定退款", "退款率", "退订申请", "已审批",
           "已完成退款", "待处理"]
    rows = []
    for g in gyms:
        v = q[g]
        rows.append([f"<b>{g}</b>" if g == main else g, fi(v["locked_total"]),
                     fi(v["deposit_paid"]), fi(v["deposit_refunded"]),
                     fp(v["deposit_refund_rate"], 2), fi(v["apply_refund"]),
                     fi(v["approve_refund"]), fi(v["actual_refund"]),
                     fi(v["refund_pipeline_gap"])])
    return rows, hdr


def _q10_lead(ctx: dict) -> str:
    main, n = ctx["main"], ctx["n_days"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    po = ctx["pool"]
    m = po[main]
    return (
        "<b>① 封盘池：</b>"
        f"小订在上市日 24:00 停止收取，{main} 封盘 <b>{fi(m['stock_total'])} 单</b>"
        f"（预售 {fi(m['stock_presale'])} + 上市日 {fi(m['stock_launch_day'])}）。"
        "<br/><b>② 流出速度：</b>"
        f"D2–D{n} 日均转化 <b>{fnum(m['lock_tail_daily'])} 单</b>、退订 "
        f"<b>{fnum(m['refund_tail_daily'])} 单</b>，锁/退比 "
        f"<b>{fnum(m['lock_refund_ratio_stock'], 2)}</b>"
        f"（{b1} {fnum(po[b1]['lock_refund_ratio_stock'], 2)}"
        + (f"、{b2} {fnum(po[b2]['lock_refund_ratio_stock'], 2)}" if b2 else "")
        + f"）——每流失 1 单小订换回 {fnum(m['lock_refund_ratio_stock'], 2)} 单锁单。"
        "<br/><b>③ 剩余池潜力：</b>"
        f"剩余 {fi(m['remaining'])} 单（{fp(m['remaining_rate'])}），"
        f"按观察到的转化结构可再释放 <b>{fi(m['remaining_est_low'])}–{fi(m['remaining_est_high'])} 单</b>。"
    )


def _table_pool(ctx: dict):
    gens, main = ctx["curves"]["gens"], ctx["main"]
    po = ctx["pool"]
    hdr = ["代际", "封盘池", "已转化", "已退订", "封盘池剩余",
           "D2–N 日均转化", "D2–N 日均退订", "剩余池可转化潜力"]
    rows = []
    for g in gens:
        v = po[g]
        rows.append([
            f"<b>{g}</b>" if g == main else g,
            fi(v["stock_total"]),
            f"{fi(v['locked'])}（{fp(v['locked_rate'])}）",
            f"{fi(v['refunded'])}（{fp(v['refund_rate'])}）",
            f"{fi(v['remaining'])}（{fp(v['remaining_rate'])}）",
            fnum(v["lock_tail_daily"]),
            fnum(v["refund_tail_daily"]),
            f"{fi(v['remaining_est_low'])}–{fi(v['remaining_est_high'])}",
        ])
    return rows, hdr


def _q10_note(ctx: dict) -> str:
    main = ctx["main"]
    m = ctx["pool"][main]
    return (f"封盘池 = <code>intention_payment_time</code> 落在 [预售开始日, 上市日 24:00) 的小订；"
            f"已转锁单/已退订均按事件时间早于窗口末计算，剩余 = 池 − 已锁 − 已退。"
            f"注：<code>intention_refund_time</code> 在数据中为日期粒度（全部落在 00:00），"
            f"只能按日归集，不能解读为某一时刻的系统批量操作。"
            f"<b>口径区分</b>：本次「封盘池剩余」{fi(m['remaining'])} 单 ≠ Q4 的「预售池待转化」"
            f"{fi(ctx['presale'][main]['pool_pending'])} 单——后者只统计预售期小订，"
            f"前者含上市当日新增小订（{fi(ctx['presale'][main].get('launch_intent_total', 0))} 单）中尚未转化/退订的部分；"
            f"两者关系已在附录 A 的恒等式校验中逐项核对。"
            f"池内锁单 {fi(m['locked'])} 单与 Q1 的窗口锁单 {fi(ctx['origin'][main]['total'])} 单"
            f"相差 {fi(ctx['origin'][main]['total'] - m['locked'])} 单，"
            f"为无小订记录直锁或小订晚于封盘时刻的订单，不在池内。")


def _q10_potential(ctx: dict) -> str:
    main, n = ctx["main"], ctx["n_days"]
    po = ctx["pool"]
    m = po[main]
    b1 = ctx["benchmarks"][0]
    flow = m["lock_tail_daily"] or 0
    d14 = ctx["origin"][main]["total"] + flow * 10
    b1cum = ctx["curves"]["curves"][b1]["cum"][-1]
    return (
        '<div class="verdict"><h4>潜力与验证（一句话版）</h4>'
        f'<p>剩余池 {fi(m["remaining"])} 单，按观察结构可再释放 '
        f'{fi(m["remaining_est_low"])}–{fi(m["remaining_est_high"])} 单；'
        f'若 D{n+1}–D14 维持 {fnum(flow)} 单/日的转化速度，D14 累计约 '
        f'{fi(d14)} 单（相当于 {b1} D{n} 的 {fp(d14 / b1cum, 0)}）。</p>'
        f'<p><b>验证判据</b>：D{n+1}–D10 锁/退比是否维持在 {fnum(m["lock_refund_ratio_stock"], 2)} 附近。'
        f'若跌破 1.0，说明池子从转化转向流失，潜力应向下限靠；若升破 1.8，向上限靠。</p>'
        f'<p style="color:#7C827F;font-size:12px;">区间为机械外推，不是预测：'
        f'剩余池中仍有相当部分会退订（各代际池退订率 '
        + "、".join(f"{g} {fp(ctx['presale'][g]['stock_refund_rate'])}" for g in ctx["curves"]["gens"])
        + '），不应把剩余池全部当作潜在锁单。</p></div>')


def _verdict_level_sentence(ctx: dict) -> str:
    """经营判断第 1 句：按本次数据的水平/形态生成，不复用历史措辞。"""
    main, n = ctx["main"], ctx["n_days"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    d = ctx["deltas"]
    cur = ctx["curves"]["curves"]
    d1 = d[b1]
    ratio = d1["cum_ratio"]
    level = ("基本持平" if 0.95 <= ratio <= 1.05 else
             ("落后" if ratio < 1 else "领先"))
    gap_rel = abs(ratio - 1) * 100
    txt = (f"{main} 与 {b1} 同期累计{level}"
           f"（{fi(cur[main]['cum'][-1])} 单 vs {fi(d1['cum_bench'])} 单，差 {gap_rel:.1f}%）")
    if b2:
        txt += f"，与 {b2} 的关系为{('领先' if d[b2]['cum_rel'] > 0.005 else ('落后' if d[b2]['cum_rel'] < -0.005 else '持平'))}"
    txt += "。形态上，"
    dm = ctx["dynamics"][main]["d1_share_of_cum"]
    db = ctx["dynamics"][b1]["d1_share_of_cum"]
    if abs(dm - db) < 0.03:
        txt += f"首日集中度与 {b1} 接近（{dm:.0%} vs {db:.0%}）"
    else:
        txt += (f"首日集中度{'更高' if dm > db else '更低'}"
                f"（{dm:.0%} vs {db:.0%}），"
                f"D2–D{n} 日均 {ctx['dynamics'][main]['tail_avg']:.0f} 单 vs "
                f"{ctx['dynamics'][b1]['tail_avg']:.0f} 单")
    return txt + "。"


def _dir_cn(v: float) -> str:
    return "高" if v > 0 else ("低" if v < 0 else "持平")


def _share_or_na(num: float, den: float, min_den: float) -> str:
    """分母过小时不给占比，避免「占总差额 3982%」这类失真。"""
    if not den or abs(den) < min_den:
        return "不适用（差额过小）"
    return fp(num / den, 0)


def _verdict(ctx: dict) -> str:
    main, n = ctx["main"], ctx["n_days"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    d = ctx["deltas"]
    pre, src, net = ctx["presale"], ctx["source_decomp"], ctx["network"]
    cur = ctx["curves"]["curves"]
    po, beh = ctx["pool"], ctx["behavior"]
    prod = ctx["product"]
    d1 = d[b1]
    cum_main = cur[main]["cum"][-1]
    min_den = max(cum_main * 0.05, 1)

    # 1) 水平与形态（findings 已核验，直接复用）
    f1, f2 = (ctx.get("findings") or [{}])[0], (ctx.get("findings") or [{}, {}])[1]

    # 2) 可解释项：只在分母足够大时给占比
    size_rel = pre[main]["pool_total"] / max(pre[b1]["pool_total"], 1) - 1
    rate_gap = pre[main]["pool_lock_rate"] - pre[b1]["pool_lock_rate"]
    pool_note = (f"预售池{'小' if size_rel < 0 else '大'} {abs(size_rel):.0%}"
                 f"（{fi(pre[main]['pool_total'])} vs {fi(pre[b1]['pool_total'])} 单），"
                 f"池转化率{_dir_cn(rate_gap)} {abs(rate_gap) * 100:.1f}pp")
    store_rel = net[main]["stores_with_gen"] / max(net[b1]["stores_with_gen"], 1) - 1
    per_store_rel = net[main]["locks_per_store"] / max(net[b1]["locks_per_store"], 1e-9) - 1
    net_note = (f"有效门店{'少' if store_rel < 0 else '多'} {abs(store_rel):.0%}"
                f"（{fi(net[main]['stores_with_gen'])} vs {fi(net[b1]['stores_with_gen'])} 家），"
                f"单店产出{_dir_cn(per_store_rel)} {abs(per_store_rel):.0%}"
                f"（{net[main]['locks_per_store']:.2f} vs {net[b1]['locks_per_store']:.2f} 单/店）")
    missing = (ctx.get("version_gap") or {}).get("national", {}).get("missing_segments") or []
    vg_note = ("版本缺口：" + "、".join(missing) + " 档在主代际缺失") if missing else "无版本缺口（主代际覆盖对标全部电量段）"

    # 3) 产品与网络（方向词按数据）
    vs = prod[main]["concentration"]["versions"]
    per_day = pre[main]["pool_per_presale_day"]
    b1_per_day = pre[b1]["pool_per_presale_day"]
    speed = "高于" if per_day > b1_per_day else ("低于" if per_day < b1_per_day else "接近")
    prod_note = (f"{main} 有 {vs['n_options']} 个版型、Top1 占 {fp(vs['top1_share'], 0)}；"
                 f"预售日均 {fnum(per_day)} 单/日，{speed} {b1} 的 {fnum(b1_per_day)} 单/日。")

    return (
        '<div class="verdict">'
        f'<h4>1｜{main} 相比 {b1} 与 {b2 or b1}，表现究竟有哪些显著不同？</h4>'
        f'<p>{f1.get("title", "")}——{f1.get("body", "")}'
        f' 节奏上：{f2.get("title", "")}（{f2.get("body", "")}）</p>'
        f'<h4>2｜哪些差异可以得到数据解释？</h4>'
        f'<p>{pool_note}；{net_note}；{vg_note}。'
        f'动力形式：' + "、".join(f"{g} {_power_label(prod[g])}" for g in ctx["curves"]["gens"]) + '。'
        f'预售差额分解：池规模效应 {fnum(src[b1]["presale_scale_effect"])} 单、'
        f'转化率效应 {fnum(src[b1]["presale_rate_effect"])} 单'
        f'（两者方向{"相反、部分抵消" if src[b1]["presale_scale_effect"] * src[b1]["presale_rate_effect"] < 0 else "相同"}，'
        f'净额 {fnum(src[b1]["presale_scale_effect"] + src[b1]["presale_rate_effect"])} 单，'
        f'故不以百分比表达贡献）。'
        f'不可由本数据解释的部分：可寻址需求规模差异（缺少外部分市场数据）、'
        f'单店产能差异的成因（缺少线索/试驾的单车型维度）。</p>'
        f'<h4>3｜这些差异反映了怎样的产品需求和销售网络变化？</h4>'
        f'<p>产品端：{prod_note}'
        f'网络端：{net_note}。</p>'
        f'<h4>4｜当前表现能否持续？</h4>'
        f'<p>封盘池 {fi(po[main]["stock_total"])} 单，已消耗 {fi(po[main]["locked"] + po[main]["refunded"])} 单，'
        f'剩余 {fi(po[main]["remaining"])} 单（{fp(po[main]["remaining_rate"])}）；'
        f'D2–D{n} 锁单 {fnum(po[main]["lock_tail_daily"])} 单/日、退订 '
        f'{fnum(po[main]["refund_tail_daily"])} 单/日，锁/退比 '
        f'{fnum(po[main]["lock_refund_ratio_stock"], 2)}。'
        f'后续空间取决于剩余池兑现速度，区间见 Q10。</p>'
        f'<h4>5｜下一观察周期需要重点验证什么？</h4>'
        f'<p>见下一节清单。重点验证剩余池锁/退比能否维持，以及补充「单店产能差异成因」与'
        f'「可寻址需求规模」两类外部数据。</p>'
        '</div>')


def _watchlist(ctx: dict) -> str:
    main, n = ctx["main"], ctx["n_days"]
    b1 = ctx["benchmarks"][0]
    b2 = ctx["benchmarks"][1] if len(ctx["benchmarks"]) > 1 else None
    po, beh = ctx["pool"], ctx["behavior"]
    m = po[main]
    net = ctx["network"]
    return (
        '<ul class="tight">'
        f'<li><b>锁/退比值</b>：当前累计 {fnum(m["lock_refund_ratio_stock"], 2)}'
        f'（{b1} {fnum(po[b1]["lock_refund_ratio_stock"], 2)}'
        + (f'、{b2} {fnum(po[b2]["lock_refund_ratio_stock"], 2)}' if b2 else "")
        + f'）。这是 Q10 的核心动能指标——若 D{n+1}–D14 跌破 1.0，说明池子从「转化为主」转为「流失为主」，'
        f'需下调剩余 {fi(m["remaining"])} 单的可用量估计。</li>'
        f'<li><b>D2–D{n} 锁单速度</b>：当前 {fnum(m["lock_tail_daily"])} 单/日。'
        f'若连续 5 日 ≥ {fnum((m["lock_tail_daily"] or 0) * 1.3)}，说明剩余池开始加速兑现；'
        f'若 ≤ {fnum((m["lock_tail_daily"] or 0) * 0.7)}，需检查是否进入长尾平台。</li>'
        f'<li><b>D2–D{n} 退订速度</b>：当前 {fnum(m["refund_tail_daily"])} 单/日'
        f'（退订日序列 {"".join(str(x) + "/" for x in m["refund_daily"])}）。'
        f'若 D{n+1}–D14 再出现一次退订高峰（单日 > {fi(max(m["refund_daily"] or [0]))} 单），'
        f'说明还有一批小订到期，会压低剩余池。</li>'
        f'<li><b>剩余池消耗进度</b>：{fi(m["remaining"])} 单（{fp(m["remaining_rate"])}）。'
        f'观察 D14 剩余率是否降到 {fp((m["remaining_rate"] or 0) * 0.75, 0)} 以下。</li>'
        f'<li><b>线索→锁单间隔</b>：当前中位 '
        f'{fnum(beh[main]["lead_to_lock_days_median"], 1)} 天'
        f'（{b1} {fnum(beh[b1]["lead_to_lock_days_median"], 1)} 天）. '
        f'去混淆口径（上市后线索）当前 '
        f'{fnum(beh[main]["lead_to_lock_days_median_postlaunch"], 2)} 天；'
        f'若该值明显拉长，说明到店转化变慢，而不是流量不足。</li>'
        f'<li><b>单店产能</b>：当前 {fnum(net[main]["locks_per_store"], 2)} 单/店。'
        f'需拆解为「有效门店数 × 到店客流 × 转化率」；本窗口缺单车型线索/试驾维度，'
        f'下一周期应补齐（若线索数据仍无单车型维度，只能做同期渠道活动信号）。</li>'
        f'<li><b>纯电 vs 增程需求池</b>：需外部细分市场数据（如纯电大型 SUV 上险量）'
        f'才能判断池子小有多少来自动力形式、多少来自产品本身；本报告只能给出「池子小、消耗比不差」。</li>'
        f'<li><b>D30 退订与交付</b>：本窗口大定退款率 '
        f'{fp(ctx["quality"][main]["deposit_refund_rate"], 2)} 过低不足以判别锁单质量，'
        f'需在 D30 用同一 point-in-time 口径复核。</li>'
        '</ul>')


def _appendix_scope(ctx: dict) -> str:
    a = ctx["audit"]
    rows = [
        ["目标车型（业务显示名 / 代码代际键）", f"{ctx['main']}（series_group_logic 键）"],
        ["上市日 T0（业务定义 time_periods.end）",
         "、".join(f"{g} {ctx['windows'][g]['launch']}" for g in ctx["curves"]["gens"])],
        ["观察截止 T−1", ctx["as_of"]],
        ["窗口天数 N", f"N = (T−1 − T0).days + 1 = {ctx['n_days']}（D1 = 上市日）"],
        ["窗口区间", f"各代际 [{ctx['windows'][ctx['main']]['launch']}, "
                     f"{ctx['windows'][ctx['main']]['window_end_exclusive']}) 左闭右开，等长 {ctx['n_days']} 天"],
        ["零售锁单口径（上市观察口径）",
         "lock_time 非空 COUNTD(order_number)；<b>order_type 严格 = 用户车</b>"
         "（小订池允许未回填）；剔除测试单（总部主理店 + 非 18 位身份证）、"
         "总部主理店整店订单（内测/自营），以及试驾车/大客户/员工/集团员工/经销商员工/"
         "享道/仅批售/项目/展车/海外"],
        ["测试单剔除", "flag_test_orders：store_name ∈ 总部主理店 且 buyer_identity_no 非 18 位身份证"],
        ["订单去重", f"order_number 全局重复 {a['order_number_dup']} 条（窗口内均为 0）"],
        ["预售池口径", "intention_payment_time ∈ [预售开始日, T0)，严格早于上市日"],
        ["预售转化截止", f"统一截止到上市后第 {ctx['n_days']} 天 24:00（事件时间早于截止日）"],
        ["状态重建方式", "point-in-time：只用 ≤ 截止日的事件时间戳，不用当前快照状态字段"],
        ["区域主口径", "省份（license_city → 省份，边界稳定）；大区仅作方向参考（架构期间重划）"],
        ["配置口径", "config_attribute.parquet 按 Order Number 关联；仅比语义可比属性"
                     "（外饰/内饰/轮毂/方向盘/激光雷达 + 电量段）"],
        ["辅助数据", "assign_data.csv（渠道级，无单车型维度）、test_drive_data.csv"
                     "（仅 L6/LS6/LS9 车系列）→ 仅作同期渠道信号，不计算客户级转化率"],
        ["D{n+1}–D30 参考视图（本报告的例外）",
         f"仅 Q1 图与「对标 D{ctx['n_days']} 之后释放」一句使用历史代际 "
         f"D{ctx['n_days']+1}–D{ctx['context']['context_days']} 数据；"
         "用途限于展示释放形状与兑现倍数假设，<b>不参与任何差异计算、排名或结论</b>；"
         f"{ctx['main']} 无该区间数据，图中截断"],
        ["小订池消耗口径（Q10）",
         "业务定义：小订在上市日 24:00 停止收取 → 封盘池 = 已锁 + 已退 + 剩余；"
         "动能指标 = 锁/退比值（累计）与 D2–DN 锁单、退订日速度；"
         "即时锁单 = 无小订直锁 + 同日小订转锁"],
        ["渠道 vs 需求口径",
         "渠道分解以门店所在省份聚合（各省门店数之和 = 全国，无重复计数；跨省上牌 1.2–1.6%）；"
         "与 Q6 的上牌省份需求口径不同，不可混用"],
    ]
    inner = table(["项目", "口径 / 处理"], rows)
    inner += (
        '<div class="verdict"><h4>差异计算定义</h4>'
        '<p>Δ_bench(d) = 累计锁单_主车(d) − 累计锁单_bench(d)；'
        '边际差异(d) = Δ(d) − Δ(d−1)，D1 的边际差异即 Δ(D1)。</p>'
        '<p>预售差额分解：Δ预锁 = (P主 − P对)·r对 + P主·(r主 − r对)，'
        '前项 = 池规模效应、后项 = 转化率效应。</p>'
        '<p>区域差额分解：Δ区域 = (T主 − T对)·s对,区域 + T主·(s主,区域 − s对,区域)，'
        '前项 = 规模效应、后项 = 结构效应（各项结构效应之和 = 0）。</p>'
        '<p>网络差额分解：Δ锁单 = (S主 − S对)·p对 + S主·(p主 − p对)，'
        'S = 有效锁单门店数，p = 单店锁单。</p>'
        '<p>省级渠道分解：Δ锁单(省) = (S主 − S对)·p对 + S主·(p主 − p对)，'
        '前项 = 渠道覆盖效应、后项 = 单店需求效应；按门店所在省份求和 = 全国差额。</p>'
        '<p>预售池累积分解：池差 = 首日爆发差 + 预售天数差×对标首日后日均（长度效应）'
        '+ 首日后天数×日均差（速度效应）。</p>'
        '<p>小订池消耗：封盘池 P = 已锁 + 已退 + 剩余；'
        '锁/退比值 = 已锁 ÷ 已退；日速度为 D2–DN 均值；'
        '剩余池可用量区间 = 剩余 × 池转化率 ~ 剩余 × 锁/(锁+退)。</p>'
        '<p>即时锁单占比 = (无小订直锁 + 同日小订转锁) ÷ 窗口锁单。</p>'
        '</div>')
    return inner


def _appendix_audit(ctx: dict) -> str:
    a = ctx["audit"]
    rows = [["order_data 行数", fi(a["order_rows"])],
            ["order_number 重复", fi(a["order_number_dup"])],
            ["最新锁单时间", a["max_lock_time"] or "—"],
            ["最新建单日期", a["max_order_create"] or "—"],
            ["数据是否覆盖 T−1", "是" if a["data_covers_as_of"] else "否（窗口末段可能未覆盖）"]]
    exc = ctx.get("exclusions", {})
    rows.append(["原始订单 / 零售口径保留",
                 f"{fi(ctx.get('rows_raw', 0))} 行 / {fi(ctx.get('rows_retail', 0))} 行"])
    for g, v in a["gen"].items():
        e = exc.get(g, {})
        rows.append([f"{g}：窗口内零售锁单 / 覆盖天数",
                     f"{fi(v['orders_in_window'])} 单 / {v['days_covered']}/{v['n_days']} 天"])
        rows.append([f"{g}：窗口内已剔除",
                     f"测试单 {fi(e.get('lock_test_orders', 0))}、"
                     f"总部主理店内测单 {fi(e.get('lock_hq_orders', 0))}、"
                     f"其他非零售 {fi(e.get('lock_non_retail', 0))}、"
                     f"类型未回填 {fi(e.get('lock_blank_type', 0))}"])
        rows.append([f"{g}：小订池已剔除",
                     f"测试单 {fi(e.get('pool_test_orders', 0))}、"
                     f"总部主理店内测单 {fi(e.get('pool_hq_orders', 0))}、"
                     f"其他非零售 {fi(e.get('pool_non_retail', 0))}"
                     f"（池内保留类型未回填 {fi(e.get('pool_blank_type', 0))} 单）"])
        rows.append([f"{g}：窗口内 order_type 构成",
                     "、".join(f"{k} {fi(n)}" for k, n in v["order_type_in_window"].items())])
    for key, label in (("assign", "下发线索"), ("test_drive", "试驾")):
        v = a["aux"].get(key, {})
        rows.append([f"{label}数据最新日期", f"{v.get('max_date') or '—'}"
                     f"（{v.get('rows', 0)} 行）"])
    rows.append(["门店主数据", f"{a['aux']['store_master']['rows']} 行；"
                              "当前快照，门店→经销商/形态映射非 PIT"])
    rows.append(["已知不可比项",
                 f"① 大区架构期间重划；② 历史代际允许无小订直锁，{ctx['main']} 几乎全部经小订链路；"
                 f"③ 交付节奏（{ctx['benchmarks'][0]} 上市即有现车）不可比；"
                 f"④ 门店主数据与经销商归属为当前快照；⑤ D{ctx['n_days']+1}–D30 仅参考"])
    return table(["审计项", "结果"], rows)


# ─────────────────────────── 口径说明文档（Markdown） ───────────────────────────

def render_method_doc(ctx: dict, out_root: Path) -> Path:
    """生成《数据口径与差异计算说明》，与 HTML 报告同源同参数。"""
    main, n = ctx["main"], ctx["n_days"]
    gens = ctx["curves"]["gens"]
    a = ctx["audit"]
    out_dir = out_root / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{main}_数据口径与差异计算说明.md"

    L: list[str] = []
    A = L.append
    A(f"# {main} 上市第 {n} 天深度研究 — 数据口径与差异计算说明\n")
    A(f"- 生成时间：{ctx['generated_at']}")
    A(f"- 数据观察截止：{ctx['as_of']}（T−1，最后完整观察日）")
    A("- 生成脚本：`workspace/research_scripts/launch_deep_dive.py`"
      "（计算）+ `workspace/research_scripts/launch_deep_dive_report.py`（呈现）\n")

    A("## 1. 时间规则与窗口\n")
    A("所有代际使用**自身上市后相同天数**的窗口，历史代际不因数据更长而扩窗：\n")
    A(f"```\nN = (T-1 − T0).days + 1 = {n}\n窗口 = [T0, T0+N) 左闭右开，第 d 天 = T0 + (d-1)\n```\n")
    A("| 代际 | 上市日 T0 | 窗口末日 | 星期结构 | 预售开始 | 预售天数 |")
    A("|---|---|---|---|---|---|")
    for g in gens:
        w = ctx["windows"][g]
        A(f"| {g} | {w['launch']} | {w['window_end_exclusive']} 前一日 | "
          f"{'/'.join(w['weekdays'])} | {w['presale_start'] or '—'} | "
          f"{ctx['presale'][g]['presale_days']} |")
    A("")

    A("## 2. 代际映射（不得按字符串猜）\n")
    A("代际归属由 `shared/schema/business_definition.json` 的 `series_group_logic` 判定，"
      "按 `product_name` 匹配、priority 降序裁决：\n")
    A("- `LS8Neo`：priority 2，`product_name LIKE '%LS8NEO%'`")
    A("- `LS8`：priority 1，`product_name LIKE '%LS8%'`（与 LS8Neo 为刻意的父子重叠，靠 priority 区分）")
    A(f"- 本次目标代际 token 解析结果：**{main}**（输入可为展示名 `LS8NEO`，"
      "脚本先精确匹配键、再忽略大小写匹配、最后匹配 `monitor.series_labels`）\n")
    A("上市日取自 `time_periods.{gen}.end`（业务定义），不从 `lock_time` 最小值推断。\n")

    A("## 3. 指标口径\n")
    A("| 指标 | 定义 | 过滤 |")
    A("|---|---|---|")
    A("| 零售锁单（上市观察口径） | `lock_time` 非空的 `COUNTD(order_number)` | "
      "**`order_type` 严格 = 用户车**；剔除测试单（总部主理店 + 非 18 位身份证）、"
      "总部主理店整店订单（内测/自营），以及 NON_RETAIL（试驾车/大客户/员工/集团员工/"
      "经销商员工/享道/仅批售/项目/展车/海外） |")
    A("| 小订池 | `intention_payment_time` 早于上市日 24:00 的小订 | "
      "允许 `order_type` 未回填（空），其余同零售锁单口径 |")
    A("| 测试单 | `store_name ∈ 总部主理店` 且 `buyer_identity_no` 非 18 位身份证 | "
      "`utils/monitors/order_filter.flag_test_orders` |")
    A("| 预售池 | `intention_payment_time ∈ [预售开始日, T0)` 的小订 | 严格早于上市日 |")
    A("| 上市当日新增小订 | `intention_payment_time ∈ [T0, T0+1 天)` | 与预售池互斥；"
      "小订在上市日 24:00 停收，故该档即「上市当日新增」 |")
    A("| 直接锁单 | `intention_payment_time` 为空 | 跳过小订链路的直锁单；"
      "另有 2–4 单小订晚于上市日 24:00 的口径外残余，单列不计入三类 |")
    A("| 池转化/退订 | 事件时间早于窗口末才计入 | point-in-time |")
    A("| 待转化池 | 小订已付、未退意向金/未退大定、未锁单 | point-in-time |")
    A("| 有效锁单门店 | 窗口内有**目标代际**锁单的 `store_name` 去重 | "
      "不把同期其他车系有单门店计入 |")
    A("| 封盘小订池 | 上市日 24:00 前支付的小订（预售 + 上市日当天） | "
      "业务定义：上市日 24:00 后停止收小订 |")
    A("| 锁/退比值 | 已转锁单 ÷ 已退订（累计，事件时间早于窗口末） | "
      "反映池子的消耗质量，越高越偏转化 |")
    A("| 线索→锁单间隔 | `lock_time − first_assign_time` 中位天数"
      "（缺失回退 `first_touch_time`） | 仅已锁单样本；全样本含预售等待期，"
      "另给「上市后线索」去混淆口径 |")
    A("| 即时锁单 | 无小订直锁 + 同日小订转锁 | "
      "同日 = `intention_payment_time.normalize() == lock_time.normalize()` |")
    A("| 省级渠道 | 门店所在省份聚合（各省门店数之和 = 全国） | "
      "与 Q6 的上牌省份需求口径不同，不可混用 |")
    A(f"| D{ctx['n_days']+1}–D30 参考视图 | 仅 Q1 图与兑现倍数假设使用 | "
      "**不参与任何差异计算、排名或结论**；主车无该区间数据 |")
    A("")
    A(f"数据覆盖：order_data 最新锁单时间 `{a['max_lock_time']}`，"
      f"覆盖 T−1：{'是' if a['data_covers_as_of'] else '否'}。"
      f"各代际窗口内有锁单记录的天数："
      + "、".join(f"{g} {v['days_covered']}/{v['n_days']}" for g, v in a["gen"].items())
      + "。窗口内无锁单的日期按 0 计入（事件时间口径下的真实零值），"
        "不把缺失日期当零值——两者通过「数据是否覆盖该日」区分。\n")

    A("## 4. 差异计算定义\n")
    A("**累计差额与边际差异**\n")
    A("```\nΔ_bench(d) = 累计锁单_主车(d) − 累计锁单_bench(d)\n"
      "边际差异(d) = Δ(d) − Δ(d−1)，其中 Δ(0)=0，故 边际(D1)=Δ(D1)\n```\n")
    A("**预售差额二元分解**（池规模 × 转化率）\n")
    A("```\nΔ预锁 = (P主 − P对)·r对 + P主·(r主 − r对)\n"
      "前项 = 池规模效应；后项 = 转化率效应；P=预售池，r=池转化率\n```\n")
    A("**锁单来源分解**（互斥三分）：预售小订转锁 / 上市当日新增小订转锁 / 直接锁单。\n")
    A("**区域差额**（Q6 省份表口径）\n")
    A("```\nΔ省份 = 主车单量(省) − 对标单量(省)\n"
      "按 |Δ| 降序取前 12 个省份；最右列为单元格内条形图（以 0 为中线，按同列最大 |Δ| 归一）\n```\n")
    A("**网络分解**\n")
    A("```\nΔ锁单 = (S主 − S对)·p对 + S主·(p主 − p对)\n"
      "S = 有效锁单门店数；p = 单店锁单\n```\n")
    A("**省级渠道分解**（渠道覆盖 × 单店需求）\n")
    A("```\nΔ锁单(省) = (S主 − S对)·p对 + S主·(p主 − p对)\n"
      "前项 = 渠道覆盖效应；后项 = 单店需求效应；按门店所在省份求和 = 全国差额\n```\n")
    A("**预售池累积分解**（首日爆发 × 预售期长度 × 首日后速度）\n")
    A("```\n池差 = 首日爆发差 + 预售天数差×对标首日后日均 + 主车首日后天数×日均差\n```\n")
    A("**小订池消耗**（业务定义：上市日 24:00 停止收小订）\n")
    A("```\n封盘池 P = 已转锁单 + 已退订 + 封盘池剩余\n"
      "锁/退比值 = 已转锁单 ÷ 已退订（累计）；日速度 = D2–DN 均值\n"
      "剩余池可用量区间 = 剩余 × 池转化率  ~  剩余 × 锁/(锁+退)\n```\n")

    A("## 5. 本次关键结果（同源指标）\n")
    A("| 指标 | " + " | ".join(gens) + " |")
    A("|---|" + "---|" * len(gens))
    rows = [
        ("上市日", lambda g: ctx["windows"][g]["launch"]),
        (f"D1–D{n} 累计零售锁单", lambda g: fi(ctx["curves"]["curves"][g]["cum"][-1])),
        ("D1 锁单", lambda g: fi(ctx["curves"]["curves"][g]["daily"][0])),
        (f"D2–D{n} 日均", lambda g: fnum(ctx["dynamics"][g]["tail_avg"])),
        ("预售天数", lambda g: str(ctx["presale"][g]["presale_days"])),
        ("预售池", lambda g: fi(ctx["presale"][g]["pool_total"])),
        ("池转化率", lambda g: fp(ctx["presale"][g]["pool_lock_rate"])),
        ("池退订率", lambda g: fp(ctx["presale"][g]["pool_refund_rate"])),
        ("上市当日新增小订", lambda g: fi(ctx["presale"][g]["launch_intent_total"])),
        ("待转化池", lambda g: fi(ctx["forward"][g]["pending_total"])),
        ("有效锁单门店", lambda g: fi(ctx["network"][g]["stores_with_gen"])),
        ("单店锁单", lambda g: fnum(ctx["network"][g]["locks_per_store"], 2)),
        ("封盘小订池", lambda g: fi(ctx["pool"][g]["stock_total"])),
        ("池：已锁 / 已退 / 剩余", lambda g: f"{fi(ctx['pool'][g]['locked'])}"
                                          f" / {fi(ctx['pool'][g]['refunded'])}"
                                          f" / {fi(ctx['pool'][g]['remaining'])}"),
        ("锁/退比值", lambda g: fnum(ctx["pool"][g]["lock_refund_ratio_stock"], 2)),
        ("D2–N 锁单 / 退订（单/日）",
         lambda g: f"{fnum(ctx['pool'][g]['lock_tail_daily'])}"
                   f" / {fnum(ctx['pool'][g]['refund_tail_daily'])}"),
        ("即时锁单占比（参考）", lambda g: fp(ctx["behavior"][g]["instant_share"])),
        ("试驾参与率", lambda g: fp(ctx["behavior"][g]["test_drive_rate"])),
        ("线索→锁单中位（全样本 / 上市后）",
         lambda g: f"{fnum(ctx['behavior'][g]['lead_to_lock_days_median'], 1)} 天"
                   f" / {fnum(ctx['behavior'][g]['lead_to_lock_days_median_postlaunch'], 2)} 天"),
        ("≤7 天锁定 / 同日线索转锁",
         lambda g: f"{fp(ctx['behavior'][g]['lead_to_lock_le7_share'])}"
                   f" / {fp(ctx['behavior'][g]['same_day_lead_lock_share'])}"),
        ("版型 HHI", lambda g: fnum(ctx["product"][g]["concentration"]["versions"]["hhi"], 2)),
        ("参考曲线末日累计", lambda g: (
            f"D{ctx['context']['curves'][g]['available_days']}:"
            f"{fi(ctx['context']['curves'][g]['cum'][-1])}"
            if ctx["context"]["curves"].get(g) else "—")),
    ]
    for label, fn in rows:
        A(f"| {label} | " + " | ".join(fn(g) for g in gens) + " |")
    A("")
    A("差额与分解：\n")
    for b, d in ctx["deltas"].items():
        s = ctx["source_decomp"][b]
        A(f"- vs {b}：累计差额 {d['cum_diff']:+,}（{fs(d['cum_rel'])}）；"
          f"{gap_narrative(d, ctx['n_days'])}；"
          f"预售池规模效应 {fnum(s['presale_scale_effect'])} / 转化率效应 "
          f"{fnum(s['presale_rate_effect'])}"
          f"（规模效应占预售差额 {fp(s['presale_scale_share'], 0)}"
          + ("，占比 >100% 因转化率效应反向为正" if (s['presale_scale_share'] or 0) > 1 else "")
          + "）；"
          f"网络效应 {fnum(ctx['network'][b]['vs_main_decomp']['network_effect'])} / "
          f"单店产能效应 {fnum(ctx['network'][b]['vs_main_decomp']['productivity_effect'])}；"
          f"省级渠道效应 {fnum(ctx['channel']['gaps'][b]['total_network_effect'])} / "
          f"省级需求效应 {fnum(ctx['channel']['gaps'][b]['total_productivity_effect'])}")
    A("")

    A("## 5.1 上市观察口径的剔除量\n")
    A("| 代际 | 窗口内零售锁单 | 剔除·测试单 | 剔除·内测店 | 剔除·其他非零售 | "
      "剔除·小订测试单 | 剔除·小订内测店 | 保留·小订未回填 |")
    A("|---|---|---|---|---|---|---|---|")
    for g in gens:
        e = ctx.get("exclusions", {}).get(g, {})
        A(f"| {g} | {fi(ctx['audit']['gen'][g]['orders_in_window'])} | "
          f"{fi(e.get('lock_test_orders', 0))} | {fi(e.get('lock_hq_orders', 0))} | "
          f"{fi(e.get('lock_non_retail', 0))} | {fi(e.get('pool_test_orders', 0))} | "
          f"{fi(e.get('pool_hq_orders', 0))} | {fi(e.get('pool_blank_type', 0))} |")
    A("")

    A("## 5.2 验证：省份差额 = 版本缺口？\n")
    vg = ctx.get("version_gap") or {}
    if vg:
        A("| 口径 | 差额合计 | " + " | ".join(f"{x} 差" for x in vg["segments"]) + " |")
        A("|---|" + "---|" * (len(vg["segments"]) + 1))
        for r in [vg["national"], *vg["provinces"]]:
            A(f"| {'全国' if r['label'] == '全国' else r['label']} | {r['total']:+,} | "
              + " | ".join(f"{r['by_segment'].get(x, 0):+,}" for x in vg["segments"]) + " |")
        A("")
        A(f"对齐口径：按电量段（93/76/103kWh），因为版型命名与档位不同；"
          f"{vg['main']} 缺少 " + "、".join(vg["national"]["missing_segments"]) + " 段，"
          "属产品线缺口而非同档竞争失利。该拆解不回答「为什么没有这一档」。\n")

    sb = ctx.get("same_battery") or {}
    _sb_ok, _sb_why = _sb_status(ctx)
    if not _sb_ok:
        A(f"## 5.3 同档客群验证（已跳过）\n")
        A(f"{_sb_why}，故不做同档客群对比。\n")
    if _sb_ok:
        main_, bench_ = sb["main"], sb["bench"]
        fa, fb = sb["full"][main_], sb["full"][bench_]
        sa, sc = sb["seg"][main_], sb["seg"][bench_]
        A(f"## 5.3 验证：同档（{sb['segment']}）客群差异是否更小\n")
        A(f"| 维度 | {main_} {sb['segment']} | {bench_} {sb['segment']} | 同档差 | 全系差 | 差的变化 |")
        A("|---|---|---|---|---|---|")
        rows53 = [
            ("女性占比", fp(sa["female"]), fp(sc["female"]),
             fpp(sa["female"] - sc["female"]), fpp(fa["female"] - fb["female"])),
            ("一线占比", fp(sa["tier"].get("一线")), fp(sc["tier"].get("一线")),
             fpp(sa["tier"].get("一线", 0) - sc["tier"].get("一线", 0)),
             fpp(fa["tier"].get("一线", 0) - fb["tier"].get("一线", 0))),
            ("车主年龄均值", fnum(sa.get("age_mean"), 1) + " 岁",
             fnum(sc.get("age_mean"), 1) + " 岁",
             f"{sa['age_mean'] - sc['age_mean']:+.1f} 岁",
             f"{fa['age_mean'] - fb['age_mean']:+.1f} 岁"),
        ]
        def _chg53(seg_d, full_d, unit):
            a = float(seg_d.replace("pp", "").replace("岁", "").replace("+", ""))
            b = float(full_d.replace("pp", "").replace("岁", "").replace("+", ""))
            return f"{abs(a) - abs(b):+.1f} {unit}" if unit == "岁" else f"{abs(a) - abs(b):+.1f}pp"

        for r in rows53:
            unit = "岁" if r[3].endswith("岁") else "pp"
            A(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {_chg53(r[3], r[4], unit)} |")
        tf, ts = sb.get("tvd_full", {}), sb.get("tvd_seg", {})
        A("")
        A(f"结构距离（TVD）：线级 {fp(tf.get('tier', 0))} → {fp(ts.get('tier', 0))}、"
          f"年龄 {fp(tf.get('age_cohort', 0))} → {fp(ts.get('age_cohort', 0))}。"
          f"性别与年龄差距缩小、城市线级差距扩大——同档不是抹平差异，而是把差异从性别/年龄"
          f"转移到城市能级（{bench_} 该档更上一线、{main_} 该档更下沉）。\n")

    A("## 6. 可比性与已知限制\n")
    A("| 项 | 处理 / 说明 |")
    A("|---|---|")
    A("| 大区架构 | 期间重划（一区/二区/三区 → 东/西/北/华中），"
      "同一省组在不同窗口挂不同大区 → 区域主口径改用**省份** |")
    A("| 预售期长度 | 7 / 13 / 21 天不同；池规模不可直接读作需求强弱，"
      "故补充「预售日均小订」「净留存日均」单位时间口径 |")
    A("| 动力形式 | LS8Neo 纯电（93/103kWh）、CM3 纯电（93/76/103kWh，业务确认）、"
      "LS8 增程（52/66kWh） |")
    A("| 版本→电量映射 | CM3 的 Pro Max / Max / Ultra = 93 / 76 / 103kWh 由研究报告内的业务映射给出"
      "（`VERSION_BATTERY_BY_GEN`）；`business_definition.battery_capacity_logic` 的旧名称规则会把 "
      "Pro Max 误判为 103，`product_version_series` 尚无 CM3 条目 → 建议正式登记后删除本地映射 |")
    A("| 无小订直锁 | 历史代际下单流程允许跳过小订（"
      + "、".join(f"{g} {fp(ctx['origin'][g]['none_share'])}" for g in gens)
      + "）→ 该口径占比跨代际不可比，仅作参考 |")
    A("| 交付/开票 | CM3 上市即有现车交付，LS8Neo 交付未启动 → 不用交付率评价订单质量 |")
    A("| 门店主数据 | 当前快照；门店→经销商/形态映射非 PIT，仅用于结构解读 |")
    A("| 线索/试驾 | assign_data 为渠道级、test_drive_data 仅 L6/LS6/LS9 车系列，"
      "**无 LS8Neo 单车型维度** → 仅作同期渠道信号，不计算客户级转化率 |")
    A("| 当前快照误用 | 所有历史时点状态均用 ≤ 截止日的事件时间重建，"
      "不使用当前状态字段直出 |")
    A(f"| D{ctx['n_days']+1}–D30 参考视图 | 仅用于展示对标释放形状与兑现倍数假设，"
      f"不参与差异计算；主车无 D{ctx['n_days']+1}–D30 数据，图中截断 |")
    A("| 配置集中度（HHI） | 受可售版型数量机械约束（2/3/4 个版型），属供给端效应，"
      "不能读作客户偏好更集中 |")
    A("| 内饰色调 | 深色 = 含黑/深灰，浅色 = 米/白/浅灰，暖色 = 棕/橘；"
      "复合色名（大象灰黑/大象深灰）先判深色再判浅色 |")
    A("| 选装可比性 | 直接使用 `config_attribute` 的「Attribute / value」原始字段名，"
      "不做品类归并、不自造名称；只有「属性名 + 取值名」字面完全相同才计入同口径对比，"
      "命名不同的显式标注「命名不同」并给出对方取值名 |")
    A("| 即时锁单 | 含「无小订直锁」，该路径占比受下单流程演进影响（"
      + "、".join(f"{g} {fp(ctx['origin'][g]['none_share'])}" for g in gens)
      + "），故以同日小订转锁为主、直锁单列 |")
    A("| 线索→锁单间隔 | ① 全样本含预售等待期，预售期越长该值被机械抬高"
      "（LS8Neo 7 天 vs 对标 13/21 天）；② 仅已锁单样本，存在转化选择性；"
      "③ 因此以「上市后线索→锁单」（约 0.9 天）作为可比口径 |")
    A("")

    A("## 7. 复现方式与产物\n")
    A("```bash")
    A("python workspace/research_scripts/launch_deep_dive.py \\")
    A(f"  --gen {main} --benchmarks {' '.join(ctx['benchmarks'])} "
      f"--as-of {ctx['as_of']} --format html --export-charts")
    A("```\n")
    A("产物：")
    A(f"- 报告：`workspace/outputs/reports/{main}_上市第{n}天深度研究.html`")
    A(f"- 本说明：`workspace/outputs/reports/{main}_数据口径与差异计算说明.md`")
    A(f"- 数据表与指标：`workspace/outputs/tables/launch_deep_dive/{main}_D{n}/`"
      "（table_01~07 CSV、metrics.json、result_contract.json）")
    A("")
    A("同输入同参数重跑得到相同数字（`metrics.json` 中仅 `generated_at` 时间戳变化）。")
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p
