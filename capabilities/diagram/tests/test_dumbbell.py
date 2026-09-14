"""Tests for dumbbell rendering, the CLI, and self-check integration."""

import importlib.util
import json
from pathlib import Path

import pytest

from capabilities.diagram.dumbbell import build_chart, load_chart, main, render
from capabilities.diagram.renderers.svg import chart_slug, render_svg
from capabilities.diagram.schemas import DumbbellValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = (
    REPO_ROOT
    / "capabilities"
    / "diagram"
    / "examples"
    / "milestone_dumbbell_tesla_huawei.json"
)
SELF_CHECK = (
    REPO_ROOT / ".opencode" / "skills" / "diagram-design" / "scripts" / "self_check.py"
)


def _payload() -> dict:
    return {
        "title": "BEV 落地时间差",
        "entity_a": "Tesla",
        "entity_b": "Huawei",
        "source_note": "示例数据",
        "rows": [
            {
                "milestone": "BEV",
                "date_a": "2021-08-19",
                "event_a": "AI Day BEV",
                "date_b": "2022-05-07",
                "event_b": "ADS 1.0",
            }
        ],
    }


class TestSvg:
    def test_accessible_svg_contract(self):
        svg = render_svg(build_chart(_payload()))
        assert 'role="img"' in svg
        assert svg.index("<title") < svg.index("<desc")
        assert "<title" in svg and "<desc" in svg

    def test_title_is_first_child(self):
        svg = render_svg(build_chart(_payload()))
        body = svg.split(">", 1)[1]
        assert body.lstrip().startswith("<title")

    def test_prefixed_ids(self):
        chart = build_chart(_payload())
        prefix = chart_slug(chart)
        svg = render_svg(chart)
        assert f'id="{prefix}-title"' in svg
        assert f'id="{prefix}-desc"' in svg
        assert f'aria-labelledby="{prefix}-title {prefix}-desc"' in svg

    def test_contains_two_endpoints_and_delta(self):
        svg = render_svg(build_chart(_payload()))
        assert svg.count("<circle") >= 2
        assert "+261d" in svg
        assert "2021-08-19" in svg and "2022-05-07" in svg

    def test_negative_delta_sign(self):
        payload = _payload()
        row = payload["rows"][0]
        row["date_a"], row["date_b"] = row["date_b"], row["date_a"]
        svg = render_svg(build_chart(payload))
        assert "-261d" in svg

    def test_invalid_chart_raises(self):
        with pytest.raises(DumbbellValidationError):
            render_svg(build_chart({"title": "x", "rows": []}))


class TestHtml:
    def test_self_contained(self):
        html = render(build_chart(_payload()))
        assert html.startswith("<!DOCTYPE html>")
        assert "fonts.googleapis.com" not in html
        assert "<svg" in html
        assert "<script" not in html
        assert "<img" not in html

    def test_uses_local_noto_sans_cjk_sc(self):
        html = render(build_chart(_payload()))
        assert '"Noto Sans CJK SC", sans-serif' in html

    def test_cjk_content_preserved(self):
        html = render(build_chart(_payload()))
        assert "BEV 落地时间差" in html


class TestCli:
    def test_html_output(self, tmp_path, capsys):
        input_path = tmp_path / "chart.json"
        input_path.write_text(json.dumps(_payload()), encoding="utf-8")
        code = main(["--input", str(input_path), "--output-root", str(tmp_path)])
        assert code == 0
        contract = json.loads(capsys.readouterr().out)
        assert contract["status"] == "success"
        assert contract["chart_type"] == "milestone_temporal_dumbbell"
        output = Path(contract["artifacts"]["output"])
        assert output.exists() and output.suffix == ".html"

    def test_json_format_has_no_artifact(self, tmp_path, capsys):
        input_path = tmp_path / "chart.json"
        input_path.write_text(json.dumps(_payload()), encoding="utf-8")
        code = main(["--input", str(input_path), "--format", "json"])
        assert code == 0
        contract = json.loads(capsys.readouterr().out)
        assert contract["artifacts"] == {}
        assert contract["result"]["rows"][0]["delta_days"] == 261

    def test_invalid_input_reports_error(self, tmp_path, capsys):
        input_path = tmp_path / "bad.json"
        input_path.write_text(json.dumps({"rows": []}), encoding="utf-8")
        assert main(["--input", str(input_path)]) == 1
        assert json.loads(capsys.readouterr().out)["status"] == "error"

    def test_load_example_fixture(self):
        chart = load_chart(EXAMPLE)
        assert len(chart.rows) == 3
        assert chart.rows[0].delta_days == 261


class TestSelfCheckIntegration:
    def test_generated_html_passes_diagram_design_self_check(self, tmp_path):
        if not SELF_CHECK.exists():
            pytest.skip("diagram-design skill self_check.py not available")

        spec = importlib.util.spec_from_file_location("diagram_self_check", SELF_CHECK)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        html_path = tmp_path / "dumbbell.html"
        html_path.write_text(render(build_chart(_payload())), encoding="utf-8")
        assert module.verify(html_path) == []
