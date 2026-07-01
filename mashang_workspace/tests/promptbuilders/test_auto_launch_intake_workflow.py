"""
Phase 4: Auto Launch Intake Workflow tests.

Covers:
A. markdown renderer
B. intake workflow
C. CLI availability
D. Anti-regression
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# ── Paths ────────────────────────────────────────────────────────
_TEST_DIR = Path(__file__).resolve().parent
_WORKSPACE = _TEST_DIR.parent.parent  # mashang_workspace/
_PROJECT = _WORKSPACE.parent  # mashang-service root

AUTO_LAUNCH = _WORKSPACE / "promptbuilders" / "auto_launch"
VALIDATORS = AUTO_LAUNCH / "validators"
RENDERERS = AUTO_LAUNCH / "renderers"
INTAKE = AUTO_LAUNCH / "intake"
AI_OUTPUTS = AUTO_LAUNCH / "examples" / "ai_outputs"
NORMALIZED = AUTO_LAUNCH / "examples" / "normalized"
REPORTS = AUTO_LAUNCH / "examples" / "reports"

RADAR_RAW = AI_OUTPUTS / "daily_radar_sample.json"
BRIEF_RAW = AI_OUTPUTS / "event_48h_sample.json"
RADAR_NORM = NORMALIZED / "daily_radar_sample.normalized.json"
BRIEF_NORM = NORMALIZED / "event_48h_sample.normalized.json"

RENDER_SCRIPT = RENDERERS / "render_markdown_report.py"
INTAKE_SCRIPT = INTAKE / "process_ai_output.py"

PYTHON = sys.executable


def _run(cmd, expect_zero=True, cwd=None):
    """Run a command and return result."""
    cwd = cwd or str(_WORKSPACE)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if expect_zero and result.returncode != 0:
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
    return result


# ── A. Markdown renderer ─────────────────────────────────────────


def test_render_event_48h_to_markdown():
    """Render event_48h normalized to markdown."""
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        out = f.name
    try:
        result = _run([PYTHON, str(RENDER_SCRIPT), str(BRIEF_NORM), "--output", out])
        assert result.returncode == 0
        md = Path(out).read_text("utf-8")
        assert "## 1." in md  # has sections
        assert "已确认事实" in md
    finally:
        os.unlink(out)


def test_render_daily_radar_to_markdown():
    """Render daily_radar normalized to markdown."""
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        out = f.name
    try:
        result = _run([PYTHON, str(RENDER_SCRIPT), str(RADAR_NORM), "--output", out])
        assert result.returncode == 0
        md = Path(out).read_text("utf-8")
        assert "已确认事实" in md
        assert "未确认说法" in md
        assert "来源" in md
    finally:
        os.unlink(out)


def test_render_contains_confirmed_inference_unconfirmed():
    """Markdown has separate sections for facts, inferences, unconfirmed."""
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        out = f.name
    try:
        _run([PYTHON, str(RENDER_SCRIPT), str(BRIEF_NORM), "--output", out])
        md = Path(out).read_text("utf-8")
        assert "已确认事实" in md
        assert "推断" in md
        assert "未确认说法" in md
        assert "证据缺口" in md
    finally:
        os.unlink(out)


def test_unconfirmed_claims_not_in_confirmed_section():
    """Unconfirmed claims must not appear in the confirmed_facts section."""
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        out = f.name
    try:
        _run([PYTHON, str(RENDER_SCRIPT), str(BRIEF_NORM), "--output", out])
        md = Path(out).read_text("utf-8")

        # Extract the confirmed facts section
        conf_start = md.find("## 3. 已确认事实")
        unconf_start = md.find("## 5. 未确认说法")
        if conf_start >= 0 and unconf_start > conf_start:
            conf_section = md[conf_start:unconf_start]

            # Load normalized data to get actual unconfirmed claims
            data = json.loads(BRIEF_NORM.read_text("utf-8"))
            for claim in data.get("unconfirmed_claims", []):
                assert claim not in conf_section, \
                    f"unconfirmed claim leaked into confirmed section: {claim}"
    finally:
        os.unlink(out)


# ── B. Intake workflow ──────────────────────────────────────────


def test_intake_event_48h():
    """Full intake on event_48h sample."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f_norm:
        norm_out = f_norm.name
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f_rep:
        rep_out = f_rep.name
    try:
        result = _run([
            PYTHON, str(INTAKE_SCRIPT), str(BRIEF_RAW),
            "--normalized-output", norm_out,
            "--report-output", rep_out,
        ])
        assert result.returncode == 0
        assert "done" in result.stdout
        assert "[auto_launch intake]" in result.stdout

        # Check outputs exist
        assert os.path.exists(norm_out)
        assert os.path.exists(rep_out)

        # Check normalized content
        data = json.loads(Path(norm_out).read_text("utf-8"))
        assert data["record_type"] == "brief"
        assert len(data["source_items"]) > 0
    finally:
        os.unlink(norm_out)
        os.unlink(rep_out)


def test_intake_daily_radar():
    """Full intake on daily_radar sample."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f_norm:
        norm_out = f_norm.name
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f_rep:
        rep_out = f_rep.name
    try:
        result = _run([
            PYTHON, str(INTAKE_SCRIPT), str(RADAR_RAW),
            "--normalized-output", norm_out,
            "--report-output", rep_out,
        ])
        assert result.returncode == 0

        assert os.path.exists(norm_out)
        assert os.path.exists(rep_out)

        data = json.loads(Path(norm_out).read_text("utf-8"))
        assert data["record_type"] == "event"
    finally:
        os.unlink(norm_out)
        os.unlink(rep_out)


def test_intake_fails_on_bad_input():
    """Intake returns non-zero on missing-source_items input."""
    bad = {"event_id": "test"}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bad, f)
        bad_path = f.name
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f_norm:
        norm_out = f_norm.name
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f_rep:
        rep_out = f_rep.name
    try:
        result = _run([
            PYTHON, str(INTAKE_SCRIPT), bad_path,
            "--normalized-output", norm_out,
            "--report-output", rep_out,
        ], expect_zero=False)
        assert result.returncode != 0
        assert "VALIDATION FAILED" in result.stdout
    finally:
        os.unlink(bad_path)
        os.unlink(norm_out)
        os.unlink(rep_out)


# ── C. CLI availability ─────────────────────────────────────────


def test_render_cli_has_output_flag():
    """render_markdown_report.py requires --output."""
    result = _run([PYTHON, str(RENDER_SCRIPT), str(BRIEF_NORM)], expect_zero=False)
    assert result.returncode != 0


def test_intake_cli_has_required_flags():
    """process_ai_output.py requires both --normalized-output and --report-output."""
    result = _run([PYTHON, str(INTAKE_SCRIPT), str(BRIEF_RAW)], expect_zero=False)
    assert result.returncode != 0


# ── D. Anti-regression ──────────────────────────────────────────


def test_makefile_has_no_old_monitor():
    makefile = _PROJECT / "Makefile"
    text = makefile.read_text("utf-8")
    assert "auto-launch-monitor:" not in text


def test_promptbuilders_readme_still_canonical():
    readme = AUTO_LAUNCH / "README.md"
    text = readme.read_text("utf-8")
    assert "Workflow Asset" in text
