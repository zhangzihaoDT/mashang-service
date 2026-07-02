"""volc_search_query_builder 测试 v2 — staged + intent-aware + profile"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_scripts.auto_launch.search_intent_compiler import compile_intent
from research_scripts.auto_launch.search_task_config_builder import build_task_config
from research_scripts.auto_launch.search_budget_manager import build_budget_plan
from research_scripts.auto_launch.volc_search_query_builder import build_query_plan


def _query_count(plan):
    return sum(len(t.get("queries", [])) for t in plan.get("targets", []))


def test_standard_scan_5_queries():
    intent = compile_intent("看看极氪最近 7 天都有什么动作", "2026-07-02")
    config = build_task_config(intent)
    budget = build_budget_plan(intent)
    plan = build_query_plan(config, budget)
    assert _query_count(plan) == 5, f"Expected 5 for standard_scan, got {_query_count(plan)}"
    assert plan["profile"] == "standard_scan"
    print("[PASS] test_standard_scan_5_queries")


def test_lite_scan_3_queries():
    intent = compile_intent("看看极氪最近 7 天都有什么动作", "2026-07-02")
    config = build_task_config(intent)
    budget = build_budget_plan(intent, cli_profile="lite_scan")
    plan = build_query_plan(config, budget)
    assert _query_count(plan) == 3, f"Expected 3 for lite_scan, got {_query_count(plan)}"
    print("[PASS] test_lite_scan_3_queries")


def test_deep_scan_8_queries():
    intent = compile_intent("看看极氪最近 7 天都有什么动作", "2026-07-02")
    config = build_task_config(intent)
    budget = build_budget_plan(intent, cli_profile="deep_scan")
    plan = build_query_plan(config, budget)
    assert _query_count(plan) == 8, f"Expected 8 for deep_scan, got {_query_count(plan)}"
    print("[PASS] test_deep_scan_8_queries")


def test_every_query_has_stage():
    intent = compile_intent("看看极氪最近 7 天都有什么动作", "2026-07-02")
    config = build_task_config(intent)
    budget = build_budget_plan(intent)
    plan = build_query_plan(config, budget)
    for t in plan["targets"]:
        for q in t.get("queries", []):
            assert "stage" in q, f"Missing stage in {q['query']}"
    print("[PASS] test_every_query_has_stage")


def test_scout_refine_counts():
    intent = compile_intent("看看极氪最近 7 天都有什么动作", "2026-07-02")
    config = build_task_config(intent)
    budget = build_budget_plan(intent)
    plan = build_query_plan(config, budget)
    scouts = [q for t in plan["targets"] for q in t["queries"] if q.get("stage") == "scout"]
    refines = [q for t in plan["targets"] for q in t["queries"] if q.get("stage") == "refine"]
    assert len(scouts) == 3, f"Expected 3 scout, got {len(scouts)}"
    assert len(refines) == 2, f"Expected 2 refine, got {len(refines)}"
    print("[PASS] test_scout_refine_counts")


def test_price_intent_no_partnership():
    intent = compile_intent("看看极氪最近 7 天权益和价格有什么变化", "2026-07-02")
    config = build_task_config(intent)
    budget = build_budget_plan(intent)
    plan = build_query_plan(config, budget)
    all_queries = [q["query"] for t in plan["targets"] for q in t["queries"]]
    for q in all_queries:
        assert "联名" not in q, f"Price intent should not include partnership query: {q}"
        assert "高管" not in q
        assert "爆料" not in q
    print("[PASS] test_price_intent_no_partnership")


def test_sales_intent_focused():
    intent = compile_intent("看看极氪最近交付和销量表现", "2026-07-02")
    config = build_task_config(intent)
    budget = build_budget_plan(intent)
    plan = build_query_plan(config, budget)
    all_text = " ".join(q["query"] for t in plan["targets"] for q in t["queries"])
    assert "交付" in all_text or "销量" in all_text
    assert "联名" not in all_text
    print("[PASS] test_sales_intent_focused")


def test_official_only_source_focus():
    intent = compile_intent("只看官方，看看极氪最近有什么动作", "2026-07-02")
    config = build_task_config(intent)
    budget = build_budget_plan(intent)
    plan = build_query_plan(config, budget)
    for t in plan["targets"]:
        for q in t["queries"]:
            for sf in q.get("source_tier_focus", []):
                assert sf == "tier_1_official", f"Expected only tier_1_official, got {sf}"
    print("[PASS] test_official_only_source_focus")


def test_profile_in_plan():
    intent = compile_intent("看看极氪最近 7 天都有什么动作", "2026-07-02")
    config = build_task_config(intent)
    budget = build_budget_plan(intent, cli_profile="deep_scan")
    plan = build_query_plan(config, budget)
    assert plan.get("profile") == "deep_scan"
    print("[PASS] test_profile_in_plan")
