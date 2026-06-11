#!/usr/bin/env python
"""
mashang_runtime — 旧 Runtime 内部路径工具

提供 mashang_runtime 内部脚本统一的根目录和工作区目录定位。

路径规则:
  PROJECT_ROOT  = mashang-service 根目录 (含 dataset/ .env)
  RUNTIME_ROOT  = mashang_runtime 目录
  DATASET_DIR   = PROJECT_ROOT / "dataset"
  LOGS_DIR      = PROJECT_ROOT / "logs"
"""

import sys
from pathlib import Path

_RUNTIME_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _RUNTIME_ROOT.parent

RUNTIME_ROOT = _RUNTIME_ROOT
PROJECT_ROOT = _PROJECT_ROOT
DATASET_DIR = _PROJECT_ROOT / "dataset"
LOGS_DIR = _PROJECT_ROOT / "logs"
SHARED_DIR = _PROJECT_ROOT / "shared"
SHARED_OPERATORS_DIR = SHARED_DIR / "operators"
SHARED_SCHEMA_DIR = SHARED_DIR / "schema"
BUSINESS_DEFINITION_PATH = SHARED_SCHEMA_DIR / "business_definition.json"

# 确保 shared 优先、runtime 其次、root 最末
for p in [str(SHARED_DIR), str(_RUNTIME_ROOT), str(_PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)
    else:
        # Ensure ordering: shared > runtime > root
        sys.path.remove(p)
        sys.path.insert(0, p)
