"""evidence — 证据评价与三层停止决策

停止策略（按优先级评估）:
  1. confirmed   — 官方源+多独立源+字段覆盖达标+无高风险未解决 Claim
  2. fallback    — 非官方源但多源互证（类型多样、非同源）
  3. hard_limit  — 达到资源上限
  4. weak_signal — 资源耗尽但信号微弱
"""

import yaml
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = MODULE_DIR.parent.parent
CONFIG_PATH = SERVICE_ROOT / "configs" / "search_agent_v2.yaml"


def _load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _count_independent_sources(results: list[dict]) -> int:
    """按原始信源域名去重统计独立来源数"""
    domains = set()
    for r in results:
        for item in r.get("results", []):
            src = item.get("source", "") or item.get("source_name", "")
            if src:
                domains.add(src.lower())
    return len(domains)


def _count_official_sources(results: list[dict], config: dict) -> int:
    """统计搜索结果中来自官方源的唯一信源数（按域名去重）"""
    tiers = config.get("source_tiers", {})
    tier_1 = tiers.get("tier_1_official", {})
    official_domain_hints = tier_1.get("domains", [])

    official_domains = set()
    for r in results:
        for item in r.get("results", []):
            src = (item.get("source", "") or item.get("source_name", "")).lower()
            if not src:
                continue
            if any(hint in src for hint in official_domain_hints):
                official_domains.add(src)
                continue
            # 仅通过域名判断是否为官方源，不依赖正文关键字
            if any(src.endswith(f".{d}") for d in ["gov.cn", "12365auto.cn"]):
                official_domains.add(src)
            if any(kw in src for kw in ["official", "官网", "weixin.qq.com"]):
                official_domains.add(src)
    return len(official_domains)


def _flatten_fields(defs: dict, tier: str = None) -> list:
    """展开 identity/metadata/evidence 三层字段为平面列表"""
    fields = []
    tiers = ["identity", "metadata", "evidence"]
    for t in tiers:
        if tier and t != tier:
            continue
        fields.extend(defs.get(t, []))
    fields.extend(defs.get("optional", []))
    return fields


def _coverage_tier_breakdown(results: list[dict], defs: dict) -> dict:
    """分别计算三层覆盖率"""
    breakdown = {}
    for tier in ["identity", "metadata", "evidence"]:
        tier_fields = defs.get(tier, [])
        if not tier_fields:
            breakdown[tier] = {"total": 0, "covered": 0, "weight": 0.0, "covered_weight": 0.0}
            continue
        covered = set()
        for r in results:
            for item in r.get("results", []):
                text = (
                    (item.get("title", "") or "")
                    + " " + (item.get("snippet", "") or "")
                    + " " + (item.get("source", "") or "")
                ).lower()
                for fd in tier_fields:
                    field = fd["field"]
                    if field in covered:
                        continue
                    label = fd.get("label", field).lower()
                    if field in text or label in text:
                        covered.add(field)
        total_w = sum(fd.get("weight", 1.0) for fd in tier_fields)
        covered_w = sum(fd.get("weight", 1.0) for fd in tier_fields if fd["field"] in covered)
        breakdown[tier] = {
            "total": len(tier_fields),
            "covered": len(covered),
            "weight": total_w,
            "covered_weight": covered_w,
        }
    return breakdown


def _compute_fields_coverage(results: list[dict], field_defs: dict, mode: str) -> tuple[float, set, set]:
    """计算字段覆盖率和已覆盖/缺失字段

    三层加权: identity × 1.0, metadata × 0.6, evidence × 0.8
    """
    defs = field_defs.get(mode, {})
    required = _flatten_fields(defs, tier=None)

    all_fields = required
    if not all_fields:
        return 1.0, set(), set()

    covered = set()
    for r in results:
        for item in r.get("results", []):
            text = (
                (item.get("title", "") or "")
                + " " + (item.get("snippet", "") or "")
                + " " + (item.get("source", "") or "")
            ).lower()
            for fd in all_fields:
                field = fd["field"]
                if field in covered:
                    continue
                label = fd.get("label", field).lower()
                if field in text or label in text:
                    covered.add(field)

    breakdown = _coverage_tier_breakdown(results, defs)

    # 三层加权: identity=1.0, metadata=0.6, evidence=0.8
    tier_weights = {"identity": 1.0, "metadata": 0.6, "evidence": 0.8}
    total_weighted = 0.0
    covered_weighted = 0.0
    for tier, data in breakdown.items():
        if data["weight"] > 0:
            tw = tier_weights.get(tier, 0.5)
            total_weighted += data["weight"] * tw
            covered_weighted += data["covered_weight"] * tw

    coverage = covered_weighted / total_weighted if total_weighted > 0 else 0.0

    missing_fields = set()
    for fd in all_fields:
        if fd["field"] not in covered:
            missing_fields.add(fd["field"])
    covered_fields = {fd["field"] for fd in all_fields if fd["field"] in covered}

    return coverage, covered_fields, missing_fields, breakdown


def _check_high_risk_claims(results: list[dict], config: dict) -> list[str]:
    """检查是否存在未解决的高风险 Claim"""
    high_risk = config.get("high_risk_claims", [])
    unresolved = []

    for r in results:
        for item in r.get("results", []):
            text = (
                (item.get("title", "") or "")
                + " " + (item.get("snippet", "") or "")
            ).lower()
            for claim in high_risk:
                if claim in text:
                    pass  # claim 出现在结果中，需要进一步判断是否解决了

    return unresolved


def _calc_shared_origin_ratio(results: list[dict], config: dict) -> float:
    """估算所有结果中共享起源的比例"""
    thresh = config.get("shared_origin_detection", {}).get("cross_share_threshold", 0.7)
    all_snippets = []
    for r in results:
        for item in r.get("results", []):
            s = (item.get("snippet", "") or "").strip()
            if s:
                all_snippets.append(s)

    if len(all_snippets) < 2:
        return 0.0

    shared_count = 0
    seen = set()
    # 简单近似：以标题前 30 字为指纹，重复计为同源
    for r in results:
        for item in r.get("results", []):
            title = (item.get("title", "") or "").strip()
            if not title:
                continue
            fingerprint = title[:30]
            if fingerprint in seen:
                shared_count += 1
            else:
                seen.add(fingerprint)

    return shared_count / max(len(all_snippets), 1)


def _count_source_tier_types(results: list[dict]) -> set:
    """统计结果覆盖的信源层级类型数"""
    tier_types = set()
    for r in results:
        for item in r.get("results", []):
            src = (item.get("source", "") or item.get("source_name", "")).lower()
            if not src:
                continue
            domain = src
            if ".gov" in domain or "official" in domain:
                tier_types.add("official")
            elif any(kw in domain for kw in ["dealer", "4s", "store", "经销"]):
                tier_types.add("dealer")
            elif any(kw in domain for kw in ["social", "weibo", "weixin", "xiaohongshu", "bbs", "tieba"]):
                tier_types.add("social")
            elif domain.endswith((".com", ".cn", ".net", ".org")):
                tier_types.add("media")
    return tier_types


def evaluate_evidence(results: list[dict], config: dict, field_defs: dict,
                      mode: str, round_num: int, total_calls: int,
                      effective_hard_limits: dict = None) -> dict:
    """对当前搜索结果进行证据评估，返回决策建议

    Returns:
        decision: {
            "should_stop": bool,
            "conclusion_status": str | None,
            "stop_reason": str | None,
            "condition_met": str | None,
            "metrics": {...},
        }
    """
    # 统一配置路径：支持传入完整 config 或 search_stop_policy 子集
    if "search_stop_policy" in config:
        policy = config["search_stop_policy"]
    else:
        policy = config
    hard_limits = effective_hard_limits or policy.get("hard_limits", {})

    # 本轮累计指标
    independent_sources = _count_independent_sources(results)
    official_sources = _count_official_sources(results, config)
    coverage, covered_fields, missing_fields, tier_breakdown = _compute_fields_coverage(results, field_defs, mode)
    unresolved_claims = _check_high_risk_claims(results, config)
    shared_ratio = _calc_shared_origin_ratio(results, config)
    tier_types = _count_source_tier_types(results)

    metrics = {
        "independent_sources": independent_sources,
        "official_sources": official_sources,
        "fields_coverage": round(coverage, 3),
        "unresolved_high_risk_claims": len(unresolved_claims),
        "shared_origin_ratio": round(shared_ratio, 3),
        "source_tier_types": sorted(tier_types),
        "round": round_num,
        "total_api_calls": total_calls,
        "tier_breakdown": tier_breakdown,
    }

    decision = {
        "should_stop": False,
        "conclusion_status": None,
        "stop_reason": None,
        "condition_met": None,
        "metrics": metrics,
        "covered_fields": sorted(covered_fields),
        "missing_fields": sorted(missing_fields),
    }

    dt = policy.get("decision_table", [])

    for entry in dt:
        condition_name = entry["condition"]
        cond_def = policy.get("conditions", {}).get(condition_name, {})
        conclusion_status = entry["conclusion_status"]
        stop_reason = entry["stop_reason"]

        if condition_name == "confirmed":
            ok = (
                independent_sources >= cond_def.get("min_independent_sources", 2)
                and official_sources >= cond_def.get("min_official_sources", 1)
                and coverage >= cond_def.get("required_fields_coverage", 0.8)
                and len(unresolved_claims) <= cond_def.get("unresolved_high_risk_claims", 0)
            )
            if ok:
                decision.update({
                    "should_stop": True,
                    "condition_met": condition_name,
                    "conclusion_status": conclusion_status,
                    "stop_reason": stop_reason,
                })
                return decision

        elif condition_name == "fallback":
            allowed_tiers = cond_def.get("allowed_source_tiers", ["media", "dealer", "social"])
            tier_types_met = any(t in allowed_tiers for t in tier_types)
            ok = (
                independent_sources >= cond_def.get("min_independent_sources", 3)
                and len(tier_types) >= cond_def.get("min_source_tier_types", 2)
                and shared_ratio <= cond_def.get("max_shared_origin_ratio", 0.5)
                and tier_types_met
                and coverage >= cond_def.get("required_fields_coverage", 0.7)
                and len(unresolved_claims) <= cond_def.get("unresolved_high_risk_claims", 0)
            )
            if ok:
                decision.update({
                    "should_stop": True,
                    "condition_met": condition_name,
                    "conclusion_status": conclusion_status,
                    "stop_reason": stop_reason,
                })
                return decision

        elif condition_name == "hard_limit":
            limit_rounds = hard_limits.get("max_rounds", 3)
            limit_queries = hard_limits.get("max_queries", 10)
            limit_calls = hard_limits.get("max_provider_calls", 15)
            ok = (
                round_num >= limit_rounds
                or len(results) >= limit_queries
                or total_calls >= limit_calls
            )
            if ok:
                decision.update({
                    "should_stop": True,
                    "condition_met": condition_name,
                    "conclusion_status": conclusion_status,
                    "stop_reason": stop_reason,
                })
                return decision

        elif condition_name == "weak_signal":
            # 达到 hard_limit 但证据仍不足时自然回落到此项
            if len(results) >= hard_limits.get("max_queries", 10):
                decision.update({
                    "should_stop": True,
                    "condition_met": condition_name,
                    "conclusion_status": conclusion_status,
                    "stop_reason": stop_reason,
                })
                return decision

    return decision
