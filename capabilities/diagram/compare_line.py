"""Comparison Line — Python API and CLI.

Compare several entities across the same ordered categories using a
colour **and** line-shape double encoding (see ``renderers/line.py`` for
the visual rules). Built from the presale first-four-days comparison.

Usage::

    python -m capabilities.diagram.compare_line --input rows.json --format html
    python -m capabilities.diagram.compare_line --input rows.json --format svg
    python -m capabilities.diagram.compare_line --input rows.json --format json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from capabilities.diagram.renderers.line import (
    line_slug,
    render_line_html,
    render_line_svg,
)
from capabilities.diagram.schemas import (
    CHART_TYPE_COMPARISON_LINE,
    ComparisonLineChart,
    ComparisonLineValidationError,
)
from capabilities.diagram.theme import DEFAULT_THEME, DumbbellTheme

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
DEFAULT_OUTPUT_ROOT = os.path.join(_REPO_ROOT, "outputs", "diagram")


def build_chart(payload: dict, title: Optional[str] = None) -> ComparisonLineChart:
    """Build and validate a chart from a plain JSON payload."""
    chart = ComparisonLineChart.from_dict(payload)
    if title:
        chart.title = title
    return chart.validate()


def load_chart(path: str | Path, title: Optional[str] = None) -> ComparisonLineChart:
    """Load a chart from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ComparisonLineValidationError("input JSON must be an object")
    return build_chart(data, title=title)


def render(
    chart: ComparisonLineChart,
    theme: Optional[DumbbellTheme] = None,
) -> str:
    """Render the chart as a self-contained HTML document."""
    return render_line_html(chart, theme)


def render_svg(
    chart: ComparisonLineChart,
    theme: Optional[DumbbellTheme] = None,
) -> str:
    """Render the chart as a standalone SVG document body."""
    return render_line_svg(chart, theme)


def _to_contract(
    chart: ComparisonLineChart,
    artifacts: Optional[dict] = None,
) -> dict:
    low, high = chart.value_bounds()
    return {
        "status": "success",
        "capability": "capabilities.diagram",
        "chart_type": CHART_TYPE_COMPARISON_LINE,
        "scope": {
            "categories": list(chart.categories),
            "category_count": len(chart.categories),
            "series_count": len(chart.series),
            "own_series": chart.own_series.name if chart.own_series else None,
            "value_range": {"min": low, "max": high},
            "value_suffix": chart.value_suffix,
        },
        "result": {
            "title": chart.title,
            "series": [item.to_dict() for item in chart.series],
        },
        "artifacts": artifacts or {},
        "errors": [],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Comparison Line — compare entities across ordered categories"
    )
    parser.add_argument("--input", required=True, help="Path to the chart JSON payload")
    parser.add_argument(
        "--format", default="html", choices=["html", "svg", "json"], help="Output format"
    )
    parser.add_argument("--title", default=None, help="Override the chart title")
    parser.add_argument("--output", default=None, help="Explicit output file path")
    parser.add_argument(
        "--output-root", default=DEFAULT_OUTPUT_ROOT, help="Output root directory"
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        chart = load_chart(args.input, title=args.title)
    except (ComparisonLineValidationError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "errors": [str(exc)]}, ensure_ascii=False))
        return 1

    artifacts: dict[str, str] = {}
    if args.format == "json":
        print(json.dumps(_to_contract(chart, artifacts), ensure_ascii=False, indent=2))
        return 0

    slug = line_slug(chart)
    if args.format == "html":
        content, extension = render(chart), ".html"
    else:
        content, extension = render_svg(chart), ".svg"

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(args.output_root) / "charts" / f"{slug}{extension}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    artifacts["output"] = str(output_path)

    print(json.dumps(_to_contract(chart, artifacts), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
