"""
Daily Monitor Report generator tests.

Covers:
1. Real intake outputs generate report
2. No-event day generates report
3. Missing fields don't crash
4. HTML contains core content
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_WORKSPACE = _TEST_DIR.parent.parent
_PROJECT = _WORKSPACE.parent

AUTO_LAUNCH = _WORKSPACE / "promptbuilders" / "auto_launch"
INTAKE_SCRIPT = AUTO_LAUNCH / "intake" / "process_ai_output.py"
REPORT_SCRIPT = AUTO_LAUNCH / "reports" / "generate_daily_monitor_report.py"

PYTHON = sys.executable

# ── Sample data ──────────────────────────────────────────────────

DAILY_SAMPLE = {
    "task_name": "auto_launch_daily_sales_action_monitor",
    "battle_field": "large_six_seat_suv",
    "our_model": "智己 LS8",
    "monitor_date": "2026-07-01",
    "time_window": {"start": "2026-06-30", "end": "2026-07-01"},
    "input_assets": {"watchlist_path": "x.csv", "event_types_path": "x.yaml"},
    "event_candidates": [
        {
            "event_model": "问界 M7", "event_brand": "问界",
            "event_type": "official_rights_update", "event_name": "权益更新",
            "event_date": "2026-07-01", "confidence": "medium",
            "source_items": [{"source_name": "官网", "source_title": "公告",
                              "source_url": "https://example.com", "source_tier": "official",
                              "publish_time": "2026-07-01"}],
            "impact_vs_our_model": {"price_pressure": "medium", "rights_pressure": "high",
                                     "configuration_pressure": "low", "delivery_pressure": "unknown"},
            "missing_evidence": ["缺数据"]
        }
    ],
    "no_event_models": ["零跑 D19", "小鹏 GX"],
    "needs_review": [{"event_model": "理想 i6", "reason": "来源不足"}],
}

DAILY_EMPTY = {
    "task_name": "auto_launch_daily_sales_action_monitor",
    "battle_field": "large_six_seat_suv",
    "our_model": "智己 LS8",
    "monitor_date": "2026-07-01",
    "time_window": {"start": "2026-06-30", "end": "2026-07-01"},
    "input_assets": {"watchlist_path": "x.csv", "event_types_path": "x.yaml"},
    "event_candidates": [],
    "no_event_models": ["零跑 D19", "小鹏 GX", "理想 i6"],
    "needs_review": [],
}


def _run_intake(data, tmpdir):
    """Run intake on data in tmpdir, return intake dir path."""
    in_path = os.path.join(tmpdir, "input.json")
    with open(in_path, "w") as f:
        json.dump(data, f)
    out_dir = os.path.join(tmpdir, "out")
    result = subprocess.run(
        [PYTHON, str(INTAKE_SCRIPT), in_path, "--output-dir", out_dir],
        capture_output=True, text=True, cwd=str(_WORKSPACE),
    )
    assert result.returncode == 0, f"intake failed: {result.stdout}"
    return out_dir


def _run_report(intake_dir, tmpdir):
    """Run report generator on intake_dir, outputting to tmpdir."""
    md_path = os.path.join(tmpdir, "report.md")
    html_path = os.path.join(tmpdir, "report.html")
    result = subprocess.run(
        [PYTHON, str(REPORT_SCRIPT), "--input-dir", intake_dir,
         "--output-md", md_path, "--output-html", html_path],
        capture_output=True, text=True, cwd=str(_WORKSPACE),
    )
    assert result.returncode == 0, f"report failed: {result.stdout}"
    return md_path, html_path


# ── 1. Real intake outputs generate report ──────────────────────


def test_report_generates_md_and_html():
    """Report generator produces both MD and HTML from real intake outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        intake_dir = _run_intake(DAILY_SAMPLE, tmpdir)
        md_path, html_path = _run_report(intake_dir, tmpdir)

        assert os.path.exists(md_path)
        assert os.path.exists(html_path)

        md = Path(md_path).read_text("utf-8")
        assert "# Auto Launch Daily Monitor Report" in md
        assert "问界 M7" in md
        assert "official_rights_update" in md

        html = Path(html_path).read_text("utf-8")
        assert "Auto Launch Daily Monitor Report" in html
        assert "Event Candidates" in html


# ── 2. No-event day generates report ────────────────────────────


def test_no_event_day_report():
    """No-event day with empty candidates should generate report."""
    with tempfile.TemporaryDirectory() as tmpdir:
        intake_dir = _run_intake(DAILY_EMPTY, tmpdir)
        md_path, html_path = _run_report(intake_dir, tmpdir)

        md = Path(md_path).read_text("utf-8")
        assert "None" in md
        assert "no-event daily monitor pilot" in md

        html = Path(html_path).read_text("utf-8")
        assert "report_manifest.json" in os.listdir(intake_dir)


# ── 3. HTML contains core content ──────────────────────────────


def test_html_has_summary_cards():
    """HTML report should have summary count cards."""
    with tempfile.TemporaryDirectory() as tmpdir:
        intake_dir = _run_intake(DAILY_SAMPLE, tmpdir)
        _, html_path = _run_report(intake_dir, tmpdir)

        html = Path(html_path).read_text("utf-8")
        # Summary cards
        assert "summary-cards" in html
        assert "Event Candidates" in html
        assert "Needs Review" in html
        # Core sections
        assert "Run Summary" in html
        assert "今日明确销售动作" in html
        assert "待复核项目" in html
        assert "未发现动作车型" in html or "未发现明确动作车型" in html
        assert "Next Step" in html


# ── 4. report_manifest created ──────────────────────────────────


def test_report_manifest_created():
    """report_manifest.json should be created in intake dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        intake_dir = _run_intake(DAILY_SAMPLE, tmpdir)
        _run_report(intake_dir, tmpdir)

        manifest = json.loads(Path(intake_dir, "report_manifest.json").read_text("utf-8"))
        assert manifest["report_type"] == "daily_monitor_report"
        assert manifest["event_candidates_count"] == 1
        assert manifest["needs_review_count"] == 1
        assert manifest["no_event_models_count"] == 2
