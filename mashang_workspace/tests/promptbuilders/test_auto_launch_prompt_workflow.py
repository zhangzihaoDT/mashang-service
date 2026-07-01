"""
Phase 2: Auto Launch Prompt Workflow Structure Tests

Covers:
A. Core file existence
B. Prompt section integrity
C. Variable placeholder coverage
D. Credibility and source requirements
E. Schema basic fields
F. Old monitor no longer primary entry
"""

import json
import os
from pathlib import Path

# test file: mashang_workspace/tests/promptbuilders/test_auto_launch_prompt_workflow.py
# target:     mashang_workspace/promptbuilders/auto_launch/
_TEST_DIR = Path(__file__).resolve().parent  # .../tests/promptbuilders
_WORKSPACE = _TEST_DIR.parent  # .../tests
_WORKSPACE_ROOT = _WORKSPACE.parent  # .../mashang_workspace
_PROJECT_ROOT = _WORKSPACE_ROOT.parent  # .../mashang-service/
BASE = _WORKSPACE_ROOT / "promptbuilders" / "auto_launch"
PROMPTS = BASE / "prompts"
PLANS = BASE / "plan_templates"
SCHEMAS = BASE / "schemas"
SEARCH = BASE / "search_adapters"
VALIDATORS = BASE / "validators"


# ── A. Core file existence ────────────────────────────────────────


def test_readme_exists():
    assert (BASE / "README.md").exists()


def test_all_prompts_exist():
    expected = [
        "daily_radar.md",
        "event_48h_brief.md",
        "event_72h_followup.md",
        "impact_vs_our_model.md",
        "llm_judge.md",
    ]
    for name in expected:
        assert (PROMPTS / name).exists(), f"Missing: {name}"


def test_all_plan_templates_exist():
    expected = [
        "chatgpt_plan_daily_radar.md",
        "chatgpt_plan_event_48h.md",
    ]
    for name in expected:
        assert (PLANS / name).exists(), f"Missing: {name}"


def test_schemas_exist():
    assert (SCHEMAS / "auto_launch_event.schema.json").exists()
    assert (SCHEMAS / "auto_launch_brief.schema.json").exists()


def test_search_adapters_exist():
    assert (SEARCH / "README.md").exists()
    assert (SEARCH / "volc_search.md").exists()


def test_validators_readme_exists():
    assert (VALIDATORS / "README.md").exists()


# ── B. Prompt section integrity ──────────────────────────────────

PLAN_READY_PROMPTS = ["daily_radar.md", "event_48h_brief.md",
                       "event_72h_followup.md", "impact_vs_our_model.md"]

REQUIRED_SECTIONS = ["Role", "Output Format", "Validation Rules", "Uncertainty Rules"]
PLAN_EXTRA_SECTIONS = ["Time Window", "Source Rules"]


def _read_prompt(name):
    return (PROMPTS / name).read_text("utf-8")


def _read_plan(name):
    return (PLANS / name).read_text("utf-8")


def test_daily_radar_has_required_sections():
    text = _read_prompt("daily_radar.md")
    for sec in REQUIRED_SECTIONS + PLAN_EXTRA_SECTIONS:
        assert f"## {sec}" in text, f"daily_radar missing section: {sec}"


def test_event_48h_brief_has_required_sections():
    text = _read_prompt("event_48h_brief.md")
    for sec in REQUIRED_SECTIONS + PLAN_EXTRA_SECTIONS:
        assert f"## {sec}" in text, f"event_48h_brief missing section: {sec}"


def test_event_72h_followup_has_required_sections():
    text = _read_prompt("event_72h_followup.md")
    for sec in REQUIRED_SECTIONS + PLAN_EXTRA_SECTIONS:
        assert f"## {sec}" in text, f"event_72h_followup missing section: {sec}"


def test_impact_vs_our_model_has_required_sections():
    text = _read_prompt("impact_vs_our_model.md")
    for sec in REQUIRED_SECTIONS + PLAN_EXTRA_SECTIONS:
        assert f"## {sec}" in text, f"impact_vs_our_model missing section: {sec}"


def test_llm_judge_has_required_sections():
    text = _read_prompt("llm_judge.md")
    assert "## Role" in text
    assert "## Output Format" in text
    assert "## Validation Rules" in text, "llm_judge.md missing Validation Rules"
    assert "## Uncertainty Rules" in text, "llm_judge.md missing Uncertainty Rules"


# ── C. Variable placeholder coverage ─────────────────────────────

# Variables may appear with or without spaces: {{time_window}} or {{ time_window }}
# We normalize by stripping braces inner whitespace for matching.
def _var_bare(var):
    """Convert {{time_window}} to {{ time_window }} for matching."""
    inner = var.strip("{}").strip()
    return "{{" + inner + "}}"


_REQUIRED_VARS_ALL = ["{{time_window}}", "{{battle_field}}", "{{watchlist}}"]
_REQUIRED_VARS_EVENT = ["{{event_model}}", "{{event_type}}"]


def _check_var_in_text(text, var_bare):
    """Check both {{var}} and {{ var }} forms."""
    var_no_space = "{{" + var_bare.strip("{}").strip() + "}}"
    var_with_space = "{{ " + var_bare.strip("{}").strip() + " }}"
    return var_no_space in text or var_with_space in text


def test_daily_radar_has_required_vars():
    text = _read_prompt("daily_radar.md")
    for var_bare in _REQUIRED_VARS_ALL:
        assert _check_var_in_text(text, var_bare), f"daily_radar missing var: {var_bare}"


def test_event_48h_brief_has_required_vars():
    text = _read_prompt("event_48h_brief.md")
    for var_bare in _REQUIRED_VARS_ALL + _REQUIRED_VARS_EVENT:
        assert _check_var_in_text(text, var_bare), f"event_48h_brief missing var: {var_bare}"
    assert _check_var_in_text(text, "{{our_model}}"), "event_48h_brief missing {{our_model}}"


def test_event_72h_followup_has_required_vars():
    text = _read_prompt("event_72h_followup.md")
    for var_bare in _REQUIRED_VARS_ALL + _REQUIRED_VARS_EVENT:
        assert _check_var_in_text(text, var_bare), f"event_72h_followup missing var: {var_bare}"
    assert _check_var_in_text(text, "{{our_model}}"), "event_72h_followup missing {{our_model}}"


def test_impact_vs_our_model_has_required_vars():
    text = _read_prompt("impact_vs_our_model.md")
    for var_bare in _REQUIRED_VARS_ALL + _REQUIRED_VARS_EVENT:
        assert _check_var_in_text(text, var_bare), f"impact_vs_our_model missing var: {var_bare}"


# ── D. Credibility and source requirements ───────────────────────

CREDIBILITY_KEYWORDS = ["source", "confidence", "confirmed_fact",
                        "inference", "unconfirmed_claim"]

MISSING_EVIDENCE_KEYWORDS = ["missing_evidence", "unresolved_questions"]

PROMPT_CREDIBILITY_CHECKS = [
    ("daily_radar.md", CREDIBILITY_KEYWORDS),
    ("daily_radar.md", MISSING_EVIDENCE_KEYWORDS),
    ("event_48h_brief.md", CREDIBILITY_KEYWORDS),
    ("event_48h_brief.md", MISSING_EVIDENCE_KEYWORDS),
    ("event_72h_followup.md", CREDIBILITY_KEYWORDS),
    ("event_72h_followup.md", MISSING_EVIDENCE_KEYWORDS),
    ("impact_vs_our_model.md", CREDIBILITY_KEYWORDS),
    ("impact_vs_our_model.md", MISSING_EVIDENCE_KEYWORDS),
    ("llm_judge.md", CREDIBILITY_KEYWORDS),
]

PLAN_CREDIBILITY_CHECKS = [
    ("chatgpt_plan_daily_radar.md", CREDIBILITY_KEYWORDS),
    ("chatgpt_plan_daily_radar.md", MISSING_EVIDENCE_KEYWORDS),
    ("chatgpt_plan_event_48h.md", CREDIBILITY_KEYWORDS),
    ("chatgpt_plan_event_48h.md", MISSING_EVIDENCE_KEYWORDS),
]


def _check_credibility(text, keywords):
    """Check that at least one keyword from each group is present."""
    for keyword in keywords:
        if keyword in text:
            return True
    return False


def test_prompt_credibility():
    for name, keywords in PROMPT_CREDIBILITY_CHECKS:
        text = _read_prompt(name)
        assert _check_credibility(text, keywords), \
            f"{name} missing credibility keywords: {keywords}"


def test_plan_credibility():
    for name, keywords in PLAN_CREDIBILITY_CHECKS:
        text = _read_plan(name)
        assert _check_credibility(text, keywords), \
            f"{name} missing credibility keywords: {keywords}"


def test_prompt_no_source_no_conclusion():
    """All prompts should forbid conclusions without sources."""
    for name in PLAN_READY_PROMPTS:
        text = _read_prompt(name)
        assert "无来源" in text and "来源 URL" in text, \
            f"{name} missing source requirement"


def test_plan_no_source_no_conclusion():
    for name in ["chatgpt_plan_daily_radar.md", "chatgpt_plan_event_48h.md"]:
        text = _read_plan(name)
        assert "来源 URL" in text, f"{name} missing source URL requirement"


# ── E. Schema basic fields ───────────────────────────────────────

def _read_schema(name):
    return json.loads((SCHEMAS / name).read_text("utf-8"))


def test_event_schema_has_minimal_fields():
    schema = _read_schema("auto_launch_event.schema.json")
    props = schema.get("properties", {})
    required = schema.get("required", [])
    for field in ["event_id", "event", "battle_field", "confirmed_facts",
                   "inferences", "unconfirmed_claims", "confidence_level"]:
        assert field in props or field in required, \
            f"event schema missing field: {field}"
        assert field in required, \
            f"event schema required missing: {field}"


def test_brief_schema_has_minimal_fields():
    schema = _read_schema("auto_launch_brief.schema.json")
    props = schema.get("properties", {})
    required = schema.get("required", [])
    for field in ["brief_id", "our_model", "event_model", "battle_field",
                   "time_window", "executive_summary", "source_items",
                   "missing_evidence", "confidence_level", "followup_recommendation"]:
        assert field in props or field in required, \
            f"brief schema missing field: {field}"
        assert field in required, \
            f"brief schema required missing: {field}"


# ── F. Old monitor no longer primary entry ───────────────────────

def test_makefile_has_no_auto_launch_monitor_target():
    makefile = _PROJECT_ROOT / "Makefile"
    assert makefile.exists()
    text = makefile.read_text("utf-8")
    assert "auto-launch-monitor:" not in text, \
        "Makefile still contains auto-launch-monitor target"


def test_root_agents_md_does_not_recommend_old_monitor():
    agents = _PROJECT_ROOT / "AGENTS.md"
    assert agents.exists()
    text = agents.read_text("utf-8")
    assert "auto_launch_monitor.py" not in text, \
        "Root AGENTS.md still references old monitor"


def test_workspace_agents_md_references_old_monitor_only_as_history():
    """Workspace AGENTS.md may mention old monitor in transition notes,
    but should not recommend it as an active entry point."""
    agents = _WORKSPACE_ROOT / "AGENTS.md"
    assert agents.exists()
    text = agents.read_text("utf-8")
    # Allow mention with "已下线" marker
    if "auto_launch_monitor.py" in text:
        assert "已下线" in text, \
            "Workspace AGENTS.md must mark old monitor as 已下线"


def test_promptbuilders_readme_is_canonical():
    readme = (BASE / "README.md").read_text("utf-8")
    assert "Prompt Workflow Asset" in readme or "Workflow Asset" in readme, \
        "README is not positioned as Prompt workflow asset"
    assert "已下线" in readme or "legacy" in readme.lower(), \
        "README does not mention legacy status"


def test_replaced_monitor_is_migration_notice():
    """Old monitor file should be a migration notice, not the full old script."""
    old_monitor = _WORKSPACE_ROOT / "research_scripts" / "auto_launch_monitor.py"
    assert old_monitor.exists(), "Migration notice file should still exist"
    text = old_monitor.read_text("utf-8")
    # Should NOT contain old main logic keywords that indicate a runnable script
    assert "argparse" not in text, \
        "Migration notice still contains argparse (old CLI)"
    assert "build_llm_judge_prompt" not in text, \
        "Migration notice still contains old logic entry point"
    assert "已下线" in text, \
        "Migration notice missing '已下线' marker"
