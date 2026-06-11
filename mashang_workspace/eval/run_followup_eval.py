#!/usr/bin/env python
"""
Follow-up Eval Runner — 验证多轮追问场景的脚本调度能力

读取 eval/cases/followup_cases.json，对每轮 turns 执行:
  1. 上下文继承解析
  2. expected_context → 推荐脚本 + CLI 参数
  3. 时间窗口 symbolic 解析
  4. dry-run / execute 模式

支持两种模式:
  - expected_context 模式: 从 cases JSON 读取 expected_context (Phase 3)
  - parse_text 模式: 从 user 文本调用 context_parser (Phase 4)

用法:
    python eval/run_followup_eval.py --help
    python eval/run_followup_eval.py                                    # dry-run
    python eval/run_followup_eval.py --execute                          # 真实执行
    python eval/run_followup_eval.py --parse-text                       # 从自然语言解析 context
    python eval/run_followup_eval.py --parse-text --format json --output outputs/tables/parse_result.json
"""

import sys, argparse, json, subprocess, re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any

import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parents[1])); from utils.paths import WORKSPACE_ROOT, PROJECT_ROOT
DEFAULT_CASES = WORKSPACE_ROOT / "eval" / "cases" / "followup_cases.json"
FOLLOWUP_OUTPUT_DIR = WORKSPACE_ROOT / "outputs" / "tables"

CONTEXT_SCRIPT_MAP: list[tuple[list[str], list[str], str]] = [
    (["lock_count"], ["model", "model_or_series", "series", "energy_type"], "scripts/lock_by_model.py"),
    (["lock_count_share", "share"], ["model", "series", "energy_type"], "scripts/lock_by_model.py"),
    (["reev_share_trend", "share_trend"], [], "scripts/lock_by_model.py"),
    (["lock_count"], ["city"], "scripts/lock_city_distribution.py"),
    (["lock_count"], [], "scripts/daily_lock_count.py"),
    (["lock_forecast", "forecast_lock_count", "cohort_forecast"], [], "scripts/cohort_forecast.py"),
    (["release_curve", "lock_release_curve"], [], "scripts/release_curve_analysis.py"),
    (["voc_theme", "jtbd_theme"], [], "scripts/voc_theme_analysis.py"),
]


def _match_script(ctx: dict) -> str:
    metric = (ctx.get("metric") or "").lower()
    group_by = (ctx.get("group_by") or "").lower()

    for metrics, group_bys, script in CONTEXT_SCRIPT_MAP:
        if metric in metrics:
            if not group_bys or group_by in group_bys:
                return script
    for metrics, group_bys, script in CONTEXT_SCRIPT_MAP:
        if group_by in group_bys:
            return script
    return "scripts/daily_lock_count.py"


# ─── 2. Context → CLI Args 生成 ────────────────────────────────────────────

def _resolve_date_range(time_window: str, as_of: date, series: str | None = None) -> tuple[str | None, str | None, str | None]:
    if not time_window:
        return None, None, None

    tw = time_window.lower()

    if tw == "yesterday":
        d = as_of - timedelta(days=1)
        return None, None, d.strftime("%Y-%m-%d")
    if tw == "today":
        return None, None, as_of.strftime("%Y-%m-%d")

    day_map = {
        "last_7_days": 7, "last_15_days": 15, "last_30_days": 30,
    }
    if tw in day_map:
        n = day_map[tw]
        end = as_of
        start = as_of - timedelta(days=n)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), None

    # Handle dynamic last_N_days
    m = __import__("re").match(r"last_(\d+)_days", tw)
    if m:
        n = int(m.group(1))
        end = as_of
        start = as_of - timedelta(days=n)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), None

    if tw == "this_month":
        start = as_of.replace(day=1)
        return start.strftime("%Y-%m-%d"), as_of.strftime("%Y-%m-%d"), None
    if tw == "last_month":
        first_of_this = as_of.replace(day=1)
        end = first_of_this
        start = (first_of_this - timedelta(days=1)).replace(day=1)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), None
    if tw == "since_launch":
        try:
            bdef_path = PROJECT_ROOT / "schema" / "business_definition.json"
            if bdef_path.exists():
                with open(bdef_path) as f:
                    bdef = json.load(f)
                periods = bdef.get("time_periods", {})
                if series and series.upper() in periods:
                    launch = periods[series.upper()].get("end", "")
                    if launch:
                        return launch, as_of.strftime("%Y-%m-%d"), None
        except Exception:
            pass
        launch_map = {
            "LS6": "2025-09-10", "L6": "2025-05-13",
            "LS8": "2026-04-16", "LS9": "2025-11-12",
            "LS7": "2023-01-01", "L7": "2023-01-01",
        }
        s = (series or "").upper()
        start = launch_map.get(s, "2025-01-01")
        return start, as_of.strftime("%Y-%m-%d"), None

    return None, None, None


def _build_args(ctx: dict, as_of: date) -> list[str]:
    args: list[str] = []
    time_window = ctx.get("time_window")
    series = ctx.get("series")
    model = ctx.get("model")
    city = ctx.get("city")
    limit = ctx.get("limit")
    script = _match_script(ctx)

    t_start, t_end, t_date = _resolve_date_range(time_window, as_of, series)
    script_name = Path(script).name

    if script_name == "daily_lock_count.py" and t_date:
        args.extend(["--date", t_date])
    else:
        if t_start:
            args.extend(["--start-date", t_start])
        if t_end:
            args.extend(["--end-date", t_end])
    if series:
        args.extend(["--series", series])
    if model:
        args.extend(["--model", model])
    if city:
        args.extend(["--city", city])
    if limit and script_name != "daily_lock_count.py":
        args.extend(["--limit", str(limit)])
    if "--format" not in args:
        args.extend(["--format", "terminal"])
    return args


# ─── 3. 上下文继承逻辑 (expected_context 模式) ────────────────────────────

_FIELDS_TO_INHERIT = {"metric", "series", "model", "city", "time_window", "group_by", "analysis_type"}
_FIELDS_ADDITIVE = {"filter", "filter_ref", "limit"}


def _resolve_context(turns: list[dict], as_of: date) -> list[dict]:
    results = []
    prev_ctx: dict[str, Any] = {}

    for turn in turns:
        expected = turn.get("expected_context", {})
        resolved = dict(prev_ctx)
        inherited = {}
        overridden = {}

        for key, value in expected.items():
            if value is not None and value != "":
                if key == "filter" or key == "filter_ref":
                    resolved.setdefault("filters", [])
                    if value not in resolved["filters"]:
                        resolved["filters"].append(value)
                    inherited[key] = resolved.get(key, [])
                elif key in _FIELDS_TO_INHERIT:
                    if key in prev_ctx and prev_ctx.get(key) != value:
                        overridden[key] = {"from": prev_ctx.get(key), "to": value}
                    resolved[key] = value
                else:
                    resolved[key] = value
            elif key in _FIELDS_TO_INHERIT and key in prev_ctx:
                inherited[key] = prev_ctx[key]
                resolved[key] = prev_ctx[key]

        missing = {}
        if not resolved.get("metric"):
            missing["metric"] = "not specified and no inheritance"
        if not resolved.get("time_window"):
            missing["time_window"] = "not specified and no inheritance"

        script = _match_script(resolved)
        script_args = _build_args(resolved, as_of)
        cmd = f"python {script} " + " ".join(script_args)

        results.append({
            "turn_index": len(results),
            "user": turn.get("user", ""),
            "expected_context": expected,
            "resolved_context": dict(resolved),
            "inherited_context": inherited,
            "overridden_context": overridden,
            "missing_context": missing,
            "recommended_script": script,
            "recommended_args": script_args,
            "recommended_command": cmd,
            "can_execute": len(missing) == 0 and bool(script),
        })
        prev_ctx = dict(resolved)

    return results


# ─── 3b. 上下文继承逻辑 (parse_text 模式) ─────────────────────────────────

def _resolve_context_from_parse(turns: list[dict], as_of: date, prev_result_ctx: dict | None = None) -> tuple[list[dict], int, int]:
    from context_parser import parse_context  # same directory

    results = []
    prev_ctx: dict[str, Any] = {}
    matched_count = 0
    total_count = 0
    result_ctx = prev_result_ctx or {}

    for turn in turns:
        user_text = turn.get("user", "")
        expected = turn.get("expected_context", {})

        parse_result = parse_context(user_text, previous_context=prev_ctx,
                                     previous_result_context=result_ctx)
        resolved = parse_result["resolved_context"]

        # 比较 resolved_context 与 expected_context
        mismatch_fields = []
        for key in ("metric", "time_window", "series", "group_by", "filter", "analysis_type", "model", "city"):
            ev = expected.get(key)
            rv = resolved.get(key)
            # Normalize: "filters" list vs single "filter"
            if key == "filter":
                resolved_filters = resolved.get("filters", [])
                ev_list = [ev] if isinstance(ev, str) else (ev or [])
                if set(ev_list) != set(resolved_filters):
                    mismatch_fields.append(key)
            elif ev is not None and ev != "":
                if isinstance(ev, str) and ev.lower() != str(rv or "").lower():
                    mismatch_fields.append(key)
                elif not isinstance(ev, str) and ev != rv:
                    mismatch_fields.append(key)

        context_match = len(mismatch_fields) == 0
        if context_match:
            matched_count += 1
        total_count += 1

        script = _match_script(resolved)
        script_args = _build_args(resolved, as_of)
        cmd = f"python {script} " + " ".join(script_args)

        missing = parse_result.get("missing_context", {})

        results.append({
            "turn_index": len(results),
            "user": user_text,
            "expected_context": expected,
            "parsed_context": parse_result["parsed_context"],
            "resolved_context": dict(resolved),
            "inherited_context": parse_result["inherited_context"],
            "overridden_context": parse_result["overridden_context"],
            "missing_context": missing,
            "result_reference": parse_result.get("result_reference"),
            "confidence": parse_result["confidence"],
            "context_match": context_match,
            "mismatch_fields": mismatch_fields,
            "recommended_script": script,
            "recommended_args": script_args,
            "recommended_command": cmd,
            "can_execute": len(missing) == 0 and bool(script),
        })

        prev_ctx = dict(resolved)
        result_ctx = resolved  # pass resolved as result context for next turn

    return results, matched_count, total_count


# ─── 4. 执行器 ──────────────────────────────────────────────────────────────

def _execute_turn(script: str, args: list[str], timeout: int = 60,
                  case_id: str = "", turn_index: int = 0) -> dict:
    script_path = PROJECT_ROOT / script
    if not script_path.exists():
        return {"error": f"script not found: {script_path}", "return_code": -1}

    # 自动注入 --format json 和 --output（如果脚本支持）
    exec_args = list(args)
    if "--format" not in exec_args:
        exec_args.extend(["--format", "json"])
    if "--output" not in exec_args:
        out_dir = FOLLOWUP_OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        exec_args.extend(["--output", str(out_dir)])

    full_cmd = [sys.executable, str(script_path)] + exec_args
    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)

        # 尝试解析合同 JSON（从 stdout 或输出文件）
        contract = _try_parse_contract(result.stdout, exec_args, case_id, turn_index)
        return {
            "return_code": result.returncode,
            "stdout": result.stdout[:3000],
            "stderr": result.stderr[:1000],
            "contract": contract,
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "return_code": -1, "contract": None}
    except Exception as e:
        return {"error": str(e), "return_code": -1, "contract": None}


def _try_parse_contract(stdout: str, args: list[str], case_id: str, turn_index: int) -> dict | None:
    """尝试从 stdout 或输出文件解析 Result Contract JSON。"""
    # 先尝试从 stdout 解析
    if stdout.strip().startswith("{"):
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            pass
    # 尝试从输出文件读取
    out_dir = FOLLOWUP_OUTPUT_DIR / f"followup_{case_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    contract_paths = sorted(out_dir.glob(f"followup_{case_id}_turn_{turn_index}_*.json"))
    for cp in contract_paths:
        try:
            return json.loads(cp.read_text())
        except Exception:
            pass
    return None


# ─── 5. Main ────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Follow-up Eval Runner")
    parser.add_argument("--cases", type=str, default=str(DEFAULT_CASES),
                        help="follow-up cases JSON 文件路径")
    parser.add_argument("--output", type=str,
                        help="输出文件路径 (默认 stdout)")
    parser.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"],
                        help="输出格式 (默认 terminal)")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="仅生成推荐命令，不执行 (默认)")
    parser.add_argument("--execute", action="store_true",
                        help="真实执行推荐命令")
    parser.add_argument("--as-of-date", type=str,
                        help="相对日期基准 (YYYY-MM-DD，默认今天)")
    parser.add_argument("--timeout", type=int, default=60,
                        help="每个脚本执行超时秒数 (默认 60)")
    parser.add_argument("--parse-text", action="store_true",
                        help="使用 context_parser 从自然语言解析 context (而非 expected_context)")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.execute:
        args.dry_run = False

    as_of = datetime.strptime(args.as_of_date, "%Y-%m-%d").date() if args.as_of_date else date.today()

    cases_path = Path(args.cases)
    if not cases_path.exists():
        print(f"[Error] cases 文件不存在: {cases_path}", file=sys.stderr)
        sys.exit(1)

    with open(cases_path, encoding="utf-8") as f:
        cases = json.load(f)

    all_results = []
    total_turns = 0
    executable_count = 0
    executed_count = 0
    success_count = 0
    total_matched = 0
    total_compared = 0

    for case in cases:
        case_id = case.get("case_id", "unknown")
        turns = case.get("turns", [])

        if args.parse_text:
            turn_results, matched, compared = _resolve_context_from_parse(turns, as_of)
            total_matched += matched
            total_compared += compared
        else:
            turn_results = _resolve_context(turns, as_of)

        case_result = {
            "case_id": case_id,
            "description": case.get("description", ""),
            "total_turns": len(turns),
            "turns": turn_results,
        }

        if not args.dry_run:
            for idx, tr in enumerate(turn_results):
                if tr["can_execute"]:
                    exec_result = _execute_turn(
                        tr["recommended_script"], tr["recommended_args"],
                        timeout=args.timeout, case_id=case_id, turn_index=idx,
                    )
                    tr["execution"] = exec_result
                    executed_count += 1
                    if exec_result.get("return_code") == 0:
                        success_count += 1
                    # 从 contract 提取下一轮 followup_context
                    contract = exec_result.get("contract")
                    if contract:
                        fc = contract.get("followup_context", {})
                        if fc:
                            tr["followup_context"] = fc

        all_results.append(case_result)
        total_turns += len(turns)
        executable_count += sum(1 for t in turn_results if t["can_execute"])

    # ── 输出 ──
    match_rate = round(total_matched / total_compared, 4) if total_compared > 0 else 0.0

    output = {
        "meta": {
            "as_of_date": as_of.isoformat(),
            "dry_run": args.dry_run,
            "parse_text": args.parse_text,
            "cases_file": str(cases_path),
            "total_cases": len(cases),
            "total_turns": total_turns,
            "executable_turns": executable_count,
            "executed_turns": executed_count,
            "successful_executions": success_count,
        },
        "cases": all_results,
    }

    if args.parse_text:
        output["meta"]["context_match_rate"] = match_rate
        output["meta"]["context_matched_turns"] = total_matched
        output["meta"]["context_total_compared"] = total_compared

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
        mode_label = "PARSE-TEXT" if args.parse_text else "EXPECTED-CONTEXT"
        print(f"{'='*70}")
        print(f"Follow-up Eval Runner [{mode_label}]")
        print(f"{'='*70}")
        print(f"  Cases: {len(cases)}, Turns: {total_turns}")
        print(f"  Executable: {executable_count}/{total_turns}")
        print(f"  Mode: {'DRY-RUN' if args.dry_run else 'EXECUTE'}")
        print(f"  As-of: {as_of}")
        if args.parse_text and total_compared > 0:
            print(f"  Context Match: {total_matched}/{total_compared} ({match_rate*100:.1f}%)")
        print()

        for case_result in all_results:
            print(f"{'─'*70}")
            print(f"Case: {case_result['case_id']}")
            print(f"  {case_result['description']}")
            for tr in case_result["turns"]:
                idx = tr["turn_index"]
                script = tr["recommended_script"]
                can = "✅" if tr["can_execute"] else "❌"

                if args.parse_text:
                    cm = tr.get("context_match", True)
                    mm = tr.get("mismatch_fields", [])
                    cm_str = f" ctx={'✅' if cm else '❌'}({','.join(mm)})" if mm else " ctx=✅"
                    conf = f" conf={tr.get('confidence', 0):.2f}"
                else:
                    cm_str = ""
                    conf = ""

                missing_keys = list(tr["missing_context"].keys())
                missing_str = f" missing={missing_keys}" if missing_keys else ""
                inherited_keys = list(tr["inherited_context"].keys())
                inherited_str = f" inherit={inherited_keys}" if inherited_keys else ""
                overridden_str = ""
                for k, v in tr.get("overridden_context", {}).items():
                    if isinstance(v, dict) and "from" in v and "to" in v:
                        overridden_str += f" {v['from']}→{v['to']}"
                    else:
                        overridden_str += f" {k}={v}"

                print(f"  [{idx}] {tr['user']}")
                print(f"       {script} {can}{cm_str}{conf}{missing_str}{inherited_str}{overridden_str}")
                print(f"       cmd: {tr['recommended_command'][:120]}")

                if "execution" in tr:
                    exec_info = tr["execution"]
                    rc = exec_info.get("return_code", -1)
                    status = "✅" if rc == 0 else "❌"
                    print(f"       execution: {status} rc={rc}")
                print()

        print(f"{'─'*70}")
        print(f"Summary: {total_turns} turns, {executable_count} executable, {executed_count} executed, {success_count} success")
        if args.parse_text and total_compared > 0:
            print(f"Context Match: {total_matched}/{total_compared} ({match_rate*100:.1f}%)")
        print(f"{'='*70}")

    return output


if __name__ == "__main__":
    main()
