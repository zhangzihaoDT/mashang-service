"""State, queue, evidence and question-derivation primitives."""

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
    evidence.setdefault("relation", "supports")          # supports|contradicts|refines|rules_out|explains
    evidence.setdefault("targets", [])                    # hypothesis ids
    evidence.setdefault("parents", [])                    # evidence ids this builds on
    evidence.setdefault("hypothesis_id", None)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(evidence, ensure_ascii=False, default=str) + "\n")
    state = read_state(topic)
    state.setdefault("evidence_ids", []).append(evidence["id"])
    state["last_analysis"] = evidence.get("analysis")
    write_state(topic, state)
    return evidence["id"]


def load_queue() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "queue.yaml").read_text(encoding="utf-8")) or {}


def write_queue(queue: dict[str, Any]) -> None:
    (ROOT / "queue.yaml").write_text(
        yaml.safe_dump(queue, allow_unicode=True, sort_keys=False), encoding="utf-8")


def derive_questions(result: dict[str, Any], state: dict[str, Any],
                     queue_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn an Analysis Result Contract into candidate next questions.

    Heuristics:
      - compare rows  -> drilldown (largest gap metric) + explain_gap (smallest)
      - sequential regress path -> suppression/confounder question
      - diagnostics list       -> typed follow-up questions
    """
    res = result.get("result", {})
    questions: list[dict[str, Any]] = []
    seen = {q.get("question") for q in queue_items}

    def add(qtype: str, question: str, priority: int) -> None:
        if question not in seen:
            questions.append({"type": qtype, "question": question, "priority": priority})
            seen.add(question)

    rows = res.get("rows")
    if isinstance(rows, list) and rows:
        metrics = [k for k in rows[0] if k not in ("value", "label", "n")
                   and isinstance(rows[0][k], (int, float))]
        if len(rows) >= 2 and metrics:
            pairs = []
            for i in range(len(rows)):
                for j in range(i + 1, len(rows)):
                    gaps = {m: rows[j][m] - rows[i][m] for m in metrics}
                    pairs.append((i, j, sum(abs(g) for g in gaps.values()), gaps))
            if pairs:
                i, j, _, gaps = max(pairs, key=lambda p: p[2])
                g0, g1 = str(rows[i].get("label", rows[i].get("value"))), str(rows[j].get("label", rows[j].get("value")))
                largest = max(gaps, key=lambda m: abs(gaps[m]))
                smallest = min(gaps, key=lambda m: abs(gaps[m]))
                if abs(gaps[largest]) >= 1.0:
                    add("drilldown", f"{largest} 差异（{g0} vs {g1}）由哪些具体题项驱动？", 92)
                if smallest != largest and abs(gaps[largest]) - abs(gaps[smallest]) >= 2.0:
                    add("explain_gap", f"为什么 {largest} 的差异（{gaps[largest]:+.1f}）显著高于 {smallest}（{gaps[smallest]:+.1f}）？", 90)

    if res.get("mode") == "sequential" and res.get("path"):
        path = res["path"]
        if len(path) >= 2:
            first, last = path[0], path[-1]
            if first.get("coef") and last.get("coef") and first["coef"] != 0:
                ratio = abs(last["coef"] / first["coef"])
                if ratio >= 1.2:
                    add("confounder",
                        f"哪个控制变量产生 suppression 效应（exposure coef {first['coef']:+.2f} → {last['coef']:+.2f}，{ratio:.2f}×）？逐控制变量诊断。",
                        95)

    for d in res.get("diagnostics") or []:
        dtype = d.get("type")
        if dtype == "coefficient_amplification":
            add("confounder", "效应在控制后放大，哪个控制变量解释？逐变量 coefficient path。", 93)
        elif dtype == "sign_reversal":
            add("confounder", "效应符号反转，识别结构性混淆来源。", 96)
        elif dtype == "significance_disappears":
            add("confounder", "控制后显著性消失，哪个变量吸收了原始差异？", 94)
        elif dtype == "significance_emerges":
            add("confounder", "控制后效应显现，可能存在负混淆。", 88)
        elif dtype == "tiny_effect_significant":
            add("interpret", "效应统计显著但低于业务阈值，重估商业意义。", 70)

    return questions


def enqueue(topic: str, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append derived questions to queue.yaml (dedup by question text)."""
    queue = load_queue()
    existing_q = {item.get("question") for item in queue.get("items", [])}
    added = []
    for q in questions:
        if q.get("question") in existing_q:
            continue
        item = {
            "id": f"Q{len(queue.get('items', [])) + len(added) + 1:03d}",
            "priority": q.get("priority", 50),
            "question": q["question"],
            "reason": f"auto-derived from analysis ({q.get('type')})",
            "action": q.get("action", ""),
            "status": "open",
        }
        queue.setdefault("items", []).append(item)
        existing_q.add(q["question"])
        added.append(item)
    write_queue(queue)
    return added


def next_action(topic: str) -> dict[str, Any]:
    queue = load_queue()
    state = read_state(topic)
    if state.get("status") in set(queue.get("stop_conditions", {}).get("terminal_statuses", [])):
        return {"status": "stopped", "reason": state.get("stop_reason"), "state": state}
    open_items = [item for item in queue.get("items", []) if item.get("status") == "open"]
    open_items.sort(key=lambda item: item.get("priority", 0), reverse=True)
    return {"status": "continue" if open_items else "stopped", "action": open_items[0] if open_items else None, "state": state}


def evaluate_stop(topic: str) -> dict[str, Any]:
    queue = load_queue()
    state = read_state(topic)
    evidence_path = run_dir(topic) / "evidence.jsonl"
    count = len(evidence_path.read_text(encoding="utf-8").splitlines()) if evidence_path.exists() else 0
    rules = queue.get("stop_conditions", {})
    gates = {
        "evidence_count": count >= rules.get("min_supporting_evidence", 2),
        "confidence": state.get("confidence") in {"medium", "high"},
        "effect_interpreted": bool(state.get("effect_interpreted", False)),
        "mechanism_depth": int(state.get("mechanism_depth", 0)) >= int(rules.get("min_mechanism_depth", 3)),
        "no_high_priority_open": not any(
            item.get("status") == "open" and int(item.get("priority", 0)) >= int(rules.get("high_priority_threshold", 85))
            for item in queue.get("items", [])
        ),
    }
    ready = all(gates.values())
    if ready and state.get("status") != "ready":
        state["status"] = "ready"
        state["stop_reason"] = "READY: evidence + confidence + mechanism_depth + no high-priority open question"
        write_state(topic, state)
    return {"status": state.get("status", "exploring"), "gates": gates, "evidence_count": count, "state": state}
