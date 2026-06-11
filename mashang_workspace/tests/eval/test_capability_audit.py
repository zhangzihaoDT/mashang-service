"""
Tests for capability registry and audit runner
"""

import subprocess, sys, json
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
REGISTRY_FILE = _WS_DIR / "registry" / "capability_registry.json"
AUDIT_RUNNER = _WS_DIR / "eval" / "run_capability_audit.py"

VALID_TIERS = {"runtime", "research", "utility", "legacy"}
VALID_STATUSES = {"active", "partial", "experimental", "deprecated"}


def _run_audit(args: list[str] = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(AUDIT_RUNNER)]
    if args:
        cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def test_registry_exists():
    assert REGISTRY_FILE.exists()


def test_registry_valid_json():
    data = json.loads(REGISTRY_FILE.read_text())
    assert isinstance(data, list)
    assert len(data) >= 8


def test_all_ids_unique():
    data = json.loads(REGISTRY_FILE.read_text())
    ids = [c["capability_id"] for c in data]
    assert len(ids) == len(set(ids))


def test_all_tiers_valid():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        assert c["tier"] in VALID_TIERS, f"{c['capability_id']}: invalid tier {c['tier']}"


def test_all_statuses_valid():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        assert c["status"] in VALID_STATUSES, f"{c['capability_id']}: invalid status {c['status']}"


def test_all_scripts_exist():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        script = c.get("script", "")
        if script:
            full = _WS_DIR / script.replace("mashang_workspace/", "")
            assert full.exists(), f"{c['capability_id']}: script not found {full}"


def test_runtime_has_contract():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        if c["tier"] == "runtime":
            assert c["result_contract"] is True, f"{c['capability_id']}: runtime missing result_contract"


def test_runtime_has_numeric():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        if c["tier"] == "runtime":
            assert c.get("numeric_eval_case"), f"{c['capability_id']}: runtime missing numeric_eval_case"


def test_runtime_has_gate():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        if c["tier"] == "runtime":
            assert c["contract_gate"] is True, f"{c['capability_id']}: runtime missing contract_gate"


def test_research_not_auto():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        if c["tier"] == "research":
            assert c["auto_schedulable"] is False, f"{c['capability_id']}: research should not be auto_schedulable"


def test_legacy_not_auto():
    data = json.loads(REGISTRY_FILE.read_text())
    for c in data:
        if c["tier"] == "legacy":
            assert c["auto_schedulable"] is False, f"{c['capability_id']}: legacy should not be auto_schedulable"


def test_audit_help():
    r = _run_audit(["--help"])
    assert r.returncode == 0
    assert "Capability Audit" in r.stdout


def test_audit_json_output():
    r = _run_audit(["--format", "json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "meta" in data
    assert "results" in data
    assert data["meta"]["total"] >= 8


def test_audit_all_passed():
    r = _run_audit(["--format", "json"])
    data = json.loads(r.stdout)
    assert data["meta"]["failed"] == 0, f"{data['meta']['failed']} capabilities failed audit"


def test_eval_suite_capability():
    """run_eval.py --suite capability 正常运行。"""
    runner = _WS_DIR / "eval" / "run_eval.py"
    r = subprocess.run(
        [sys.executable, str(runner), "--suite", "capability", "--format", "json"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "capability" in data["suites"]
