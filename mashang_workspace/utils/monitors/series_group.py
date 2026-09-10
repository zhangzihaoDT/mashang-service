"""series_group_logic 统一入口。

直接按文件加载 shared/operators/series_group_logic.py，避免 `import operators`
触发 shared/operators/__init__.py → registry → mashang_runtime/tools 依赖链。
"""

from __future__ import annotations

import importlib.util

from utils.paths import SHARED_OPERATORS_DIR

DEFAULT_GROUP = "其他"


def _load_shared_module():
    path = SHARED_OPERATORS_DIR / "series_group_logic.py"
    spec = importlib.util.spec_from_file_location("_shared_series_group_logic", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_shared = _load_shared_module()

apply_series_group_logic = _shared.apply_series_group_logic
eval_series_group_logic_expr = _shared._eval_series_group_logic_expr
rule_condition = _shared._rule_condition
rule_priority = _shared._rule_priority
