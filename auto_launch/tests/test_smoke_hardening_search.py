"""v1.0.3 Search Smoke Hardening 测试"""
import sys, json, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── 1. Semantic fingerprint dedupe ────────────────────────────────

from auto_launch.src.fact_store import _build_fingerprint, _is_delivery_event, _extract_period, _extract_core_numbers


def test_delivery_event_detection():
    assert _is_delivery_event("delivery_start") is True
    assert _is_delivery_event("sales_milestone") is True
    assert _is_delivery_event("交付数据") is True
    assert _is_delivery_event("销量") is True
    assert _is_delivery_event("预售") is False
    assert _is_delivery_event("权益调整") is False
    assert _is_delivery_event("technology_release") is False
    assert _is_delivery_event("") is False


def test_same_delivery_merged():
    """同一品牌、同一月份、同一数字的交付新闻应合并"""
    fp1 = _build_fingerprint("极氪", "", "delivery_start", "2026-07-09",
                             "同比激增111%!极氪6月交付35169台")
    fp2 = _build_fingerprint("极氪", "", "delivery_start", "2026-07-09",
                             "极氪6月交付35169辆，同比翻番!")
    assert fp1 == fp2, "同品牌同月份同数字的交付新闻应合并"


def test_different_period_not_merged():
    """不同月份的交付新闻不应合并"""
    fp1 = _build_fingerprint("极氪", "", "delivery_start", "2026-06-01",
                             "极氪6月交付35169台")
    fp2 = _build_fingerprint("极氪", "", "delivery_start", "2026-07-01",
                             "极氪7月交付40000台")
    assert fp1 != fp2, "不同月份不应合并"


def test_ota_not_merged_with_delivery():
    """OTA 版本更新不应与交付数据合并"""
    fp1 = _build_fingerprint("极氪", "", "technology_release", "2026-07-09",
                             "Zeekr Rolls Out OTA 7.2 Update")
    fp2 = _build_fingerprint("极氪", "", "delivery_start", "2026-07-09",
                             "极氪6月交付35169台")
    assert fp1 != fp2, "OTA 与交付不应合并"


def test_different_brands_not_merged():
    """不同品牌的交付不应合并"""
    fp1 = _build_fingerprint("极氪", "", "delivery_start", "2026-07-09",
                             "6月交付35169台")
    fp2 = _build_fingerprint("理想", "", "delivery_start", "2026-07-09",
                             "6月交付35169台")
    assert fp1 != fp2, "不同品牌不应合并"


def test_9x_presale_not_merged_with_7x_delivery():
    """9X 预售和 7X 交付不应合并"""
    fp1 = _build_fingerprint("极氪", "9X", "预售", "2026-07-08",
                             "极氪 9X 五座版开启预售")
    fp2 = _build_fingerprint("极氪", "7X", "开启交付", "2026-07-07",
                             "极氪 7X 开启交付")
    assert fp1 != fp2, "不同事件类型不应合并"


def test_ota_versions_not_merged():
    """OTA 7.2 / 5.6 / 6.5 不应被合并"""
    fp1 = _build_fingerprint("极氪", "", "technology_release", "", "Zeekr OTA 7.2 Update")
    fp2 = _build_fingerprint("极氪", "", "technology_release", "", "极氪001 OTA 5.6 推送")
    fp3 = _build_fingerprint("极氪", "", "technology_release", "", "极氪 OTA 6.5 更新")
    assert len({fp1, fp2, fp3}) == 3, "不同 OTA 版本不应合并"


def test_extract_period():
    assert _extract_period("2026-07-09", "") == "2026-07"
    assert _extract_period("", "极氪6月交付35169台") == "6月"
    assert _extract_period("", "") == ""


def test_extract_core_numbers():
    nums = _extract_core_numbers("极氪6月交付35169台，同比增长111%")
    assert "35169" in nums
    assert "111" not in nums  # < 3 digits


# ── 2. Brief event type groups ──────────────────────────────────

from auto_launch.src.brief_renderer import _group_by_event_type, generate_brief, _EVENT_TYPE_GROUPS


def test_delivery_start_in_delivery_group():
    """delivery_start 出现在交付/销量分组"""
    items = [{"brand": "极氪", "event_type": "delivery_start", "title": "t",
              "source_tier": "tier_3_industry_media", "seen_count": 1}]
    result = _group_by_event_type(items)
    group_names = [g[0] for g in result]
    assert "交付/销量" in group_names
    # Check group_by_event_type directly
    items = [{"brand": "极氪", "event_type": "delivery_start", "title": "t",
              "source_tier": "tier_3_industry_media", "seen_count": 1}]
    result = _group_by_event_type(items)
    group_names = [g[0] for g in result]
    assert "交付/销量" in group_names


def test_technology_release_in_tech_group():
    """technology_release 出现在产品/技术分组"""
    items = [{"brand": "极氪", "event_type": "technology_release", "title": "t",
              "source_tier": "tier_3_industry_media", "seen_count": 1}]
    result = _group_by_event_type(items)
    group_names = [g[0] for g in result]
    assert "产品/技术" in group_names


def test_channel_campaign_in_brand_group():
    """channel_campaign 出现在品牌/合作分组"""
    items = [{"brand": "极氪", "event_type": "channel_campaign", "title": "t",
              "source_tier": "tier_3_industry_media", "seen_count": 1}]
    result = _group_by_event_type(items)
    group_names = [g[0] for g in result]
    assert "品牌/合作" in group_names


def test_known_types_not_in_other():
    """已知事件类型不应落入'其他'分组"""
    known_types = ["交付数据", "交付", "开启交付", "delivery_start", "delivery_metric",
                   "technology_release", "ota_update", "channel_campaign", "benefit_adjustment",
                   "partnership", "brand_campaign", "executive_voice"]
    for et in known_types:
        items = [{"brand": "极氪", "event_type": et, "title": "t",
                  "source_tier": "tier_3_industry_media", "seen_count": 1}]
        result = _group_by_event_type(items)
        group_names = [g[0] for g in result]
        assert "其他" not in group_names, f"{et} 不应落入'其他'"


# ── 3. Source domain resolver subdomain coverage ────────────────

from auto_launch.src.source_domain_resolver import SourceDomainResolver


def test_yiche_subdomain_recognized():
    resolver = SourceDomainResolver()
    result = resolver.resolve("https://news.yiche.com/auto/article.html", "易车", "title")
    assert result["source_tier_guess"] in ("tier_3_industry_media",), f"易车应为 tier_3, got {result['source_tier_guess']}"
    assert "vertical_auto_media" in result["source_type_guess"]


def test_finance_sina_recognized():
    resolver = SourceDomainResolver()
    result = resolver.resolve("https://finance.sina.com.cn/auto/xxx.html", "新浪财经", "title")
    assert result["source_tier_guess"] in ("tier_3_industry_media",), f"新浪财经应为 tier_3"


def test_unknown_domain_still_tier5():
    resolver = SourceDomainResolver()
    result = resolver.resolve("https://some-random-blog.com/post", "自媒体", "title")
    assert result["source_tier_guess"] == "tier_5_unverified"


# ── 4. Query date fallback ──────────────────────────────────────

from auto_launch.src.fact_store import FactStore


def test_query_includes_recent_event_date(monkeypatch):
    """event_date 在窗口内但 last_seen 较旧时，应被包含"""
    import tempfile
    from datetime import datetime
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    store = FactStore(db_path)
    store.insert({
        "brand": "极氪", "model": "9X", "event_type": "预售",
        "event_date": datetime.now().strftime("%Y-%m-%d"),
        "title": "极氪9X预售", "source_tier": "tier_1_official",
    })
    results = store.query(days=1, limit=10)
    assert len(results) >= 1, "event_date=今天 应在 days=1 查询中返回"
    store.close()
    Path(db_path).unlink(missing_ok=True)


def test_query_excludes_old_dates():
    """event_date 和 last_seen 都超出窗口时不返回"""
    import tempfile
    from datetime import datetime, timedelta
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    store = FactStore(db_path)
    old_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    old_ts = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    # Insert with last_seen also set to old (simulate old fact not recently seen)
    store.insert({
        "brand": "极氪", "model": "9X", "event_type": "预售",
        "event_date": old_date,
        "title": "极氪9X预售", "source_tier": "tier_1_official",
    })
    # Manually override last_seen to simulate old fact
    store._cur.execute("UPDATE facts SET last_seen = ? WHERE brand = '极氪'", (old_ts,))
    store._conn.commit()
    results = store.query(days=7, limit=10)
    assert len(results) == 0, f"30 天前的事实不应在 days=7 中返回, got {len(results)}"
    store.close()
    Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
