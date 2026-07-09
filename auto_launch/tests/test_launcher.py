"""launcher 测试 — 使用 monkeypatch mock input()"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _inputs(sequence: list):
    """Return a list of values the mock will cycle through."""
    it = iter(sequence)

    def mock_input(prompt=""):
        # print(prompt, end="", file=sys.stderr)  # enable for debugging
        return next(it)

    return mock_input


def test_menu_render_exit_6(monkeypatch):
    """Select 6 to exit immediately."""
    from auto_launch.src.launcher import run_launcher
    monkeypatch.setattr("builtins.input", _inputs(["6"]))
    run_launcher()


def test_exit_via_q(monkeypatch):
    """q also exits."""
    from auto_launch.src.launcher import run_launcher
    monkeypatch.setattr("builtins.input", _inputs(["q"]))
    run_launcher()


def test_choice_1_cancel(monkeypatch):
    """Select 1 then /cancel."""
    from auto_launch.src.launcher import run_launcher
    monkeypatch.setattr("builtins.input", _inputs(["1", "2026-07-09", "/cancel", "6"]))
    run_launcher()


def test_choice_1_daily_run(monkeypatch):
    """Select 1, paste text, /done, y for brief, then exit."""
    from auto_launch.src.launcher import run_launcher
    daily = "## 智己 LS6 权益调整\n\n- 品牌: 智己\n- 车型: LS6\n- 事件类型: 权益调整\n- 时间: 2026-07-09\n- 来源: immotors.com\n- 信源等级: tier_1_official\n"
    monkeypatch.setattr("builtins.input", _inputs([
        "1", "2026-07-09", daily, "/done", "y", "6",
    ]))
    run_launcher()


def test_choice_1_writes_facts(monkeypatch):
    """After choice 1, facts should be in the store."""
    from auto_launch.src.fact_store import FactStore
    from auto_launch.src.launcher import run_launcher
    daily = "## 理想 L6 上市\n\n- 品牌: 理想\n- 车型: L6\n- 事件类型: 上市\n- 时间: 2026-07-09\n- 来源: lixiang.com\n- 信源等级: tier_1_official\n"
    monkeypatch.setattr("builtins.input", _inputs([
        "1", "2026-07-09", daily, "/done", "y", "6",
    ]))
    run_launcher()
    store = FactStore()
    facts = store.query(brand="理想", days=90, limit=10)
    assert any(f["brand"] == "理想" and f["event_type"] == "上市" for f in facts)


def test_choice_1_generates_brief_file(monkeypatch):
    """Brief file should be written to outputs/briefs/{date}.md."""
    from auto_launch.src.launcher import run_launcher
    daily = "## 小米 SU7 交付\n\n- 品牌: 小米\n- 车型: SU7\n- 事件类型: 交付数据\n- 时间: 2026-07-09\n- 来源: xiaomiev.com\n- 信源等级: tier_1_official\n"
    monkeypatch.setattr("builtins.input", _inputs([
        "1", "2026-07-09", daily, "/done", "y", "6",
    ]))
    run_launcher()
    brief_path = Path(__file__).resolve().parents[2] / "auto_launch" / "outputs" / "briefs" / "2026-07-09.md"
    assert brief_path.exists()
    assert len(brief_path.read_text(encoding="utf-8")) > 50


def test_choice_2_not_live(monkeypatch):
    """Select 2 with live=N — no real API call."""
    from auto_launch.src.launcher import run_launcher
    monkeypatch.setattr("builtins.input", _inputs([
        "2", "看看极氪最近7天", "2026-07-09", "n", "6",
    ]))
    run_launcher()


def test_choice_3_view_facts(monkeypatch):
    """Select 3 to view facts — doesn't crash."""
    from auto_launch.src.launcher import run_launcher
    monkeypatch.setattr("builtins.input", _inputs([
        "3", "7", "", "6",
    ]))
    run_launcher()


def test_choice_4_brief(monkeypatch):
    """Select 4 — generates brief from existing facts, answers 'n' to file write."""
    from auto_launch.src.launcher import run_launcher
    monkeypatch.setattr("builtins.input", _inputs([
        "4", "90", "", "n", "6",
    ]))
    run_launcher()


def test_choice_5_inspect(monkeypatch):
    """Select 5 — renders outputs inspect."""
    from auto_launch.src.launcher import run_launcher
    monkeypatch.setattr("builtins.input", _inputs([
        "5", "6",
    ]))
    run_launcher()


def test_invalid_choice(monkeypatch):
    """Invalid choice shows error and returns to menu."""
    from auto_launch.src.launcher import run_launcher
    monkeypatch.setattr("builtins.input", _inputs([
        "0", "6",
    ]))
    run_launcher()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
