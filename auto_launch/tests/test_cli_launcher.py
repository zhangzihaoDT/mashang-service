"""CLI launch / start 测试"""
import sys, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CLI = "auto_launch/cli.py"


def test_cli_launch_help():
    """launch 不需要 --help，验证它作为 subcommand 可识别"""
    r = subprocess.run([sys.executable, CLI, "--help"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "launch" in r.stdout
    assert "start" in r.stdout
    print("[PASS] test_cli_launch_help")


def test_cli_start_help():
    r = subprocess.run([sys.executable, CLI, "--help"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "start" in r.stdout
    print("[PASS] test_cli_start_help")


def test_cli_launch_exit_via_6():
    """Launch and exit via option 6."""
    r = subprocess.run(
        [sys.executable, CLI, "launch"],
        capture_output=True, text=True, cwd=Path(sys.path[0]),
        input="6\n", timeout=5,
    )
    assert r.returncode == 0
    assert "Auto Launch" in r.stdout
    assert "再见" in r.stdout
    print("[PASS] test_cli_launch_exit_via_6")


def test_cli_launch_exit_via_q():
    """Launch and exit via q."""
    r = subprocess.run(
        [sys.executable, CLI, "launch"],
        capture_output=True, text=True, cwd=Path(sys.path[0]),
        input="q\n", timeout=5,
    )
    assert r.returncode == 0
    assert "再见" in r.stdout
    print("[PASS] test_cli_launch_exit_via_q")


def test_cli_start_alias():
    """start is an alias for launch."""
    r = subprocess.run(
        [sys.executable, CLI, "start"],
        capture_output=True, text=True, cwd=Path(sys.path[0]),
        input="6\n", timeout=5,
    )
    assert r.returncode == 0
    assert "Auto Launch" in r.stdout
    print("[PASS] test_cli_start_alias")


def test_cli_launch_choice_3():
    """Select option 3 (view facts) then exit."""
    r = subprocess.run(
        [sys.executable, CLI, "launch"],
        capture_output=True, text=True, cwd=Path(sys.path[0]),
        input="3\n7\n\n6\n", timeout=5,
    )
    assert r.returncode == 0
    print("[PASS] test_cli_launch_choice_3")


def test_cli_launch_choice_5():
    """Select option 5 (outputs inspect) then exit."""
    r = subprocess.run(
        [sys.executable, CLI, "launch"],
        capture_output=True, text=True, cwd=Path(sys.path[0]),
        input="5\n6\n", timeout=5,
    )
    assert r.returncode == 0
    assert "Outputs Inspection Report" in r.stdout or "Runs" in r.stdout
    print("[PASS] test_cli_launch_choice_5")


if __name__ == "__main__":
    test_cli_launch_help()
    test_cli_start_help()
    test_cli_launch_exit_via_6()
    test_cli_launch_exit_via_q()
    test_cli_start_alias()
    test_cli_launch_choice_3()
    test_cli_launch_choice_5()
    print("\n✅ 所有 CLI launcher 测试通过")
