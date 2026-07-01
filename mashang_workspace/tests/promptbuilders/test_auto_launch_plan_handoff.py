"""
Phase 5: ChatGPT Plan handoff + output-dir workflow tests.

Covers:
A. output-dir mode
B. backward compatibility with --normalized-output/--report-output
C. Makefile anti-regression
D. Runbook existence
E. .gitignore rules
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
_WORKSPACE = _TEST_DIR.parent.parent
_PROJECT = _WORKSPACE.parent

AUTO_LAUNCH = _WORKSPACE / "promptbuilders" / "auto_launch"
INTAKE_SCRIPT = AUTO_LAUNCH / "intake" / "process_ai_output.py"
BRIEF_RAW = AUTO_LAUNCH / "examples" / "ai_outputs" / "event_48h_sample.json"
RADAR_RAW = AUTO_LAUNCH / "examples" / "ai_outputs" / "daily_radar_sample.json"
RUNBOOK = AUTO_LAUNCH / "runbooks" / "chatgpt_plan_handoff.md"
GITIGNORE = _PROJECT / ".gitignore"

PYTHON = sys.executable


def _run(cmd, expect_zero=True, cwd=None):
    cwd = cwd or str(_WORKSPACE)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if expect_zero and result.returncode != 0:
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
    return result


# ── A. output-dir mode ───────────────────────────────────────────


def test_output_dir_creates_all_files():
    """--output-dir generates raw_ai_output.json / normalized.json / report.md / intake_manifest.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run([
            PYTHON, str(INTAKE_SCRIPT), str(BRIEF_RAW),
            "--output-dir", tmpdir,
        ])
        assert result.returncode == 0

        files = os.listdir(tmpdir)
        assert "raw_ai_output.json" in files
        assert "normalized.json" in files
        assert "report.md" in files
        assert "intake_manifest.json" in files


def test_intake_manifest_has_required_fields():
    """intake_manifest.json contains record_type / record_key / confidence_level / counts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _run([
            PYTHON, str(INTAKE_SCRIPT), str(BRIEF_RAW),
            "--output-dir", tmpdir,
        ])
        manifest = json.loads(Path(tmpdir, "intake_manifest.json").read_text("utf-8"))
        for field in ["input_path", "normalized_path", "report_path",
                       "record_type", "record_key", "confidence_level",
                       "created_at",
                       "source_items_count", "confirmed_facts_count",
                       "inferences_count", "unconfirmed_claims_count",
                       "missing_evidence_count"]:
            assert field in manifest, f"manifest missing: {field}"

        assert manifest["record_type"] == "brief"
        assert manifest["record_key"] == "brief_wenjie_m7_launch_2026-07-20_vs_ls8"
        assert manifest["confidence_level"] == "medium"
        assert manifest["source_items_count"] >= 1
        assert manifest["confirmed_facts_count"] >= 1


def test_output_dir_works_with_daily_radar():
    """output-dir also works with event-type input."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run([
            PYTHON, str(INTAKE_SCRIPT), str(RADAR_RAW),
            "--output-dir", tmpdir,
        ])
        assert result.returncode == 0
        manifest = json.loads(Path(tmpdir, "intake_manifest.json").read_text("utf-8"))
        assert manifest["record_type"] == "event"
        assert manifest["record_key"] == "li_i6_presale_2026-07-15"

        files = os.listdir(tmpdir)
        assert "normalized.json" in files
        assert "report.md" in files
        assert "intake_manifest.json" in files


# ── B. Backward compatibility ───────────────────────────────────


def test_old_normalized_report_mode_still_works():
    """--normalized-output + --report-output still works as before."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f_n:
        norm_path = f_n.name
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f_r:
        rpt_path = f_r.name
    try:
        result = _run([
            PYTHON, str(INTAKE_SCRIPT), str(BRIEF_RAW),
            "--normalized-output", norm_path,
            "--report-output", rpt_path,
        ])
        assert result.returncode == 0
        assert os.path.exists(norm_path)
        assert os.path.exists(rpt_path)
    finally:
        os.unlink(norm_path)
        os.unlink(rpt_path)


def test_old_mode_fails_without_report_output():
    """--normalized-output alone should fail (missing --report-output)."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f_n:
        norm_path = f_n.name
    try:
        result = _run([
            PYTHON, str(INTAKE_SCRIPT), str(BRIEF_RAW),
            "--normalized-output", norm_path,
        ], expect_zero=False)
        assert result.returncode != 0
    finally:
        os.unlink(norm_path)


# ── C. Makefile anti-regression ──────────────────────────────────


def test_makefile_has_no_old_monitor():
    makefile = _PROJECT / "Makefile"
    text = makefile.read_text("utf-8")
    assert "auto-launch-monitor:" not in text


def test_makefile_has_intake_target():
    makefile = _PROJECT / "Makefile"
    text = makefile.read_text("utf-8")
    assert "auto-launch-intake:" in text


def test_help_text_not_monitor():
    makefile = _PROJECT / "Makefile"
    text = makefile.read_text("utf-8")
    # Find the help section for auto-launch-intake
    help_lines = [l for l in text.split("\n") if "auto-launch-intake" in l and "echo" in l]
    for line in help_lines:
        assert "monitor" not in line.lower(), \
            f"Help text should not describe intake as monitor: {line}"
        assert "intake" in line.lower()


# ── D. Runbook existence ─────────────────────────────────────────


def test_runbook_exists():
    assert RUNBOOK.exists()


def test_runbook_contains_key_concepts():
    text = RUNBOOK.read_text("utf-8")
    assert "ChatGPT Plan" in text
    assert "validate" in text or "intake" in text
    assert "normalize" in text or "normalized" in text
    assert "report.md" in text
    assert "intake_manifest" in text


def test_runbook_states_boundaries():
    text = RUNBOOK.read_text("utf-8")
    assert "不负责" in text
    assert "搜索" in text
    assert "API" in text or "API" in text
    assert "数据库" in text


# ── E. .gitignore ────────────────────────────────────────────────


def test_gitignore_ignores_auto_launch_outputs():
    assert GITIGNORE.exists()
    text = GITIGNORE.read_text("utf-8")
    # The canonical output directory should be gitignored
    assert "mashang_workspace/outputs/auto_launch/" in text


def test_gitignore_has_defensive_promptbuilders_outputs():
    """promptbuilders/outputs/ should be gitignored as defensive measure."""
    assert GITIGNORE.exists()
    text = GITIGNORE.read_text("utf-8")
    assert "promptbuilders/outputs/" in text


def test_gitignore_does_not_ignore_examples():
    assert GITIGNORE.exists()
    text = GITIGNORE.read_text("utf-8")
    # promptbuilders/auto_launch/examples should NOT be ignored
    # There should be no rule that matches promptbuilders/auto_launch/examples/
    # Check that examples dirs in promptbuilders are not explicitly ignored
    lines_about_examples = [l for l in text.split("\n")
                           if "example" in l.lower() and not l.strip().startswith("#")]
    # Any examples-ignoring line should NOT match our promptbuilders path
    for line in lines_about_examples:
        if "outputs/auto_launch" in line:
            continue  # this is about outputs, not promptbuilders
        if "promptbuilders" in line:
            pytest.fail(f".gitignore should not ignore promptbuilders examples: {line}")


# ── F. Output path canonicalization ─────────────────────────────


def test_no_wrong_output_paths_in_key_files():
    """README / runbooks / Makefile should not reference promptbuilders/outputs/auto_launch."""
    key_files = [
        _PROJECT / "Makefile",
        AUTO_LAUNCH / "README.md",
        RUNBOOK,
    ]
    wrong_pattern = "promptbuilders/outputs/auto_launch"
    for f in key_files:
        if f.exists():
            text = f.read_text("utf-8")
            assert wrong_pattern not in text, f"{f} contains wrong output path: {wrong_pattern}"


def test_promptbuilder_docstring_uses_canonical_output():
    """promptbuilder.py docstring should reference mashang_workspace/outputs/auto_launch/."""
    pb = AUTO_LAUNCH / "promptbuilder.py"
    text = pb.read_text("utf-8")
    assert "mashang_workspace/outputs/auto_launch/prompts/" in text


# ── G. Legacy outputs cleanup ────────────────────────────────────


def test_old_output_dirs_removed():
    """Old runtime output subdirs should not exist in outputs/auto_launch."""
    out_root = _PROJECT / "mashang_workspace" / "outputs" / "auto_launch"
    for bad_dir in ["ai_response_examples", "prompts", "normalized", "reports"]:
        assert not (out_root / bad_dir).exists(), \
            f"Old output dir should be removed: {bad_dir}"


def test_golden_cases_renamed_to_legacy():
    """Old golden_cases is renamed to legacy_promptbuilder_cases."""
    golden = AUTO_LAUNCH / "examples" / "golden_cases"
    legacy = AUTO_LAUNCH / "examples" / "legacy_promptbuilder_cases"
    assert not golden.exists(), "golden_cases should no longer exist"
    assert legacy.exists(), "legacy_promptbuilder_cases should exist"


def test_legacy_cases_exist():
    """Legacy promptbuilder cases are preserved under new name."""
    legacy = AUTO_LAUNCH / "examples" / "legacy_promptbuilder_cases"
    assert (legacy / "byd_datang_ev_launch_7d_vs_ls8.md").exists()
    assert (legacy / "byd_datang_ev_launch_7d_vs_ls8.metadata.json").exists()
    assert (legacy / "ledao_l80_launch_48h_vs_ls8.md").exists()
    assert (legacy / "wenjie_m7_launch_72h_vs_ls8.md").exists()
    assert (legacy / "xiaomi_yu7_launch_72h_vs_competitors.md").exists()


def test_readme_mentions_examples_boundary():
    """README clarifies the boundary between examples/ and outputs/."""
    text = (AUTO_LAUNCH / "README.md").read_text("utf-8")
    assert "只用于新 intake workflow" in text
    assert "可提交的样例" in text


def test_readme_does_not_call_legacy_golden():
    """README directory listing should use legacy_promptbuilder_cases, not golden_cases."""
    text = (AUTO_LAUNCH / "README.md").read_text("utf-8")
    lines = text.split("\n")
    # Find the directory listing section for examples/
    in_examples = False
    found_legacy = False
    for line in lines:
        if "committed samples" in line:
            in_examples = True
            continue
        if in_examples and line.strip().startswith("├──") or line.strip().startswith("└──"):
            if "legacy_promptbuilder_cases" in line:
                found_legacy = True
            if "golden_cases" in line:
                assert False, f"directory listing should not reference golden_cases: {line}"
    assert found_legacy, "directory listing should reference legacy_promptbuilder_cases"


def test_readme_legacy_not_regression_standard():
    """README clarifies legacy cases are not regression standard."""
    text = (AUTO_LAUNCH / "README.md").read_text("utf-8")
    assert "不构成 regression 基准" in text
    assert "不代表当前工作流的质量标准" in text


def test_runbook_mentions_examples_boundary():
    """Runbook clarifies the boundary between examples/ and outputs/."""
    text = RUNBOOK.read_text("utf-8")
    assert "可提交的样例" in text
    assert "examples/" in text
