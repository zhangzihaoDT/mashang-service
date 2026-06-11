"""
Tests for legacy contract scripts: atp_price_report.py, lock_predict_backtest_cli.py
"""

import subprocess, sys, json
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = _WS_DIR / "runtime_scripts"
RESEARCH_DIR = _WS_DIR / "research_scripts"


def _resolve_script(script_name: str) -> Path:
    # Map script names to their tier directories
    tier_map = {
        "atp_price_report.py": RUNTIME_DIR,
        "lock_predict_backtest_cli.py": RESEARCH_DIR,
    }
    return tier_map.get(script_name, RUNTIME_DIR) / script_name


def _run_help(script_name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_resolve_script(script_name)), "--help"],
        capture_output=True, text=True, timeout=30,
    )


def _run_json(script_name: str, extra_args: list[str] = None) -> subprocess.CompletedProcess:
    args = [sys.executable, str(_resolve_script(script_name)), "--format", "json"]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def test_atp_report_help():
    r = _run_help("atp_price_report.py")
    assert r.returncode == 0
    assert "ATP" in r.stdout


def test_backtest_cli_help():
    r = _run_help("lock_predict_backtest_cli.py")
    assert r.returncode == 0
    assert "回测" in r.stdout or "Cohort" in r.stdout


def test_atp_report_json():
    r = _run_json("atp_price_report.py", ["--month", "2026-05"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["status"] in ("success", "partial_success")
    assert "scope" in data
    assert "result" in data
    assert "followup_context" in data


def test_atp_report_contract_fields():
    r = _run_json("atp_price_report.py", ["--month", "2026-05"])
    data = json.loads(r.stdout)
    for field in ("status", "script", "scope", "result", "followup_context", "warnings", "errors"):
        assert field in data, f"missing required field: {field}"
    assert "avg_atp" in data.get("result", {}).get("metrics", {})
    assert "vehicle_count" in data.get("result", {}).get("metrics", {})


def test_backtest_cli_json():
    r = _run_json("lock_predict_backtest_cli.py")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["status"] in ("success", "partial_success")


def test_backtest_cli_contract_fields():
    r = _run_json("lock_predict_backtest_cli.py")
    data = json.loads(r.stdout)
    for field in ("status", "script", "scope", "result", "followup_context", "warnings", "errors"):
        assert field in data, f"missing required field: {field}"


def test_contract_gate_includes_new():
    """run_eval.py 的 CONTRACT_SCRIPTS 包含新增脚本。"""
    import ast
    runner_path = _WS_DIR / "eval" / "run_eval.py"
    src = runner_path.read_text()
    assert "atp_price_report.py" in src
    assert "lock_predict_backtest_cli.py" in src


def test_numeric_cases_includes_new():
    """numeric_cases.json 包含新增 cases。"""
    cases_path = _WS_DIR / "eval" / "cases" / "numeric_cases.json"
    cases = json.loads(cases_path.read_text())
    ids = [c["case_id"] for c in cases]
    assert "numeric_atp_price_006" in ids
    assert "numeric_lock_predict_backtest_007" in ids
