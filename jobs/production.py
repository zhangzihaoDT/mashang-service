#!/usr/bin/env python
"""受控的生产数据 Job：只接受已登记的业务目标，不使用 shell，也不接受任意命令。

当前登记：
  data-refresh-tableau-hs
    刷新订单、选配、锁单归因和交付库存，与 daily 共用生产写入锁。

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
import re
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

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataset.updater.refresh_validation import MANAGED_VALIDATION, inspect_dataset, validate_output

JOB_ID = "data-refresh-daily"
TABLEAU_HS_JOB = "data-refresh-tableau-hs"
STATUS_TARGET = "data-status"
DAILY_DATASETS = ("order_data", "assign_data")
TP_MIX_JOB = "update-tp-and-mix-ways-dataset"
JOB_DATASETS = {
    TP_MIX_JOB: (
        "tp_mix_brand_monthly",
        "tp_mix_geo_monthly",
        "tp_mix_market_energy_monthly",
        "tp_mix_model_monthly",
        "tp_mix_price_segment_monthly",
        "tp_mix_product_segment_monthly",
    ),
    JOB_ID: DAILY_DATASETS,
    TABLEAU_HS_JOB: ("order_data", "config_attribute", "lock_attribution", "delivery_inventory"),
    "data-refresh-order-data": ("order_data",),
    "data-refresh-assign-data": ("assign_data",),
    "data-refresh-config-attribute": ("config_attribute",),
    "data-refresh-lock-attribution": ("lock_attribution",),
    "data-refresh-delivery-inventory": ("delivery_inventory",),
    "data-refresh-test-drive-data": ("test_drive_data",),
}
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


def verify_production_root(repo_root: str | Path, job: str = JOB_ID) -> Path:
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
    for target in (job, STATUS_TARGET):
        if target not in makefile.replace(":", " ").split():
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


def _atomic_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with open(temporary, "x", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    if exclusive:
        try:
            os.link(temporary, path)
        finally:
            temporary.unlink()
    else:
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

    def __init__(self, root: Path, run_id: str, requested_by: str, *, job: str = JOB_ID):
        self.root = root
        self.run_id = run_id
        self.requested_by = requested_by
        self.job = job
        self.path = root / LOG_DIR / f"{job}.lock"
        self.holder = root / LOG_DIR / f"{job}.holder.json"
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
                f"已有 {self.job} 正在执行"
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

    def fileno(self) -> int:
        return self._file.fileno()

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
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=1)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    # The group can still contain children after the leader exits.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=10)


def run_logged(
    argv: list[str], cwd: Path, log_path: Path, timeout: int, *, lock: JobLock, journal: Path | None = None,
) -> tuple[int, float]:
    """运行固定 argv，把 stdout/stderr 写入日志，超时终止整个进程组。"""
    started = time.monotonic()
    env = os.environ.copy()
    env.pop("MAKEFLAGS", None)
    env.pop("MFLAGS", None)
    env.pop("MASHANG_REFRESH_JOURNAL", None)
    if journal is not None:
        env["MASHANG_REFRESH_JOURNAL"] = str(journal)
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
            pass_fds=(lock.fileno(),),
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
            "size_bytes": item.get("size_bytes"),
            "file_mtime": item.get("file_mtime"),
            "data_asof": item.get("data_asof"),
            "data_asof_column": item.get("data_asof_column"),
        }
    return result


def _select_snapshot(snapshot: dict[str, dict], datasets: tuple[str, ...]) -> dict[str, dict]:
    return {key: snapshot.get(key, {}) for key in datasets}


def _compare(before: dict[str, dict], after: dict[str, dict]) -> tuple[list[str], bool, list[str]]:
    changed: list[str] = []
    new_data = False
    anomalies: list[str] = []
    for key in before:
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


def _record_paths(root: Path, run_id: str, job: str = JOB_ID) -> tuple[Path, Path, Path, Path]:
    directory = root / LOG_DIR
    return (
        directory / "records" / f"{run_id}.json",
        directory / ("latest.json" if job == JOB_ID else f"{job}-latest.json"),
        directory / f"{run_id}.log",
        directory / "events.jsonl",
    )


def _write_record(record: dict, record_path: Path, latest_path: Path) -> None:
    _atomic_json(record_path, record)
    latest = _load_record(latest_path)
    if not latest or latest.get("started_at", "") <= record["started_at"]:
        _atomic_json(latest_path, record)


def _summary(record: dict) -> str:
    status = record["status"]
    if status == "success":
        if record.get("outcome") == "updated_existing":
            return f"既有数据已订正；最新数据时点 {record.get('latest_data_time') or '未知'}"
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


def _load_record(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _validate_run_id(run_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", run_id):
        raise ProductionJobError("Invalid run ID")


def _matching_record(record_path: Path, job: str, run_id: str) -> dict:
    record = _load_record(record_path)
    if record and (record.get("job") != job or record.get("run_id") != run_id):
        raise ProductionJobError("Run ID is already bound to a different job")
    return record


def _target_snapshot(root: Path, all_data: dict, job: str) -> dict:
    target = _select_snapshot(all_data, JOB_DATASETS[job])
    for key in MANAGED_VALIDATION.get(job, ()):
        evidence = target[key]
        relative = evidence.get("path")
        if relative is None:
            evidence.update(valid=False, validation_error="Dataset missing from registry")
            continue
        path = (root / relative).resolve()
        if not path.is_relative_to(root / "dataset"):
            evidence.update(valid=False, validation_error="Dataset path is outside the production dataset root")
            continue
        evidence.update(inspect_dataset(key, root / relative))
    return target


def _journal_steps(path: Path) -> dict:
    latest = {}
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    step = json.loads(line)
                    latest[step["dataset"]] = step
                except (ValueError, KeyError, TypeError):
                    # A killed writer may leave a trailing partial line.
                    continue
    except FileNotFoundError:
        pass
    return latest


def _dataset_results(record: dict, journal: Path) -> tuple[list[str], bool, list[str]]:
    steps = _journal_steps(journal)
    results = {}
    changed = []
    new_data = False
    anomalies = []
    for key, after in record["after"].items():
        before = record["before"].get(key, {})
        step = steps.get(key, {})
        rc = step.get("returncode")
        different = before.get("sha256") != after.get("sha256")
        step_matches = step.get("state") == "finished" and step.get("sha256") == after.get("sha256")
        problems = validate_output(key, before, after)
        if step.get("state") == "finished" and not step_matches:
            problems.append(f"{key}: current output differs from completed step")
        if rc == 0 and not step_matches:
            problems.append(f"{key}: completed updater has no matching output evidence")
        if rc == 0:
            execution = "succeeded"
        elif rc is not None:
            execution = "timeout" if rc == 124 else "failed"
        else:
            execution = "interrupted" if step else "not_started"

        if not after.get("valid"):
            publication = "invalid"
        elif different:
            publication = "published" if step_matches and not problems else "changed_unconfirmed"
        else:
            publication = "unchanged"

        if different:
            changed.append(key)
        for field in ("validated_rows", "validated_cutoff"):
            prior, current = before.get(field), after.get(field)
            if publication == "published" and current is not None and (prior is None or current > prior):
                new_data = True
        anomalies.extend(problems)
        results[key] = {
            "execution_status": execution, "publish_status": publication, "returncode": rc,
            "before_sha256": before.get("sha256"), "after_sha256": after.get("sha256"),
            "verified": not problems, "verification_errors": problems,
        }
    record["dataset_results"] = results
    return changed, new_data, anomalies


def _collect_result(record: dict, root: Path, all_data: dict, journal: Path, *, recovered: bool = False) -> None:
    job = record["job"]
    record["after"] = _target_snapshot(root, all_data, job)
    record["latest_data_time_by_dataset"] = {
        key: item["data_asof"] for key, item in all_data.items() if item.get("data_asof")
    }
    refresh_rc = record.get("refresh_returncode")
    status_rc = record.get("status_returncode")
    if job in MANAGED_VALIDATION:
        changed, new_data, anomalies = _dataset_results(record, journal)
        states = {item["execution_status"] for item in record["dataset_results"].values()}
    else:
        changed, new_data, anomalies = _compare(record["before"], record["after"])
        states = set()
    if job == "data-refresh-config-attribute":
        config = record["after"]["config_attribute"]
        if not config.get("exists") or not config.get("rows") or not config.get("file_mtime"):
            anomalies.append("config_attribute 缺失、为空或无法核验")
    if job == TP_MIX_JOB:
        for key, evidence in record["after"].items():
            if not evidence.get("exists") or not evidence.get("rows") or not evidence.get("data_asof"):
                anomalies.append(f"{key} 缺失、为空或无法核验业务月份")

    record.update(changed_datasets=changed, new_data=new_data, latest_data_time=_latest_time(record["after"]))
    record["warnings"].extend(anomalies)
    if refresh_rc == 124 or "timeout" in states:
        record.update(status="timeout", error=f"{job} 刷新超时，按运行记录核验已发布数据")
    elif refresh_rc not in (None, 0) or "failed" in states:
        record.update(status="failed", error=f"{job} 刷新失败（退出码 {refresh_rc}）")
    elif status_rc not in (None, 0) or anomalies:
        record.update(status="verification_failed", error="；".join(anomalies) or f"data-status 退出码 {status_rc}")
    elif job in MANAGED_VALIDATION and states != {"succeeded"}:
        record.update(status="verification_failed", error="刷新未完成，缺少目标表的完整执行记录")
    elif recovered and job not in MANAGED_VALIDATION and (refresh_rc is None or status_rc is None):
        record.update(status="verification_failed", error="刷新中断，缺少完成记录")
    elif new_data or (changed and job in MANAGED_VALIDATION):
        record["status"] = "success"
    else:
        record["status"] = "no_new_data"

    if job in MANAGED_VALIDATION:
        record["outcome"] = record["status"]
        if record["status"] == "success":
            record["outcome"] = "all_succeeded" if new_data else "updated_existing"
        elif changed:
            record["outcome"] = "partial_write"


def _finish(record: dict, record_path: Path, latest_path: Path, events_path: Path) -> dict:
    record["finished_at"] = utc_now()
    record["duration_s"] = round(
        (datetime.fromisoformat(record["finished_at"]) - datetime.fromisoformat(record["started_at"])).total_seconds(), 2
    )
    record["summary"] = _summary(record)
    _write_record(record, record_path, latest_path)
    _append_event(events_path, {"at": record["finished_at"], "event": "finished",
                                "run_id": record["run_id"], "status": record["status"]})
    return record


def _recover_locked(root: Path, record: dict, paths: tuple[Path, Path, Path, Path]) -> dict:
    record_path, latest_path, _, events_path = paths
    record["recovered"] = True
    if record.get("before"):
        _collect_result(record, root, dataset_snapshot(root), record_path.with_suffix(".steps.jsonl"), recovered=True)
    else:
        record.update(status="failed", outcome="failed", error="Interrupted before the refresh scope was recorded")
    return _finish(record, record_path, latest_path, events_path)


def run_job(
    repo_root: str | Path,
    *,
    job: str = JOB_ID,
    timeout: int = DEFAULT_TIMEOUT,
    requested_by: str = "",
    run_id: Optional[str] = None,
) -> dict:
    """Execute a fixed refresh. A repeated run ID observes or recovers its first run."""
    root = Path(repo_root).expanduser().resolve()
    run_id = run_id or os.getenv("MASHANG_JOB_RUN_ID") or f"{job}-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    requested_by = (requested_by or os.getenv("MASHANG_JOB_REQUESTED_BY", ""))[:200]
    record: dict = {
        "version": 1, "job": job, "run_id": run_id, "status": "running",
        "started_at": utc_now(), "finished_at": None, "duration_s": None,
        "repo_root": str(root), "requested_by": requested_by, "timeout_seconds": timeout,
        "commands": [], "before": {}, "after": {}, "changed_datasets": [], "new_data": False,
        "latest_data_time": None, "latest_data_time_by_dataset": {}, "data_status_text": "",
        "warnings": [], "error": None, "record_path": None,
    }
    if job in MANAGED_VALIDATION:
        record.update(contract_version=2, outcome="running", dataset_results={})
    try:
        _validate_run_id(run_id)
        root = verify_production_root(root, job)
    except ProductionJobError as error:
        record.update(status="failed", finished_at=utc_now(), duration_s=0, error=str(error), summary=str(error))
        if job in MANAGED_VALIDATION:
            record["outcome"] = "failed"
        return record

    paths = _record_paths(root, run_id, job)
    record_path, latest_path, log_path, events_path = paths
    journal = record_path.with_suffix(".steps.jsonl")
    record.update(record_path=str(record_path), log_path=str(log_path))
    existing = _matching_record(record_path, job, run_id)
    if existing and existing["status"] != "running":
        return existing
    try:
        with JobLock(root, run_id, requested_by) as lock:
            existing = _matching_record(record_path, job, run_id)
            if existing:
                return _recover_locked(root, existing, paths) if existing["status"] == "running" else existing
            try:
                _atomic_json(record_path, record, exclusive=True)
            except FileExistsError:
                return _matching_record(record_path, job, run_id)

            try:
                record["git"] = _repo_state(root)
                record["before"] = _target_snapshot(root, dataset_snapshot(root), job)
                _append_event(events_path, {"at": utc_now(), "event": "snapshot_before", "run_id": run_id})
                _write_record(record, record_path, latest_path)
                refresh_argv = _make_command(job)
                refresh_rc, refresh_s = run_logged(
                    refresh_argv, root, log_path, timeout, lock=lock,
                    journal=journal if job in MANAGED_VALIDATION else None,
                )
                record["refresh_returncode"] = refresh_rc
                record["commands"].append({"argv": refresh_argv, "returncode": refresh_rc, "duration_s": refresh_s})
                _write_record(record, record_path, latest_path)
                status_argv = _make_command(STATUS_TARGET)
                status_rc, status_s = run_logged(status_argv, root, log_path, STATUS_TIMEOUT, lock=lock)
                record["status_returncode"] = status_rc
                record["commands"].append({"argv": status_argv, "returncode": status_rc, "duration_s": status_s})
                record["data_status_text"] = _read_tail(log_path, 12000)
                _collect_result(record, root, dataset_snapshot(root), journal)
            except Exception as error:
                record.update(status="failed", error=f"{type(error).__name__}: {error}")
                if job in MANAGED_VALIDATION:
                    record["outcome"] = "verification_unknown" if record.get("refresh_returncode") is not None else "failed"
            return _finish(record, record_path, latest_path, events_path)
    except JobBusy as error:
        existing = _matching_record(record_path, job, run_id)
        if existing:
            return existing
        record.update(status="busy", error=str(error), summary=str(error), finished_at=utc_now(), duration_s=0)
        if job in MANAGED_VALIDATION:
            record["outcome"] = "busy"
        try:
            _atomic_json(record_path, record, exclusive=True)
        except FileExistsError:
            return _matching_record(record_path, job, run_id)
        return record


def run_record(repo_root: str | Path, job: str, run_id: str, *, recover: bool = False) -> dict:
    _validate_run_id(run_id)
    root = verify_production_root(repo_root, job)
    paths = _record_paths(root, run_id, job)
    record = _matching_record(paths[0], job, run_id)
    if not record:
        return {"job": job, "run_id": run_id, "status": "not_found", "summary": "No record for this run ID"}
    if not recover or record["status"] != "running":
        return record
    try:
        with JobLock(root, run_id, "recover"):
            current = _matching_record(paths[0], job, run_id)
            return _recover_locked(root, current, paths) if current["status"] == "running" else current
    except JobBusy:
        return _matching_record(paths[0], job, run_id)


def _read_tail(path: Path, limit: int) -> str:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - limit))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def latest_record(repo_root: str | Path, job: str = JOB_ID) -> dict:
    root = verify_production_root(repo_root, job)
    path = root / LOG_DIR / ("latest.json" if job == JOB_ID else f"{job}-latest.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"status": "idle", "job": job, "summary": "暂无执行记录"}
    except ValueError as error:
        raise ProductionJobError(f"最新记录无法解析：{error}") from error


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "status", "check", "recover"])
    parser.add_argument("job", nargs="?", default=JOB_ID)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--requested-by", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    try:
        if args.job not in JOB_DATASETS:
            raise ProductionJobError(f"未登记的 job：{args.job}")
        if args.action == "check":
            root = verify_production_root(args.repo_root, args.job)
            print(json.dumps({"status": "ok", "job": args.job, "repo_root": str(root)}, ensure_ascii=False))
            return 0
        if args.action in {"status", "recover"}:
            if args.action == "recover" and not args.run_id:
                raise ProductionJobError("recover requires --run-id")
            record = (run_record(args.repo_root, args.job, args.run_id, recover=args.action == "recover")
                      if args.run_id else latest_record(args.repo_root, args.job))
            print(json.dumps(record, ensure_ascii=False))
            return int(record["status"] == "not_found")
        record = run_job(
            args.repo_root,
            job=args.job,
            timeout=max(1, args.timeout),
            requested_by=args.requested_by,
            run_id=args.run_id or None,
        )
        print(json.dumps(record, ensure_ascii=False))
        if record["status"] == "busy":
            return 2
        return 0 if record["status"] in {"success", "no_new_data", "running"} else 1
    except Exception as error:  # noqa: BLE001 - CLI prints structured failures
        print(json.dumps({"status": "failed", "job": args.job, "error": str(error)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
