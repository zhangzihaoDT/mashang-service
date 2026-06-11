"""
Phase 13 Step 2 — Runtime V2 Follow-up Context tests
"""

import sys, json
from pathlib import Path

_V2_ROOT = Path(__file__).resolve().parents[1]
_WS_ROOT = _V2_ROOT.parent / "mashang_workspace"
_PRJ_ROOT = _V2_ROOT.parent
for p in [str(_V2_ROOT), str(_PRJ_ROOT), str(_WS_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)


def test_session_store_save_and_load():
    from app.session_store import save, load, delete
    save("_test_v2", {"test": "data", "turn_count": 1})
    data = load("_test_v2")
    assert data["test"] == "data"
    assert data["turn_count"] == 1
    delete("_test_v2")
    data2 = load("_test_v2")
    assert data2.get("turn_count", 0) == 0


def test_session_id_sanitization():
    from app.session_store import sanitize
    assert sanitize("safe_id_123") == "safe_id_123"
    assert sanitize("demo session!@#") == "demo_session___"


def test_reset_session():
    from app.session_store import save, load, delete
    save("_test_reset", {"turn_count": 5})
    delete("_test_reset")
    data = load("_test_reset")
    assert data.get("turn_count", 0) == 0


def test_context_manager_previous_context():
    from app.context_manager import parse
    prev = {"metric": "lock_count", "time_window": "yesterday", "series": "LS8", "group_by": "city"}
    r = parse("分车型看看", previous_context=prev)
    # Should inherit metric and series
    assert r["resolved_context"].get("metric") == "lock_count"
    assert r["resolved_context"].get("series") == "LS8"
    assert r["previous_context_used"] is True


def test_dispatcher_followup_city():
    """第二轮 'LS8 的城市分布' 在有 previous_context 时 dispatch 到 lock_city_distribution。"""
    from app.capability_dispatcher import dispatch
    from app.context_manager import parse
    prev = {"metric": "lock_count", "time_window": "yesterday", "series": "LS8", "group_by": "series"}
    ctx = parse("城市分布", previous_context=prev)
    r = dispatch(ctx)
    assert r["capability_id"] == "lock_city_distribution"


def test_runtime_service_session():
    """runtime_service 支持 --session 参数。"""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(_V2_ROOT / "app" / "runtime_service.py"),
         "昨天锁单数分车型", "--session", "_test_v2_svc", "--format", "json"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["session"]["session_id"] == "_test_v2_svc"
    # Clean up
    from app.session_store import delete as del_session
    del_session("_test_v2_svc")


def test_reset_session_parameter():
    """runtime_service 支持 --reset-session。"""
    from app.session_store import save
    save("_test_reset2", {"turn_count": 10})
    import subprocess
    r = subprocess.run(
        [sys.executable, str(_V2_ROOT / "app" / "runtime_service.py"),
         "昨天锁单数分车型", "--session", "_test_reset2", "--reset-session", "--format", "json"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0
    from app.session_store import load
    data = load("_test_reset2")
    assert data.get("turn_count", 0) == 1  # Reset and first turn
    from app.session_store import delete as del_session
    del_session("_test_reset2")


def test_eval_supports_turns():
    """eval runner 支持 turns 格式的多轮 case。"""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(_V2_ROOT / "eval" / "run_runtime_v2_eval.py"),
         "--format", "json"],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    # Should include the followup case
    ids = [r2["case_id"] for r2 in data["results"]]
    assert "runtime_v2_followup_lock_model_to_city_001" in ids


def test_runtime_script_path_enforced():
    """workspace_script_adapter 不允许 runtime_scripts 外的脚本。"""
    from app.workspace_script_adapter import execute
    r = execute("test", "/etc/passwd", {})
    assert r["status"] == "error"
    assert "invalid_script_tier" in r.get("error", "")


def test_config_uses_runtime_scripts():
    """config 中 lock_by_model 指向 runtime_scripts/。"""
    cfg = json.loads((_V2_ROOT / "config" / "runtime_v2_config.json").read_text())
    for cap in ["lock_by_model", "lock_city_distribution"]:
        path = cfg.get("runtime_scripts", {}).get(cap, "")
        assert "runtime_scripts" in path, f"{cap} path not in runtime_scripts: {path}"


def test_unknown_followup_not_research():
    """未知追问不会调用 research_scripts。"""
    from app.context_manager import parse
    from app.capability_dispatcher import dispatch
    prev = {"metric": "lock_count", "time_window": "yesterday"}
    ctx = parse("释放曲线分析", previous_context=prev)
    r = dispatch(ctx)
    assert r["capability_id"] is None
