#!/usr/bin/env python
"""jobs.production — hermetic tests for the controlled data-refresh-daily job.

Every test uses a temporary repository and a temporary Makefile. No test reads or
writes the real mashang-service dataset directory.
"""

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

_JOBS_ROOT = Path(__file__).resolve().parents[1]
_PRJ_ROOT = _JOBS_ROOT.parent
for path in (str(_PRJ_ROOT), str(_JOBS_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from jobs import production  # noqa: E402


REGISTRY = """
import json
from dataclasses import asdict, dataclass
from pathlib import Path

@dataclass(frozen=True)
class Dataset:
    key: str
    label: str
    path: str
    exists: bool
    rows: int
    file_mtime: str
    data_asof: str
    data_asof_column: str

def describe_all():
    state = json.loads((Path(__file__).resolve().parents[2] / 'state.json').read_text())
    return [
        asdict(Dataset('order_data', '订单数据', 'dataset/order_data.parquet', True,
                       state['order_rows'], state['order_mtime'], state['order_asof'], 'lock_time')),
        asdict(Dataset('assign_data', '下发线索', 'dataset/assign_data.csv', True,
                       state['assign_rows'], state['assign_mtime'], state['assign_asof'], 'Assign Time 年/月/日')),
    ]
"""


def make_repo(tmp_path: Path, recipe: str) -> Path:
    root = tmp_path / "service"
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/bin/python").symlink_to(sys.executable)
    (root / "dataset/updater").mkdir(parents=True)
    (root / "dataset/updater/update_all_datasets.py").write_text("# fixture\n", encoding="utf-8")
    (root / "dataset/updater/dataset_registry.py").write_text(REGISTRY, encoding="utf-8")
    (root / "state.json").write_text(
        json.dumps(
            {
                "order_rows": 100,
                "order_mtime": "2026-11-05T08:00:00",
                "order_asof": "2026-11-05T07:00:00",
                "assign_rows": 50,
                "assign_mtime": "2026-11-05T08:00:00",
                "assign_asof": "2026-11-05T06:00:00",
            }
        ),
        encoding="utf-8",
    )
    (root / "Makefile").write_text(
        "data-refresh-daily:\n" + textwrap.indent(recipe, "\t") + "\ndata-status:\n\t@echo data-status-ok\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
    return root


ADVANCE = (
    "python3 -c \"import json,pathlib; p=pathlib.Path('state.json'); d=json.loads(p.read_text()); "
    "d['order_rows']=101; d['order_asof']='2026-11-05T09:00:00'; p.write_text(json.dumps(d))\""
)


def test_success_records_new_data_and_status(tmp_path):
    root = make_repo(tmp_path, ADVANCE)
    record = production.run_job(root, timeout=30)
    assert record["status"] == "success"
    assert record["new_data"] is True
    assert record["latest_data_time"] == "2026-11-05T09:00:00"
    assert record["changed_datasets"] == ["order_data"]
    assert record["before"]["order_data"]["rows"] == 100
    assert record["after"]["order_data"]["rows"] == 101
    assert Path(record["record_path"]).exists()
    assert (root / "logs/production-jobs/latest.json").exists()
    latest = json.loads((root / "logs/production-jobs/latest.json").read_text())
    assert latest["status"] == "success"
    assert "data-status-ok" in Path(record["log_path"]).read_text(errors="replace")


def test_no_new_data_is_not_reported_as_failure(tmp_path):
    root = make_repo(tmp_path, "@true")
    record = production.run_job(root, timeout=30)
    assert record["status"] == "no_new_data"
    assert record["new_data"] is False
    assert record["latest_data_time"] == "2026-11-05T07:00:00"
    assert "未产生新数据" in record["summary"]


def test_failed_refresh_is_reported_and_status_still_runs(tmp_path):
    root = make_repo(tmp_path, "@exit 3")
    record = production.run_job(root, timeout=30)
    assert record["status"] == "failed"
    assert record["commands"][0]["returncode"] != 0
    assert record["commands"][1]["returncode"] == 0
    assert "data-status-ok" in Path(record["log_path"]).read_text(errors="replace")


def test_timeout_kills_the_process_group(tmp_path):
    root = make_repo(tmp_path, "@sleep 5")
    started = time.monotonic()
    record = production.run_job(root, timeout=1)
    assert record["status"] == "timeout"
    assert record["commands"][0]["returncode"] == 124
    assert time.monotonic() - started < 4


def test_linked_worktree_is_rejected_before_any_log_write(tmp_path):
    root = make_repo(tmp_path, ADVANCE)
    worktree = tmp_path / "ticket-worktree"
    subprocess.run(["git", "worktree", "add", "-q", str(worktree), "-b", "agent/test"], cwd=root, check=True)
    with pytest.raises(production.ProductionJobError, match="Ticket worktree"):
        production.verify_production_root(worktree)
    record = production.run_job(worktree, timeout=5)
    assert record["status"] == "failed"
    assert "Ticket worktree" in record["error"]
    assert not (worktree / "logs/production-jobs").exists()


def test_second_process_is_busy(tmp_path):
    root = make_repo(tmp_path, "@true")
    lock = root / "logs/production-jobs/data-refresh-daily.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl,time,sys; f=open(sys.argv[1],'a+'); fcntl.flock(f.fileno(),fcntl.LOCK_EX); print('locked',flush=True); time.sleep(20)",
            str(lock),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "locked"
        record = production.run_job(root, timeout=5)
        assert record["status"] == "busy"
        assert "正在执行" in record["error"]
    finally:
        holder.terminate()
        holder.wait(timeout=5)


def test_check_action_is_read_only(tmp_path, capsys):
    root = make_repo(tmp_path, ADVANCE)
    assert production.main(["check", "data-refresh-daily", "--repo-root", str(root)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"status": "ok", "job": "data-refresh-daily", "repo_root": str(root)}
    assert not (root / "logs").exists()


def test_unknown_job_is_refused(tmp_path, capsys):
    root = make_repo(tmp_path, ADVANCE)
    assert production.main(["check", "rm-rf", "--repo-root", str(root)]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "未登记的 job" in payload["error"]


def test_adapter_contract_carries_structured_job_result(tmp_path, monkeypatch):
    from jobs.adapter import run_job

    root = make_repo(tmp_path, ADVANCE)
    monkeypatch.setenv("PYTHONPATH", str(_PRJ_ROOT))
    config = {
        "data_refresh_daily": {
            "module": "dataset",
            "label": "fixture",
            "cwd": str(root),
            "argv_template": [
                "{python}", "-m", "jobs.production", "run", "data-refresh-daily",
                "--repo-root", str(root),
            ],
            "params": {},
            "summary": "json",
            "timeout_seconds": 60,
        }
    }
    result = run_job("data_refresh_daily", jobs_override=config)
    assert result["status"] == "ok"
    assert result["summary_json"]["status"] == "success"
    assert result["summary_json"]["new_data"] is True
    assert result["summary_json"]["latest_data_time"] == "2026-11-05T09:00:00"
