"""
series_group_logic 规则重叠审计回归测试

治理目标：
  - 重叠只允许发生在族内（LS6 家族 / L6 家族），由 priority/precedence 裁决；
  - 跨车系重叠（同一 product_name 命中不同车系规则）视为规则治理问题，必须为零；
  - DM2 规则收紧后，非 L6 家族的 "M2" 产品不得落入 DM2。
"""

import importlib.util
import json
from pathlib import Path

import pytest

_WS_DIR = Path(__file__).resolve().parents[1]
_PRJ_DIR = _WS_DIR.parent
_BUSINESS_DEF = _PRJ_DIR / "shared" / "schema" / "business_definition.json"
_AUDIT_SCRIPT = _WS_DIR / "utility_scripts" / "audit_series_group_overlap.py"


def _bdef() -> dict:
    return json.loads(_BUSINESS_DEF.read_text(encoding="utf-8"))


def _audit():
    """加载 audit_series_group_overlap.py 的 audit_overlap 函数。"""
    spec = importlib.util.spec_from_file_location("audit_mod", _AUDIT_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {_AUDIT_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.audit_overlap


def test_audit_reports_intended_within_family_overlaps_only():
    """族内重叠应被审计识别，且不跨车系。"""
    bdef = _bdef()
    names = [
        "L6 M2 Pro Max",          # DM0 ∩ DM2（L6 族内）
        "全新一代 智己  L6 Prof. JimmyChoo 高定限量版（93kWh）",  # DM1 ∩ DM2
        "LS6 76 Max 上汽一亿台限定版",  # CM2 ∩ CM0（LS6 族内）
        "智己LS9",                # 单规则
    ]
    res = _audit()(bdef, names)
    assert res["overlap_count"] == 3
    assert res["cross_family_overlap_count"] == 0
    assert set(res["overlaps"]["L6 M2 Pro Max"]) == {"DM0", "DM2"}


def test_audit_flags_cross_family_overlap():
    """跨车系重叠（规则治理问题）应被审计标记。"""
    bdef = _bdef()
    synthetic = bdef.copy()
    # 人为制造跨车系重叠：一个产品同时命中 L6 族(DM0) 与 LS6 族(CM0)
    synthetic["series_group_logic"] = dict(bdef["series_group_logic"])
    synthetic["series_group_logic"]["DM0"] = {
        "priority": 1,
        "condition": "product_name LIKE '%L6%' OR product_name LIKE '%LS6%'",
    }
    res = _audit()(synthetic, ["智己LS6 Max"])
    assert res["cross_family_overlap_count"] == 1
    assert res["cross_family_overlaps"]["智己LS6 Max"] == ["CM0", "DM0"]


def test_tightened_dm2_excludes_non_l6_m2():
    """DM2 收紧后，含 M2 但非 L6 家族的产品不得进入 DM2。"""
    bdef = _bdef()
    names = ["智己LS6 M2", "L6 M2 Max", "Prof.Jimmy Choo 高定限量版 标准续航版"]
    res = _audit()(bdef, names)
    for p, hits in res["overlaps"].items():
        assert "DM2" not in hits or p != "智己LS6 M2"


def test_real_data_no_cross_family_overlap():
    """真实数据断言：全量 product_name 无跨车系重叠（CI 无数据集时跳过）。"""
    import pandas as pd
    dataset = _PRJ_DIR / "dataset" / "order_data.parquet"
    if not dataset.exists():
        pytest.skip("dataset/order_data.parquet 不存在（CI 跳过真实数据断言）")
    product_names = pd.read_parquet(dataset, columns=["product_name"])["product_name"].dropna().tolist()
    product_names = sorted(set(product_names))
    res = _audit()(_bdef(), product_names)
    assert res["cross_family_overlap_count"] == 0, res["cross_family_overlaps"]
    assert res["overlap_count"] > 0  # 族内重叠存在且被审计捕获
