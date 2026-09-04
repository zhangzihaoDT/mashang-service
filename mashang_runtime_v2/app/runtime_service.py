#!/usr/bin/env python
"""
Runtime V2 — Runtime Service CLI

最小可运行闭环：
  user_text → context_manager → capability_dispatcher → workspace_script_adapter → result_contract_adapter → response_renderer → answer

支持 --session 实现多轮追问。
"""

import sys, argparse, json
from pathlib import Path

_V2_ROOT = Path(__file__).resolve().parents[1]
_WS_ROOT = _V2_ROOT.parent / "mashang_workspace"
_PRJ_ROOT = _V2_ROOT.parent
for p in [str(_V2_ROOT), str(_PRJ_ROOT), str(_WS_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.context_manager import parse as parse_context
from app.capability_dispatcher import dispatch, load_config
from app.workspace_script_adapter import execute
from app.result_contract_adapter import load as load_contract
from app.response_renderer import render
from app.session_store import load as load_session, save as save_session, delete as delete_session, make_entry, cleanup as cleanup_sessions, sanitize


def run_pipeline(user_text: str, session_id: str = "", debug: bool = False) -> dict:
    """运行完整 pipeline。支持 session 继承上下文。"""
    # 1. Load session context
    previous_context = None
    previous_result_context = None
    session = None
    session_info = {"session_id": session_id, "previous_session_loaded": False}
    if session_id:
        session = load_session(session_id)
        if session and session.get("last_context"):
            previous_context = session["last_context"]
            previous_result_context = session.get("last_result_context")
            session_info["previous_session_loaded"] = True
            session_info["session_path"] = str(_V2_ROOT / "data" / "sessions" / f"{sanitize(session_id)}.json")
            session_info["turn_count"] = session.get("turn_count", 0)

    # 2. Context
    context = parse_context(user_text, previous_context=previous_context,
                            previous_result_context=previous_result_context)
    if debug:
        print(f"[Context] resolved={context.get('resolved_context', {})}")
        if context.get("inherited_context"):
            print(f"[Context] inherited={context.get('inherited_context')}")

    # 3. Dispatch
    dispatch_result = dispatch(context)
    if debug:
        print(f"[Dispatch] {dispatch_result.get('capability_id', 'no_match')}")

    if dispatch_result.get("error"):
        answer = dispatch_result.get("message", "无法匹配能力。")
        result = {"user_text": user_text, "session": session_info,
                  "context": context, "dispatch": dispatch_result,
                  "execution": {}, "contract": {}, "answer": answer}
        _save_failed_session(session_id, session, context, dispatch_result, answer, user_text)
        return result

    # 4. Execute
    exec_result = execute(dispatch_result["capability_id"], dispatch_result["script"], context)

    if exec_result.get("status") == "error":
        answer = f"执行出错：{exec_result.get('error', 'unknown')}"
        result = {"user_text": user_text, "session": session_info,
                  "context": context, "dispatch": dispatch_result,
                  "execution": exec_result, "contract": {}, "answer": answer}
        _save_failed_session(session_id, session, context, dispatch_result, answer, user_text)
        return result

    # 5. Load contract
    contract_data = load_contract(exec_result.get("contract"), exec_result.get("stdout", ""))

    # 6. Render（展示配置来自 config：metric 标签 + 追问后缀，不在内核硬编码）
    _config = load_config()
    _cap_cfg = (_config.get("capabilities") or {}).get(dispatch_result.get("capability_id"), {})
    answer = render(
        contract_data,
        metric_labels=_config.get("metric_labels", {}),
        hint_suffix=_cap_cfg.get("followup_suffix", ""),
    )

    result = {
        "user_text": user_text,
        "session": session_info,
        "context": context,
        "dispatch": dispatch_result,
        "execution": exec_result,
        "contract": contract_data,
        "answer": answer,
    }

    # 7. Save session
    if session_id:
        entry = make_entry(context, dispatch_result, contract_data, answer)
        if session:
            entry["turn_count"] = session.get("turn_count", 0) + 1
        save_session(session_id, entry)
        if debug:
            print(f"[Session] saved turn={entry['turn_count']}")

    return result


def _save_failed_session(session_id: str, session: dict | None, context: dict,
                         dispatch_result: dict, answer: str, user_text: str):
    """保存失败的 session 但不覆盖有效 context。"""
    if not session_id:
        return
    existing = session or {}
    entry = {"turn_count": existing.get("turn_count", 0) + 1}
    # Only update context if we have a resolved one
    if context and context.get("resolved_context"):
        entry["last_context"] = existing.get("last_context", context.get("resolved_context"))
    else:
        entry["last_context"] = existing.get("last_context")
    entry["last_result_context"] = existing.get("last_result_context")
    entry["last_capability"] = dispatch_result.get("capability_id", existing.get("last_capability"))
    entry["last_answer"] = existing.get("last_answer", answer[:500])
    entry["last_error"] = dispatch_result.get("error", answer[:200])
    # Preserve created_at from existing
    if existing.get("created_at"):
        entry["created_at"] = existing["created_at"]
    save_session(session_id, entry)


def main():
    parser = argparse.ArgumentParser(description="Runtime V2 — 最小可运行闭环")
    parser.add_argument("text", nargs="?", type=str, default="", help="用户自然语言问题")
    parser.add_argument("--format", type=str, default="text", choices=["text", "json"])
    parser.add_argument("--output", type=str, help="输出文件路径")
    parser.add_argument("--debug", action="store_true", help="打印调试信息")
    parser.add_argument("--session", type=str, help="多轮对话 session ID")
    parser.add_argument("--reset-session", action="store_true", help="重置 session")
    parser.add_argument("--cleanup-sessions", action="store_true", help="清理过期 session")
    parser.add_argument("--clear-session", type=str, help="清空指定 session")
    args = parser.parse_args()

    # Session cleanup
    if args.cleanup_sessions:
        removed = cleanup_sessions()
        print(f"清理了 {removed} 个过期 session 文件。")
        return

    # Clear specific session
    if args.clear_session:
        delete_session(args.clear_session)
        print(f"已清除 session: {args.clear_session}")
        return

    # Reset session
    if args.reset_session and args.session:
        delete_session(args.session)

    # Run pipeline
    if not args.text:
        parser.print_help()
        return

    result = run_pipeline(args.text, session_id=args.session or "", debug=args.debug)

    if args.format == "json":
        # Capture stdout cleanly, debug goes to stderr
        body = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(body, encoding="utf-8")
            print(f"[Output] {args.output}")
        else:
            print(body)
    else:
        print(result.get("answer", ""))


if __name__ == "__main__":
    main()
