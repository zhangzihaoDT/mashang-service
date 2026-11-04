"""Tests for the comparison line primitive: contract, SVG rules, CLI."""

import json
import tempfile
from pathlib import Path

import pytest

from capabilities.diagram.compare_line import (
    build_chart,
    load_chart,
    main,
    render,
    render_svg,
)
from capabilities.diagram.renderers.line import line_slug, nice_step, series_styles
from capabilities.diagram.schemas import (
    CHART_TYPE_COMPARISON_LINE,
    ComparisonLineChart,
    ComparisonLineValidationError,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = (
    REPO_ROOT
    / "capabilities"
    / "diagram"
    / "examples"
    / "comparison_line_ls8neo.json"
)


def _payload() -> dict:
    return {
        "title": "预售前 4 日累计",
        "categories": ["N0 末", "N1 末", "N2 末"],
        "series": [
            {"name": "本品", "role": "own", "values": [3, 4, 5]},
            {"name": "对标 A", "values": [6, 7, 8]},
        ],
        "source_note": "示例数据",
    }


class TestContract:
    def test_validate_keeps_declaration_order(self):
        chart = build_chart(_payload())
        assert chart.chart_type == CHART_TYPE_COMPARISON_LINE
        assert [item.name for item in chart.series] == ["本品", "对标 A"]
        assert chart.own_series is not None
        assert chart.own_series.name == "本品"
        assert chart.value_bounds() == (3.0, 8.0)

    def test_rejects_single_series(self):
        payload = _payload()
        payload["series"] = payload["series"][:1]
        with pytest.raises(ComparisonLineValidationError, match="at least two series"):
            build_chart(payload)

    def test_rejects_category_length_mismatch(self):
        payload = _payload()
        payload["series"][1]["values"] = [1, 2]
        with pytest.raises(ComparisonLineValidationError, match="values but the chart has"):
            build_chart(payload)

    def test_rejects_duplicate_series_names(self):
        payload = _payload()
        payload["series"][1]["name"] = "本品"
        with pytest.raises(ComparisonLineValidationError, match="duplicate series name"):
            build_chart(payload)

    def test_rejects_two_own_series(self):
        payload = _payload()
        payload["series"][1]["role"] = "own"
        with pytest.raises(ComparisonLineValidationError, match="at most one series"):
            build_chart(payload)

    def test_rejects_non_numeric_values(self):
        payload = _payload()
        payload["series"][1]["values"] = [1, "n/a", 3]
        with pytest.raises(ComparisonLineValidationError, match="must be a number"):
            build_chart(payload)

    def test_rejects_duplicate_categories(self):
        payload = _payload()
        payload["categories"] = ["N0", "N0", "N1"]
        with pytest.raises(ComparisonLineValidationError, match="categories must be unique"):
            build_chart(payload)

    def test_example_file_loads(self):
        chart = load_chart(EXAMPLE)
        assert chart.own_series is not None
        assert chart.own_series.name == "LS8 NEO"
        assert len(chart.categories) == 4


class TestStyleRules:
    def test_own_is_solid_and_peers_are_dashed(self):
        chart = build_chart(_payload())
        styles = series_styles(chart)
        assert styles[0]["dash"] == ""
        assert styles[0]["width"] > styles[1]["width"]
        assert styles[1]["dash"] != ""

    def test_own_color_differs_from_peers(self):
        payload = _payload()
        payload["series"].append({"name": "对标 B", "values": [2, 3, 4]})
        payload["series"].append({"name": "对标 C", "values": [1, 2, 3]})
        colors = [style["color"] for style in series_styles(build_chart(payload))]
        assert len(set(colors)) == len(colors)

    def test_colour_and_dash_can_be_overridden(self):
        payload = _payload()
        payload["series"][1]["color"] = "#000000"
        payload["series"][1]["dash"] = "2 2"
        styles = series_styles(build_chart(payload))
        assert styles[1]["color"] == "#000000"
        assert styles[1]["dash"] == "2 2"

    def test_nice_step(self):
        assert nice_step(9046 - 0) == 2000
        assert nice_step(100) == 20


class TestSvg:
    def test_accessible_svg_contract(self):
        chart = build_chart(_payload())
        svg = render_svg(chart)
        prefix = line_slug(chart)
        assert 'role="img"' in svg
        assert f'aria-labelledby="{prefix}-title {prefix}-desc"' in svg
        assert svg.index("<title") < svg.index("<desc")
        body = svg.split(">", 1)[1]
        assert body.lstrip().startswith("<title")

    def test_legend_and_end_labels_present(self):
        chart = build_chart(_payload())
        svg = render_svg(chart)
        for item in chart.series:
            assert item.name in svg
        assert ">8</text>" in svg  # peer's last value
        assert ">5</text>" in svg  # own's last value
        assert svg.count("<polyline") == len(chart.series)

    def test_peers_use_dash_arrays(self):
        svg = render_svg(build_chart(_payload()))
        assert "stroke-dasharray" in svg

    def test_markers_auto_on_short_series(self):
        svg = render_svg(build_chart(_payload()))
        assert "<circle" in svg

    def test_markers_off_when_disabled(self):
        payload = _payload()
        payload["markers"] = False
        payload["categories"] = [f"N{i}" for i in range(3)]
        svg = render_svg(build_chart(payload))
        assert "<circle" not in svg

    def test_no_javascript(self):
        html = render(build_chart(_payload()))
        assert "<script" not in html


class TestCli:
    def test_html_output(self):
        out_dir = Path(tempfile.mkdtemp())
        target = out_dir / "chart.html"
        code = main(["--input", str(EXAMPLE), "--format", "html", "--output", str(target)])
        assert code == 0
        assert target.exists()
        assert "<svg" in target.read_text(encoding="utf-8")

    def test_json_contract(self, capsys):
        code = main(["--input", str(EXAMPLE), "--format", "json"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "success"
        assert payload["chart_type"] == CHART_TYPE_COMPARISON_LINE
        assert payload["scope"]["own_series"] == "LS8 NEO"
        assert payload["scope"]["series_count"] == 4

    def test_invalid_input_returns_error(self, capsys, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"categories": ["a"], "series": []}), encoding="utf-8")
        code = main(["--input", str(bad), "--format", "json"])
        assert code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "error"

    def test_from_dict_roundtrip(self):
        chart = build_chart(_payload())
        again = ComparisonLineChart.from_dict(chart.to_dict()).validate()
        assert again.to_dict() == chart.to_dict()
