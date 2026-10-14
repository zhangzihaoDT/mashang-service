from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utility_scripts.external_daily_jobs import ExternalDailyJobs


def config(tmp_path, **updates):
    job = {'id': 'aksignal-daily', 'enabled': True, 'argv': ['/fake/python', '-m', 'src.daily_schedule', '--tick', '--offline'],
           'cwd': str(tmp_path)}
    job.update(updates)
    path = tmp_path / 'external.json'
    path.write_text(json.dumps({'schema_version': 1, 'jobs': [job]}))
    return str(path)


def test_default_and_disabled_no_spawn(tmp_path, monkeypatch):
    monkeypatch.delenv('SCHEDULER_EXTERNAL_JOBS_CONFIG', raising=False)
    monkeypatch.setattr('utility_scripts.external_daily_jobs.subprocess.Popen',
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError('spawn')))
    hooks = ExternalDailyJobs()
    hooks.tick(print)
    hooks.tick(print, config_path=config(tmp_path, enabled=False))


def test_hook_nonblocking_and_no_duplicate_live_controller(tmp_path, monkeypatch):
    calls = []
    class Child:
        def poll(self):
            return None
        def wait(self):
            raise AssertionError('blocking wait')
    monkeypatch.setattr('utility_scripts.external_daily_jobs.subprocess.Popen',
                        lambda *a, **kw: calls.append((a, kw)) or Child())
    hooks = ExternalDailyJobs()
    path = config(tmp_path)
    hooks.tick(print, config_path=path)
    hooks.tick(print, config_path=path)
    assert len(calls) == 1
    assert calls[0][1]['start_new_session'] is True


def test_invalid_config_is_soft_failure_and_dry_run_no_spawn(tmp_path, monkeypatch):
    messages = []
    hooks = ExternalDailyJobs()
    hooks.tick(messages.append, config_path=str(tmp_path / 'missing'))
    assert 'ERROR' in messages[-1]
    monkeypatch.setattr('utility_scripts.external_daily_jobs.subprocess.Popen',
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError('spawn')))
    hooks.tick(messages.append, config_path=config(tmp_path), dry_run=True)
    assert '[dry-run]' in messages[-1]


def load_scheduler():
    spec = importlib.util.spec_from_file_location('scheduler_p0', ROOT / 'utility_scripts/sales_scheduler.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0830_hook_does_not_modify_0850_daily(tmp_path, monkeypatch):
    scheduler = load_scheduler()
    definition = {'time_periods': {'CM3': {'start': '2026-09-10', 'end': '2026-09-23'}}}
    assert scheduler.due_actions(datetime(2026, 10, 14, 8, 30), definition) == []
    assert scheduler.due_actions(datetime(2026, 10, 14, 8, 50), definition) == [
        'refresh_daily', 'dataset_validate', 'daily_observation_sync', 'monitor']
    events = []
    monkeypatch.setattr(scheduler._EXTERNAL_DAILY_JOBS, 'tick', lambda *a, **k: events.append('external'))
    monkeypatch.setattr(scheduler, '_dispatch', lambda action, *a, **k: events.append(action) or 0)
    loader = SimpleNamespace(reload=lambda now: definition)
    scheduler.run_tick(datetime(2026, 10, 14, 8, 50), loader, SimpleNamespace(dry_run=True), set())
    assert events == ['external', 'refresh_daily', 'dataset_validate', 'daily_observation_sync', 'monitor']


def test_malformed_registry_cannot_interrupt_daily(tmp_path):
    for value in [[], {'schema_version': 1, 'jobs': [None]}, {'schema_version': 1, 'jobs': [{'id': None}]}]:
        path = tmp_path / 'bad.json'
        path.write_text(json.dumps(value))
        messages = []
        ExternalDailyJobs().tick(messages.append, config_path=str(path))
        assert 'ERROR' in messages[-1]
