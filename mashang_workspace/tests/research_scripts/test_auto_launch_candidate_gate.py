"""event_candidate_gate tests — confirmed window filter + path-based source rules"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_scripts.auto_launch.event_candidate_gate import gate_clusters
from research_scripts.auto_launch.source_domain_resolver import SourceDomainResolver

resolver = SourceDomainResolver()


def _cluster(items, best_tier="tier_3_industry_media", tws="in_window", has_official=False):
    return {
        "event_cluster_id": "test_cluster", "brand_key": "im",
        "event_type": "delivery_start", "event_title": "Test Event",
        "event_time": "2026-07-01", "best_publish_time": "2026-07-01T10:00:00+08:00",
        "best_source_tier": best_tier,
        "time_window_status": tws, "has_official_source": has_official,
        "has_authoritative_source": best_tier in ("tier_1_official", "tier_3_industry_media"),
        "has_dealer_source": False, "has_social_source": False,
        "source_count": len(items), "source_items": items,
        "numbers": ["40087"], "actions": ["交付"], "dates": ["2026-07-01"],
    }


def _si(query_window_role="confirmed", is_out_of_window=False, pub_time="2026-07-01T10:00:00+08:00",
         tier="tier_3_industry_media"):
    tws = "out_of_window" if is_out_of_window else "in_window"
    return {"source_name": "测试", "source_title": "Test", "source_url": "https://example.com",
            "source_publish_time": pub_time, "source_type": "vertical_auto_media",
            "source_tier": tier, "query_window_role": query_window_role,
            "is_out_of_window": is_out_of_window, "time_window_status": tws,
            "stage": "official_direct" if query_window_role == "confirmed" else "discovery",
            "is_official_direct": query_window_role == "confirmed"}


def test_confirmed_out_of_window_goes_context():
    cluster = _cluster([_si(query_window_role="confirmed", is_out_of_window=True)], tws="out_of_window")
    gated = gate_clusters([cluster])
    assert len(gated["context_only"]) == 1
    assert len(gated["candidates"]) == 0
    reasons = gated["context_only"][0]["candidate_gate_reasons"]
    assert any("confirmed_result_out_of_window" in r for r in reasons)
    print("[PASS] test_confirmed_out_of_window_goes_context")


def test_confirmed_in_window_can_candidate():
    cluster = _cluster([_si(query_window_role="confirmed", is_out_of_window=False)])
    gated = gate_clusters([cluster])
    assert len(gated["candidates"]) == 1
    print("[PASS] test_confirmed_in_window_can_candidate")


def test_discovery_out_of_window_goes_context():
    cluster = _cluster([_si(query_window_role="discovery", is_out_of_window=True)], tws="out_of_window")
    gated = gate_clusters([cluster])
    assert len(gated["context_only"]) == 1
    print("[PASS] test_discovery_out_of_window_goes_context")


def test_tier5_single_not_candidate():
    cluster = _cluster([_si(tier="tier_5_unverified")], best_tier="tier_5_unverified")
    gated = gate_clusters([cluster])
    assert len(gated["candidates"]) == 0
    print("[PASS] test_tier5_single_not_candidate")


def test_tier3_in_window_can_candidate():
    cluster = _cluster([_si(tier="tier_3_industry_media")], best_tier="tier_3_industry_media")
    gated = gate_clusters([cluster])
    assert len(gated["candidates"]) == 1
    print("[PASS] test_tier3_in_window_can_candidate")


def test_immotors_news_tier1():
    r = resolver.resolve("https://www.immotors.com/website/news_detail/220", "智己")
    assert r["source_tier_guess"] == "tier_1_official"
    assert r["source_type_guess"] == "official_website"
    print("[PASS] test_immotors_news_tier1")


def test_immotors_community_not_tier1():
    r = resolver.resolve("https://m.immotors.com/app/community/content?id=123", "智己")
    assert r["source_type_guess"] == "official_owned_platform"
    assert r["source_tier_guess"] != "tier_1_official"
    print("[PASS] test_immotors_community_not_tier1")


def test_ifeng_never_tier1():
    r = resolver.resolve("https://news.ifeng.com/c/8j2k", "凤凰网", title="智己官方宣布")
    assert r["source_tier_guess"] != "tier_1_official"
    print("[PASS] test_ifeng_never_tier1")


def test_official_direct_out_of_window_routed():
    """stage=official_direct + out_of_window → routing_bucket=context_only (via normalize)"""
    from research_scripts.auto_launch.normalize_search_results import normalize_results
    qp = {"mode": "brand_watch", "time_window": {"start_date": "2026-06-25", "end_date": "2026-07-02"},
          "targets": [{"target_id": "im", "brand": "智己",
                       "queries": [{"query": "test", "event_type_ids": [], "source_tier_focus": [],
                                     "query_role": "confirmed", "query_window_role": "confirmed",
                                     "query_window_hours": 24, "stage": "official_direct",
                                     "is_official_direct": True, "official_domain_target": "immotors.com"}]}]}
    raw = [{"query": "test", "status": "success", "result_count": 1,
            "results": [{"title": "历史新闻", "url": "https://immotors.com/old",
                          "source": "智己", "publish_time": "2023-01-01T00:00:00+08:00"}]}]
    norm = normalize_results(raw, qp)
    items = norm["items"]
    # 2023 is out of 24h window
    assert len(items) > 0
    for item in items:
        assert item["routing_bucket"] == "context_only", f"Expected context_only, got {item.get('routing_bucket')}"
    print("[PASS] test_official_direct_out_of_window_routed")


def test_discovery_in_window_eligible():
    """discovery + in_window → eligible_for_event_cluster=True"""
    from research_scripts.auto_launch.normalize_search_results import normalize_results
    qp = {"mode": "brand_watch", "time_window": {"start_date": "2026-06-25", "end_date": "2026-07-02"},
          "targets": [{"target_id": "im", "brand": "智己",
                       "queries": [{"query": "test", "event_type_ids": [], "source_tier_focus": [],
                                     "query_role": "discovery", "query_window_role": "discovery",
                                     "query_window_days": 7, "stage": "scout",
                                     "is_official_direct": False}]}]}
    raw = [{"query": "test", "status": "success", "result_count": 1,
            "results": [{"title": "今日新闻", "url": "https://example.com/news",
                          "source": "汽车之家", "publish_time": "2026-07-01T10:00:00+08:00"}]}]
    norm = normalize_results(raw, qp)
    for item in norm["items"]:
        assert item.get("eligible_for_event_cluster") is not False
    print("[PASS] test_discovery_in_window_eligible")

