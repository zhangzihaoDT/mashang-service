"""域名/信源解析测试"""
import sys, yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_scripts.auto_launch.source_domain_resolver import SourceDomainResolver

# 用真实配置初始化
_cfg_path = Path(sys.path[0]) / "promptbuilders" / "auto_launch" / "configs" / "source_domains.yaml"
_config = yaml.safe_load(_cfg_path.read_text()) if _cfg_path.exists() else {}
resolver = SourceDomainResolver(_config)


def test_zeekrgroup_official():
    r = resolver.resolve("https://www.zeekrgroup.com/news", "极氪科技集团")
    assert r["source_type_guess"] == "official_website"
    assert r["source_tier_guess"] == "tier_1_official"
    print("[PASS] test_zeekrgroup_official")


def test_zeekr_dot_com_official():
    r = resolver.resolve("https://www.zeekr.com/model", "极氪")
    assert r["source_tier_guess"] == "tier_1_official"
    print("[PASS] test_zeekr_dot_com_official")


def test_official_social_weibo():
    r = resolver.resolve("https://m.weibo.cn/detail/123", "极氪Zeekr的微博", title="极氪Zeekr")
    assert r["source_type_guess"] == "official_social_account"
    assert r["source_tier_guess"] == "tier_1_official"
    print("[PASS] test_official_social_weibo")


def test_autohome_vertical_media():
    r = resolver.resolve("https://www.autohome.com.cn/news/123", "汽车之家")
    assert r["source_type_guess"] == "vertical_auto_media"
    assert r["source_tier_guess"] == "tier_3_industry_media"
    print("[PASS] test_autohome_vertical_media")


def test_dongchedi_vertical_media():
    r = resolver.resolve("https://www.dongchedi.com/article/123", "懂车帝")
    assert r["source_type_guess"] == "vertical_auto_media"
    print("[PASS] test_dongchedi_vertical_media")


def test_dealer_autohome():
    r = resolver.resolve("https://dealer.autohome.com.cn/123", "经销商")
    assert r["source_type_guess"] == "dealer_page"
    assert r["source_tier_guess"] == "tier_5_unverified"
    print("[PASS] test_dealer_autohome")


def test_dealer_yiche():
    r = resolver.resolve("https://dealer.yiche.com/123", "经销商")
    assert r["source_type_guess"] == "dealer_page"
    print("[PASS] test_dealer_yiche")


def test_toutiao_portal():
    r = resolver.resolve("https://m.toutiao.com/article/123", "今日头条")
    assert r["source_type_guess"] == "portal_or_aggregator"
    assert r["source_tier_guess"] == "tier_5_unverified"
    print("[PASS] test_toutiao_portal")


def test_qq_portal():
    r = resolver.resolve("https://new.qq.com/rain/a/123", "腾讯新闻")
    assert r["source_type_guess"] == "portal_or_aggregator"
    print("[PASS] test_qq_portal")


def test_unknown_domain():
    r = resolver.resolve("https://randomblog.com/article", "Unknown")
    assert r["source_type_guess"] == "unknown"
    assert r["source_tier_guess"] == "tier_5_unverified"
    print("[PASS] test_unknown_domain")


def test_immotors_official():
    r = resolver.resolve("https://www.immotors.com/news", "智己")
    assert r["source_tier_guess"] == "tier_1_official"
    print("[PASS] test_immotors_official")


def test_weibo_not_official():
    r = resolver.resolve("https://m.weibo.cn/detail/456", "普通用户", title="随便说说")
    assert r["source_type_guess"] == "social_platform"
    assert r["source_tier_guess"] == "tier_4_social_signal"
    print("[PASS] test_weibo_not_official")
