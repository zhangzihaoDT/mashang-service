#!/usr/bin/env python
"""jobs — Worker / Hub 调用入口（确定性执行，无自然语言路由）。

用法:
    python -m jobs.cli --job nev_apeal_production_golden
    python -m jobs.cli --job nev_apeal_research_state --job-param topic=topic_x
    python -m jobs.cli --list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_JOBS_ROOT = Path(__file__).resolve().parent
_PRJ_ROOT = _JOBS_ROOT.parent
for p in (str(_PRJ_ROOT), str(_JOBS_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from jobs.adapter import load_jobs, run_job  # noqa: E402


def _job_short(result: dict) -> str:
    jid = result.get("job_id")
    st = result.get("status")
    if st == "error":
        return f"[job] {jid} error: {result.get('error')}"
    lines = [f"[job] {jid}: {st} (returncode={result.get('returncode')}, {result.get('duration_s')}s)"]
    out = (result.get("output") or "").strip().splitlines()
    lines.extend(out[:6])
    for a in result.get("artifacts", []):
        marks = "✓" if a.get("exists") else "✗"
        lines.append(f"  artifact {marks} {a.get('path')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="jobs — 确定性 job 执行入口")
    parser.add_argument("--job", type=str, default=None, help="job id（见 --list）")
    parser.add_argument("--job-param", action="append", default=[], metavar="K=V",
                        help="job 参数，可重复（如 topic=expectation_calibration）")
    parser.add_argument("--job-timeout", type=int, default=None, help="job 超时（秒）")
    parser.add_argument("--list", action="store_true", help="列出已声明 job")
    parser.add_argument("--format", type=str, default="text", choices=["text", "json"])
    parser.add_argument("--output", type=str, help="输出文件路径")
    args = parser.parse_args(argv)

    if args.list:
        jobs = load_jobs()
        for jid, cfg in jobs.items():
            print(f"{jid}\t{cfg.get('label', '')}")
        return 0

    if not args.job:
        parser.print_help()
        return 2

    params: dict = {}
    for kv in args.job_param:
        if "=" in kv:
            k, v = kv.split("=", 1)
            params[k] = v
        else:
            params[kv] = ""

    result = run_job(args.job, params=params, timeout=args.job_timeout)
    body = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(body, encoding="utf-8")
        print(f"[Output] {args.output}")
    elif args.format == "json":
        print(body)
    else:
        print(_job_short(result))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
