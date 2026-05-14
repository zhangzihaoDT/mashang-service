import re

from agent.state import AgentState


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
    elif any(k in q for k in ["分门店", "按门店"]):
        required["breakdown_dimension"] = "store"
    elif any(k in q for k in ["分大区", "按大区"]):
        required["breakdown_dimension"] = "region"
    elif any(k in q for k in ["分城市", "按城市"]):
        required["breakdown_dimension"] = "city"
    elif any(k in q for k in ["性别", "男女"]):
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


ANALYSIS_EVIDENCE_CONTRACT = {
    "trend": {
        "required_fact_types": ["trend_summary"],
        "finish_reason": "trend_summary_found",
    },
    "diagnosis": {
        "required_fact_types": ["trend_summary", "contribution_summary"],
        "finish_reason": "trend_and_contribution_found",
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


def infer_intent_from_question(question: str) -> str:
    q = (question or "").strip()
    if not q:
        return "unknown"
    q_ns = q.replace(" ", "")
    if any(k in q_ns for k in ["为什么", "原因", "怎么回事", "为何", "导致", "怎么导致", "如何导致"]):
        return "diagnosis"
    if any(k in q_ns for k in ["同比", "年同比", "环比", "周环比", "日环比"]):
        return "compare"
    if any(k in q_ns for k in ["趋势", "走势", "变化趋势", "波动"]):
        return "trend"
    if re.search(r"近\s*\d+\s*(日|天|周|月|年)", q_ns):
        return "trend"
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


def evaluate_state_readiness(state: AgentState) -> dict:
    loop = getattr(state, "loop", None)
    iteration = int(getattr(loop, "iteration", 0) or 0)
    max_steps = int(getattr(loop, "max_steps", 5) or 5)
    if iteration >= max_steps:
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
        missing = [t for t in required if isinstance(t, str) and t and not has_fact_type(state, t)]
        if not missing:
            return {
                "ready": True,
                "reason": str(contract.get("finish_reason") or "ready"),
                "missing_info": [],
                "recommended_next_action": "finish",
            }

        if intent == "diagnosis":
            if "trend_summary" in missing:
                return {
                    "ready": False,
                    "reason": "missing_trend_summary",
                    "missing_info": ["trend_summary"],
                    "recommended_next_action": "run_dsl",
                    "recommended_query": _rewrite_to_trend_query(getattr(state, "question", "")),
                }
            if "contribution_summary" in missing and has_fact_type(state, "trend_summary"):
                return {
                    "ready": False,
                    "reason": "missing_contribution_summary",
                    "missing_info": ["contribution_summary"],
                    "recommended_next_action": "run_dsl",
                    "recommended_query": f"{getattr(state, 'question', '')}；请按关键维度拆解下降贡献（例如车系/城市/门店），并给出主要贡献项。",
                }

        if intent == "trend":
            return {
                "ready": False,
                "reason": "missing_trend_summary",
                "missing_info": ["trend_summary"],
                "recommended_next_action": "run_dsl",
            }

        return {
            "ready": False,
            "reason": "missing_required_facts",
            "missing_info": missing,
            "recommended_next_action": "run_dsl",
        }

    if intent == "trend":
        if has_block_type(state, "trend_summary"):
            return {
                "ready": True,
                "reason": "trend_summary_found",
                "missing_info": [],
                "recommended_next_action": "finish",
            }
        return {
            "ready": False,
            "reason": "missing_trend_summary",
            "missing_info": ["trend_summary"],
            "recommended_next_action": "run_dsl",
        }

    if intent == "compare":
        if any(has_block_type(state, t) for t in ["yoy", "wow", "dod"]):
            return {
                "ready": True,
                "reason": "comparison_result_found",
                "missing_info": [],
                "recommended_next_action": "finish",
            }
        return {
            "ready": False,
            "reason": "missing_comparison_result",
            "missing_info": ["comparison_result"],
            "recommended_next_action": "run_dsl",
        }

    if intent == "diagnosis":
        has_trend = has_block_type(state, "trend_summary")
        has_contribution = has_block_type(state, "contribution_summary")
        if has_trend and has_contribution:
            return {
                "ready": True,
                "reason": "trend_and_contribution_found",
                "missing_info": [],
                "recommended_next_action": "finish",
            }
        if has_trend and not has_contribution:
            return {
                "ready": False,
                "reason": "missing_contribution_summary",
                "missing_info": ["contribution_summary"],
                "recommended_next_action": "run_dsl",
                "recommended_query": f"{getattr(state, 'question', '')}；请按关键维度拆解下降贡献（例如车系/城市/门店），并给出主要贡献项。",
            }
        return {
            "ready": False,
            "reason": "missing_trend_summary",
            "missing_info": ["trend_summary"],
            "recommended_next_action": "run_dsl",
            "recommended_query": _rewrite_to_trend_query(getattr(state, "question", "")),
        }

    has_any_result = bool(getattr(getattr(state, "memory", None), "facts", None) or getattr(getattr(state, "results", None), "structured_blocks", None) or [])
    if not has_any_result:
        return {
            "ready": False,
            "reason": "no_result",
            "missing_info": ["result"],
            "recommended_next_action": "run_dsl",
        }
    repair_count = int(getattr(getattr(state, "memory", None), "working_memory", {}).get("repair_count", 0))
    if repair_count >= 2:
        return {
            "ready": True,
            "reason": "repair_limit_reached",
            "missing_info": [],
            "recommended_next_action": "finish",
        }
    if result_satisfies_goal(state):
        return {
            "ready": True,
            "reason": "default_has_result_and_satisfies_goal",
            "missing_info": [],
            "recommended_next_action": "finish",
        }
    repair_query = _generate_repair_query(state)
    if repair_query:
        return {
            "ready": False,
            "reason": "result_does_not_satisfy_goal",
            "missing_info": ["result_quality"],
            "recommended_next_action": "run_dsl",
            "recommended_query": repair_query,
        }
    return {
        "ready": True,
        "reason": "default_has_result",
        "missing_info": [],
        "recommended_next_action": "finish",
    }
