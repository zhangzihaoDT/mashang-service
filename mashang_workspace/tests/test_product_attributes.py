"""产品属性解析回归：product_name → 代际 → 版本 → 动力（版本字典为单一事实来源）。

治理目标：
  - 动力类型只由 product_version_series 决定，不由 52/66 模糊匹配决定；
  - 新增纯电版本（如 93 RWD / NEO 103 Max+）只改版本字典；
  - 字典未覆盖的版本必须显式「未知」并告警，不得静默归类；
  - 电池容量不复用版本编号（52/66/93/103 不等于实测 kWh）。
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_WS_DIR = Path(__file__).resolve().parents[1]
_PRJ_DIR = _WS_DIR.parent
_BUSINESS_DEF = _PRJ_DIR / "shared" / "schema" / "business_definition.json"

sys.path.insert(0, str(_PRJ_DIR / "shared"))

from operators.product_attributes import (  # noqa: E402
    KWH_NOT_CONFIRMED,
    NO_SEAT,
    UNCLASSIFIED,
    UNKNOWN,
    resolve_product_attributes,
)
from operators.series_group_logic import apply_series_group_logic  # noqa: E402


def _bdef() -> dict:
    return json.loads(_BUSINESS_DEF.read_text(encoding="utf-8"))


def _resolve(names, bdef=None):
    bdef = bdef or _bdef()
    df = pd.DataFrame({"product_name": names})
    df = apply_series_group_logic(df, bdef)
    return resolve_product_attributes(df, bdef)


def test_power_type_comes_from_version_dictionary():
    names = [
        "智己LS8 52 Max+ 科技旗舰大五座",
        "智己LS8 52 Lite 奢享大六座",
        "智己LS8 66 Ultra 奢享大六座",
        "LS8 93 RWD 5座",
        "智己LS8 NEO 93 Max+",
        "智己LS8 NEO 103 Max+",
    ]
    a = _resolve(names)
    assert a.version.tolist() == [
        "52 Max+", "52 Lite", "66 Ultra", "93 RWD", "NEO93 Max+", "NEO103 Max+"
    ]
    assert a.power_type.tolist() == ["增程", "增程", "增程", "纯电", "纯电", "纯电"]
    assert a.warnings == []


def test_93_rwd_is_bev_not_reengineered_by_52_66_heuristic():
    """历史模糊规则下 93 RWD 因「无 52/66」被误判纯电属巧合；现在由版本字典显式声明。"""
    bdef = _bdef()
    a = _resolve(["LS8 93 RWD 5座"], bdef)
    assert a.power_type.tolist() == ["纯电"]
    # 即使把版本串改成纯数字，判定仍以字典为准，不看电量段
    stripped = json.loads(json.dumps(bdef))
    stripped["product_version_series"]["series"]["LS8"]["93 RWD"]["power_type"] = "未知"
    assert _resolve(["LS8 93 RWD 5座"], stripped).power_type.tolist() == ["未知"]


def test_bare_name_and_new_version_are_unknown_with_warning():
    a = _resolve(["智己LS8", "智己LS8 NEO", "智己LS8 新版本 5座"])
    assert a.version.tolist()[:2] == [UNCLASSIFIED, UNCLASSIFIED]
    assert a.power_type.tolist() == [UNKNOWN, UNKNOWN, UNKNOWN]
    assert a.warnings, "未登记版本必须告警，不得静默归类"
    assert any("product_version_series" in w for w in a.warnings)


def test_unknown_new_version_warning_is_actionable():
    """新增版本若不登记，动力必须是未知——避免新名字悄悄改变增程/纯电拆分。"""
    bdef = _bdef()
    patched = json.loads(json.dumps(bdef))
    patched["product_version_logic"]["LS8"]["52 Max Ultra"] = {
        "priority": 3,
        "condition": "product_name LIKE '%LS8%' AND product_name LIKE '%52MaxUltra%'",
    }
    a = _resolve(["智己LS8 52 Max Ultra 五座"], patched)
    assert a.version.tolist() == ["52 Max Ultra"]
    assert a.power_type.tolist() == [UNKNOWN]
    assert any("52 Max Ultra" in w for w in a.warnings)


def test_seats_and_battery_are_independent():
    a = _resolve(
        [
            "智己LS8 52 Max+ 科技旗舰大五座",
            "智己LS8 52 Max+ 奢享大六座",
            "智己LS8 52 Max+",
            "智己LS8 NEO 93 Max+",
        ]
    )
    assert a.seat_count.tolist() == ["五座", "六座", NO_SEAT, NO_SEAT]
    # 版本编号（52/93/103）不自动写入电池容量
    assert set(a.battery_kwh) == {KWH_NOT_CONFIRMED}


def test_confirmed_battery_kwh_is_used_when_declared():
    bdef = _bdef()
    patched = json.loads(json.dumps(bdef))
    patched["product_version_series"]["series"]["LS8"]["93 RWD"]["battery_kwh"] = 93
    a = _resolve(["LS8 93 RWD 5座"], patched)
    assert a.battery_kwh.tolist() == ["93kwh"]


def test_neo_generation_inherits_ls8_family_version_table():
    """LS8Neo 是 LS8 族代际组，共用版本表，无需重复登记。"""
    bdef = _bdef()
    assert "LS8Neo" not in bdef["product_version_series"]["series"]
    assert "LS8Neo" in bdef["model_series_mapping"]["LS8"]
    a = _resolve(["智己LS8 NEO 93 Max+", "智己LS8 NEO 103 Max+"], bdef)
    assert a.generation.tolist() == ["LS8Neo", "LS8Neo"]
    assert a.power_type.tolist() == ["纯电", "纯电"]


def test_non_ls8_series_keep_legacy_rule():
    """非版本字典车系（LS6/L6/LS9）继续走 product_type_logic，行为不变。"""
    a = _resolve(
        [
            "全新一代智己LS6 52 Max",   # CM3 增程
            "全新一代智己LS6 Ultra",     # CM3 纯电
            "智己L6",                   # 裸名 → 无 52/66 → 纯电（历史口径）
        ]
    )
    assert a.generation.tolist() == ["CM3", "CM3", "DM0"]
    assert a.power_type.tolist() == ["增程", "纯电", "纯电"]


def test_product_type_logic_bev_rule_covers_93_103():
    """product_type_logic 的纯电定义需显式包含 93/103 电量段。"""
    bdef = _bdef()
    bev = bdef["product_type_logic"]["纯电"]
    assert "%93%" in bev.replace(" ", "")
    assert "%103%" in bev.replace(" ", "")


def test_quick_lock_ratio_uses_shared_resolver():
    """quick_lock_ratio 的动力判定必须走 shared 版本字典，不再硬编码 52/66。"""
    import importlib.util

    path = _WS_DIR / "research_scripts" / "quick_lock_ratio.py"
    src = path.read_text(encoding="utf-8")
    assert "product_type_of" in src
    assert 'any(num in s for num in ["52", "66"])' not in src

    spec = importlib.util.spec_from_file_location("qlr_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    bdef = _bdef()
    assert mod.product_type_of("LS8 93 RWD 5座", bdef) == "纯电"
    assert mod.product_type_of("智己LS8 NEO 103 Max+", bdef) == "纯电"
    assert mod.product_type_of("智己LS8 52 Max+ 科技旗舰大五座", bdef) == "增程"
    # 裸名不再被「无 52/66 ⇒ 纯电」兜底成纯电
    assert mod.product_type_of("智己LS8", bdef) == "未知"
    assert mod.product_type_of(None, bdef) == "未知"
