"""
Tests for shared operators & schema extraction
"""

import sys, json
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[1]
_PRJ_DIR = _WS_DIR.parent


def test_shared_dir_exists():
    assert (_PRJ_DIR / "shared").exists()


def test_shared_operators_exists():
    assert (_PRJ_DIR / "shared" / "operators").exists()


def test_shared_schema_exists():
    assert (_PRJ_DIR / "shared" / "schema").exists()


def test_shared_business_definition_exists():
    assert (_PRJ_DIR / "shared" / "schema" / "business_definition.json").exists()


def test_shared_readme_exists():
    assert (_PRJ_DIR / "shared" / "README.md").exists()


def test_paths_shared_dir():
    sys.path.insert(0, str(_WS_DIR))
    from utils.paths import SHARED_DIR, SHARED_OPERATORS_DIR, SHARED_SCHEMA_DIR, BUSINESS_DEFINITION_PATH
    assert SHARED_DIR == _PRJ_DIR / "shared"
    assert SHARED_OPERATORS_DIR == _PRJ_DIR / "shared" / "operators"
    assert BUSINESS_DEFINITION_PATH == _PRJ_DIR / "shared" / "schema" / "business_definition.json"


def test_ensure_shared_import_operators():
    """ensure_shared_on_path() 后可以 import operators。"""
    from utils.paths import ensure_shared_on_path
    ensure_shared_on_path()
    import operators
    assert hasattr(operators, "atp_analysis") or hasattr(operators, "run_registered_operator")


def test_ensure_shared_can_read_business_def():
    from utils.paths import ensure_shared_on_path, BUSINESS_DEFINITION_PATH
    ensure_shared_on_path()
    bdef = json.loads(BUSINESS_DEFINITION_PATH.read_text())
    assert "time_periods" in bdef
    assert "series_group_logic" in bdef


def test_legacy_runtime_operators_still_exist():
    assert (_PRJ_DIR / "mashang_runtime" / "operators").exists()


def test_legacy_runtime_schema_still_exist():
    assert (_PRJ_DIR / "mashang_runtime" / "schema").exists()


def test_legacy_runtime_operators_readme():
    assert (_PRJ_DIR / "mashang_runtime" / "operators" / "README.md").exists()


def test_legacy_runtime_schema_readme():
    assert (_PRJ_DIR / "mashang_runtime" / "schema" / "README.md").exists()


def test_root_no_operators():
    assert not (_PRJ_DIR / "operators").exists()


def test_root_no_schema():
    assert not (_PRJ_DIR / "schema").exists()


def test_make_atp_demo_works():
    """atp_price_report.py 通过 shared operators 可运行。"""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(_WS_DIR / "runtime_scripts" / "atp_price_report.py"),
         "--month", "2026-05", "--format", "json"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["status"] == "success"
    assert data["result"]["metrics"]["vehicle_count"] > 0


def test_effective_locked_orders_registered_in_metrics():
    """metrics.json 中「有效锁单当量」的 operator 指向 effective_locked_orders。"""
    metrics = json.loads((_PRJ_DIR / "shared" / "schema" / "metrics.json").read_text())
    entries = metrics["metrics"]
    op = next((m["operator"] for m in entries.values()
               if m.get("aliases") and "ELOE" in m["aliases"]), None)
    assert op == "effective_locked_orders"


def test_effective_locked_orders_in_registry():
    """registry.json 注册了 effective_locked_orders 算子与 intent。"""
    reg = json.loads((_PRJ_DIR / "shared" / "operators" / "registry.json").read_text())
    assert "effective_locked_orders" in reg["operators"]
    assert "effective_locked_orders" in reg["intent_map"]
    assert reg["intent_map"]["effective_locked_orders"]["operator"] == "effective_locked_orders"
    assert reg["operators"]["effective_locked_orders"]["dataset"] == "order_data"


def _ensure_shared_operators():
    """确保导入的是 shared/operators 而非 mashang_runtime/operators。

    跨文件测试可能已把 mashang_runtime 的 operators 包载入 sys.modules，
    ensure_shared_on_path() 调整 sys.path 无法覆盖已导入的包，因此先清理再导入。
    """
    import sys
    for _k in [k for k in list(sys.modules) if k == "operators" or k.startswith("operators.")]:
        del sys.modules[_k]
    from utils.paths import ensure_shared_on_path
    ensure_shared_on_path()


def test_effective_locked_orders_operator_importable():
    """ensure_shared_on_path() 后可导入 effective_locked_orders 算子。"""
    _ensure_shared_operators()
    from operators.effective_locked_orders import (
        run_effective_locked_orders_operator, estimate_curve_global, score_current_pool,
    )
    assert callable(run_effective_locked_orders_operator)
    assert callable(estimate_curve_global)


def test_effective_locked_orders_synthetic():
    """合成数据确定性验证：历史订单 40 日内开票 → 条件概率=1；悬置订单 ELOE 累加。"""
    import pandas as pd
    _ensure_shared_operators()
    from operators.effective_locked_orders import run_effective_locked_orders_operator

    base = pd.Timestamp("2026-01-01")
    hist = pd.DataFrame({
        "order_number": [f"H{i}" for i in range(60)],
        "series": ["LS6"] * 60,
        "lock_time": [base + pd.Timedelta(days=i) for i in range(60)],
        "invoice_upload_time": [base + pd.Timedelta(days=i) + pd.Timedelta(days=40) for i in range(60)],
        "apply_refund_time": [pd.NaT] * 60,
        "actual_refund_time": [pd.NaT] * 60,
    })
    stalled = pd.DataFrame({
        "order_number": ["S1"],
        "series": ["LS8"],
        "lock_time": [pd.Timestamp("2026-05-01")],
        "invoice_upload_time": [pd.NaT],
        "apply_refund_time": [pd.NaT],
        "actual_refund_time": [pd.NaT],
    })
    df = pd.concat([hist, stalled], ignore_index=True)

    r = run_effective_locked_orders_operator(df, as_of="2026-06-01")
    assert "error" not in r, r
    assert r["summary"]["悬置订单数"] == 1
    assert r["summary"]["有效锁单当量ELOE"] == 1.0
    assert r["summary"]["有效率"] == 1.0
    assert r["summary"]["风险暴露量"] == 0.0
