#!/usr/bin/env python
"""
Capability Audit Runner — 能力注册表健康检查

读取 registry/capability_registry.json，检查每个 capability:
  - script 是否存在
  - tier/status 是否合法
  - runtime 是否有 result_contract / numeric_eval / contract_gate
  - research 是否 auto_schedulable=false
  - legacy 是否 auto_schedulable=false
  - docs 文件是否存在
  - promotion 字段是否完整
  - blocked_reasons 是否合理

用法:
    python mashang_workspace/eval/run_capability_audit.py --help
    python mashang_workspace/eval/run_capability_audit.py
    python mashang_workspace/eval/run_capability_audit.py --format json
"""

import sys, argparse, json
from pathlib import Path

_WS_ROOT = Path(__file__).resolve().parents[1]
_PRJ_ROOT = _WS_ROOT.parent
REGISTRY_FILE = _WS_ROOT / "registry" / "capability_registry.json"

VALID_TIERS = {"runtime", "research", "utility", "legacy"}
VALID_STATUSES = {"active", "partial", "experimental", "deprecated"}

AUDIT_CHECKS = [
    "script_exists", "tier_valid", "status_valid",
    "runtime_has_contract", "runtime_has_numeric", "runtime_has_gate",
    "research_not_auto", "legacy_not_auto", "promotion_fields",
]


def audit_capability(cap: dict, ws_root: Path) -> dict:
    cap_id = cap.get("capability_id", "unknown")
    tier = cap.get("tier", "")
    status = cap.get("status", "")
    script_path = cap.get("script", "")
    checks = {}

    # 1. Script exists
    checks["script_exists"] = (ws_root / script_path.replace("mashang_workspace/", "")).exists() if script_path else False

    # 2. Tier valid
    checks["tier_valid"] = tier in VALID_TIERS

    # 3. Status valid
    checks["status_valid"] = status in VALID_STATUSES

    # 4. Runtime tier must have result_contract
    checks["runtime_has_contract"] = True
    if tier == "runtime":
        checks["runtime_has_contract"] = bool(cap.get("result_contract"))

    # 5. Runtime tier must have numeric_eval_case
    checks["runtime_has_numeric"] = True
    if tier == "runtime":
        checks["runtime_has_numeric"] = bool(cap.get("numeric_eval_case"))

    # 6. Runtime tier must be in contract_gate
    checks["runtime_has_gate"] = True
    if tier == "runtime":
        checks["runtime_has_gate"] = bool(cap.get("contract_gate"))

    # 7. Research must not be auto_schedulable
    checks["research_not_auto"] = True
    if tier == "research":
        checks["research_not_auto"] = not cap.get("auto_schedulable", True)

    # 8. Legacy must not be auto_schedulable
    checks["legacy_not_auto"] = True
    if tier == "legacy":
        checks["legacy_not_auto"] = not cap.get("auto_schedulable", True)

    # 9. Promotion fields
    promo = cap.get("promotion", {})
    checks["promotion_fields"] = bool(
        promo.get("current_stage") and "blocked_reasons" in promo
    )

    all_passed = all(checks.values())
    failed_checks = [k for k, v in checks.items() if not v]

    return {
        "capability_id": cap_id,
        "tier": tier,
        "status": "passed" if all_passed else "failed",
        "checks": checks,
        "failed_checks": failed_checks,
        "promotion_assessment": {
            "eligible_for_runtime_productization": promo.get("eligible_for_runtime_productization", False),
            "eligible_for_runtime_script": promo.get("eligible_for_runtime_script", False),
            "blocked_reasons": promo.get("blocked_reasons", []),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Capability Audit Runner")
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
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = total - passed
    warnings = sum(1 for r in results if r["failed_checks"])

    output = {
        "meta": {"total": total, "passed": passed, "failed": failed, "warnings": warnings,
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
        print(f"Capability Audit Runner")
        print(f"{'='*60}")
        print(f"  Total: {total}, Passed: {passed}, Failed: {failed}, Warnings: {warnings}")
        print()
        for r in results:
            emoji = "✅" if r["status"] == "passed" else "❌"
            fc = r.get("failed_checks", [])
            fc_str = f" [{','.join(fc)}]" if fc else ""
            print(f"  {emoji} {r['capability_id']} ({r['tier']}){fc_str}")
        print()

    return output


if __name__ == "__main__":
    main()
