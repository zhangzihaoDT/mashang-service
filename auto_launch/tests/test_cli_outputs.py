"""CLI outputs inspect / clean 测试"""
import sys, subprocess, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CLI = "auto_launch/cli.py"


def test_cli_outputs_inspect_help():
    r = subprocess.run([sys.executable, CLI, "outputs", "inspect", "--help"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    print("[PASS] test_cli_outputs_inspect_help")


def test_cli_outputs_clean_help():
    r = subprocess.run([sys.executable, CLI, "outputs", "clean", "--help"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "older-than" in r.stdout
    print("[PASS] test_cli_outputs_clean_help")


def test_cli_outputs_inspect_runs():
    r = subprocess.run([sys.executable, CLI, "outputs", "inspect"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "Outputs Inspection Report" in r.stdout
    assert "Runs" in r.stdout or "runs" in r.stdout
    print("[PASS] test_cli_outputs_inspect_runs")


def test_cli_outputs_inspect_has_facts():
    r = subprocess.run([sys.executable, CLI, "outputs", "inspect"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "SQLite" in r.stdout or "Facts" in r.stdout
    print("[PASS] test_cli_outputs_inspect_has_facts")


def test_cli_outputs_clean_dry_run():
    r = subprocess.run([sys.executable, CLI, "outputs", "clean", "--dry-run"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "dry-run" in r.stdout
    assert "Never cleaned" in r.stdout
    print("[PASS] test_cli_outputs_clean_dry_run")


def test_cli_outputs_clean_older_than():
    r = subprocess.run([sys.executable, CLI, "outputs", "clean", "--older-than", "30", "--dry-run"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "30 days" in r.stdout or "30" in r.stdout
    print("[PASS] test_cli_outputs_clean_older_than")


def test_cli_outputs_clean_never_lists_facts():
    """Verify clean --dry-run output mentions 'facts' as never-cleaned."""
    r = subprocess.run([sys.executable, CLI, "outputs", "clean", "--dry-run"],
                       capture_output=True, text=True, cwd=Path(sys.path[0]))
    assert r.returncode == 0
    assert "Never cleaned" in r.stdout
    assert "facts" in r.stdout
    print("[PASS] test_cli_outputs_clean_never_lists_facts")


if __name__ == "__main__":
    test_cli_outputs_inspect_help()
    test_cli_outputs_clean_help()
    test_cli_outputs_inspect_runs()
    test_cli_outputs_inspect_has_facts()
    test_cli_outputs_clean_dry_run()
    test_cli_outputs_clean_older_than()
    test_cli_outputs_clean_no_files_deleted()
    print("\n✅ 所有 CLI outputs 测试通过")
