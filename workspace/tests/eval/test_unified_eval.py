"""
Tests for unified eval runner (run_eval.py)
"""

import subprocess, sys, json
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
EVAL_RUNNER = _WS_DIR / "eval" / "run_eval.py"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(EVAL_RUNNER)] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def test_eval_help():
    r = _run(["--help"])
    assert r.returncode == 0
    assert "Unified Eval Runner" in r.stdout


def test_eval_suite_smoke():
    """--suite smoke 可以运行。"""
    r = _run(["--suite", "smoke", "--format", "json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "suites" in data
    assert "smoke" in data["suites"]


def test_eval_suite_parser():
    """--suite parser 可以运行。"""
    r = _run(["--suite", "parser", "--format", "json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "parser" in data["suites"]


def test_eval_suite_all_json():
    """--suite all --format json 可以运行（不崩溃）。"""
    r = _run(["--suite", "all", "--format", "json", "--timeout", "120"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["summary"]["total_suites"] >= 4


def test_eval_suite_reference():
    """--suite reference 可以运行。"""
    r = _run(["--suite", "reference", "--format", "json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "reference" in data["suites"]
