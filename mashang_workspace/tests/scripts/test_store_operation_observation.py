"""store_operation_observation.py smoke test — 门店经营状况观察（全门店）。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

_PRJ = Path(__file__).resolve().parents[3]
_WS_DIR = _PRJ / "mashang_workspace"
SCRIPT = _WS_DIR / "utility_scripts" / "store_operation_observation.py"

COLUMNS = ["门店", "门店类型", "近7日下发线索", "CM3小订", "小订/线索"]
LEADS_CSV = _PRJ / "dataset" / "门店下发线索数.csv"
ORDER_PARQUET = _PRJ / "dataset" / "order_data.parquet"


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=180)


def test_help():
    r = _run("--help")
    assert r.returncode == 0
    assert "--window-days" in r.stdout and "--format" in r.stdout


@pytest.mark.skipif(not (LEADS_CSV.exists() and ORDER_PARQUET.exists()),
                    reason="线索库 / order_data 不存在")
def test_json_smoke():
    r = _run("--format", "json", "--as-of", "2026-09-16")
    assert r.returncode == 0, r.stderr[-2000:]
    data = json.loads(r.stdout)
    assert data["status"] == "success"
    table = data["result"]["tables"][0]
    assert table["columns"] == COLUMNS
    assert len(table["rows"]) > 100
    assert all(set(row) == set(COLUMNS) for row in table["rows"][:5])


@pytest.mark.skipif(not (LEADS_CSV.exists() and ORDER_PARQUET.exists()),
                    reason="线索库 / order_data 不存在")
def test_csv_output(tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPT), "--format", "csv",
                        "--output", str(tmp_path), "--as-of", "2026-09-16"],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    out = tmp_path / "store_operation_observation.csv"
    assert out.exists()
    header = out.read_text(encoding="utf-8-sig").splitlines()[0]
    assert header == ",".join(COLUMNS)
