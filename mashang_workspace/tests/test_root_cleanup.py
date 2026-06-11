"""
Phase 7 — 验证根目录清理完成、路径策略正确。
"""

import sys, importlib
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_WS_DIR))

from utils.paths import PROJECT_ROOT, WORKSPACE_ROOT, DATASET_DIR, OUTPUTS_DIR, DOCS_DIR, SCRIPTS_DIR, EVAL_DIR, TESTS_DIR, UTILS_DIR


def test_root_docs_not_exists():
    """根目录 docs/ 不应存在（已归档）。"""
    assert not (PROJECT_ROOT / "docs").exists(), "根目录 docs/ 应该已归档"


def test_root_scripts_not_exists():
    """根目录 scripts/ 不应存在。"""
    assert not (PROJECT_ROOT / "scripts").exists(), "根目录 scripts/ 应该已归档"


def test_root_eval_not_exists():
    """根目录 eval/ 不应存在。"""
    assert not (PROJECT_ROOT / "eval").exists(), "根目录 eval/ 应该已归档"


def test_root_tests_not_exists():
    """根目录 tests/ 不应存在。"""
    assert not (PROJECT_ROOT / "tests").exists(), "根目录 tests/ 应该已归档"


def test_root_utils_not_exists():
    """根目录 utils/ 不应存在。"""
    assert not (PROJECT_ROOT / "utils").exists(), "根目录 utils/ 应该已归档"


def test_workspace_docs_exists():
    """mashang_workspace/docs/ 应存在。"""
    assert DOCS_DIR.exists(), f"workspace docs 不存在: {DOCS_DIR}"


def test_workspace_scripts_exists():
    """mashang_workspace/scripts/ 应存在。"""
    assert SCRIPTS_DIR.exists(), f"workspace scripts 不存在: {SCRIPTS_DIR}"


def test_workspace_eval_exists():
    """mashang_workspace/eval/ 应存在。"""
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
    """核心标记：根目录已清理 + workspace 路径正确。"""
    assert not (PROJECT_ROOT / "docs").exists()
    assert DOCS_DIR.exists()
    assert not (PROJECT_ROOT / "scripts").exists()
    assert SCRIPTS_DIR.exists()
    assert not (PROJECT_ROOT / "eval").exists()
    assert EVAL_DIR.exists()
    assert not (PROJECT_ROOT / "tests").exists()
    assert TESTS_DIR.exists()
