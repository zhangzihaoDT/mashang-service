"""claim_evaluator — Claim-level 证据评估

v2.3: 将 field-level binary coverage 升级为 claim-level multi-quality evidence

核心分层:
  Coverage 负责: Search Loop
  Claim    负责: Result Understanding

证据有两个正交维度:
  quality    — 证据本身是什么（mention_only / qualitative / quantitative / official）
  direction  — 证据对 claim 的支持关系（support / contradict / neutral）

Claim 有两个聚合维度:
  value  — 聚合后的结论内容（high / low / positive / negative / mixed / present / absent）
  status — 聚合后的确信度（unknown / partial / probable / confirmed）
"""

import re
from enum import Enum
from typing import Optional


class EvidenceQuality(str, Enum):
    MISSING = "missing"
    MENTION_ONLY = "mention_only"
    QUALITATIVE = "qualitative"
    QUANTITATIVE = "quantitative"
    OFFICIAL = "official"


class EvidenceDirection(str, Enum):
    SUPPORT = "support"
    CONTRADICT = "contradict"
    NEUTRAL = "neutral"


class ClaimStatus(str, Enum):
    UNKNOWN = "unknown"
    PARTIAL = "partial"
    PROBABLE = "probable"
    CONFIRMED = "confirmed"


# 定量检测：数字 + 单位
_QUANTITATIVE_PATTERNS = [
    re.compile(r'\d+[\.\d]*\s*(台|辆|元|亿|公里|㎞|km|秒|分钟|小时|天|%|万)'),
    re.compile(r'\d+[\.\d]*\s*万(起|起售|以上|以下|元)?'),
    re.compile(r'(售价|价格|预售价|定价|售价仅|仅)\s*\d+[\.\d]*\s*万'),
    re.compile(r'\d+[\.\d]*\s*(万|千|百)\s*(台|辆|人|次|条|篇)'),
]

# 反证关键词（按 field）：对特定 claim 核心主张有否定意义的词
_FIELD_CONTRADICTED = {
    "buzz_volume": ["无人问津", "没人讨论", "没有热度", "零关注", "冷清"],
    "sentiment": ["投诉", "差评", "被骂", "口碑差", "不满", "维权", "暴跌", "溃败", "崩盘"],
}

# 定性检测补充词
_QUALITATIVE_BONUS = [
    "非常", "极其", "特别", "相当", "比较", "有点",
    "好评", "差评", "称赞", "批评", "吐槽", "推荐",
    "惊艳", "震撼", "失望", "满意", "不满",
]

# 证据质量分数（用于 status 聚合）
_QUALITY_SCORE = {
    EvidenceQuality.OFFICIAL: 3,
    EvidenceQuality.QUANTITATIVE: 2,
    EvidenceQuality.QUALITATIVE: 1,
    EvidenceQuality.MENTION_ONLY: 0,
}


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


def _has_field_contradicted(text: str, field: str) -> bool:
    kws = _FIELD_CONTRADICTED.get(field, [])
    if not kws:
        return False
    for kw in kws:
        if kw in text:
            return True
    return False


def _classify_evidence(text: str, source_type: Optional[str],
                       field: str, kw_matched: bool) -> tuple[EvidenceQuality, EvidenceDirection]:
    """对一条 result item 判断 (quality, direction)"""
    direction = EvidenceDirection.NEUTRAL

    if not kw_matched:
        return EvidenceQuality.MENTION_ONLY, direction

    # 反证检测（direction = contradict）
    if _has_field_contradicted(text, field):
        direction = EvidenceDirection.CONTRADICT
    else:
        direction = EvidenceDirection.SUPPORT

    # quality 检测
    if source_type == "official":
        return EvidenceQuality.OFFICIAL, direction

    if _has_quantitative(text):
        return EvidenceQuality.QUANTITATIVE, direction

    if _has_qualitative_extra(text):
        return EvidenceQuality.QUALITATIVE, direction

    return EvidenceQuality.QUALITATIVE, direction


def _aggregate_claim_status(evidences: list[dict]) -> ClaimStatus:
    """根据 evidence 质量分数聚合为 claim 确信度"""
    if not evidences:
        return ClaimStatus.UNKNOWN

    total_score = 0
    for e in evidences:
        q = EvidenceQuality(e["quality"])
        total_score += _QUALITY_SCORE.get(q, 0)

    if total_score >= 6:
        return ClaimStatus.CONFIRMED
    if total_score >= 3:
        return ClaimStatus.PROBABLE
    if total_score >= 1:
        return ClaimStatus.PARTIAL
    return ClaimStatus.UNKNOWN


def _infer_claim_value(evidences: list[dict], field: str) -> str:
    """根据 evidence 的 direction 分布推断 claim 的值"""
    support_count = sum(1 for e in evidences if e.get("direction") == "support")
    contradict_count = sum(1 for e in evidences if e.get("direction") == "contradict")

    if not evidences:
        return "unknown"

    if contradict_count > support_count:
        if field == "sentiment":
            return "negative"
        return "low"

    if support_count > contradict_count:
        if field == "sentiment":
            return "positive"
        return "high"

    # support ≈ contradict
    if field == "sentiment":
        return "mixed"

    # 对于其他 field，support 多就是 present/high
    return "present" if support_count > 0 else "unknown"


def _best_quality(evidences: list[dict]) -> Optional[str]:
    rank = [
        EvidenceQuality.OFFICIAL,
        EvidenceQuality.QUANTITATIVE,
        EvidenceQuality.QUALITATIVE,
        EvidenceQuality.MENTION_ONLY,
    ]
    for q in rank:
        if any(e["quality"] == q.value for e in evidences):
            return q.value
    return None


def _build_summary(label: str, value: str, status: ClaimStatus,
                   best: Optional[str], count: int) -> str:
    if status == ClaimStatus.CONFIRMED:
        return f"{label}：{value}，官方确认"
    if status == ClaimStatus.PROBABLE:
        return f"{label}：{value}，定量支撑（{count}条）"
    if status == ClaimStatus.PARTIAL:
        return f"{label}：{value}，定性描述（{count}条）"
    return f"{label}：证据不足"


def _get_source_type(item: dict, pub_map: dict) -> Optional[str]:
    src = (item.get("source", "") or item.get("source_name", "") or "").lower()
    if not src:
        return None
    for pub, tier in pub_map.items():
        if pub.lower() in src:
            if tier == "official":
                return "official"
    return None


def evaluate_claims(results: list[dict], field_defs: dict, mode: str,
                    publication_tier_map: dict = None,
                    identity_fields: set[str] = None) -> list[dict]:
    """对搜索结果进行 claim-level 证据评估

    Returns:
        claims: [{
            "field": str,
            "label": str,
            "value": str,         # high / low / positive / negative / mixed / present
            "status": str,        # unknown / partial / probable / confirmed
            "evidence": [{source, title, quality, direction}],
            "best_quality": str,
            "summary": str,
        }]
    """
    pub_map = publication_tier_map or {}
    identity_fields = identity_fields or set()
    defs = field_defs.get(mode, {})

    all_fields = []
    for tier in ["metadata", "evidence", "optional"]:
        for fd in defs.get(tier, []):
            if fd["field"] not in identity_fields:
                all_fields.append(fd)

    field_evidence: dict[str, list[dict]] = {}
    field_labels: dict[str, str] = {}
    for fd in all_fields:
        field_labels[fd["field"]] = fd.get("label", fd["field"])
        field_evidence[fd["field"]] = []

    # 扫描结果
    for r in results:
        for item in r.get("results", []):
            text = (
                (item.get("title", "") or "")
                + " " + (item.get("snippet", "") or "")
            ).lower()
            source_type = _get_source_type(item, pub_map)

            for fd in all_fields:
                field = fd["field"]
                match_kw = fd.get("match_keywords", [])
                label = fd.get("label", "").lower()
                kw_matched = any(kw in text for kw in match_kw) if match_kw else False

                if not (kw_matched or (label and label in text) or field in text):
                    continue

                quality, direction = _classify_evidence(text, source_type, field, kw_matched)
                field_evidence[field].append({
                    "source": item.get("source", "") or item.get("source_name", "") or "",
                    "title": (item.get("title", "") or "")[:100],
                    "quality": quality.value,
                    "direction": direction.value,
                })

    # 构建 claims
    claims = []
    for field in field_labels:
        ev_list = field_evidence[field]
        status = _aggregate_claim_status(ev_list)
        value = _infer_claim_value(ev_list, field)
        best = _best_quality(ev_list)
        summary = _build_summary(field_labels[field], value, status, best, len(ev_list))

        claims.append({
            "field": field,
            "label": field_labels[field],
            "value": value,
            "status": status.value,
            "evidence": ev_list[:10],
            "evidence_count": len(ev_list),
            "best_quality": best,
            "summary": summary,
        })

    return claims
