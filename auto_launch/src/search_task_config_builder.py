"""
search_task_config_builder.py — 将 search_intent 转为可执行搜索任务配置。

用法:
  python search_task_config_builder.py \
    --intent auto_launch/outputs/search/2026-07-02/brand_watch/search_intent.json
"""

import json, sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent
PROJECT_ROOT = SERVICE_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml


def _load_brand_watchlist():
    path = SERVICE_ROOT / "configs" / "priority_brand_watchlist.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f)


def _load_model_watchlist():
    path = SERVICE_ROOT / "configs" / "ls8_competitor_watchlist.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f)


def _load_source_tiers():
    path = SERVICE_ROOT / "configs" / "source_tiers.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f)


def _load_event_types():
    path = SERVICE_ROOT / "configs" / "event_types.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f)


def _resolve_target_aliases(target: dict, brand_wl: dict, model_wl: dict):
    """从 watchlist 中补充品牌/车型的别名信息"""
    brand_name = target.get("brand", "")
    aliases = [brand_name]
    sub_brands = []
    models = []

    # brand watchlist
    for cat in brand_wl.get("brands", []):
        for sb in cat.get("sub_brands", []):
            if sb["name"] == brand_name:
                aliases.extend(sb.get("keywords", []))
                models = sb.get("models", [])
            if sb["name"] != brand_name:
                sub_brands.append(sb["name"])

    # model watchlist
    for t in model_wl.get("targets", []):
        if t["brand"] == brand_name:
            aliases.extend(t.get("brand_aliases", []))
            if target.get("model") and t["model"] == target["model"]:
                models.append(t["model"])

    # deduplicate
    seen = set()
    deduped = []
    for a in aliases:
        if a not in seen:
            seen.add(a)
            deduped.append(a)

    return {
        "target_id": target.get("target_id", brand_name.lower()),
        "target_type": target["target_type"],
        "brand": brand_name,
        "aliases": deduped,
        "sub_brands": sub_brands,
        "models": models,
    }


def build_task_config(intent: dict, output_path: str = None):
    brand_wl = _load_brand_watchlist()
    model_wl = _load_model_watchlist()
    source_tiers = _load_source_tiers()
    event_types = _load_event_types()

    targets = []
    for t in intent.get("targets", []):
        enriched = _resolve_target_aliases(t, brand_wl, model_wl)
        targets.append(enriched)

    # source strategy: expand to tier-level config
    ss = intent.get("source_strategy", {})
    # preserve intent-level flags for query builder use
    source_strategy_meta = {
        "official_first": ss.get("official_first", True),
        "include_authoritative_media": ss.get("include_authoritative_media", True),
        "include_social_signals": ss.get("include_social_signals", True),
        "social_signals_as_discovery_only": ss.get("social_signals_as_discovery_only", True),
        "allow_unverified_as_discovery_only": ss.get("allow_unverified_as_discovery_only", True),
    }
    source_strategy = dict(source_strategy_meta)
    if source_tiers:
        for tier in source_tiers.get("tiers", []):
            tier_key = f"tier_{tier['tier']}_{tier['name'].replace(' ', '_')}"
            enabled = True
            purpose = tier.get(f"{intent.get('mode', 'brand_watch')}_usage", tier.get("description", ""))
            source_strategy[tier_key] = {
                "enabled": enabled if tier["tier"] <= 3 else ss.get("social_signals_as_discovery_only", True),
                "purpose": purpose,
            }
            # apply overrides
            if not ss.get("include_authoritative_media", True) and tier["tier"] == 2:
                source_strategy[tier_key]["enabled"] = False
            if not ss.get("include_social_signals", True) and tier["tier"] >= 4:
                source_strategy[tier_key]["enabled"] = False

    event_type_ids = intent.get("event_scope", {}).get("event_type_ids", [])
    mode = intent["mode"]

    task_config = {
        "task_name": "auto_launch_search_task",
        "mode": mode,
        "monitor_date": intent["monitor_date"],
        "target_count": len(targets),
        "targets": targets,
        "time_window": intent["time_window"],
        "source_strategy": source_strategy,
        "event_type_ids": event_type_ids,
        "query_budget": intent.get("query_budget", {
            "query_budget_per_target": 8,
            "result_limit_per_query": 10,
        }),
    }

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(task_config, f, ensure_ascii=False, indent=2)
        print(f"[task_config] 已写入: {output_path}")

    return task_config


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="搜索任务配置构建器")
    parser.add_argument("--intent", required=True, help="search_intent JSON 路径")
    parser.add_argument("--output", help="输出路径")
    args = parser.parse_args()

    with open(args.intent) as f:
        intent = json.load(f)
    config = build_task_config(intent, args.output)
    print(json.dumps(config, ensure_ascii=False, indent=2))
