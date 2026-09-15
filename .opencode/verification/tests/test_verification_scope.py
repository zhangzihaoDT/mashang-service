"""
Verification Scope Contract — 自测。

验证契约 schema 完整性、路径分类、动态 target 生成，以及 baseline-aware 判定。
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import resolve_verification_scope as rvs  # noqa: E402


def _contract():
    return rvs.load_contract()


# ── schema ──
def test_contract_targets_referenced_by_rules_exist():
    c = _contract()
    target_ids = set(c["targets"])
    for rule in c["rules"]:
        for tid in rule.get("targets", []):
            assert tid in target_ids, f"{rule['id']} 引用不存在的 target: {tid}"


def test_baseline_entries_have_metadata():
    for b in _contract()["baseline_failures"]:
        assert "::" in b["test"], f"baseline 需为 pytest node id: {b}"
        assert b.get("reason"), f"baseline 缺 reason: {b}"


def test_all_rules_have_note():
    for rule in _contract()["rules"]:
        assert rule.get("id")
        assert rule.get("match")
        assert rule.get("note"), f"规则缺 note: {rule['id']}"


# ── path classification ──
def test_glob_star_star_matches_root_and_nested_md():
    assert rvs.match_path("AGENTS.md", "**/*.md")
    assert rvs.match_path("docs/cpca_market_research.md", "**/*.md")
    assert not rvs.match_path("mashang_workspace/x.py", "**/*.md")


def test_doc_only_is_noop():
    scope = rvs.resolve_scope(_contract(), ["docs/cpca_market_research.md"])
    assert scope["decision"] == "no-op"
    assert scope["required_targets"] == []
    assert scope["matched_rules"] == ["doc-only"]


def test_research_script_adds_scripts_and_help_smoke():
    path = "mashang_workspace/research_scripts/new_report.py"
    scope = rvs.resolve_scope(_contract(), [path])
    ids = {t["id"] for t in scope["required_targets"]}
    assert "pytest.scripts" in ids
    assert f"smoke:{path}" in ids


def test_runtime_script_adds_core_eval():
    scope = rvs.resolve_scope(
        _contract(), ["mashang_workspace/runtime_scripts/daily_lock_count.py"]
    )
    ids = {t["id"] for t in scope["required_targets"]}
    assert "eval.core" in ids
    assert "pytest.scripts" in ids


def test_capability_change_uses_nearest_tests():
    scope = rvs.resolve_scope(_contract(), ["capabilities/ocr/engine.py"])
    ids = {t["id"] for t in scope["required_targets"]}
    assert "pytest:capabilities/ocr/tests" in ids


def test_research_app_change_uses_nearest_tests():
    scope = rvs.resolve_scope(_contract(), ["research_apps/auto_launch/cli.py"])
    ids = {t["id"] for t in scope["required_targets"]}
    assert any(i.startswith("pytest:research_apps/auto_launch") for i in ids)


def test_changed_test_file_runs_itself():
    path = "mashang_workspace/tests/eval/test_context_parser.py"
    scope = rvs.resolve_scope(_contract(), [path])
    ids = {t["id"] for t in scope["required_targets"]}
    assert f"pytest:{path}" in ids


def test_non_test_eval_script_smokes_not_pytest():
    path = "mashang_workspace/eval/run_capability_audit.py"
    scope = rvs.resolve_scope(_contract(), [path])
    ids = {t["id"] for t in scope["required_targets"]}
    assert f"smoke:{path}" in ids
    assert not any(i.startswith(f"pytest:{path}") for i in ids)
    assert "pytest.eval" in ids and "eval.ci" in ids


def test_nearest_tests_does_not_leak_to_root_tests():
    assert rvs._nearest_tests("shared/loaders/thing.py") is None


def test_generated_outputs_are_noop_not_unclassified():
    scope = rvs.resolve_scope(_contract(), ["mashang_workspace/outputs/tables/x.csv"])
    assert scope["decision"] == "no-op"
    assert scope["unclassified_files"] == []


def test_generic_dataset_asset_does_not_expand_scope():
    scope = rvs.resolve_scope(
        _contract(), ["dataset/cpca/tesla_monthly_wholesale_retail_export.csv"]
    )
    assert scope["decision"] == "no-op"
    assert scope["required_targets"] == []


def test_tp_and_mix_dataset_triggers_build_contract():
    scope = rvs.resolve_scope(_contract(), ["dataset/TP&MIX-ways/registry.json"])
    ids = {t["id"] for t in scope["required_targets"]}
    assert "pytest.dataset" in ids


def test_unclassified_file_review():
    scope = rvs.resolve_scope(_contract(), [".gitignore"])
    assert scope["decision"] == "review"
    assert scope["unclassified_files"] == [".gitignore"]


# ── baseline-aware verdict ──
def test_is_baseline_suffix_match():
    node = "mashang_workspace/tests/test_root_cleanup.py::test_root_docs_not_exists"
    assert rvs._is_baseline(node, {node})
    assert not rvs._is_baseline("mashang_workspace/tests/other.py::test_new", {node})


def test_run_marks_baseline_only_failure_as_passed():
    contract = {
        "baseline_failures": [{"test": "synthetic/case.py::test_known"}],
        "targets": {},
    }
    target = {
        "id": "synthetic.baseline",
        "command": ["{python}", "-c",
                    "import sys; print('FAILED synthetic/case.py::test_known'); sys.exit(1)"],
    }
    res = rvs.run_targets(contract, [target])
    assert res["regressions"] == []
    assert res["executions"][0]["status"] == "passed_with_baseline"


def test_run_flags_non_baseline_failure_as_regression():
    contract = {"baseline_failures": [], "targets": {}}
    target = {
        "id": "synthetic.new",
        "command": ["{python}", "-c",
                    "import sys; print('FAILED synthetic/case.py::test_new'); sys.exit(1)"],
    }
    res = rvs.run_targets(contract, [target])
    assert "synthetic/case.py::test_new" in res["regressions"]
    assert res["executions"][0]["status"] == "failed"


def test_include_forces_run_even_for_doc_only():
    scope = rvs.resolve_scope(_contract(), ["docs/x.md"], include=["pytest.eval"])
    assert scope["decision"] == "run"
    ids = {t["id"] for t in scope["required_targets"]}
    assert "pytest.eval" in ids


def test_run_all_expands_and_marks_source():
    scope = rvs.resolve_scope(_contract(), [], run_all=True)
    assert scope["decision"] == "run"
    assert scope["matched_rules"] == ["ALL(expanded)"]
    assert len(scope["required_targets"]) == len(_contract()["targets"])
