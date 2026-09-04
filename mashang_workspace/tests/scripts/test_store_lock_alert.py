"""skills_store_lock_alert.py smoke test — 门店锁单停滞预警（含 Bloc 经销商聚合）。"""

import subprocess, sys, json
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
SCRIPT = _WS_DIR / "utility_scripts" / "skills_store_lock_alert.py"


def test_store_lock_alert_help():
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    assert "--as-of" in r.stdout


def test_store_lock_alert_json_smoke():
    r = subprocess.run([sys.executable, str(SCRIPT), "--as-of", "2026-09-03", "--format", "json"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    data = json.loads(r.stdout)
    assert data["summary"]["active_store_count"] > 0
    assert data["summary"]["as_of_date"] == "2026-09-03"
    assert data["summary"]["stores_never_locked"] >= 0
    # 经销商聚合存在且主体数合理
    bs = data["bloc_summary"]
    assert bs["matched_bloc_count"] > 0
    assert bs["matched_bloc_count"] <= data["summary"]["active_store_count"]
    # 各分桶有 bucket_label
    assert data["bucket_summary"][0]["bucket_key"] == "0~3d_active"
