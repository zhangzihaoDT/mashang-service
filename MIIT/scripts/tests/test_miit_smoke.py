"""MIIT 模块 CLI 冒烟测试：验证所有旧入口可用（--help 可执行）。"""
import subprocess
import sys
from pathlib import Path

MIIT = Path(__file__).resolve().parents[2]

ENTRY_POINTS = [
    "scripts/miit_gov_search.py",
    "scripts/01_scan_batch.py",
    "scripts/02_archive_vehicle_details.py",
    "scripts/03_parse_vehicle_tax.py",
    "scripts/04_build_wide_table.py",
    "scripts/05_generate_brand_report.py",
    "scripts/06_generate_category_report.py",
]


def test_all_cli_help():
    for ep in ENTRY_POINTS:
        r = subprocess.run(
            [sys.executable, str(MIIT / ep), "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"{ep} --help failed:\n{r.stderr}"
