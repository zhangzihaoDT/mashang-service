"""Schema ↔ docs drift guard.

守护 `shared/schema/` 的机器可读契约与 `reference/*.md` 语义视图不漂移：
- 注册表中的每个 metric / derived / relation 都在 reference 文档中出现；
- reference 文档引用的仓库内路径真实存在，且不再引用已删除的 `scripts/` 目录；
- reference 文档都被 `shared/schema/README.md` 索引。
"""

import json
import re
from pathlib import Path

import pytest

_PRJ = Path(__file__).resolve().parents[2]
_SCHEMA = _PRJ / "shared" / "schema"
_REFERENCE = _SCHEMA / "reference"
_METRICS = json.loads((_SCHEMA / "metrics.json").read_text(encoding="utf-8"))
_METRIC_DOC = _REFERENCE / "metric_definitions.md"


def _norm(text: str) -> str:
    """去掉空白并统一全角括号，避免「省份 TopK 占比」这类写法误判。"""
    return (
        re.sub(r"\s+", "", text)
        .replace("（", "(")
        .replace("）", ")")
        .replace("，", ",")
    )


def test_all_registry_metrics_documented():
    doc = _norm(_METRIC_DOC.read_text(encoding="utf-8"))
    missing = [name for name in _METRICS["metrics"] if _norm(name) not in doc]
    assert not missing, f"metrics.json 中的指标未写入 metric_definitions.md: {missing}"


def test_all_derived_and_relations_documented():
    doc = _norm(_METRIC_DOC.read_text(encoding="utf-8"))
    missing_derived = [
        name for name in _METRICS.get("derived_metrics", {}) if _norm(name) not in doc
    ]
    missing_relations = [
        name for name in _METRICS.get("metric_relations", {}) if _norm(name) not in doc
    ]
    assert not missing_derived, f"derived_metrics 未写入文档: {missing_derived}"
    assert not missing_relations, f"metric_relations 未写入文档: {missing_relations}"


def test_reference_doc_paths_exist():
    """reference 文档中引用的脚本/代码路径必须存在；`scripts/` 已删除，出现即失败。"""
    token_re = re.compile(r"`([^`]+)`")
    problems: list[str] = []
    for md in sorted(_REFERENCE.glob("*.md")):
        for token in token_re.findall(md.read_text(encoding="utf-8")):
            token = token.strip().rstrip("。，,；;）)")
            token = token.split("::")[0].split("#")[0]
            if not re.match(r"^(scripts|mashang_workspace|shared|dataset)/", token):
                continue
            if any(ch in token for ch in "*{}"):
                continue  # glob / 占位符不检查
            if token.startswith("scripts/"):
                problems.append(f"{md.name}: 已删除的 scripts/ 路径 {token}")
            elif token.startswith(("mashang_workspace/", "shared/")):
                if not (_PRJ / token).exists():
                    problems.append(f"{md.name}: 路径不存在 {token}")
            # dataset/ 可能未在本机检出，只要求前缀正确
    assert not problems, "reference 文档路径检查失败:\n" + "\n".join(problems)


def test_reference_docs_indexed():
    readme = (_SCHEMA / "README.md").read_text(encoding="utf-8")
    missing = [md.name for md in sorted(_REFERENCE.glob("*.md")) if md.name not in readme]
    assert not missing, f"shared/schema/README.md 未索引 reference 文档: {missing}"


@pytest.mark.parametrize("name", ["metric_definitions.md", "business_glossary.md",
                                  "time_window_rules.md", "vehicle_mapping.md"])
def test_reference_doc_not_empty(name):
    assert (_REFERENCE / name).stat().st_size > 0
