"""
Phase 13 Step 1 — Runtime V2 Self-contained Entry tests
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


def test_config_enabled_capabilities():
    cfg = json.loads((_V2_ROOT / "config" / "runtime_v2_config.json").read_text())
    caps = cfg.get("enabled_capabilities", [])
    assert "lock_by_model" in caps
    assert "lock_city_distribution" in caps
    assert len(caps) == 2


def test_dispatcher_lock_by_model():
    from app.capability_dispatcher import dispatch
    ctx = {"raw_text": "锁单分车型", "resolved_context": {"metric": "lock_count", "group_by": "model"}}
    r = dispatch(ctx)
    assert r["capability_id"] == "lock_by_model"


def test_dispatcher_lock_city():
    from app.capability_dispatcher import dispatch
    ctx = {"raw_text": "LS8 城市分布", "resolved_context": {"metric": "lock_count", "group_by": "city", "series": "LS8"}}
    r = dispatch(ctx)
    assert r["capability_id"] == "lock_city_distribution"


def test_dispatcher_unknown():
    from app.capability_dispatcher import dispatch
    ctx = {"resolved_context": {"metric": "unknown"}}
    r = dispatch(ctx)
    assert r["capability_id"] is None


def test_adapter_build_lock_by_model_args():
    from app.workspace_script_adapter import build_args
    ctx = {"resolved_context": {"time_window": "yesterday", "date": "2026-06-10"}}
    args = build_args("lock_by_model", ctx)
    assert "--format" in args
    assert "--date" in args


def test_adapter_build_lock_city_args():
    from app.workspace_script_adapter import build_args
    ctx = {"resolved_context": {"time_window": "yesterday", "series": "LS8", "date": "2026-06-10"}}
    args = build_args("lock_city_distribution", ctx)
    assert "--format" in args
    assert "--series" in args


def test_contract_adapter_mock():
    from app.result_contract_adapter import load
    mock = {"status": "success", "script": "t.py", "scope": {},
            "result": {"summary": "test", "metrics": {"total": 100}},
            "followup_context": {"metric": "lock_count"}}
    r = load(mock)
    assert r["status"] == "success"
    assert r["summary"] == "test"


def test_renderer_lock_by_model():
    from app.response_renderer import render
    data = {"status": "success", "summary": "锁单分析", "metrics": {"total": 100},
            "dimensions": [{"name": "series", "items": [{"value": "LS8", "metrics": {"count": 60}}]}],
            "followup_context": {"top_entities": [{"field": "series", "value": "LS8"}]}}
    r = render(data)
    assert "锁单分析" in r
    assert "100" in r
    assert "LS8" in r


def test_renderer_lock_city():
    from app.response_renderer import render
    data = {"status": "success", "summary": "城市分布", "metrics": {"total": 75},
            "dimensions": [{"name": "license_city", "items": [{"value": "成都", "metrics": {"count": 15}}]}],
            "followup_context": {"top_entities": []}}
    r = render(data)
    assert "城市分布" in r
    assert "75" in r


def test_runtime_service_help():
    import subprocess
    r = subprocess.run(
        [sys.executable, str(_V2_ROOT / "app" / "runtime_service.py"), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0


def test_eval_runner_help():
    import subprocess
    r = subprocess.run(
        [sys.executable, str(_V2_ROOT / "eval" / "run_runtime_v2_eval.py"), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0


def test_runtime_service_pipeline():
    """完整 pipeline 可运行（验证链路通，不验证具体数值）。"""
    from app.runtime_service import run_pipeline
    result = run_pipeline("昨天锁单数分车型")
    assert result["dispatch"]["capability_id"] == "lock_by_model"
    assert isinstance(result["answer"], str)
    assert len(result["answer"]) > 0
