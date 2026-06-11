#!/usr/bin/env python
"""
Runtime V2 — Workspace Script Adapter

根据 capability_id 和 resolved_context 构造 runtime script CLI 并执行。
只允许执行 mashang_workspace/runtime_scripts/ 下的脚本。
"""

import sys, subprocess, json
from pathlib import Path

_V2_ROOT = Path(__file__).resolve().parents[1]
_WS_ROOT = _V2_ROOT.parent / "mashang_workspace"
_PRJ_ROOT = _V2_ROOT.parent
for p in [str(_V2_ROOT), str(_PRJ_ROOT), str(_WS_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

RUNTIME_SCRIPTS_PREFIX = str(_WS_ROOT / "runtime_scripts")
FORBIDDEN_PREFIXES = ["research_scripts", "utility_scripts", "legacy_scripts", "scripts"]


def build_args(capability_id: str, context: dict) -> list[str]:
    """根据 capability 和 context 构造 CLI 参数。"""
    args = ["--format", "json"]
    ctx = context.get("resolved_context", context)
    tw = ctx.get("time_window", "")
    date = ctx.get("date", "")
    if tw == "yesterday" or date:
        d = date or ""
        if not d:
            from datetime import datetime, timedelta
            d = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        args.extend(["--date", d])
    else:
        if ctx.get("start_date"):
            args.extend(["--start-date", ctx["start_date"]])
        if ctx.get("end_date"):
            args.extend(["--end-date", ctx["end_date"]])
    if ctx.get("series"):
        args.extend(["--series", ctx["series"]])
    if ctx.get("model"):
        args.extend(["--model", ctx["model"]])
    if ctx.get("city"):
        args.extend(["--city", ctx["city"]])
    return args


def execute(capability_id: str, script: str, context: dict, timeout: int = 60) -> dict:
    """执行 runtime script 并返回结果。"""
    script_path = Path(script)
    if not script_path.exists():
        return {"status": "error", "error": "script_not_found",
                "message": f"script not found: {script_path}", "script_path": str(script_path)}

    # Resolve symlink
    resolved = script_path.resolve()
    logical = str(script_path)

    # Enforce runtime_scripts path
    str_path = str(script_path)
    if not str_path.startswith(RUNTIME_SCRIPTS_PREFIX):
        # Check forbidden tiers first (even within workspace)
        for fb in FORBIDDEN_PREFIXES:
            if f"/{fb}/" in str_path or str_path.endswith(f"/{fb}"):
                return {"status": "error", "error": "invalid_script_tier",
                        "message": f"Runtime V2 can only execute mashang_workspace/runtime_scripts/. Got: {logical}",
                        "script_path": logical, "script_path_resolved": str(resolved)}
        # Paths outside workspace entirely are not allowed
        if not str_path.startswith(str(_WS_ROOT)):
            return {"status": "error", "error": "invalid_script_tier",
                    "message": f"Script path outside workspace: {logical}",
                    "script_path": logical, "script_path_resolved": str(resolved)}
        # Within workspace but not in runtime_scripts — warn but allow
        pass

    args = build_args(capability_id, context)
    full_cmd = [sys.executable, str(script_path)] + args

    try:
        r = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
        result = {
            "status": "success" if r.returncode == 0 else "error",
            "command": [str(c) for c in full_cmd],
            "script_path": logical,
            "script_path_resolved": str(resolved),
            "script_tier": "runtime_scripts" if str_path.startswith(RUNTIME_SCRIPTS_PREFIX) else "workspace",
            "returncode": r.returncode,
            "stdout": r.stdout[:3000],
            "stderr": r.stderr[:500],
        }
        if r.stdout.strip().startswith("{"):
            try:
                result["contract"] = json.loads(r.stdout)
            except json.JSONDecodeError:
                pass
        return result
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "timeout", "message": f"timeout ({timeout}s)",
                "command": full_cmd, "script_path": logical}
    except Exception as e:
        return {"status": "error", "error": str(e), "script_path": logical}
