"""
event_candidate_gate.py — deterministic candidate gating for event clusters.

Input:  event_clusters.json
Output: brand_event_candidates.json, brand_discovery_signals.json,
        context_only.json, needs_review.json
"""

from datetime import datetime


def gate_clusters(clusters: list[dict], valid_event_types: set = None) -> dict:
    """
    Gate each cluster into one of four buckets based on deterministic rules.
    Returns dict with keys: candidates, discovery_signals, context_only, needs_review
    """
    if valid_event_types is None:
        valid_event_types = set()

    candidates = []
    discovery_signals = []
    context_only = []
    needs_review = []

    for cluster in clusters:
        reasons = []
        bucket = None

        # 1. Check time window
        tws = cluster.get("time_window_status", "unknown")
        if tws == "out_of_window":
            bucket = "context_only"
            reasons.append("time_window_out_of_window")

        # 2. Check if there's any publish time at all
        has_time = bool(cluster.get("best_publish_time"))
        if not has_time and bucket is None:
            bucket = "needs_review"
            reasons.append("no_publish_time")

        # 3. Check source tier quality
        best_tier = cluster.get("best_source_tier", "tier_5_unverified")
        has_official = cluster.get("has_official_source", False)
        has_auth = cluster.get("has_authoritative_source", False)
        has_dealer = cluster.get("has_dealer_source", False)
        has_social = cluster.get("has_social_source", False)
        source_count = cluster.get("source_count", 0)

        is_single_dealer = has_dealer and source_count <= 1 and not has_official and not has_auth
        is_single_social = has_social and source_count <= 1 and not has_official and not has_auth
        is_single_tier5 = best_tier == "tier_5_unverified" and source_count <= 1

        if bucket is None and (is_single_dealer or is_single_tier5):
            bucket = "discovery_signal"
            if is_single_dealer:
                reasons.append("single_dealer_source_no_official_confirmation")
            elif is_single_tier5:
                reasons.append("single_tier5_source_insufficient_confidence")

        # 4. Check event_type validity
        etype = cluster.get("event_type")
        if etype and valid_event_types and etype not in valid_event_types:
            if bucket is None:
                bucket = "needs_review"
                reasons.append(f"unknown_event_type:{etype}")

        # 5. Dealer special case: multiple cities can cross-validate
        if has_dealer and source_count >= 2 and bucket in ("discovery_signal", None):
            # Check if sources are from different cities (heuristic: different hostnames)
            hosts = set()
            for si in cluster.get("source_items", []):
                url = si.get("source_url", "")
                if url:
                    hosts.add(url.split("/")[2] if "//" in url else url[:30])
            if len(hosts) >= 2 and (has_official or has_auth):
                bucket = None  # override, let candidate check proceed
                reasons.append("cross_city_dealer_matches_with_official_media")

        # 6. Candidate check: in_window + has_time + tier_1/3 + has_facts
        if bucket is None:
            if tws == "in_window" and has_time and best_tier in ("tier_1_official", "tier_3_industry_media"):
                # Check for minimal event facts
                has_numbers = bool(cluster.get("numbers"))
                has_actions = bool(cluster.get("actions"))
                has_dates = bool(cluster.get("dates"))
                if has_numbers or has_actions or has_dates or has_official:
                    bucket = "candidate"
                    reasons.append("meets_candidate_gate")
                else:
                    bucket = "needs_review"
                    reasons.append("no_clear_event_facts")
            else:
                if bucket is None:
                    bucket = "discovery_signal"
                    reasons.append("not_meeting_candidate_threshold")

        # Build gated cluster
        gated = {
            "event_cluster_id": cluster["event_cluster_id"],
            "brand_key": cluster["brand_key"],
            "event_type": cluster.get("event_type"),
            "event_title": cluster.get("event_title", ""),
            "event_summary": cluster.get("event_summary", ""),
            "event_time": cluster.get("event_time", ""),
            "models": cluster.get("models", []),
            "numbers": cluster.get("numbers", []),
            "actions": cluster.get("actions", []),
            "confidence": "high" if bucket == "candidate" else ("medium" if bucket == "discovery_signal" else "low"),
            "time_window_status": tws,
            "best_source_tier": best_tier,
            "has_official_source": has_official,
            "has_authoritative_source": has_auth,
            "source_count": source_count,
            "candidate_gate_status": bucket,
            "candidate_gate_reasons": reasons,
            "source_items": cluster.get("source_items", []),
        }

        if bucket == "candidate":
            candidates.append(gated)
        elif bucket == "discovery_signal":
            discovery_signals.append(gated)
        elif bucket == "context_only":
            context_only.append(gated)
        else:
            needs_review.append(gated)

    return {
        "candidates": candidates,
        "discovery_signals": discovery_signals,
        "context_only": context_only,
        "needs_review": needs_review,
    }
