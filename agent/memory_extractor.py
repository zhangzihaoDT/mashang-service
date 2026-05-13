import datetime
import json

from openai import OpenAI

from agent.llm_config import DEEPSEEK_CHAT_MODEL
from agent.state import AgentState


def _extract_json_content(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return raw


def _sanitize_facts(
    facts: object,
    structured_blocks_payload: list[dict],
) -> tuple[list[dict], dict]:
    missing_info: dict = {}
    if not isinstance(facts, list):
        return ([], {"invalid_facts_type": {"expected": "list", "got": str(type(facts).__name__)}})

    allowed_fact_types = set()
    allowed_block_ids = set()
    for b in structured_blocks_payload:
        if not isinstance(b, dict):
            continue
        bid = b.get("block_id")
        btype = b.get("block_type")
        if isinstance(bid, str) and bid:
            allowed_block_ids.add(bid)
        if isinstance(btype, str) and btype:
            allowed_fact_types.add(btype)

    cleaned: list[dict] = []
    dropped: list[dict] = []
    for f in facts:
        if not isinstance(f, dict) or not f:
            continue
        src_obj = f.get("source") if isinstance(f.get("source"), dict) else {}
        src = src_obj.get("block_id") or f.get("source_block_id")
        ftype = f.get("fact_type")
        if not isinstance(src, str) or not src:
            dropped.append({"reason": "missing_source_block_id", "fact": f})
            continue
        if allowed_block_ids and src not in allowed_block_ids:
            dropped.append({"reason": "unknown_source_block_id", "fact": f})
            continue
        if not isinstance(ftype, str) or not ftype:
            dropped.append({"reason": "missing_fact_type", "fact": f})
            continue
        if allowed_fact_types and ftype not in allowed_fact_types:
            dropped.append({"reason": "unsupported_fact_type", "fact": f})
            continue
        if not isinstance(f.get("source"), dict):
            f["source"] = {"block_id": src}
        if f.get("values") is not None and not isinstance(f.get("values"), dict):
            dropped.append({"reason": "invalid_values_type", "fact": f})
            continue
        if f.get("conclusion") is not None and not isinstance(f.get("conclusion"), dict):
            dropped.append({"reason": "invalid_conclusion_type", "fact": f})
            continue
        cleaned.append(f)

    if dropped:
        missing_info["dropped_facts"] = dropped[:20]
    return (cleaned, missing_info)


def _build_deterministic_facts(state: AgentState, limit_blocks: int = 3) -> list[dict]:
    out: list[dict] = []
    blocks = getattr(getattr(state, "results", None), "structured_blocks", None)
    if not isinstance(blocks, list) or not blocks:
        return []
    for b in blocks[-limit_blocks:]:
        result = getattr(b, "result", None)
        plan = getattr(b, "plan", None)
        if not isinstance(result, dict) or not isinstance(plan, dict):
            continue
        metric = result.get("metric_alias") or result.get("metric") or ""
        dataset = plan.get("dataset")
        time = plan.get("time") if isinstance(plan.get("time"), dict) else {}
        start = time.get("start")
        end = time.get("end")
        block_id = getattr(b, "block_id", None)
        window_days = result.get("window_days")
        label = None
        if isinstance(window_days, int) and window_days > 0:
            label = f"近{window_days}日"

        if getattr(b, "block_type", None) == "trend_summary":
            direction = result.get("direction")
            out.append(
                {
                    "fact_id": f"fact_{block_id}_trend_summary_{metric}",
                    "fact_type": "trend_summary",
                    "metric": metric,
                    "dataset": dataset,
                    "dimension": None,
                    "time_range": {
                        "start": start,
                        "end": end,
                        "grain": "day",
                        "label": label,
                    },
                    "values": {
                        "slope": result.get("slope"),
                        "total_change": result.get("total_change"),
                        "latest_value": result.get("latest"),
                        "mean": result.get("mean"),
                        "median": result.get("median"),
                        "std": result.get("std"),
                        "cv": result.get("cv"),
                        "max_value": result.get("max_value"),
                        "min_value": result.get("min_value"),
                    },
                    "conclusion": {
                        "direction": direction,
                        "latest_position": result.get("latest_position"),
                        "latest_percentile_rank": result.get("latest_percentile_rank"),
                        "streak_direction": result.get("streak_direction"),
                        "streak_length": result.get("streak_length"),
                        "recent_direction": result.get("recent_direction"),
                    },
                    "source": {
                        "block_id": block_id,
                        "step": getattr(b, "step", None),
                        "block_type": getattr(b, "block_type", None),
                        "route": (getattr(b, "execution_meta", None) or {}).get("route") if isinstance(getattr(b, "execution_meta", None), dict) else None,
                    },
                    "evidence_type": "descriptive_trend",
                }
            )
        if getattr(b, "block_type", None) == "contribution_summary":
            dim_field = result.get("dimension_field")
            rows = result.get("rows")
            top_contributors: list[dict] = []
            if isinstance(dim_field, str) and isinstance(rows, list):
                for r in rows[:5]:
                    if not isinstance(r, dict):
                        continue
                    top_contributors.append(
                        {
                            dim_field: r.get("dimension"),
                            "delta": r.get("delta"),
                            "contribution_share": r.get("contribution_share"),
                        }
                    )
            others = result.get("others") if isinstance(result.get("others"), dict) else {}
            top10_share = None
            others_share = None
            if isinstance(result.get("total_delta"), (int, float)) and isinstance(rows, list):
                total_delta = float(result.get("total_delta") or 0.0)
                top_delta = float(sum(float((r.get("delta") or 0.0)) for r in rows[:10] if isinstance(r, dict)))
                top10_share = None if total_delta == 0.0 else float(top_delta / total_delta)
                others_share = others.get("contribution_share")
            conclusion = None
            if isinstance(dim_field, str) and top10_share is not None and others_share is not None:
                conclusion = f"按{dim_field}拆解，前10项合计贡献总变化的{top10_share:.1%}，其余项合计贡献{others_share:.1%}。"

            baseline_period = result.get("baseline_period") if isinstance(result.get("baseline_period"), dict) else {}
            target_period = result.get("target_period") if isinstance(result.get("target_period"), dict) else {}
            if not baseline_period and isinstance(result.get("first_date"), str):
                try:
                    first_date = datetime.date.fromisoformat(str(result.get("first_date"))[:10])
                    baseline_period = {"start": first_date.isoformat(), "end": (first_date + datetime.timedelta(days=1)).isoformat()}
                except Exception:
                    baseline_period = {}
            if not target_period and isinstance(result.get("last_date"), str):
                try:
                    last_date = datetime.date.fromisoformat(str(result.get("last_date"))[:10])
                    target_period = {"start": last_date.isoformat(), "end": (last_date + datetime.timedelta(days=1)).isoformat()}
                except Exception:
                    target_period = {}
            out.append(
                {
                    "fact_id": f"fact_{block_id}_contribution_summary_{metric}_{dim_field}",
                    "fact_type": "contribution_summary",
                    "metric": metric,
                    "dataset": dataset,
                    "dimension": dim_field,
                    "time_range": {
                        "start": start,
                        "end": end,
                        "grain": "day",
                        "label": label,
                    },
                    "values": {
                        "comparison_method": result.get("comparison_method") or "first_vs_last",
                        "baseline_period": baseline_period or None,
                        "target_period": target_period or None,
                        "first_total": result.get("first_total"),
                        "last_total": result.get("last_total"),
                        "total_delta": result.get("total_delta"),
                        "top10_contribution_share": top10_share,
                        "others_contribution_share": others_share,
                        "top_contributors": top_contributors,
                    },
                    "conclusion": {
                        "summary": conclusion,
                        "evidence_type": "descriptive_contribution",
                    },
                    "source": {
                        "block_id": block_id,
                        "step": getattr(b, "step", None),
                        "block_type": getattr(b, "block_type", None),
                        "route": (getattr(b, "execution_meta", None) or {}).get("route") if isinstance(getattr(b, "execution_meta", None), dict) else None,
                    },
                    "evidence_type": "descriptive_contribution",
                }
            )
    return out


def _compact_structured_blocks(state: AgentState, limit_blocks: int = 3) -> list[dict]:
    blocks = []
    raw = getattr(getattr(state, "results", None), "structured_blocks", None)
    if not isinstance(raw, list) or not raw:
        return []
    for b in raw[-limit_blocks:]:
        block_id = getattr(b, "block_id", None)
        step = getattr(b, "step", None)
        block_type = getattr(b, "block_type", None)
        status = getattr(b, "status", None)
        question = getattr(b, "question", None)
        statistics = getattr(b, "statistics", None)
        execution_meta = getattr(b, "execution_meta", None)
        error = getattr(b, "error", None)
        result = getattr(b, "result", None)

        compact = {
            "block_id": block_id,
            "step": step,
            "block_type": block_type,
            "status": status,
            "question": question,
            "statistics": statistics if isinstance(statistics, dict) else None,
            "execution_meta": execution_meta if isinstance(execution_meta, dict) else {},
            "error": error,
        }
        if isinstance(result, dict):
            for key in ["type", "window_days", "latest", "mean", "median", "total_change", "direction", "slope"]:
                if key in result:
                    compact.setdefault("result_summary", {})[key] = result.get(key)
        blocks.append(compact)
    return blocks


def extract_memory_update(client: OpenAI, state: AgentState, last_result: str) -> dict:
    facts_payload = json.dumps(state.memory.facts, ensure_ascii=False)
    working_payload = json.dumps(state.memory.working_memory, ensure_ascii=False)
    compact_structured = _compact_structured_blocks(state)
    structured_payload = json.dumps(compact_structured, ensure_ascii=False)
    deterministic_facts = _build_deterministic_facts(state)
    deterministic_facts_payload = json.dumps(deterministic_facts, ensure_ascii=False)
    messages = [
        {
            "role": "system",
            "content": (
                "你是记忆抽取器。"
                "请从当前执行结果中提取可复用结论 facts，并更新 working_memory。"
                "只输出 JSON，格式: "
                "{\"facts\": [...], \"working_memory_update\": {...}, \"missing_info\": {...}}。"
                "只抽取已经由 structured_blocks 支持的事实。"
                "不要推测。"
                "不要复述完整执行结果。"
                "facts 必须是数组，每个元素是一个 Fact（字典）。"
                "每条 fact 必须包含 source 对象，且 source.block_id 必须来自 structured_blocks.block_id。"
                "每条 fact 尽量包含 fact_type / metric / dataset / dimension / time_range / values / conclusion / evidence_type。"
                "如果信息不足，写入 missing_info，而不是编造 fact。"
                "不要编造，不要重复已有事实。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"目标:\n{state.question}\n\n"
                f"已有 facts:\n{facts_payload}\n\n"
                f"已有 working_memory:\n{working_payload}\n\n"
                f"structured_blocks（最近几条，供抽取事实）:\n{structured_payload}\n\n"
                f"deterministic_facts（可直接复用/补全）:\n{deterministic_facts_payload}\n\n"
                f"当前结果:\n{str(last_result or '')}\n\n"
                "请输出 JSON。"
            ),
        },
    ]
    try:
        response = client.chat.completions.create(model=DEEPSEEK_CHAT_MODEL, messages=messages)
        content = str(response.choices[0].message.content or "")
        parsed = json.loads(_extract_json_content(content))
        if isinstance(parsed, dict):
            facts = parsed.get("facts")
            cleaned, sanitize_missing = _sanitize_facts(facts, compact_structured)
            if not cleaned and deterministic_facts:
                parsed["facts"] = deterministic_facts
            else:
                parsed["facts"] = cleaned
            missing_info = parsed.get("missing_info")
            if not isinstance(missing_info, dict):
                missing_info = {}
            for k, v in sanitize_missing.items():
                if k not in missing_info:
                    missing_info[k] = v
            parsed["missing_info"] = missing_info
            if not isinstance(parsed.get("working_memory_update"), dict):
                parsed["working_memory_update"] = {}
            return parsed
    except Exception:
        pass
    return {"facts": _build_deterministic_facts(state), "working_memory_update": {}, "missing_info": {}}


def apply_memory_update(state: AgentState, update: dict) -> None:
    if not isinstance(update, dict):
        return
    state.merge_facts(update.get("facts") or {})
    state.update_working_memory(update.get("working_memory_update") or {})
    missing = update.get("missing_info")
    if isinstance(missing, dict):
        if not isinstance(state.memory.missing_info, dict):
            state.memory.missing_info = {}
        for k, v in missing.items():
            if k not in state.memory.missing_info:
                state.memory.missing_info[k] = v
