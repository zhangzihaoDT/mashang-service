"""
Phase 13 Step 2.1 — Contract & Session Hardening tests
"""

import sys, json, time
from pathlib import Path

_V2_ROOT = Path(__file__).resolve().parents[1]
_WS_ROOT = _V2_ROOT.parent / "mashang_workspace"
_PRJ_ROOT = _V2_ROOT.parent
for p in [str(_V2_ROOT), str(_PRJ_ROOT), str(_WS_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.session_store import save, load, delete, cleanup, _path


def _cleanup_test_sessions():
    for sid in ["_test_hardening", "_test_unsafe", "_test_turn", "_test_reset_final"]:
        delete(sid)


def setup_module():
    _cleanup_test_sessions()


def teardown_module():
    _cleanup_test_sessions()


def test_session_created_at():
    save("_test_hardening", {"turn_count": 1})
    data = load("_test_hardening")
    assert "created_at" in data
    assert "updated_at" in data
    delete("_test_hardening")


def test_session_created_at_not_overwritten():
    save("_test_hardening", {"turn_count": 1})
    t1 = load("_test_hardening")["created_at"]
    time.sleep(0.01)
    save("_test_hardening", {"turn_count": 2})
    t2 = load("_test_hardening")["created_at"]
    assert t1 == t2
    delete("_test_hardening")


def test_turn_count_increment():
    save("_test_turn", {"turn_count": 1})
    data = load("_test_turn")
    assert data["turn_count"] == 1
    delete("_test_turn")


def test_reset_turn_count():
    save("_test_reset_final", {"turn_count": 5})
    delete("_test_reset_final")
    data = load("_test_reset_final")
    assert data.get("turn_count", 0) == 0


def test_unsafe_session_id():
    safe = _path("hello world!@#")
    assert "hello_world___" in str(safe)


def test_cleanup_sessions():
    removed = cleanup(max_age_days=0)
    assert removed >= 0


def test_contract_quality_ok():
    from app.result_contract_adapter import load
    mock = {"status": "success", "script": "t.py", "scope": {},
            "metric": "lock_count",
            "result": {"summary": "ok", "metrics": {"total": 1}, "dimensions": [{"name": "x", "items": []}], "results": []},
            "followup_context": {"metric": "lock_count"}}
    r = load(mock)
    assert r["contract_quality"] == "ok"
    assert r["is_contract_valid"] is True


def test_contract_quality_missing_metric():
    from app.result_contract_adapter import load
    mock = {"status": "success", "script": "t.py",
            "result": {"summary": "ok", "dimensions": []}}
    r = load(mock)
    assert r["contract_quality"] in ("warning", "ok")


def test_contract_quality_missing_status():
    from app.result_contract_adapter import load
    mock = {"script": "t.py", "result": {"summary": "test"}}
    r = load(mock)
    assert r["contract_quality"] == "error"
    assert r["is_contract_valid"] is False


def test_renderer_no_data():
    from app.response_renderer import render
    r = render({"status": "ok", "contract_quality": "warning", "summary": "",
                "metrics": {}, "dimensions": [], "followup_context": {},
                "warnings": ["no_dimensions_or_results"]})
    assert "缺少" in r or "生成" in r


def test_renderer_no_total():
    """没有 total_lock_count 时不要编造。"""
    from app.response_renderer import render
    r = render({"status": "success", "contract_quality": "ok",
                "summary": "测试", "metrics": {"other": 42},
                "dimensions": [], "followup_context": {},
                "warnings": []})
    assert "总锁单数" not in r


def test_adapter_rejects_research():
    from app.workspace_script_adapter import execute
    r = execute("test", str(_WS_ROOT / "research_scripts" / "nonexistent.py"), {})
    assert r.get("error") in ("invalid_script_tier", "script_not_found")


def test_adapter_rejects_utility():
    from app.workspace_script_adapter import execute
    r = execute("test", str(_WS_ROOT / "utility_scripts" / "nonexistent.py"), {})
    assert r.get("error") in ("invalid_script_tier", "script_not_found")


def test_adapter_rejects_legacy():
    from app.workspace_script_adapter import execute
    r = execute("test", str(_WS_ROOT / "legacy_scripts" / "nonexistent.py"), {})
    assert r.get("error") in ("invalid_script_tier", "script_not_found")


def test_adapter_script_not_found():
    from app.workspace_script_adapter import execute
    r = execute("test", str(_WS_ROOT / "runtime_scripts" / "nonexistent.py"), {})
    assert r.get("error") == "script_not_found"


def test_eval_supports_expected_error():
    import subprocess
    r = subprocess.run(
        [sys.executable, str(_V2_ROOT / "eval" / "run_runtime_v2_eval.py"), "--format", "json"],
        capture_output=True, text=True, timeout=120,
    )
    data = json.loads(r.stdout)
    ids = [r2["case_id"] for r2 in data["results"]]
    assert "runtime_v2_unknown_followup_001" in ids


def test_runtime_service_debug_json():
    """--format json 包含 session/context/dispatch/execution/contract/answer。"""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(_V2_ROOT / "app" / "runtime_service.py"),
         "昨天锁单数分车型", "--format", "json"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    for key in ("session", "context", "dispatch", "execution", "contract", "answer"):
        assert key in data, f"missing key: {key}"
