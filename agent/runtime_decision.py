import re

from agent.state import AgentState


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
    return {
        "ready": bool(has_any_result),
        "reason": "default_has_result" if has_any_result else "no_result",
        "missing_info": [] if has_any_result else ["result"],
        "recommended_next_action": "finish" if has_any_result else "run_dsl",
    }
