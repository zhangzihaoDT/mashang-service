"""Schema ↔ docs drift guard.

守护 `shared/schema/` 的机器可读契约与 `reference/*.md` 语义视图不漂移：
- 注册表中的每个 metric / derived / relation 都在 reference 文档中出现；
- reference 文档引用的仓库内路径真实存在，且不再引用已删除的 `scripts/` 目录；
- reference 文档都被 `shared/schema/README.md` 索引；
- `vehicle_mapping.md` 的系列分组规则 / 代际分组关系 / 上市时间窗 / 电池容量四张视图
  与 `business_definition.json` 逐项一致（历史上 CM3/DM2 曾因漏登记长期缺行）。
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
_BUSINESS_DEF = json.loads(
    (_SCHEMA / "business_definition.json").read_text(encoding="utf-8")
)
_VEHICLE_DOC = _REFERENCE / "vehicle_mapping.md"

# `CM3 (precedence=4): product_name LIKE '%M3%' ...` —— 仅用于 series_group_logic 代码块。
_RULE_LINE = re.compile(
    r"^(?P<gen>[^\s(]+?)\s*\(precedence=(?P<priority>\d+)\)\s*:\s*(?P<condition>.+)$"
)


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


# ---------------------------------------------------------------------------
# vehicle_mapping.md ↔ business_definition.json 的逐项对齐（代际 / 时间窗 / 电池）
# ---------------------------------------------------------------------------

def _vehicle_doc_text() -> str:
    return _VEHICLE_DOC.read_text(encoding="utf-8")


def _markdown_rows(width: int, first_cells: set[str]) -> dict[str, list[str]]:
    """抽取列数为 width、且首列命中 first_cells 的表格行，便于按 key 逐字段比对。"""
    rows: dict[str, list[str]] = {}
    for raw in _vehicle_doc_text().splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == width and cells[0] in first_cells:
            rows[cells[0]] = cells
    return rows


def _documented_series_group_rules() -> dict[str, tuple[int, str]]:
    """解析文档 `GEN (precedence=N): condition` 代码块，保留条件字面文本。"""
    rules: dict[str, tuple[int, str]] = {}
    for raw in _vehicle_doc_text().splitlines():
        match = _RULE_LINE.match(raw.strip())
        if match:
            rules[match.group("gen")] = (
                int(match.group("priority")),
                match.group("condition"),
            )
    return rules


def test_series_group_logic_matches_doc():
    """文档规则块必须逐一等于 business_definition.series_group_logic（含 priority 与条件字面）。"""
    documented = _documented_series_group_rules()
    expected = _BUSINESS_DEF["series_group_logic"]

    missing = sorted(set(expected) - set(documented))
    extra = sorted(set(documented) - set(expected))
    assert not missing and not extra, (
        f"vehicle_mapping.md 系列分组规则与 JSON 代际不一致: 缺 {missing}，多 {extra}"
    )

    mismatched = []
    for gen, rule in expected.items():
        if isinstance(rule, dict):
            priority = int(rule.get("priority", 0))
            condition = str(rule.get("condition", ""))
        else:  # 旧字符串格式 ⇒ priority=0
            priority, condition = 0, str(rule)
        if documented[gen] != (priority, condition):
            mismatched.append(
                f"{gen}: doc={documented[gen]} json=({priority}, {condition})"
            )
    assert not mismatched, "规则文本与 JSON 不一致:\n" + "\n".join(mismatched)


def test_model_series_mapping_matches_doc():
    """车系-系列分组关系必须等于 business_definition.model_series_mapping（含顺序）。"""
    normalized = _norm(_vehicle_doc_text())
    expected = {
        series: _norm(f"{series} → [{', '.join(generations)}]")
        for series, generations in _BUSINESS_DEF["model_series_mapping"].items()
    }
    missing = [line for line in expected.values() if line not in normalized]
    assert not missing, "vehicle_mapping.md 车系-分组关系缺失或不一致:\n" + "\n".join(missing)


def test_time_periods_table_matches_doc():
    """上市时间窗表必须覆盖 time_periods 全部代际，且日期逐项一致。

    文档用「—」表示该代际无预售期、用「待确认」表示上市日未定；
    JSON 缺 `start` 时必须写「—」；缺 `end` / `finish` 时允许待确认类占位。
    """
    periods = _BUSINESS_DEF["time_periods"]
    rows = _markdown_rows(4, set(periods))

    missing = sorted(set(periods) - set(rows))
    assert not missing, f"vehicle_mapping.md 上市时间窗表缺代际: {missing}"

    problems = []
    for gen, period in periods.items():
        cells = rows[gen]  # [代际, 预售开始, 上市日, 预计成熟]
        if "start" in period:
            if cells[1] != period["start"]:
                problems.append(f"{gen} 预售开始: doc={cells[1]} json={period['start']}")
        elif cells[1] != "—":
            problems.append(f"{gen} 无预售开始，doc 应写「—」而非 {cells[1]}")
        if "end" in period and cells[2] != period["end"]:
            problems.append(f"{gen} 上市日: doc={cells[2]} json={period['end']}")
        if "finish" in period and cells[3] != period["finish"]:
            problems.append(f"{gen} 预计成熟: doc={cells[3]} json={period['finish']}")
    assert not problems, "上市时间窗与 JSON 不一致:\n" + "\n".join(problems)


def test_battery_capacity_logic_matches_doc():
    """电池容量表必须等于 business_definition.battery_capacity_logic（规则字面一致）。"""
    rules = _BUSINESS_DEF["battery_capacity_logic"]
    rows = _markdown_rows(2, set(rules))

    missing = sorted(set(rules) - set(rows))
    assert not missing, f"vehicle_mapping.md 电池容量表缺行: {missing}"

    mismatched = [
        f"{key}: doc={rows[key][1]} json={condition}"
        for key, condition in rules.items()
        if rows[key][1] != str(condition)
    ]
    assert not mismatched, "电池容量规则与 JSON 不一致:\n" + "\n".join(mismatched)
