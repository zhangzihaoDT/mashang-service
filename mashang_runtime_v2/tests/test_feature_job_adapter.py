#!/usr/bin/env python
"""Runtime V2 — Feature Job Adapter hermetic tests.

覆盖（不执行真实 Research Application，不依赖 dataset/网络）：
  - success / failure / summary-json
  - unknown job
  - 参数白名单校验（date 格式、pattern、未声明参数）
  - argv 注入为单个参数（无 shell）
  - artifact 探测
  - CLI --job 快速失败路径
"""

import json
import sys
from pathlib import Path

import pytest

_V2_ROOT = Path(__file__).resolve().parents[1]
_PRJ_ROOT = _V2_ROOT.parent


def _py_job(code: str, summary: str | None = None, params: dict | None = None,
            artifacts: list[str] | None = None, cwd: str = "{repo_root}") -> dict:
    argv = ["{python}", "-c", code]
    return {
        "module": "fixture",
        "label": "fixture job",
        "cwd": cwd,
        "argv_template": argv,
        "params": params or {},
        "summary": summary or "text",
        "artifacts": artifacts or [],
        "timeout_seconds": 30,
    }


class TestJobExec:
    def test_success(self):
        from app.feature_job_adapter import run_job
        jobs = {"demo": _py_job("print('HELLO_JOB')")}
        r = run_job("demo", jobs_override=jobs)
        assert r["status"] == "ok"
        assert r["returncode"] == 0
        assert "HELLO_JOB" in r["output"]

    def test_failure(self):
        from app.feature_job_adapter import run_job
        jobs = {"demo": _py_job("import sys; sys.exit(3)")}
        r = run_job("demo", jobs_override=jobs)
        assert r["status"] == "failed"
        assert r["returncode"] == 3
        assert r["error"]

    def test_summary_json(self):
        from app.feature_job_adapter import run_job
        jobs = {"demo": _py_job("import json; print(json.dumps({'status': 'PASS', 'slides': 10}))", summary="json")}
        r = run_job("demo", jobs_override=jobs)
        assert r["status"] == "ok"
        assert r["summary_json"]["status"] == "PASS"
        assert r["summary_json"]["slides"] == 10

    def test_unknown_job(self):
        from app.feature_job_adapter import run_job
        r = run_job("does_not_exist", jobs_override={"demo": _py_job("print('x')")})
        assert r["status"] == "error"
        assert "unknown feature_job" in r["error"]


class TestParamValidation:
    def test_bad_date_rejected_without_run(self, monkeypatch):
        from app.feature_job_adapter import run_job
        called = {"n": 0}

        def _fail(*a, **k):
            called["n"] += 1
            raise AssertionError("subprocess 不应被调用")

        monkeypatch.setattr("subprocess.run", _fail)
        jobs = {"demo": _py_job("print('x')", params={"date": {"type": "date", "required": True}})}
        r = run_job("demo", {"date": "01-01-2026"}, jobs_override=jobs)
        assert r["status"] == "error"
        assert "YYYY-MM-DD" in r["error"]
        assert called["n"] == 0

    def test_pattern_rejected(self, monkeypatch):
        from app.feature_job_adapter import run_job
        called = {"n": 0}

        def _fail(*a, **k):
            called["n"] += 1
            raise AssertionError("subprocess 不应被调用")

        monkeypatch.setattr("subprocess.run", _fail)
        jobs = {"demo": _py_job("print('x')", params={"topic": {"type": "pattern", "required": True, "pattern": "^[a-z_]+$"}})}
        r = run_job("demo", {"topic": "Bad Topic!"}, jobs_override=jobs)
        assert r["status"] == "error"
        assert called["n"] == 0

    def test_undeclared_param_rejected(self, monkeypatch):
        from app.feature_job_adapter import run_job
        monkeypatch.setattr("subprocess.run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("not called")))
        jobs = {"demo": _py_job("print('x')", params={"topic": {"type": "pattern", "required": True, "pattern": "^[a-z_]+$"}})}
        r = run_job("demo", {"topic": "ok", "evil": "rm -rf /"}, jobs_override=jobs)
        assert r["status"] == "error"
        assert "未声明的 job 参数" in r["error"]

    def test_param_stays_single_argv_element(self):
        from app.feature_job_adapter import run_job
        code = "import sys; print(repr(sys.argv[1:]))"
        jobs = {"demo": _py_job(code, params={"name": {"type": "pattern", "required": True, "pattern": "^[a-z ]+$"}})}
        jobs["demo"]["argv_template"] = ["{python}", "-c", code, "{name}"]
        r = run_job("demo", {"name": "hello world"}, jobs_override=jobs)
        assert r["status"] == "ok"
        assert r["output"].strip() == "['hello world']"


class TestArtifacts:
    def test_artifact_detection(self, tmp_path):
        from app.feature_job_adapter import run_job
        (tmp_path / "out.txt").write_text("result", encoding="utf-8")
        jobs = {"demo": _py_job("print('x')", artifacts=["out.txt"], cwd=str(tmp_path))}
        r = run_job("demo", jobs_override=jobs)
        assert r["artifacts"][0]["exists"] is True
        assert r["artifacts"][0]["size"] == 6

    def test_missing_artifact(self, tmp_path):
        from app.feature_job_adapter import run_job
        jobs = {"demo": _py_job("print('x')", artifacts=["nope.txt"], cwd=str(tmp_path))}
        r = run_job("demo", jobs_override=jobs)
        assert r["artifacts"][0]["exists"] is False


class TestCli:
    def test_job_unknown_fails_fast(self):
        import subprocess
        r = subprocess.run(
            [sys.executable, str(_V2_ROOT / "app" / "runtime_service.py"), "--job", "does_not_exist"],
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 1
        assert "unknown feature_job" in r.stdout + r.stderr

    def test_help_mentions_job(self):
        import subprocess
        r = subprocess.run(
            [sys.executable, str(_V2_ROOT / "app" / "runtime_service.py"), "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0
        assert "--job" in r.stdout
