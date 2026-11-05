"""
Smoke tests for eval/run_followup_eval.py
"""

import subprocess
import sys
import json
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
FOLLOWUP_RUNNER = _WS_DIR / "eval" / "run_followup_eval.py"
FOLLOWUP_CASES = _WS_DIR / "eval" / "cases" / "followup_cases.json"


def _run_runner(args: list[str]) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(FOLLOWUP_RUNNER)] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def test_runner_help():
    """--help 正常输出。"""
    result = _run_runner(["--help"])
    assert result.returncode == 0
    assert "Follow-up Eval Runner" in result.stdout


def test_runner_reads_cases():
    """默认参数能读取 cases JSON。"""
    result = _run_runner(["--cases", str(FOLLOWUP_CASES)])
    assert result.returncode == 0
    assert "Case:" in result.stdout or "cases" in json.loads(
        result.stdout  # in case json format is detected
    )


def test_runner_json_output():
    """--format json 输出有效 JSON。"""
    result = _run_runner(["--cases", str(FOLLOWUP_CASES), "--format", "json"])
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "meta" in data
    assert "cases" in data
    assert data["meta"]["total_cases"] >= 3
    assert data["meta"]["total_turns"] >= 7


def test_runner_json_output_to_file(tmp_path):
    """--output 写入 JSON 文件。"""
    out_file = tmp_path / "followup_result.json"
    result = _run_runner([
        "--cases", str(FOLLOWUP_CASES),
        "--format", "json",
        "--output", str(out_file),
    ])
    assert result.returncode == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert "cases" in data


def test_followup_ls6_energy_inheritance():
    """followup_ls6_energy_001 第二轮应继承 LS6、metric、group_by，并覆盖 time_window。"""
    result = _run_runner(["--as-of-date", "2026-06-11", "--format", "json"])
    data = json.loads(result.stdout)
    target_case = next(c for c in data["cases"] if c["case_id"] == "followup_ls6_energy_001")
    assert len(target_case["turns"]) == 2

    turn0 = target_case["turns"][0]
    assert turn0["resolved_context"]["metric"] == "lock_count_share"
    assert turn0["resolved_context"]["series"] == "LS6"
    assert turn0["resolved_context"]["time_window"] == "last_15_days"

    turn1 = target_case["turns"][1]
    assert turn1["resolved_context"]["metric"] == "lock_count_share"  # 显式指定
    assert turn1["resolved_context"]["series"] == "LS6"  # 显式指定
    assert turn1["resolved_context"]["time_window"] == "last_7_days"  # 覆盖
    # metric/series/group_by 在 JSON 中显式指定，不算 inherited
    # time_window 被显式覆盖
    assert turn1["overridden_context"]["time_window"]["from"] == "last_15_days"
    assert turn1["overridden_context"]["time_window"]["to"] == "last_7_days"


def test_followup_lock_model_city_script():
    """followup_lock_model_city_001 第二轮应推荐 lock_city_distribution.py。"""
    result = _run_runner(["--as-of-date", "2026-06-11", "--format", "json"])
    data = json.loads(result.stdout)
    target_case = next(c for c in data["cases"] if c["case_id"] == "followup_lock_model_city_001")
    assert len(target_case["turns"]) == 2

    turn0 = target_case["turns"][0]
    assert "lock_by_model.py" in turn0["recommended_script"]

    turn1 = target_case["turns"][1]
    assert "lock_city_distribution.py" in turn1["recommended_script"]
    assert turn1["can_execute"] is True


def test_dry_run_does_not_execute():
    """dry-run 模式下不执行脚本。"""
    result = _run_runner(["--cases", str(FOLLOWUP_CASES), "--format", "json"])
    data = json.loads(result.stdout)
    assert data["meta"]["dry_run"] is True
    assert "execution" not in data["cases"][0]["turns"][0]


def test_missing_context_detection():
    """缺少关键字段时 can_execute=False。"""
    # 构造一个缺失 metric 的 case
    minimal_cases = json.dumps([{
        "case_id": "test_missing",
        "turns": [{"user": "test", "expected_context": {}}]
    }], ensure_ascii=False)
    tmp_file = _WS_DIR / "outputs" / "tables" / "_test_missing.json"
    tmp_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file.write_text(minimal_cases, encoding="utf-8")

    result = _run_runner(["--cases", str(tmp_file), "--format", "json"])
    data = json.loads(result.stdout)
    turn0 = data["cases"][0]["turns"][0]
    assert turn0["can_execute"] is False
    assert "metric" in turn0["missing_context"]
    tmp_file.unlink()
