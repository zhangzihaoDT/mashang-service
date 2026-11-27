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

def _parse_dates(series):
    import pandas as pd
    return pd.to_datetime(series, format="mixed", errors="coerce")

def describe_all():
    state = json.loads((Path(__file__).resolve().parents[2] / 'state.json').read_text())
    return [
        asdict(Dataset('order_data', '订单数据', 'dataset/order_data.parquet', True,
                       state['order_rows'], state['order_mtime'], state['order_asof'], 'lock_time')),
        asdict(Dataset('assign_data', '下发线索', 'dataset/assign_data.csv', True,
                       state['assign_rows'], state['assign_mtime'], state['assign_asof'], 'Assign Time 年/月/日')),
    ]
"""

WRITE_DATA = """
import hashlib
import json
import os
from pathlib import Path

import pandas as pd

state = json.loads(Path("state.json").read_text())
order_rows = state["order_rows"]
keys = pd.Series([str(i) for i in range(order_rows)])
order_time = pd.Timestamp(state["order_asof"])
output = Path("dataset/order_data.parquet")
orders = pd.DataFrame({
    "order_number": keys, "lock_time": order_time, "order_create_date": order_time,
    "product_name": "智己LS9", "series": "LS9", "order_type": "用户车",
    "approve_refund_time": pd.NaT, "intention_payment_time": pd.NaT, "intention_refund_time": pd.NaT,
    "deposit_payment_time": pd.NaT, "deposit_refund_time": pd.NaT,
    "buyer_identity_no": "x", "owner_identity_no": "x", "store_name": "fixture",
})
if not output.exists() or len(pd.read_parquet(output)) != order_rows:
    orders.to_parquet(output, index=False)
assign = Path("dataset/assign_data.csv")
assign_csv = pd.DataFrame({
    "Assign Time 年/月/日": pd.date_range(end=state["assign_asof"], periods=state["assign_rows"]),
    "下发线索数": 1,
}).to_csv(index=False)
if not assign.exists() or assign.read_text() != assign_csv:
    assign.write_text(assign_csv)
if journal := os.environ.get("MASHANG_REFRESH_JOURNAL"):
    with open(journal, "a") as stream:
        for key, path in [("order_data", output), ("assign_data", assign)]:
            step = {"dataset": key, "state": "finished", "returncode": 0,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            print(json.dumps(step), file=stream)
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
    (root / "write_data.py").write_text(WRITE_DATA)
    subprocess.run([sys.executable, "write_data.py"], cwd=root, check=True)
    (root / "Makefile").write_text(
        "data-refresh-daily:\n" + textwrap.indent(recipe, "\t")
        + "\n\t@.venv/bin/python write_data.py\ndata-status:\n\t@echo data-status-ok\n",
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
    assert record["contract_version"] == 2
    assert record["outcome"] == "all_succeeded"
    assert record["dataset_results"]["order_data"]["publish_status"] == "published"
    assert record["dataset_results"]["assign_data"]["publish_status"] == "unchanged"
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


@pytest.mark.parametrize("config_rows, expected", [(11, "success"), (0, "verification_failed")])
def test_config_job_runs_only_config_target_and_verifies_only_config(tmp_path, monkeypatch, config_rows, expected):
    root = make_repo(tmp_path, "@false")
    with (root / "Makefile").open("a", encoding="utf-8") as handle:
        handle.write("data-refresh-config-attribute:\n\t@echo config-only\n")
    states = iter([
        {"config_attribute": {"exists": True, "rows": 10, "file_mtime": "before"}, "order_data": {"rows": 100}},
        {"config_attribute": {"exists": True, "rows": config_rows, "file_mtime": "after"}, "order_data": {"rows": 99}},
    ])
    monkeypatch.setattr(production, "dataset_snapshot", lambda _: next(states))
    result = production.run_job(root, job="data-refresh-config-attribute", timeout=30)
    assert result["status"] == expected
    assert set(result["before"]) == set(result["after"]) == {"config_attribute"}
    assert [command["argv"][-1] for command in result["commands"]] == ["data-refresh-config-attribute", "data-status"]


def managed_repo(tmp_path, monkeypatch, outcomes):
    """Run the actual scoped updater dispatcher with local-only child processes."""
    root = make_repo(tmp_path, "@true")
    updater = root / "dataset/updater"
    for name in ("update_all_datasets.py", "dataset_registry.py"):
        (updater / name).write_bytes((_PRJ_ROOT / "dataset/updater" / name).read_bytes())
    date = "2026-11-05 10:00:00"
    for name, basename in (
        ("order_data_to_parquet", "order_data.parquet"),
        ("assign_data_to_csv", "assign_data.csv"),
        ("lock_attribution_data_to_parquet", "lock_attribution_data.parquet"),
    ):
        action = outcomes.get(name, "raise SystemExit(9)")
        (updater / f"{name}.py").write_text(
            f"import sys,time\nfrom pathlib import Path\nimport pandas as pd\n"
            f"p=Path('dataset/{basename}')\nnew_time={date!r}\n{action}\n"
        )
    (root / "Makefile").write_text(
        "export MOBILE := 1\n"
        "data-refresh-daily:\n\t@.venv/bin/python dataset/updater/update_all_datasets.py --mobile --scope daily\n"
        "data-refresh-order-data:\n\t@.venv/bin/python dataset/updater/update_all_datasets.py --mobile --scope order_data\n"
        "data-refresh-lock-attribution:\n\t@.venv/bin/python dataset/updater/update_all_datasets.py --mobile --scope lock_attribution\n"
        "data-status:\n\t@.venv/bin/python dataset/updater/update_all_datasets.py --status-only\n"
    )
    monkeypatch.delenv("MASHANG_JOB_RUN_ID", raising=False)
    monkeypatch.setenv("STORE_INFO_CSV", str(root / "dataset/store_info.csv"))
    return root


UPDATE_ORDER = """df=pd.read_parquet(p)
df.loc[0,'lock_time']=pd.Timestamp(new_time)
df.to_parquet(p,index=False)"""


def test_daily_actual_dispatch_reports_partial_write(tmp_path, monkeypatch):
    root = managed_repo(tmp_path, monkeypatch, {"order_data_to_parquet": UPDATE_ORDER})
    record = production.run_job(root, run_id="fixture-daily-partial")
    assert record["status"] == "failed" and record["outcome"] == "partial_write"
    assert record["dataset_results"]["order_data"]["execution_status"] == "succeeded"
    assert record["dataset_results"]["order_data"]["publish_status"] == "published"
    assert record["dataset_results"]["assign_data"]["execution_status"] == "failed"
    assert record["dataset_results"]["assign_data"]["publish_status"] == "unchanged"
    assert production.run_job(root, run_id=record["run_id"]) == record


def test_order_job_is_single_table_and_can_detect_corruption(tmp_path, monkeypatch):
    root = managed_repo(tmp_path, monkeypatch, {"order_data_to_parquet": UPDATE_ORDER})
    prior = (root / "dataset/assign_data.csv").read_bytes()
    options = {"job": "data-refresh-order-data"}
    result = production.run_job(root, run_id="fixture-order-update", **options)
    assert result["status"] == "success" and result["outcome"] == "all_succeeded"
    assert set(result["before"]) == set(result["after"]) == {"order_data"}
    assert result["after"]["order_data"]["validated_cutoff"] == "2026-11-05T10:00:00"
    assert (root / "dataset/assign_data.csv").read_bytes() == prior

    (root / "dataset/updater/order_data_to_parquet.py").write_text(
        "from pathlib import Path\nPath('dataset/order_data.parquet').write_bytes(b'corrupt')\n"
    )
    corrupt = production.run_job(root, run_id="fixture-order-corrupt", **options)
    assert corrupt["status"] == "verification_failed"
    assert corrupt["dataset_results"]["order_data"]["publish_status"] == "invalid"
    assert (root / "dataset/assign_data.csv").read_bytes() == prior


def test_attribution_job_reports_in_place_corrections_and_unchanged_replays(tmp_path, monkeypatch):
    root = managed_repo(tmp_path, monkeypatch, {"lock_attribution_data_to_parquet": """
df=pd.read_parquet(p)
df['channel']='corrected'
df.to_parquet(p,index=False)
"""})
    subprocess.run([sys.executable, "-c", """
import pandas as pd
pd.DataFrame({
    'lc_user_phone_md5': ['fixture'],
    'lc_main_code': ['lead'],
    'lc_order_lock_time_min': [pd.Timestamp('2026-11-02')],
    'channel': ['original'],
}).to_parquet('dataset/lock_attribution_data.parquet',index=False)
"""], cwd=root, check=True)
    job = "data-refresh-lock-attribution"
    order_hash = production.inspect_dataset("order_data", root / "dataset/order_data.parquet")["sha256"]
    corrected = production.run_job(root, job=job, run_id="fixture-attribution-corrected")
    assert corrected["status"] == "success" and corrected["outcome"] == "updated_existing"
    assert corrected["new_data"] is False
    assert set(corrected["dataset_results"]) == {"lock_attribution"}
    assert corrected["dataset_results"]["lock_attribution"]["publish_status"] == "published"
    same = production.run_job(root, job=job, run_id="fixture-attribution-same-data")
    assert same["status"] == same["outcome"] == "no_new_data"
    assert production.inspect_dataset("order_data", root / "dataset/order_data.parquet")["sha256"] == order_hash

def test_recover_interrupted_runner_without_repeating_refresh(tmp_path, monkeypatch):
    order_action = UPDATE_ORDER + "\nPath('ran').open('a').write('once\\n')\n"
    root = managed_repo(tmp_path, monkeypatch, {
        "order_data_to_parquet": order_action,
        "assign_data_to_csv": "Path('waiting').touch(); time.sleep(1.5)",
    })
    run_id = "fixture-crash-recovery"
    env = {**os.environ, "PYTHONPATH": str(_PRJ_ROOT)}
    runner = subprocess.Popen(
        [sys.executable, "-B", "-m", "jobs.production", "run", "--repo-root", str(root), "--run-id", run_id],
        cwd=root, env=env, stdout=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 12
        while not (root / "waiting").exists() and time.monotonic() < deadline:
            time.sleep(0.03)
        assert (root / "waiting").exists()
        runner.kill()
        runner.wait(timeout=5)
        # Make keeps the production lock until the updater returns, even after the runner dies.
        assert production.run_record(root, production.JOB_ID, run_id, recover=True)["status"] == "running"
        while time.monotonic() < deadline:
            recovered = production.run_record(root, production.JOB_ID, run_id, recover=True)
            if recovered["status"] != "running":
                break
            time.sleep(0.05)
        assert recovered["status"] == "success"
        assert recovered["recovered"] is True
        assert recovered["dataset_results"]["order_data"]["publish_status"] == "published"
        assert recovered["dataset_results"]["assign_data"]["publish_status"] == "unchanged"
        assert production.run_job(root, run_id=run_id) == recovered
        assert (root / "ran").read_text() == "once\n"
    finally:
        if runner.poll() is None:
            runner.kill()
            runner.wait(timeout=5)
