"""
volc_search_query_builder.py — 根据 search_task_config 生成可执行的 Volc Search query plan。

用法:
  python volc_search_query_builder.py \
    --task-config outputs/auto_launch/search/2026-07-02/brand_watch/search_task_config.json
"""

import json, sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT))

import yaml


def _load_search_templates():
    path = WORKSPACE_ROOT / "promptbuilders" / "auto_launch" / "configs" / "volc_search.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f)


def _build_brand_queries(target: dict, time_window: dict, event_ids: list, templates: dict,
                         budget: int, source_strategy: dict):
    """为品牌级监控生成查询"""
    brand = target["brand"]
    aliases = target.get("aliases", [brand])
    days = time_window.get("days", 7)

    queries = []

    # determine which template set to use
    is_open = len(event_ids) > 5
    template_set = templates.get("search_templates", {}).get("brand_open_scan", []) if is_open else templates.get("search_templates", {}).get("event_specific", [])

    for tpl in template_set:
        if len(queries) >= budget:
            break
        pattern = tpl["pattern"]
        q = pattern.replace("{brand}", brand).replace("{days}", str(days))
        # skip if no relevant event focus
        tf = tpl.get("event_focus", [])
        if "all" not in tf and not any(e in event_ids for e in tf):
            continue
        purpose = f"discover {', '.join(tf[:3])}"
        source_focus = _infer_source_focus(tf, source_strategy)
        queries.append({
            "query": q,
            "event_type_ids": tf if "all" not in tf else event_ids,
            "source_tier_focus": source_focus,
            "purpose": purpose,
        })

    return queries


def _build_model_queries(target: dict, time_window: dict, event_ids: list, templates: dict,
                         budget: int, source_strategy: dict):
    """为车型级监控生成查询"""
    brand = target["brand"]
    model = target.get("model", "")
    display = f"{brand}{model}" if model else brand
    days = time_window.get("days", 7)

    queries = []
    is_open = len(event_ids) > 5
    template_set = templates.get("search_templates", {}).get("model_open_scan", []) if is_open else templates.get("search_templates", {}).get("event_specific", [])

    for tpl in template_set:
        if len(queries) >= budget:
            break
        pattern = tpl["pattern"]
        q = pattern.replace("{model}", display).replace("{target}", display).replace("{brand}", brand).replace("{days}", str(days))
        tf = tpl.get("event_focus", [])
        if "all" not in tf and not any(e in event_ids for e in tf):
            continue
        purpose = f"discover {', '.join(tf[:3])}"
        source_focus = _infer_source_focus(tf, source_strategy)
        queries.append({
            "query": q,
            "event_type_ids": tf if "all" not in tf else event_ids,
            "source_tier_focus": source_focus,
            "purpose": purpose,
        })

    return queries


def _infer_source_focus(event_focus: list, source_strategy: dict) -> list:
    """根据事件类型和策略推断应优先的 source tier"""
    # rumor/leak should always include social/unverified
    if "rumor_or_leak" in event_focus or "channel_campaign" in event_focus or "user_event" in event_focus:
        return ["tier_1_official", "tier_3_industry_media", "tier_4_social_signal", "tier_5_unverified"]

    # official price/launch changes → official first
    if any(e in event_focus for e in ["launch", "presale", "official_price_change", "benefit_adjustment"]):
        return ["tier_1_official", "tier_2_authoritative_media"]

    # default
    return ["tier_1_official", "tier_2_authoritative_media", "tier_3_industry_media"]


def build_query_plan(task_config: dict, output_path: str = None):
    templates = _load_search_templates()
    mode = task_config["mode"]
    time_window = task_config["time_window"]
    event_ids = task_config.get("event_type_ids", [])
    budget = task_config.get("query_budget", {}).get("query_budget_per_target", 8)
    source_strategy = task_config.get("source_strategy", {})

    targets = []
    for t in task_config.get("targets", []):
        if mode == "brand_watch":
            queries = _build_brand_queries(t, time_window, event_ids, templates, budget, source_strategy)
        else:
            queries = _build_model_queries(t, time_window, event_ids, templates, budget, source_strategy)
        targets.append({
            "target_id": t["target_id"],
            "brand": t["brand"],
            "queries": queries,
        })

    plan = {
        "task_name": "auto_launch_volc_search",
        "mode": mode,
        "monitor_date": task_config["monitor_date"],
        "time_window": {
            "start_date": time_window["start_date"],
            "end_date": time_window["end_date"],
        },
        "targets": targets,
    }

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        print(f"[query_plan] 已写入: {output_path}")

    return plan


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Volc Search 查询计划生成器")
    parser.add_argument("--task-config", required=True, help="search_task_config JSON 路径")
    parser.add_argument("--output", help="输出路径")
    args = parser.parse_args()

    with open(args.task_config) as f:
        task_config = json.load(f)
    plan = build_query_plan(task_config, args.output)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
