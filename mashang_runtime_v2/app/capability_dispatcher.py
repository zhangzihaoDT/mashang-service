#!/usr/bin/env python
"""
Runtime V2 — Capability Dispatcher

从 capability_registry.json 读取能力，根据 resolved_context 匹配能力。
支持 follow-up 场景（继承 previous_context）。
"""

import sys, json
from pathlib import Path

_V2_ROOT = Path(__file__).resolve().parents[1]
_WS_ROOT = _V2_ROOT.parent / "mashang_workspace"
_PRJ_ROOT = _V2_ROOT.parent
for p in [str(_V2_ROOT), str(_PRJ_ROOT), str(_WS_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

REGISTRY_PATH = _WS_ROOT / "registry" / "capability_registry.json"
CONFIG_PATH = _V2_ROOT / "config" / "runtime_v2_config.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"enabled_capabilities": ["lock_by_model", "lock_city_distribution"]}


def _load_registry() -> list:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return []


def dispatch(context: dict) -> dict:
    """根据 resolved_context 匹配能力。"""
    ctx = context.get("resolved_context", context)
    metric = (ctx.get("metric") or "").lower()
    group_by = (ctx.get("group_by") or "").lower()
    user_text = context.get("raw_text", "")

    config = _load_config()
    enabled = config.get("enabled_capabilities", [])
    registry = _load_registry()
    rscripts = config.get("runtime_scripts", {})
    # Only match by metric+group_by if user text has relevant keywords or metric was explicitly parsed
    _relevant_keywords = {
        "lock_by_model": ["锁单", "分车型", "车型", "车系", "model", "series", "销量", "结构"],
        "lock_city_distribution": ["城市", "分布", "city", "区域", "大区"],
    }

    if "lock_by_model" in enabled:
        if metric == "lock_count" and group_by in ("model", "series", "energy_type"):
            if _has_keyword(user_text, _relevant_keywords["lock_by_model"]):
                return _build("lock_by_model", rscripts, f"lock_count + {group_by} group", 0.9, registry)

    if "lock_city_distribution" in enabled:
        if group_by == "city":
            if _has_keyword(user_text, _relevant_keywords["lock_city_distribution"]):
                return _build("lock_city_distribution", rscripts,
                              f"city distribution (metric={metric})", 0.85, registry)

    # Text keyword fallback — only match clear intent keywords
    if "lock_by_model" in enabled and ("分车型" in user_text or "车型" in user_text):
        if not ctx.get("metric") or ctx.get("metric") in ("lock_count", ""):
            return _build("lock_by_model", rscripts, "text keyword match", 0.7, registry)

    if "lock_city_distribution" in enabled and ("城市分布" in user_text or "分城市" in user_text):
        if not ctx.get("metric") or ctx.get("metric") in ("lock_count", ""):
            return _build("lock_city_distribution", rscripts, "text keyword match", 0.7, registry)

    return {"capability_id": None, "error": "no_capability_matched",
            "message": "当前 Runtime V2 仅支持 lock_by_model 与 lock_city_distribution。"}


def _has_keyword(text: str, keywords: list[str]) -> bool:
    """检查文本是否包含任一关键词。"""
    t = text.lower()
    return any(k.lower() in t for k in keywords)


def _build(cap_id: str, rscripts: dict, reason: str, confidence: float, registry: list) -> dict:
    script_path = rscripts.get(cap_id, f"mashang_workspace/runtime_scripts/{cap_id}.py")
    cap = _find_capability(registry, cap_id)
    return {
        "capability_id": cap_id,
        "script": str(Path(_V2_ROOT.parent) / script_path),
        "reason": reason,
        "confidence": confidence,
        "capability": cap,
    }


def _find_capability(registry: list, cap_id: str) -> dict | None:
    for c in registry:
        if c.get("capability_id") == cap_id:
            return c
    return None
