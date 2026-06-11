import json
import os
import re
import sys
import uuid
import datetime
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from agent.llm_config import DEEPSEEK_CHAT_MODEL
from agent.memory_extractor import apply_memory_update, extract_memory_update
from agent.planner import PlanningAgent, plan_runtime_action
from agent.runtime_decision import latest_intent, ANALYSIS_EVIDENCE_CONTRACT
from agent.schema import DATA_PATH_FILE, SCHEMA_DIR
from agent.state import AgentState, LoopState, ResultBlock, _to_json_safe
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


def _save_memory(obj: dict) -> bool:
    path = _memory_file()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[Warning] _save_memory 写入失败: {e}")
        return False


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


_STM_TTL_TURNS = 5

def _save_short_term(key: str, value: object) -> None:
    memory = _load_memory()
    if "short_term_memory" not in memory:
        memory["short_term_memory"] = {}
    memory["short_term_memory"][key] = value
    memory["short_term_memory"]["_meta"] = {
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "turn_count": 0,
    }
    _save_memory(memory)


def _load_short_term(key: str) -> object | None:
    memory = _load_memory()
    stm = memory.get("short_term_memory", {})
    meta = stm.get("_meta", {})
    turn_count = meta.get("turn_count", 0)
    if turn_count > _STM_TTL_TURNS:
        memory.pop("short_term_memory", None)
        _save_memory(memory)
        return None
    stm["_meta"] = {**meta, "turn_count": turn_count + 1}
    _save_memory(memory)
    return stm.get(key)


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
        base_original = original_question.strip()
        raw_question = pending.get("original_raw_question")
        if isinstance(raw_question, str) and raw_question.strip():
            base_original = raw_question.strip()
        elif "澄清上下文:" in base_original:
            m = re.search(r"原始问题=([^ ]+\s*[^ 澄清问题]*)", base_original)
            if not m:
                m = re.search(r"原始问题=(.+?)\s+澄清", base_original)
            if m:
                base_original = m.group(1).strip()
        base_original = base_original.replace("\n", " ").replace("？", "").replace("?", "").strip().rstrip("。；;")
        options_detail = clarification.get("_options_detail")
        if isinstance(options_detail, list) and options_detail:
            chosen = None
            chosen_col = None
            reply_norm = reply.replace(" ", "")
            for opt in options_detail:
                opt_label = str(opt.get("label", "")).replace(" ", "")
                opt_id = str(opt.get("id", "")).replace(" ", "")
                if reply_norm == opt_label or reply_norm == opt_id:
                    chosen = opt.get("label", opt.get("id", ""))
                    chosen_col = opt.get("id")
                    break
                if opt_label in reply_norm or opt_id in reply_norm:
                    chosen = opt.get("label", opt.get("id", ""))
                    chosen_col = opt.get("id")
                    break
                if reply_norm in opt_label or reply_norm in opt_id:
                    chosen = opt.get("label", opt.get("id", ""))
                    chosen_col = opt.get("id")
                    break
            if chosen:
                clean = base_original
                short = str(chosen).replace("下发", "").strip()
                for pat in ["下发线索转化率", "下发线索转化", "线索转化率", "转化率"]:
                    if pat in clean:
                        clean = clean.replace(pat, short)
                        break
                return clean
        question = (
            str(clarification.get("question") or "")
            .replace("\n", " ").replace("？", "").replace("?", "").strip()
        )
        options = clarification.get("options")
        options_text = ""
        if isinstance(options, list) and options:
            options_text = " / ".join(str(o) for o in options)
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


_NEW_QUESTION_KEYWORDS = frozenset(["锁单", "交付", "开票", "小订", "意向金", "金额", "试驾", "同比", "环比", "昨天", "去年", "今年", "按", "分"])


def classify_pending_reply(user_query: str, pending: dict) -> str:
    if not isinstance(pending, dict):
        return "new_question"
    reply = (user_query or "").strip()
    if not reply:
        return "new_question"
    if pending.get("type") != "clarification":
        return "new_question"
    clarification = pending.get("clarification")
    if not isinstance(clarification, dict):
        return "new_question"

    if _matches_pending_option(user_query, {"pending": pending}):
        return "clarification_answer"

    if len(reply) >= 12:
        return "new_question"
    if any(k in reply for k in _NEW_QUESTION_KEYWORDS):
        return "new_question"

    return "ambiguous"


_CN_DIGITS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
_SELECTION_PREFIXES = ("选", "我选", "选择", "就", "按", "用", "看")


def _matches_pending_option(user_query: str, memory: dict) -> bool:
    pending = memory.get("pending")
    if not isinstance(pending, dict):
        return False
    reply = (user_query or "").strip()
    if not reply:
        return False
    normalized_reply = reply.replace(" ", "")
    ptype = pending.get("type")
    if ptype != "clarification":
        return False
    clarification = pending.get("clarification")
    if not isinstance(clarification, dict):
        return False

    # Build (label, id) entries from options / _options_detail
    entries: list[tuple[str, str]] = []
    detail = clarification.get("_options_detail")
    if isinstance(detail, list):
        for d in detail:
            label = str(d.get("label", "")).strip()
            oid = str(d.get("id", "")).strip()
            if label:
                entries.append((label, oid))
    else:
        raw_opts = clarification.get("options")
        if isinstance(raw_opts, list):
            for o in raw_opts:
                label = str(o).strip()
                if label:
                    entries.append((label, ""))
    if not entries:
        return False

    def _exact_or_prefixed(text: str, target: str) -> bool:
        t = text.replace(" ", "")
        c = target.replace(" ", "")
        if t == c:
            return True
        for prefix in _SELECTION_PREFIXES:
            if t == (prefix + c).replace(" ", ""):
                return True
        return False

    for idx, (label, oid) in enumerate(entries):
        # (1) Exact match or selection-verb match
        if _exact_or_prefixed(reply, label):
            return True
        if oid and _exact_or_prefixed(reply, oid):
            return True

        # (2) Number reference
        num = idx + 1
        patterns = {str(num), f"选{num}", f"第{num}个", f"第{num}", f"{num}个"}
        if idx < len(_CN_DIGITS):
            cn = _CN_DIGITS[idx]
            patterns.update([cn, f"选{cn}", f"第{cn}个", f"第{cn}", f"{cn}个"])
        if normalized_reply in {p.replace(" ", "") for p in patterns}:
            return True
        if reply in patterns:
            return True

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
        safe_entry = _to_json_safe(entry)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Warning] _append_query_log 写入失败: {e}")


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
    exit_reason = ""
    query_id = uuid.uuid4().hex[:12]

    print(f"\n{'='*60}")
    print(f"用户提问: '{user_query}'")

    memory = _load_memory()
    pending = memory.get("pending")
    classification = classify_pending_reply(user_query, pending) if pending else "new_question"
    merged = None
    restored_state = None

    if classification == "clarification_answer":
        merged = _merge_pending_context(user_query, memory)
        snapshot = memory.get("pending", {}).get("state_snapshot")
        if isinstance(snapshot, dict):
            restored_state = AgentState.from_snapshot(snapshot)

    if merged:
        _clear_pending(memory)
        user_query = merged
        if restored_state is not None:
            restored_state.question = user_query
            restored_state.normalized_question = _normalize_question_text(user_query)
            restored_state.loop.done = False
        print(f"\n{'='*60}")
        print("已合并上一轮澄清上下文，继续规划...")
    elif classification in ("new_question", "ambiguous"):
        _clear_pending(memory)
        if classification == "ambiguous":
            print("[Warning] 输入无法明确判断是否为上一轮的回答，已按新问题处理")

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

        from operators.registry import get_operator_catalog_md
        from schema import MetricRegistry
        planning_agent = PlanningAgent(
            client=client,
            schema_md=schema_context.get("schema_md", ""),
            business_definition=schema_context.get("business_definition", ""),
            operator_catalog=get_operator_catalog_md(),
            metric_registry=MetricRegistry(),
        )
        comparison_tool = ComparisonTool(query_tool=query_tool)
        composition_tool = CompositionTool(query_tool=query_tool)
        statistics_tool = StatisticsTool()
        multi_table_tool = MultiTableMetricTool(query_tool=query_tool)
        if restored_state is not None:
            state = restored_state
        else:
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
                stm = memory.get("short_term_memory", {}) if isinstance(memory, dict) else {}
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
                        "short_term_memory": stm,
                        "structured_blocks": state.results.structured_blocks,
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
                    _operator_result = step_result.get("_operator_result")
                    _cache_key = step_result.get("_cache_key", "")
                    _original = step_result.get("original_question") or action_query
                    pending_entry = {
                        "type": "clarification",
                        "clarification": clarification,
                        "original_question": _original,
                        "original_raw_question": _original,
                        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
                        "state_snapshot": state.to_snapshot(),
                    }
                    existing = _load_memory()
                    existing["pending"] = pending_entry
                    if _operator_result and isinstance(_operator_result, dict) and _cache_key:
                        stm = existing.setdefault("short_term_memory", {})
                        stm[_cache_key] = _operator_result
                        stm["_meta"] = {
                            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
                            "turn_count": 0,
                        }
                    save_ok = _save_memory(existing)
                    if not save_ok:
                        print("[Warning] 保存 pending + state_snapshot 失败，澄清状态可能无法恢复")
                    exit_reason = "clarification"
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
                    _clear_pending(memory)
                    state.add_step(action, _trim_text(err_text))
                    state.loop.done = True
                    exit_reason = "error"
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

        # Capture exit_reason from runtime decision result
        if not exit_reason:
            if state.loop.iteration >= state.loop.max_steps and not state.loop.done:
                exit_reason = "max_steps_reached"
            elif state.loop.history:
                last_entry = state.loop.history[-1]
                last_action = last_entry.get("action", {}) if isinstance(last_entry, dict) else {}
                if isinstance(last_action, dict):
                    exit_reason = last_action.get("reason", "") or last_action.get("action", "unknown")
            if not exit_reason:
                exit_reason = "unknown"

        # Save the last DataFrame result for cross-session report generation
        try:
            import pandas as pd
            for blk in (state.results.structured_blocks or []):
                r = getattr(blk, "result", None)
                if isinstance(r, pd.DataFrame) and not r.empty:
                    save_dir = Path(__file__).resolve().parents[1] / "logs"
                    save_dir.mkdir(parents=True, exist_ok=True)
                    r.to_parquet(save_dir / "last_result.parquet", index=False)
                    break
        except Exception:
            pass

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
        if not exit_reason:
            exit_reason = "exception"
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
            "exit_reason": exit_reason,
            "used_dataset": used_dataset or "",
            "used_metrics": used_metrics,
            "used_dimensions": used_dimensions,
            "latency_ms": latency_ms,
            "token_usage": {},
            "result_summary": result_summary,
            "user_feedback": None,
        }
        # ── eval logging fields ──
        try:
            entry["query_id"] = query_id
            entry["final_answer"] = final_answer_text or final_error_text
            if isinstance(state, AgentState):
                entry["eval_intent"] = latest_intent(state)
                entry["contract_matched"] = entry["eval_intent"] in ANALYSIS_EVIDENCE_CONTRACT
                facts_list = getattr(getattr(state, "memory", None), "facts", None)
                if isinstance(facts_list, list):
                    entry["facts"] = facts_list
                    seen_ft: list[str] = []
                    for f in facts_list:
                        ft = f.get("fact_type") if isinstance(f, dict) else None
                        if isinstance(ft, str) and ft and ft not in seen_ft:
                            seen_ft.append(ft)
                    entry["fact_types"] = seen_ft
                else:
                    entry["facts"] = []
                    entry["fact_types"] = []
                wm = getattr(getattr(state, "memory", None), "working_memory", None)
                if isinstance(wm, dict):
                    mf = wm.get("_last_missing_facts")
                    entry["missing_facts"] = list(mf) if isinstance(mf, list) else []
                else:
                    entry["missing_facts"] = []
                hist = getattr(getattr(state, "loop", None), "history", None)
                entry["loop_history"] = hist if isinstance(hist, list) else []
                sb_list = getattr(getattr(state, "results", None), "structured_blocks", None)
                sb_summary: list[dict] = []
                if isinstance(sb_list, list):
                    for blk in sb_list:
                        s = {"block_type": getattr(blk, "block_type", ""),
                             "execution_status": getattr(blk, "status", "")}
                        r = getattr(blk, "result", None)
                        if r is not None:
                            s["has_result"] = True
                            if hasattr(r, "columns"):
                                s["result_type"] = "dataframe"
                                try:
                                    s["columns"] = list(r.columns)
                                    s["row_count"] = len(r)
                                except Exception:
                                    pass
                            elif isinstance(r, dict):
                                s["result_type"] = "dict"
                                s["columns"] = list(r.keys())
                            elif isinstance(r, str):
                                s["result_type"] = "str"
                            else:
                                s["result_type"] = type(r).__name__
                        else:
                            s["has_result"] = False
                        p = getattr(blk, "plan", None)
                        if isinstance(p, dict):
                            ai = p.get("analysis_intent")
                            if isinstance(ai, dict):
                                s["plan_intent"] = ai.get("type", "")
                        sb_summary.append(s)
                entry["structured_blocks_summary"] = sb_summary
        except Exception:
            pass
        _append_query_log(entry)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        query = "下发线索数 (门店) 的平均值是多少？"
    answer = run_main_agent(query)
    print(answer)
