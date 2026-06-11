"""
Tests for eval/context_parser.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from eval.context_parser import parse_context


def _check(result: dict, field: str, expected, msg: str = ""):
    """Helper: assert resolved_context[field] == expected."""
    actual = result["resolved_context"].get(field)
    assert actual == expected, f"{msg}: expected {expected!r}, got {actual!r}"


def test_yesterday_lock_by_model():
    """昨天锁单数分车型 → lock_count + yesterday + group_by=model (actually 'series' in text)"""
    r = parse_context("昨天锁单数分车型")
    assert r["resolved_context"]["metric"] == "lock_count"
    assert r["resolved_context"]["time_window"] == "yesterday"
    assert r["resolved_context"]["group_by"] == "model"


def test_yesterday_ls8_city():
    """昨天 LS8 的 75 个锁单城市分布 → lock_count + yesterday + LS8 + city"""
    r = parse_context("昨天 LS8 的 75 个锁单城市分布")
    _check(r, "metric", "lock_count")
    _check(r, "time_window", "yesterday")
    _check(r, "series", "LS8")
    assert r["resolved_context"].get("group_by") == "city", f"got {r['resolved_context'].get('group_by')}"


def test_ls6_energy_share():
    """近 15 日 LS6 增程和纯电占比 → lock_count_share + last_15_days + LS6 + energy_type"""
    r = parse_context("近 15 日 LS6 增程和纯电占比")
    _check(r, "metric", "lock_count_share")
    _check(r, "series", "LS6")
    _check(r, "group_by", "energy_type")
    # time_window could be last_15_days
    tw = r["resolved_context"].get("time_window", "")
    assert "15" in tw, f"expected time_window containing 15, got {tw}"


def test_last_7_days_inheritance():
    """那最近 7 天呢？ 在 previous_context 下继承 metric/series/group_by，覆盖 time_window"""
    prev = {"metric": "lock_count_share", "time_window": "last_15_days", "series": "LS6", "group_by": "energy_type"}
    r = parse_context("那最近 7 天呢？", previous_context=prev)
    _check(r, "metric", "lock_count_share")
    _check(r, "series", "LS6")
    _check(r, "group_by", "energy_type")
    tw = r["resolved_context"].get("time_window", "")
    assert "7" in tw, f"expected time_window containing 7, got {tw}"
    assert r["overridden_context"].get("time_window", {}).get("from") == "last_15_days"


def test_large_battery_filter():
    """只看大电池组 在 previous_context 下追加 filter = large_battery"""
    prev = {"metric": "lock_count_share", "time_window": "since_launch", "series": "LS8", "group_by": "model"}
    r = parse_context("只看大电池组", previous_context=prev)
    _check(r, "metric", "lock_count_share")
    _check(r, "series", "LS8")
    _check(r, "group_by", "model")
    filters = r["resolved_context"].get("filters", [])
    assert "large_battery" in filters, f"expected large_battery in filters, got {filters}"


def test_recent_30_cohort_forecast():
    """最近 30 天 cohort 预测锁单 → lock_forecast + last_30_days"""
    r = parse_context("最近 30 天 cohort 预测锁单")
    # lock_forecast has higher confidence, but cohort_forecast is also valid
    assert r["resolved_context"]["metric"] in ("lock_forecast", "cohort_forecast")
    tw = r["resolved_context"].get("time_window", "")
    assert "30" in tw, f"expected last_30_days, got {tw}"


def test_release_curve():
    """锁单释放曲线分析 → release_curve"""
    r = parse_context("锁单释放曲线分析")
    _check(r, "metric", "release_curve")


def test_voc_jtbd():
    """VOC 按 JTBD 主题分布 → voc_theme + jtbd_theme"""
    r = parse_context("VOC 按 JTBD 主题分布")
    _check(r, "metric", "voc_theme")
    _check(r, "group_by", "jtbd_theme")


def test_no_input():
    """空文本 → missing context"""
    r = parse_context("")
    assert "metric" in r["missing_context"]
    assert r["confidence"] == 0.0


def test_city_filter():
    """只看上海的数据 → 继承 previous_context 中的 metric/time_window，添加 city"""
    prev = {"metric": "lock_count", "time_window": "this_month", "group_by": "city", "limit": 10}
    r = parse_context("只看上海的数据", previous_context=prev)
    _check(r, "metric", "lock_count")
    _check(r, "time_window", "this_month")
    assert r["resolved_context"].get("city") == "上海", f"expected 上海, got {r['resolved_context'].get('city')}"


def test_inherited_fields_tracked():
    """继承的字段应在 inherited_context 中体现。"""
    prev = {"metric": "lock_count", "time_window": "yesterday", "series": "LS8", "group_by": "city"}
    r = parse_context("分车型看看", previous_context=prev)
    # '分车型' should set group_by=model, overriding
    _check(r, "metric", "lock_count")
    _check(r, "series", "LS8")
    assert r["resolved_context"].get("group_by") == "model"
    assert r["inherited_context"].get("metric") == "lock_count"
    assert r["inherited_context"].get("series") == "LS8"
