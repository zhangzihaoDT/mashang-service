#!/usr/bin/env python
"""
Runtime V2 Eval Runner

读取 eval/runtime_v2_cases.json，支持单轮和多轮 (turns) case。
调用 runtime_service pipeline 验证结果。
"""

import sys, argparse, json
from pathlib import Path

_V2_ROOT = Path(__file__).resolve().parents[1]
_WS_ROOT = _V2_ROOT.parent / "mashang_workspace"
_PRJ_ROOT = _V2_ROOT.parent
for p in [str(_V2_ROOT), str(_PRJ_ROOT), str(_WS_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.runtime_service import run_pipeline
from app.session_store import delete as delete_session


def evaluate_case(case: dict) -> dict:
    case_id = case.get("case_id", "unknown")
    turns = case.get("turns", [])

    if turns:
        return _evaluate_turns(case_id, turns)
    # Single turn
    user_text = case.get("user_text", "")
    expected_cap = case.get("expected_capability")
    must_contain = case.get("must_contain", [])
    return _evaluate_single(case_id, user_text, expected_cap, must_contain)


def _evaluate_single(case_id: str, user_text: str, expected_cap: str | None,
                     must_contain: list[str], session_id: str = "",
                     expected_error: str | None = None,
                     allow_warning: bool = False) -> dict:
    result = run_pipeline(user_text)
    checks = _make_checks(result, expected_cap, must_contain,
                          expected_error=expected_error, allow_warning=allow_warning)
    all_passed = all(c["passed"] for c in checks)
    return {"case_id": case_id, "passed": all_passed, "checks": checks,
            "answer_preview": result.get("answer", "")[:200]}


def _evaluate_turns(case_id: str, turns: list[dict]) -> dict:
    session_id = f"eval_{case_id}"
    delete_session(session_id)
    checks = []
    for i, turn in enumerate(turns):
        r = run_pipeline(turn["user_text"], session_id=session_id)
        tc = _make_checks(r, turn.get("expected_capability"), turn.get("must_contain", []),
                          prefix=f"turn{i}_",
                          expected_error=turn.get("expected_error"),
                          allow_warning=turn.get("allow_warning", False))
        checks.extend(tc)
    delete_session(session_id)
    all_passed = all(c["passed"] for c in checks)
    return {"case_id": case_id, "passed": all_passed, "checks": checks}


def _make_checks(result: dict, expected_cap: str | None, must_contain: list[str],
                 prefix: str = "", expected_error: str | None = None,
                 allow_warning: bool = False) -> list[dict]:
    checks = []
    actual_cap = result.get("dispatch", {}).get("capability_id")

    if expected_error:
        dispatch_err = result.get("dispatch", {}).get("error", "")
        actual_err = dispatch_err or actual_cap
        err_ok = expected_error in str(actual_err)
        checks.append({"name": f"{prefix}error", "passed": err_ok,
                       "detail": f"error={actual_err} (expected={expected_error})"})
    elif expected_cap:
        cap_ok = actual_cap == expected_cap
        checks.append({"name": f"{prefix}capability", "passed": cap_ok,
                       "detail": f"cap={actual_cap} (expected {expected_cap})"})
    answer = result.get("answer", "")
    for kw in must_contain:
        kw_ok = kw in answer
        checks.append({"name": f"{prefix}contains_{kw[:20]}", "passed": kw_ok,
                       "detail": f"contains '{kw}'={kw_ok}"})
    return checks


def main():
    parser = argparse.ArgumentParser(description="Runtime V2 Eval Runner")
    parser.add_argument("--cases", type=str,
                        default=str(_V2_ROOT / "eval" / "runtime_v2_cases.json"))
    parser.add_argument("--output", type=str, help="输出 JSON 文件路径")
    parser.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    args = parser.parse_args()

    cases_path = Path(args.cases)
    cases = json.loads(cases_path.read_text())

    results = [evaluate_case(c) for c in cases]
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    output = {
        "meta": {"total": total, "passed": passed, "failed": failed,
                 "pass_rate": round(passed / total, 4) if total else 0},
        "results": results,
    }

    if args.format == "json":
        body = json.dumps(output, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(body, encoding="utf-8")
            print(f"[Output] JSON: {args.output}")
        else:
            print(body)
    else:
        print(f"Runtime V2 Eval — {passed}/{total} passed, {failed} failed")
        for r in results:
            emoji = "✅" if r["passed"] else "❌"
            print(f"  {emoji} {r['case_id']}")
            for c in r["checks"]:
                ck = "✅" if c["passed"] else "❌"
                print(f"    {ck} {c['name']}: {c['detail']}")


if __name__ == "__main__":
    main()
