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


# ── E. source_items rendering ────────────────────────────────────


def test_report_source_table_no_question_marks():
    """Report source table should not render as | ? | ? | ? |."""
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        out = f.name
    try:
        _run([PYTHON, str(RENDER_SCRIPT), str(BRIEF_NORM), "--output", out])
        md = Path(out).read_text("utf-8")
        # Find the source table section
        src_section = md[md.find("## 8. 来源"):]
        # Check no placeholder values
        assert "| ? | ? | ? |" not in src_section
        assert "| ? | ? | ? | ? |" not in src_section
    finally:
        os.unlink(out)


def test_report_source_shows_tier_and_name():
    """Report source table should show source_tier and source_name."""
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        out = f.name
    try:
        _run([PYTHON, str(RENDER_SCRIPT), str(BRIEF_NORM), "--output", out])
        md = Path(out).read_text("utf-8")
        assert "example.com" in md or "http" in md
        # Should show source_tier values, not "unknown" for known tier
        data = json.loads(BRIEF_NORM.read_text("utf-8"))
        for item in data.get("source_items", []):
            tier = item.get("source_tier") or item.get("tier") or ""
            if tier or tier == 0:
                tier_str = str(tier)
                assert tier_str in md or f"| {tier_str} |" in md
    finally:
        os.unlink(out)


# ── F. Structured field rendering ───────────────────────────────


RENDERER_DIR = AUTO_LAUNCH / "renderers"


def _render_with_input(normalized_data, suffix=".md"):
    """Render arbitrary normalized data to a temp md file and return path + content."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(normalized_data, f)
        norm_path = f.name
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        md_path = f.name
    result = _run([
        PYTHON, str(RENDERER_DIR / "render_markdown_report.py"),
        norm_path, "--output", md_path,
    ])
    md = Path(md_path).read_text("utf-8")
    os.unlink(norm_path)
    os.unlink(md_path)
    return result, md


def test_structured_confirmed_facts_no_dict_string():
    """Structured confirmed_facts dict should not render Python dict string."""
    data = {
        "record_type": "brief",
        "record_key": "test",
        "confirmed_facts": [
            {"fact": "问界M7增程长续航版于6月29日上市",
             "source_ids": ["S1", "S2"],
             "confidence_level": "high"},
        ],
        "inferences": [],
        "unconfirmed_claims": [],
        "missing_evidence": [],
        "source_items": [],
    }
    result, md = _render_with_input(data)
    assert result.returncode == 0
    assert "{'fact':" not in md
    assert "问界M7增程长续航版" in md
    assert "S1" in md
    assert "置信度" in md


def test_structured_inferences_no_dict_string():
    """Structured inferences dict should not render Python dict string."""
    data = {
        "record_type": "brief",
        "record_key": "test",
        "confirmed_facts": [],
        "inferences": [
            {"inference": "M7长续航版与LS8价格带重叠",
             "basis": "两车起售价均为30万级",
             "source_ids": ["S1"],
             "confidence_level": "medium"},
        ],
        "unconfirmed_claims": [],
        "missing_evidence": [],
        "source_items": [],
    }
    result, md = _render_with_input(data)
    assert result.returncode == 0
    assert "{'inference':" not in md
    assert "M7长续航版" in md
    assert "两车起售价" in md


def test_structured_missing_evidence_no_dict_string():
    """Structured missing_evidence dict should not render Python dict string."""
    data = {
        "record_type": "brief",
        "record_key": "test",
        "confirmed_facts": [],
        "inferences": [],
        "unconfirmed_claims": [],
        "missing_evidence": [
            {"field": "智己LS8近期锁单数据",
             "why_it_matters": "无法判断M7上市对LS8的实际销量影响",
             "suggested_followup": "等待下月销量数据公布"},
        ],
        "source_items": [],
    }
    result, md = _render_with_input(data)
    assert result.returncode == 0
    assert "{'field':" not in md
    assert "智己LS8" in md
    assert "无法判断" in md


def test_structured_unconfirmed_claims_no_dict_string():
    """Structured unconfirmed_claims dict should not render Python dict string."""
    data = {
        "record_type": "brief",
        "record_key": "test",
        "confirmed_facts": [],
        "inferences": [],
        "unconfirmed_claims": [
            {"claim": "智己可能近期调整LS8权益",
             "source_ids": ["S3"],
             "reason_unconfirmed": "仅来自论坛用户讨论"},
        ],
        "missing_evidence": [],
        "source_items": [],
    }
    result, md = _render_with_input(data)
    assert result.returncode == 0
    assert "{'claim':" not in md
    assert "调整LS8权益" in md
    assert "论坛用户讨论" in md


def test_structured_string_fallback_still_works():
    """String-array items should still render as simple bullets."""
    data = {
        "record_type": "brief",
        "record_key": "test",
        "confirmed_facts": ["普通字符串事实"],
        "inferences": ["普通字符串推断"],
        "unconfirmed_claims": ["普通字符串说法"],
        "missing_evidence": ["普通字符串缺口"],
        "source_items": [],
    }
    result, md = _render_with_input(data)
    assert result.returncode == 0
    assert "普通字符串事实" in md
    assert "普通字符串推断" in md
    assert "普通字符串说法" in md
    assert "普通字符串缺口" in md
