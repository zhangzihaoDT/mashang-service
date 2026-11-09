"""quick_lock_ratio 口径治理回归。

治理约束：
  - 锁单数统一为 order_number 去重后的有效锁单事件；
  - 上市日/代际一律来自 schema（time_periods.end / series_group_logic），脚本内不再自带映射；
  - 图 4 按 product_version 精确识别 66 Ultra，分母为 LS8 代际组（排除 NEO）；
  - 单图失败不得让整份报告静默缺失该图。
"""

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

_WS_DIR = Path(__file__).resolve().parents[1]
_PRJ_DIR = _WS_DIR.parent
_BUSINESS_DEF = _PRJ_DIR / "shared" / "schema" / "business_definition.json"
_SCRIPT = _WS_DIR / "research_scripts" / "quick_lock_ratio.py"

sys.path.insert(0, str(_WS_DIR))
sys.path.insert(0, str(_PRJ_DIR / "shared"))


@pytest.fixture(scope="module")
def mod():
    import importlib.util

    spec = importlib.util.spec_from_file_location("qlr_gov", _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def bdef() -> dict:
    return json.loads(_BUSINESS_DEF.read_text(encoding="utf-8"))


def _events(mod, bdef, rows) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["order_number", "lock_time", "product_name", "series"])
    return mod.prepare_lock_events(frame, bdef)


def test_no_hand_written_launch_mapping_in_source():
    """脚本不得再自带「新一代→CM2 / 全新→CM1」等代际映射。"""
    src = _SCRIPT.read_text(encoding="utf-8")
    assert 'series_group = "CM2"' not in src
    assert 'series_group = "CM1"' not in src
    assert '"2026-04-16"' not in src, "LS8 上市日不得硬编码"


def test_launch_date_comes_from_time_periods(mod, bdef):
    """上市日取 time_periods.end（上市日），不是预售开始日 start。"""
    launch = mod.get_launch_date_for_product("智己LS8 66 Ultra 科技旗舰大五座", bdef)
    assert launch == date.fromisoformat(bdef["time_periods"]["LS8"]["end"])
    presale_start = date.fromisoformat(bdef["time_periods"]["LS8"]["start"])
    assert launch != presale_start, "不得把预售开始日当作上市日"


def test_launch_date_unknown_generation_returns_none(mod, bdef):
    """代际无法判定 / 上市日未确认 → None，不得用预售日冒充。"""
    assert mod.get_launch_date_for_product("不存在的车", bdef) is None
    # 使用独立配置模拟未确认上市日，不依赖实际代际的当前上市状态。
    from copy import deepcopy

    unconfirmed = deepcopy(bdef)
    unconfirmed["time_periods"]["LS8Neo"].pop("end", None)
    assert mod.get_launch_date_for_product("智己LS8 NEO 93 Max+", unconfirmed) is None


def test_launch_date_supports_new_generations(mod, bdef):
    """LS8Neo / DM2 / CM3 等新代际通过 series_group_logic 识别，不依赖旧硬编码。"""
    assert mod._generation_of("智己LS8 NEO 93 Max+", bdef) == "LS8Neo"
    assert mod.get_launch_date_for_product("智己LS8 NEO 93 Max+", bdef) == date.fromisoformat(
        bdef["time_periods"]["LS8Neo"]["end"]
    )
    assert mod._generation_of("全新一代智己LS6 Max", bdef) == "CM3"
    assert mod.get_launch_date_for_product("全新一代智己LS6 Max", bdef) == date.fromisoformat(
        bdef["time_periods"]["CM3"]["end"]
    )


def test_lock_counts_are_deduplicated(mod, bdef):
    """同一 order_number 多次出现时只计一次锁单事件。"""
    ev = _events(mod, bdef, [
        ("o1", "2026-05-01 10:00", "智己LS8 66 Ultra 科技旗舰大五座", "LS8"),
        ("o1", "2026-05-01 11:00", "智己LS8 66 Ultra 科技旗舰大五座", "LS8"),
        ("o2", "2026-05-01 12:00", "智己LS8 52 Max+ 科技旗舰大五座", "LS8"),
    ])
    assert len(ev) == 3
    assert int(mod.daily_lock_counts(ev).sum()) == 2


def test_ls8_66_uses_product_version_not_substring(mod, bdef):
    """图 4 按 product_version 精确识别 66 Ultra。"""
    ev = _events(mod, bdef, [
        ("o1", "2026-05-02 10:00", "智己LS8 66 Ultra 科技旗舰大五座", "LS8"),
        ("o2", "2026-05-02 11:00", "智己LS8 52 Max+ 科技旗舰大五座", "LS8"),
        # 含 "66" 字面量但并非 66 Ultra 版本（旧口径会被误计）
        ("o3", "2026-05-02 12:00", "智己LS8 52 Max+ 66周年纪念版", "LS8"),
    ])
    m = mod.compute_ls8_66_metrics(ev, bdef, today=date(2026, 5, 3))
    assert int(m["daily_66"].sum()) == 1
    assert int(m["daily_total"].sum()) == 3


def test_ls8_denominator_excludes_neo(mod, bdef):
    """分母为 LS8 代际组，NEO 独立成代际，不计入。"""
    ev = _events(mod, bdef, [
        ("o1", "2026-05-02 10:00", "智己LS8 66 Ultra 科技旗舰大五座", "LS8"),
        ("o2", "2026-05-02 11:00", "智己LS8 NEO 93 Max+", "LS8"),
    ])
    m = mod.compute_ls8_66_metrics(ev, bdef, today=date(2026, 5, 3))
    assert int(m["daily_total"].sum()) == 1


def test_ls8_66_starts_at_launch_date_not_presale(mod, bdef):
    """窗口起点 = 上市日端；预售期锁单不计入。"""
    launch = bdef["time_periods"]["LS8"]["end"]
    presale = bdef["time_periods"]["LS8"]["start"]
    ev = _events(mod, bdef, [
        ("presale", f"{presale} 12:00", "智己LS8 66 Ultra 科技旗舰大五座", "LS8"),
        ("launch", f"{launch} 12:00", "智己LS8 66 Ultra 科技旗舰大五座", "LS8"),
    ])
    m = mod.compute_ls8_66_metrics(ev, bdef, today=date.fromisoformat(launch))
    assert int(m["daily_total"].sum()) == 1


def test_failed_chart_is_visible_in_html(mod):
    """单图失败要在 HTML 中留可见错误块，不得静默缺失。"""
    charts, errors = {}, {}

    def boom():
        raise ValueError("模拟失败：缺少列")

    mod.run_chart(4, "LS8 66 Ultra 锁单占比", boom, charts, errors)
    assert 4 in errors and 4 not in charts
    block = mod._error_block(4, mod.CHART_TITLES[4], errors[4][1])
    assert "图 4 生成失败" in block
    assert "缺少列" in block


def test_empty_result_is_reported_as_error(mod, bdef):
    """返回空结果也算失败（避免空图静默出现在报告里）。"""
    charts, errors = {}, {}
    mod.run_chart(3, "LS6", lambda: None, charts, errors)
    assert 3 in errors and 3 not in charts
