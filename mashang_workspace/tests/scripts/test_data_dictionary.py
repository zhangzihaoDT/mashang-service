"""
Smoke test: 验证 data_dictionary.py 在最小参数下运行不崩溃。
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO_ROOT.parent


def test_data_dict_help():
    """--help 正常输出。"""
    script = REPO_ROOT / "utility_scripts" / "data_dictionary.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"data_dictionary.py --help 失败: {result.stderr}"


def test_data_dict_terminal_output():
    """默认参数输出 terminal 格式不崩溃。"""
    script = REPO_ROOT / "utility_scripts" / "data_dictionary.py"
    result = subprocess.run(
        [sys.executable, str(script), "--input", "dataset", "--format", "terminal"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"data_dictionary.py terminal 输出失败: {result.stderr}"
    assert "数据字典生成完成" in result.stderr or "数据字典生成完成" in result.stdout, "输出缺少完成标志"


def test_data_dict_csv_output():
    """--format csv 能正常生成 CSV 文件。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        script = REPO_ROOT / "utility_scripts" / "data_dictionary.py"
        result = subprocess.run(
            [sys.executable, str(script), "--input", "dataset", "--format", "csv", "--output", tmpdir],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"data_dictionary.py CSV 输出失败: {result.stderr}"
        csv_file = Path(tmpdir) / "data_dictionary.csv"
        assert csv_file.exists(), f"CSV 文件未生成: {csv_file}"
        content = csv_file.read_text()
        assert "column_name" in content, "CSV 缺少 column_name 列"


def test_data_dict_json_output():
    """--format json 能正常生成 JSON 文件。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        script = REPO_ROOT / "utility_scripts" / "data_dictionary.py"
        result = subprocess.run(
            [sys.executable, str(script), "--input", "dataset", "--format", "json", "--output", tmpdir],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"data_dictionary.py JSON 输出失败: {result.stderr}"
        json_file = Path(tmpdir) / "data_dictionary.json"
        assert json_file.exists(), f"JSON 文件未生成: {json_file}"
        import json as j
        data = j.loads(json_file.read_text())
        assert len(data) > 0, "JSON 数据为空"
        assert "column_name" in data[0], "JSON 缺少 column_name 字段"
