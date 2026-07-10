"""CLI report --type daily-brief 测试"""
import sys, subprocess, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CLI = "auto_launch/cli.py"


def test_report_daily_brief_help():
    r = subprocess.run([sys.executable, CLI, "report", "--help"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "brand-daily" in r.stdout
    assert "daily-brief" in r.stdout
    print("[PASS] test_report_daily_brief_help")


def test_report_daily_brief_default():
    r = subprocess.run([sys.executable, CLI, "report", "--type", "daily-brief"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "简报" in r.stdout or "facts" in r.stdout
    print(f"[PASS] test_report_daily_brief_default")


def test_report_daily_brief_with_brand():
    r = subprocess.run([sys.executable, CLI, "report", "--type", "daily-brief", "--brand", "智己"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    print(f"[PASS] test_report_daily_brief_with_brand")


def test_report_daily_brief_output_file():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "brief.md"
        r = subprocess.run([sys.executable, CLI, "report", "--type", "daily-brief",
                            "--days", "90", "--output", str(out)],
                           capture_output=True, text=True, cwd=Path(sys.path[0]))
        assert r.returncode == 0
        assert out.exists()
    print(f"[PASS] test_report_daily_brief_output_file")


def test_report_daily_brief_since_until():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "brief.md"
        r = subprocess.run([sys.executable, CLI, "report", "--type", "daily-brief",
                            "--since", "2026-01-01T00:00:00", "--output", str(out)],
                           capture_output=True, text=True, cwd=Path(sys.path[0]))
        assert r.returncode == 0
    print(f"[PASS] test_report_daily_brief_since_until")


if __name__ == "__main__":
    test_report_daily_brief_help()
    test_report_daily_brief_default()
    test_report_daily_brief_with_brand()
    test_report_daily_brief_output_file()
    test_report_daily_brief_since_until()
    print("\n✅ 所有 report daily-brief 测试通过")
