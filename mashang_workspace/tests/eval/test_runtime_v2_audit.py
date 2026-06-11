"""
Tests for Runtime V2 Readiness Audit
"""

import subprocess, sys, json
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
REGISTRY_FILE = _WS_DIR / "registry" / "capability_registry.json"
AUDIT_RUNNER = _WS_DIR / "eval" / "run_runtime_v2_audit.py"


def _run(args: list[str] = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(AUDIT_RUNNER)]
    if args:
        cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def test_audit_help():
    r = _run(["--help"])
    assert r.returncode == 0
    assert "Runtime V2" in r.stdout


def test_audit_json_output():
    r = _run(["--format", "json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "meta" in data
    assert "results" in data


def test_all_candidates_are_runtime():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        if c.get("promotion", {}).get("runtime_v2_candidate"):
            assert c["tier"] == "runtime", f"{c['capability_id']} is candidate but tier={c['tier']}"


def test_all_candidates_autoschedulable():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        if c.get("promotion", {}).get("runtime_v2_candidate"):
            assert c["auto_schedulable"] is True, f"{c['capability_id']} candidate but not auto_schedulable"


def test_all_candidates_have_contract():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        if c.get("promotion", {}).get("runtime_v2_candidate"):
            assert c["result_contract"] is True, f"{c['capability_id']} candidate but no result_contract"


def test_research_not_candidate():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        if c["tier"] == "research":
            assert c.get("promotion", {}).get("runtime_v2_candidate") is False, \
                f"{c['capability_id']} is research but marked as v2 candidate"


def test_utility_not_candidate():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        if c["tier"] == "utility":
            assert c.get("promotion", {}).get("runtime_v2_candidate") is False, \
                f"{c['capability_id']} is utility but marked as v2 candidate"


def test_legacy_not_candidate():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        if c["tier"] == "legacy":
            assert c.get("promotion", {}).get("runtime_v2_candidate") is False, \
                f"{c['capability_id']} is legacy but marked as v2 candidate"


def test_lock_by_model_is_candidate():
    data = json.loads(REGISTRY_FILE.read_text())
    entry = next(c for c in data if c["capability_id"] == "lock_by_model")
    assert entry.get("promotion", {}).get("runtime_v2_candidate") is True


def test_cohort_forecast_not_candidate():
    data = json.loads(REGISTRY_FILE.read_text())
    entry = next(c for c in data if c["capability_id"] == "cohort_forecast")
    assert entry.get("promotion", {}).get("runtime_v2_candidate") is False


def test_eval_suite_runtime_v2():
    """run_eval.py --suite runtime-v2 正常运行。"""
    runner = _WS_DIR / "eval" / "run_eval.py"
    r = subprocess.run(
        [sys.executable, str(runner), "--suite", "runtime-v2", "--format", "json"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "runtime-v2" in data["suites"]
