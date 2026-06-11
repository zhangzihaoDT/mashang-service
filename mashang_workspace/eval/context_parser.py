#!/usr/bin/env python
"""
Context Parser — 将用户自然语言转成结构化 context

输入:
    - user_text: 用户自然语言问题
    - previous_context: 上一轮 context (可选)

输出:
    - parsed_context: 从文本解析出的原始字段
    - resolved_context: 合并 inheritance 后的 context
    - inherited_context: 从上一轮继承的字段
    - overridden_context: 被覆盖的字段 (含 from→to)
    - missing_context: 缺失的关键字段
    - confidence: 解析置信度 (0.0~1.0)
    - parser_mode: "rule_based"

Phase 4 目标: context match rate >= 80%
"""

import re
from datetime import datetime, date, timedelta
from typing import Any

# ─── 1. Metric 规则 ──────────────────────────────────────────────────────────

METRIC_RULES: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"释放曲线"), "release_curve", 0.95),
    (re.compile(r"VOC|JTBD|主题分析"), "voc_theme", 0.95),
    (re.compile(r"预测锁单|cohort.*预测|成熟度"), "lock_forecast", 0.92),
    (re.compile(r"预测锁单|cohort.*预测|成熟度"), "cohort_forecast", 0.90),
    (re.compile(r"ATP|均价|平均开票|价格"), "atp_price", 0.90),
    (re.compile(r"增程占比趋势"), "reev_share_trend", 0.92),
    (re.compile(r"增程和纯电占比|增程和纯电|能源类型"), "lock_count_share", 0.88),
    (re.compile(r"占比|率[^字]|结构|份额"), "lock_count_share", 0.75),
    (re.compile(r"分布"), "lock_count_share", 0.60),
    (re.compile(r"锁单数|锁单量|锁单"), "lock_count", 0.85),
    (re.compile(r"预测"), "cohort_forecast", 0.60),
]

# ─── 2. Time Window 规则 ────────────────────────────────────────────────────

TIME_WINDOW_RULES: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"上市以来"), "since_launch", 0.95),
    (re.compile(r"昨天|昨日"), "yesterday", 0.95),
    (re.compile(r"今天|今日"), "today", 0.80),
    (re.compile(r"近\s*(\d+)\s*(天|日)"), "last_N_days", 0.90),  # special handler
    (re.compile(r"最近\s*(\d+)\s*(天|日)"), "last_N_days", 0.90),
    (re.compile(r"近\s*(\d+)\s*(周|星期)"), "last_N_weeks", 0.80),
    (re.compile(r"本月"), "this_month", 0.85),
    (re.compile(r"上月|上个月"), "last_month", 0.85),
]

SERIES_PATTERNS = [
    "LS8", "LS6", "L6", "L7", "LS9", "LS7",
    "ls8", "ls6", "l6", "l7", "ls9", "ls7",
]

# ─── 3. Group By 规则 ────────────────────────────────────────────────────────

GROUP_BY_RULES: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"增程.*纯电|纯电.*增程|能源类型|增程和纯电"), "energy_type", 0.95),
    (re.compile(r"车型结构|车型占比|分车型"), "model", 0.90),
    (re.compile(r"车系结构|车系占比|分车系"), "series", 0.85),
    (re.compile(r"城市分布|分城市|按城市"), "city", 0.90),
    (re.compile(r"大区|区域分布|分区域"), "region", 0.80),
    (re.compile(r"渠道分布|分渠道"), "channel", 0.80),
    (re.compile(r"JTBD|主题分布|按主题"), "jtbd_theme", 0.80),
]

# ─── 4. Filter 规则 ──────────────────────────────────────────────────────────

FILTER_RULES: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"只看大电池|大电池组"), "large_battery", 0.95),
    (re.compile(r"只看小电池|小电池组"), "small_battery", 0.90),
    (re.compile(r"只看.*增程|只查增程"), "energy_type_reev", 0.85),
    (re.compile(r"只看.*纯电|只查纯电"), "energy_type_bev", 0.85),
    (re.compile(r"只看.*五座|只查五座"), "seat_5", 0.85),
    (re.compile(r"只看.*六座|只查六座"), "seat_6", 0.85),
]

# ─── 5. Analysis Type 规则 ───────────────────────────────────────────────────

ANALYSIS_TYPE_RULES: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"释放曲线"), "release_curve", 0.93),
    (re.compile(r"回测|backtest"), "backtest", 0.90),
    (re.compile(r"同比|环比|对比|变化"), "compare", 0.80),
    (re.compile(r"趋势|走势|波动"), "trend", 0.75),
    (re.compile(r"占比|份额|share"), "share", 0.70),
]


def _match_rules(text: str, rules: list[tuple[re.Pattern, str, float]]) -> tuple[str | None, str | None, float]:
    """对 text 匹配规则，返回 (key, value, confidence)。"""
    best_key = None
    best_value = None
    best_conf = 0.0

    for pattern, value, conf in rules:
        m = pattern.search(text)
        if m:
            # special handling for last_N_days
            if value == "last_N_days" and m.lastindex and m.group(1):
                n = int(m.group(1))
                key = f"last_{n}_days"
                # validate reasonable range
                if 1 <= n <= 365:
                    return key, value, conf
                return key, value, conf * 0.5
            if value == "last_N_weeks" and m.lastindex and m.group(1):
                n = int(m.group(1)) * 7
                key = f"last_{n}_days"
                if 1 <= n <= 365:
                    return key, value, conf
                return key, value, conf * 0.5
            if conf > best_conf:
                best_key = value
                best_value = value
                best_conf = conf

    return best_key, best_value, best_conf


def _extract_series(text: str) -> tuple[str | None, float]:
    """从文本提取车系。"""
    for pat in SERIES_PATTERNS:
        if pat in text.upper():
            return pat.upper(), 0.95
    return None, 0.0


def _extract_model(text: str) -> tuple[str | None, float]:
    """从文本提取车型特征词。"""
    model_pats = [
        (re.compile(r"(?:新一代|全新)\s*智己\s*(LS[689]|L[67])\s*(\d+)"), 0.90),
        (re.compile(r"(LS[689]|L[67])\s*(\d+)"), 0.85),
    ]
    for pattern, conf in model_pats:
        m = pattern.search(text.upper())
        if m:
            return m.group(0).strip(), conf
    return None, 0.0


def _extract_city(text: str) -> tuple[str | None, float]:
    """从文本提取城市名。"""
    city_pats = [
        (re.compile(r"(?:只看|在|位于)\s*(上海|北京|深圳|广州|成都|杭州|武汉|西安|南京|重庆|苏州|天津|长沙|郑州|东莞|青岛|合肥|佛山|宁波|昆明|沈阳|大连|厦门|福州|哈尔滨|济南|温州|南宁|贵阳|南昌|太原|海口|长春|兰州|银川|西宁|拉萨|乌鲁木齐|常州|南通|嘉兴|绍兴|泉州|潍坊|烟台|珠海|中山|惠州|徐州|唐山|洛阳|襄阳|芜湖)"), 0.90),
    ]
    for pattern, conf in city_pats:
        m = pattern.search(text)
        if m:
            return m.group(1), conf
    return None, 0.0


def _resolve_result_reference(text: str, previous_result_context: dict | None,
                               prev_ctx: dict | None = None) -> dict | None:
    """
    从文本中解析结果引用，支持消歧处理。
    返回 result_reference dict 或 None。
    """
    if not previous_result_context:
        return None
    top_entities = previous_result_context.get("top_entities", [])
    if not top_entities:
        return None

    # ── 排名引用 ──
    if re.search(r"排名第一|最高的|上面第一个|第一名|Top\s*[1一]", text):
        e = top_entities[0]
        return {
            "status": "resolved",
            "type": "rank_reference",
            "rank": 1,
            "resolved_entity": {"field": e.get("field"), "value": e.get("value")},
            "resolved": {"field": e.get("field"), "value": e.get("value")},
            "source": e,
        }

    # ── 实体代指 ──
    if re.search(r"刚才那个|上面那个|那个车型|那个车系", text):
        e = top_entities[0]
        return {
            "status": "resolved",
            "type": "entity_reference",
            "resolved_entity": {"field": e.get("field"), "value": e.get("value")},
            "resolved": {"field": e.get("field"), "value": e.get("value")},
            "source": e,
        }

    # ── 数量代指：这 N 个/单/条/笔/台/辆 ──
    m = re.search(r"这\s*(\d+)\s*(个|单|条|笔|台|辆)", text)
    if not m:
        return None

    target_val = int(m.group(1))

    # 找出所有匹配 top_entities
    candidates = []
    for entity in top_entities:
        metrics = entity.get("metrics", {})
        for v in metrics.values():
            if isinstance(v, (int, float)) and abs(v - target_val) < 1:
                candidates.append(entity)
                break

    if not candidates:
        return {
            "status": "no_match",
            "type": "metric_value_reference",
            "value": target_val,
            "available_values": [e.get("metrics", {}) for e in top_entities],
        }

    if len(candidates) == 1:
        e = candidates[0]
        return {
            "status": "resolved",
            "type": "metric_value_reference",
            "value": target_val,
            "resolved_entity": {"field": e.get("field"), "value": e.get("value")},
            "resolved": {"field": e.get("field"), "value": e.get("value")},
            "source": e,
        }

    # ── 多候选消歧 ──
    # 1. 文本中是否显式包含车系
    text_series, _ = _extract_series(text)
    if text_series:
        for c in candidates:
            if c.get("value") == text_series or (c.get("field") == "series" and c.get("value") == text_series):
                return {
                    "status": "resolved",
                    "type": "metric_value_reference",
                    "value": target_val,
                    "disambiguation": "explicit_series_in_text",
                    "resolved_entity": {"field": c.get("field"), "value": c.get("value")},
                    "resolved": {"field": c.get("field"), "value": c.get("value")},
                    "source": c,
                }

    # 2. previous_context 中是否带有明确的 series
    if prev_ctx and prev_ctx.get("series"):
        for c in candidates:
            if c.get("value") == prev_ctx["series"]:
                return {
                    "status": "resolved",
                    "type": "metric_value_reference",
                    "value": target_val,
                    "disambiguation": "previous_context_series",
                    "resolved_entity": {"field": c.get("field"), "value": c.get("value")},
                    "resolved": {"field": c.get("field"), "value": c.get("value")},
                    "source": c,
                }

    # 3. 无法消歧 → ambiguous
    question = "你指的是"
    for i, c in enumerate(candidates):
        val = c.get("value", "?")
        metric_str = ", ".join(f"{k}={v}" for k, v in c.get("metrics", {}).items())
        question += f"「{val}（{metric_str}）」"
        if i < len(candidates) - 1:
            question += "，还是"
    question += "？"

    return {
        "status": "ambiguous",
        "type": "metric_value_reference",
        "value": target_val,
        "candidates": candidates,
        "need_clarification": True,
        "clarification_question": question,
    }


def parse_context(user_text: str, previous_context: dict | None = None,
                  previous_result_context: dict | None = None) -> dict:
    """
    解析用户自然语言 → 结构化 context。

    Args:
        user_text: 用户输入（中文自然语言）
        previous_context: 上一轮的 resolved_context（用于字段继承）
        previous_result_context: 上一轮的 followup_context（用于结果引用）

    Returns:
        包含 parsed/resolved/inherited/overridden/missing 等字段的 dict
    """
    text = user_text.strip()
    if not text:
        return {
            "raw_text": text,
            "parsed_context": {},
            "resolved_context": {},
            "inherited_context": {},
            "overridden_context": {},
            "missing_context": {"metric": "no input", "time_window": "no input"},
            "confidence": 0.0,
            "parser_mode": "rule_based",
            "warnings": [],
        }

    parsed: dict[str, Any] = {}
    confidences: dict[str, float] = {}
    warnings: list[str] = []

    # 1. Metric
    m_key, m_val, m_conf = _match_rules(text, METRIC_RULES)
    if m_key:
        parsed["metric"] = m_key
        confidences["metric"] = m_conf

    # 2. Time Window
    t_key, t_val, t_conf = _match_rules(text, TIME_WINDOW_RULES)
    if t_key:
        parsed["time_window"] = t_key
        confidences["time_window"] = t_conf

    # 3. Series
    series, series_conf = _extract_series(text)
    if series:
        parsed["series"] = series
        confidences["series"] = series_conf

    # 4. Model
    model, model_conf = _extract_model(text)
    if model:
        parsed["model"] = model
        confidences["model"] = model_conf

    # 5. City
    city, city_conf = _extract_city(text)
    if city:
        parsed["city"] = city
        confidences["city"] = city_conf

    # 6. Group By
    g_key, g_val, g_conf = _match_rules(text, GROUP_BY_RULES)
    if g_key:
        parsed["group_by"] = g_key
        confidences["group_by"] = g_conf
    elif "分布" in text:
        # "城市分布" → city, "车型分布" → model
        if re.search(r"城市|区域|大区", text):
            parsed["group_by"] = "city"
            confidences["group_by"] = 0.60
        elif re.search(r"车型|车系", text):
            parsed["group_by"] = "model"
            confidences["group_by"] = 0.60

    # 7. Filter
    f_key, f_val, f_conf = _match_rules(text, FILTER_RULES)
    if f_key:
        parsed.setdefault("filters", [])
        if f_key not in parsed["filters"]:
            parsed["filters"].append(f_key)
        confidences["filter"] = f_conf


    # 8. Analysis Type (after metric to handle context)
    a_key, a_val, a_conf = _match_rules(text, ANALYSIS_TYPE_RULES)
    if a_key:
        parsed["analysis_type"] = a_key
        confidences["analysis_type"] = a_conf
    # 趋势 + 占比/份额 → share_trend (override plain trend)
    if re.search(r"趋势", text) and re.search(r"占比|份额", text):
        parsed["analysis_type"] = "share_trend"
        confidences["analysis_type"] = 0.85
    # cohort 预测
    if not parsed.get("analysis_type") and re.search(r"cohort|预测", text):
        parsed["analysis_type"] = "cohort_forecast"
        confidences["analysis_type"] = 0.75

    # ─── 上下文继承 ──────────────────────────────────────────────────────
    prev = previous_context or {}
    resolved = dict(parsed)
    inherited = {}
    overridden = {}

    inherit_fields = {"metric", "series", "model", "city", "time_window",
                      "group_by", "analysis_type", "limit"}

    for field in inherit_fields:
        if field in parsed:
            # Check if it's an override from previous
            if field in prev and prev[field] != parsed[field]:
                overridden[field] = {"from": prev[field], "to": parsed[field]}
            resolved[field] = parsed[field]
        elif field in prev and prev[field] is not None:
            inherited[field] = prev[field]
            resolved[field] = prev[field]

    # Filters: additive
    parsed_filters = parsed.get("filters", [])
    prev_filters = prev.get("filters", []) if isinstance(prev.get("filters"), list) else []
    all_filters = list(prev_filters)
    for f in parsed_filters:
        if f not in all_filters:
            all_filters.append(f)
    if all_filters:
        resolved["filters"] = all_filters
    # Track inherited filters
    if prev_filters and not parsed_filters:
        inherited["filters"] = prev_filters

    # ─── Missing Context (moved before result_reference for access) ────
    missing = {}
    if not resolved.get("metric"):
        missing["metric"] = "not parsed from text"
    if not resolved.get("time_window"):
        missing["time_window"] = "not parsed from text"

    # 7b. Result Reference (after resolved is available for prev_ctx)
    result_ref = _resolve_result_reference(text, previous_result_context, prev_ctx=resolved)
    if result_ref:
        parsed["result_reference"] = result_ref
        status = result_ref.get("status")
        if status == "resolved":
            entity = result_ref.get("resolved_entity", {})
            if entity.get("field") in ("series", "model") and "series" not in parsed:
                parsed["series"] = entity["value"]
                resolved["series"] = entity["value"]
                confidences["series"] = 0.85
        elif status == "ambiguous":
            missing["result_reference_disambiguation"] = result_ref.get("clarification_question", "多候选歧义")
        elif status == "no_match":
            warnings.append(f"结果引用 {result_ref.get('value')} 未匹配任何 top_entities")

    # 继承 filter_ref 和 limit
    for field in ("filter_ref", "limit"):
        if field not in parsed and field in prev and prev[field] is not None:
            inherited[field] = prev[field]
            resolved[field] = prev[field]

    # ─── Overall Confidence ─────────────────────────────────────────────
    if confidences:
        avg_conf = sum(confidences.values()) / len(confidences)
    else:
        avg_conf = 0.0
    # Penalize for missing critical fields
    if missing:
        avg_conf *= 0.5

    return {
        "raw_text": text,
        "parsed_context": dict(parsed),
        "resolved_context": dict(resolved),
        "inherited_context": inherited,
        "overridden_context": overridden,
        "missing_context": missing,
        "result_reference": parsed.get("result_reference"),
        "confidence": round(avg_conf, 3),
        "parser_mode": "rule_based",
        "warnings": warnings,
    }
