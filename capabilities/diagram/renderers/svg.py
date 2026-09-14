"""Static inline-SVG renderer for a milestone temporal dumbbell chart.

Honest time axis: x positions are proportional to real date gaps. The
chart is a pure function of the validated contract — no JavaScript, no
external images, no randomness.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Iterable, Optional

from capabilities.diagram.schemas import MilestoneDumbbellChart
from capabilities.diagram.theme import DEFAULT_THEME, DumbbellTheme

VIEWBOX_W = 1040
MARGIN_LEFT = 176
MARGIN_RIGHT = 40
AXIS_TOP = 88
TICK_LABEL_Y = 72
ROWS_TOP = 112
ROW_H = 80
LEGEND_H = 72

# Two endpoints whose centered date/event labels would overlap get one point's
# labels dropped to a lower band. Real x positions are unchanged, so the time
# axis stays honest.
LABEL_PAD_PX = 16

AXIS_X0 = MARGIN_LEFT
AXIS_X1 = VIEWBOX_W - MARGIN_RIGHT


def _esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _rough_width(text: str, font_size: float = 9.0) -> float:
    """Rough advance width, CJK counted full-width. Used only to keep labels
    inside the canvas and apart; it does not affect any data geometry."""
    width = 0.0
    for ch in text:
        width += font_size if ord(ch) > 0x2E7F else font_size * 0.56
    return width


def _label_half_width(day: date, event: Optional[str]) -> float:
    widths = [_rough_width(day.isoformat())]
    if event:
        widths.append(_rough_width(event))
    return max(widths) / 2


def chart_slug(chart: MilestoneDumbbellChart) -> str:
    """Stable, filesystem-safe slug used for element IDs."""
    base = re.sub(r"[^a-z0-9]+", "-", (chart.title or "dumbbell").lower()).strip("-")
    base = base or "dumbbell"
    digest = hashlib.sha1(
        (chart.title + "|" + chart.entity_a + "|" + chart.entity_b).encode("utf-8")
    ).hexdigest()[:8]
    return f"{base[:40]}-{digest}"


def _iter_months(start: date, end: date) -> Iterable[date]:
    year, month = start.year, start.month
    while True:
        current = date(year, month, 1)
        if current > end:
            return
        yield current
        month += 1
        if month > 12:
            month = 1
            year += 1


def _time_ticks(t_min: date, t_max: date) -> list[tuple[date, str]]:
    """Adaptive ticks with labels matched to the visible span."""
    span = (t_max - t_min).days
    ticks: list[tuple[date, str]] = []
    if span <= 60:
        current = t_min + timedelta(days=(7 - t_min.weekday()) % 7)
        while current <= t_max:
            ticks.append((current, f"{current.month:02d}-{current.day:02d}"))
            current += timedelta(days=14)
    elif span <= 400:
        for month in _iter_months(t_min, t_max):
            ticks.append((month, f"{month.year}-{month.month:02d}"))
    elif span <= 1500:
        for month in _iter_months(t_min, t_max):
            if month.month in (1, 4, 7, 10):
                ticks.append((month, f"{month.year}-{month.month:02d}"))
    else:
        for month in _iter_months(t_min, t_max):
            if month.month == 1:
                ticks.append((month, f"{month.year}"))
    return ticks


def _delta_label(delta_days: int) -> str:
    if delta_days == 0:
        return "0d"
    sign = "+" if delta_days > 0 else "-"
    return f"{sign}{abs(delta_days)}d"


def render_svg(
    chart: MilestoneDumbbellChart,
    theme: Optional[DumbbellTheme] = None,
) -> str:
    """Render the chart as a standalone ``<svg>`` element string."""
    chart.validate()
    theme = theme or DEFAULT_THEME
    prefix = chart_slug(chart)

    rows = chart.sorted_rows()
    dates = [d for row in rows for d in (row.parsed_date_a, row.parsed_date_b)]
    t_raw_min, t_raw_max = min(dates), max(dates)
    if t_raw_min == t_raw_max:
        t_min = t_raw_min - timedelta(days=30)
        t_max = t_raw_max + timedelta(days=30)
    else:
        pad = max(7, int((t_raw_max - t_raw_min).days * 0.06))
        t_min = t_raw_min - timedelta(days=pad)
        t_max = t_raw_max + timedelta(days=pad)
    span = (t_max - t_min).days

    def x_of(day: date) -> float:
        return AXIS_X0 + (day - t_min).days / span * (AXIS_X1 - AXIS_X0)

    def row_geometry(row, index):
        y = ROWS_TOP + index * ROW_H + ROW_H // 2
        x_a = x_of(row.parsed_date_a)
        x_b = x_of(row.parsed_date_b)
        half_a = _label_half_width(row.parsed_date_a, row.event_a)
        half_b = _label_half_width(row.parsed_date_b, row.event_b)
        # Stagger only when the two centered label blocks would actually touch.
        stagger = abs(x_b - x_a) < half_a + half_b + LABEL_PAD_PX
        return y, x_a, x_b, half_a, half_b, stagger

    geo = [row_geometry(row, index) for index, row in enumerate(rows)]
    extra_bottom = 28 if any(g[5] for g in geo) else 0
    rows_bottom = ROWS_TOP + len(rows) * ROW_H + extra_bottom
    viewbox_h = rows_bottom + LEGEND_H

    out: list[str] = []
    out.append(
        f'<svg viewBox="0 0 {VIEWBOX_W} {viewbox_h}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-labelledby="{prefix}-title {prefix}-desc">'
    )
    title = _esc(chart.title or "Milestone Temporal Dumbbell")
    desc = _esc(
        f"哑铃图，比较 {chart.entity_a} 与 {chart.entity_b} 在 {len(rows)} "
        f"个里程碑上的时间位置与差值。"
    )
    out.append(f'<title id="{prefix}-title">{title}</title>')
    out.append(f'<desc id="{prefix}-desc">{desc}</desc>')
    out.append("<defs>")
    out.append(
        f'<marker id="{prefix}-arrow" markerWidth="8" markerHeight="6" '
        f'refX="7" refY="3" orient="auto">'
        f'<polygon points="0 0, 8 3, 0 6" fill="{theme.accent}"/></marker>'
    )
    out.append("</defs>")
    out.append(f'<rect width="100%" height="100%" fill="{theme.paper}"/>')

    # Time axis: vertical gridlines with labels, real proportional spacing.
    for tick_date, label in _time_ticks(t_min, t_max):
        if not (t_min <= tick_date <= t_max):
            continue
        x = x_of(tick_date)
        out.append(
            f'<line x1="{x:.1f}" y1="{AXIS_TOP}" x2="{x:.1f}" y2="{rows_bottom}" '
            f'stroke="{theme.rule}" stroke-width="0.8"/>'
        )
        out.append(
            f'<text x="{x:.1f}" y="{TICK_LABEL_Y}" fill="{theme.muted}" '
            f'font-size="9" font-family="{theme.font_mono}" '
            f'text-anchor="middle">{_esc(label)}</text>'
        )
    out.append(
        f'<line x1="{AXIS_X0}" y1="{AXIS_TOP}" x2="{AXIS_X1}" y2="{AXIS_TOP}" '
        f'stroke="{theme.rule_solid}" stroke-width="1"/>'
    )

    for row, (y, x_a, x_b, half_a, half_b, stagger) in zip(rows, geo):
        # Connector, drawn before the dots; arrowhead marks the later endpoint.
        left_x, right_x = sorted((x_a, x_b))
        out.append(
            f'<line x1="{left_x:.1f}" y1="{y}" x2="{right_x - 6:.1f}" y2="{y}" '
            f'stroke="{theme.muted}" stroke-width="1.2" '
            f'marker-end="url(#{prefix}-arrow)"/>'
        )

        # Time delta, masked above the connector.
        mid_x = (x_a + x_b) / 2
        label = _delta_label(row.delta_days)
        mask_w = max(36, 12 + 7 * len(label))
        out.append(
            f'<rect x="{mid_x - mask_w / 2:.1f}" y="{y - 26}" width="{mask_w}" '
            f'height="16" rx="2" fill="{theme.paper}"/>'
        )
        out.append(
            f'<text x="{mid_x:.1f}" y="{y - 14}" fill="{theme.brown}" '
            f'font-size="9" font-family="{theme.font_mono}" '
            f'text-anchor="middle">{_esc(label)}</text>'
        )

        # Milestone label (left gutter).
        out.append(
            f'<text x="{MARGIN_LEFT - 24}" y="{y + 4}" fill="{theme.ink_strong}" '
            f'font-size="12" font-weight="600" font-family="{theme.font_sans}" '
            f'text-anchor="end">{_esc(row.milestone)}</text>'
        )

        for x, color, tint, day, event, half in (
            (
                x_a,
                theme.entity_a,
                theme.entity_a_tint,
                row.parsed_date_a,
                row.event_a,
                half_a,
            ),
            (
                x_b,
                theme.entity_b,
                theme.entity_b_tint,
                row.parsed_date_b,
                row.event_b,
                half_b,
            ),
        ):
            out.append(
                f'<circle cx="{x:.1f}" cy="{y}" r="5" fill="{tint}" '
                f'stroke="{color}" stroke-width="1.5"/>'
            )
            # Keep the time axis honest but avoid label collisions: when the
            # two label blocks would overlap, drop the later one's labels to a
            # lower band instead of moving the points.
            base = y + 20
            if stagger and x > (x_a + x_b) / 2:
                base = y + 48
            # Anchor away from the canvas edges so long labels are not clipped.
            if x + half > AXIS_X1 - 8:
                anchor = "end"
            elif x - half < MARGIN_LEFT - 8:
                anchor = "start"
            else:
                anchor = "middle"
            out.append(
                f'<text x="{x:.1f}" y="{base}" fill="{theme.ink}" '
                f'font-size="9" font-weight="500" font-family="{theme.font_mono}" '
                f'text-anchor="{anchor}">{day.isoformat()}</text>'
            )
            if event:
                out.append(
                    f'<text x="{x:.1f}" y="{base + 14}" fill="{theme.muted}" '
                    f'font-size="9" font-family="{theme.font_sans}" '
                    f'text-anchor="{anchor}">{_esc(event)}</text>'
                )

    # Legend strip at the bottom.
    legend_y = rows_bottom + 40
    out.append(
        f'<line x1="{AXIS_X0}" y1="{rows_bottom + 16}" x2="{AXIS_X1}" '
        f'y2="{rows_bottom + 16}" stroke="{theme.rule}" stroke-width="0.8"/>'
    )
    for offset, name, color in (
        (0, chart.entity_a, theme.entity_a),
        (200, chart.entity_b, theme.entity_b),
    ):
        cx = AXIS_X0 + offset
        out.append(
            f'<circle cx="{cx}" cy="{legend_y - 4}" r="4" fill="{color}"/>'
        )
        out.append(
            f'<text x="{cx + 12}" y="{legend_y}" fill="{theme.muted}" '
            f'font-size="10" font-family="{theme.font_sans}">{_esc(name)}</text>'
        )
    out.append(
        f'<text x="{AXIS_X0 + 400}" y="{legend_y}" fill="{theme.muted}" '
        f'font-size="10" font-family="{theme.font_mono}">Δ = later − earlier (days)</text>'
    )

    out.append("</svg>")
    return "".join(out)
