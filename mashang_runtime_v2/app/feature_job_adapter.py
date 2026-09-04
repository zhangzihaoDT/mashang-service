#!/usr/bin/env python
"""
Runtime V2 — Feature Job Adapter（Research Application orchestration PoC）

通过 runtime_v2_config.json 的 feature_jobs 声明式定义"调用外部 Research Application 的 job"：
固定 argv 模板 + 白名单参数 + 指定 cwd → subprocess（无 shell）→ status/duration →
artifact 探测 → 结构化结果（JSON 摘要或文本输出）。

安全约束：
  - argv 只由 config 模板拼装，{python}/{repo_root} 与已声明参数是仅有的可替换 token；
  - 参数经白名单校验（date/pattern），用户文本不进入 shell；
  - cwd 来自 config（相对仓库根解析），不允许任意命令注入。

design: Research Application 业务逻辑留在其各自目录（不复制进 runtime_v2），
本 adapter 只负责"如何调用 + 收集状态/产物"。MIIT / auto_launch / project_4 等后续
只需在 config 增加 feature_jobs 条目。
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_V2_ROOT = Path(__file__).resolve().parents[1]
_PRJ_ROOT = _V2_ROOT.parent
CONFIG_PATH = _V2_ROOT / "config" / "runtime_v2_config.json"

OUTPUT_TRIM = 4000


def load_feature_jobs(config: Optional[dict] = None) -> dict:
    cfg = config
    if cfg is None:
        if CONFIG_PATH.exists():
            cfg = json.loads(CONFIG_PATH.read_text())
        else:
            cfg = {}
    return cfg.get("feature_jobs", {})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_params(job_cfg: dict, params: dict) -> dict:
    """白名单校验并填充默认值；非法参数抛 ValueError（不执行）。"""
    spec = job_cfg.get("params", {})
    clean: dict = {}
    for name, meta in spec.items():
        ptype = meta.get("type", "str")
        value = params.get(name, meta.get("default"))
        if value is None:
            if meta.get("required"):
                raise ValueError(f"job 缺少必填参数: {name}")
            continue
        value = str(value)
        if ptype == "date":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError(f"参数 {name} 需为 YYYY-MM-DD，got: {value!r}")
        elif ptype == "pattern":
            pat = meta.get("pattern")
            if pat and not re.fullmatch(pat, value):
                raise ValueError(f"参数 {name} 不匹配 {pat}: {value!r}")
        clean[name] = value
    unknown = set(params) - set(spec)
    if unknown:
        raise ValueError(f"未声明的 job 参数: {sorted(unknown)}")
    return clean


def resolve_text(text: str, tokens: dict) -> str:
    out = text
    for key, value in tokens.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def resolve_template(template: list[str], tokens: dict) -> list[str]:
    return [resolve_text(part, tokens) for part in template]


def _stat_artifact(path: Path) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False}
    st = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size": st.st_size,
        "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def run_job(job_id: str, params: Optional[dict] = None, timeout: Optional[int] = None,
            jobs_override: Optional[dict] = None, config: Optional[dict] = None) -> dict:
    """运行一个 feature job，返回结构化结果。

    jobs_override / config 供测试注入（hermetic，不依赖真实 feature）。
    """
    params = params or {}
    started = time.time()
    created = _now()

    jobs = load_feature_jobs(config)
    if jobs_override is not None:
        jobs = jobs_override
    job_cfg = jobs.get(job_id)
    if not job_cfg:
        return {
            "job_id": job_id,
            "status": "error",
            "error": f"unknown feature_job: {job_id}",
            "created_at": created,
        }

    try:
        clean_params = validate_params(job_cfg, params)
    except ValueError as e:
        return {
            "job_id": job_id,
            "module": job_cfg.get("module", ""),
            "status": "error",
            "error": str(e),
            "created_at": created,
        }

    repo_root = str(_PRJ_ROOT)
    tokens = {
        "python": sys.executable,
        "repo_root": repo_root,
        **clean_params,
    }
    argv = resolve_template(job_cfg.get("argv_template", []), tokens)
    unresolved = [a for a in argv if a.startswith("{") and a.endswith("}")]
    if unresolved:
        return {
            "job_id": job_id,
            "module": job_cfg.get("module", ""),
            "status": "error",
            "error": f"argv_template 存在未解析 token: {unresolved}",
            "created_at": created,
        }

    cwd_tpl = job_cfg.get("cwd", "{repo_root}")
    cwd = resolve_text(cwd_tpl, tokens) if cwd_tpl else repo_root
    cwd = cwd if os.path.isabs(cwd) else str(Path(repo_root) / cwd)
    cwd_path = Path(cwd)

    env = os.environ.copy()
    if job_cfg.get("add_cwd_to_path"):
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (cwd + os.pathsep + existing) if existing else cwd

    timeout_s = timeout or job_cfg.get("timeout_seconds") or 180

    try:
        r = subprocess.run(argv, cwd=str(cwd_path), capture_output=True, text=True,
                           timeout=timeout_s, env=env)
        returncode = r.returncode
        stdout = r.stdout or ""
        stderr = (r.stderr or "").strip()
    except subprocess.TimeoutExpired as e:
        return {
            "job_id": job_id,
            "module": job_cfg.get("module", ""),
            "label": job_cfg.get("label", ""),
            "status": "failed",
            "error": f"timeout ({timeout_s}s)",
            "duration_s": round(time.time() - started, 2),
            "command": argv,
            "cwd": str(cwd_path),
            "created_at": created,
            "output": "",
            "artifacts": [],
        }
    except Exception as e:  # pragma: no cover - defensive
        return {
            "job_id": job_id,
            "module": job_cfg.get("module", ""),
            "label": job_cfg.get("label", ""),
            "status": "error",
            "error": str(e),
            "duration_s": round(time.time() - started, 2),
            "command": argv,
            "created_at": created,
        }

    # output / summary
    output = stdout.strip()[:OUTPUT_TRIM]
    summary_json = None
    if job_cfg.get("summary") == "json" and stdout.strip().startswith("{"):
        try:
            summary_json = json.loads(stdout)
        except json.JSONDecodeError:
            pass

    artifacts = []
    for tpl in job_cfg.get("artifacts", []):
        rel = resolve_text(tpl, tokens)
        p = rel if os.path.isabs(rel) else str(Path(cwd_path) / rel)
        artifacts.append(_stat_artifact(Path(p)))

    ok = returncode == 0
    return {
        "job_id": job_id,
        "module": job_cfg.get("module", ""),
        "label": job_cfg.get("label", ""),
        "status": "ok" if ok else "failed",
        "returncode": returncode,
        "duration_s": round(time.time() - started, 2),
        "command": argv,
        "cwd": str(cwd_path),
        "params": clean_params,
        "output": output,
        "summary_json": summary_json,
        "error": None if ok else (stderr or output[-500:] or "non-zero exit"),
        "artifacts": artifacts,
        "created_at": created,
    }
