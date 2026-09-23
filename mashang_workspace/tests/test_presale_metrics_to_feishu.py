"""指定代际预售小订快照的 freshness gate 测试。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


_WS_DIR = Path(__file__).resolve().parents[1]
_PRJ_DIR = _WS_DIR.parent

for _path in (str(_PRJ_DIR), str(_WS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


@pytest.fixture
def module():
    path = _WS_DIR / "research_scripts" / "presale_metrics_to_feishu.py"
    spec = importlib.util.spec_from_file_location("presale_metrics_to_feishu_test", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载脚本: {path}")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _prepare(monkeypatch, module, fresh: bool = True):
    monkeypatch.setattr(module, "load_business_definition", lambda: {})
    monkeypatch.setattr(module.freshness, "check", lambda **_: {"fresh": fresh, "reason": "test stale"})
    monkeypatch.setattr(module, "load_order", lambda: object())
    monkeypatch.setattr(module, "apply_series_group_logic", lambda df, _: df)
    monkeypatch.setattr(module, "compute", lambda *_: {"generation": "CM3"})
    monkeypatch.setattr(module, "build_card", lambda metrics, show_notes: {"metrics": metrics})


def _invoke(monkeypatch, module, *args):
    monkeypatch.setattr(sys, "argv", ["presale_metrics_to_feishu.py", *args])
    return module.main()


def test_fresh_snapshot_sends(monkeypatch, module):
    _prepare(monkeypatch, module, fresh=True)
    sent = []
    monkeypatch.setattr(module, "notify", lambda **kwargs: sent.append(kwargs) or SimpleNamespace(ok=True))

    rc = _invoke(monkeypatch, module, "--series", "CM3")

    assert rc == 0
    assert len(sent) == 1


def test_stale_snapshot_does_not_send(monkeypatch, module, capsys):
    _prepare(monkeypatch, module, fresh=False)
    monkeypatch.setattr(module, "notify", lambda **_: pytest.fail("stale snapshot must not send"))

    rc = _invoke(monkeypatch, module, "--series", "CM3")

    assert rc == 2
    assert "跳过飞书推送" in capsys.readouterr().out


def test_stale_dry_run_previews_without_sending(monkeypatch, module, capsys):
    _prepare(monkeypatch, module, fresh=False)
    monkeypatch.setattr(module, "notify", lambda **_: pytest.fail("dry-run must not send"))

    rc = _invoke(monkeypatch, module, "--series", "CM3", "--dry-run")

    output = capsys.readouterr().out
    assert rc == 0
    assert "数据 stale" in output
    assert '"generation": "CM3"' in output


def test_as_of_skips_live_freshness_gate(monkeypatch, module):
    _prepare(monkeypatch, module, fresh=False)
    monkeypatch.setattr(module.freshness, "check", lambda **_: pytest.fail("historical run must skip gate"))
    sent = []
    monkeypatch.setattr(module, "notify", lambda **kwargs: sent.append(kwargs) or SimpleNamespace(ok=True))

    rc = _invoke(monkeypatch, module, "--series", "CM3", "--as-of", "2026-09-23")

    assert rc == 0
    assert len(sent) == 1


def test_allow_stale_sends_with_warning(monkeypatch, module, capsys):
    _prepare(monkeypatch, module, fresh=False)
    sent = []
    monkeypatch.setattr(module, "notify", lambda **kwargs: sent.append(kwargs) or SimpleNamespace(ok=True))

    rc = _invoke(monkeypatch, module, "--series", "CM3", "--allow-stale")

    assert rc == 0
    assert len(sent) == 1
    assert "--allow-stale" in capsys.readouterr().out
