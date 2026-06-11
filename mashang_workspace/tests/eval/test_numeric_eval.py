"""
Tests for eval/run_numeric_eval.py
"""

import subprocess, sys, json
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
NUMERIC_RUNNER = _WS_DIR / "eval" / "run_numeric_eval.py"
NUMERIC_CASES = _WS_DIR / "eval" / "cases" / "numeric_cases.json"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(NUMERIC_RUNNER)] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def test_numeric_help():
    r = _run(["--help"])
    assert r.returncode == 0
    assert "Numeric Eval Runner" in r.stdout


def test_numeric_terminal():
    r = _run(["--cases", str(NUMERIC_CASES)])
    assert r.returncode == 0
    assert "Numeric Eval Runner" in r.stdout
    assert "Total:" in r.stdout or "total" in r.stdout


def test_numeric_json():
    r = _run(["--cases", str(NUMERIC_CASES), "--format", "json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "meta" in data
    assert "results" in data
    assert data["meta"]["total"] >= 3


def test_numeric_first_case():
    """至少第一个 case (lock_by_model) 可以执行。"""
    r = _run(["--cases", str(NUMERIC_CASES), "--format", "json", "--timeout", "120"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    first = data["results"][0]
    assert first["case_id"] == "numeric_lock_by_model_001"
    # At minimum, should run without crashing
    assert "checks" in first
    assert len(first["checks"]) > 0


def test_numeric_executes_all():
    """所有 numeric cases 均可执行。"""
    r = _run(["--cases", str(NUMERIC_CASES), "--format", "json", "--timeout", "120"])
    data = json.loads(r.stdout)
    assert data["meta"]["total"] == data["meta"]["passed"] + data["meta"]["failed"]
