"""query_rewriter — 信息缺口驱动的动态 Query 改写

核心变化 vs V1:
  - 不依赖固定 staged 模板
  - 根据 gap_analyzer 的输出生成下一轮查询
  - 支持缺失字段 → Query、未解决 Claim → Query、信源缺口 → Query
"""

import yaml
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent.parent
CONFIG_PATH = SERVICE_ROOT / "configs" / "search_agent_v2.yaml"


def _load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _deduplicate_queries(queries: list[dict], existing: list[dict]) -> list[dict]:
    """对已有 Query 去重（基于 query 文本的简单去重）"""
    existing_texts = {q.get("query", "") for q in existing}
    seen = set(existing_texts)
    deduped = []
    for q in queries:
        text = q.get("query", "")
        if text not in seen:
            seen.add(text)
            deduped.append(q)
    return deduped


def rewrite_queries(gap: dict, task_config: dict, existing_queries: list[dict] = None,
                    round_num: int = 1, query_budget: int = 3) -> list[dict]:
    """根据信息缺口生成下一轮查询

    Args:
        gap: gap_analyzer 输出的缺口分析
        task_config: 搜索任务配置
        existing_queries: 已有查询（用于去重）
        round_num: 当前轮次（1-based）
        query_budget: 本轮最大查询数

    Returns:
        queries: [{query, purpose, source_tier_focus, gap_driven}]
    """
    config = _load_config()
    rules = config.get("gap_query_rules", {})
    targets = task_config.get("targets", [])
    target = targets[0] if targets else {}
    brand = target.get("brand", "")
    model = target.get("model", "")
    display = f"{brand} {model}".strip() if model else brand
    time_window = task_config.get("time_window", {})
    days = time_window.get("days", 7)

    new_queries = []

    # 1. 从缺失字段生成 Query
    for mf in gap.get("missing_fields", []):
        field_rules = rules.get(mf, [])
        for rule in field_rules:
            if len(new_queries) >= query_budget:
                break
            pattern = rule["pattern"]
            q_text = (
                pattern
                .replace("{target}", display)
                .replace("{brand}", brand)
                .replace("{model}", model or brand)
                .replace("{event_type}", "")
                .replace("{days}", str(days))
            )
            q_text = q_text.replace("  ", " ").strip()
            new_queries.append({
                "query": q_text,
                "purpose": rule.get("purpose", f"补充{mf}"),
                "source_tier_focus": ["tier_1_official", "tier_3_industry_media"],
                "gap_driven": True,
                "gap_field": mf,
                "round": round_num,
            })
        if len(new_queries) >= query_budget:
            break

    # 2. 从信源缺口生成 Query
    for tier_gap in gap.get("source_tier_gaps", []):
        if len(new_queries) >= query_budget:
            break
        if tier_gap["missing_tier"] == "tier_1_official":
            q_text = f"{brand} 官方 公告 最近{days}天"
            new_queries.append({
                "query": q_text,
                "purpose": "查找官方源",
                "source_tier_focus": ["tier_1_official"],
                "gap_driven": True,
                "gap_field": "official_confirmation",
                "round": round_num,
            })

    # 3. 从未解决 Claim 生成 Query
    for claim in gap.get("unresolved_claims", []):
        if len(new_queries) >= query_budget:
            break
        q_text = f"{brand} {claim} 最近{days}天"
        new_queries.append({
            "query": q_text,
            "purpose": f"验证{claim}",
            "source_tier_focus": ["tier_1_official", "tier_3_industry_media"],
            "gap_driven": True,
            "gap_field": f"claim_{claim}",
            "round": round_num,
        })

    # 4. 去重
    if existing_queries:
        new_queries = _deduplicate_queries(new_queries, existing_queries)

    return new_queries[:query_budget]
