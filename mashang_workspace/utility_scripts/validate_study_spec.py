#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StudySpec 校验器

校验 configs/studies/specs/ 下的研究配置实例（StudySpec）：
  1. YAML 可解析、根节点为映射
  2. 必需字段齐全、类型正确（内置结构校验，零第三方依赖）
  3. 若已安装 jsonschema，则额外按 configs/studies/schema.json 严格校验
  4. 语义一致性：analyses.id 唯一、classifiers 标签在 priority 中覆盖、
     thresholds 引用一致性、输出文件可解析

用法：
  python mashang_workspace/utility_scripts/validate_study_spec.py
  python mashang_workspace/utility_scripts/validate_study_spec.py --spec <path>
  python mashang_workspace/utility_scripts/validate_study_spec.py --strict
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = _REPO_ROOT / "mashang_workspace"
_STUDIES_DIR = _WS / "configs" / "studies"
_SPECS_DIR = _STUDIES_DIR / "specs"
_CLASSIFIERS_DIR = _STUDIES_DIR / "classifiers"
_SCHEMA_FILE = _STUDIES_DIR / "schema.json"

_REQUIRED_TOP = [
    "spec_version", "id", "name", "version", "status",
    "objective", "data", "window", "analyses", "classifiers", "thresholds", "outputs",
]

_THRESHOLD_KEYS = [
    "opportunity_min_sales", "top3_top_n", "stable_active_months",
    "breakout_growth_pct_min", "breakout_segment_share_pct_min",
    "breakout_scale_quantile", "current_status_rising_pct", "current_status_falling_pct",
]


def _err(issues: list, msg: str) -> None:
    issues.append(msg)


def validate_spec(spec: dict, issues: list) -> bool:
    if not isinstance(spec, dict):
        _err(issues, "根节点必须是映射")
        return False

    for key in _REQUIRED_TOP:
        if key not in spec:
            _err(issues, f"缺少必需字段: {key}")

    if not isinstance(spec.get("id", ""), str) or not re.fullmatch(r"[a-z0-9_]+", spec.get("id", "")):
        _err(issues, "id 必须为小写字母/数字/下划线")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(spec.get("version", ""))):
        _err(issues, "version 必须为语义化版本号 X.Y.Z")
    if spec.get("status") not in ("draft", "active", "archived"):
        _err(issues, f"status 必须是 draft/active/archived，当前: {spec.get('status')!r}")

    _check_objective(spec, issues)
    _check_window(spec, issues)
    _check_analyses(spec, issues)
    _check_classifiers(spec, issues)
    _check_thresholds(spec, issues)
    _check_outputs(spec, issues)
    _check_validation_design(spec, issues)
    return bool(issues)


def _check_objective(spec: dict, issues: list) -> None:
    obj = spec.get("objective")
    if not isinstance(obj, dict):
        return
    if not isinstance(obj.get("summary", ""), str) or not obj.get("summary"):
        _err(issues, "objective.summary 必须为非空字符串")
    questions = obj.get("questions")
    if not isinstance(questions, list) or not questions:
        _err(issues, "objective.questions 必须为非空列表")
        return
    seen = set()
    for q in questions:
        if not isinstance(q, dict) or not isinstance(q.get("id", ""), str) or not q.get("id"):
            _err(issues, "objective.questions[].id 必须为非空字符串")
        elif q["id"] in seen:
            _err(issues, f"objective.questions 存在重复 id: {q['id']}")
        else:
            seen.add(q["id"])
        if not isinstance(q.get("question", ""), str) or not q.get("question"):
            _err(issues, f"objective.questions[{q.get('id')}] 缺少 question")


def _check_window(spec: dict, issues: list) -> None:
    win = spec.get("window")
    if not isinstance(win, dict):
        _err(issues, "window 必须是映射")
        return

    def _check_period(prefix: str, period: object) -> None:
        if not isinstance(period, dict):
            _err(issues, f"{prefix} 必须是映射")
            return
        for field in ("start", "end"):
            value = period.get(field)
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
                _err(issues, f"{prefix}.{field} 必须为 YYYY-MM-DD")
        start = period.get("start")
        end = period.get("end")
        if isinstance(start, str) and isinstance(end, str) and start >= end:
            _err(issues, f"{prefix}.start 必须早于 end")

    has_default = "default" in win
    has_validation = "observation" in win and "validation" in win
    if not has_default and not has_validation:
        _err(issues, "window 必须提供 default（分析研究）或 observation+validation（验证研究）")
        return

    if has_default:
        _check_period("window.default", win.get("default"))
    if has_validation:
        _check_period("window.observation", win.get("observation"))
        _check_period("window.validation", win.get("validation"))
        obs = win.get("observation") or {}
        free = obs.get("freeze_date")
        if not isinstance(free, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", free or ""):
            _err(issues, "window.observation.freeze_date 必须为 YYYY-MM-DD")
        elif isinstance(obs.get("end"), str) and free != obs["end"]:
            _err(issues, "window.observation.freeze_date 必须等于 observation.end")
        vstart = (win.get("validation") or {}).get("start")
        oend = obs.get("end")
        if isinstance(vstart, str) and isinstance(oend, str) and vstart <= oend:
            _err(issues, "window.validation.start 必须晚于 observation.end")
        duration = (win.get("validation") or {}).get("duration_months")
        if duration is not None and (not isinstance(duration, int) or duration < 1):
            _err(issues, "window.validation.duration_months 必须为正整数")

    comp = win.get("comparison")
    if isinstance(comp, dict):
        for field in ("recent_months", "prior_months"):
            value = comp.get(field)
            if not isinstance(value, int) or value < 1:
                _err(issues, f"window.comparison.{field} 必须为正整数")


def _check_validation_design(spec: dict, issues: list) -> None:
    vd = spec.get("validation_design")
    if vd is None:
        return
    if not isinstance(vd, dict):
        _err(issues, "validation_design 必须是映射")
        return

    snapshot = vd.get("opportunity_snapshot")
    if snapshot is not None:
        if not isinstance(snapshot, dict):
            _err(issues, "validation_design.opportunity_snapshot 必须是映射")
        else:
            if not isinstance(snapshot.get("frozen_at", ""), str) or not snapshot.get("frozen_at"):
                _err(issues, "validation_design.opportunity_snapshot.frozen_at 必须为非空字符串")
            markets = snapshot.get("markets")
            if not isinstance(markets, list) or not markets:
                _err(issues, "validation_design.opportunity_snapshot.markets 必须为非空列表")
            else:
                seen = set()
                for m in markets:
                    if not isinstance(m, dict):
                        _err(issues, "opportunity_snapshot.markets[].必须是映射")
                        continue
                    for field in ("rank", "market", "judgment"):
                        if field not in m:
                            _err(issues, f"opportunity_snapshot.markets[] 缺少字段 {field}")
                    if m.get("rank") in seen:
                        _err(issues, f"opportunity_snapshot.markets 存在重复 rank: {m.get('rank')}")
                    else:
                        seen.add(m.get("rank"))

    measurements = vd.get("measurements")
    if measurements is not None:
        if not isinstance(measurements, list) or not measurements:
            _err(issues, "validation_design.measurements 必须为非空列表")
        else:
            seen = set()
            for item in measurements:
                if not isinstance(item, dict) or not isinstance(item.get("id", ""), str) or not item.get("id"):
                    _err(issues, "validation_design.measurements[].id 必须为非空字符串")
                elif item["id"] in seen:
                    _err(issues, f"validation_design.measurements 存在重复 id: {item['id']}")
                else:
                    seen.add(item["id"])

    cm = vd.get("confusion_matrix")
    if cm is not None:
        if not isinstance(cm, dict):
            _err(issues, "validation_design.confusion_matrix 必须是映射")
        elif not isinstance(cm.get("cells"), list) or not cm.get("cells"):
            _err(issues, "validation_design.confusion_matrix.cells 必须为非空列表")
        else:
            for cell in cm["cells"]:
                for field in ("label", "condition", "meaning"):
                    if not isinstance(cell, dict) or not isinstance(cell.get(field, ""), str) or not cell.get(field):
                        _err(issues, f"confusion_matrix.cells[].{field} 必须为非空字符串")
                        break

    events = vd.get("event_cases")
    if events is not None:
        if not isinstance(events, list) or not events:
            _err(issues, "validation_design.event_cases 必须为非空列表")
        else:
            seen = set()
            for case in events:
                if not isinstance(case, dict) or not isinstance(case.get("id", ""), str) or not case.get("id"):
                    _err(issues, "validation_design.event_cases[].id 必须为非空字符串")
                elif case["id"] in seen:
                    _err(issues, f"validation_design.event_cases 存在重复 id: {case['id']}")
                else:
                    seen.add(case["id"])
                if not isinstance(case.get("model", ""), str) or not case.get("model"):
                    _err(issues, f"validation_design.event_cases[{case.get('id')}].model 必须为非空字符串")

    questions = vd.get("evaluation_questions")
    if questions is not None:
        if not isinstance(questions, list) or not questions:
            _err(issues, "validation_design.evaluation_questions 必须为非空列表")
        else:
            seen = set()
            for q in questions:
                if not isinstance(q, dict) or not isinstance(q.get("id", ""), str) or not q.get("id"):
                    _err(issues, "validation_design.evaluation_questions[].id 必须为非空字符串")
                elif q["id"] in seen:
                    _err(issues, f"validation_design.evaluation_questions 存在重复 id: {q['id']}")
                else:
                    seen.add(q["id"])
                if not isinstance(q.get("question", ""), str) or not q.get("question"):
                    _err(issues, "validation_design.evaluation_questions[].question 必须为非空字符串")


def _check_analyses(spec: dict, issues: list) -> None:
    analyses = spec.get("analyses")
    if not isinstance(analyses, list) or not analyses:
        _err(issues, "analyses 必须为非空列表")
        return
    seen = set()
    for a in analyses:
        if not isinstance(a, dict):
            _err(issues, "analyses[].必须是映射")
            continue
        aid = a.get("id", "")
        if not isinstance(aid, str) or not aid:
            _err(issues, "analyses[].id 必须为非空字符串")
        elif aid in seen:
            _err(issues, f"analyses 存在重复 id: {aid}")
        else:
            seen.add(aid)
        for field in ("name", "script_fn"):
            if not isinstance(a.get(field), str) or not a.get(field):
                _err(issues, f"analyses[{aid}].{field} 必须为非空字符串")


def _check_classifiers(spec: dict, issues: list) -> None:
    classifiers = spec.get("classifiers")
    if not isinstance(classifiers, dict) or not classifiers:
        _err(issues, "classifiers 必须为非空映射")
        return
    for name, cls in classifiers.items():
        if not isinstance(cls, dict):
            _err(issues, f"classifiers.{name} 必须是映射")
            continue
        labels = cls.get("labels")
        if not isinstance(labels, list) or not labels:
            _err(issues, f"classifiers.{name}.labels 必须为非空列表")
            continue
        priority = cls.get("priority")
        if isinstance(priority, list):
            missing = [lab for lab in labels if lab not in priority]
            if missing:
                _err(issues, f"classifiers.{name} 的 labels 未全部纳入 priority: {missing}")
        if "rules" in cls and not isinstance(cls["rules"], dict):
            _err(issues, f"classifiers.{name}.rules 必须是映射")


def _check_thresholds(spec: dict, issues: list) -> None:
    thresholds = spec.get("thresholds")
    if not isinstance(thresholds, dict) or not thresholds:
        _err(issues, "thresholds 必须为非空映射")
        return
    for key, value in thresholds.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _err(issues, f"thresholds.{key} 必须为数值")
    for key in _THRESHOLD_KEYS:
        if key in thresholds and (isinstance(thresholds[key], bool) or not isinstance(thresholds[key], (int, float))):
            _err(issues, f"thresholds.{key} 必须为数值")
    if "opportunity_min_sales" in thresholds and thresholds["opportunity_min_sales"] <= 0:
        _err(issues, "thresholds.opportunity_min_sales 必须为正数")


def _check_outputs(spec: dict, issues: list) -> None:
    outputs = spec.get("outputs")
    if not isinstance(outputs, dict):
        _err(issues, "outputs 必须是映射")
        return
    tables = outputs.get("tables")
    if not isinstance(tables, list) or not tables:
        _err(issues, "outputs.tables 必须为非空列表")
    else:
        seen = set()
        for t in tables:
            if not isinstance(t, dict) or not isinstance(t.get("id", ""), str) or not t.get("id"):
                _err(issues, "outputs.tables[].id 必须为非空字符串")
            elif t["id"] in seen:
                _err(issues, f"outputs.tables 存在重复 id: {t['id']}")
            else:
                seen.add(t["id"])
            if not isinstance(t.get("file"), str) or not t.get("file"):
                _err(issues, f"outputs.tables[{t.get('id')}].file 必须为非空字符串")
            elif "{window}" in t.get("file", "") and "window" not in spec:
                _err(issues, f"outputs.tables[{t.get('id')}].file 使用 {{window}} 占位符但缺少 window 定义")
    report = outputs.get("report")
    if not isinstance(report, dict) or not isinstance(report.get("file", ""), str) or not report.get("file"):
        _err(issues, "outputs.report.file 必须为非空字符串")


def _run_json_schema(spec: dict, issues: list) -> None:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return
    schema = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=spec, schema=schema)
    except jsonschema.ValidationError as exc:
        _err(issues, f"jsonschema 校验失败: {exc.message} (path: {'/'.join(map(str, exc.path)) or '/'})")


def _discover_specs() -> list[Path]:
    if not _SPECS_DIR.exists():
        return []
    return sorted(p for p in _SPECS_DIR.glob("*.yaml") if p.is_file())


def _discover_classifiers() -> list[Path]:
    if not _CLASSIFIERS_DIR.exists():
        return []
    return sorted(p for p in _CLASSIFIERS_DIR.glob("*.yaml") if p.is_file())


def _validate_classifier(spec: dict, issues: list) -> bool:
    """Classifier Spec 轻量校验（与 StudySpec 结构不同）。"""
    for key in ("id", "name", "version", "status", "runtime"):
        if key not in spec:
            _err(issues, f"缺少必需字段: {key}")
    if spec.get("status") not in ("experimental", "research", "active", "archived"):
        _err(issues, f"status 必须是 experimental/research/active/archived，当前: {spec.get('status')!r}")
    if "regime_switch" not in spec or not isinstance(spec.get("regime_switch"), dict):
        _err(issues, "classifier 缺少 regime_switch（regime 判定）")
    if "branches" not in spec or not isinstance(spec.get("branches"), dict):
        _err(issues, "classifier 缺少 branches（各 regime 分支）")
    if spec.get("status") in ("experimental", "research"):
        for key in ("evidence_status", "output_contract"):
            if key not in spec:
                _err(issues, f"research 状态 classifier 缺少 {key}（证据链/输出契约）")
    return bool(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description="StudySpec / Classifier 校验器")
    parser.add_argument("--spec", help="指定 spec 文件路径（默认校验 configs/studies/specs/*.yaml）")
    parser.add_argument("--strict", action="store_true", help="存在任何问题（含告警）时返回非 0")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if args.spec:
        paths = [Path(args.spec)]
    else:
        paths = _discover_specs() + _discover_classifiers()
        if not paths:
            print(f"❌ 未找到 StudySpec/Classifier: {_SPECS_DIR}/ 与 {_CLASSIFIERS_DIR}/ 下无 *.yaml")
            return 1

    results = []
    failed = False
    for path in paths:
        try:
            spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            results.append({"file": str(path), "status": "error", "issues": [f"YAML 解析失败: {exc}"]})
            failed = True
            continue

        issues: list = []
        if path.parent == _CLASSIFIERS_DIR:
            has_errors = _validate_classifier(spec, issues)
        else:
            has_errors = validate_spec(spec, issues)
            _run_json_schema(spec, issues)
        ok = not has_errors and not issues
        if not ok:
            failed = True
        results.append({"file": str(path), "status": "ok" if ok else "error", "issues": issues})

    if args.json:
        print(json.dumps({"passed": not failed, "results": results}, ensure_ascii=False, indent=2))
    else:
        for r in results:
            if r["status"] == "ok":
                print(f"✅ {r['file']} — PASS")
            else:
                print(f"❌ {r['file']} — FAIL")
                for issue in r["issues"]:
                    print(f"   - {issue}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
