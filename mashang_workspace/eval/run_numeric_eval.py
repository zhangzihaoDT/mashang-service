#!/usr/bin/env python
"""
Numeric Eval Runner — 执行并校验脚本的 Result Contract

读取 eval/cases/numeric_cases.json，对每个 case:
  1. 执行 command
  2. 解析 Result Contract JSON
  3. 校验 status / required_fields / numeric metrics
  4. 输出 pass/fail

用法:
    python eval/run_numeric_eval.py --help
    python eval/run_numeric_eval.py
    python eval/run_numeric_eval.py --format json --output outputs/tables/numeric_eval_result.json
"""

import sys, argparse, json, subprocess
from pathlib import Path

import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parents[1])); from utils.paths import WORKSPACE_ROOT, OUTPUTS_DIR

DEFAULT_CASES = WORKSPACE_ROOT / "eval" / "cases" / "numeric_cases.json"


def _resolve_command(command: str) -> str:
    """将命令开头的 python 替换为当前解释器，避免依赖系统 PATH 中的 python。"""
    stripped = command.strip()
    if stripped.startswith("python "):
        return sys.executable + stripped[len("python"):]
    if stripped.startswith("python3 "):
        return sys.executable + stripped[len("python3"):]
    return command


def _field_exists(data: dict, field_path: str) -> bool:
    """检查嵌套字段是否存在，如 'result.dimensions'。"""
    parts = field_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False
    return True


def _check_metric(contract: dict, key: str, expected_val: dict) -> tuple[bool, str]:
    """检查指标数值条件。"""
    result = contract.get("result", {})
    metrics = result.get("metrics", {})
    actual = metrics.get(key)
    if actual is None:
        return False, f"metrics.{key} not found"
    op = expected_val.get("operator", ">=")
    target = expected_val.get("value", 0)
    if op == ">=":
        ok = actual >= target
    elif op == ">":
        ok = actual > target
    elif op == "==":
        ok = actual == target
    elif op == "<=":
        ok = actual <= target
    else:
        ok = True
    return ok, f"metrics.{key}={actual} {op} {target}"


def evaluate_case(case: dict, timeout: int = 60) -> dict:
    case_id = case.get("case_id", "unknown")
    command = _resolve_command(case.get("command", ""))
    expected = case.get("expected", {})
    checks = []

    # 执行
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, timeout=timeout,
    )
    stdout = result.stdout

    # 尝试解析 contract JSON
    contract = None
    contract_parse_error = None
    if stdout.strip().startswith("{"):
        try:
            contract = json.loads(stdout)
        except json.JSONDecodeError as e:
            contract_parse_error = str(e)

    # 如果 stdout 没有 JSON，尝试从 output 目录读取
    if not contract:
        out_dir = OUTPUTS_DIR / "tables"
        # find the latest JSON in outputs/tables that matches the case
        candidate = None
        for f in sorted(out_dir.glob("*.json"), reverse=True):
            try:
                candidate = json.loads(f.read_text())
            except Exception:
                continue
            # heuristic: match scope fields
            if candidate.get("script", "").endswith(case_id.split("_")[2] + ".py"):
                contract = candidate
                break
            if candidate.get("status") == "success":
                contract = candidate
                break

    # Status 校验（支持字符串或列表）
    expected_status = expected.get("status", "success")
    actual_status = contract.get("status", "error") if contract else "error"
    if isinstance(expected_status, list):
        status_ok = actual_status in expected_status
    else:
        status_ok = actual_status == expected_status
    checks.append({
        "name": "status_match",
        "passed": status_ok,
        "detail": f"status={actual_status} (expected {expected_status})",
    })

    if not contract:
        checks.append({
            "name": "contract_parse",
            "passed": False,
            "detail": contract_parse_error or "no JSON contract found in stdout",
        })
        return {"case_id": case_id, "passed": False, "checks": checks, "error": "contract_parse_failed"}

    # Required fields 校验
    for field_path in expected.get("required_fields", []):
        exists = _field_exists(contract, field_path)
        checks.append({
            "name": f"field.{field_path}",
            "passed": exists,
            "detail": f"{'found' if exists else 'not found'}",
        })

    # Metrics 校验
    for metric_key, metric_cfg in expected.get("metrics", {}).items():
        ok, detail = _check_metric(contract, metric_key, metric_cfg)
        checks.append({"name": f"metric.{metric_key}", "passed": ok, "detail": detail})

    # Warnings / Errors
    if contract.get("errors"):
        checks.append({
            "name": "no_errors",
            "passed": False,
            "detail": f"contract has errors: {contract['errors']}",
        })

    all_passed = all(c["passed"] for c in checks)
    return {"case_id": case_id, "passed": all_passed, "checks": checks, "contract_status": actual_status}


def main():
    parser = argparse.ArgumentParser(description="Numeric Eval Runner")
    parser.add_argument("--cases", type=str, default=str(DEFAULT_CASES))
    parser.add_argument("--output", type=str, help="输出 JSON 文件路径")
    parser.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--tier", type=str, default="all", choices=["all", "core", "research"],
                        help="过滤 case tier (core/research/all)")
    args = parser.parse_args()

    cases_path = Path(args.cases)
    if not cases_path.exists():
        print(f"[Error] cases 文件不存在: {cases_path}", file=sys.stderr)
        sys.exit(1)

    with open(cases_path) as f:
        all_cases = json.load(f)

    if args.tier != "all":
        cases = [c for c in all_cases if c.get("tier", "core") == args.tier]
    else:
        cases = all_cases

    results = []
    for case in cases:
        result = evaluate_case(case, timeout=args.timeout)
        results.append(result)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    output = {
        "meta": {"total": total, "passed": passed, "failed": failed, "pass_rate": round(passed / total * 100, 1) if total else 0},
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
        print(f"{'='*60}")
        print(f"Numeric Eval Runner")
        print(f"{'='*60}")
        print(f"  Total: {total}, Passed: {passed}, Failed: {failed}, Rate: {output['meta']['pass_rate']}%")
        print()
        for r in results:
            status = "✅" if r["passed"] else "❌"
            print(f"  {status} {r['case_id']}")
            for c in r["checks"]:
                ck = "✅" if c["passed"] else "❌"
                print(f"    {ck} {c['name']}: {c['detail']}")
            print()

    return output


if __name__ == "__main__":
    main()
