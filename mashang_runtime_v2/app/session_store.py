#!/usr/bin/env python
"""
Runtime V2 — Session Store

基于本地文件的 session 存储，用于多轮上下文传递。
session 文件路径：mashang_runtime_v2/data/sessions/<session_id>.json
"""

import json, re, time
from datetime import datetime
from pathlib import Path

_V2_ROOT = Path(__file__).resolve().parents[1]
_WS_ROOT = _V2_ROOT.parent / "mashang_workspace"
SESSIONS_DIR = _V2_ROOT / "data" / "sessions"

SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def sanitize(session_id: str) -> str:
    """确保 session_id 只包含安全字符，非法字符替换为 _。"""
    if not SAFE_ID_RE.match(session_id):
        return re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    return session_id


def _path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{sanitize(session_id)}.json"


def load(session_id: str) -> dict:
    """读取 session，不存在时返回空 session。"""
    p = _path(session_id)
    if p.exists():
        return json.loads(p.read_text())
    return {"session_id": session_id, "turn_count": 0}


def save(session_id: str, data: dict):
    """保存 session。保留 created_at，更新 updated_at。"""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    existing = {}
    p = _path(session_id)
    if p.exists():
        try:
            existing = json.loads(p.read_text())
        except Exception:
            pass
    data["session_id"] = session_id
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if not data.get("created_at"):
        data["created_at"] = existing.get("created_at", now)
    data["updated_at"] = now
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def delete(session_id: str):
    """删除 session。"""
    p = _path(session_id)
    if p.exists():
        p.unlink()


def cleanup(max_age_days: int = 7):
    """删除超过 max_age_days 未更新的 session 文件。"""
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    if SESSIONS_DIR.exists():
        for f in SESSIONS_DIR.glob("*.json"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
    return removed


def make_entry(context: dict, dispatch_result: dict, contract_adapter: dict,
               answer: str, error: str | None = None) -> dict:
    """从 pipeline 结果构造 session entry。"""
    entry = {}
    if context:
        rc = context.get("resolved_context", {})
        entry["last_context"] = rc if rc else None
        entry["last_inherited"] = context.get("inherited_context", {})
    if dispatch_result:
        entry["last_capability"] = dispatch_result.get("capability_id")
    fc = contract_adapter.get("followup_context", {}) if contract_adapter else {}
    entry["last_result_context"] = fc if fc else None
    entry["last_answer"] = answer[:500] if answer else ""
    entry["last_error"] = error
    entry["turn_count"] = 1
    return entry
