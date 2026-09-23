"""presale_metrics_to_feishu shim 的委托与默认代际解析测试。

预售监控实现已收敛到 runtime_scripts/vehicle_sales_monitor.py；
本 shim 只负责注入 --force-phase / --phase presale 并委托。
"""

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


def _value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def test_inject_adds_force_phase_and_presale_phase(module):
    argv = module._inject(["--series", "CM3", "--dry-run"])
    assert "--force-phase" in argv
    assert _value(argv, "--phase") == "presale"
    assert _value(argv, "--series") == "CM3"
    assert "--dry-run" in argv


def test_inject_keeps_explicit_phase(module):
    argv = module._inject(["--series", "CM3", "--phase", "presale"])
    assert argv.count("--phase") == 1


def test_inject_resolves_default_presale_series(monkeypatch, module):
    monkeypatch.setattr(module, "load_business_definition", lambda: {})
    monkeypatch.setattr(
        module, "detect_active", lambda bdef, today, phases=None: [{"generation": "CM3"}]
    )
    argv = module._inject([])
    assert _value(argv, "--series") == "CM3"


def test_inject_default_series_uses_as_of(monkeypatch, module):
    seen = {}
    monkeypatch.setattr(module, "load_business_definition", lambda: {})

    def fake_detect(bdef, today, phases=None):
        seen["today"] = today
        return [{"generation": "CM2"}]

    monkeypatch.setattr(module, "detect_active", fake_detect)
    argv = module._inject(["--as-of", "2025-08-15"])
    assert _value(argv, "--series") == "CM2"
    assert str(seen["today"].date()) == "2025-08-15"


def test_inject_no_presale_returns_none(monkeypatch, module, capsys):
    monkeypatch.setattr(module, "load_business_definition", lambda: {})
    monkeypatch.setattr(module, "detect_active", lambda bdef, today, phases=None: [])
    assert module._inject([]) is None
    assert "无 presale 代际" in capsys.readouterr().out


def test_main_delegates_augmented_argv(monkeypatch, module):
    captured: dict = {}

    class FakeRunner:
        def main(self):
            captured["argv"] = list(sys.argv[1:])
            return 7

    monkeypatch.setattr(module, "_load_runner", lambda: FakeRunner())
    monkeypatch.setattr(sys, "argv", ["presale_metrics_to_feishu.py", "--series", "CM3"])

    rc = module.main()

    assert rc == 7
    assert "--force-phase" in captured["argv"]
    assert _value(captured["argv"], "--phase") == "presale"
    assert _value(captured["argv"], "--series") == "CM3"


def test_main_short_circuits_without_presale(monkeypatch, module, capsys):
    monkeypatch.setattr(module, "load_business_definition", lambda: {})
    monkeypatch.setattr(module, "detect_active", lambda bdef, today, phases=None: [])
    monkeypatch.setattr(module, "_load_runner", lambda: SimpleNamespace(main=pytest.fail))
    monkeypatch.setattr(sys, "argv", ["presale_metrics_to_feishu.py"])

    assert module.main() == 0
    assert "无 presale 代际" in capsys.readouterr().out
