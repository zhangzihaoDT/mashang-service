"""claim_evaluator — Claim-level 证据评估

v2.3: 将 field-level binary coverage 升级为 claim-level multi-quality evidence

架构:
  输入: search results + field_definitions + identity
  输出: per-claim evidence set, each with quality level

  EvidenceQuality:
    missing              — 无相关结果
    mention_only         — 仅提及关键词，无实质信息
    indirect             — 同一品牌/车型但非该字段
    qualitative          — 有定性描述（程度/情感词）
    quantitative         — 有定量数据（数字+单位）
    officially_confirmed — 官方源确认
    contradicted         — 反证

  Claim:
    field, label, status, evidence[], summary
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EvidenceQuality(str, Enum):
    MISSING = "missing"
    MENTION_ONLY = "mention_only"
    INDIRECT = "indirect"
    QUALITATIVE = "qualitative"
    QUANTITATIVE = "quantitative"
    OFFICIALLY_CONFIRMED = "officially_confirmed"
    CONTRADICTED = "contradicted"


class ClaimStatus(str, Enum):
    UNKNOWN = "unknown"
    PARTIAL = "partial"
    PROBABLE = "probable"
    CONFIRMED = "confirmed"
    CONTRADICTED = "contradicted"


# 定量检测：数字 + 单位
_QUANTITATIVE_PATTERNS = [
    re.compile(r'\d+[\.\d]*\s*(台|辆|元|亿|公里|㎞|km|秒|分钟|小时|天|%|万)'),
    re.compile(r'\d+[\.\d]*\s*万(起|起售|以上|以下|元)?'),
    re.compile(r'(售价|价格|预售价|定价|售价仅|仅)\s*\d+[\.\d]*\s*万'),
    re.compile(r'\d+[\.\d]*\s*(万|千|百)\s*(台|辆|人|次|条|篇)'),
]

# 反证关键词（按 field）：对特定 claim 有否定意义
# 原则：只有直接否定该 claim 核心主张的词才算 contradicted
_FIELD_CONTRADICTED = {
    "buzz_volume": ["无人问津", "没人讨论", "没有热度", "零关注", "冷清"],
    "sentiment": ["投诉", "差评", "被骂", "口碑差", "不满", "维权", "暴跌", "溃败", "崩盘"],
    "key_fact": [],  # 关键事实无反证概念
    "wechat_mention": [],
    "wechat_value": [],
    "social_discussion": [],
    "event_date": [],
    "event_type": [],
    "source": [],
    "official_confirmation": [],
    "sales_status": [],
    "price_change": [],
    "benefit_adjustment": [],
}

# 定性检测：程度/情感词（超出 match_keywords 的补充）
_QUALITATIVE_BONUS = [
    "非常", "极其", "特别", "相当", "比较", "有点",
    "好评", "差评", "称赞", "批评", "吐槽", "推荐",
    "惊艳", "震撼", "失望", "满意", "不满",
]


def _has_quantitative(text: str) -> bool:
    for pat in _QUANTITATIVE_PATTERNS:
        if pat.search(text):
            return True
    return False


def _has_qualitative_extra(text: str) -> bool:
    for kw in _QUALITATIVE_BONUS:
        if kw in text:
            return True
    return False


def _has_contradicted(text: str, field: str) -> bool:
    kws = _FIELD_CONTRADICTED.get(field, [])
    if not kws:
        return False
    for kw in kws:
        if kw in text:
            return True
    return False


def _classify_evidence(text: str, source_type: Optional[str],
                       field: str, field_kw_matched: bool) -> EvidenceQuality:
    """对一条 result item 判断证据质量等级"""
    if not field_kw_matched:
        return EvidenceQuality.MENTION_ONLY

    if _has_contradicted(text, field):
        if source_type == "official":
            return EvidenceQuality.CONTRADICTED
        return EvidenceQuality.CONTRADICTED

    if source_type == "official":
        return EvidenceQuality.OFFICIALLY_CONFIRMED

    if _has_quantitative(text):
        return EvidenceQuality.QUANTITATIVE

    if _has_qualitative_extra(text):
        return EvidenceQuality.QUALITATIVE

    return EvidenceQuality.QUALITATIVE


def _aggregate_claim_status(qualities: list[EvidenceQuality]) -> ClaimStatus:
    """根据 evidence 质量分布聚合为 claim 级别状态"""
    if not qualities:
        return ClaimStatus.UNKNOWN

    if any(q == EvidenceQuality.CONTRADICTED for q in qualities):
        return ClaimStatus.CONTRADICTED

    if any(q == EvidenceQuality.OFFICIALLY_CONFIRMED for q in qualities):
        return ClaimStatus.CONFIRMED

    quant_count = sum(1 for q in qualities if q == EvidenceQuality.QUANTITATIVE)
    qual_count = sum(1 for q in qualities if q in (EvidenceQuality.QUALITATIVE, EvidenceQuality.QUANTITATIVE))

    if quant_count >= 2:
        return ClaimStatus.PROBABLE
    if qual_count >= 2:
        return ClaimStatus.PARTIAL
    if qual_count >= 1:
        return ClaimStatus.PARTIAL

    return ClaimStatus.UNKNOWN


def evaluate_claims(results: list[dict], field_defs: dict, mode: str,
                    publication_tier_map: dict = None,
                    identity_fields: set[str] = None) -> list[dict]:
    """对搜索结果进行 claim-level 证据评估

    Returns:
        claims: [{
            "field": str,
            "label": str,
            "status": str,
            "evidence": [{
                "source": str,
                "title": str,
                "quality": str,
            }],
            "summary": str,
        }]
    """
    pub_map = publication_tier_map or {}
    identity_fields = identity_fields or set()
    defs = field_defs.get(mode, {})

    # 收集所有非 identity 字段
    all_fields = []
    for tier in ["metadata", "evidence", "optional"]:
        for fd in defs.get(tier, []):
            if fd["field"] not in identity_fields:
                all_fields.append(fd)

    # 按 field 分组 evidence
    field_evidence: dict[str, list[dict]] = {}
    field_labels: dict[str, str] = {}

    for fd in all_fields:
        field = fd["field"]
        field_labels[field] = fd.get("label", field)
        field_evidence[field] = []

    # 扫描所有结果
    for r in results:
        for item in r.get("results", []):
            text = (
                (item.get("title", "") or "")
                + " " + (item.get("snippet", "") or "")
            ).lower()
            source_type = _get_source_type(item, pub_map)

            # 对该 item，判断每个 field 是否命中
            for fd in all_fields:
                field = fd["field"]
                match_kw = fd.get("match_keywords", [])
                label = fd.get("label", "").lower()
                field_name = fd["field"]

                kw_matched = any(kw in text for kw in match_kw) if match_kw else False
                label_matched = (label and label in text) if label else False
                name_matched = field_name in text

                if not (kw_matched or label_matched or name_matched):
                    # 间接命中：品牌/车型在结果中但该 field 未匹配
                    continue

                quality = _classify_evidence(text, source_type, field, kw_matched)
                field_evidence[field].append({
                    "source": item.get("source", "") or item.get("source_name", "") or "",
                    "title": (item.get("title", "") or "")[:100],
                    "quality": quality.value,
                })

    # 构建 claims
    claims = []
    for field in field_labels:
        ev_list = field_evidence[field]
        qualities = [EvidenceQuality(e["quality"]) for e in ev_list]
        status = _aggregate_claim_status(qualities)
        best = _best_quality(qualities)

        summary = _build_summary(field, field_labels[field], status, best, len(ev_list))

        claims.append({
            "field": field,
            "label": field_labels[field],
            "status": status.value,
            "evidence": ev_list[:10],
            "evidence_count": len(ev_list),
            "best_quality": best.value if best else None,
            "summary": summary,
        })

    return claims


def _get_source_type(item: dict, pub_map: dict) -> Optional[str]:
    src = (item.get("source", "") or item.get("source_name", "") or "").lower()
    if not src:
        return None
    for pub, tier in pub_map.items():
        if pub.lower() in src:
            if tier == "official":
                return "official"
    return None


def _best_quality(qualities: list[EvidenceQuality]) -> Optional[EvidenceQuality]:
    """返回 evidence 中的最高质量等级"""
    rank = [
        EvidenceQuality.CONTRADICTED,
        EvidenceQuality.OFFICIALLY_CONFIRMED,
        EvidenceQuality.QUANTITATIVE,
        EvidenceQuality.QUALITATIVE,
        EvidenceQuality.MENTION_ONLY,
        EvidenceQuality.INDIRECT,
    ]
    for q in rank:
        if q in qualities:
            return q
    return None


def _build_summary(field: str, label: str, status: ClaimStatus,
                   best: Optional[EvidenceQuality], count: int) -> str:
    if status == ClaimStatus.CONTRADICTED:
        return f"{label}：存在反证"
    if status == ClaimStatus.CONFIRMED:
        return f"{label}：官方确认"
    if status == ClaimStatus.PROBABLE:
        return f"{label}：有多源定量数据支撑（{count}条）"
    if status == ClaimStatus.PARTIAL:
        return f"{label}：有定性描述（{count}条）"
    return f"{label}：证据不足"
