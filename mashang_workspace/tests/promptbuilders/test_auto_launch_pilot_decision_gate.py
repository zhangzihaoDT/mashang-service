"""
Phase 8: Auto Launch Pilot Run Decision Gate tests.

Covers:
A. Runbook existence and content
B. Scorecard existence and content
C. README boundary
D. Anti-regression
"""

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────
_TEST_DIR = Path(__file__).resolve().parent
_WORKSPACE = _TEST_DIR.parent.parent
_PROJECT = _WORKSPACE.parent

AUTO_LAUNCH = _WORKSPACE / "promptbuilders" / "auto_launch"
RUNBOOK = AUTO_LAUNCH / "runbooks" / "pilot_run_decision_gate.md"
SCORECARD = AUTO_LAUNCH / "templates" / "pilot_quality_scorecard.md"
LEGACY_DIR = AUTO_LAUNCH / "examples" / "legacy_promptbuilder_cases"
GOLDEN_DIR = AUTO_LAUNCH / "examples" / "golden_cases"


# ── A. Runbook existence and content ─────────────────────────────


def test_runbook_exists():
    assert RUNBOOK.exists()


def test_runbook_contains_chatgpt_plan():
    text = RUNBOOK.read_text("utf-8")
    assert "ChatGPT Plan" in text
    assert "chatgpt_plan_event_48h" in text


def test_runbook_contains_volc_search():
    text = RUNBOOK.read_text("utf-8")
    assert "Volc Search" in text
    assert "volc" in text.lower()


def test_runbook_contains_intake():
    text = RUNBOOK.read_text("utf-8")
    assert "auto-launch-intake" in text
    assert "intake" in text


def test_runbook_contains_output_dir():
    text = RUNBOOK.read_text("utf-8")
    assert "output-dir" in text or "OUT_DIR" in text or "output_dir" in text


def test_runbook_contains_golden_case_criteria():
    text = RUNBOOK.read_text("utf-8")
    assert "golden case" in text
    assert "晋升" in text


def test_runbook_no_registry():
    """Runbook should not mention creating a registry."""
    text = RUNBOOK.read_text("utf-8")
    # "registry" is only OK if it's saying NOT to create one
    assert "不创建" in text or "registry" not in text.lower()


# ── B. Scorecard existence and content ───────────────────────────


def test_scorecard_exists():
    assert SCORECARD.exists()


def test_scorecard_contains_structure_checks():
    text = SCORECARD.read_text("utf-8")
    assert "validate passed" in text
    assert "normalize passed" in text
    assert "report generated" in text


def test_scorecard_contains_quality_dimensions():
    text = SCORECARD.read_text("utf-8")
    assert "source quality" in text
    assert "fact / inference separation" in text
    assert "impact analysis depth" in text
    assert "sales response usefulness" in text
    assert "uncertainty handling" in text
    assert "report readability" in text
    assert "reuse value" in text


def test_scorecard_contains_decision():
    text = SCORECARD.read_text("utf-8")
    assert "是否可晋升" in text or "Golden Case" in text
    assert "decision" in text or "decision" in text.lower()


# ── C. README boundary ──────────────────────────────────────────


def test_readme_no_current_golden():
    readme = (AUTO_LAUNCH / "README.md").read_text("utf-8")
    assert "暂无 golden cases" in readme


def test_readme_legacy_not_regression():
    readme = (AUTO_LAUNCH / "README.md").read_text("utf-8")
    assert "不构成 regression 基准" in readme


def test_readme_mentions_pilot_decision_gate():
    readme = (AUTO_LAUNCH / "README.md").read_text("utf-8")
    assert "Pilot Run Decision Gate" in readme
    assert "pilot_quality_scorecard" in readme or "scorecard" in readme


# ── D. Anti-regression ──────────────────────────────────────────


def test_golden_cases_dir_not_exists():
    assert not GOLDEN_DIR.exists()


def test_legacy_promptbuilder_cases_exists():
    assert LEGACY_DIR.exists()


def test_no_registry_json():
    """No registry.json exists anywhere in promptbuilders/auto_launch."""
    registries = list(AUTO_LAUNCH.rglob("registry.json"))
    assert len(registries) == 0, f"registry.json found: {registries}"


def test_outputs_not_polluted():
    """outputs/auto_launch should not contain old prompt/report dirs."""
    out_root = _PROJECT / "mashang_workspace" / "outputs" / "auto_launch"
    if out_root.exists():
        for bad in ["ai_response_examples", "prompts", "normalized", "reports"]:
            assert not (out_root / bad).exists(), f"outputs still contains {bad}"
