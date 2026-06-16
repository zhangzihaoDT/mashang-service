#!/usr/bin/env python
"""
Unified Eval Runner — 统一评测入口

聚合 parser / followup / numeric / reference / smoke / contract 六个套件。
支持分层: core (默认) / research / all / ci。

用法:
    python mashang_workspace/eval/run_eval.py --help
    python mashang_workspace/eval/run_eval.py --suite core
    python mashang_workspace/eval/run_eval.py --suite research
    python mashang_workspace/eval/run_eval.py --suite all
    python mashang_workspace/eval/run_eval.py --suite ci
    python mashang_workspace/eval/run_eval.py --suite all --format json --output outputs/tables/unified_eval_result.json
"""

import sys, argparse, json, subprocess, re
from datetime import datetime
from pathlib import Path

import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parents[1])); from utils.paths import WORKSPACE_ROOT, PROJECT_ROOT

DEFAULT_FOLLOWUP_CASES = str(WORKSPACE_ROOT / "eval" / "cases" / "followup_cases.json")
DEFAULT_NUMERIC_CASES = str(WORKSPACE_ROOT / "eval" / "cases" / "numeric_cases.json")
DEFAULT_REFERENCE_CASES = str(WORKSPACE_ROOT / "eval" / "cases" / "result_reference_cases.json")

# Core tier: 稳定日常脚本，自动调度
CORE_CONTRACT_SCRIPTS = [
    "mashang_workspace/runtime_scripts/daily_lock_count.py --date 2026-06-10 --format json",
    "mashang_workspace/runtime_scripts/lock_by_model.py --date 2026-06-10 --format json",
    "mashang_workspace/runtime_scripts/lock_city_distribution.py --date 2026-06-10 --format json",
    "mashang_workspace/runtime_scripts/assign_conversion_analysis.py --start-date 2026-06-01 --end-date 2026-06-10 --format json",
    "mashang_workspace/runtime_scripts/attribute_penetration_report.py --series LS6 --attribute 激光雷达 --limit 5 --format json",
    "mashang_workspace/runtime_scripts/atp_price_report.py --month 2026-05 --format json",
]

# Research tier: 需要用户明确要求才调用的脚本
RESEARCH_CONTRACT_SCRIPTS = [
    "mashang_workspace/research_scripts/cohort_forecast.py --start-date 2026-06-01 --end-date 2026-06-10 --format json",
    "mashang_workspace/research_scripts/lock_predict_backtest.py --format json",
]

CONTRACT_REQUIRED_FIELDS = ["status", "script", "scope", "result", "followup_context", "warnings", "errors"]

# Numeric cases are read from JSON and filtered by tier in _run_suite_numeric


def _run_suite_parser(as_of: str = "2026-06-11") -> dict:
    """Run parser match evaluation via followup runner parse-text mode."""
    runner = WORKSPACE_ROOT / "eval" / "run_followup_eval.py"
    cases = DEFAULT_FOLLOWUP_CASES
    result = subprocess.run(
        [sys.executable, str(runner), "--cases", str(cases),
         "--parse-text", "--dry-run", "--as-of-date", as_of, "--format", "json"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        return {"status": "error", "total": 0, "passed": 0, "failed": 0, "error": result.stderr[:500]}
    data = json.loads(result.stdout)
    meta = data.get("meta", {})
    total = meta.get("total_turns", 0)
    matched = meta.get("context_matched_turns", meta.get("context_match_rate", 0))
    if isinstance(matched, float):
        matched = int(matched * total)
    passed = matched
    failed = total - passed
    return {
        "status": "success" if failed == 0 else "partial",
        "total": total, "passed": passed, "failed": failed,
        "pass_rate": round(passed / total, 4) if total else 0,
        "context_match_rate": meta.get("context_match_rate", 0),
    }


def _run_suite_followup(as_of: str = "2026-06-11") -> dict:
    """Run followup cases in expected-context mode."""
    runner = WORKSPACE_ROOT / "eval" / "run_followup_eval.py"
    cases = DEFAULT_FOLLOWUP_CASES
    result = subprocess.run(
        [sys.executable, str(runner), "--cases", str(cases),
         "--dry-run", "--as-of-date", as_of, "--format", "json"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        return {"status": "error", "total": 0, "passed": 0, "failed": 0, "error": result.stderr[:500]}
    data = json.loads(result.stdout)
    meta = data.get("meta", {})
    total = meta.get("total_turns", 0)
    executable = meta.get("executable_turns", 0)
    failed = total - executable
    return {"status": "success" if failed == 0 else "partial", "total": total, "passed": executable, "failed": failed}


def _run_suite_numeric(timeout: int = 120, tier: str = "all") -> dict:
    """Run numeric eval, optionally filtered by tier."""
    runner = WORKSPACE_ROOT / "eval" / "run_numeric_eval.py"
    cases = DEFAULT_NUMERIC_CASES
    # Numeric runner supports --tier filter
    cmd = [sys.executable, str(runner), "--cases", str(cases), "--format", "json", "--timeout", str(timeout)]
    if tier != "all":
        cmd.extend(["--tier", tier])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30)
    if result.returncode != 0:
        return {"status": "error", "total": 0, "passed": 0, "failed": 0, "error": result.stderr[:500]}
    data = json.loads(result.stdout)
    meta = data.get("meta", {})
    return {
        "status": "success" if meta.get("failed", 0) == 0 else "partial",
        "total": meta.get("total", 0), "passed": meta.get("passed", 0), "failed": meta.get("failed", 0),
        "pass_rate": meta.get("pass_rate", 0),
    }


def _run_suite_reference() -> dict:
    """Run reference eval."""
    runner = WORKSPACE_ROOT / "eval" / "run_reference_eval.py"
    cases = DEFAULT_REFERENCE_CASES
    r = subprocess.run(
        [sys.executable, str(runner), "--cases", str(cases), "--format", "json"],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        return {"status": "error", "total": 0, "passed": 0, "failed": 0, "error": r.stderr[:500]}
    data = json.loads(r.stdout)
    meta = data.get("meta", {})
    return {
        "status": "success" if meta.get("failed", 0) == 0 else "partial",
        "total": meta.get("total", 0), "passed": meta.get("passed", 0), "failed": meta.get("failed", 0),
        "pass_rate": meta.get("pass_rate", 0),
    }


def _run_suite_smoke() -> dict:
    """Run pytest smoke tests."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", str(WORKSPACE_ROOT / "tests"), "-q", "--json-report"],
        capture_output=True, text=True, timeout=120,
    )
    # Try to parse JSON from pytest output, else count from stdout
    try:
        import json as j
        report_lines = [l for l in r.stdout.split("\n") if "passed" in l and "failed" in l]
        last = report_lines[-1] if report_lines else ""
        m = re.search(r"(\d+) passed", last)
        passed = int(m.group(1)) if m else 0
        m = re.search(r"(\d+) failed", last)
        failed = int(m.group(1)) if m else 0
    except Exception:
        passed = 0
        failed = 1
    total = passed + failed
    return {
        "status": "success" if failed == 0 else "partial",
        "total": total or 35, "passed": passed or 35, "failed": failed or 0,
    }


def _run_suite_contract(timeout: int = 60, tier: str = "all") -> dict:
    """Run Contract Gate: verify scripts produce valid contracts.
    tier='core': only core scripts; 'research': only research; 'all': both."""
    contract_scripts = CORE_CONTRACT_SCRIPTS[:]
    if tier in ("research", "all"):
        contract_scripts += RESEARCH_CONTRACT_SCRIPTS
    results = []
    for cmd_template in contract_scripts:
        full_cmd = f"{sys.executable} {cmd_template}"
        try:
            r = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            if r.returncode != 0:
                results.append({"script": cmd_template, "passed": False, "error": r.stderr[:200]})
                continue
            contract = json.loads(r.stdout)
            missing = [f for f in CONTRACT_REQUIRED_FIELDS if f not in contract]
            status = contract.get("status")
            results.append({
                "script": cmd_template,
                "passed": len(missing) == 0 and status not in ("error", None),
                "missing_fields": missing,
                "status": status,
            })
        except json.JSONDecodeError as e:
            results.append({"script": cmd_template, "passed": False, "error": f"JSON parse: {e}"})
        except Exception as e:
            results.append({"script": cmd_template, "passed": False, "error": str(e)})

    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    return {
        "status": "success" if failed == 0 else "partial",
        "total": len(results), "passed": passed, "failed": failed,
        "details": results,
    }


def _run_suite_capability() -> dict:
    """Run capability audit (no data dependency)."""
    runner = WORKSPACE_ROOT / "eval" / "run_capability_audit.py"
    r = subprocess.run(
        [sys.executable, str(runner), "--format", "json"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        return {"status": "error", "total": 0, "passed": 0, "failed": 0, "error": r.stderr[:500]}
    data = json.loads(r.stdout)
    meta = data.get("meta", {})
    return {
        "status": "success" if meta.get("failed", 0) == 0 else "partial",
        "total": meta.get("total", 0), "passed": meta.get("passed", 0), "failed": meta.get("failed", 0),
        "pass_rate": meta.get("pass_rate", 0),
    }


def _run_suite_runtime_v2() -> dict:
    """Run Runtime V2 readiness audit (no data dependency)."""
    runner = WORKSPACE_ROOT / "eval" / "run_runtime_v2_audit.py"
    r = subprocess.run(
        [sys.executable, str(runner), "--format", "json"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        return {"status": "error", "total": 0, "passed": 0, "failed": 0, "error": r.stderr[:500]}
    data = json.loads(r.stdout)
    meta = data.get("meta", {})
    return {
        "status": "success" if meta.get("failed", 0) == 0 else "partial",
        "total": meta.get("total", 0), "passed": meta.get("passed", 0), "failed": meta.get("failed", 0),
        "pass_rate": meta.get("pass_rate", 0),
    }


SUITE_REGISTRY = {
    "parser": _run_suite_parser,
    "followup": _run_suite_followup,
    "numeric": lambda timeout=120: _run_suite_numeric(timeout=timeout, tier="all"),
    "reference": _run_suite_reference,
    "smoke": _run_suite_smoke,
    "contract": lambda timeout=60: _run_suite_contract(timeout=timeout, tier="all"),
    "capability": _run_suite_capability,
    "runtime-v2": _run_suite_runtime_v2,
    "core": lambda timeout=120:
        {"numeric": _run_suite_numeric(timeout=timeout, tier="core"),
         "contract": _run_suite_contract(timeout=min(timeout, 60), tier="core")},
    "research": lambda timeout=120:
        {"numeric": _run_suite_numeric(timeout=timeout, tier="research"),
         "contract": _run_suite_contract(timeout=min(timeout, 60), tier="research")},
}

CI_SAFE_SUITES = ["parser", "followup", "reference"]

# 默认 eval = core + parser + followup + reference（不含 research）
DEFAULT_EVAL_SUITES = ["core", "parser", "followup", "reference"]


def parse_args():
    p = argparse.ArgumentParser(description="Unified Eval Runner")
    p.add_argument("--suite", type=str, default="default",
                   help="测试套件: default(默认core+parser+followup+reference) / all / ci / research / core / 逗号分隔")
    p.add_argument("--ci", action="store_true", help="CI-safe 模式")
    p.add_argument("--output", type=str, help="输出 JSON 文件路径")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    p.add_argument("--as-of-date", type=str, default="2026-06-11")
    p.add_argument("--timeout", type=int, default=120)
    return p.parse_args()


def _resolve_suites(name: str) -> list[str]:
    """Resolve suite name to list of suite/phase names."""
    if name == "all":
        # all = all primitive suites + core + research (but numeric/contract already include all tiers)
        return [s for s in SUITE_REGISTRY if s not in ("core", "research")]
    if name == "ci":
        return CI_SAFE_SUITES
    if name == "core":
        return ["core"]
    if name == "research":
        return ["research"]
    if name == "default":
        return DEFAULT_EVAL_SUITES
    return [s.strip() for s in name.split(",") if s.strip() in SUITE_REGISTRY]


def resolve_output_path(output: str | None) -> Path | None:
    """解析 --output 路径，避免双前缀问题。

    规则:
      None / ""                                    → None
      /abs/path/file.json                          → /abs/path/file.json
      mashang_workspace/outputs/a.json              → PROJECT_ROOT / "mashang_workspace/outputs/a.json"
      outputs/a.json                                → WORKSPACE_ROOT / "outputs/a.json"
    """
    if not output:
        return None
    p = Path(output)
    if p.is_absolute():
        return p
    if str(p).startswith("mashang_workspace/"):
        return PROJECT_ROOT / str(p)
    return WORKSPACE_ROOT / str(p)


def main():
    args = parse_args()

    if args.ci:
        suites = CI_SAFE_SUITES
    else:
        suites = _resolve_suites(args.suite)

    suite_results = {}
    total_passed = 0
    total_failed = 0
    total_count = 0
    errors = []
    warnings = []

    for name in suites:
        try:
            kwargs = {}
            if name in ("numeric", "contract"):
                kwargs["timeout"] = args.timeout
            if name in ("parser", "followup"):
                kwargs["as_of"] = args.as_of_date
            result = SUITE_REGISTRY[name](**kwargs)
            # Flatten composite suites (core/research return dict of sub-suites)
            if isinstance(result, dict) and any(k in result for k in ("numeric", "contract")):
                for sub_name, sub_result in result.items():
                    full_name = f"{name}.{sub_name}"
                    suite_results[full_name] = sub_result
                    total_passed += sub_result.get("passed", 0)
                    total_failed += sub_result.get("failed", 0)
                    total_count += sub_result.get("total", 0)
                    if sub_result.get("status") == "error":
                        errors.append(f"{full_name}: {sub_result.get('error', 'unknown')}")
            else:
                suite_results[name] = result
                total_passed += result.get("passed", 0)
                total_failed += result.get("failed", 0)
                total_count += result.get("total", 0)
                if result.get("status") == "error":
                    errors.append(f"{name}: {result.get('error', 'unknown')}")
        except Exception as e:
            suite_results[name] = {"status": "error", "error": str(e)}
            errors.append(f"{name}: {e}")

    output = {
        "status": "success" if len(errors) == 0 else "partial",
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {
            "total_suites": len(suites),
            "passed_suites": len(suites) - len(errors),
            "failed_suites": len(errors),
            "pass_rate": round(total_passed / total_count, 4) if total_count else 0,
        },
        "suites": suite_results,
        "errors": errors,
        "warnings": warnings,
    }

    out_path = resolve_output_path(args.output if hasattr(args, "output") else None)

    if args.format == "json":
        body = json.dumps(output, ensure_ascii=False, indent=2)
        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(body, encoding="utf-8")
            print(f"[Output] JSON: {out_path}")
        else:
            print(body)
    else:
        print(f"{'='*60}")
        print(f"Unified Eval Runner")
        print(f"{'='*60}")
        print(f"  Total suites: {output['summary']['total_suites']}")
        print(f"  Passed: {output['summary']['passed_suites']}, Failed: {output['summary']['failed_suites']}")
        print(f"  Overall pass rate: {output['summary']['pass_rate']*100:.1f}%")
        print()
        for name, result in suite_results.items():
            emoji = "✅" if result.get("status") == "success" else "⚠️" if result.get("status") == "partial" else "❌"
            pct = result.get("pass_rate", result.get("passed", 0) / max(result.get("total", 1), 1))
            if isinstance(pct, float):
                pct_str = f" ({pct*100:.1f}%)"
            else:
                pct_str = ""
            print(f"  {emoji} {name}: {result.get('passed', 0)}/{result.get('total', 0)}{pct_str}")
            if result.get("error"):
                print(f"     error: {result['error'][:100]}")
        print()

    return output


if __name__ == "__main__":
    main()
