"""Layer: Search Pipeline — 查询计划生成（staged）"""
"""
volc_search_query_builder.py — 根据 search_task_config + budget_plan 生成 staged query plan。
"""

import json, sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent
PROJECT_ROOT = SERVICE_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml


def _load_search_templates():
    path = SERVICE_ROOT / "configs" / "volc_search.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _select_templates(intent_event_ids: list[str], config: dict) -> list[dict]:
    """根据 intent event_type_ids 选择匹配的模板集"""
    req = ""  # not used here, caller provides intent
    templates = config.get("search_templates", {})

    # intent-specific mappings
    price_kw = {"official_price_change", "benefit_adjustment"}
    sales_kw = {"delivery_start", "order_milestone", "sales_milestone"}
    rumor_kw = {"rumor_or_leak"}
    official_kw = set()

    eids = set(intent_event_ids)

    if eids and eids == official_kw:
        return templates.get("intent_mappings", {}).get("official_only", templates.get("brand_scout", [])[:1])

    if eids and eids.issubset(price_kw):
        return templates.get("intent_mappings", {}).get("price_rights", templates.get("event_specific", []))

    if eids and eids.issubset(sales_kw):
        return templates.get("intent_mappings", {}).get("sales_delivery", templates.get("event_specific", []))

    if eids and eids.issubset(rumor_kw):
        return templates.get("intent_mappings", {}).get("dealer_rumor", templates.get("event_specific", []))

    return None  # use default profile-based selection


def build_query_plan(task_config: dict, budget_plan: dict = None, output_path: str = None):
    config = _load_search_templates()
    mode = task_config["mode"]
    time_window = task_config["time_window"]
    intent_event_ids = task_config.get("event_type_ids", [])
    source_strategy = task_config.get("source_strategy", {})

    # official_only override: if authoritative media disabled, force all queries to tier_1
    _official_only_mode = source_strategy.get("official_first") and not source_strategy.get("include_authoritative_media", True)
    config = _load_search_templates()
    mode = task_config["mode"]
    time_window = task_config["time_window"]
    intent_event_ids = task_config.get("event_type_ids", [])
    source_strategy = task_config.get("source_strategy", {})

    bp = budget_plan or {}
    profile_name = bp.get("profile", "standard_scan")
    budget = bp.get("query_budget_per_target", 5)
    result_limit = bp.get("result_limit_per_query", 8)
    allow_refine = bp.get("allow_refine", True)
    scout_count = bp.get("scout_query_count", 3)
    refine_budget = bp.get("refine_query_budget", 2)
    run_stage = bp.get("stage", "all")
    tw = time_window
    days = tw.get("days", 7)

    templates_config = config.get("search_templates", {})

    targets = []
    for t in task_config.get("targets", []):
        brand = t["brand"]
        display = brand

        # intent-specific templates
        intent_templates = _select_templates(intent_event_ids, config)

        queries = []

        if intent_templates is not None:
            # intent-matched templates override profile
            for tmpl in intent_templates:
                if len(queries) >= budget:
                    break
                pattern = tmpl["pattern"]
                q_text = pattern.replace("{brand}", brand).replace("{target}", display).replace("{days}", str(days))
                source_focus = _infer_source_focus(tmpl.get("event_focus", []), source_strategy)
                if _official_only_mode:
                    source_focus = ["tier_1_official"]
                query_role_val = tmpl.get("query_role", "specific_discovery")
                query_window_role = "confirmed" if query_role_val == "confirmed" else "discovery"
                queries.append({
                    "query": q_text,
                    "stage": tmpl.get("stage", "scout"),
                    "query_role": query_role_val,
                    "query_window_role": query_window_role,
                    "event_type_ids": tmpl.get("event_focus", []),
                    "source_tier_focus": source_focus,
                    "purpose": f"intent-matched: {tmpl.get('event_focus', ['general'])}",
                })

        else:
            # profile-based: scout first
            scout_templates = templates_config.get("brand_scout", [])
            actual_scout_count = budget_plan.get("scout_query_count", scout_count) if budget_plan else scout_count
            for tmpl in scout_templates[:actual_scout_count]:
                if len(queries) >= budget:
                    break
                q_text = tmpl["pattern"].replace("{brand}", brand).replace("{days}", str(days))
                source_focus = _infer_source_focus(tmpl.get("event_focus", []), source_strategy)
                if _official_only_mode:
                    source_focus = ["tier_1_official"]
                qr = tmpl.get("query_role", "overview_discovery")
                queries.append({
                    "query": q_text,
                    "stage": "scout",
                    "query_role": qr,
                    "query_window_role": "discovery",
                    "event_type_ids": tmpl.get("event_focus", []),
                    "source_tier_focus": source_focus,
                    "purpose": tmpl.get("purpose", f"scout: {tmpl.get('event_focus', ['general'])}"),
                })

            # refine (if allowed and stage != scout)
            if allow_refine and run_stage in ("all", "refine"):
                refine_templates = templates_config.get("brand_refine", [])
                if profile_name == "deep_scan":
                    refine_templates = refine_templates + templates_config.get("brand_deep", [])
                for tmpl in refine_templates[:refine_budget]:
                    if len(queries) >= budget:
                        break
                    q_text = tmpl["pattern"].replace("{brand}", brand).replace("{days}", str(days))
                    source_focus = _infer_source_focus(tmpl.get("event_focus", []), source_strategy)
                    if _official_only_mode:
                        source_focus = ["tier_1_official"]
                    qr = tmpl.get("query_role", "specific_discovery")
                    queries.append({
                        "query": q_text,
                        "stage": "refine",
                        "query_role": qr,
                        "query_window_role": "discovery",
                        "event_type_ids": tmpl.get("event_focus", []),
                        "source_tier_focus": source_focus,
                        "purpose": tmpl.get("purpose", f"refine: {tmpl.get('event_focus', ['general'])}"),
                    })

        targets.append({"target_id": t["target_id"], "brand": brand, "queries": queries})

    plan = {
        "task_name": "auto_launch_volc_search",
        "mode": mode,
        "monitor_date": task_config.get("monitor_date", ""),
        "profile": profile_name,
        "time_window": {
            "start_date": tw.get("start_date", ""),
            "end_date": tw.get("end_date", ""),
            "start_datetime": tw.get("start_datetime", ""),
            "end_datetime": tw.get("end_datetime", ""),
        },
        "search_api_time_filter": {
            "enabled": True,
            "start_date": tw.get("start_date", ""),
            "end_date": tw.get("end_date", ""),
            "fallback_to_post_filter": True,
        },
        "targets": targets,
    }

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        print(f"[query_plan] 已写入: {output_path}")

    return plan


def _infer_source_focus(event_focus: list, source_strategy: dict) -> list:
    if "rumor_or_leak" in event_focus or "channel_campaign" in event_focus:
        return ["tier_1_official", "tier_3_industry_media", "tier_4_social_signal", "tier_5_unverified"]
    if source_strategy.get("official_first") and not source_strategy.get("include_authoritative_media", True):
        return ["tier_1_official"]
    return ["tier_1_official", "tier_3_industry_media"]
