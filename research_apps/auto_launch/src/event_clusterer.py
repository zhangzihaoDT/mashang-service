"""Layer: Intelligence Utilities — 搜索结果 → 事件聚类"""
"""
event_clusterer.py — deterministic event-level clustering for normalized search results.

Input:  normalized_search_results.json (items[])
Output: event_clusters.json (clusters[] with aggregated source_items)
"""

import re
from datetime import datetime
from collections import defaultdict


# ── key factor extraction patterns ──────────────────

_MODEL_PATTERN = re.compile(r"\b(L[56789S]|LS[56789]|L7|L6|LS9\s*Hyper|LS9|LS8|LS7|LS6|L6)\b", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"(\d{4})[年/-]?(\d{1,2})[月/-]?(\d{1,2})?[日]?")
_DATE_PATTERN2 = re.compile(r"(\d{1,2})[月/.](\\d{1,2})?[日]?")
_NUMBER_PATTERN = re.compile(r"(\d+[\.\d]*(?:万|亿)?)|(\d+[\.\d]*(?=%))")
_ACTION_KEYWORDS = [
    "交付", "上市", "官宣", "权益", "限时", "OTA", "试驾", "门店",
    "争议", "维权", "联名信", "战报", "销量", "里程碑", "下线",
    "预售", "降价", "召回", "合作", "代言", "发布", "首发",
]


def _extract_models(text: str) -> list[str]:
    return list(set(_MODEL_PATTERN.findall(text)))


def _extract_numbers(text: str) -> list[str]:
    return [m.group(0) for m in _NUMBER_PATTERN.finditer(text) if m.group(0)]


def _extract_action_keywords(text: str) -> list[str]:
    found = []
    for kw in _ACTION_KEYWORDS:
        if kw in text:
            found.append(kw)
    return found


def _make_cluster_key(brand_key: str, models: list, dates: list, numbers: list, actions: list) -> str:
    parts = [brand_key]
    if models:
        parts.append("_".join(sorted(models)[:2]))
    if actions:
        parts.append("_".join(sorted(actions)[:2]))
    if numbers:
        parts.append("_".join(sorted(numbers)[:2]))
    if dates:
        parts.append("_".join(sorted(dates)[:2]))
    key = "_".join(parts)
    key = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "", key)[:80]
    return key or f"{brand_key}_cluster"


def cluster_items(items: list[dict], brand_key: str = "im") -> dict:
    """Cluster normalized search items by event key factors."""
    clusters: dict[str, dict] = {}

    for item in items:
        # Skip items not eligible for event clustering
        if not item.get("eligible_for_event_cluster", True):
            continue
        title = item.get("title", "") or ""
        snippet = item.get("snippet", "") or ""
        combined = f"{title} {snippet}"

        models = _extract_models(combined)
        numbers = _extract_numbers(combined)
        actions = _extract_action_keywords(combined)

        # Extract dates
        date_matches = _DATE_PATTERN.findall(combined)
        dates = [f"{m[0]}-{m[1]}" if not m[2] else f"{m[0]}-{m[1]}-{m[2]}" for m in date_matches]

        cluster_key = _make_cluster_key(brand_key, models, dates, numbers, actions)

        if cluster_key not in clusters:
            clusters[cluster_key] = {
                "event_cluster_id": cluster_key,
                "brand_key": brand_key,
                "event_type": None,  # will derive from best source
                "event_title": title[:100],
                "event_summary": "",
                "event_time": "",
                "models": models,
                "dates": dates,
                "numbers": numbers,
                "actions": actions,
                "source_items": [],
                "source_count": 0,
                "best_source_tier": "tier_5_unverified",
                "has_official_source": False,
                "has_authoritative_source": False,
                "has_dealer_source": False,
                "has_social_source": False,
                "time_window_status": "unknown",
                "best_publish_time": "",
            }

        c = clusters[cluster_key]
        # Update best title (prefer longer/tier_1)
        if len(title) > len(c["event_title"]):
            c["event_title"] = title

        # Merge source item
        tier = item.get("source_tier_guess", "tier_5_unverified")
        stype = item.get("source_type_guess", "")
        pub_time = (item.get("publish_time", "") or "")[:19]

        si = {
            "source_name": item.get("source_name", ""),
            "source_title": title,
            "source_url": item.get("url", ""),
            "source_publish_time": pub_time,
            "source_type": stype,
            "source_tier": tier,
            "snippet": (item.get("snippet", "") or "")[:200],
            "query_window_role": item.get("query_window_role", "discovery"),
            "is_out_of_window": item.get("is_out_of_window"),
            "time_window_status": item.get("time_window_status", "unknown"),
            "stage": item.get("stage", "discovery"),
            "is_official_direct": item.get("is_official_direct", False),
        }
        if si not in c["source_items"]:
            c["source_items"].append(si)

        # Update quality indicators
        c["source_count"] = len(c["source_items"])
        if "tier_1" in tier and c["best_source_tier"] != "tier_1_official":
            c["best_source_tier"] = "tier_1_official"
        elif "tier_3" in tier and c["best_source_tier"] not in ("tier_1_official",):
            c["best_source_tier"] = "tier_3_industry_media"
        elif "tier_2" in tier and c["best_source_tier"] not in ("tier_1_official", "tier_3_industry_media"):
            c["best_source_tier"] = tier

        if stype == "official_website" or stype == "official_social_account":
            c["has_official_source"] = True
        if stype == "dealer_page":
            c["has_dealer_source"] = True
        if stype == "social_platform":
            c["has_social_source"] = True
        if stype in ("authoritative_media", "vertical_auto_media", "tech_biz_media"):
            c["has_authoritative_source"] = True

        # Best publish time (earliest)
        if pub_time and (not c["best_publish_time"] or pub_time < c["best_publish_time"]):
            c["best_publish_time"] = pub_time
            c["event_time"] = pub_time[:10]

        # Time window status
        tws = item.get("time_window_status", "unknown")
        if tws == "in_window":
            c["time_window_status"] = "in_window"
        elif c["time_window_status"] != "in_window" and tws == "out_of_window":
            c["time_window_status"] = "out_of_window"

        # Event type from best source
        eids = item.get("event_type_ids", []) or item.get("matched_event_type_ids", []) or []
        if eids and not c["event_type"]:
            c["event_type"] = eids[0]

        # Summary (prefer tier_1 snippet)
        snippet_text = (item.get("snippet", "") or "")[:200]
        if snippet_text and (c["best_source_tier"] == "tier_1_official" or not c["event_summary"]):
            c["event_summary"] = snippet_text

    return {
        "clusters": list(clusters.values()),
        "cluster_count": len(clusters),
    }
