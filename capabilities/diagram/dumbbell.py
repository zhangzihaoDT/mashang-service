"""Milestone Temporal Dumbbell — Python API and CLI.

Compare two entities' time positions across a set of corresponding
milestones, plus the signed time delta between them.

Usage::

    python -m capabilities.diagram.dumbbell --input rows.json --format html
    python -m capabilities.diagram.dumbbell --input rows.json --format json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from capabilities.diagram.renderers.html import render_html, render_svg
from capabilities.diagram.renderers.svg import chart_slug
from capabilities.diagram.schemas import (
    CHART_TYPE_MILESTONE_DUMBBELL,
    DumbbellValidationError,
    MilestoneDumbbellChart,
)
from capabilities.diagram.theme import DEFAULT_THEME, DumbbellTheme

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
DEFAULT_OUTPUT_ROOT = os.path.join(_REPO_ROOT, "outputs", "diagram")


def build_chart(payload: dict, title: Optional[str] = None) -> MilestoneDumbbellChart:
    """Build and validate a chart from a plain JSON payload."""
    chart = MilestoneDumbbellChart.from_dict(payload)
    if title:
        chart.title = title
    return chart.validate()


def load_chart(path: str | Path, title: Optional[str] = None) -> MilestoneDumbbellChart:
    """Load a chart from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DumbbellValidationError("input JSON must be an object")
    return build_chart(data, title=title)


def render(
    chart: MilestoneDumbbellChart,
    theme: Optional[DumbbellTheme] = None,
) -> str:
    """Render the chart as a self-contained HTML document."""
    return render_html(chart, theme)


def _to_contract(
    chart: MilestoneDumbbellChart,
    artifacts: Optional[dict] = None,
) -> dict:
    return {
        "status": "success",
        "capability": "capabilities.diagram",
        "chart_type": CHART_TYPE_MILESTONE_DUMBBELL,
        "scope": {
            "entity_a": chart.entity_a,
            "entity_b": chart.entity_b,
            "milestone_count": len(chart.rows),
            "delta_definition": "date_b - date_a (days)",
        },
        "result": {
            "title": chart.title,
            "rows": [row.to_dict() for row in chart.sorted_rows()],
        },
        "artifacts": artifacts or {},
        "errors": [],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Milestone Temporal Dumbbell — compare two entities across milestones"
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
    except (DumbbellValidationError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "errors": [str(exc)]}, ensure_ascii=False))
        return 1

    artifacts: dict[str, str] = {}
    if args.format == "json":
        print(json.dumps(_to_contract(chart, artifacts), ensure_ascii=False, indent=2))
        return 0

    slug = chart_slug(chart)
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
