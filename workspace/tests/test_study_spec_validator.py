"""
StudySpec 校验器回归测试

治理目标：
  - configs/studies/specs/ 下的研究实例是机器可读、可校验、可版本化的；
  - validate_study_spec.py 必须通过当前所有研究实例；
  - 破坏必需结构时应报错，防止"写死在 plan/Python 里的分析意图"回退为不可校验。
"""

import importlib.util
import json
from pathlib import Path

import yaml

_WS_DIR = Path(__file__).resolve().parents[1]
_SPECS_DIR = _WS_DIR / "configs" / "studies" / "specs"
_VALIDATOR_SCRIPT = _WS_DIR / "utility_scripts" / "validate_study_spec.py"


def _validator():
    spec = importlib.util.spec_from_file_location("validate_study_spec_mod", _VALIDATOR_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {_VALIDATOR_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_schema_json_is_valid_json():
    schema = json.loads((_WS_DIR / "configs" / "studies" / "schema.json").read_text(encoding="utf-8"))
    assert schema["title"] == "StudySpec"
    assert "id" in schema["required"]
    assert "analyses" in schema["required"]


def test_all_spec_yamls_pass_validation():
    mod = _validator()
    spec_files = list(_SPECS_DIR.glob("*.yaml"))
    assert spec_files, f"{_SPECS_DIR}/ 下无 *.yaml"
    for path in spec_files:
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        issues: list = []
        mod.validate_spec(spec, issues)
        assert not issues, f"{path.name} 校验失败: {issues}"
        # 语义化版本与 id 约定：文件名即实例 id，不再重复 ".spec" 后缀
        assert spec["version"].count(".") == 2
        assert spec["id"] == path.stem


def test_validator_flags_missing_required_field():
    mod = _validator()
    path = next(_SPECS_DIR.glob("*.yaml"))
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    del spec["outputs"]
    issues: list = []
    ok = mod.validate_spec(spec, issues)
    assert ok
    assert any("outputs" in i for i in issues)


def test_validator_flags_bad_window():
    mod = _validator()
    path = next(_SPECS_DIR.glob("*.yaml"))
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec["window"]["default"]["start"] = "2026-07-01"  # 早于 end 的日期关系被破坏
    spec["window"]["default"]["end"] = "2025-08-01"
    issues: list = []
    ok = mod.validate_spec(spec, issues)
    assert ok
    assert any("start" in i for i in issues)


def test_validator_flags_duplicate_analysis_id():
    mod = _validator()
    path = next(_SPECS_DIR.glob("*.yaml"))
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec["analyses"].append(dict(spec["analyses"][0]))
    issues: list = []
    ok = mod.validate_spec(spec, issues)
    assert ok
    assert any("重复 id" in i for i in issues)


def _load(name: str) -> dict:
    return yaml.safe_load((_SPECS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))


def test_validation_spec_two_segment_window():
    """两段式验证研究的窗口形态：observation+validation，freeze_date=observation.end，且两段不重叠。"""
    mod = _validator()
    spec = _load("historical_opportunity_validation")
    issues: list = []
    ok = mod.validate_spec(spec, issues)
    assert not ok
    assert spec["window"]["observation"]["freeze_date"] == spec["window"]["observation"]["end"]
    assert spec["window"]["validation"]["start"] > spec["window"]["observation"]["end"]
    assert spec["window"]["validation"]["duration_months"] == 12


def test_validator_flags_overlapping_windows():
    """观测/验证两段重叠时应报错（数据泄漏）。"""
    mod = _validator()
    spec = _load("historical_opportunity_validation")
    spec["window"]["observation"]["end"] = "2024-06-30"  # 与 validation 重叠
    spec["window"]["observation"]["freeze_date"] = "2024-06-30"
    issues: list = []
    ok = mod.validate_spec(spec, issues)
    assert ok
    assert any("validation.start" in i for i in issues)


def test_validator_flags_broken_validation_design():
    """validation_design 破坏（快照市场为空 / 事件 case 缺 model）时应报错。"""
    mod = _validator()
    spec = _load("historical_opportunity_validation")
    spec["validation_design"]["opportunity_snapshot"]["markets"] = []
    issues: list = []
    ok = mod.validate_spec(spec, issues)
    assert ok
    assert any("markets" in i for i in issues)

    spec = _load("historical_opportunity_validation")
    del spec["validation_design"]["event_cases"][0]["model"]
    issues = []
    ok = mod.validate_spec(spec, issues)
    assert ok
    assert any("model" in i for i in issues)
