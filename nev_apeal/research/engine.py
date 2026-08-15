"""State, queue and evidence primitives for the Agentic Analytical Workspace."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"


def run_dir(topic: str) -> Path:
    path = RUNS / topic
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_state(topic: str) -> dict[str, Any]:
    path = run_dir(topic) / "state.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_state(topic: str, state: dict[str, Any]) -> None:
    path = run_dir(topic) / "state.yaml"
    path.write_text(yaml.safe_dump(state, allow_unicode=True, sort_keys=False), encoding="utf-8")


def append_evidence(topic: str, evidence: dict[str, Any]) -> str:
    path = run_dir(topic) / "evidence.jsonl"
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    evidence = dict(evidence)
    evidence.setdefault("id", f"E-{len(existing) + 1:03d}")
    evidence.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(evidence, ensure_ascii=False, default=str) + "\n")
    state = read_state(topic)
    state.setdefault("evidence_ids", []).append(evidence["id"])
    state["last_analysis"] = evidence.get("analysis")
    write_state(topic, state)
    return evidence["id"]


def next_action(topic: str) -> dict[str, Any]:
    queue = yaml.safe_load((ROOT / "queue.yaml").read_text(encoding="utf-8")) or {}
    state = read_state(topic)
    if state.get("status") in set(queue.get("stop_conditions", {}).get("terminal_statuses", [])):
        return {"status": "stopped", "reason": state.get("stop_reason"), "state": state}
    open_items = [item for item in queue.get("items", []) if item.get("status") == "open"]
    open_items.sort(key=lambda item: item.get("priority", 0), reverse=True)
    return {"status": "continue" if open_items else "stopped", "action": open_items[0] if open_items else None, "state": state}


def evaluate_stop(topic: str) -> dict[str, Any]:
    queue = yaml.safe_load((ROOT / "queue.yaml").read_text(encoding="utf-8")) or {}
    state = read_state(topic)
    evidence_path = run_dir(topic) / "evidence.jsonl"
    count = len(evidence_path.read_text(encoding="utf-8").splitlines()) if evidence_path.exists() else 0
    rules = queue.get("stop_conditions", {})
    if count >= rules.get("min_supporting_evidence", 2) and state.get("confidence") in {"medium", "high"}:
        state["status"] = "ready"
        state["stop_reason"] = "minimum evidence and confidence reached"
    write_state(topic, state)
    return {"status": state.get("status"), "evidence_count": count, "state": state}
