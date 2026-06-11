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
        [sys.executable, str(_WS_DIR / "scripts" / "atp_price_report.py"),
         "--month", "2026-05", "--format", "json"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["status"] == "success"
    assert data["result"]["metrics"]["vehicle_count"] > 0
