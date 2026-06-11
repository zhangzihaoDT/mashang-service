#!/usr/bin/env python3
"""
从 logs/query_log.jsonl 生成 eval/runtime_cases.jsonl，支持多种抽样策略。

用法:
    python scripts/generate_eval_cases.py
    python scripts/generate_eval_cases.py --strategy first
    python scripts/generate_eval_cases.py --strategy recent --limit 20
    python scripts/generate_eval_cases.py --strategy stratified --limit 50
    python scripts/generate_eval_cases.py --include-failures --limit 20
"""

import argparse
import json
import os
import random
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 query_log 生成 runtime eval cases")
    parser.add_argument("--input", default="logs/query_log.jsonl", help="输入 query_log.jsonl 路径")
    parser.add_argument("--output", default="eval/runtime_cases.jsonl", help="输出 runtime_cases.jsonl 路径")
    parser.add_argument("--include-failures", action="store_true", help="包含 execution_success=False 的样本")
    parser.add_argument("--limit", type=int, default=0, help="最多输出 N 条（0=不限制）")
    parser.add_argument("--strategy", default="stratified",
                        choices=["first", "recent", "random", "stratified"],
                        help="抽样策略（默认 stratified）")
    parser.add_argument("--per-intent", type=int, default=10, help="每个 eval_intent 最多抽 N 条")
    parser.add_argument("--per-exit-reason", type=int, default=5, help="每个 exit_reason 最多抽 N 条")
    parser.add_argument("--recent", type=int, default=20, help="强制加入最近 N 条")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    return parser.parse_args()


SPECIAL_EXIT_REASONS = frozenset({
    "clarification",
    "uncertain_finish",
    "contract_repair_limit",
    "stall_detected",
    "max_steps_reached",
    "error",
    "exception",
})


def load_logs(path: str) -> list[dict]:
    records: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    records.append(obj)
    except FileNotFoundError:
        print(f"[Error] 未找到输入文件: {path}")
        sys.exit(1)
    return records


def should_include(entry: dict, include_failures: bool) -> bool:
    success = bool(entry.get("execution_success", False))
    if success:
        return True
    if include_failures:
        return True
    reason = entry.get("exit_reason") or ""
    return reason in SPECIAL_EXIT_REASONS


def to_case(entry: dict, idx: int) -> dict:
    case_id = entry.get("query_id") or f"q_{idx:04d}"

    reason = entry.get("exit_reason") or ""
    excluded = [r for r in ["error", "exception"] if r != reason]

    steps = entry.get("generated_plan")
    if isinstance(steps, dict):
        steps = steps.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    return {
        "case_id": case_id,
        "source_query_id": entry.get("query_id", ""),
        "source_timestamp": entry.get("timestamp", ""),
        "question": entry.get("question", ""),
        "normalized_question": entry.get("normalized_question", ""),
        "expected": {
            "intent": entry.get("eval_intent", ""),
            "contract_matched": bool(entry.get("contract_matched", False)),
            "exit_reason": reason,
            "execution_success": bool(entry.get("execution_success", False)),
            "fact_types_any": entry.get("fact_types", []),
            "min_structured_blocks": len(entry.get("structured_blocks_summary", [])),
            "exit_reason_not_in": excluded,
        },
        "source": {
            "plan_steps": steps,
            "final_answer": entry.get("final_answer", ""),
            "result_summary": entry.get("result_summary", ""),
        },
    }


def dedup_by_question(records: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for r in records:
        key = (r.get("normalized_question") or r.get("question") or "").strip()
        if not key:
            key = r.get("timestamp", "") + str(id(r))
        seen[key] = r
    return list(seen.values())


def strategy_first(records: list[dict], args: argparse.Namespace) -> list[dict]:
    included = [r for r in records if should_include(r, args.include_failures)]
    if args.limit and args.limit > 0:
        included = included[: args.limit]
    return included


def strategy_recent(records: list[dict], args: argparse.Namespace) -> list[dict]:
    included = [r for r in records if should_include(r, args.include_failures)]
    included.reverse()
    if args.limit and args.limit > 0:
        included = included[: args.limit]
    return included


def strategy_random(records: list[dict], args: argparse.Namespace) -> list[dict]:
    rng = random.Random(args.seed)
    included = [r for r in records if should_include(r, args.include_failures)]
    rng.shuffle(included)
    if args.limit and args.limit > 0:
        included = included[: args.limit]
    return included


def get_normalized_question(rec: dict) -> str:
    return (rec.get("normalized_question") or rec.get("question") or "").strip()


def strategy_stratified(records: list[dict], args: argparse.Namespace) -> list[dict]:
    rng = random.Random(args.seed)

    usable = [r for r in records if should_include(r, args.include_failures)]

    special: list[dict] = []
    normal: list[dict] = []
    for r in usable:
        reason = (r.get("exit_reason") or "").strip()
        if reason in SPECIAL_EXIT_REASONS:
            special.append(r)
        else:
            normal.append(r)

    special_dedup = dedup_by_question(special)
    normal_dedup = dedup_by_question(normal)

    selected: list[dict] = []
    seen_keys: set[str] = set()

    def _add(rec: dict) -> bool:
        key = get_normalized_question(rec)
        if not key:
            key = rec.get("timestamp", "") + rec.get("query_id", "")
        if key in seen_keys:
            return False
        seen_keys.add(key)
        selected.append(rec)
        return True

    border: list[dict] = []
    for r in special_dedup:
        _add(r)
        border.append(r)

    def _sample_bucket(pool: list[dict], bucket_key: str, max_per: int) -> list[dict]:
        buckets: dict[str, list[dict]] = {}
        for r in pool:
            k = str(r.get(bucket_key, "") or "unknown")
            buckets.setdefault(k, []).append(r)

        result: list[dict] = []
        keys_sorted = sorted(buckets.keys())
        for k in keys_sorted:
            group = buckets[k]
            rng.shuffle(group)
            for r in group:
                if len(result) >= max_per:
                    break
                result.append(r)
        return result

    intent_samples = _sample_bucket(normal_dedup, "eval_intent", args.per_intent)
    for r in intent_samples:
        _add(r)

    exit_samples = _sample_bucket(normal_dedup, "exit_reason", args.per_exit_reason)
    for r in exit_samples:
        _add(r)

    contract_pool = [r for r in normal_dedup if get_normalized_question(r) not in seen_keys]
    for target in [True, False]:
        found = [r for r in contract_pool if bool(r.get("contract_matched", False)) is target]
        if found:
            rng.shuffle(found)
            _add(found[0])

    normal_dedup.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    recent_count = 0
    for r in normal_dedup:
        if recent_count >= args.recent:
            break
        if _add(r):
            recent_count += 1

    if args.limit and args.limit > 0:
        selected = selected[: args.limit]

    return selected


def print_summary(records: list[dict], output_cases: list[dict], output_path: str) -> None:
    print(f"[OK] {output_path}  ({len(output_cases)} cases)")

    intent_counts: dict[str, int] = {}
    exit_counts: dict[str, int] = {}
    success_count = 0
    fail_count = 0
    for c in output_cases:
        intent = c["expected"]["intent"] or "unknown"
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
        reason = c["expected"]["exit_reason"] or "unknown"
        exit_counts[reason] = exit_counts.get(reason, 0) + 1
        if c["expected"]["execution_success"]:
            success_count += 1
        else:
            fail_count += 1

    print(f"  输入日志: {len(records)} 条")
    unique = dedup_by_question(records)
    print(f"  去重后  : {len(unique)} 条")
    print(f"  输出 case: {len(output_cases)} 条")
    print(f"  按 eval_intent 统计: {dict(sorted(intent_counts.items()))}")
    print(f"  按 exit_reason 统计: {dict(sorted(exit_counts.items()))}")
    print(f"  execution_success: True={success_count} False={fail_count}")


def main() -> None:
    args = parse_args()

    input_path = os.path.abspath(args.input)
    output_path = os.path.abspath(args.output)

    records = load_logs(input_path)
    if not records:
        print(f"[Warning] {input_path} 中无有效记录")
        sys.exit(0)

    strategy_map = {
        "first": strategy_first,
        "recent": strategy_recent,
        "random": strategy_random,
        "stratified": strategy_stratified,
    }
    selected = strategy_map[args.strategy](records, args)

    if not selected:
        print(f"[Warning] 共 {len(records)} 条记录，均被过滤器排除")
        sys.exit(0)

    out_dir = os.path.dirname(output_path)
    os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for i, entry in enumerate(selected):
            case = to_case(entry, i + 1)
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    print_summary(records, [to_case(e, i + 1) for i, e in enumerate(selected)], output_path)


if __name__ == "__main__":
    main()
