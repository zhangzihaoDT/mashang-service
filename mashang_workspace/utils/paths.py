#!/usr/bin/env python
"""
mashang_workspace — 路径工具模块

提供跨脚本统一的项目根目录和工作区目录定位。

路径规则:
  PROJECT_ROOT   = mashang-service 根目录 (含 dataset/ .env 等)
   WORKSPACE_ROOT = mashang_workspace 目录 (含 runtime_scripts/ research_scripts/ eval/ 等)
  DATASET_DIR    = PROJECT_ROOT / "dataset"
  OUTPUTS_DIR    = WORKSPACE_ROOT / "outputs"
  DOCS_DIR       = WORKSPACE_ROOT / "docs"
"""

import sys
from pathlib import Path

# 根据本文件位置推导：utils/paths.py → WORKSPACE_ROOT → PROJECT_ROOT
_WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _WORKSPACE_ROOT.parent  # mashang-service/

WORKSPACE_ROOT = _WORKSPACE_ROOT
PROJECT_ROOT = _PROJECT_ROOT
DATASET_DIR = _PROJECT_ROOT / "dataset"
OUTPUTS_DIR = _WORKSPACE_ROOT / "outputs"
DOCS_DIR = _WORKSPACE_ROOT / "docs"
RUNTIME_SCRIPTS_DIR = _WORKSPACE_ROOT / "runtime_scripts"
RESEARCH_SCRIPTS_DIR = _WORKSPACE_ROOT / "research_scripts"
UTILITY_SCRIPTS_DIR = _WORKSPACE_ROOT / "utility_scripts"
LEGACY_SCRIPTS_DIR = _WORKSPACE_ROOT / "legacy_scripts"  # retired — directory deleted
REPORTS_DIR = OUTPUTS_DIR / "reports"
EVAL_DIR = _WORKSPACE_ROOT / "eval"
TESTS_DIR = _WORKSPACE_ROOT / "tests"
UTILS_DIR = _WORKSPACE_ROOT / "utils"
CASES_DIR = _WORKSPACE_ROOT / "eval" / "cases"
RUNTIME_DIR = _PROJECT_ROOT / "mashang_runtime"
SHARED_DIR = _PROJECT_ROOT / "shared"
SHARED_OPERATORS_DIR = SHARED_DIR / "operators"
SHARED_SCHEMA_DIR = SHARED_DIR / "schema"
BUSINESS_DEFINITION_PATH = SHARED_SCHEMA_DIR / "business_definition.json"
CONFIG_SEMANTICS_PATH = SHARED_SCHEMA_DIR / "config_semantics.json"
SHARED_DATA_PATH_MD = SHARED_SCHEMA_DIR / "data_path.md"


def resolve_data_path(description_keyword: str) -> Path | None:
    """从 shared/schema/data_path.md 中按描述关键词查找对应的数据路径。

    data_path.md 是外部数据源的唯一登记处，每行格式：{描述}：{路径}
    """
    if not SHARED_DATA_PATH_MD.exists():
        return None
    for line in SHARED_DATA_PATH_MD.read_text(encoding="utf-8").splitlines():
        if "：" not in line:
            continue
        desc, path_raw = line.split("：", 1)
        if description_keyword in desc:
            # data_path.md 是 markdown，路径中的下划线会被转义（\_ → _）
            path = path_raw.strip().replace("\\_", "_").replace("\\", "")
            p = Path(path)
            if p.exists():
                return p
    return None


def ensure_workspace_on_path() -> None:
    """确保 WORKSPACE_ROOT 在 sys.path 中。"""
    ws = str(WORKSPACE_ROOT)
    if ws not in sys.path:
        sys.path.insert(0, ws)


def ensure_project_on_path() -> None:
    """确保 PROJECT_ROOT 在 sys.path 中。"""
    pr = str(PROJECT_ROOT)
    if pr not in sys.path:
        sys.path.insert(0, pr)


def ensure_runtime_on_path() -> None:
    """确保 RUNTIME_DIR 在 sys.path 中，方便旧 operators/schema 等模块导入。"""
    rt = str(RUNTIME_DIR)
    if rt not in sys.path:
        sys.path.insert(0, rt)


def ensure_shared_on_path() -> None:
    """确保 SHARED_DIR 在 sys.path 中（优先于 runtime），以便 import operators/schema 使用共享版本。

    无论 shared 是否已在 sys.path 中，都会把它提到最前，避免被 pytest 等其他 sys.path 修改
    压到 runtime 之后，导致 import operators 解析到旧 mashang_runtime/operators。
    """
    sh = str(SHARED_DIR)
    rt = str(RUNTIME_DIR)
    if sh in sys.path:
        sys.path.remove(sh)
    sys.path.insert(0, sh)
    if rt in sys.path:
        sys.path.remove(rt)
        sys.path.insert(1, rt)


def get_output_path(kind: str, filename: str) -> Path:
    """返回 outputs/{kind}/{filename} 的完整路径。kind: tables/reports/charts"""
    valid = {"tables", "reports", "charts"}
    if kind not in valid:
        raise ValueError(f"kind 必须是 {valid} 之一，收到 '{kind}'")
    p = OUTPUTS_DIR / kind / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_cases_path(filename: str) -> Path:
    """返回 eval/cases/{filename} 的完整路径。"""
    p = CASES_DIR / filename
    return p


# 启动时自动确保所有路径在 sys.path 中
ensure_workspace_on_path()
ensure_project_on_path()
ensure_runtime_on_path()
ensure_shared_on_path()
