import json
import os
import sys
import datetime
import time

from dotenv import load_dotenv
from openai import OpenAI

from agent.llm_config import DEEPSEEK_CHAT_MODEL
from agent.memory_extractor import apply_memory_update, extract_memory_update
from agent.planner import PlanningAgent, plan_runtime_action
from agent.schema import DATA_PATH_FILE, SCHEMA_DIR
from agent.state import AgentState, LoopState, ResultBlock
from agent.tool_router import run_dsl_step
from tools import CompositionTool, ComparisonTool, MultiTableMetricTool, QueryTool, StatisticsTool

FINAL_ANSWER_SYSTEM_PROMPT = (
    "你是一个智能数据分析助手。请基于给定的规划 DSL 与执行结果，直接回答用户问题，语言简洁，给出关键数值与同比/环比方向与幅度。"
    "如果执行结果包含 contribution_summary/贡献拆解，只能用描述性证据表述（例如“从贡献拆解看……”），禁止将贡献拆解直接表述为因果原因（禁止使用“原因是/导致/因为”）。"
)


def _load_api_key() -> str | None:
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if api_key:
        return api_key
    env_file = ".env"
    if not os.path.exists(env_file):
        return None
    with open(env_file, "r", encoding="utf-8") as file:
        for line in file:
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.strip().split("=", 1)[1]
    return None


def _memory_file() -> str:
    return os.path.join(os.path.dirname(__file__), ".query_agent_memory.json")


def _load_memory() -> dict:
    path = _memory_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            return {}
        if "recent_user_queries" in obj:
            obj.pop("recent_user_queries", None)
            _save_memory(obj)
        return obj
    except Exception:
        return {}


def _save_memory(obj: dict) -> None:
    path = _memory_file()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _clear_memory() -> None:
    path = _memory_file()
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _clear_pending(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    memory.pop("pending", None)
    _save_memory(memory)


def _merge_pending_context(user_query: str, memory: dict) -> str | None:
    pending = memory.get("pending")
    if not isinstance(pending, dict):
        return None
    pending_type = pending.get("type")

    reply = (user_query or "").strip()
    if not reply:
        return None

    if pending_type == "clarification":
        original_question = pending.get("original_question")
        clarification = pending.get("clarification")
        if not isinstance(original_question, str) or not isinstance(clarification, dict):
            return None
        question = (
            str(clarification.get("question") or "")
            .replace("\n", " ")
            .replace("？", "")
            .replace("?", "")
            .strip()
        )
        options = clarification.get("options")
        options_text = ""
        if isinstance(options, list) and options:
            options_text = " / ".join(str(o) for o in options)
        base_original = (
            original_question.strip()
            .replace("\n", " ")
            .replace("？", "")
            .replace("?", "")
            .strip()
            .rstrip("。；;")
        )
        base_reply = reply.replace("\n", " ").strip().rstrip("？?。；;")
        payload = (
            "澄清上下文: "
            f"原始问题={base_original} "
            f"澄清问题={question} "
            f"可选项={options_text} "
            f"用户回复={base_reply}。"
            "请基于上述上下文生成 plans；如仍不明确，请返回 clarification.need=true。"
        )
        return payload

    return None


def _looks_like_new_question(user_query: str) -> bool:
    q = (user_query or "").strip()
    if not q:
        return False
    if len(q) >= 12:
        return True
    keywords = ["锁单", "交付", "开票", "小订", "意向金", "金额", "试驾", "同比", "环比", "昨天", "去年", "今年", "按", "分"]
    return any(k in q for k in keywords)


def _matches_pending_option(user_query: str, memory: dict) -> bool:
    pending = memory.get("pending")
    if not isinstance(pending, dict):
        return False
    reply = (user_query or "").strip()
    if not reply:
        return False
    normalized_reply = reply.replace(" ", "")
    ptype = pending.get("type")
    if ptype == "clarification":
        clarification = pending.get("clarification")
        if not isinstance(clarification, dict):
            return False
        options = clarification.get("options")
        if isinstance(options, list):
            normalized_options = {str(o).replace(" ", "") for o in options}
            if normalized_reply in normalized_options:
                return True
            for opt in normalized_options:
                if opt and opt in normalized_reply:
                    return True
            tokens = set()
            for o in options:
                s = str(o).strip()
                if not s:
                    continue
                for sep in ["（", "(", " "]:
                    if sep in s:
                        s = s.split(sep, 1)[0].strip()
                if s:
                    tokens.add(s)
            for t in tokens:
                if t and t in reply:
                    return True
            relaxed_tokens = set()
            for t in tokens:
                base = str(t).replace("数量", "").replace("数目", "").replace("数量", "").strip()
                for suffix in ["量", "数"]:
                    if base.endswith(suffix) and len(base) > 1:
                        base = base[: -len(suffix)]
                if base:
                    relaxed_tokens.add(base)
            for t in relaxed_tokens:
                if t and t in reply:
                    return True
        if normalized_reply in {"1", "2", "3", "4"}:
            return True
        return False
    return False


def _looks_like_clarification_answer(user_query: str) -> bool:
    q = (user_query or "").strip()
    if not q:
        return False
    if len(q) <= 6:
        return True
    return False


def _trim_text(text: str, limit: int = 1800) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


def _normalize_question_text(text: str) -> str:
    raw = str(text or "").replace("\n", " ").strip()
    if not raw:
        return ""
    while "  " in raw:
        raw = raw.replace("  ", " ")
    return raw


def _query_log_path() -> str:
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(root_dir, "logs")
    try:
        os.makedirs(logs_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(logs_dir, "query_log.jsonl")


def _append_query_log(entry: dict) -> None:
    if not os.getenv("ENABLE_QUERY_LOG"):
        return
    if not isinstance(entry, dict) or not entry:
        return
    path = _query_log_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return


def _generate_final_answer(client: OpenAI, user_query: str, result_blocks: list[str]) -> str:
    print("\n[Thinking] AnalysisAgent 正在生成最终回答...")
    joined_results = '\n\n---\n\n'.join(result_blocks)
    messages = [
        {
            "role": "system",
            "content": FINAL_ANSWER_SYSTEM_PROMPT,
        },
        {"role": "user", "content": f"用户问题: {user_query}\n\n{joined_results}"},
    ]
    final_response = client.chat.completions.create(model=DEEPSEEK_CHAT_MODEL, messages=messages)
    return final_response.choices[0].message.content or ""


def _try_extract_fast_path_answer(blocks: list[str]) -> str | None:
    for b in blocks:
        text = _extract_result_text(b)
        if not text:
            continue
        try:
            obj = json.loads(text)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("type") == "fast_path" and obj.get("kind") in ("data_update", "data_sync"):
            return str(obj.get("answer") or "")
    return None


def _extract_result_text(result_block: str) -> str:
    marker = "执行结果:\n"
    text = str(result_block or "")
    idx = text.find(marker)
    if idx == -1:
        return text.strip()
    return text[idx + len(marker) :].strip()


def _build_finish_grounded_answer(action: dict, last_result_block: str) -> str:
    reason = str(action.get("reason") or "").strip()
    analysis = str(action.get("analysis") or "").strip()
    result_text = _extract_result_text(last_result_block)
    result_preview = _trim_text(result_text, limit=1600) if result_text else ""
    narrative = "\n\n".join([p for p in [reason, analysis] if p])
    if narrative and result_preview:
        return f"{narrative}\n\n查询结果:\n{result_preview}"
    if result_preview:
        return f"查询结果:\n{result_preview}"
    return narrative


def _generate_finish_summary(client: OpenAI, user_query: str, action: dict, last_result_block: str) -> str:
    result_text = _extract_result_text(last_result_block)
    if not result_text:
        return _build_finish_grounded_answer(action, last_result_block)
    messages = [
        {
            "role": "system",
            "content": (
                "你是严格的数据总结助手。只能基于给定查询结果回答。"
                "必须给出明确结论、关键数字，并尽量列出明细。"
                "如果问题是“哪些天/哪些项”，必须输出清单（可分点）。"
                "如果查询结果包含 contribution_summary/贡献拆解，只能用描述性证据表述（例如“从贡献拆解看……”），禁止将贡献拆解直接表述为因果原因（禁止使用“原因是/导致/因为”）。"
                "禁止编造、禁止只复述过程。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户问题:\n{user_query}\n\n"
                f"Finish reason:\n{str(action.get('reason') or '')}\n\n"
                f"Finish analysis:\n{str(action.get('analysis') or '')}\n\n"
                f"查询结果:\n{result_text}\n\n"
                "请直接给最终回答。"
            ),
        },
    ]
    try:
        response = client.chat.completions.create(model=DEEPSEEK_CHAT_MODEL, messages=messages)
        text = str(response.choices[0].message.content or "").strip()
        if text:
            return text
    except Exception:
        pass
    return _build_finish_grounded_answer(action, last_result_block)


def _format_execution_meta(meta: dict) -> str:
    if not isinstance(meta, dict):
        return "unknown"
    engine = str(meta.get("engine") or "unknown")
    route = str(meta.get("route") or "unknown")
    return f"{engine}::{route}"


def run_main_agent(user_query: str) -> str:
    started_at = time.time()
    original_question = str(user_query or "")
    query_log_steps: list[dict] = []
    query_log_clarification: dict | None = None
    query_rounds = 0
    query_rounds_max = 5
    dsl_rounds = 0
    final_execution_success = False
    final_answer_text = ""
    final_error_text = ""

    print(f"\n{'='*60}")
    print(f"用户提问: '{user_query}'")

    memory = _load_memory()
    merged = None
    if memory.get("pending") and (
        _matches_pending_option(user_query, memory)
        or _looks_like_clarification_answer(user_query)
        or not _looks_like_new_question(user_query)
    ):
        merged = _merge_pending_context(user_query, memory)
    if merged:
        _clear_pending(memory)
        user_query = merged
        print(f"\n{'='*60}")
        print("已合并上一轮澄清上下文，继续规划...")
    elif memory.get("pending") and _looks_like_new_question(user_query):
        _clear_pending(memory)

    try:
        api_key = _load_api_key()
        if not api_key:
            final_error_text = "Error: Could not find API key in .env"
            return final_error_text

        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        query_tool = QueryTool(
            data_path_file=str(DATA_PATH_FILE),
            schema_dir=str(SCHEMA_DIR),
        )

        schema_context = query_tool._schema_context()

        planning_agent = PlanningAgent(
            client=client,
            schema_md=schema_context.get("schema_md", ""),
            business_definition=schema_context.get("business_definition", ""),
        )
        comparison_tool = ComparisonTool(query_tool=query_tool)
        composition_tool = CompositionTool(query_tool=query_tool)
        statistics_tool = StatisticsTool()
        multi_table_tool = MultiTableMetricTool(query_tool=query_tool)
        state = AgentState(question=user_query, normalized_question=_normalize_question_text(user_query), loop=LoopState(max_steps=5))
        query_rounds_max = int(state.loop.max_steps or 5)
        goal_time_info = planning_agent.infer_goal_time_window(user_query, datetime.date.today())
        goal_time_window = goal_time_info.get("window") if isinstance(goal_time_info, dict) else None
        goal_time_window_confidence = goal_time_info.get("confidence") if isinstance(goal_time_info, dict) else None
        finish_grounded_answer = ""
        while not state.loop.done and state.loop.iteration < state.loop.max_steps:
            query_rounds += 1
            print(f"\n=== Loop Step {state.loop.iteration + 1}/{state.loop.max_steps} ===")
            action = plan_runtime_action(client, state)
            print(f"[Loop] action={json.dumps(action, ensure_ascii=False)}")

            if action.get("action") == "run_dsl":
                dsl_rounds += 1
                action_query = str(action.get("query") or state.question).strip() or state.question
                step_result = run_dsl_step(
                    action_query=action_query,
                    planning_agent=planning_agent,
                    query_tool=query_tool,
                    comparison_tool=comparison_tool,
                    statistics_tool=statistics_tool,
                    composition_tool=composition_tool,
                    multi_table_tool=multi_table_tool,
                    memory_context={
                        "facts": state.memory.facts,
                        "working_memory": state.memory.working_memory,
                        "execution_log": memory.get("execution_log") if isinstance(memory, dict) else [],
                        "goal_time_window": goal_time_window,
                        "goal_time_window_confidence": goal_time_window_confidence,
                    },
                )
                status = step_result.get("status")
                if isinstance(step_result.get("plan"), dict):
                    query_log_steps.append(
                        {
                            "action_query": action_query,
                            "plan": step_result.get("plan") or {},
                            "execution_meta": step_result.get("execution_meta") or {},
                            "status": status,
                        }
                    )
                if status == "clarification":
                    clarification = step_result.get("clarification") or {}
                    query_log_clarification = clarification if isinstance(clarification, dict) else {}
                    _save_memory(
                        {
                            "pending": {
                                "type": "clarification",
                                "clarification": clarification,
                                "original_question": step_result.get("original_question") or action_query,
                                "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
                            }
                        }
                    )
                    opts = clarification.get("options") or []
                    opts_text = " / ".join([str(o) for o in opts]) if isinstance(opts, list) else ""
                    qtext = clarification.get("question") or "需要你补充信息后才能继续。"
                    state.add_step(action, _trim_text(f"clarification: {qtext}"))
                    if opts_text:
                        final_answer_text = f"{qtext}\n请选择其一回复：{opts_text}"
                        return final_answer_text
                    final_answer_text = str(qtext)
                    return final_answer_text
                if status == "error":
                    err_text = str(step_result.get("message") or "执行失败")
                    state.add_step(action, _trim_text(err_text))
                    state.loop.done = True
                    break

                step_blocks = step_result.get("result_blocks") or []
                step_structured = step_result.get("structured_blocks") or []
                execution_meta = step_result.get("execution_meta") or {}
                print(f"[Loop] execution={_format_execution_meta(execution_meta)}")
                state.results.blocks.extend(step_blocks)
                if isinstance(step_structured, list) and step_structured:
                    current_step = int(state.loop.iteration) + 1
                    block_seq = 0
                    for sb in step_structured:
                        if not isinstance(sb, dict):
                            continue
                        block_seq += 1
                        question = sb.get("question")
                        plan = sb.get("plan")
                        dsl = sb.get("dsl")
                        meta = sb.get("execution_meta")
                        result = sb.get("result")
                        block = sb.get("block")
                        block_type = sb.get("block_type")
                        status = sb.get("status")
                        error = sb.get("error")
                        statistics = sb.get("statistics")
                        if not isinstance(question, str) or not question:
                            continue
                        if not isinstance(plan, dict):
                            plan = {}
                        if not isinstance(dsl, dict):
                            dsl = {}
                        if not isinstance(meta, dict):
                            meta = {}
                        if not isinstance(block, str):
                            block = ""
                        if not isinstance(block_type, str) or not block_type:
                            block_type = "unknown"
                        if not isinstance(status, str) or not status:
                            status = "success"
                        if statistics is not None and not isinstance(statistics, dict):
                            statistics = None
                        block_id = f"step_{current_step}_block_{block_seq}"
                        state.results.structured_blocks.append(
                            ResultBlock(
                                block_id=block_id,
                                step=current_step,
                                block_type=block_type,
                                status=status,
                                question=question,
                                plan=plan,
                                dsl=dsl,
                                result=result,
                                statistics=statistics,
                                execution_meta=meta,
                                error=error,
                                block=block,
                            )
                        )
                merged_step_text = "\n\n---\n\n".join(step_blocks)
                state.add_step(action, _trim_text(merged_step_text))
                memory_update = extract_memory_update(client=client, state=state, last_result=merged_step_text)
                apply_memory_update(state, memory_update)
                facts_text = json.dumps(state.memory.facts, ensure_ascii=False, indent=2) if isinstance(state.memory.facts, (dict, list)) else str(state.memory.facts)
                print(f"[Loop] state.memory.facts={_trim_text(facts_text, limit=1600)}")
            elif action.get("action") == "finish":
                combined_results = "\n\n---\n\n".join([_extract_result_text(b) for b in state.results.blocks if b]) if state.results.blocks else ""
                last_block = f"执行结果:\n{combined_results}" if combined_results else ""
                fast_answer = _try_extract_fast_path_answer(state.results.blocks)
                if fast_answer:
                    finish_grounded_answer = fast_answer
                    state.add_step(action, _trim_text(str(action.get("analysis") or "完成")))
                    state.loop.done = True
                    print("[Loop] execution=finish::fast_path_direct_answer")
                else:
                    finish_grounded_answer = _generate_finish_summary(
                        client=client,
                        user_query=user_query,
                        action=action,
                        last_result_block=last_block,
                    )
                    state.add_step(action, _trim_text(str(action.get("analysis") or "完成")))
                    state.loop.done = True
                    print("[Loop] execution=finish::answer_summarization")
            else:
                state.add_step(action, "未知 action，终止。")
                state.loop.done = True

        if not state.results.blocks:
            fallback = "未产出可用查询结果。"
            if state.loop.history:
                last_result = str(state.loop.history[-1].get("result") or "")
                if last_result:
                    fallback = last_result
            print(f"\n{'='*60}")
            final_answer_text = fallback
            return fallback

        if finish_grounded_answer:
            print(f"\n{'='*60}")
            final_execution_success = True
            final_answer_text = finish_grounded_answer
            return finish_grounded_answer

        final_text = _generate_final_answer(client=client, user_query=user_query, result_blocks=state.results.blocks)
        print(f"\n{'='*60}")
        final_execution_success = True
        final_answer_text = final_text
        return final_text
    except Exception as e:
        final_error_text = f"系统处理出错: {str(e)}"
        raise
    finally:
        latency_ms = int(max(0.0, (time.time() - started_at) * 1000.0))
        used_dataset = None
        used_metrics: list[dict] = []
        used_dimensions: list[str] = []
        for s in query_log_steps:
            plan = s.get("plan") if isinstance(s, dict) else None
            if not isinstance(plan, dict):
                continue
            if used_dataset is None and plan.get("dataset"):
                used_dataset = str(plan.get("dataset"))
            metric = plan.get("metric")
            if isinstance(metric, dict) and metric.get("field") and metric.get("agg"):
                used_metrics.append(
                    {
                        "field": metric.get("field"),
                        "agg": metric.get("agg"),
                        "alias": metric.get("alias") or metric.get("business_name") or "",
                    }
                )
            dims = plan.get("dimensions")
            if isinstance(dims, list):
                for d in dims:
                    if isinstance(d, str) and d:
                        used_dimensions.append(d)
        used_dimensions = list(dict.fromkeys(used_dimensions))
        normalized_question = _normalize_question_text(user_query)
        result_summary = _trim_text(final_answer_text or final_error_text, limit=1800)
        entry = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "question": _normalize_question_text(original_question),
            "normalized_question": normalized_question,
            "query_rounds": query_rounds,
            "query_rounds_max": query_rounds_max,
            "dsl_rounds": dsl_rounds,
            "generated_plan": {"steps": query_log_steps},
            "clarification": query_log_clarification or {},
            "execution_success": bool(final_execution_success),
            "used_dataset": used_dataset or "",
            "used_metrics": used_metrics,
            "used_dimensions": used_dimensions,
            "latency_ms": latency_ms,
            "token_usage": {},
            "result_summary": result_summary,
            "user_feedback": None,
        }
        _append_query_log(entry)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        query = "下发线索数 (门店) 的平均值是多少？"
    answer = run_main_agent(query)
    print(answer)
