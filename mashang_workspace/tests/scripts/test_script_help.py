"""
Smoke test: 确保核心脚本 --help 正常输出且不崩溃。
仅检查 CLI 解析，不验证业务逻辑。
"""

import subprocess
import sys
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = _WS_DIR / "scripts"


def _run_help(script_name: str) -> bool:
    """运行 python scripts/<name>.py --help，返回是否成功。"""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        print(f"[FAIL] 脚本不存在: {script_path}")
        return False
    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True, text=True, timeout=30,
    )
    ok = result.returncode == 0
    if ok:
        print(f"[PASS] {script_name} --help")
    else:
        print(f"[FAIL] {script_name} --help (rc={result.returncode})")
        if result.stderr:
            print(f"  stderr: {result.stderr[:500]}")
    return ok


CORE_SCRIPTS = [
    "daily_lock_count.py",
    "lock_by_model.py",
    "lock_city_distribution.py",
    "release_curve_analysis.py",
    "cohort_forecast.py",
    "voc_theme_analysis.py",
    "data_dictionary.py",
]


def test_all_scripts_help():
    failures = []
    for script in CORE_SCRIPTS:
        if not _run_help(script):
            failures.append(script)
    assert not failures, f"以下脚本 --help 失败: {failures}"
