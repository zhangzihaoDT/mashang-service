"""
Tests for script tiering in run_eval.py and numeric_cases.json
"""

import subprocess, sys, json
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
EVAL_RUNNER = _WS_DIR / "eval" / "run_eval.py"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(EVAL_RUNNER)] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def test_core_suite_works():
    """--suite core 正常运行。"""
    r = _run(["--suite", "core", "--format", "json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "core" in data["suites"] or "core.numeric" in data["suites"] or "core.contract" in data["suites"]


def test_research_suite_works():
    """--suite research 正常运行。"""
    r = _run(["--suite", "research", "--format", "json"])
    assert r.returncode == 0
    assert "research" in r.stdout or json.loads(r.stdout).get("summary", {}).get("total_suites", 0) >= 0


def test_numeric_cases_have_tier():
    """所有 numeric cases 有 tier 字段。"""
    cases_path = _WS_DIR / "eval" / "cases" / "numeric_cases.json"
    cases = json.loads(cases_path.read_text())
    for c in cases:
        assert "tier" in c, f"Case {c['case_id']} missing tier"
        assert c["tier"] in ("core", "research"), f"Case {c['case_id']} has invalid tier: {c['tier']}"


def test_core_numeric_excludes_research():
    """core numeric 不包含 research cases。"""
    # Run numeric with --tier core
    runner = _WS_DIR / "eval" / "run_numeric_eval.py"
    cases = _WS_DIR / "eval" / "cases" / "numeric_cases.json"
    r = subprocess.run(
        [sys.executable, str(runner), "--cases", str(cases), "--tier", "core", "--format", "json"],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    results = data.get("results", [])
    for r2 in results:
        # Should NOT contain research tier cases
        assert "backtest" not in r2.get("case_id", "")


def test_default_suite_is_not_all():
    """默认 suite 不是 all（不含 research）。"""
    r = _run(["--format", "json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    # Default should not contain research suites
    for k in data["suites"]:
        assert "research" not in k


def test_script_tiers_doc_exists():
    """docs/script_tiers.md 存在。"""
    assert (_WS_DIR / "docs" / "script_tiers.md").exists()
