#!/usr/bin/env python3
"""
分析 eval/eval_report.json 中的失败分布。

用法:
    python eval/analyze_eval_report.py
    python eval/analyze_eval_report.py --report eval/eval_report.json
"""

import argparse
import json
import os
import sys


def _load_report(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _cluster_failed(results: list[dict]) -> dict[str, list[dict]]:
    check_keys = [
        "no_forbidden_exit_reason",
        "intent_match",
        "contract_match",
        "min_structured_blocks",
        "fact_types_any",
    ]
    clusters: dict[str, list[dict]] = {}
    for r in results:
        if r.get("status") != "failed":
            continue
        checks = r.get("checks") or {}
        failed = sorted(k for k in check_keys if not checks.get(k, True))
        label = ", ".join(failed) if failed else "(none)"
        clusters.setdefault(label, []).append(r)
    return clusters


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Eval Report")
    parser.add_argument(
        "--report",
        default="eval/eval_report.json",
        help="report 文件路径 (默认 eval/eval_report.json)",
    )
    args = parser.parse_args()

    report_path = os.path.abspath(args.report)
    if not os.path.isfile(report_path):
        print(f"[Error] report 文件不存在: {report_path}")
        sys.exit(1)

    report = _load_report(report_path)
    total = report.get("total", 0)
    hard_pass = report.get("hard_pass", 0)
    soft_pass = report.get("soft_pass", 0)
    soft_fail = report.get("soft_fail", 0)
    hard_failed = report.get("hard_failed", 0)
    timeout_count = report.get("timeout_count", 0)
    results = report.get("results", [])

    print("=" * 60)
    print("  Eval Report Analysis")
    print("=" * 60)
    print(f"  total        : {total}")
    print(f"  hard_pass    : {hard_pass}")
    print(f"  soft_pass    : {soft_pass}")
    print(f"  soft_fail    : {soft_fail}")
    print(f"  failed       : {hard_failed}")
    print(f"  timeout_count: {timeout_count}")
    print(f"  pass_rate    : {report.get('pass_rate', 'N/A')}")

    failed_results = [r for r in results if r.get("status") == "failed"]
    soft_pass_results = [r for r in results if r.get("status") == "soft_pass"]
    soft_fail_results = [r for r in results if r.get("status") == "soft_fail"]

    print()
    if failed_results:
        print("-" * 60)
        print(f"  Failed cases ({len(failed_results)}):")
        print("-" * 60)
        clusters = _cluster_failed(results)
        for label, cases in sorted(clusters.items()):
            print(f"\n  failed checks: [{label}]")
            for r in cases:
                actual = r.get("actual") or {}
                err = r.get("error") or "-"
                checks = r.get("checks") or {}
                failed_checks = sorted(
                    k for k in checks if not checks[k]
                )
                print(f"    case_id              : {r.get('case_id', '?')}")
                print(f"    question             : {r.get('question', '')[:80]}")
                print(f"    failed_checks        : {failed_checks}")
                print(f"    exit_reason          : {actual.get('exit_reason', '')}")
                print(f"    eval_intent          : {actual.get('eval_intent', '')}")
                print(f"    contract_matched     : {actual.get('contract_matched', 'N/A')}")
                print(f"    fact_types           : {actual.get('fact_types', [])}")
                print(f"    structured_block_cnt : {actual.get('structured_block_count', 'N/A')}")
                print(f"    error                : {err}")
                print()
    else:
        print("  No failed cases.")

    if soft_fail_results:
        print("-" * 60)
        print(f"  Soft-fail cases ({len(soft_fail_results)}):")
        print("-" * 60)
        for r in soft_fail_results:
            actual = r.get("actual") or {}
            print(f"    case_id         : {r.get('case_id', '?')}")
            print(f"    question        : {r.get('question', '')[:80]}")
            print(f"    warning         : {r.get('warning', '')}")
            print(f"    exit_reason     : {actual.get('exit_reason', '')}")
            print(f"    contract_matched: {actual.get('contract_matched', 'N/A')}")
            print()

    print("-" * 60)
    print("  Soft-pass warning distribution:")
    print("-" * 60)
    if soft_pass_results:
        warning_counts: dict[str, int] = {}
        for r in soft_pass_results:
            w = r.get("warning", "(no warning)")
            warning_counts[w] = warning_counts.get(w, 0) + 1
        for w, cnt in sorted(warning_counts.items(), key=lambda x: -x[1]):
            print(f"    {cnt:3d}  {w}")
    else:
        print("    (none)")
    print()

    print("=" * 60)


if __name__ == "__main__":
    main()
