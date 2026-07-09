"""
normalize_search_results 测试 — source tier guess、URL 去重、run_mode、audit 增强
"""

import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.normalize_search_results import (
    _canonicalize_url, normalize_results, build_audit
)

_SAMPLE_QUERY_PLAN = {
    "mode": "brand_watch",
    "monitor_date": "2026-07-02",
    "targets": [
        {
            "target_id": "zeekr",
            "brand": "极氪",
            "queries": [
                {"query": "极氪 最近7天 动作 消息", "event_type_ids": [],
                 "source_tier_focus": ["tier_1_official"], "query_role": "overview_discovery"},
                {"query": "极氪 权益 价格 最近7天", "event_type_ids": ["benefit_adjustment", "official_price_change"],
                 "source_tier_focus": ["tier_1_official"], "query_role": "specific_discovery"},
            ]
        }
    ]
}


def _mock_raw(query_a, query_b, same_url=False):
    url_b = "https://example.com/1" if same_url else "https://example.com/2"
    return [
        {"query": query_a, "status": "success", "result_count": 1,
         "results": [{"title": "A1", "url": "https://example.com/1", "source": "汽车之家", "publish_time": "2026-07-01"}]},
        {"query": query_b, "status": "success", "result_count": 1,
         "results": [{"title": "B1", "url": url_b, "source": "懂车帝", "publish_time": "2026-07-01"}]},
    ]


class TestSourceGuess:
    # 使用 SourceDomainResolver 替代旧的 _guess_source
    def _resolve(self, url, source="", title="", snippet=""):
        from auto_launch.src.source_domain_resolver import SourceDomainResolver
        return SourceDomainResolver().resolve(url, source, title, snippet)

    def test_autohome_is_tier3(self):
        r = self._resolve("https://www.autohome.com.cn/1", "汽车之家")
        assert r["source_tier_guess"] == "tier_3_industry_media"
        assert r["source_type_guess"] == "vertical_auto_media"

    def test_dongchedi_is_tier3(self):
        r = self._resolve("https://www.dongchedi.com/1", "懂车帝")
        assert r["source_tier_guess"] == "tier_3_industry_media"

    def test_xiaohongshu_is_tier4(self):
        r = self._resolve("https://www.xiaohongshu.com/1", "小红书")
        assert r["source_tier_guess"] == "tier_4_social_signal"

    def test_dealer_is_tier5(self):
        r = self._resolve("https://dealer.autohome.com.cn/1", "经销商")
        assert r["source_tier_guess"] == "tier_5_unverified"

    def test_unknown_falls_to_tier5(self):
        r = self._resolve("https://random.com/1", "Unknown")
        assert r["source_tier_guess"] == "tier_5_unverified"
        assert r["source_type_guess"] == "unknown"

    def test_zeekrgroup_official(self):
        r = self._resolve("https://www.zeekrgroup.com/news", "极氪科技集团")
        assert r["source_tier_guess"] == "tier_1_official"
        assert r["source_type_guess"] == "official_website"


class TestUrlDedupe:
    def test_different_urls_not_deduped(self):
        raw = _mock_raw("Q1", "Q2", same_url=False)
        result = normalize_results(raw, _SAMPLE_QUERY_PLAN)
        assert result["total"] == 2, f"Expected 2 items, got {result['total']}"

    def test_same_url_is_deduped(self):
        raw = _mock_raw("Q1", "Q2", same_url=True)
        result = normalize_results(raw, _SAMPLE_QUERY_PLAN)
        assert result["total"] == 1, f"Expected 1 item, got {result['total']}"

    def test_deduped_item_has_matched_queries(self):
        raw = _mock_raw("极氪 最近7天 动作 消息", "极氪 权益 价格 最近7天", same_url=True)
        result = normalize_results(raw, _SAMPLE_QUERY_PLAN)
        item = result["items"][0]
        assert item["dedupe_hit_count"] == 2, f"Expected hit_count=2, got {item['dedupe_hit_count']}"
        assert len(item["matched_queries"]) == 2
        assert len(item["matched_event_type_ids"]) >= 2
        assert "benefit_adjustment" in item["matched_event_type_ids"]

    def test_dedupe_stats_in_normalized(self):
        raw = _mock_raw("Q1", "Q2", same_url=True)
        result = normalize_results(raw, _SAMPLE_QUERY_PLAN)
        assert result["dedupe"]["raw_item_count"] == 2
        assert result["dedupe"]["normalized_item_count"] == 1


class TestCanonicalUrl:
    def test_remove_fragment(self):
        assert _canonicalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_remove_utm(self):
        url = "https://example.com/page?utm_source=google&id=123"
        result = _canonicalize_url(url)
        assert "utm_source" not in result
        assert "id=123" in result


class TestRunMode:
    def test_mock_run_mode_in_normalized(self):
        raw = _mock_raw("Q1", "Q2")
        result = normalize_results(raw, _SAMPLE_QUERY_PLAN, run_mode="mock")
        assert result["run_mode"] == "mock"
        assert result["is_mock"] is True

    def test_live_run_mode_in_normalized(self):
        raw = _mock_raw("Q1", "Q2")
        result = normalize_results(raw, _SAMPLE_QUERY_PLAN, run_mode="live")
        assert result["run_mode"] == "live"
        assert result["is_mock"] is False


class TestTimeWindowInAudit:
    def test_audit_has_time_window_quality(self):
        raw = [{"query": "Q1", "status": "success", "result_count": 1,
                "results": [{"title": "A", "url": "https://example.com/a",
                             "source": "汽车之家", "publish_time": "2026-07-01T10:00:00+08:00"}]}]
        qp = {"mode": "brand_watch", "monitor_date": "2026-07-02",
              "targets": [{"target_id": "zeekr", "brand": "极氪",
                           "queries": [{"query": "Q1", "event_type_ids": [],
                                        "source_tier_focus": [], "query_role": "specific_discovery"}]}],
              "time_window": {"start_date": "2026-06-25", "end_date": "2026-07-02"}}
        norm = __import__('sys').path and None
        from auto_launch.src.normalize_search_results import normalize_results, build_audit
        norm = normalize_results(raw, qp)
        audit = build_audit("test", "2026-07-02", "brand_watch", qp, raw, norm)
        assert "time_window_quality" in audit
        assert audit["time_window_quality"]["in_window_count"] >= 1
        assert "event_extraction_readiness" in audit
        assert "source_resolution_quality" in audit
        print("[PASS] test_audit_has_time_window_quality")


class TestAuditEnhancement:
    def test_audit_has_dedupe_stats(self):
        raw = _mock_raw("Q1", "Q2", same_url=True)
        norm = normalize_results(raw, _SAMPLE_QUERY_PLAN)
        audit = build_audit("test", "2026-07-02", "brand_watch", _SAMPLE_QUERY_PLAN, raw, norm)
        assert "dedupe" in audit
        assert audit["dedupe"]["raw_item_count"] == 2
        assert audit["dedupe"]["normalized_item_count"] == 1
        assert audit["dedupe"]["dedupe_ratio"] > 0

    def test_audit_has_source_quality(self):
        raw = _mock_raw("Q1", "Q2")
        norm = normalize_results(raw, _SAMPLE_QUERY_PLAN)
        audit = build_audit("test", "2026-07-02", "brand_watch", _SAMPLE_QUERY_PLAN, raw, norm)
        assert "source_quality" in audit
        assert "tier_3_industry_media_count" in audit["source_quality"]

    def test_audit_has_run_mode(self):
        raw = _mock_raw("Q1", "Q2")
        norm = normalize_results(raw, _SAMPLE_QUERY_PLAN, run_mode="mock")
        audit = build_audit("test", "2026-07-02", "brand_watch", _SAMPLE_QUERY_PLAN, raw, norm, run_mode="mock")
        assert audit["run_mode"] == "mock"
        assert audit["is_mock"] is True

    def test_mock_warning_in_audit(self):
        raw = _mock_raw("Q1", "Q2")
        norm = normalize_results(raw, _SAMPLE_QUERY_PLAN, run_mode="mock")
        audit = build_audit("test", "2026-07-02", "brand_watch", _SAMPLE_QUERY_PLAN, raw, norm, run_mode="mock")
        assert "mock_warning" in audit

    def test_no_mock_warning_for_live(self):
        raw = _mock_raw("Q1", "Q2")
        norm = normalize_results(raw, _SAMPLE_QUERY_PLAN, run_mode="live")
        audit = build_audit("test", "2026-07-02", "brand_watch", _SAMPLE_QUERY_PLAN, raw, norm, run_mode="live")
        assert "mock_warning" not in audit
