"""当前业务状态排查 runtime 脚本 smoke test。"""

import subprocess, sys, json
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
SCRIPT = _WS_DIR / "runtime_scripts" / "current_state_diagnosis.py"


def test_current_state_diagnosis_help():
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    assert "--as-of" in r.stdout


def test_current_state_diagnosis_json_contract():
    r = subprocess.run([sys.executable, str(SCRIPT), "--format", "json"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    data = json.loads(r.stdout)
    assert data["status"] == "success"
    assert data["result"]["rows"]
    assert data["scope"]["time_window"]["as_of"]
    total_pending = data["result"]["backlog"]["pending_total"]
    at_risk = data["result"]["backlog"]["at_risk_total"]
    assert total_pending > 0
    assert 0 <= at_risk <= total_pending
    # 库存为正
    assert data["result"]["inventory"]["total"] > 0


def test_current_state_diagnosis_historical_as_of():
    """历史时点：point-in-time 重建应成功，且当年口径与 backlog 报告一致。"""
    r = subprocess.run([sys.executable, str(SCRIPT), "--as-of", "2025-04-17", "--format", "json"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    data = json.loads(r.stdout)
    assert data["status"] == "success"
    assert data["result"]["as_of"] == "2025-04-17"
    ytd = data["result"]["backlog"]["ytd"]
    assert ytd["start"] == "2025-01-01"
    assert ytd["pending"] > 0
    assert 0 <= ytd["at_risk"] <= ytd["pending"]
    # 与 compute_history（当年累计, Age-only）同口径交叉校验
    import pandas as pd
    from mashang_workspace.utils.data_loader import load_order_data
    from mashang_workspace.research_scripts.backlog_rate_trend_report import compute_history
    rdf = compute_history(pd.Timestamp("2025-04-17"), frequency="monthly",
                          df=load_order_data())
    row = rdf[rdf["as_of"] == "2025-04-17"].iloc[0]
    assert ytd["pending"] == int(row["n_orders"])
    assert abs(ytd["at_risk"] - row["at_risk"]) < 1.0
