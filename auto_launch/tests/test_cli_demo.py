"""CLI demo 测试"""
import sys, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CLI = "auto_launch/cli.py"


def test_cli_demo_help():
    r = subprocess.run([sys.executable, CLI, "demo", "--help"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "reset-store" in r.stdout
    print("[PASS] test_cli_demo_help")


def test_cli_demo_reset_store():
    r = subprocess.run([sys.executable, CLI, "demo", "--reset-store"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "demo" in r.stdout
    assert "demo_dir" in r.stdout
    assert "manifest" in r.stdout
    print("[PASS] test_cli_demo_reset_store")


def test_cli_demo_creates_all_outputs():
    r = subprocess.run([sys.executable, CLI, "demo", "--reset-store"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    lines = r.stdout.strip().split("\n")
    assert len(lines) >= 3
    for line in lines[1:]:
        if ":" in line:
            parts = line.split(":", 1)
            path = parts[1].strip()
            if path.startswith("/"):
                p = Path(path)
                assert p.exists(), f"Output file missing: {path}"
    print("[PASS] test_cli_demo_creates_all_outputs")


if __name__ == "__main__":
    test_cli_demo_help()
    test_cli_demo_reset_store()
    test_cli_demo_creates_all_outputs()
    print("\n✅ 所有 CLI demo 测试通过")
