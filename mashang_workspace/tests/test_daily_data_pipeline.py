"""
Phase 13 Step 2.5 — Dataset Updater Integration & Daily Pipeline Naming

验证 dataset updater 存在、Makefile targets 正确、pipeline 文档完整。
"""

import sys
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_WS_DIR))

from utils.paths import PROJECT_ROOT, WORKSPACE_ROOT, UTILITY_SCRIPTS_DIR

DATASET_DIR = PROJECT_ROOT / "dataset"
UPDATER_DIR = DATASET_DIR / "updater"
MAKEFILE_PATH = PROJECT_ROOT / "Makefile"
REGISTRY_PATH = WORKSPACE_ROOT / "registry" / "capability_registry.json"
V2_CONFIG_PATH = PROJECT_ROOT / "mashang_runtime_v2" / "config" / "runtime_v2_config.json"
PIPELINE_DOC = WORKSPACE_ROOT / "docs" / "daily_data_pipeline.md"


def test_updater_exists():
    """dataset/updater/ 存在。"""
    assert UPDATER_DIR.exists(), f"updater dir not found: {UPDATER_DIR}"


def test_update_all_datasets_exists():
    """dataset/updater/update_all_datasets.py 存在。"""
    assert (UPDATER_DIR / "update_all_datasets.py").exists()


def test_order_data_to_parquet_exists():
    """dataset/updater/order_data_to_parquet.py 存在。"""
    assert (UPDATER_DIR / "order_data_to_parquet.py").exists()


def test_order_config_to_parquet_exists():
    """dataset/updater/order_config_to_parquet.py 存在。"""
    assert (UPDATER_DIR / "order_config_to_parquet.py").exists()


def test_lock_attribution_data_to_parquet_exists():
    """dataset/updater/lock_attribution_data_to_parquet.py 存在。"""
    assert (UPDATER_DIR / "lock_attribution_data_to_parquet.py").exists()


def test_utility_scripts_skills_order_observation_exists():
    """utility_scripts/skills_order_observation_daily.py 存在。"""
    assert (UTILITY_SCRIPTS_DIR / "skills_order_observation_daily.py").exists()


def test_utility_scripts_dataset_validate_exists():
    """utility_scripts/dataset_validate.py 存在。"""
    assert (UTILITY_SCRIPTS_DIR / "dataset_validate.py").exists()


def test_makefile_has_dataset_update():
    """Makefile 包含 dataset-update target。"""
    text = MAKEFILE_PATH.read_text()
    assert "dataset-update:" in text


def test_makefile_has_dataset_validate():
    """Makefile 包含 dataset-validate target。"""
    text = MAKEFILE_PATH.read_text()
    assert "dataset-validate:" in text


def test_makefile_has_daily_observation_dry_run():
    """Makefile 包含 daily-observation-dry-run target。"""
    text = MAKEFILE_PATH.read_text()
    assert "daily-observation-dry-run:" in text


def test_makefile_has_daily_observation_sync():
    """Makefile 包含 daily-observation-sync target。"""
    text = MAKEFILE_PATH.read_text()
    assert "daily-observation-sync:" in text


def test_makefile_has_daily_data_pipeline():
    """Makefile 包含 daily-data-pipeline 和 daily-data-pipeline-dry-run。"""
    text = MAKEFILE_PATH.read_text()
    assert "daily-data-pipeline:" in text
    assert "daily-data-pipeline-dry-run:" in text


def test_makefile_daily_sync_dry_run_is_deprecated():
    """Makefile 中 daily-sync-dry-run 是 deprecated alias。"""
    text = MAKEFILE_PATH.read_text()
    assert "DEPRECATED" in text
    assert "daily-observation-dry-run" in text


def test_runtime_v2_config_not_referencing_updater():
    """Runtime V2 config 不引用 dataset/updater。"""
    text = V2_CONFIG_PATH.read_text()
    assert "dataset/updater" not in text
    assert "update_all_datasets" not in text


def test_capability_registry_not_referencing_updater():
    """capability_registry 不把 dataset updater 标记为 capability。"""
    import json
    reg = json.loads(REGISTRY_PATH.read_text())
    for cap in reg:
        assert "update_all_datasets" not in cap.get("script", ""), \
            f"capability {cap['capability_id']} references updater"
        assert "updater" not in cap.get("script", ""), \
            f"capability {cap['capability_id']} references updater"


def test_daily_data_pipeline_doc_exists():
    """docs/daily_data_pipeline.md 存在。"""
    assert PIPELINE_DOC.exists(), f"pipeline doc not found: {PIPELINE_DOC}"


def test_makefile_has_python_variable():
    """Makefile 定义 PYTHON ?= .venv/bin/python。"""
    text = MAKEFILE_PATH.read_text()
    assert "PYTHON ?= .venv/bin/python" in text, "Makefile 缺少 PYTHON 变量"


def test_makefile_no_bare_python():
    """Makefile 中 no bare python calls (only pytest or $(PYTHON))."""
    text = MAKEFILE_PATH.read_text()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("python ") or stripped.startswith("python3 "):
            # Allow in @echo lines only
            if stripped.startswith("@"):
                continue
            raise AssertionError(f"bare python found: {line}")


def test_makefile_dataset_update_uses_python_var():
    """Makefile 中 dataset-update 使用 $(PYTHON)。"""
    text = MAKEFILE_PATH.read_text()
    lines = text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip() == "dataset-update:":
            next_line = lines[i + 1]
            assert "$(PYTHON)" in next_line, f"dataset-update not using $(PYTHON): {next_line}"
            found = True
    assert found, "dataset-update target not found"


def test_makefile_dataset_validate_uses_python_var():
    """Makefile 中 dataset-validate 使用 $(PYTHON)。"""
    text = MAKEFILE_PATH.read_text()
    lines = text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip() == "dataset-validate:":
            next_line = lines[i + 1]
            assert "$(PYTHON)" in next_line, f"dataset-validate not using $(PYTHON): {next_line}"
            found = True
    assert found, "dataset-validate target not found"


def test_makefile_daily_observation_dry_run_uses_python_var():
    """Makefile 中 daily-observation-dry-run 使用 $(PYTHON)。"""
    text = MAKEFILE_PATH.read_text()
    lines = text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip() == "daily-observation-dry-run:":
            next_line = lines[i + 1]
            assert "$(PYTHON)" in next_line, f"daily-observation-dry-run not using $(PYTHON): {next_line}"
            found = True
    assert found, "daily-observation-dry-run target not found"


def test_makefile_runtime_v2_eval_uses_python_var():
    """Makefile 中 runtime-v2-eval 使用 $(PYTHON)。"""
    text = MAKEFILE_PATH.read_text()
    lines = text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip() == "runtime-v2-eval:":
            next_line = lines[i + 1]
            assert "$(PYTHON)" in next_line, f"runtime-v2-eval not using $(PYTHON): {next_line}"
            found = True
    assert found, "runtime-v2-eval target not found"


def test_makefile_python_overridable():
    """Makefile 保留 PYTHON 可覆盖的写法 (?=)。"""
    text = MAKEFILE_PATH.read_text()
    assert "PYTHON ?=" in text, "PYTHON 未使用 ?= 运算符，不可覆盖"


def test_no_today_wording_in_docs():
    """文档中不存在"今天的数据更新并同步"。"""
    import subprocess
    r = subprocess.run(
        ["grep", "-rn", "今天的数据更新并同步", str(WORKSPACE_ROOT / "docs"),
         str(PROJECT_ROOT / "AGENTS.md"), str(WORKSPACE_ROOT / "AGENTS.md")],
        capture_output=True, text=True, timeout=5,
    )
    assert r.returncode != 0, f"发现'今天的数据更新并同步': {r.stdout}"


def test_data_update_and_sync_wording_in_docs():
    """文档中存在"数据更新并同步"。"""
    docs_text = PIPELINE_DOC.read_text()
    assert "数据更新并同步" in docs_text, "daily_data_pipeline.md 缺少'数据更新并同步'"


def test_data_update_and_sync_not_date_analysis():
    """AGENTS.md 说明"数据更新并同步"不是日期条件分析问题。"""
    agents_text = (WORKSPACE_ROOT / "AGENTS.md").read_text()
    assert "不是带日期条件的分析问题" in agents_text or "非日期分析问题" in agents_text, \
        "AGENTS.md 未说明不是日期条件分析"


def test_daily_data_pipeline_dry_run_does_not_depend_on_update():
    """daily-data-pipeline-dry-run 不依赖 dataset-update。"""
    text = MAKEFILE_PATH.read_text()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("daily-data-pipeline-dry-run:"):
            depends = line.split(":", 1)[1].strip()
            assert "dataset-update" not in depends, \
                f"dry-run target depends on dataset-update: {depends}"
            break


def test_dataset_validate_script_works():
    """dataset_validate.py --json 可执行。"""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(UTILITY_SCRIPTS_DIR / "dataset_validate.py"), "--json"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0 or r.returncode == 1, f"dataset_validate failed: {r.stderr}"
    import json
    data = json.loads(r.stdout)
    assert "status" in data
    assert "files" in data
    assert len(data["files"]) == 5
