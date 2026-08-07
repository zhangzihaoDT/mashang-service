"""
Phase 13 Step 2.2 — Workspace Script Tier Physicalization & DataOps Placement

验证脚本物理分层完成、路径正确、Runtime V2 不被破坏。
"""

import sys, json
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_WS_DIR))

from utils.paths import (
    WORKSPACE_ROOT, RUNTIME_SCRIPTS_DIR, RESEARCH_SCRIPTS_DIR,
    UTILITY_SCRIPTS_DIR, REPORTS_DIR,
)
from utils.paths import PROJECT_ROOT

REGISTRY_PATH = WORKSPACE_ROOT / "registry" / "capability_registry.json"
V2_CONFIG_PATH = PROJECT_ROOT / "mashang_runtime_v2" / "config" / "runtime_v2_config.json"


def test_runtime_scripts_is_real_dir():
    """runtime_scripts 是真实目录，不是 symlink。"""
    assert RUNTIME_SCRIPTS_DIR.exists()
    assert not RUNTIME_SCRIPTS_DIR.is_symlink(), "runtime_scripts 不应是 symlink"


def test_runtime_scripts_has_6_scripts():
    """runtime_scripts 下存在 6 个 runtime scripts。"""
    files = {f.name for f in RUNTIME_SCRIPTS_DIR.iterdir() if f.suffix == ".py"}
    expected = {
        "daily_lock_count.py", "lock_by_model.py", "lock_city_distribution.py",
        "assign_conversion_analysis.py", "attribute_penetration_report.py",
        "atp_price_report.py",
    }
    missing = expected - files
    assert not missing, f"runtime_scripts 缺少: {missing}"

    # skills_atp_price.py 已反向合并进 atp_price_report.py 后删除
    assert "skills_atp_price.py" not in files, "skills_atp_price.py 应已删除（已合并进 atp_price_report.py）"


def test_research_scripts_has_scripts():
    """research_scripts 下存在 research scripts。"""
    files = {f.name for f in RESEARCH_SCRIPTS_DIR.iterdir() if f.suffix == ".py"}
    expected = {
        "cohort_forecast.py", "release_curve_analysis.py",
        "lock_predict_backtest.py",
        "lock_release_curve.py", "quick_lock_ratio.py",
    }
    missing = expected - files
    assert not missing, f"research_scripts 缺少: {missing}"


def test_utility_scripts_has_scripts():
    """utility_scripts 下存在 skills_order_observation_daily.py。"""
    files = {f.name for f in UTILITY_SCRIPTS_DIR.iterdir() if f.suffix == ".py"}
    assert "skills_order_observation_daily.py" in files, "utility_scripts 缺少 skills_order_observation_daily.py"
    assert "data_dictionary.py" in files
    assert "generate_eval_cases.py" in files
    assert "voc_theme_analysis.py" in files
    assert "skills_attainment_rate_alert.py" in files


def test_reports_migrated_to_outputs():
    """reports 已迁移到 outputs/reports。"""
    assert REPORTS_DIR.exists()
    html_files = list(REPORTS_DIR.glob("*.html"))
    assert len(html_files) >= 1, f"outputs/reports 下没有 HTML 报告: {html_files}"


def test_capability_registry_runtime_scripts_paths():
    """capability_registry 中 runtime script paths 指向 runtime_scripts/。"""
    registry = json.loads(REGISTRY_PATH.read_text())
    for cap in registry:
        if cap.get("tier") == "runtime":
            sp = cap.get("script", "")
            assert "runtime_scripts" in sp, f"{cap['capability_id']} script path 不是 runtime_scripts: {sp}"
            full_path = WORKSPACE_ROOT / sp.replace("mashang_workspace/", "")
            assert full_path.exists(), f"{cap['capability_id']} 脚本不存在: {full_path}"


def test_capability_registry_research_scripts_paths():
    """capability_registry 中 research script paths 指向 research_scripts/ 或 promptbuilders/。"""
    valid_prefixes = ("research_scripts", "promptbuilders")
    registry = json.loads(REGISTRY_PATH.read_text())
    for cap in registry:
        if cap.get("tier") == "research":
            sp = cap.get("script", "")
            assert any(p in sp for p in valid_prefixes), \
                f"{cap['capability_id']} script path 不是 {valid_prefixes}: {sp}"
            full_path = WORKSPACE_ROOT / sp.replace("mashang_workspace/", "")
            assert full_path.exists(), f"{cap['capability_id']} 脚本不存在: {full_path}"


def test_capability_registry_utility_scripts_paths():
    """capability_registry 中 utility script paths 指向 utility_scripts/。"""
    registry = json.loads(REGISTRY_PATH.read_text())
    for cap in registry:
        if cap.get("tier") == "utility":
            sp = cap.get("script", "")
            assert "utility_scripts" in sp, f"{cap['capability_id']} script path 不是 utility_scripts: {sp}"
            full_path = WORKSPACE_ROOT / sp.replace("mashang_workspace/", "")
            assert full_path.exists(), f"{cap['capability_id']} 脚本不存在: {full_path}"


def test_runtime_v2_config_points_to_runtime_scripts():
    """Runtime V2 config 指向 runtime_scripts/。"""
    config = json.loads(V2_CONFIG_PATH.read_text())
    for cap_id, path in config.get("runtime_scripts", {}).items():
        assert "runtime_scripts" in path, f"{cap_id} config path 不是 runtime_scripts: {path}"


def test_runtime_v2_does_not_reference_scripts():
    """Runtime V2 config 不引用 old scripts/。"""
    config_str = V2_CONFIG_PATH.read_text()
    assert "scripts/" not in config_str.replace("runtime_scripts/", ""), \
        "Runtime V2 config 仍引用 scripts/"


def test_workspace_script_adapter_forbids_utility():
    """workspace_script_adapter 禁止 utility_scripts。"""
    sys.path.insert(0, str(_WS_DIR.parent / "mashang_runtime_v2"))
    from app.workspace_script_adapter import execute
    r = execute("test", str(UTILITY_SCRIPTS_DIR / "data_dictionary.py"), {})
    assert r["status"] == "error"
    assert "invalid_script_tier" in r.get("error", "")


def test_skills_order_observation_not_runtime_candidate():
    """skills_order_observation_daily.py 不被标记为 runtime_v2_candidate。"""
    registry = json.loads(REGISTRY_PATH.read_text())
    cap = next((c for c in registry if c.get("capability_id") == "skills_order_observation_daily"), None)
    if cap:
        promo = cap.get("promotion", {})
        assert promo.get("runtime_v2_candidate") is False, \
            "skills_order_observation_daily 不应是 runtime_v2_candidate"
    # If not in registry, that's also acceptable — it means it's not registered


def test_mashang_workspace_scripts_deleted():
    """mashang_workspace/scripts/ 已删除。"""
    assert not (WORKSPACE_ROOT / "scripts").exists(), "scripts/ 应该已删除"


def test_resolve_output_path_no_double_prefix():
    """run_eval.py resolve_output_path 不会生成双 mashang_workspace 前缀。"""
    from eval.run_eval import resolve_output_path
    # Absolute path
    p = resolve_output_path("/tmp/out.json")
    assert str(p) == "/tmp/out.json"
    # Relative path (WORKSPACE_ROOT based)
    p = resolve_output_path("outputs/tables/ci.json")
    assert p == WORKSPACE_ROOT / "outputs/tables/ci.json"
    assert "mashang_workspace/mashang_workspace" not in str(p)
    # Project-relative path (starts with mashang_workspace/)
    p = resolve_output_path("mashang_workspace/outputs/tables/ci.json")
    assert p == PROJECT_ROOT / "mashang_workspace/outputs/tables/ci.json"
    assert "mashang_workspace/mashang_workspace" not in str(p)
    # None
    assert resolve_output_path(None) is None
    assert resolve_output_path("") is None


def test_outputs_tables_no_old_scripts_cache():
    """outputs/tables 中不再有旧 scripts 路径缓存。"""
    import subprocess
    r = subprocess.run(
        ["grep", "-l", "mashang_workspace/scripts", str(WORKSPACE_ROOT / "outputs" / "tables")],
        capture_output=True, text=True, timeout=5,
    )
    assert r.returncode != 0 or r.stdout.strip() == "", \
        f"outputs/tables 仍含旧 scripts 缓存: {r.stdout.strip()}"
