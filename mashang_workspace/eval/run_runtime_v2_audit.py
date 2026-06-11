#!/usr/bin/env python
"""
Runtime V2 Readiness Audit — 检查能力是否满足 Runtime V2 候选条件

要求:
  - tier == runtime
  - auto_schedulable == true
  - result_contract == true
  - numeric_eval_case != null
  - contract_gate == true
  - promotion.eligible_for_runtime_v2 == true
  - promotion.runtime_v2_candidate == true
  - script exists
  - docs exist

用法:
    python mashang_workspace/eval/run_runtime_v2_audit.py --help
    python mashang_workspace/eval/run_runtime_v2_audit.py
    python mashang_workspace/eval/run_runtime_v2_audit.py --format json
"""

import sys, argparse, json
from pathlib import Path

_WS_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_FILE = _WS_ROOT / "registry" / "capability_registry.json"


def audit_capability(cap: dict, ws_root: Path) -> dict:
    cap_id = cap.get("capability_id", "unknown")
    tier = cap.get("tier", "")
    promo = cap.get("promotion", {})
    is_candidate = promo.get("runtime_v2_candidate", False)
    checks = {}

    if is_candidate:
        # Candidates must satisfy all conditions
        checks["tier_runtime"] = tier == "runtime"
        checks["auto_schedulable"] = cap.get("auto_schedulable") is True
        checks["result_contract"] = cap.get("result_contract") is True
        checks["numeric_eval"] = bool(cap.get("numeric_eval_case"))
        checks["contract_gate"] = cap.get("contract_gate") is True
        checks["script_exists"] = bool(cap.get("script")) and (ws_root / cap["script"].replace("mashang_workspace/", "")).exists()
        checks["docs_exist"] = bool(cap.get("docs"))
        checks["eligible_v2"] = promo.get("eligible_for_runtime_v2") is True
        checks["candidate_marked"] = promo.get("runtime_v2_candidate") is True
    else:
        # Non-candidates must not be marked as candidate
        checks["not_marked_candidate"] = not promo.get("runtime_v2_candidate", False)
        # Non-runtime tiers should not be eligible
        if tier in ("research", "utility", "legacy"):
            checks["tier_not_runtime"] = tier != "runtime"
            checks["not_eligible_v2"] = not promo.get("eligible_for_runtime_v2", True)
            checks["not_candidate"] = not promo.get("runtime_v2_candidate", True)

    all_passed = all(checks.values())
    failed_checks = [k for k, v in checks.items() if not v]

    return {
        "capability_id": cap_id,
        "tier": tier,
        "runtime_v2_candidate": is_candidate,
        "status": "passed" if all_passed else "failed",
        "checks": checks,
        "failed_checks": failed_checks,
        "blocked_reasons": promo.get("blocked_reasons", []),
    }


def main():
    parser = argparse.ArgumentParser(description="Runtime V2 Readiness Audit")
    parser.add_argument("--registry", type=str, default=str(REGISTRY_FILE))
    parser.add_argument("--output", type=str, help="输出 JSON 文件路径")
    parser.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    args = parser.parse_args()

    reg_path = Path(args.registry)
    if not reg_path.exists():
        print(f"[Error] 注册表不存在: {reg_path}", file=sys.stderr)
        sys.exit(1)

    with open(reg_path, encoding="utf-8") as f:
        registry = json.load(f)

    results = [audit_capability(c, _WS_ROOT) for c in registry]
    total = len(results)
    candidates = sum(1 for r in results if r["runtime_v2_candidate"])
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = total - passed

    output = {
        "meta": {"total": total, "candidates": candidates, "passed": passed, "failed": failed,
                 "pass_rate": round(passed / total, 4) if total else 0},
        "results": results,
    }

    if args.format == "json":
        body = json.dumps(output, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(body, encoding="utf-8")
            print(f"[Output] JSON: {args.output}")
        else:
            print(body)
    else:
        print(f"{'='*60}")
        print(f"Runtime V2 Readiness Audit")
        print(f"{'='*60}")
        print(f"  Total: {total}, Candidates: {candidates}, Passed: {passed}, Failed: {failed}")
        print()
        for r in results:
            emoji = "✅" if r["status"] == "passed" else "❌"
            tag = " [CANDIDATE]" if r["runtime_v2_candidate"] else " [non-candidate]"
            fc = r.get("failed_checks", [])
            fc_str = f" [{','.join(fc)}]" if fc else ""
            print(f"  {emoji} {r['capability_id']} ({r['tier']}){tag}{fc_str}")
        print()

    return output


if __name__ == "__main__":
    main()
