"""
Runtime V2 — Minimal Implementation Tests
"""

import sys, json
from pathlib import Path

_V2_ROOT = Path(__file__).resolve().parents[1]
_WS_ROOT = _V2_ROOT.parent / "mashang_workspace"
_PRJ_ROOT = _V2_ROOT.parent
for p in [str(_V2_ROOT), str(_PRJ_ROOT), str(_WS_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)


def test_config_exists():
    assert (_V2_ROOT / "config" / "runtime_v2_config.json").exists()


def test_capability_dispatcher_import():
    from app.capability_dispatcher import dispatch, _load_registry
    reg = _load_registry()
    assert len(reg) >= 8


def test_dispatch_lock_by_model():
    from app.capability_dispatcher import dispatch
    ctx = {"raw_text": "锁单分车型", "resolved_context": {"metric": "lock_count", "group_by": "model", "time_window": "yesterday"}}
    r = dispatch(ctx)
    assert r["capability_id"] == "lock_by_model"


def test_dispatch_lock_city():
    from app.capability_dispatcher import dispatch
    ctx = {"raw_text": "LS8 城市分布", "resolved_context": {"metric": "lock_count", "group_by": "city", "time_window": "yesterday", "series": "LS8"}}
    r = dispatch(ctx)
    assert r["capability_id"] == "lock_city_distribution"


def test_dispatch_unknown():
    from app.capability_dispatcher import dispatch
    ctx = {"resolved_context": {"metric": "unknown_metric"}}
    r = dispatch(ctx)
    assert r["capability_id"] is None


def test_workspace_script_adapter_build_args():
    from app.workspace_script_adapter import build_args
    ctx = {"resolved_context": {"time_window": "yesterday", "series": "LS8", "date": "2026-06-10"}}
    args = build_args("lock_city_distribution", ctx)
    assert "--format" in args
    assert "--date" in args


def test_result_contract_adapter_mock():
    from app.result_contract_adapter import load
    mock = {"status": "success", "script": "test.py",
            "scope": {}, "result": {"summary": "test", "metrics": {"count": 5}},
            "followup_context": {"metric": "lock_count"}}
    r = load(mock)
    assert r["status"] == "success"
    assert r["metrics"]["count"] == 5


def test_response_renderer_no_data():
    from app.response_renderer import render
    result = render({"status": "error", "error": "test error"})
    assert "出错" in result


def test_response_renderer_contract():
    from app.response_renderer import render
    data = {"status": "success", "summary": "锁单分析", "metrics": {"total": 100},
            "dimensions": [{"name": "series", "items": [{"value": "LS8", "metrics": {"count": 60}}]}],
            "followup_context": {}}
    result = render(data)
    assert "锁单分析" in result
    assert "100" in result
    assert "LS8" in result


def test_eval_cases_exist():
    assert (_V2_ROOT / "eval" / "runtime_v2_cases.json").exists()


def test_eval_runner_help():
    import subprocess
    r = subprocess.run(
        [sys.executable, str(_V2_ROOT / "eval" / "run_runtime_v2_eval.py"), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0


def test_pipeline_dry_run():
    """runtime_service JSON pipeline 可运行（不真实执行脚本，仅验证链路）。"""
    from app.runtime_service import run_pipeline
    # Use a query that should dispatch but fail at execution due to no --date default handling
    result = run_pipeline("昨天锁单数分车型")
    # At minimum, context and dispatch should work
    assert "context" in result
    assert "dispatch" in result


def test_context_manager_import():
    from app.context_manager import parse
    r = parse("昨天锁单数分车型")
    assert r["resolved_context"].get("metric") == "lock_count"
    assert r["resolved_context"].get("time_window") == "yesterday"
