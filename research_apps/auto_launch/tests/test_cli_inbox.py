"""CLI inbox 测试"""
import sys, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "daily_run_sample.md"
CLI = "auto_launch/cli.py"


def test_cli_inbox_help():
    result = subprocess.run(
        [sys.executable, CLI, "inbox", "--help"],
        capture_output=True, text=True, cwd=Path(sys.path[0])
    )
    assert "inbox" in result.stdout or "Inbox" in result.stdout or result.returncode == 0
    print(f"[PASS] test_cli_inbox_help")


def test_cli_inbox_with_file():
    result = subprocess.run(
        [sys.executable, CLI, "inbox", "--input", str(FIXTURE), "--date", "2026-07-09"],
        capture_output=True, text=True, cwd=Path(sys.path[0])
    )
    assert "Kept" in result.stdout or "KEEP" in result.stdout or "Inbox Summary" in result.stdout
    print(f"[PASS] test_cli_inbox_with_file: exit={result.returncode}")


def test_cli_facts_help():
    result = subprocess.run(
        [sys.executable, CLI, "facts", "--help"],
        capture_output=True, text=True, cwd=Path(sys.path[0])
    )
    assert "facts" in result.stdout or result.returncode == 0
    print(f"[PASS] test_cli_facts_help")


def test_cli_facts_no_data():
    """事实库为空时，facts 不报错"""
    result = subprocess.run(
        [sys.executable, CLI, "facts", "--days", "1"],
        capture_output=True, text=True, cwd=Path(sys.path[0])
    )
    assert result.returncode == 0
    print(f"[PASS] test_cli_facts_no_data")


def test_cli_inbox_no_input_starts_interactive():
    """不带 --input 时进入交互模式（模拟 EOF 应优雅退出）"""
    result = subprocess.run(
        [sys.executable, CLI, "inbox", "--date", "2026-07-09"],
        capture_output=True, text=True, cwd=Path(sys.path[0]),
        input="/cancel\n", timeout=5,
    )
    assert "已取消" in result.stdout or "cancel" in result.stdout or result.returncode == 0
    print(f"[PASS] test_cli_inbox_no_input_starts_interactive")


if __name__ == "__main__":
    test_cli_inbox_help()
    test_cli_inbox_with_file()
    test_cli_facts_help()
    test_cli_facts_no_data()
    test_cli_inbox_no_input_starts_interactive()
    print("\n✅ 所有测试通过")
