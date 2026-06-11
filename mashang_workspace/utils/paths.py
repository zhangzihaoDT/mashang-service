#!/usr/bin/env python
"""
mashang_workspace — 路径工具模块

提供跨脚本统一的项目根目录和工作区目录定位。

路径规则:
  PROJECT_ROOT   = mashang-service 根目录 (含 dataset/ .env 等)
  WORKSPACE_ROOT = mashang_workspace 目录 (含 docs/ scripts/ eval/ 等)
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
SCRIPTS_DIR = _WORKSPACE_ROOT / "scripts"
EVAL_DIR = _WORKSPACE_ROOT / "eval"
TESTS_DIR = _WORKSPACE_ROOT / "tests"
UTILS_DIR = _WORKSPACE_ROOT / "utils"
CASES_DIR = _WORKSPACE_ROOT / "eval" / "cases"
RUNTIME_DIR = _PROJECT_ROOT / "mashang_runtime"
SHARED_DIR = _PROJECT_ROOT / "shared"
SHARED_OPERATORS_DIR = SHARED_DIR / "operators"
SHARED_SCHEMA_DIR = SHARED_DIR / "schema"
BUSINESS_DEFINITION_PATH = SHARED_SCHEMA_DIR / "business_definition.json"


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
    """确保 SHARED_DIR 在 sys.path 中（优先于 runtime），以便 import operators/schema 使用共享版本。"""
    sh = str(SHARED_DIR)
    # Insert shared before runtime so it takes priority
    rt = str(RUNTIME_DIR)
    if sh not in sys.path:
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
