#!/usr/bin/env python3
"""
逐条运行 eval/runtime_cases.jsonl，检查 Agent Runtime 行为是否符合 expected。

用法:
    python eval/run_runtime_eval.py
    python eval/run_runtime_eval.py --limit 10 --verbose
    python eval/run_runtime_eval.py \
        --cases eval/runtime_cases.jsonl \
        --report eval/eval_report.json
"""

import argparse
import json
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("ENABLE_QUERY_LOG", "1")

from agent.agent_loop import run_main_agent


class _TimeoutError(Exception):
    pass


def _run_agent_with_timeout(question: str, timeout: int) -> None:
    if not hasattr(signal, "SIGALRM"):
        run_main_agent(question)
        return

    def _handler(signum, frame):
        raise _TimeoutError(f"case timed out after {timeout}s")

    old_handler = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(timeout)
    try:
        run_main_agent(question)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs",
    "query_log.jsonl",
)


def _count_log_lines() -> int:
    try:
        with open(_LOG_PATH) as f:
            return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def _read_last_log(after_line: int) -> dict | None:
    try:
        with open(_LOG_PATH) as f:
            lines = f.readlines()
        if len(lines) <= after_line:
            return None
        last = lines[-1].strip()
        return json.loads(last) if last else None
    except Exception:
        return None


def _run_case(case: dict, timeout: int = 60) -> dict:
    case_id = case.get("case_id", "?")
    question = case.get("question", "")
    expected = case.get("expected", {})

    if not question:
        return {
            "case_id": case_id,
            "question": "",
            "passed": False,
            "status": "failed",
            "checks": {},
            "actual": {},
            "error": "empty question",
        }

    before = _count_log_lines()

    try:
        _run_agent_with_timeout(question, timeout)
    except _TimeoutError:
        return {
            "case_id": case_id,
            "question": question[:80],
            "passed": False,
            "status": "failed",
            "checks": {},
            "actual": {},
            "warning": "case_timeout",
            "error": f"timeout after {timeout}s",
        }
    except Exception as e:
        return {
            "case_id": case_id,
            "question": question[:80],
            "passed": False,
            "status": "failed",
            "checks": {},
            "actual": {},
            "error": str(e),
        }

    actual_log = _read_last_log(after_line=before)
    if actual_log is None:
        return {
            "case_id": case_id,
            "question": question,
            "passed": False,
            "checks": {},
            "actual": {},
            "error": "no new log entry",
        }

    actual = {
        "exit_reason": actual_log.get("exit_reason") or "",
        "eval_intent": actual_log.get("eval_intent") or "",
        "contract_matched": bool(actual_log.get("contract_matched", False)),
        "fact_types": actual_log.get("fact_types") or [],
        "structured_block_count": len(actual_log.get("structured_blocks_summary") or []),
    }

    checks = {}

    # 1. exit_reason not in forbidden list
    forbidden = expected.get("exit_reason_not_in") or []
    checks["no_forbidden_exit_reason"] = actual["exit_reason"] not in forbidden

    # 2. intent match (skip if expected intent is empty)
    exp_intent = expected.get("intent") or ""
    checks["intent_match"] = (
        True if not exp_intent else actual["eval_intent"] == exp_intent
    )

    # 3. contract match (skip if expected.contract_matched is None / missing)
    exp_contract = expected.get("contract_matched")
    checks["contract_match"] = (
        True
        if exp_contract is None
        else bool(actual["contract_matched"]) == bool(exp_contract)
    )

    # 4. min structured blocks (skip if <= 0)
    min_blocks = expected.get("min_structured_blocks") or 0
    checks["min_structured_blocks"] = (
        True if min_blocks <= 0 else actual["structured_block_count"] >= min_blocks
    )

    # 5. fact_types intersection (skip if empty)
    exp_facts = expected.get("fact_types_any") or []
    checks["fact_types_any"] = (
        True
        if not exp_facts
        else bool(set(actual["fact_types"]) & set(exp_facts))
    )

    all_checks_pass = all(checks.values())
    contract_match_only_fail = (
        not checks.get("contract_match", True)
        and all(v for k, v in checks.items() if k != "contract_match")
    )
    min_blocks_only_fail = (
        not checks.get("min_structured_blocks", True)
        and actual["structured_block_count"] > 0
        and all(v for k, v in checks.items() if k != "min_structured_blocks")
    )
    exit_reason = actual["exit_reason"]

    _STABLE_REASONS = {
        "metric_value_found",
        "trend_summary_found",
        "dimension_breakdown_found",
        "dimension_share_trend_found",
        "share_breakdown_found",
        "default_has_result_and_satisfies_goal",
        "uncertain_finish",
    }
    _RISK_REASONS = {
        "contract_repair_limit",
        "stall_detected",
        "repair_limit_reached",
        "max_steps_reached",
    }

    warning = None
    if min_blocks_only_fail and (
        checks.get("fact_types_any", False)
        or checks.get("contract_match", False)
        or exit_reason in _STABLE_REASONS
    ):
        _passed = True
        status = "soft_pass"
        warning = "structured_block_count_below_expected_but_has_evidence"
    elif all_checks_pass:
        _passed = True
        if actual["contract_matched"]:
            status = "hard_pass"
        else:
            status = "soft_pass"
            warning = "passed_but_contract_not_matched"
    elif contract_match_only_fail:
        if exit_reason in _STABLE_REASONS:
            _passed = True
            status = "soft_pass"
            warning = "contract_match_mismatch_but_functional_pass"
        elif exit_reason in _RISK_REASONS:
            _passed = False
            status = "soft_fail"
            warning = "contract_match_mismatch_with_runtime_risk"
        else:
            _passed = False
            status = "soft_fail"
            warning = "contract_match_mismatch_with_runtime_risk"
    else:
        _passed = False
        status = "failed"

    result = {
        "case_id": case_id,
        "question": question[:80],
        "passed": _passed,
        "status": status,
        "checks": checks,
        "actual": actual,
        "error": None,
    }
    if warning:
        result["warning"] = warning
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Runtime Eval Runner")
    parser.add_argument(
        "--cases", default="eval/runtime_cases.jsonl", help="cases 文件路径"
    )
    parser.add_argument(
        "--report", default="eval/eval_report.json", help="report 输出路径"
    )
    parser.add_argument("--limit", type=int, default=0, help="最多执行 N 条")
    parser.add_argument("--timeout", type=int, default=60, help="单 case 超时秒数 (默认 60)")
    parser.add_argument("--verbose", action="store_true", help="打印每条结果")
    args = parser.parse_args()

    cases_path = os.path.abspath(args.cases)
    report_path = os.path.abspath(args.report)

    try:
        with open(cases_path, encoding="utf-8") as f:
            cases = [
                json.loads(line)
                for line in f
                if line.strip()
            ]
    except FileNotFoundError:
        print(f"[Error] 未找到 cases 文件: {cases_path}")
        sys.exit(1)

    if args.limit and args.limit > 0:
        cases = cases[: args.limit]

    if not cases:
        print("[Warning] cases 文件为空")
        sys.exit(0)

    print(f"Running {len(cases)} eval case(s) ...")

    results: list[dict] = []
    for i, case in enumerate(cases):
        cid = case.get("case_id", "?")
        q = (case.get("question") or "")[:50]
        if args.verbose:
            print(f"  [{i + 1}/{len(cases)}] {cid}: {q} ...")

        result = _run_case(case, timeout=args.timeout)
        results.append(result)

        if args.verbose:
            status_label = result.get("status", "FAIL").upper()
            detail = result.get("error") or (
                str(result.get("checks")) if not result["passed"] else ""
            )
            warning = result.get("warning")
            if warning:
                detail = (detail + "; " if detail else "") + warning
            print(f"    {status_label}{'  ' + detail if detail else ''}")

    total = len(results)
    hard_pass = sum(1 for r in results if r.get("status") == "hard_pass")
    soft_pass = sum(1 for r in results if r.get("status") == "soft_pass")
    soft_fail = sum(1 for r in results if r.get("status") == "soft_fail")
    hard_failed = sum(1 for r in results if r.get("status") == "failed")
    timeout_count = sum(1 for r in results if r.get("warning") == "case_timeout")
    _passed = hard_pass + soft_pass
    _failed = soft_fail + hard_failed
    rate = round(_passed / total, 4) if total else 0.0

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "total": total,
                "passed": _passed,
                "failed": _failed,
                "pass_rate": rate,
                "hard_pass": hard_pass,
                "soft_pass": soft_pass,
                "soft_fail": soft_fail,
                "hard_failed": hard_failed,
                "timeout_count": timeout_count,
                "results": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\n{'=' * 50}")
    print(f"  Eval Report: {_passed}/{total} passed ({rate:.1%})")
    print(f"    hard_pass: {hard_pass}")
    print(f"    soft_pass: {soft_pass}")
    print(f"    soft_fail: {soft_fail}")
    print(f"    failed   : {hard_failed}")
    if timeout_count:
        print(f"    timeout  : {timeout_count}")
    if hard_failed or soft_fail:
        print(f"  Non-passing cases:")
        for r in results:
            if r.get("status") in ("soft_fail", "failed"):
                err = r.get("error") or ""
                chk = r.get("checks", {})
                print(f"    [{r.get('status')}] {r['case_id']}: {err or chk}")
    print(f"{'=' * 50}")
    print(f"  Report saved to: {report_path}")


if __name__ == "__main__":
    main()
