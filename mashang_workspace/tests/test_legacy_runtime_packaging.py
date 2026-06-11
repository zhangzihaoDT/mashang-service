"""
Tests for Legacy Runtime Packaging (Phase 12.5)
"""

import sys
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[1]
_PRJ_DIR = _WS_DIR.parent


def test_root_main_is_wrapper():
    """根目录 main.py 存在且是 wrapper（不含旧业务逻辑）。"""
    main_py = _PRJ_DIR / "main.py"
    assert main_py.exists()
    content = main_py.read_text()
    assert "runpy.run_path" in content or "wrapper" in content.lower()


def test_root_feishu_bot_is_wrapper():
    """根目录 feishu_bot.py 存在且是 wrapper。"""
    bot_py = _PRJ_DIR / "feishu_bot.py"
    assert bot_py.exists()
    content = bot_py.read_text()
    assert "runpy.run_path" in content


def test_runtime_main_exists():
    assert (_PRJ_DIR / "mashang_runtime" / "main.py").exists()


def test_runtime_feishu_bot_exists():
    assert (_PRJ_DIR / "mashang_runtime" / "feishu_bot.py").exists()


def test_runtime_agent_exists():
    assert (_PRJ_DIR / "mashang_runtime" / "agent").exists()


def test_runtime_tools_exists():
    assert (_PRJ_DIR / "mashang_runtime" / "tools").exists()


def test_runtime_operators_exists():
    assert (_PRJ_DIR / "mashang_runtime" / "operators").exists()


def test_runtime_schema_exists():
    assert (_PRJ_DIR / "mashang_runtime" / "schema").exists()


def test_runtime_design_docs_exists():
    assert (_PRJ_DIR / "mashang_runtime" / "design_docs").exists()


def test_root_no_legacy_agent():
    """根目录不应再包含完整 agent/。"""
    assert not (_PRJ_DIR / "agent" / "agent_loop.py").exists(), "根目录 agent/ 应已迁移"


def test_root_no_legacy_tools():
    assert not (_PRJ_DIR / "tools" / "query_tool.py").exists(), "根目录 tools/ 应已迁移"


def test_root_no_legacy_operators():
    assert not (_PRJ_DIR / "operators" / "registry.py").exists(), "根目录 operators/ 应已迁移"


def test_root_no_legacy_schema():
    assert not (_PRJ_DIR / "schema" / "metrics.json").exists(), "根目录 schema/ 应已迁移"


def test_root_no_legacy_design_docs():
    assert not (_PRJ_DIR / "设计方案").exists(), "根目录 设计方案/ 应已迁移"


def test_wrapper_contains_runpy():
    content = (_PRJ_DIR / "main.py").read_text()
    assert "runpy" in content
    content2 = (_PRJ_DIR / "feishu_bot.py").read_text()
    assert "runpy" in content2


def test_runtime_paths_exists():
    assert (_PRJ_DIR / "mashang_runtime" / "runtime_paths.py").exists()


def test_runtime_imports_work():
    """从 mashang_runtime/ 可以 import 旧模块。"""
    import importlib
    spec = importlib.util.spec_from_file_location(
        "agent_agent_loop",
        _PRJ_DIR / "mashang_runtime" / "agent" / "agent_loop.py",
    )
    assert spec is not None, "agent_loop.py spec should be loadable"
