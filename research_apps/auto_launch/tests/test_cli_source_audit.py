"""CLI source-audit 测试"""
import sys, subprocess, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CLI = "auto_launch/cli.py"


def test_cli_source_audit_help():
    r = subprocess.run([sys.executable, CLI, "source-audit", "--help"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "watchlist" in r.stdout
    assert "priority" in r.stdout
    assert "ls8" in r.stdout
    print("[PASS] test_cli_source_audit_help")


def test_cli_source_audit_default_watchlist():
    r = subprocess.run([sys.executable, CLI, "source-audit", "--days", "7"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "Source Coverage Audit" in r.stdout
    print("[PASS] test_cli_source_audit_default_watchlist")


def test_cli_source_audit_watchlist_priority():
    r = subprocess.run([sys.executable, CLI, "source-audit", "--watchlist", "priority", "--days", "7"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "Source Coverage Audit" in r.stdout
    print("[PASS] test_cli_source_audit_watchlist_priority")


def test_cli_source_audit_watchlist_ls8():
    r = subprocess.run([sys.executable, CLI, "source-audit", "--watchlist", "ls8", "--days", "7"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "Source Coverage Audit" in r.stdout
    print("[PASS] test_cli_source_audit_watchlist_ls8")


def test_cli_source_audit_format_json():
    r = subprocess.run([sys.executable, CLI, "source-audit", "--days", "7", "--format", "json"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "total" in data
    assert "official_rate" in data
    assert "expected_flags" in data
    print("[PASS] test_cli_source_audit_format_json")


def test_cli_source_audit_output_file():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "sa.md"
        r = subprocess.run([sys.executable, CLI, "source-audit", "--days", "7", "--output", str(out)],
                           capture_output=True, text=True, cwd=Path(sys.path[0]))
        assert r.returncode == 0
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "Source Coverage Audit" in content
    print("[PASS] test_cli_source_audit_output_file")


def test_cli_source_audit_output_json_file():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "sa.json"
        r = subprocess.run([sys.executable, CLI, "source-audit", "--days", "7", "--format", "json", "--output", str(out)],
                           capture_output=True, text=True, cwd=Path(sys.path[0]))
        assert r.returncode == 0
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "total" in data
        assert "watchlist" in data
    print("[PASS] test_cli_source_audit_output_json_file")


if __name__ == "__main__":
    test_cli_source_audit_help()
    test_cli_source_audit_default_watchlist()
    test_cli_source_audit_watchlist_priority()
    test_cli_source_audit_watchlist_ls8()
    test_cli_source_audit_format_json()
    test_cli_source_audit_output_file()
    test_cli_source_audit_output_json_file()
    print("\n✅ 所有 CLI source-audit 测试通过")
