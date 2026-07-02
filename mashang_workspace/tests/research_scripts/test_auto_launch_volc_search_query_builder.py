"""volc_search_query_builder 测试"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_scripts.auto_launch.search_intent_compiler import compile_intent
from research_scripts.auto_launch.search_task_config_builder import build_task_config
from research_scripts.auto_launch.volc_search_query_builder import build_query_plan


def test_query_plan_budget_respected():
    """query plan 的 query 数量不超过 budget"""
    intent = compile_intent("看看极氪最近 7 天都有什么动作", "2026-07-02")
    config = build_task_config(intent)
    plan = build_query_plan(config)
    budget = config.get("query_budget", {}).get("query_budget_per_target", 8)
    for t in plan["targets"]:
        assert len(t["queries"]) <= budget, f"Expected <= {budget} queries, got {len(t['queries'])}"
    print("[PASS] test_query_plan_budget_respected")


def test_every_query_has_required_fields():
    """每条 query 都必须包含 query/event_type_ids/source_tier_focus/purpose"""
    intent = compile_intent("看看问界 M7 最近 7 天权益和价格有什么变化", "2026-07-02")
    config = build_task_config(intent)
    plan = build_query_plan(config)
    for t in plan["targets"]:
        for q in t.get("queries", []):
            assert "query" in q, f"Missing 'query' in {q}"
            assert "event_type_ids" in q, f"Missing 'event_type_ids' in {q}"
            assert "source_tier_focus" in q, f"Missing 'source_tier_focus' in {q}"
            assert "purpose" in q, f"Missing 'purpose' in {q}"
    print("[PASS] test_every_query_has_required_fields")


def test_brand_watch_queries():
    """brand_watch 的 query 应覆盖多类事件"""
    intent = compile_intent("看看极氪最近 7 天都有什么动作", "2026-07-02")
    config = build_task_config(intent)
    plan = build_query_plan(config)
    assert plan["mode"] == "brand_watch"
    for t in plan["targets"]:
        assert len(t["queries"]) > 1, "brand_watch should have multiple queries covering different event types"
    print("[PASS] test_brand_watch_queries")


def test_model_watch_queries():
    """model_watch 的 query 应包含车型名"""
    intent = compile_intent("看看理想 i6 最近有没有价格和权益变化", "2026-07-02")
    config = build_task_config(intent)
    plan = build_query_plan(config)
    assert plan["mode"] == "model_watch"
    for t in plan["targets"]:
        for q in t.get("queries", []):
            assert "i6" in q["query"] or "理想" in q["query"], f"Query should contain model name: {q['query']}"
    print("[PASS] test_model_watch_queries")


if __name__ == "__main__":
    test_query_plan_budget_respected()
    test_every_query_has_required_fields()
    test_brand_watch_queries()
    test_model_watch_queries()
    print("\n✅ 所有 query_builder 测试通过")
