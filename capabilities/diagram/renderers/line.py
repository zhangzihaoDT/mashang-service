"""Static inline-SVG renderers for a comparison line chart.

Design rules (accumulated from the LS8 NEO presale comparison):

1. One entity = one colour **and** one line shape. Colour alone is not
   enough when four or more series share a small chart.
2. The subject (``role="own"``) is always solid, heavier and drawn last, so
   it reads as the foreground; peers cycle through clay / sage / mauve /
   steel and use dash / dashdot / longdash.
3. The legend draws a line swatch with the real dash pattern, so the reader
   decodes shape first, colour second.
4. The last value of each series is labelled at the right edge, with a
   minimum vertical gap, instead of forcing a legend-to-line round trip.
5. Markers appear only when the series is short (auto: <= 8 points);
   longer series keep a clean line plus a terminal dot.

The renderer is a pure function of the validated contract: no JavaScript,
no external assets, no randomness.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Optional

from capabilities.diagram.schemas import ComparisonLineChart
from capabilities.diagram.theme import DEFAULT_THEME, DumbbellTheme

VIEW_W = 1040
VIEW_H = 452
MARGIN_LEFT = 76
MARGIN_RIGHT = 136
PLOT_TOP = 118
PLOT_BOTTOM = 60

#: own series — solid, heavy, primary ink
OWN_STYLE = {"color": "#174A7C", "dash": "", "width": 3.0}

#: peers — colour + dash cycle (never colour alone)
PEER_STYLES = (
    {"color": "#C06F45", "dash": "6 4", "width": 1.9},  # clay / dash
    {"color": "#7A8B76", "dash": "9 4 2 4", "width": 2.0},  # sage / dashdot
    {"color": "#7D6A8E", "dash": "14 6", "width": 1.9},  # mauve / longdash
    {"color": "#4F6F82", "dash": "6 4", "width": 1.9},  # steel / dash
    {"color": "#6A93B8", "dash": "2 4", "width": 1.9},  # sky / dot
)

AUTO_MARKER_MAX_POINTS = 8
END_LABEL_GAP = 17.0


def _esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _rough_width(text: str, font_size: float = 11.0) -> float:
    """Rough advance width; CJK counted full-width (legend layout only)."""
    width = 0.0
    for ch in text:
        width += font_size if ord(ch) > 0x2E7F else font_size * 0.56
    return width


def line_slug(chart: ComparisonLineChart) -> str:
    """Stable, filesystem-safe slug used for element IDs and output names."""
    base = re.sub(r"[^a-z0-9]+", "-", (chart.title or "comparison-line").lower())
    base = base.strip("-") or "comparison-line"
    digest = hashlib.sha1(
        (chart.title + "|" + "|".join(item.name for item in chart.series)).encode("utf-8")
    ).hexdigest()[:8]
    return f"{base[:40]}-{digest}"


def series_styles(chart: ComparisonLineChart) -> list[dict]:
    """Resolve colour + dash + width for every series, in declaration order."""
    styles: list[dict] = []
    peer_index = 0
    for item in chart.series:
        if item.role == "own":
            style = dict(OWN_STYLE)
        else:
            style = dict(PEER_STYLES[peer_index % len(PEER_STYLES)])
            peer_index += 1
        if item.color:
            style["color"] = item.color
        if item.dash:
            style["dash"] = item.dash
        styles.append(style)
    return styles


def nice_step(span: float, target: int = 5) -> float:
    """A 1/2/2.5/5 x 10^k step giving roughly ``target`` intervals."""
    if span <= 0:
        return 1.0
    raw = span / max(1, target)
    magnitude = 10 ** math.floor(math.log10(raw))
    for factor in (1, 2, 2.5, 5, 10):
        if raw <= factor * magnitude:
            return factor * magnitude
    return 10 * magnitude


def _axis_domain(chart: ComparisonLineChart) -> tuple[float, float, float]:
    data_min, data_max = chart.value_bounds()
    low = chart.y_min if chart.y_min is not None else min(0.0, data_min)
    high = chart.y_max if chart.y_max is not None else data_max
    step = chart.y_step if chart.y_step is not None else nice_step(high - low)
    low = math.floor(low / step) * step
    high = math.ceil(high / step) * step
    if high <= low:
        high = low + step
    return low, high, step


def _format_value(chart: ComparisonLineChart, value: float) -> str:
    return f"{value:,.{chart.decimals}f}{chart.value_suffix}"


def render_line_svg(
    chart: ComparisonLineChart,
    theme: Optional[DumbbellTheme] = None,
) -> str:
    """Render the chart as a standalone ``<svg>`` element string."""
    chart.validate()
    theme = theme or DEFAULT_THEME
    prefix = line_slug(chart)

    low, high, step = _axis_domain(chart)
    ticks = []
    value = low
    while value <= high + step * 1e-6 and len(ticks) <= 12:
        ticks.append(value)
        value += step

    plot_w = VIEW_W - MARGIN_LEFT - MARGIN_RIGHT
    plot_h = VIEW_H - PLOT_TOP - PLOT_BOTTOM
    categories = chart.categories
    n = len(categories)

    def x_of(index: int) -> float:
        if n == 1:
            return MARGIN_LEFT + plot_w / 2
        return MARGIN_LEFT + plot_w * index / (n - 1)

    def y_of(value: float) -> float:
        return PLOT_TOP + plot_h - (value - low) / (high - low) * plot_h

    show_markers = (
        chart.markers if chart.markers is not None else n <= AUTO_MARKER_MAX_POINTS
    )
    styles = series_styles(chart)

    out: list[str] = []
    out.append(
        f'<svg viewBox="0 0 {VIEW_W} {VIEW_H}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-labelledby="{prefix}-title {prefix}-desc">'
    )
    title = _esc(chart.title or "Comparison Line")
    names = "、".join(item.name for item in chart.series)
    out.append(f'<title id="{prefix}-title">{title}</title>')
    out.append(
        f'<desc id="{prefix}-desc">对比折线图：{_esc(names)} 在 '
        f'{_esc("、".join(categories))} 上的数值对比。</desc>'
    )
    out.append(f'<rect width="100%" height="100%" fill="{theme.paper}"/>')

    # ── legend: line swatch carries the dash pattern ──
    legend_x = MARGIN_LEFT
    legend_y = 30.0
    for item, style in zip(chart.series, styles):
        dash_attr = f' stroke-dasharray="{style["dash"]}"' if style["dash"] else ""
        out.append(
            f'<line x1="{legend_x:.1f}" y1="{legend_y:.1f}" x2="{legend_x + 26:.1f}" '
            f'y2="{legend_y:.1f}" stroke="{style["color"]}" '
            f'stroke-width="{style["width"]:.2f}"{dash_attr}/>'
        )
        out.append(
            f'<text x="{legend_x + 34:.1f}" y="{legend_y + 4:.1f}" font-size="12" '
            f'fill="{theme.ink_strong}">{_esc(item.name)}</text>'
        )
        legend_x += 34 + _rough_width(item.name, 12) + 26
        if legend_x > VIEW_W - MARGIN_RIGHT - 120:
            legend_x = MARGIN_LEFT
            legend_y += 22
            if legend_y > PLOT_TOP - 30:
                break

    # ── y grid + ticks ──
    for tick in ticks:
        y = y_of(tick)
        out.append(
            f'<line x1="{MARGIN_LEFT}" y1="{y:.1f}" x2="{VIEW_W - MARGIN_RIGHT}" '
            f'y2="{y:.1f}" stroke="{theme.rule}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{MARGIN_LEFT - 10}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{theme.muted}">{_esc(_format_value(chart, tick))}</text>'
        )
    out.append(
        f'<line x1="{MARGIN_LEFT}" y1="{PLOT_TOP + plot_h}" '
        f'x2="{VIEW_W - MARGIN_RIGHT}" y2="{PLOT_TOP + plot_h}" '
        f'stroke="{theme.rule_solid}" stroke-width="1"/>'
    )

    # ── x categories ──
    for index, category in enumerate(categories):
        out.append(
            f'<text x="{x_of(index):.1f}" y="{PLOT_TOP + plot_h + 24:.1f}" '
            f'text-anchor="middle" font-size="11.5" fill="{theme.muted}">'
            f"{_esc(category)}</text>"
        )
    if chart.x_label:
        out.append(
            f'<text x="{VIEW_W - MARGIN_RIGHT}" y="{PLOT_TOP + plot_h + 46:.1f}" '
            f'text-anchor="end" font-size="11" fill="{theme.muted}">'
            f"{_esc(chart.x_label)}</text>"
        )
    if chart.y_label:
        out.append(
            f'<text x="{MARGIN_LEFT}" y="{PLOT_TOP - 14}" text-anchor="start" '
            f'font-size="11" fill="{theme.muted}">{_esc(chart.y_label)}</text>'
        )

    # ── lines: peers first, own last so the subject stays on top ──
    order = [
        index
        for index, item in enumerate(chart.series)
        if item.role != "own"
    ] + [index for index, item in enumerate(chart.series) if item.role == "own"]

    for index in order:
        item = chart.series[index]
        style = styles[index]
        points = " ".join(
            f"{x_of(i):.1f},{y_of(value):.1f}" for i, value in enumerate(item.values)
        )
        dash_attr = f' stroke-dasharray="{style["dash"]}"' if style["dash"] else ""
        out.append(
            f'<polyline points="{points}" fill="none" stroke="{style["color"]}" '
            f'stroke-width="{style["width"]:.2f}" stroke-linejoin="round" '
            f'stroke-linecap="butt"{dash_attr}/>'
        )
        if show_markers:
            radius = 4.4 if item.role == "own" else 3.2
            for i, value in enumerate(item.values):
                out.append(
                    f'<circle cx="{x_of(i):.1f}" cy="{y_of(value):.1f}" r="{radius}" '
                    f'fill="{style["color"]}" stroke="{theme.paper}" stroke-width="1.2"/>'
                )

    # ── end labels with a minimum vertical gap ──
    ends = sorted(
        (
            y_of(item.values[-1]),
            index,
            _format_value(chart, item.values[-1]),
        )
        for index, item in enumerate(chart.series)
    )
    placed: list[float] = []
    for y, index, label in ends:
        adjusted = y
        while any(abs(adjusted - other) < END_LABEL_GAP for other in placed):
            adjusted += END_LABEL_GAP
        placed.append(adjusted)
        out.append(
            f'<text x="{x_of(n - 1) + 10:.1f}" y="{adjusted + 4:.1f}" '
            f'font-size="11.5" fill="{styles[index]["color"]}" '
            f'font-weight="{700 if chart.series[index].role == "own" else 500}">'
            f"{_esc(label)}</text>"
        )

    out.append("</svg>")
    return "".join(out)


def render_line_html(
    chart: ComparisonLineChart,
    theme: Optional[DumbbellTheme] = None,
) -> str:
    """Render a complete single-file HTML document around the SVG."""
    theme = theme or DEFAULT_THEME
    svg = render_line_svg(chart, theme)
    title = chart.title or "Comparison Line"
    subtitle = chart.subtitle or "多主体在同一组有序类别上的对比"
    footer = chart.source_note or "Source: 未标注"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_esc(title)}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: {theme.paper};
      color: {theme.ink_strong};
      font-family: {theme.font_sans};
      min-height: 100vh;
      display: flex;
      justify-content: center;
      padding: 48px 32px;
    }}
    .frame {{ width: 100%; max-width: 1100px; }}
    .eyebrow {{
      font-family: {theme.font_mono};
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: {theme.muted};
      margin-bottom: 8px;
    }}
    h1 {{
      font-family: {theme.font_serif};
      font-size: 28px;
      font-weight: 400;
      letter-spacing: -0.02em;
      line-height: 1.2;
      color: {theme.ink};
      margin-bottom: 8px;
    }}
    .subtitle {{ font-size: 13px; color: {theme.muted}; margin-bottom: 24px; }}
    .chart {{ width: 100%; overflow-x: auto; }}
    .chart svg {{ width: 100%; min-width: 760px; display: block; }}
    footer {{
      margin-top: 24px;
      padding-top: 12px;
      border-top: 1px solid {theme.rule};
      font-family: {theme.font_mono};
      font-size: 10px;
      color: {theme.muted};
    }}
  </style>
</head>
<body>
  <div class="frame">
    <p class="eyebrow">Comparison Line · Diagram</p>
    <h1>{_esc(title)}</h1>
    <p class="subtitle">{_esc(subtitle)}</p>
    <div class="chart">
{svg}
    </div>
    <footer>{_esc(footer)}</footer>
  </div>
</body>
</html>
"""



__all__ = [
    "AUTO_MARKER_MAX_POINTS",
    "OWN_STYLE",
    "PEER_STYLES",
    "line_slug",
    "nice_step",
    "render_line_html",
    "render_line_svg",
    "series_styles",
]
