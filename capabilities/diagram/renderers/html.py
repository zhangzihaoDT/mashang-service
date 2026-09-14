"""Self-contained HTML wrapper around the dumbbell SVG."""

from __future__ import annotations

from typing import Optional

from capabilities.diagram.renderers.svg import render_svg
from capabilities.diagram.schemas import MilestoneDumbbellChart
from capabilities.diagram.theme import DEFAULT_THEME, DumbbellTheme


def render_html(
    chart: MilestoneDumbbellChart,
    theme: Optional[DumbbellTheme] = None,
) -> str:
    """Render a complete single-file HTML document."""
    theme = theme or DEFAULT_THEME
    svg = render_svg(chart, theme)
    title = chart.title or "Milestone Temporal Dumbbell"
    subtitle = chart.subtitle or (
        f"{chart.entity_a} vs {chart.entity_b} — 里程碑时间位置与差值"
    )
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
    .chart svg {{ width: 100%; min-width: 900px; display: block; }}
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
    <p class="eyebrow">Milestone Temporal Dumbbell · Diagram</p>
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


def _esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
