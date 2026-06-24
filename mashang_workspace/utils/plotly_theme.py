"""
mashang-service Plotly 图表主题 — 统一视觉组件库

汽车情报 / 数据分析 / AI 工作流风格。

Usage:
    from utils.plotly_theme import ZH, apply_zh_theme, get_series_color

    # color by business role, not series order
    fig.add_trace(go.Scatter(..., line=dict(color=get_series_color('own'))))
    fig.add_trace(go.Scatter(..., line=dict(color=get_series_color('competitor', 0))))

    # unified theme
    apply_zh_theme(fig)

Modes:
    comparison — own, event, competitor (via index), ash
    diverging  — positive, negative, emphasized zero line
    ranking    — steel default, own/event for highlights
    trend      — own main, ash reference, event for annotations
"""

import numpy as np

# ── Semantic Chart Palette ──
ZH = {
    'own': '#174A7C',         # 本品、主指标、主结论
    'event': '#D79A36',        # 事件车型、关键冲击对象、重点高亮
    'steel': '#4F6F82',        # 普通竞品 1
    'sage': '#7A8B76',         # 普通竞品 2
    'clay': '#C06F45',         # 风险、扰动、异常
    'mauve': '#7D6A8E',        # 普通竞品 3
    'sky_muted': '#6A93B8',    # 普通竞品 4
    'ash': '#9AA3AD',          # 参考线、历史均值、行业均值

    'positive': '#2A9D8F',     # 正向变化
    'negative': '#D95F59',     # 负向变化
    'warning': '#D79A36',      # 预警、临界点
    'neutral': '#6B7280',      # 中性/背景

    # chart palette (sequential order for fallback)
    'c1': '#174A7C',
    'c2': '#D79A36',
    'c3': '#4F6F82',
    'c4': '#7A8B76',
    'c5': '#7D6A8E',
    'c6': '#C06F45',
    'c7': '#6A93B8',
    'c8': '#9AA3AD',
}

# ── Theme Constants ──
CHART_BG = '#FFFFFF'
PLOT_BG = '#FFFFFF'
GRID_COLOR = '#EEF2F6'
AXIS_LINE = '#C7CDD4'
ZERO_LINE = '#6B7280'
AXIS_TEXT = '#5F6B7A'
AXIS_TITLE = '#374151'

# ── Role/Mode-based Color Assignment ──
_COMPETITOR_CYCLE = ['steel', 'sage', 'mauve', 'sky_muted']

def get_series_color(role: str = 'steel', index: int = 0) -> str:
    """Return color by role (own/event/competitor/ash/positive/negative).

    For 'competitor', cycles through muted competitor palette by index.
    """
    if role == 'own':
        return ZH['own']
    if role == 'event':
        return ZH['event']
    if role == 'ash':
        return ZH['ash']
    if role == 'positive':
        return ZH['positive']
    if role == 'negative':
        return ZH['negative']
    if role == 'neutral':
        return ZH['neutral']
    if role == 'competitor':
        key = _COMPETITOR_CYCLE[index % len(_COMPETITOR_CYCLE)]
        return ZH[key]
    return ZH.get(role, ZH['ash'])


def apply_zh_theme(fig, emphasize_zero=True):
    """Apply mashang-service Plotly theme to a figure.

    Sets paper/plot background, grid, axis lines, zeroline, tick/title fonts.
    """
    fig.update_layout(
        paper_bgcolor=CHART_BG,
        plot_bgcolor=PLOT_BG,
    )
    fig.update_xaxes(
        showline=True,
        linecolor=AXIS_LINE,
        linewidth=1,
        gridcolor=GRID_COLOR,
        zeroline=False,
        tickfont=dict(color=AXIS_TEXT),
        title_font=dict(color=AXIS_TITLE),
    )
    fig.update_yaxes(
        showline=True,
        linecolor=AXIS_LINE,
        linewidth=1,
        gridcolor=GRID_COLOR,
        zeroline=emphasize_zero,
        zerolinecolor=ZERO_LINE,
        zerolinewidth=2,
        tickfont=dict(color=AXIS_TEXT),
        title_font=dict(color=AXIS_TITLE),
    )


def align_dual_zero(fig, y1=None, y2=None):
    """Align zerolines of yaxis and yaxis2 at same visual position."""
    y1r = fig.layout.yaxis.range
    y2r = fig.layout.yaxis2.range
    if y1r is not None and y2r is not None:
        lo1, hi1 = y1r
        lo2, hi2 = y2r
    elif y1 is not None and y2 is not None:
        lo1, hi1 = float(min(y1)), float(max(y1))
        lo2, hi2 = float(min(y2)), float(max(y2))
    else:
        return
    r1 = hi1 - lo1
    r2 = hi2 - lo2
    if r1 <= 0 or r2 <= 0:
        return
    neg1 = max(0.0, -lo1)
    pos1 = max(0.0, hi1)
    neg2 = max(0.0, -lo2)
    pos2 = max(0.0, hi2)
    if pos1 == 0 or pos2 == 0:
        return
    ratio = neg1 / pos1
    if ratio > 0:
        lo2 = -max(neg2, pos2 * ratio)
        hi2 = max(pos2, neg2 / ratio)
    else:
        lo2 = -neg2
        hi2 = pos2
    fig.layout.yaxis2.range = [lo2, hi2]
