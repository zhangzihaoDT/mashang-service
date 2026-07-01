"""
Phase 9: Volc Search Prompt Bridge tests.

Covers:
A. Prompt file existence
B. Query plan Prompt structure
C. Result-to-brief Prompt structure
D. Runbook
E. README and adapter docs
F. Anti-regression
"""

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────
_TEST_DIR = Path(__file__).resolve().parent
_WORKSPACE = _TEST_DIR.parent.parent
_PROJECT = _WORKSPACE.parent

AUTO_LAUNCH = _WORKSPACE / "promptbuilders" / "auto_launch"
PROMPTS = AUTO_LAUNCH / "prompts"
RU = AUTO_LAUNCH / "runbooks"
SA = AUTO_LAUNCH / "search_adapters"

QUERY_PLAN = PROMPTS / "volc_search_query_plan.md"
RESULT_BRIEF = PROMPTS / "volc_search_result_to_event_brief.md"
VOLC_RUNBOOK = RU / "volc_search_assisted_pilot.md"


# ── A. File existence ───────────────────────────────────────────


def test_query_plan_prompt_exists():
    assert QUERY_PLAN.exists()


def test_result_to_brief_prompt_exists():
    assert RESULT_BRIEF.exists()


def test_volc_runbook_exists():
    assert VOLC_RUNBOOK.exists()


# ── B. Query plan Prompt structure ──────────────────────────────


QP_SECTIONS = [
    "## Role", "## Scope", "## Input Variables", "## Search Strategy",
    "## Source Priority", "## Query Generation Rules",
    "## Output Format", "## Validation Rules", "## Uncertainty Rules",
]

QP_VARS = [
    "{{time_window}}", "{{battle_field}}", "{{our_model}}",
    "{{event_model}}", "{{event_brand}}", "{{event_type}}",
    "{{watchlist}}", "{{source_tiers}}",
]

QP_KEYWORDS = [
    "official", "mainstream_media", "industry_media", "social_or_forum",
    "search_tasks", "negative_queries",
]


def test_query_plan_has_required_sections():
    text = QUERY_PLAN.read_text("utf-8")
    for sec in QP_SECTIONS:
        assert sec in text, f"query plan missing section: {sec}"


def test_query_plan_has_required_vars():
    text = QUERY_PLAN.read_text("utf-8")
    for var in QP_VARS:
        # Check both {{var}} and {{ var }} forms
        bare = var.strip("{}").strip()
        assert f"{{{{{bare}}}}}" in text or f"{{{{ {bare} }}}}" in text, \
            f"query plan missing var: {var}"


def test_query_plan_has_keywords():
    text = QUERY_PLAN.read_text("utf-8")
    for kw in QP_KEYWORDS:
        assert kw in text, f"query plan missing keyword: {kw}"


# ── C. Result-to-brief Prompt structure ─────────────────────────


RB_SECTIONS = [
    "## Role", "## Scope", "## Input Variables",
    "## Evidence Rules", "## Source Tier Rules",
    "## Fact / Inference / Claim Separation",
    "## Impact Analysis Rules", "## Output Format",
    "## Validation Rules", "## Uncertainty Rules",
]

RB_VARS = [
    "{{volc_search_results}}",
    "{{time_window}}", "{{battle_field}}", "{{our_model}}",
    "{{event_model}}", "{{event_brand}}", "{{event_type}}",
    "{{source_tiers}}",
]

RB_KEYWORDS = [
    "source_items", "confirmed_facts", "inferences", "unconfirmed_claims",
    "missing_evidence", "confidence_level", "followup_recommendation",
]


def test_result_brief_has_required_sections():
    text = RESULT_BRIEF.read_text("utf-8")
    for sec in RB_SECTIONS:
        assert sec in text, f"result brief missing section: {sec}"


def test_result_brief_has_required_vars():
    text = RESULT_BRIEF.read_text("utf-8")
    for var in RB_VARS:
        bare = var.strip("{}").strip()
        assert f"{{{{{bare}}}}}" in text or f"{{{{ {bare} }}}}" in text, \
            f"result brief missing var: {var}"


def test_result_brief_has_keywords():
    text = RESULT_BRIEF.read_text("utf-8")
    for kw in RB_KEYWORDS:
        assert kw in text, f"result brief missing keyword: {kw}"


def test_result_brief_has_source_name_field():
    """Result-to-brief source_items must include source_name field."""
    text = RESULT_BRIEF.read_text("utf-8")
    assert '"source_name"' in text, "missing source_name field in source_items output schema"


def test_result_brief_has_raw_url_constraint():
    """Result-to-brief must require pure URL, no Markdown link format."""
    text = RESULT_BRIEF.read_text("utf-8")
    assert "纯 URL" in text or "纯URL" in text
    assert "Markdown" in text
    assert "source_name" in text or "source_tier" in text


# ── D. Runbook ──────────────────────────────────────────────────


def test_volc_runbook_contains_query_plan_ref():
    text = VOLC_RUNBOOK.read_text("utf-8")
    assert "volc_search_query_plan" in text


def test_volc_runbook_contains_result_brief_ref():
    text = VOLC_RUNBOOK.read_text("utf-8")
    assert "volc_search_result_to_event_brief" in text


def test_volc_runbook_contains_intake():
    text = VOLC_RUNBOOK.read_text("utf-8")
    assert "auto-launch-intake" in text


def test_volc_runbook_contains_index():
    text = VOLC_RUNBOOK.read_text("utf-8")
    assert "auto-launch-index" in text


def test_volc_runbook_states_boundaries():
    text = VOLC_RUNBOOK.read_text("utf-8")
    assert "不实现" in text or "不负责" in text
    assert "API" in text
    assert "golden case" not in text or "不创建" in text


# ── E. README and adapter docs ──────────────────────────────────


def test_readme_mentions_volc_assisted_path():
    readme = (AUTO_LAUNCH / "README.md").read_text("utf-8")
    assert "Volc-assisted" in readme or "volc_search" in readme.lower()


def test_volc_search_md_mentions_prompt_bridge():
    text = (SA / "volc_search.md").read_text("utf-8")
    assert "Prompt Bridge" in text
    assert "volc_search_query_plan" in text


def test_search_adapters_readme_mentions_prompts():
    text = (SA / "README.md").read_text("utf-8")
    assert "volc_search_query_plan" in text
    assert "volc_search_result_to_event_brief" in text


def test_runbooks_readme_mentions_volc_assisted():
    text = (RU / "README.md").read_text("utf-8")
    assert "volc_search_assisted_pilot" in text


# ── F. Anti-regression ──────────────────────────────────────────


def test_no_legacy_monitor_target():
    makefile = _PROJECT / "Makefile"
    text = makefile.read_text("utf-8")
    assert "auto-launch-monitor:" not in text


def test_no_new_runner_script():
    """No volc_search_runner.py should exist."""
    runners = list(AUTO_LAUNCH.rglob("*runner*.py"))
    assert len(runners) == 0, f"runner scripts found: {runners}"


def test_outputs_not_polluted():
    """No new files written to outputs/auto_launch by this phase."""
    out_root = _PROJECT / "mashang_workspace" / "outputs" / "auto_launch"
    if out_root.exists():
        for bad in ["ai_response_examples", "prompts", "normalized", "reports"]:
            assert not (out_root / bad).exists(), f"outputs still contains {bad}"
