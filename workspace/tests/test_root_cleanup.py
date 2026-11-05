"""
Phase 7 — 验证根目录清理完成、路径策略正确。
"""

import sys, importlib
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_WS_DIR))

from utils.paths import PROJECT_ROOT, WORKSPACE_ROOT, DATASET_DIR, OUTPUTS_DIR, DOCS_DIR, EVAL_DIR, TESTS_DIR, UTILS_DIR, BUSINESS_SCRIPTS_DIR, RESEARCH_SCRIPTS_DIR, UTILITY_SCRIPTS_DIR, LEGACY_SCRIPTS_DIR, REPORTS_DIR


def _visible_items(directory: Path):
    """Return non-hidden, non-generated entries in a directory."""
    skip = {"__pycache__", ".DS_Store"}
    return sorted(
        f.name for f in directory.iterdir()
        if not f.name.startswith(".") and f.name not in skip
    )


SCRIPTS_ALLOWLIST = frozenset({
    "__init__.py",
    "build_tp_and_mix_ways_dataset.py",
    "render_official_document.py",
    "smoke_test_official_document_render.py",
    "analyze_nev_apeal_topic.py",
    "explore_sav.py",
    "parse_nev_apeal_questionnaire.py",
    "verify_nev_apeal_2024.py",
})
TESTS_ALLOWLIST = frozenset({
    "test_tp_and_mix_ways_dataset_build.py",
    "test_tp_and_mix_ways_raw_guard.py",
})


def test_docs_and_skills_have_one_project_location():
    """文档和 Skills 在根目录统一发现，工作区采用 workspace 名称。"""
    assert WORKSPACE_ROOT == PROJECT_ROOT / "workspace"
    assert DOCS_DIR == PROJECT_ROOT / "docs"
    assert (DOCS_DIR / "README.md").is_file()
    assert not (WORKSPACE_ROOT / "docs").exists()
    assert not (WORKSPACE_ROOT / ".opencode").exists()
    for name in ("branded_html_report", "cpca-weekly-data-capture",
                 "monthly-market-report", "runtime-eval-diagnosis"):
        assert (PROJECT_ROOT / ".opencode" / "skills" / name / "SKILL.md").is_file()


def test_skill_discovery_uses_project_directory():
    from workspace.utility_scripts.build_workspace_skills_catalog import scan_workspace_skills
    from workspace.utility_scripts.build_workspace_capability_inventory import load_skills

    expected = {
        str(p.parent.relative_to(PROJECT_ROOT))
        for p in (PROJECT_ROOT / ".opencode" / "skills").glob("*/SKILL.md")
    }
    catalog = scan_workspace_skills()
    inventory = load_skills()
    assert {s["directory"].rstrip("/") for s in catalog} == expected
    assert {s["path"].rstrip("/") for s in inventory} == expected
    assert len(catalog) == len(expected)
    assert len(inventory) == len(expected)


def test_root_scripts_not_exists():
    """根目录 scripts/ 仅含 service 级构建脚本，非 workspace 脚本。"""
    scripts_dir = PROJECT_ROOT / "scripts"
    if scripts_dir.exists():
        items = _visible_items(scripts_dir)
        unexpected = [f for f in items if f not in SCRIPTS_ALLOWLIST]
        assert not unexpected, f"scripts/ 发现未允许文件: {unexpected}"
        assert all(f.endswith(".py") for f in items if f != "__init__" or True), \
            f"scripts/ 应仅含 .py 文件: {items}"


def test_root_eval_not_exists():
    """根目录 eval/ 不应存在。"""
    assert not (PROJECT_ROOT / "eval").exists(), "根目录 eval/ 应该已归档"


def test_root_tests_not_exists():
    """根目录 tests/ 仅含 service 级测试（如 test_tp_and_mix_ways_dataset_build.py），非 workspace 测试。"""
    tests_dir = PROJECT_ROOT / "tests"
    if tests_dir.exists():
        items = _visible_items(tests_dir)
        unexpected = [f for f in items if f not in TESTS_ALLOWLIST]
        assert not unexpected, f"tests/ 发现未允许文件: {unexpected}"


def test_root_utils_not_exists():
    """根目录 utils/ 不应存在。"""
    assert not (PROJECT_ROOT / "utils").exists(), "根目录 utils/ 应该已归档"


def test_project_docs_exists():
    """docs/ 应存在。"""
    assert DOCS_DIR.exists(), f"workspace docs 不存在: {DOCS_DIR}"


def test_workspace_scripts_not_exists():
    """workspace/scripts/ 已删除。"""
    assert not (WORKSPACE_ROOT / "scripts").exists(), "workspace scripts/ 应该已经删除"


def test_business_scripts_is_real_dir():
    """business_scripts/ 是真实目录，不是 symlink。"""
    assert BUSINESS_SCRIPTS_DIR.exists(), f"business_scripts 不存在: {BUSINESS_SCRIPTS_DIR}"
    assert not BUSINESS_SCRIPTS_DIR.is_symlink(), "business_scripts 不应是 symlink"


def test_business_scripts_has_6_scripts():
    """business_scripts/ 下应有 6 个 runtime 脚本。"""
    files = [f.name for f in BUSINESS_SCRIPTS_DIR.iterdir() if f.suffix == ".py"]
    expected = {"daily_lock_count.py", "lock_by_model.py", "lock_city_distribution.py",
                "assign_conversion_analysis.py", "attribute_penetration_report.py",
                "atp_price_report.py"}
    assert expected.issubset(set(files)), f"business_scripts 缺少脚本: {expected - set(files)}"


def test_research_scripts_exists():
    """research_scripts/ 存在且有脚本。"""
    assert RESEARCH_SCRIPTS_DIR.exists(), f"research_scripts 不存在: {RESEARCH_SCRIPTS_DIR}"
    files = [f.name for f in RESEARCH_SCRIPTS_DIR.iterdir() if f.suffix == ".py"]
    assert len(files) >= 5, f"research_scripts 脚本不足: {files}"


def test_utility_scripts_exists():
    """utility_scripts/ 存在且含 skills_order_observation_daily.py。"""
    assert UTILITY_SCRIPTS_DIR.exists(), f"utility_scripts 不存在: {UTILITY_SCRIPTS_DIR}"
    assert (UTILITY_SCRIPTS_DIR / "skills_order_observation_daily.py").exists(), \
        "utility_scripts 缺少 skills_order_observation_daily.py"


def test_legacy_scripts_retired():
    """legacy_scripts/ 已退休删除。"""
    assert not LEGACY_SCRIPTS_DIR.exists(), f"legacy_scripts 应已删除: {LEGACY_SCRIPTS_DIR}"


def test_reports_dir_exists():
    """outputs/reports/ 存在。"""
    assert REPORTS_DIR.exists(), f"reports 目录不存在: {REPORTS_DIR}"


def test_workspace_eval_exists():
    """workspace/eval/ 应存在。"""
    assert EVAL_DIR.exists(), f"workspace eval 不存在: {EVAL_DIR}"


def test_utils_paths_importable():
    """utils.paths 可导入且包含必需常量。"""
    from utils.paths import PROJECT_ROOT, WORKSPACE_ROOT, DATASET_DIR
    assert PROJECT_ROOT is not None
    assert WORKSPACE_ROOT is not None
    assert DATASET_DIR is not None


def test_project_root_is_correct():
    """PROJECT_ROOT 指向 mashang-service/。"""
    assert PROJECT_ROOT.name == "mashang-service" or (PROJECT_ROOT / "dataset").exists()


def test_dataset_dir():
    """DATASET_DIR = 根目录 / "dataset"。"""
    assert DATASET_DIR == PROJECT_ROOT / "dataset"
    assert DATASET_DIR.exists(), f"dataset 不存在: {DATASET_DIR}"


def test_workspace_outputs():
    """OUTPUTS_DIR 指向 workspace outputs。"""
    assert OUTPUTS_DIR == WORKSPACE_ROOT / "outputs"


def test_root_cleanup_docs_removed():
    """历史根目录清理文档已删除。"""
    assert not (PROJECT_ROOT / "ROOT_CLEANUP.md").exists()
    assert not (PROJECT_ROOT / "RUNTIME_FREEZE.md").exists()


def test_archive_removed():
    """archive/ 目录已删除。"""
    assert not (PROJECT_ROOT / "archive").exists()


def test_path_resolution():
    """核心标记：根目录清理状态 + workspace 路径正确。

    Service 级目录允许存在（严格白名单）：
      - scripts/   — 仅 SCRIPTS_ALLOWLIST 中的文件
      - tests/     — 仅 TESTS_ALLOWLIST 中的文件
    Workspace 级目录不应出现在根目录：
      - eval/      — 应在 workspace/eval/
      - utils/     — 应在 workspace/utils/
    """
    for name, allowlist in [("scripts", SCRIPTS_ALLOWLIST), ("tests", TESTS_ALLOWLIST)]:
        d = PROJECT_ROOT / name
        if d.exists():
            items = _visible_items(d)
            unexpected = [f for f in items if f not in allowlist]
            assert not unexpected, f"根目录 {name}/ 发现未允许文件: {unexpected}"

    assert DOCS_DIR.exists()
    assert EVAL_DIR.exists()
    assert TESTS_DIR.exists()
    assert not (PROJECT_ROOT / "eval").exists(), "根目录 eval/ 应该已归档到 workspace"
    assert not (WORKSPACE_ROOT / "scripts").exists(), "workspace scripts/ 应该已经删除"
    assert BUSINESS_SCRIPTS_DIR.exists()
    assert RESEARCH_SCRIPTS_DIR.exists()
    assert UTILITY_SCRIPTS_DIR.exists()
    assert not LEGACY_SCRIPTS_DIR.exists()
    assert REPORTS_DIR.exists()
