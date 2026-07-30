"""gap_analyzer — 结构化信息缺口分析

输入: 当前搜索结果 + 任务定义
输出: 缺口描述 + 下一轮搜索目标

核心变化 vs V1:
  - 不再按固定事件类型匹配模板
  - 根据 missing_fields + unresolved_claims 动态生成搜索目标
"""

import yaml
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent.parent
CONFIG_PATH = SERVICE_ROOT / "configs" / "search_agent_v2.yaml"


def _load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def analyze_gaps(results: list[dict], task_config: dict,
                 covered_fields: set, missing_fields: set,
                 evidence_metrics: dict) -> dict:
    """分析当前搜索结果中的信息缺口

    Args:
        results: 本轮搜索结果列表
        task_config: 搜索任务配置
        covered_fields: 已覆盖的字段集合
        missing_fields: 缺失的字段集合
        evidence_metrics: evidencer 输出的指标

    Returns:
        gap: {
            "answered_fields": [...],
            "missing_fields": [...],
            "unresolved_claims": [...],
            "next_search_objectives": [...],
            "priority_gap": str | None,
        }
    """
    config = _load_config()
    mode = task_config.get("mode", "brand_watch")
    targets = task_config.get("targets", [])
    brand = targets[0].get("brand", "") if targets else ""

    raw_claims = evidence_metrics.get("unresolved_high_risk_claims", [])
    unresolved_claims = raw_claims if isinstance(raw_claims, list) else []

    objectives = []
    for mf in sorted(missing_fields):
        if mf == "event_date":
            objectives.append(f"查找{brand}相关事件的具体发生时间")
        elif mf == "official_confirmation":
            objectives.append(f"查找{brand}官方回应或公告")
        elif mf == "sales_status":
            objectives.append(f"确认{brand}的销售状态（开售/交付/预售）")
        elif mf == "price_change":
            objectives.append(f"查找{brand}的价格调整信息")
        elif mf == "benefit_adjustment":
            objectives.append(f"查找{brand}的权益/优惠调整")
        elif mf == "launch_status":
            objectives.append(f"确认{brand}的上市发布状态")
        elif mf == "buzz_volume":
            objectives.append(f"查找{brand}的声量热度数据（微信指数/百度指数/讨论度）")
        elif mf == "wechat_index":
            objectives.append(f"查找{brand}的微信指数或微信公众号文章热度")
        elif mf == "social_discussion":
            objectives.append(f"查找{brand}在小红书、微博、抖音等平台的讨论热度")
        elif mf == "sentiment":
            objectives.append(f"查找{brand}的口碑情感倾向和用户评价")
        else:
            objectives.append(f"补充{brand}的{mf}信息")

    # 未解决的高风险 claim 也作为目标
    for claim in unresolved_claims:
        objectives.append(f"验证{brand}的{claim}信息真实性")

    config_data = _load_config()
    sorted_missing = sorted(missing_fields)
    gap = {
        "answered_fields": sorted(covered_fields),
        "missing_fields": sorted_missing,
        "unresolved_claims": unresolved_claims,
        "next_search_objectives": objectives,
        "source_tier_gaps": _check_source_tier_gaps(results, config_data),
        "priority_gap": sorted_missing[0] if sorted_missing else None,
    }

    return gap


def _check_source_tier_gaps(results: list[dict], config: dict) -> list:
    """检查信源层级覆盖是否有明显缺口"""
    tiers = config.get("source_tiers", {})
    tier_keys = sorted(tiers.keys())
    covered_tiers = set()

    for r in results:
        for item in r.get("results", []):
            src = (item.get("source", "") or item.get("source_name", "")).lower()
            domain = src
            for tk in tier_keys:
                info = tiers[tk]
                domain_hints = info.get("domains", [])
                if any(h in domain for h in domain_hints):
                    covered_tiers.add(tk)

    gaps = []
    if "tier_1_official" not in covered_tiers:
        gaps.append({"missing_tier": "tier_1_official", "label": "官方源", "priority": "high"})
    if "tier_2_authoritative_media" not in covered_tiers:
        gaps.append({"missing_tier": "tier_2_authoritative_media", "label": "权威媒体", "priority": "medium"})

    return gaps
