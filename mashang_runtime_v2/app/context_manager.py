#!/usr/bin/env python
"""
Runtime V2 — Context Manager

复用 mashang_workspace/eval/context_parser.py 进行自然语言→上下文解析。
支持 previous_context 和 previous_result_context 用于多轮追问。
"""

import sys
from pathlib import Path

_V2_ROOT = Path(__file__).resolve().parents[1]
_WS_ROOT = _V2_ROOT.parent / "mashang_workspace"
for p in [str(_V2_ROOT.parent), str(_WS_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from eval.context_parser import parse_context
from utils.paths import ensure_shared_on_path
ensure_shared_on_path()


def parse(user_text: str, previous_context: dict | None = None,
          previous_result_context: dict | None = None) -> dict:
    """解析用户自然语言，返回结构化 context。"""
    result = parse_context(user_text, previous_context=previous_context,
                           previous_result_context=previous_result_context)
    parsed = result.get("parsed_context", {})
    resolved = result.get("resolved_context", {})
    inherited = result.get("inherited_context", {})

    return {
        "raw_text": user_text,
        "parsed_context": parsed,
        "resolved_context": resolved,
        "inherited_context": inherited,
        "missing_context": result.get("missing_context", {}),
        "previous_context_used": bool(previous_context and inherited),
        "confidence": result.get("confidence", 0.0),
        "raw": result,
    }
