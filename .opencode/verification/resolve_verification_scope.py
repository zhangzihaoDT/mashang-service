#!/usr/bin/env python
"""
Verification Scope Resolver — 按改动范围解析最小验证范围。

契约: .opencode/verification/scope_contract.json

把「充分验证」定义为「命中改动范围的验证」，而不是「扩大 pytest scope」：
  - 只运行 matched_rules 解析出的 required_targets
  - scope 外的失败不算本次回归
  - baseline_failures（已知历史失败）不算回归
  - 扩大范围必须显式 --all / --include

用法:
    python .opencode/verification/resolve_verification_scope.py --worktree
    python .opencode/verification/resolve_verification_scope.py --changed a.py b.md --format json
    python .opencode/verification/resolve_verification_scope.py --worktree --run
    python .opencode/verification/resolve_verification_scope.py --range HEAD~1..HEAD --run
    python .opencode/verification/resolve_verification_scope.py --all --format json
"""

import re
import sys
import json
import fnmatch
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
CONTRACT_PATH = HERE / "scope_contract.json"
SCRIPT_REL = ".opencode/verification/resolve_verification_scope.py"


# ── glob matching (supports **/) ──
def _glob_to_regex(pattern: str) -> str:
    out = []
    i = 0
    n = len(pattern)
    while i < n:
        if pattern[i:i + 3] == "**/":
            out.append("(?:.*/)?")
            i += 3
        elif pattern[i:i + 2] == "**":
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return "^" + "".join(out) + "$"


def match_path(path: str, pattern: str) -> bool:
    return re.match(_glob_to_regex(pattern), path) is not None


def load_contract(path: Path = CONTRACT_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ── changed-file discovery ──
def git_changed_files(mode: str, ref_range: str | None) -> list:
    root = str(PROJECT_ROOT)
    if mode == "staged":
        args = ["git", "diff", "--name-only", "--cached"]
    elif mode == "range":
        args = ["git", "diff", "--name-only", ref_range]
    else:
        args = ["git", "status", "--porcelain"]
    r = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise SystemExit(f"git 失败: {r.stderr.strip()}")
    files = []
    if mode == "worktree":
        for line in r.stdout.splitlines():
            if not line.strip():
                continue
            payload = line[3:].strip()
            if " -> " in payload:
                payload = payload.split(" -> ", 1)[1]
            files.append(payload.strip('"'))
    else:
        files = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    return sorted(set(files))


# ── target + dynamic resolution ──
def _static_target(contract: dict, tid: str) -> dict:
    t = contract["targets"][tid]
    return {
        "id": tid,
        "command": t["command"],
        "data_dependency": t.get("data_dependency", False),
        "description": t.get("description", ""),
        "source": "rule",
    }


def _nearest_tests(rel_path: str) -> str | None:
    """向上寻找改动文件所属模块的 tests/，不越界到仓库根 tests/。"""
    for parent in Path(rel_path).parents:
        if parent == Path("."):
            break
        if parent.name == "tests" and len(parent.parts) >= 2:
            return str(parent)
        cand = parent / "tests"
        if len(cand.parts) >= 2 and (PROJECT_ROOT / cand).is_dir():
            return str(cand)
    return None


def resolve_scope(contract: dict, changed: list, include: list | None = None,
                  run_all: bool = False) -> dict:
    targets: dict[str, dict] = {}
    matched_rules: list[str] = []
    unclassified: list[str] = []
    code_files: list[str] = []

    if run_all:
        matched_rules = ["ALL(expanded)"]
        for tid in contract["targets"]:
            targets[tid] = _static_target(contract, tid)

    for path in changed:
        file_rules = [r for r in contract["rules"] if any(match_path(path, p) for p in r["match"])]
        if not file_rules:
            unclassified.append(path)
            continue
        for rule in file_rules:
            if rule["id"] not in matched_rules:
                matched_rules.append(rule["id"])
            if rule.get("code", True):
                code_files.append(path)
            for tid in rule.get("targets", []):
                targets[tid] = _static_target(contract, tid)

            dyn = rule.get("dynamic")
            if dyn == "script_help" and path.endswith(".py"):
                tid = f"smoke:{path}"
                targets[tid] = {
                    "id": tid, "command": ["{python}", path, "--help"],
                    "data_dependency": False,
                    "description": f"{path} --help 冒烟", "source": "dynamic",
                }
            elif dyn == "pytest_file" and path.endswith(".py"):
                base = path.rsplit("/", 1)[-1]
                if base.startswith("test_") or base.endswith("_test.py"):
                    tid = f"pytest:{path}"
                    targets[tid] = {
                        "id": tid, "command": ["{python}", "-m", "pytest", path, "-q"],
                        "data_dependency": False,
                        "description": f"改动测试文件 {path}", "source": "dynamic",
                    }
                else:
                    tid = f"smoke:{path}"
                    targets[tid] = {
                        "id": tid, "command": ["{python}", path, "--help"],
                        "data_dependency": False,
                        "description": f"{path} --help 冒烟（非测试文件）", "source": "dynamic",
                    }
            elif dyn == "nearest_tests":
                tests_dir = _nearest_tests(path)
                if tests_dir:
                    tid = f"pytest:{tests_dir}"
                    targets[tid] = {
                        "id": tid, "command": ["{python}", "-m", "pytest", tests_dir, "-q"],
                        "data_dependency": False,
                        "description": f"{tests_dir}（{path} 所属模块 tests）", "source": "dynamic",
                    }
                elif path.endswith(".py"):
                    tid = f"smoke:{path}"
                    targets[tid] = {
                        "id": tid, "command": ["{python}", path, "--help"],
                        "data_dependency": True,
                        "description": f"{path} --help 冒烟（无 tests/，仅冒烟）", "source": "dynamic",
                    }

    for tid in (include or []):
        if tid in contract["targets"]:
            targets[tid] = _static_target(contract, tid)
        else:
            targets[tid] = {
                "id": tid, "command": ["{python}", tid], "data_dependency": False,
                "description": "显式 --include", "source": "explicit",
            }

    if not run_all:
        if not code_files and changed and not unclassified:
            decision = "no-op"
        elif not targets and (unclassified or not changed):
            decision = "no-op" if not changed else "review"
        else:
            decision = "run"
        if include and targets:
            decision = "run"
    else:
        decision = "run"

    required = [targets[k] for k in sorted(targets)]
    out_of_scope = sorted(set(contract["targets"]) - set(targets))
    return {
        "changed_files": changed,
        "matched_rules": matched_rules,
        "required_targets": required,
        "out_of_scope_targets": out_of_scope,
        "excluded_baseline_failures": contract.get("baseline_failures", []),
        "unclassified_files": unclassified,
        "decision": decision,
    }


# ── execution + baseline-aware verdict ──
def _baseline_set(contract: dict) -> set:
    return {b["test"] for b in contract.get("baseline_failures", [])}


def _is_baseline(node: str, baseline: set) -> bool:
    node = node.lstrip("./")
    for b in baseline:
        b = b.lstrip("./")
        if node == b or node.endswith(b) or b.endswith(node):
            return True
    return False


def _parse_failed_nodes(output: str) -> list:
    nodes = set()
    for m in re.finditer(r"^(?:FAILED|ERROR)\s+(\S+)", output, re.MULTILINE):
        nodes.add(m.group(1).rstrip(":"))
    return sorted(nodes)


def run_targets(contract: dict, required: list, timeout: int = 600) -> dict:
    baseline = _baseline_set(contract)
    executions = []
    regressions = []
    for t in required:
        argv = [sys.executable if tok == "{python}" else tok for tok in t["command"]]
        try:
            r = subprocess.run(argv, cwd=str(PROJECT_ROOT), capture_output=True,
                               text=True, timeout=timeout)
            out = (r.stdout or "") + "\n" + (r.stderr or "")
            failed = _parse_failed_nodes(out)
            if r.returncode == 0:
                status = "passed"
            else:
                in_baseline = [n for n in failed if _is_baseline(n, baseline)]
                outside = [n for n in failed if n not in in_baseline]
                if failed and not outside:
                    status = "passed_with_baseline"
                else:
                    status = "failed"
                fallback = [f"{t['id']}: exit {r.returncode}"] if not failed else []
                regressions.extend(outside or fallback)
            executions.append({
                "target": t["id"], "command": " ".join(argv),
                "returncode": r.returncode, "status": status,
                "failed_nodes": failed,
                "failures_in_baseline": [n for n in failed if _is_baseline(n, baseline)],
            })
        except subprocess.TimeoutExpired:
            executions.append({"target": t["id"], "command": " ".join(argv),
                               "returncode": None, "status": "failed",
                               "failed_nodes": [], "error": f"timeout {timeout}s"})
            regressions.append(f"{t['id']}: timeout")
    return {"executions": executions, "regressions": sorted(set(regressions))}


# ── output ──
def build_report(contract: dict, scope: dict, run_result: dict | None) -> dict:
    decision = scope["decision"]
    if decision == "no-op":
        summary = "改动为纯文档 / 无需测试，decision=no-op。"
    else:
        ids = ", ".join(t["id"] for t in scope["required_targets"]) or "(无)"
        summary = f"命中 {len(scope['matched_rules'])} 条规则，最小验证范围: {ids}。"

    result = {"summary": summary}
    errors = []
    status = "success"
    if run_result:
        result["executions"] = run_result["executions"]
        result["regressions"] = run_result["regressions"]
        failed = [e for e in run_result["executions"] if e["status"] == "failed"]
        if failed:
            status = "error"
            errors = [f"scope 内失败: {e['target']}" for e in failed]
        elif run_result["regressions"]:
            status = "error"
            errors = run_result["regressions"]
        elif any(e["status"] == "passed_with_baseline" for e in run_result["executions"]):
            result["summary"] += " 仅命中 baseline 历史失败，视为通过。"
    if scope["unclassified_files"]:
        result["summary"] += f" 注意: {len(scope['unclassified_files'])} 个文件未分类。"

    return {
        "status": status,
        "script": SCRIPT_REL,
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "scope": {
            "changed_files": scope["changed_files"],
            "matched_rules": scope["matched_rules"],
            "required_targets": scope["required_targets"],
            "out_of_scope_targets": scope["out_of_scope_targets"],
            "excluded_baseline_failures": scope["excluded_baseline_failures"],
            "unclassified_files": scope["unclassified_files"],
            "decision": scope["decision"],
        },
        "result": result,
        "warnings": [] if not scope["out_of_scope_targets"] else [
            "以下 target 未纳入本次验证范围（scope 内失败才算回归）: "
            + ", ".join(scope["out_of_scope_targets"])
        ],
        "errors": errors,
    }


def format_terminal(contract: dict) -> str:
    s = contract["scope"]
    lines = ["[Summary]", "  " + contract["result"]["summary"], "", "[Scope]"]
    lines.append(f"  decision: {s['decision']}")
    lines.append(f"  changed: {len(s['changed_files'])} 个文件")
    for f in s["changed_files"][:20]:
        lines.append(f"    - {f}")
    lines.append(f"  matched_rules: {', '.join(s['matched_rules']) or '(无)'}")
    lines.append("  最小验证范围:")
    for t in s["required_targets"]:
        dep = " [依赖 dataset]" if t["data_dependency"] else ""
        lines.append(f"    • {t['id']}{dep}")
        lines.append("      $ " + " ".join(t["command"]).replace("{python}", "python"))
    if s["unclassified_files"]:
        lines.append("  ⚠ 未分类文件: " + ", ".join(s["unclassified_files"]))
    lines.append("")
    lines.append("[Out of Scope — 未纳入，失败不算本次回归]")
    lines.append("  " + (", ".join(s["out_of_scope_targets"]) or "(无)"))
    if s["excluded_baseline_failures"]:
        lines.append("")
        lines.append("[Baseline — 已知历史失败，不算回归]")
        for b in s["excluded_baseline_failures"]:
            lines.append(f"  - {b['test']}")
    if "executions" in contract["result"]:
        lines.append("")
        lines.append("[Result]")
        for e in contract["result"]["executions"]:
            lines.append(f"  {e['status']:<22} {e['target']} (rc={e['returncode']})")
        if contract["result"].get("regressions"):
            lines.append("  regressions:")
            for r in contract["result"]["regressions"]:
                lines.append(f"    ❌ {r}")
    if contract["errors"]:
        lines.append("")
        lines.append("[Errors]")
        for e in contract["errors"]:
            lines.append(f"  ❌ {e}")
    return "\n".join(lines)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Verification Scope Resolver")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--worktree", action="store_true", help="git 工作区改动（默认）")
    src.add_argument("--staged", action="store_true", help="暂存区改动")
    src.add_argument("--range", type=str, help="git 范围，如 HEAD~1..HEAD")
    p.add_argument("--changed", nargs="*", default=None, help="显式指定改动文件")
    p.add_argument("--include", nargs="*", default=None, help="显式追加 target")
    p.add_argument("--all", action="store_true", dest="run_all", help="显式扩大范围（全部 target）")
    p.add_argument("--run", action="store_true", help="执行 scope 内 target")
    p.add_argument("--timeout", type=int, default=600, help="单个 target 超时秒数")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    p.add_argument("--output", type=str, default=None, help="输出 JSON 文件")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    contract = load_contract()

    if args.changed is not None:
        changed = sorted(set(args.changed))
    elif args.staged:
        changed = git_changed_files("staged", None)
    elif args.range:
        changed = git_changed_files("range", args.range)
    else:
        changed = git_changed_files("worktree", None)

    include = list(args.include or [])

    scope = resolve_scope(contract, changed, include=include, run_all=args.run_all)
    run_result = None
    if args.run and scope["decision"] == "run" and scope["required_targets"]:
        run_result = run_targets(contract, scope["required_targets"], timeout=args.timeout)

    report = build_report(contract, scope, run_result)

    if args.output:
        outp = Path(args.output)
        if not outp.is_absolute():
            outp = PROJECT_ROOT / outp
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_terminal(report))
        if args.output:
            print(f"\n[Output] JSON: {Path(args.output)}")

    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
