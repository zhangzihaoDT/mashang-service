"""search_budget_manager 测试"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.search_budget_manager import build_budget_plan, _infer_profile


def _make_intent(req, eids=None, mode="brand_watch"):
    return {
        "user_request": req, "monitor_date": "2026-07-02", "mode": mode,
        "targets": [{"brand": "极氪", "target_id": "zeekr"}],
        "event_scope": {"event_type_ids": eids or []},
        "intent_type": "open_ended_activity_scan" if not eids else "specific_event_scan",
    }


def test_open_scan_defaults_to_standard():
    i = _make_intent("看看极氪最近 7 天都有什么动作")
    bp = build_budget_plan(i)
    assert bp["profile"] == "standard_scan"
    assert bp["query_budget_per_target"] == 5
    print("[PASS] test_open_scan_defaults_to_standard")


def test_deep_scan_keyword():
    i = _make_intent("全面复盘极氪近期动作")
    bp = build_budget_plan(i)
    assert bp["profile"] == "deep_scan"
    assert bp["query_budget_per_target"] == 8
    print("[PASS] test_deep_scan_keyword")


def test_single_event_is_lite():
    i = _make_intent("看看极氪权益", eids=["benefit_adjustment", "official_price_change"])
    bp = build_budget_plan(i)
    assert bp["profile"] == "lite_scan"
    assert bp["query_budget_per_target"] == 3
    print("[PASS] test_single_event_is_lite")


def test_cli_profile_overrides():
    i = _make_intent("看看极氪最近 7 天都有什么动作")
    bp = build_budget_plan(i, cli_profile="deep_scan")
    assert bp["profile"] == "deep_scan"
    assert bp["query_budget_per_target"] == 8
    print("[PASS] test_cli_profile_overrides")


def test_lite_budget():
    i = _make_intent("看看极氪权益", eids=["benefit_adjustment"])
    bp = build_budget_plan(i)
    assert bp["query_budget_per_target"] == 3
    print("[PASS] test_lite_budget")


def test_standard_budget():
    i = _make_intent("看看极氪最近 7 天都有什么动作")
    bp = build_budget_plan(i)
    assert bp["query_budget_per_target"] == 5
    print("[PASS] test_standard_budget")


def test_deep_budget():
    i = _make_intent("全面复盘极氪近期动作")
    bp = build_budget_plan(i)
    assert bp["query_budget_per_target"] == 8
    print("[PASS] test_deep_budget")


def test_cache_default_enabled():
    i = _make_intent("看看极氪最近 7 天都有什么动作")
    bp = build_budget_plan(i)
    assert bp["cache"]["enabled"] is True
    print("[PASS] test_cache_default_enabled")


def test_cache_disabled():
    i = _make_intent("看看极氪最近 7 天都有什么动作")
    bp = build_budget_plan(i, disable_cache=True)
    assert bp["cache"]["enabled"] is False
    print("[PASS] test_cache_disabled")
