import re

from agent.state import AgentState
from schema import MetricRegistry

_metric_registry = MetricRegistry()

_SERIES_TOKENS = ("LS9", "LS8", "LS7", "LS6", "L7", "L6")


def extract_required_slots(question: str) -> dict:
    q = (question or "").replace(" ", "")
    required: dict[str, str] = {}

    if any(k in q for k in ["按周", "每周", "周度", "逐周", "周别"]):
        required["time_grain"] = "week"
    elif any(k in q for k in ["按月", "每月", "月度", "逐月", "月别"]):
        required["time_grain"] = "month"
    elif any(k in q for k in ["按日", "每日", "日度", "逐日", "日别", "按天"]):
        required["time_grain"] = "day"

    if any(k in q for k in ["分车型", "按车型", "车型", "分车系", "按车系", "车系"]):
        required["breakdown_dimension"] = "model"
    elif any(k in q for k in ["分产品", "分产品名称", "按产品", "按产品名称", "产品名称", "product_name", "productname"]):
        required["breakdown_dimension"] = "product"
    elif any(k in q for k in ["分门店", "按门店"]):
        required["breakdown_dimension"] = "store"
    elif any(k in q for k in ["分大区", "按大区"]):
        required["breakdown_dimension"] = "region"
    elif any(k in q for k in ["分城市", "按城市", "分门店城市", "按门店城市", "分上牌城市", "按上牌城市"]):
        required["breakdown_dimension"] = "city"
    elif any(k in q for k in ["性别", "男女", "分性别", "按性别"]):
        required["breakdown_dimension"] = "gender"

    if any(k in q for k in ["锁单"]):
        required["metric"] = "lock_order_count"
    elif any(k in q for k in ["交付"]):
        required["metric"] = "delivery_count"

    if any(k in q for k in ["占比", "比例", "份额"]):
        required["post_metric"] = "share"

    return required


def _check_result_columns(result_text: str) -> list[str]:
    if not isinstance(result_text, str) or not result_text:
        return []
    lines = result_text.strip().split("\n")
    if not lines:
        return []
    return [c.strip() for c in lines[0].split() if c.strip()]


def _result_sample_values(result_text: str) -> dict[str, list[str]]:
    if not isinstance(result_text, str) or not result_text:
        return {}
    lines = result_text.strip().split("\n")
    if len(lines) < 2:
        return {}
    cols = _check_result_columns(result_text)
    if not cols:
        return {}
    samples: dict[str, list[str]] = {c: [] for c in cols}
    for line in lines[1:]:
        parts = line.split()
        for i, c in enumerate(cols):
            if i < len(parts):
                samples[c].append(parts[i])
    return samples


def result_satisfies_goal(state: AgentState) -> bool:
    question = getattr(state, "question", "") or ""
    required = extract_required_slots(question)
    if not required:
        return True

    blocks = getattr(getattr(state, "results", None), "structured_blocks", None)
    if not isinstance(blocks, list) or not blocks:
        return False

    for b in blocks:
        result_obj = getattr(b, "result", None)
        if result_obj is None:
            continue

        if isinstance(result_obj, str):
            cols = _check_result_columns(result_obj)
            result_str = result_obj
        elif isinstance(result_obj, dict):
            cols = list(result_obj.keys())
            result_str = None
        elif hasattr(result_obj, "columns"):
            cols = list(result_obj.columns)
            result_str = str(result_obj)
        else:
            continue

        if not cols:
            continue

        cols_lower = [c.lower() for c in cols]

        time_grain = required.get("time_grain")
        if time_grain:
            keywords = {"week": ["week", "w"], "month": ["month"], "day": ["day", "date"]}
            col_match = any(any(k in c for k in keywords.get(time_grain, [])) for c in cols_lower)
            if not col_match:
                if result_str:
                    samples = _result_sample_values(result_str)
                    value_match = False
                    for col_vals in samples.values():
                        combined = " ".join(col_vals)
                        if time_grain == "week" and re.search(r"第\s*\d+\s*周", combined):
                            value_match = True
                            break
                        if time_grain == "month" and re.search(r"\d+\s*月|第\s*\d+\s*月", combined):
                            value_match = True
                            break
                    if not value_match:
                        continue
                else:
                    continue

        if required.get("post_metric") == "share":
            if not any("占比" in c or "share" in c.lower() or "ratio" in c.lower() or "pct" in c.lower() for c in cols):
                continue

        if required.get("breakdown_dimension") == "model":
            if not any(c in cols for c in ["sub_model_name", "model_name", "config_name", "product_name"]):
                if not any("车型" in c or "model" in c.lower() or "product" in c.lower() or "config" in c.lower() for c in cols):
                    continue

        if required.get("breakdown_dimension") == "product":
            if not any("product_name" in c for c in cols):
                if not any("产品" in c for c in cols):
                    continue

        return True

    return False


def _generate_repair_query(state: AgentState) -> str | None:
    question = getattr(state, "question", "") or ""
    required = extract_required_slots(question)
    if not required:
        return None

    repair_parts = [question.rstrip("。；;")]
    if required.get("post_metric") == "share":
        repair_parts.append("需要包含每周期占比")
    if required.get("time_grain"):
        cn = {"week": "周", "month": "月", "day": "日"}
        repair_parts.append(f"按{cn.get(required['time_grain'], required['time_grain'])}分组")
    if required.get("breakdown_dimension"):
        repair_parts.append("需要包含拆解维度列")

    return "，".join(repair_parts) + "。"


# ── Evidence Contract 定稿表 ──────────────────────────────────────────
# intent                    required_fact_types
# ─────────────────────────────────────────────────────────────────────
# metric                    metric_value
# trend                     trend_summary
# compare                   comparison_result
# composition               dimension_breakdown
# share                     dimension_breakdown + share_summary
# time_grouped_share        time_grouped_metric + dimension_breakdown + share_summary
# ranking                   ranking_result
# distribution              distribution_summary
# diagnosis                 trend_summary + contribution_summary
# metric_ratio              metric_value + dimension_breakdown
# metric_ratio_trend        time_grouped_metric + trend_summary
# dimension_share           dimension_breakdown + share_summary
# dimension_share_trend     time_grouped_metric + share_summary + trend_summary
ANALYSIS_EVIDENCE_CONTRACT = {
    "metric": {
        "required_fact_types": ["metric_value"],
        "finish_reason": "metric_value_found",
        "repair_query_template": "{question}；请返回核心指标值。",
    },
    "trend": {
        "required_fact_types": ["trend_summary"],
        "finish_reason": "trend_summary_found",
        "repair_query_template": "{question}；请补充趋势摘要，包括方向、波动、峰谷和连续变化。",
    },
    "compare": {
        "required_fact_types": ["comparison_result"],
        "finish_reason": "comparison_result_found",
        "repair_query_template": "{question}；请补充对比结果，包括基准值、目标值、差值和变化率。",
    },
    "composition": {
        "required_fact_types": ["dimension_breakdown"],
        "finish_reason": "dimension_breakdown_found",
        "repair_query_template": "{question}；请按指定维度拆解结果。",
    },
    "share": {
        "required_fact_types": ["dimension_breakdown", "share_summary"],
        "finish_reason": "share_summary_found",
        "repair_query_template": "{question}；请补充分组明细和占比字段。",
    },
    "time_grouped_share": {
        "required_fact_types": [
            "time_grouped_metric",
            "dimension_breakdown",
            "share_summary",
        ],
        "finish_reason": "time_grouped_share_found",
        "repair_query_template": "{question}；请按时间粒度和拆解维度分组，并计算每个时间分组内的占比。",
    },
    "ranking": {
        "required_fact_types": ["ranking_result"],
        "finish_reason": "ranking_result_found",
        "repair_query_template": "{question}；请返回排序结果，包括排名、维度和指标值。",
    },
    "distribution": {
        "required_fact_types": ["distribution_summary"],
        "finish_reason": "distribution_summary_found",
        "repair_query_template": "{question}；请补充分布摘要，包括均值、中位数、分位数或区间分布。",
    },
    "diagnosis": {
        "required_fact_types": ["trend_summary", "contribution_summary"],
        "finish_reason": "trend_and_contribution_found",
        "repair_query_template": "{question}；请先给出趋势摘要，再按关键维度拆解贡献。",
    },
    "metric_ratio": {
        "required_fact_types": ["metric_value", "dimension_breakdown"],
        "finish_reason": "metric_ratio_found",
        "repair_query_template": "{question}；请返回派生比例指标的计算结果，包含分子、分母及比值。",
    },
    "metric_ratio_trend": {
        "required_fact_types": ["time_grouped_metric", "trend_summary"],
        "finish_reason": "metric_ratio_trend_found",
        "repair_query_template": "{question}；请按时间粒度返回派生比例指标的趋势，包含每日的分子、分母及比值。",
    },
    "dimension_share": {
        "required_fact_types": ["dimension_breakdown", "share_summary"],
        "finish_reason": "dimension_share_found",
        "repair_query_template": "{question}；请按维度分组返回占比。",
    },
    "dimension_share_trend": {
        "required_fact_types": ["time_grouped_metric", "share_summary", "trend_summary"],
        "finish_reason": "dimension_share_trend_found",
        "repair_query_template": "{question}；请按时间粒度返回该维度成员的每日占比及趋势。",
    },
    "time_grouped_share_breakdown": {
        "required_fact_types": ["time_grouped_metric", "dimension_breakdown", "share_summary"],
        "finish_reason": "time_grouped_share_breakdown_found",
        "repair_query_template": "{question}；请按时间粒度返回每个拆分维度的占比。",
    },
}


def has_fact_type(state: AgentState, fact_type: str) -> bool:
    if not isinstance(fact_type, str) or not fact_type:
        return False
    facts = getattr(getattr(state, "memory", None), "facts", None)
    if not isinstance(facts, list) or not facts:
        return False
    for f in facts:
        if isinstance(f, dict) and f.get("fact_type") == fact_type:
            return True
    return False


def has_block_type(state: AgentState, block_type: str) -> bool:
    if not isinstance(block_type, str) or not block_type:
        return False
    blocks = getattr(getattr(state, "results", None), "structured_blocks", None)
    if not isinstance(blocks, list) or not blocks:
        return False
    for b in blocks:
        if getattr(b, "block_type", None) != block_type:
            continue
        status = getattr(b, "status", None)
        if status in {"ok", "success"}:
            return True
    return False


def _infer_series_tokens(q: str) -> list[str]:
    q_upper = q.upper()
    tokens = []
    for s in _SERIES_TOKENS:
        if s in q_upper:
            tokens.append(s)
    return list(dict.fromkeys(tokens))


def infer_intent_from_question(question: str) -> str:
    q = (question or "").strip()
    if not q:
        return "unknown"

    q_ns = q.replace(" ", "")

    # ── 优先：诊断 ──
    if any(k in q_ns for k in ["为什么", "原因", "怎么回事", "为何", "导致", "怎么导致", "如何导致"]):
        return "diagnosis"

    # ── Tier 1: MetricRegistry 匹配（指标比值 / 转化率 / 渗透率）──
    has_ratio_keyword = any(k in q_ns for k in ["占比", "比例", "率", "份额"])
    if has_ratio_keyword:
        pair = _metric_registry.match_metric_relation(q)
        if pair:
            has_trend = any(k in q_ns for k in ["趋势", "走势", "波动", "近", "日", "周", "月"])
            return "metric_ratio_trend" if has_trend else "metric_ratio"

    # ── Tier 2: 单一维度成员占比（如 "LS6 锁单占比" — series 成员 vs 总体）──
    #    保护: 必须含 "占比/份额"（不含 "率/转化率/渗透率"），且 Tier 1 已排除 metric_relation
    has_rate_excl = any(k in q_ns for k in ["率"])
    if has_ratio_keyword and not has_rate_excl:
        series_tokens = _infer_series_tokens(q)
        has_metric_keyword = any(k in q_ns for k in ["锁单", "交付", "开票", "小订", "大定", "订单", "下发线索", "在营门店", "留存"])
        if series_tokens and has_metric_keyword:
            has_trend = any(k in q_ns for k in ["趋势", "走势", "波动", "近", "日", "周", "月"])
            return "dimension_share_trend" if has_trend else "dimension_share"

    # ── Tier 3: 多成员构成占比 —— share_breakdown / time_grouped_share_breakdown ──
    #    "各渠道占比" → share_breakdown
    #    "每周分车系占比" → time_grouped_share_breakdown
    has_each = any(k in q_ns for k in ["各", "每"])
    has_time_group = any(k in q_ns for k in [
        "按周", "每周", "周度", "逐周", "周别",
        "按月", "每月", "月度", "逐月", "月别",
        "按日", "每日", "日度", "逐日", "日别", "按天",
    ])
    has_breakdown = any(k in q_ns for k in [
        "分车型", "按车型", "车型",
        "分车系", "按车系", "车系",
        "分门店", "按门店",
        "分大区", "按大区",
        "分城市", "按城市",
        "分渠道", "按渠道", "渠道",
        "分省份", "按省份",
        "性别", "男女",
        # product_name
        "分产品", "分产品名称", "按产品", "按产品名称",
        "产品名称", "产品名", "productname", "product_name",
        # store_city / license_city / gender
        "分门店城市", "按门店城市", "分上牌城市", "按上牌城市",
        "分性别", "按性别",
    ])
    has_share = any(k in q_ns for k in ["占比", "比例", "份额", "构成", "结构"])

    if has_time_group and has_breakdown and has_share and has_each:
        return "time_grouped_share_breakdown"
    if has_time_group and has_breakdown and has_share:
        return "time_grouped_share"
    if has_time_group and has_breakdown:
        return "composition"
    if has_breakdown and has_share and has_each:
        return "share_breakdown"
    if has_breakdown and has_share:
        return "share"
    if has_breakdown:
        return "composition"
    if has_share:
        return "share"

    # ── Tier 4: 对比 ──
    if any(k in q_ns for k in ["同比", "年同比", "环比", "周环比", "日环比", "对比", "相比", "vs", "VS"]):
        return "compare"

    # ── Tier 5: 排名 ──
    if any(k in q_ns for k in ["TOP", "Top", "top", "排名", "排行", "最高", "最低", "前十", "前10"]):
        return "ranking"

    # ── Tier 6: 分布 ──
    if any(k in q_ns for k in ["分布", "分位", "中位数", "均值", "平均值", "标准差"]):
        return "distribution"

    # ── Tier 7: 趋势 ──
    if any(k in q_ns for k in ["趋势", "走势", "变化趋势", "波动"]):
        return "trend"

    if re.search(r"近\s*\d+\s*(日|天|周|月|年)", q_ns):
        return "trend"

    # ── Tier 8: 简单指标查询 ──
    if any(k in q_ns for k in ["多少", "是多少", "总数", "合计", "数量", "总量", "总共有"]):
        return "metric"

    return "unknown"


def _rewrite_to_trend_query(question: str) -> str:
    q = (question or "").strip()
    if not q:
        return q
    q = q.replace("？", "?").replace("?", "")
    for token in ["为什么", "原因", "怎么回事", "为何", "导致", "怎么导致", "如何导致"]:
        if token in q:
            q = q.split(token, 1)[0]
    q = q.strip()
    if not q:
        return question
    if "趋势" in q or "走势" in q:
        return q
    return f"{q}趋势"


def latest_intent(state: AgentState) -> str:
    planning = getattr(state, "planning", None)
    if planning is not None:
        records = getattr(planning, "records", None)
        if isinstance(records, list) and records:
            last = records[-1]
            if isinstance(last, dict) and isinstance(last.get("analysis_intent"), str) and last.get("analysis_intent"):
                return str(last.get("analysis_intent"))
    return infer_intent_from_question(getattr(state, "question", ""))


def _contract_repair_query(state: AgentState, contract: dict, missing: list[str]) -> str:
    question = getattr(state, "question", "") or ""
    template = contract.get("repair_query_template")
    if isinstance(template, str) and template:
        return template.format(
            question=question,
            missing="、".join(missing),
        )
    return f"{question}；当前缺少必要证据：{'、'.join(missing)}，请补充后再回答。"


def _available_fact_types(state: AgentState) -> list[str]:
    facts = getattr(getattr(state, "memory", None), "facts", None)
    if not isinstance(facts, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for f in facts:
        if isinstance(f, dict):
            ft = f.get("fact_type")
            if isinstance(ft, str) and ft not in seen:
                seen.add(ft)
                out.append(ft)
    return out


def _debug_decision_line(
    question: str,
    intent: str,
    required: list[str],
    available: list[str],
    missing: list[str],
    action: str,
    finish_reason: str,
) -> None:
    q = (question or "")[:50].replace("|", "/").replace("\n", " ")
    r = ",".join(required) if required else "-"
    a = ",".join(available) if available else "-"
    m = ",".join(missing) if missing else "-"
    print(f"[Eval] {q} | {intent} | {r} | {a} | {m} | {action} | {finish_reason}")


def evaluate_state_readiness(state: AgentState) -> dict:
    loop = getattr(state, "loop", None)
    iteration = int(getattr(loop, "iteration", 0) or 0)
    max_steps = int(getattr(loop, "max_steps", 5) or 5)
    question = getattr(state, "question", "") or ""

    if iteration >= max_steps:
        _debug_decision_line(question, "unknown", [], [], [], "finish", "max_steps_reached")
        return {
            "ready": True,
            "reason": "max_steps_reached",
            "missing_info": [],
            "recommended_next_action": "finish",
        }

    intent = latest_intent(state)

    contract = ANALYSIS_EVIDENCE_CONTRACT.get(intent) if isinstance(intent, str) else None
    if isinstance(contract, dict):
        required = contract.get("required_fact_types")
        if not isinstance(required, list):
            required = []
        available = _available_fact_types(state)
        missing = [t for t in required if isinstance(t, str) and t and t not in available]
        print(f"[RuntimeDecision] inferred_intent={intent}")
        print(f"[RuntimeDecision] required_fact_types={required}")
        print(f"[RuntimeDecision] available_fact_types={available}")
        print(f"[RuntimeDecision] missing_fact_types={missing}")

        working = getattr(getattr(state, "memory", None), "working_memory", None)
        if isinstance(working, dict) and iteration >= 2 and missing:
            last_missing = working.get("_last_missing_facts")
            if isinstance(last_missing, list) and set(last_missing) == set(missing):
                working["_stall_count"] = (working.get("_stall_count") or 0) + 1
            else:
                working["_stall_count"] = 0
            working["_last_missing_facts"] = missing
            if (working.get("_stall_count") or 0) >= 2:
                print(f"[RuntimeDecision] stall detected: {missing} persisted {working['_stall_count']+1}x → force-finish")
                _debug_decision_line(question, intent, required, available, missing, "finish", "stall_detected")
                return {
                    "ready": True,
                    "reason": "stall_detected",
                    "missing_info": missing,
                    "recommended_next_action": "finish",
                }
        elif isinstance(working, dict):
            working["_last_missing_facts"] = missing
            working["_stall_count"] = 0

        if not missing:
            finish_reason = str(contract.get("finish_reason") or "ready")
            _debug_decision_line(question, intent, required, available, missing, "finish", finish_reason)
            return {
                "ready": True,
                "reason": finish_reason,
                "missing_info": [],
                "recommended_next_action": "finish",
            }
        missing_str = "_and_".join(missing)
        _debug_decision_line(question, intent, required, available, missing, "run_dsl", missing_str)
        return {
            "ready": False,
            "reason": f"missing_{missing_str}",
            "missing_info": missing,
            "recommended_next_action": "run_dsl",
            "recommended_query": _contract_repair_query(state, contract, missing),
        }

    has_any_result = bool(getattr(getattr(state, "memory", None), "facts", None) or getattr(getattr(state, "results", None), "structured_blocks", None) or [])
    if not has_any_result:
        _debug_decision_line(question, intent, [], [], [], "run_dsl", "no_result")
        return {
            "ready": False,
            "reason": "no_result",
            "missing_info": ["result"],
            "recommended_next_action": "run_dsl",
        }
    repair_count = int(getattr(getattr(state, "memory", None), "working_memory", {}).get("repair_count", 0))
    if repair_count >= 2:
        _debug_decision_line(question, intent, [], [], [], "finish", "repair_limit_reached")
        return {
            "ready": True,
            "reason": "repair_limit_reached",
            "missing_info": [],
            "recommended_next_action": "finish",
        }
    if result_satisfies_goal(state):
        _debug_decision_line(question, intent, [], [], [], "finish", "goal_satisfied")
        return {
            "ready": True,
            "reason": "default_has_result_and_satisfies_goal",
            "missing_info": [],
            "recommended_next_action": "finish",
        }
    repair_query = _generate_repair_query(state)
    if repair_query:
        _debug_decision_line(question, intent, [], [], [], "run_dsl", "goal_not_satisfied")
        return {
            "ready": False,
            "reason": "result_does_not_satisfy_goal",
            "missing_info": ["result_quality"],
            "recommended_next_action": "run_dsl",
            "recommended_query": repair_query,
        }
    _debug_decision_line(question, intent, [], [], [], "finish", "default_has_result")
    return {
        "ready": True,
        "reason": "default_has_result",
        "missing_info": [],
        "recommended_next_action": "finish",
    }
