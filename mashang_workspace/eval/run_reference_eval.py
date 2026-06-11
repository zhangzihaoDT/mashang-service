#!/usr/bin/env python
"""
Reference Eval Runner — 校验 result_reference 解析质量

通过子进程调用 _parse_helper.py 避免根目录 eval/ 模块阴影。

用法:
    python mashang_workspace/eval/run_reference_eval.py --help
    python mashang_workspace/eval/run_reference_eval.py
    python mashang_workspace/eval/run_reference_eval.py --format json
"""

import sys, argparse, json, subprocess
from pathlib import Path

import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parents[1])); from utils.paths import WORKSPACE_ROOT, CASES_DIR, OUTPUTS_DIR

PARSE_HELPER = WORKSPACE_ROOT / "eval" / "_parse_helper.py"
DEFAULT_CASES = CASES_DIR / "result_reference_cases.json"


def _parse_via_subprocess(text: str, prev_ctx: dict, prev_result: dict) -> dict:
    """调用 workspace 的 context_parser 解析（避免模块阴影）。"""
    payload = json.dumps({"text": text, "prev_ctx": prev_ctx, "prev_result": prev_result}, ensure_ascii=False)
    r = subprocess.run(
        [sys.executable, str(PARSE_HELPER), payload],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode != 0:
        return {"error": r.stderr[:500]}
    return json.loads(r.stdout)


def evaluate_case(case: dict) -> dict:
    case_id = case.get("case_id", "unknown")
    prev_result = case.get("previous_result_context", {})
    prev_ctx = case.get("previous_context", {})
    turns = case.get("turns", [])
    checks = []

    for turn in turns:
        user_text = turn.get("user", "")
        expected = turn.get("expected", {})

        r = _parse_via_subprocess(user_text, prev_ctx, prev_result)
        ref = r.get("result_reference")
        actual_status = ref.get("status") if ref else None
        expected_status = expected.get("result_reference_status")

        status_ok = actual_status == expected_status
        checks.append({
            "name": f"status[{turn.get('user','')[:30]}]",
            "passed": status_ok,
            "detail": f"status={actual_status} (expected {expected_status})",
        })

        if actual_status == "resolved" and expected.get("series"):
            actual_series = r.get("resolved_context", {}).get("series")
            series_ok = actual_series == expected["series"]
            checks.append({
                "name": f"series[{turn.get('user','')[:30]}]",
                "passed": series_ok,
                "detail": f"series={actual_series} (expected {expected['series']})",
            })

        if actual_status == "ambiguous":
            has_q = bool(ref and ref.get("clarification_question"))
            checks.append({
                "name": f"clarification[{turn.get('user','')[:30]}]",
                "passed": has_q,
                "detail": f"has_clarification={has_q}",
            })

    all_passed = all(c["passed"] for c in checks)
    return {"case_id": case_id, "passed": all_passed, "checks": checks}


def main():
    parser = argparse.ArgumentParser(description="Reference Eval Runner")
    parser.add_argument("--cases", type=str, default=str(DEFAULT_CASES))
    parser.add_argument("--output", type=str, help="输出 JSON 文件路径")
    parser.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    args = parser.parse_args()

    cases_path = Path(args.cases)
    with open(cases_path) as f:
        cases = json.load(f)

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
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(body, encoding="utf-8")
            print(f"[Output] JSON: {out_path}")
        else:
            print(body)
    else:
        print(f"{'='*60}")
        print(f"Reference Eval Runner")
        print(f"{'='*60}")
        print(f"  Total: {total}, Passed: {passed}, Failed: {failed}")
        print()
        for r in results:
            emoji = "✅" if r["passed"] else "❌"
            print(f"  {emoji} {r['case_id']}")
            for c in r["checks"]:
                ck = "✅" if c["passed"] else "❌"
                print(f"    {ck} {c['name']}: {c['detail']}")
            print()

    return output


if __name__ == "__main__":
    main()
