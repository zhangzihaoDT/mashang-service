"""Layer: Intelligence Utilities — 域名/信源识别"""
"""
source_domain_resolver.py — 域名/信源解析器。

基于 source_domains.yaml 和启发式规则，判断每条 item 的
source_type_guess 和 source_tier_guess。
"""

import sys, re
from pathlib import Path
from urllib.parse import urlparse

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent
PROJECT_ROOT = SERVICE_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml


def _load_domain_config() -> dict:
    path = SERVICE_ROOT / "configs" / "source_domains.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


class SourceDomainResolver:
    def __init__(self, config: dict = None):
        self.cfg = config or _load_domain_config()
        self._build_index()

    def _build_index(self):
        # official domains: flattened to set
        self._official_domains = set()
        for brand, domains in self.cfg.get("official_domains", {}).items():
            for d in domains:
                self._official_domains.add(d.lower())

        # vertical auto media
        self._vam_domains = set(self.cfg.get("vertical_auto_media_domains", []))

        # tech/biz media
        self._tech_biz = set(self.cfg.get("tech_biz_media_domains", []))

        # authoritative media
        self._auth_media = set(self.cfg.get("authoritative_media_domains", []))

        # portal/aggregator
        self._portal = set(self.cfg.get("portal_or_aggregator_domains", []))

        # social platforms
        self._social = set(self.cfg.get("social_platform_domains", []))

        # dealer prefixes
        self._dealer_prefixes = self.cfg.get("dealer_domain_prefixes", [])
        self._dealer_domain_patterns = self.cfg.get("dealer_domain_patterns", [])

        # official social accounts: brand → platform → [account names]
        self._off_social = self.cfg.get("official_social_accounts", {})

    def _path_prefix(self, url: str) -> str:
        """Extract path prefix for URL path-based rules."""
        try:
            parsed = urlparse(url)
            path = parsed.path or ""
            return path.lower()
        except Exception:
            return ""

    def resolve(self, url: str, source_name: str, title: str = "", snippet: str = "") -> dict:
        domain = self._extract_domain(url)
        subdomain = self._extract_subdomain(url)
        path = self._path_prefix(url)

        # 0a. immotors.com path-based rules
        if domain in ("immotors.com", "www.immotors.com"):
            if path.startswith("/app/community/"):
                return self._result("official_owned_platform", "tier_4_social_signal", domain,
                                    "domain matched official owned platform; author not verified")
            if path.startswith("/website/configurator/") or path.startswith("/website/vehicle_config/"):
                return self._result("official_product_page", "tier_1_official", domain,
                                    "domain matched official_domains; product/config page")
            if path.startswith("/website/news_detail/") or path.startswith("/website/news/"):
                return self._result("official_website", "tier_1_official", domain,
                                    "domain matched official_domains; news page")
            # default immotors.com → official
            return self._result("official_website", "tier_1_official", domain,
                                "domain matched official_domains")

        # 0b. m.immotors.com path-based rules
        if domain == "m.immotors.com":
            if path.startswith("/app/community/"):
                return self._result("official_owned_platform", "tier_4_social_signal", domain,
                                    "domain matched official owned platform; author not verified")
            return self._result("official_owned_platform", "tier_4_social_signal", domain,
                                "domain matched official owned platform; default tier_4")

        # 1. Official domain match (highest priority)
        if domain in self._official_domains:
            return self._result("official_website", "tier_1_official", domain,
                                f"domain matched official_domains")

        # 2. Official social account match (check source_name AND title)
        off_account = self._match_official_social(source_name, domain)
        if not off_account and title:
            off_account = self._match_official_social(title, domain)
        if off_account:
            return self._result("official_social_account", "tier_1_official", domain,
                                f"account name matched official_social_accounts.{off_account}")

        # 3. Dealer page (check prefix before full domain match)
        if self._is_dealer(subdomain, domain):
            return self._result("dealer_page", "tier_5_unverified", domain,
                                "subdomain/domain matched dealer pattern")

        # 4. Vertical auto media
        if domain in self._vam_domains or any(domain.endswith(f".{d}") for d in self._vam_domains if "." in d):
            return self._result("vertical_auto_media", "tier_3_industry_media", domain,
                                "domain matched vertical_auto_media_domains")

        # 5. Authoritative media
        if domain in self._auth_media:
            return self._result("authoritative_media", "tier_3_industry_media", domain,
                                "domain matched authoritative_media_domains")

        # 5b. Tech/biz media
        if domain in self._tech_biz:
            return self._result("tech_biz_media", "tier_3_industry_media", domain,
                                "domain matched tech_biz_media_domains")

        # 6. Portal / aggregator
        if domain in self._portal:
            return self._result("portal_or_aggregator", "tier_5_unverified", domain,
                                "domain matched portal_or_aggregator_domains; original source unknown")

        # 7. Social platform
        if domain in self._social:
            return self._result("social_platform", "tier_4_social_signal", domain,
                                "domain matched social_platform_domains")

        # 8. Fallback: heuristic check — only sets claim_source_hint, never upgrades tier
        combined = f"{source_name} {title} {snippet}".lower()
        claim_source_hint = None
        claim_source_hint_reason = None
        if any(kw in combined for kw in ["官网", "官方", "新闻中心", "品牌方", "据官方"]):
            claim_source_hint = "maybe_official"
            claim_source_hint_reason = "keyword heuristic found official keywords in text"
        if any(kw in combined for kw in ["销售朋友", "经销商", "门店优惠", "到店"]):
            claim_source_hint = "maybe_dealer"
            claim_source_hint_reason = "keyword heuristic found dealer keywords in text"
        if any(kw in combined for kw in ["论坛", "车友圈", "车友群", "社区"]):
            claim_source_hint = "maybe_forum"
            claim_source_hint_reason = "keyword heuristic found forum keywords in text"

        result = self._result("unknown", "tier_5_unverified", domain,
                              "no domain match; default unknown")
        if claim_source_hint:
            result["claim_source_hint"] = claim_source_hint
            result["claim_source_hint_reason"] = claim_source_hint_reason
        return result

    def _extract_domain(self, url: str) -> str:
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            # strip leading www.
            host = re.sub(r"^www\.", "", host)
            return host.lower()
        except Exception:
            return ""

    def _extract_subdomain(self, url: str) -> str:
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            return host.lower()
        except Exception:
            return ""

    def _is_dealer(self, subdomain: str, domain: str) -> bool:
        for prefix in self._dealer_prefixes:
            if subdomain.startswith(prefix.lower()):
                return True
        # pattern-based: dealer*.autohome.com.cn, dealer*.yiche.com etc.
        for pattern in self._dealer_domain_patterns:
            # pattern like "dealer.*.autohome.com.cn"
            parts = pattern.split(".*.")
            if len(parts) == 2:
                if parts[0] in subdomain and domain == parts[1]:
                    return True
        return False

    def _match_official_social(self, source_name: str, domain: str) -> str | None:
        combined = source_name.lower()
        # determine platform from domain
        platform = None
        if "weibo" in domain:
            platform = "weibo"
        elif "douyin" in domain:
            platform = "douyin"

        if not platform:
            return None

        for brand, accounts in self._off_social.items():
            accts = accounts.get(platform, [])
            for acct in accts:
                if acct.lower() in combined:
                    return brand
        return None

    def _result(self, stype: str, stier: str, domain: str, reason: str) -> dict:
        return {
            "domain": domain,
            "source_type_guess": stype,
            "source_tier_guess": stier,
            "source_resolution_reason": reason,
        }
