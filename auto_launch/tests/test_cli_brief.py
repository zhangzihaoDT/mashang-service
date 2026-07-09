"""CLI brief 测试"""
import sys, subprocess, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CLI = "auto_launch/cli.py"


def test_cli_brief_help():
    result = subprocess.run(
        [sys.executable, CLI, "brief", "--help"],
        capture_output=True, text=True, cwd=Path(sys.path[0])
    )
    assert result.returncode == 0
    print(f"[PASS] test_cli_brief_help")


def test_cli_brief_default():
    """默认 --days 1 不应报错"""
    result = subprocess.run(
        [sys.executable, CLI, "brief"],
        capture_output=True, text=True, cwd=Path(sys.path[0])
    )
    assert result.returncode == 0
    assert "今日最值得关注" in result.stdout or "无匹配数据" in result.stdout
    print(f"[PASS] test_cli_brief_default")


def test_cli_brief_with_brand():
    result = subprocess.run(
        [sys.executable, CLI, "brief", "--brand", "智己", "--days", "7"],
        capture_output=True, text=True, cwd=Path(sys.path[0])
    )
    assert result.returncode == 0
    print(f"[PASS] test_cli_brief_with_brand")


def test_cli_brief_output_file():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "brief.md"
        result = subprocess.run(
            [sys.executable, CLI, "brief", "--days", "7", "--output", str(out)],
            capture_output=True, text=True, cwd=Path(sys.path[0])
        )
        assert result.returncode == 0
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert len(content) > 50
    print(f"[PASS] test_cli_brief_output_file")


def test_cli_brief_since_until():
    result = subprocess.run(
        [sys.executable, CLI, "brief", "--since", "2026-07-01", "--until", "2026-07-09"],
        capture_output=True, text=True, cwd=Path(sys.path[0])
    )
    assert result.returncode == 0
    print(f"[PASS] test_cli_brief_since_until")


if __name__ == "__main__":
    test_cli_brief_help()
    test_cli_brief_default()
    test_cli_brief_with_brand()
    test_cli_brief_output_file()
    test_cli_brief_since_until()
    print("\n✅ 所有测试通过")
