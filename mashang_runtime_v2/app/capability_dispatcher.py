#!/usr/bin/env python
"""
Runtime V2 — Capability Dispatcher

从 runtime_v2_config.json 读取能力（capabilities.<id>.dispatch 规则），
根据 resolved_context 匹配能力。内核不含任何业务能力硬编码 —— 规则全部声明在 config：
  - 第一轮：对每个 enabled 能力求值 explicit（metric / group_by / keywords 门）
  - 第二轮：对每个 enabled 能力求值 keyword_fallback（raw_text 关键词 + metric_allowed）
匹配顺序 = config 中 capabilities 的插入顺序；首中即返回。

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


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def _load_config() -> dict:
    return load_config()


def _load_registry() -> list:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return []


def _has_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in keywords)


def _metric_allowed(metric: str, allowed: list[str]) -> bool:
    m = metric if metric else ""
    return m in allowed


def _match_explicit(ctx: dict, raw_text: str, rule: dict) -> bool:
    metric = (ctx.get("metric") or "").lower()
    group_by = (ctx.get("group_by") or "").lower()

    want_metric = rule.get("metric")
    if want_metric and metric != want_metric.lower():
        return False

    group_by_ok = rule.get("group_by") or []
    if group_by_ok and group_by not in [g.lower() for g in group_by_ok]:
        return False

    keywords = rule.get("keywords") or []
    if keywords and not _has_any(raw_text, keywords):
        return False

    return True


def _match_keyword_fallback(ctx: dict, raw_text: str, rule: dict) -> bool:
    keywords = rule.get("keywords") or []
    if not keywords or not _has_any(raw_text, keywords):
        return False

    allowed = rule.get("metric_allowed")
    if allowed is not None and not _metric_allowed((ctx.get("metric") or "").lower(), allowed):
        return False

    return True


def dispatch(context: dict) -> dict:
    """根据 resolved_context 匹配能力（config 声明式规则）。"""
    ctx = context.get("resolved_context", context)
    raw_text = context.get("raw_text", "")

    config = load_config()
    enabled = config.get("enabled_capabilities", [])
    caps = config.get("capabilities", {})
    registry = _load_registry()

    # Pass 1: explicit metric/group_by/keywords rules, in config order
    for cap_id in caps:
        if cap_id not in enabled:
            continue
        rule = (caps[cap_id].get("dispatch") or {}).get("explicit")
        if not rule:
            continue
        if _match_explicit(ctx, raw_text, rule):
            return _build(cap_id, caps[cap_id], "explicit rule", rule.get("confidence", 0.5), registry)

    # Pass 2: keyword fallback rules, in config order
    for cap_id in caps:
        if cap_id not in enabled:
            continue
        rule = (caps[cap_id].get("dispatch") or {}).get("keyword_fallback")
        if not rule:
            continue
        if _match_keyword_fallback(ctx, raw_text, rule):
            return _build(cap_id, caps[cap_id], "keyword fallback", rule.get("confidence", 0.5), registry)

    labels = [caps[c].get("label", c) for c in caps if c in enabled]
    listed = "、".join(labels) if labels else "无"
    return {"capability_id": None, "error": "no_capability_matched",
            "message": f"未匹配到已启用的能力：{listed}。"}


def _build(cap_id: str, cap_cfg: dict, reason: str, confidence: float, registry: list) -> dict:
    script = cap_cfg.get("script", f"mashang_workspace/runtime_scripts/{cap_id}.py")
    cap = _find_capability(registry, cap_id)
    return {
        "capability_id": cap_id,
        "script": str(Path(_V2_ROOT.parent) / script),
        "reason": reason,
        "confidence": confidence,
        "capability": cap,
    }


def _find_capability(registry: list, cap_id: str) -> dict | None:
    for c in registry:
        if c.get("capability_id") == cap_id:
            return c
    return None
