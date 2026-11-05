#!/usr/bin/env python
"""受控的生产数据 Job：只接受已登记的业务目标，不使用 shell，也不接受任意命令。

当前登记：
  data-refresh-daily
    在经验证的主 checkout 中运行 `make -j1 data-refresh-daily`，
    随后自动运行 `make -j1 data-status`，并比较刷新前后的结构化数据集状态。

安全边界：
  - 只允许固定 job id；argv 由本模块固定拼装，不接收用户命令。
  - 拒绝 linked worktree / submodule：`.git` 必须是目录，且 git toplevel 必须等于目标仓库。
  - 文件锁阻止并发刷新；超时会终止整个子进程组。
  - 记录写入 `logs/production-jobs/`（仓库已忽略），包含 JSON 运行记录、JSONL 事件和完整命令日志。
  - 业务实现仍由 Makefile / dataset updater 承担；本模块只负责执行、加锁、超时与结果核验。
"""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

JOB_ID = "data-refresh-daily"
MAKE_TARGET = "data-refresh-daily"
STATUS_TARGET = "data-status"
DAILY_DATASETS = ("order_data", "assign_data")
DEFAULT_TIMEOUT = 1800
STATUS_TIMEOUT = 180
LOG_DIR = Path("logs") / "production-jobs"


class ProductionJobError(Exception):
    """生产 Job 的配置或环境错误；不会启动任何写操作。"""


class JobBusy(ProductionJobError):
    """另一个生产 Job 持有同一把锁。"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(argv: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def _git(root: Path, *args: str) -> str:
    result = _run(["git", "-C", str(root), *args], root)
    if result.returncode != 0:
        raise ProductionJobError(
            f"git {' '.join(args)} 失败：{(result.stderr or result.stdout).strip()[:300]}"
        )
    return result.stdout.strip()


def verify_production_root(repo_root: str | Path) -> Path:
    """验证目标是一个真实的主 checkout，而不是临时 Ticket worktree。

    linked worktree 的 `.git` 是文件；submodule 也是文件。两者都拒绝。
    """
    root = Path(repo_root).expanduser().resolve()
    if not root.is_dir():
        raise ProductionJobError(f"生产仓库不存在：{root}")

    git_marker = root / ".git"
    if not git_marker.is_dir():
        kind = "文件（linked worktree / submodule）" if git_marker.is_file() else "缺失"
        raise ProductionJobError(
            f"拒绝在非主 checkout 执行生产更新：{root} 的 .git 是{kind}；"
            "Ticket worktree 只能用于开发与只读查询。"
        )

    required = (
        "Makefile",
        ".venv/bin/python",
        "dataset/updater/update_all_datasets.py",
        "dataset/updater/dataset_registry.py",
    )
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        raise ProductionJobError(f"生产仓库缺少 {', '.join(missing)}：{root}")

    makefile = (root / "Makefile").read_text(encoding="utf-8", errors="replace")
    for target in (f"{MAKE_TARGET}:", f"{STATUS_TARGET}:"):
        if target not in makefile:
            raise ProductionJobError(f"Makefile 缺少受控目标 {target}：{root}")

    toplevel = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    if toplevel != root:
        raise ProductionJobError(
            f"生产仓库根目录不一致：请求 {root}，git toplevel {toplevel}。"
        )
    return root


def _make_command(target: str) -> list[str]:
    make = shutil.which("make") or "/usr/bin/make"
    return [make, "-j1", target]


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with open(temporary, "x", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


class JobLock:
    """跨进程阻塞锁；锁文件由内核持有，进程退出自动释放。

    holder 文件只用于解释“谁在运行”，不是锁本身。
    """

    def __init__(self, root: Path, run_id: str, requested_by: str):
        self.root = root
        self.run_id = run_id
        self.requested_by = requested_by
        self.path = root / LOG_DIR / f"{JOB_ID}.lock"
        self.holder = root / LOG_DIR / f"{JOB_ID}.holder.json"
        self._file = None

    def __enter__(self) -> "JobLock":
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._file = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = self._read_holder()
            self._file.close()
            self._file = None
            raise JobBusy(
                f"已有 {JOB_ID} 正在执行"
                + (f"（pid {holder.get('pid')}，开始于 {holder.get('started_at')}）" if holder else "")
            )
        _atomic_json(
            self.holder,
            {
                "pid": os.getpid(),
                "run_id": self.run_id,
                "requested_by": self.requested_by,
                "started_at": utc_now(),
            },
        )
        return self

    def _read_holder(self) -> dict:
        try:
            return json.loads(self.holder.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def __exit__(self, *_exc) -> None:
        try:
            self.holder.unlink(missing_ok=True)
        finally:
            if self._file is not None:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
                self._file.close()
                self._file = None


@contextmanager
def _log_stream(path: Path) -> Iterator[Any]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "ab", buffering=0) as handle:
        yield handle


def _terminate_group(process: subprocess.Popen) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


def run_logged(argv: list[str], cwd: Path, log_path: Path, timeout: int) -> tuple[int, float]:
    """运行固定 argv，把 stdout/stderr 写入日志，超时终止整个进程组。"""
    started = time.monotonic()
    env = os.environ.copy()
    env.pop("MAKEFLAGS", None)
    env.pop("MFLAGS", None)
    env["PYTHONUNBUFFERED"] = "1"
    with _log_stream(log_path) as output:
        output.write(f"\n[{utc_now()}] $ {' '.join(argv)}\n".encode())
        process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            output.write(f"[{utc_now()}] 超时 {timeout}s，终止进程组 {process.pid}\n".encode())
            _terminate_group(process)
            returncode = 124
        output.write(f"[{utc_now()}] exit={returncode}\n".encode())
    return returncode, round(time.monotonic() - started, 2)


def _registry(root: Path):
    module_path = root / "dataset/updater/dataset_registry.py"
    name = f"_mashang_dataset_registry_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise ProductionJobError(f"无法加载数据集清单：{module_path}")
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the defining module through sys.modules; register it before executing.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def dataset_snapshot(root: Path) -> dict[str, dict]:
    """只读状态：行数、文件更新时间、数据最新时点。"""
    registry = _registry(root)
    result: dict[str, dict] = {}
    for item in registry.describe_all():
        result[item["key"]] = {
            "label": item.get("label"),
            "path": item.get("path"),
            "exists": item.get("exists"),
            "rows": item.get("rows"),
            "file_mtime": item.get("file_mtime"),
            "data_asof": item.get("data_asof"),
            "data_asof_column": item.get("data_asof_column"),
        }
    return result


def _daily_snapshot(snapshot: dict[str, dict]) -> dict[str, dict]:
    return {key: snapshot.get(key, {}) for key in DAILY_DATASETS}


def _compare(before: dict[str, dict], after: dict[str, dict]) -> tuple[list[str], bool, list[str]]:
    changed: list[str] = []
    new_data = False
    anomalies: list[str] = []
    for key in DAILY_DATASETS:
        old, new = before.get(key, {}), after.get(key, {})
        old_rows, new_rows = old.get("rows"), new.get("rows")
        old_asof, new_asof = old.get("data_asof"), new.get("data_asof")
        old_mtime, new_mtime = old.get("file_mtime"), new.get("file_mtime")
        if old_rows != new_rows or old_asof != new_asof or old_mtime != new_mtime:
            changed.append(key)
        if isinstance(old_rows, int) and isinstance(new_rows, int) and new_rows > old_rows:
            new_data = True
        if new_asof and not old_asof:
            new_data = True
        elif new_asof and old_asof:
            if new_asof > old_asof:
                new_data = True
            elif new_asof < old_asof:
                anomalies.append(f"{key} 数据时点回退：{old_asof} -> {new_asof}")
        if isinstance(old_rows, int) and isinstance(new_rows, int) and new_rows < old_rows:
            anomalies.append(f"{key} 行数减少：{old_rows} -> {new_rows}")
    return changed, new_data, anomalies


def _latest_time(snapshot: dict[str, dict]) -> Optional[str]:
    values = [item.get("data_asof") for item in snapshot.values() if item.get("data_asof")]
    return max(values) if values else None


def _repo_state(root: Path) -> dict:
    try:
        return {
            "head": _git(root, "rev-parse", "HEAD"),
            "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(_git(root, "status", "--porcelain")),
        }
    except ProductionJobError as error:
        return {"error": str(error)}


def _record_paths(root: Path, run_id: str) -> tuple[Path, Path, Path, Path]:
    directory = root / LOG_DIR
    return (
        directory / "records" / f"{run_id}.json",
        directory / "latest.json",
        directory / f"{run_id}.log",
        directory / "events.jsonl",
    )


def _write_record(record: dict, record_path: Path, latest_path: Path) -> None:
    _atomic_json(record_path, record)
    _atomic_json(latest_path, record)


def _summary(record: dict) -> str:
    status = record["status"]
    if status == "success":
        return f"数据更新完成；最新数据时点 {record.get('latest_data_time') or '未知'}"
    if status == "no_new_data":
        return f"刷新完成，但未产生新数据；最新数据时点仍为 {record.get('latest_data_time') or '未知'}"
    if status == "busy":
        return record.get("error") or "已有刷新任务正在执行"
    if status == "timeout":
        return f"执行超时（{record.get('timeout_seconds')}s），已终止进程组；请核验日志"
    if status == "verification_failed":
        return record.get("error") or "刷新命令结束，但 data-status 校验失败"
    return record.get("error") or "数据更新失败；请查看日志"


def run_job(
    repo_root: str | Path,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    requested_by: str = "",
    run_id: Optional[str] = None,
) -> dict:
    """执行一次 data-refresh-daily；返回结构化记录，不抛出业务失败。"""
    root = Path(repo_root).expanduser().resolve()
    run_id = (
        run_id
        or os.getenv("MASHANG_JOB_RUN_ID", "")
        or f"{JOB_ID}-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    )
    requested_by = (requested_by or os.getenv("MASHANG_JOB_REQUESTED_BY", ""))[:200]
    started_at = utc_now()

    # 先核验目标，再写任何文件：Ticket worktree / submodule 不得留下运行记录或日志。
    try:
        root = verify_production_root(root)
    except ProductionJobError as error:
        return {
            "version": 1,
            "job": JOB_ID,
            "run_id": run_id,
            "status": "failed",
            "started_at": started_at,
            "finished_at": utc_now(),
            "duration_s": 0,
            "repo_root": str(root),
            "requested_by": requested_by,
            "before": {},
            "after": {},
            "changed_datasets": [],
            "new_data": False,
            "latest_data_time": None,
            "warnings": [],
            "error": str(error),
            "summary": str(error),
            "record_path": None,
        }

    record_path, latest_path, log_path, events_path = _record_paths(root, run_id)
    record: dict = {
        "version": 1,
        "job": JOB_ID,
        "run_id": run_id,
        "status": "running",
        "started_at": started_at,
        "finished_at": None,
        "duration_s": None,
        "repo_root": str(root),
        "requested_by": requested_by,
        "timeout_seconds": timeout,
        "commands": [],
        "before": {},
        "after": {},
        "changed_datasets": [],
        "new_data": False,
        "latest_data_time": None,
        "latest_data_time_by_dataset": {},
        "data_status_text": "",
        "log_path": str(log_path),
        "warnings": [],
        "error": None,
    }
    _append_event(events_path, {"at": started_at, "event": "requested", "run_id": run_id, "requested_by": requested_by})
    _write_record(record, record_path, latest_path)

    try:
        record["repo_root"] = str(root)
        record["git"] = _repo_state(root)
        record["record_path"] = str(record_path)

        before_all = dataset_snapshot(root)
        record["before"] = _daily_snapshot(before_all)
        _append_event(events_path, {"at": utc_now(), "event": "snapshot_before", "run_id": run_id})
        _write_record(record, record_path, latest_path)

        try:
            with JobLock(root, run_id, requested_by):
                refresh_code, refresh_s = run_logged(
                    _make_command(MAKE_TARGET), root, log_path, timeout
                )
                record["commands"].append(
                    {"argv": _make_command(MAKE_TARGET), "returncode": refresh_code, "duration_s": refresh_s}
                )
                _append_event(
                    events_path,
                    {"at": utc_now(), "event": "refresh_finished", "run_id": run_id, "returncode": refresh_code},
                )

                status_code, status_s = run_logged(
                    _make_command(STATUS_TARGET), root, log_path, STATUS_TIMEOUT
                )
                record["commands"].append(
                    {"argv": _make_command(STATUS_TARGET), "returncode": status_code, "duration_s": status_s}
                )
                record["data_status_text"] = _read_tail(log_path, 12000)
                _append_event(
                    events_path,
                    {"at": utc_now(), "event": "status_finished", "run_id": run_id, "returncode": status_code},
                )
        except JobBusy as error:
            record.update(status="busy", error=str(error), finished_at=utc_now())
            _append_event(events_path, {"at": utc_now(), "event": "busy", "run_id": run_id, "error": str(error)})
            _write_record(record, record_path, latest_path)
            return record

        after_all = dataset_snapshot(root)
        record["after"] = _daily_snapshot(after_all)
        record["latest_data_time_by_dataset"] = {
            key: item.get("data_asof") for key, item in after_all.items() if item.get("data_asof")
        }
        changed, new_data, anomalies = _compare(record["before"], record["after"])
        record["changed_datasets"] = changed
        record["new_data"] = new_data
        record["latest_data_time"] = _latest_time(record["after"])
        record["warnings"].extend(anomalies)

        if refresh_code == 124:
            record["status"] = "timeout"
            record["error"] = f"{MAKE_TARGET} 超时（{timeout}s），进程组已终止"
        elif refresh_code != 0:
            record["status"] = "failed"
            record["error"] = f"{MAKE_TARGET} 退出码 {refresh_code}"
        elif status_code != 0:
            record["status"] = "verification_failed"
            record["error"] = f"{STATUS_TARGET} 退出码 {status_code}；刷新结果未完成核验"
        elif anomalies:
            record["status"] = "verification_failed"
            record["error"] = "；".join(anomalies)
        elif new_data:
            record["status"] = "success"
        else:
            record["status"] = "no_new_data"

        record["finished_at"] = utc_now()
        record["duration_s"] = round(
            (datetime.fromisoformat(record["finished_at"]) - datetime.fromisoformat(started_at)).total_seconds(), 2
        )
        record["summary"] = _summary(record)
        _append_event(
            events_path,
            {"at": record["finished_at"], "event": "finished", "run_id": run_id, "status": record["status"]},
        )
        _write_record(record, record_path, latest_path)
        return record
    except Exception as error:  # noqa: BLE001 - record every environment failure
        finished_at = utc_now()
        record.update(
            status="failed",
            error=f"{type(error).__name__}: {error}",
            finished_at=finished_at,
            duration_s=round(
                (datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)).total_seconds(), 2
            ),
        )
        record["summary"] = _summary(record)
        _append_event(
            events_path,
            {"at": record["finished_at"], "event": "error", "run_id": run_id, "error": record["error"]},
        )
        _write_record(record, record_path, latest_path)
        return record


def _read_tail(path: Path, limit: int) -> str:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - limit))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def latest_record(repo_root: str | Path) -> dict:
    root = verify_production_root(repo_root)
    path = root / LOG_DIR / "latest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"status": "idle", "job": JOB_ID, "summary": "暂无执行记录"}
    except ValueError as error:
        raise ProductionJobError(f"最新记录无法解析：{error}") from error


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "status", "check"])
    parser.add_argument("job", nargs="?", default=JOB_ID)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--requested-by", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    try:
        if args.job != JOB_ID:
            raise ProductionJobError(f"未登记的 job：{args.job}")
        if args.action == "check":
            root = verify_production_root(args.repo_root)
            print(json.dumps({"status": "ok", "job": JOB_ID, "repo_root": str(root)}, ensure_ascii=False))
            return 0
        if args.action == "status":
            print(json.dumps(latest_record(args.repo_root), ensure_ascii=False))
            return 0
        record = run_job(
            args.repo_root,
            timeout=max(1, args.timeout),
            requested_by=args.requested_by,
            run_id=args.run_id or None,
        )
        print(json.dumps(record, ensure_ascii=False))
        if record["status"] == "busy":
            return 2
        return 0 if record["status"] in {"success", "no_new_data"} else 1
    except Exception as error:  # noqa: BLE001 - CLI prints structured failures
        print(json.dumps({"status": "failed", "job": JOB_ID, "error": str(error)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
