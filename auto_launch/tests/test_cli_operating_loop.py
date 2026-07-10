"""CLI run-day / replay / timeline / source-audit 测试"""
import sys, subprocess, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CLI = "auto_launch/cli.py"
FIXTURES = str(Path(__file__).resolve().parent / "fixtures" / "daily_runs")


def test_cli_run_day_help():
    r = subprocess.run([sys.executable, CLI, "run-day", "--help"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    print("[PASS] test_cli_run_day_help")


def test_cli_run_day_dry_run():
    r = subprocess.run([sys.executable, CLI, "run-day", "--brand", "智己", "--date", "2026-07-09"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "run-day" in r.stdout
    assert "source_audit" in r.stdout
    print(f"[PASS] test_cli_run_day_dry_run")


def test_cli_replay_fixtures():
    r = subprocess.run([sys.executable, CLI, "replay", "--input-dir", FIXTURES, "--reset-store"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "days" in r.stdout or "raw" in r.stdout
    print(f"[PASS] test_cli_replay_fixtures")


def test_cli_timeline_help():
    r = subprocess.run([sys.executable, CLI, "timeline", "--help"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    print("[PASS] test_cli_timeline_help")


def test_cli_timeline_default():
    r = subprocess.run([sys.executable, CLI, "timeline", "--days", "30"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "事件时间线" in r.stdout or "无匹配数据" in r.stdout
    print(f"[PASS] test_cli_timeline_default")


def test_cli_timeline_with_event_type():
    r = subprocess.run([sys.executable, CLI, "timeline", "--event-type", "权益调整", "--days", "30"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    print(f"[PASS] test_cli_timeline_with_event_type")


def test_cli_timeline_output():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "tl.md"
        r = subprocess.run([sys.executable, CLI, "timeline", "--days", "30", "--output", str(out)],
                           capture_output=True, text=True, cwd=Path(sys.path[0]))
        assert r.returncode == 0
        assert out.exists()
    print(f"[PASS] test_cli_timeline_output")


if __name__ == "__main__":
    test_cli_run_day_help()
    test_cli_run_day_dry_run()
    test_cli_replay_fixtures()
    test_cli_timeline_help()
    test_cli_timeline_default()
    test_cli_timeline_with_event_type()
    test_cli_timeline_output()
    print("\n✅ 所有测试通过")
