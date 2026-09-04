"""source_auditor 防回归测试"""
import sys, json
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.source_auditor import (
    audit, render_markdown,
    _load_priority_brands, _load_ls8_targets,
    _gather_brand_facts, _gather_target_facts,
    _tier_label,
)


# ── 1. 不依赖 source_coverage_expectations.yaml ─────────────────────

def test_no_source_coverage_expectations():
    """确保不存在被删除的旧 config 文件"""
    path = Path(__file__).resolve().parents[2] / "auto_launch" / "configs" / "source_coverage_expectations.yaml"
    assert not path.exists(), "source_coverage_expectations.yaml 不得存在"


# ── 2. 从 priority_brand_watchlist.yaml 推导 ────────────────────────

def test_load_priority_brands():
    brands = _load_priority_brands()
    assert len(brands) >= 15, f"Expected >= 15 brands, got {len(brands)}"
    catalogs = [b["catalog"] for b in brands]
    assert "智己" in catalogs
    assert "理想" in catalogs
    assert "鸿蒙智行" in catalogs


def test_load_ls8_targets():
    targets = _load_ls8_targets()
    assert len(targets) >= 8, f"Expected >= 8 targets, got {len(targets)}"
    ids = [t["target_id"] for t in targets]
    assert "leapmotor_d19" in ids
    assert "aito_m7" in ids


# ── 3. catalog + sub_brand 聚合 ─────────────────────────────────────

def test_gather_brand_facts_aggregates_catalog_and_sub_brands():
    by_brand = defaultdict(list)
    by_brand["鸿蒙智行"].append({"brand": "鸿蒙智行", "source_tier": "tier_1_official"})
    by_brand["问界"].append({"brand": "问界", "source_tier": "tier_3_industry_media"})
    by_brand["智界"].append({"brand": "智界", "source_tier": "tier_4_social_signal"})

    entry = {"catalog": "鸿蒙智行", "sub_brands": [
        {"name": "问界"}, {"name": "智界"}, {"name": "享界"}, {"name": "尊界"}, {"name": "尚界"}
    ]}
    facts = _gather_brand_facts(entry, by_brand)
    assert len(facts) == 3


def test_harmony_catalog_coverage():
    """鸿蒙智行系列子品牌能正确归到 catalog 视角"""
    by_brand = defaultdict(list)
    by_brand["问界"].append({"brand": "问界", "source_tier": "tier_1_official", "title": "AITO M7", "event_type": "launch"})
    by_brand["智界"].append({"brand": "智界", "source_tier": "tier_1_official", "title": "智界 V9", "event_type": "launch"})
    by_brand["享界"].append({"brand": "享界", "source_tier": "tier_3_industry_media", "title": "享界 S9", "event_type": "launch"})
    by_brand["尊界"].append({"brand": "尊界", "source_tier": "tier_4_social_signal", "title": "尊界 S800", "event_type": "launch"})

    facts = []
    for items in by_brand.values():
        facts.extend(items)

    report = audit(facts, watchlist="priority")

    gaps = {ef["brand"]: ef["flag"] for ef in report["expected_flags"]}
    assert "expected_official_missing" not in gaps.get("鸿蒙智行", "")

    assert report["watchlist"] == "priority"


# ── 4. 输出 contract 保持不变 ──────────────────────────────────────

def test_audit_contract_keys():
    facts = [
        {"brand": "智己", "model": "LS6", "source_tier": "tier_1_official", "source_url": "https://immotors.com",
         "event_date": "2026-07-01", "title": "智己LS6上市", "event_type": "launch"},
        {"brand": "理想", "model": "L6", "source_tier": "tier_3_industry_media", "source_url": "https://autohome.com.cn",
         "event_date": "2026-07-01", "title": "理想L6报道", "event_type": "launch"},
        {"brand": "智己", "model": "LS8", "source_tier": "tier_1_official", "source_url": "https://immotors.com",
         "event_date": "", "title": "智己LS8配置", "event_type": "config_release"},
    ]
    report = audit(facts)

    assert report["total"] == 3
    assert report["brands"] == 2
    assert report["models"] == 3
    assert "brand_coverage" in report
    assert "event_type_coverage" in report
    assert "low_quality" in report
    assert "expected_flags" in report
    assert "suggestions" in report
    assert "watchlist" in report

    for bname, cov in report["brand_coverage"].items():
        assert "facts" in cov
        assert "official" in cov
        assert "auto_media" in cov
        assert "social" in cov
        assert "missing_url" in cov
        assert "official_rate" in cov

    for et, cov in report["event_type_coverage"].items():
        assert "facts" in cov
        assert "official_rate" in cov
        assert "media_rate" in cov
        assert "weak_source_count" in cov


def test_audit_empty_facts():
    report = audit([])
    assert report["total"] == 0
    assert "warnings" in report
    assert report["warnings"] == ["no facts"]


def test_audit_no_brand_facts():
    """facts 中 brand 字段缺失的处理"""
    facts = [
        {"source_tier": "tier_1_official", "source_url": "https://x.com", "event_date": "2026-07-01",
         "title": "no brand", "event_type": "launch"},
    ]
    report = audit(facts)
    assert report["total"] == 1
    assert report["brands"] == 0


# ── 5. ls8 watchlist ───────────────────────────────────────────────

def test_ls8_watchlist_audit():
    facts = [
        {"brand": "零跑", "model": "D19", "source_tier": "tier_1_official", "source_url": "https://leapmotor.cn",
         "event_date": "2026-07-01", "title": "零跑D19上市", "event_type": "launch"},
        {"brand": "理想", "model": "i6", "source_tier": "tier_3_industry_media", "source_url": "https://autohome.com.cn",
         "event_date": "2026-07-01", "title": "理想i6报道", "event_type": "launch"},
    ]
    report = audit(facts, watchlist="ls8")
    assert report["watchlist"] == "ls8"
    assert report["total"] == 2
    assert "brand_coverage" in report


def test_ls8_target_facts_gathering():
    by_brand = defaultdict(list)
    by_brand["零跑"].append({"brand": "零跑", "model": "D19", "source_tier": "tier_1_official"})
    by_brand["理想"].append({"brand": "理想", "model": "L6", "source_tier": "tier_1_official"})

    target = {"target_id": "leapmotor_d19", "brand": "零跑", "model": "D19",
              "brand_aliases": ["零跑", "Leapmotor"], "model_aliases": ["零跑D19", "Leapmotor D19"]}
    facts = _gather_target_facts(target, by_brand)
    assert len(facts) == 1


# ── 6. render_markdown 输出格式 ────────────────────────────────────

def test_render_markdown_empty():
    md = render_markdown({"total": 0, "warnings": ["no facts"]})
    assert "无数据" in md


def test_render_markdown_has_sections():
    facts = [
        {"brand": "智己", "model": "LS6", "source_tier": "tier_1_official", "source_url": "https://immotors.com",
         "event_date": "2026-07-01", "title": "智己LS6上市", "event_type": "launch"},
    ]
    report = audit(facts)
    md = render_markdown(report)
    assert "Source Coverage Audit" in md
    assert "Per-Brand Coverage" in md
    assert "Per-Event-Type Coverage" in md
    assert "Low Quality Facts" in md or "Suggestions" in md


# ── 7. missing_url / missing_event_date / weak_source ──────────────

def test_audit_detects_missing_fields():
    facts = [
        {"brand": "智己", "source_tier": "tier_4_social_signal", "event_date": "2026-07-01", "title": "t1", "event_type": "launch"},
        {"brand": "理想", "source_tier": "tier_5_unverified", "source_url": "https://x.com", "title": "t2", "event_type": "launch"},
    ]
    report = audit(facts)
    assert report["missing_url"] == 1
    assert report["missing_event_date"] == 1
    assert report["weak_count"] >= 1


# ── 8. tier_label mapping ──────────────────────────────────────────

def test_tier_label():
    assert _tier_label("tier_1_official") == "official"
    assert _tier_label("tier_3_industry_media") == "auto_media"
    assert _tier_label("tier_4_social_signal") == "social"
    assert _tier_label("tier_5_unverified") == "weak"
    assert _tier_label("") == "unknown"
    assert _tier_label("tier_2_authoritative") == "authoritative"


if __name__ == "__main__":
    test_no_source_coverage_expectations()
    test_load_priority_brands()
    test_load_ls8_targets()
    test_gather_brand_facts_aggregates_catalog_and_sub_brands()
    test_harmony_catalog_coverage()
    test_audit_contract_keys()
    test_audit_empty_facts()
    test_audit_no_brand_facts()
    test_ls8_watchlist_audit()
    test_ls8_target_facts_gathering()
    test_render_markdown_empty()
    test_render_markdown_has_sections()
    test_audit_detects_missing_fields()
    test_tier_label()
    print("\n✅ 所有 source_auditor 测试通过")
