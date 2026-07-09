"""
search_budget_manager.py — 根据 search_intent 和配置生成 search_budget_plan。

用法:
  python search_budget_manager.py --intent outputs/search_intent.json
"""

import json, sys, re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent
PROJECT_ROOT = SERVICE_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml


def _load_search_config():
    path = SERVICE_ROOT / "configs" / "volc_search.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _infer_profile(intent: dict, cli_profile: str = None) -> str:
    if cli_profile:
        return cli_profile
    req = intent.get("user_request", "")
    event_ids = intent.get("event_scope", {}).get("event_type_ids", [])
    mode = intent.get("mode", "brand_watch")

    # deep scan keywords
    if any(kw in req for kw in ["深入", "全面", "复盘", "详细", "deep"]):
        return "deep_scan"

    # single event type (non-empty) → lite
    if len(event_ids) <= 2 and len(event_ids) > 0 and mode == "brand_watch":
        return "lite_scan"

    return "standard_scan"


def build_budget_plan(intent: dict, cli_profile: str = None,
                       cli_max_queries: int = None, cli_result_limit: int = None,
                       refresh: bool = False, disable_cache: bool = False,
                       cli_stage: str = None) -> dict:
    config = _load_search_config()
    profile_name = _infer_profile(intent, cli_profile)
    profile = config.get("query_profiles", {}).get(profile_name, config.get("query_profiles", {}).get("standard_scan", {}))

    cache_cfg = config.get("cache", {})
    budget = {
        "task_name": "auto_launch_search_budget_plan",
        "mode": intent.get("mode", "brand_watch"),
        "monitor_date": intent.get("monitor_date", ""),
        "user_request": intent.get("user_request", ""),
        "profile": profile_name,
        "target_count": len(intent.get("targets", [])),
        "query_budget_per_target": cli_max_queries or profile.get("query_budget_per_target", 5),
        "result_limit_per_query": cli_result_limit or profile.get("result_limit_per_query", 8),
        "allow_refine": profile.get("allow_refine", False),
        "scout_query_count": profile.get("scout_query_count", 3),
        "refine_query_budget": profile.get("refine_query_budget", 2),
        "stage": cli_stage or "all",
        "cache": {
            "enabled": not disable_cache and cache_cfg.get("enabled", True),
            "ttl_hours": cache_cfg.get("ttl_hours", 24),
            "refresh": refresh,
            "root_dir": str(SERVICE_ROOT / "outputs" / "search_cache"),
        },
        "budget_reason": _budget_reason(intent, profile_name),
    }
    return budget


def _budget_reason(intent: dict, profile: str) -> str:
    req = intent.get("user_request", "")
    if profile == "lite_scan":
        return "single event type or daily watch uses lite_scan"
    if profile == "deep_scan":
        return "user requested deep/comprehensive scan"
    return f"open ended {intent.get('mode', 'brand')} activity scan uses {profile} by default"
