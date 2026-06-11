#!/usr/bin/env python
"""
Result Contract — 统一脚本执行结果协议

提供构建 success/error contract、保存、打印摘要等工具函数。
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def build_success_contract(
    script: str,
    command: str,
    scope: dict,
    result: dict,
    artifacts: dict | None = None,
    followup_context: dict | None = None,
    warnings: list | None = None,
) -> dict:
    """构建成功执行的结果 contract。"""
    return {
        "status": "success",
        "script": script,
        "command": command,
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "scope": _default_scope(scope),
        "result": result,
        "artifacts": artifacts or {},
        "followup_context": followup_context or {},
        "warnings": warnings or [],
        "errors": [],
    }


def build_partial_contract(
    script: str,
    command: str,
    scope: dict,
    result: dict,
    warnings: list,
    artifacts: dict | None = None,
    followup_context: dict | None = None,
) -> dict:
    """构建部分成功的结果 contract（骨架脚本或能力未完全实现时使用）。"""
    return {
        "status": "partial_success",
        "script": script,
        "command": command,
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "scope": _default_scope(scope),
        "result": result,
        "artifacts": artifacts or {},
        "followup_context": followup_context or {},
        "warnings": warnings,
        "errors": [],
    }


def build_error_contract(
    script: str,
    command: str,
    error_message: str,
    scope: dict | None = None,
    warnings: list | None = None,
) -> dict:
    """构建执行出错的结果 contract。"""
    return {
        "status": "error",
        "script": script,
        "command": command,
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "scope": _default_scope(scope or {}),
        "result": {},
        "artifacts": {},
        "followup_context": {},
        "warnings": warnings or [],
        "errors": [{"message": error_message}],
    }


def _default_scope(scope: dict) -> dict:
    """补齐 scope 中缺失的字段。"""
    defaults = {
        "data_source": None,
        "time_window": {},
        "filters": {},
        "metric_definition": None,
    }
    defaults.update(scope)
    return defaults


def save_contract_json(contract: dict, output_path: str | Path, print_info: bool = True) -> Path:
    """将 contract 保存为 JSON 文件。"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)
    if print_info:
        print(f"  JSON: {path}")
    return path


def print_contract_summary(contract: dict) -> None:
    """打印 contract 终端摘要。"""
    print(f"[Summary]")
    print(f"  Status: {contract['status']}")
    print()
    print("[Scope]")
    s = contract.get("scope", {})
    print(f"  数据源: {s.get('data_source', 'N/A')}")
    tw = s.get("time_window", {})
    if tw.get("date"):
        print(f"  时间: {tw['date']}")
    elif tw.get("start_date"):
        print(f"  时间: {tw['start_date']} ~ {tw.get('end_date', '')}")
    flt = s.get("filters", {})
    if flt:
        print(f"  过滤: {flt}")
    if s.get("metric_definition"):
        print(f"  口径: {s['metric_definition']}")
    print()
    print("[Result]")
    r = contract.get("result", {})
    if r.get("summary"):
        print(f"  {r['summary']}")
    metrics = r.get("metrics", {})
    if metrics:
        for k, v in metrics.items():
            print(f"  {k}: {v}")
    if r.get("dimensions"):
        for dim in r["dimensions"]:
            items = dim.get("items", [])
            print(f"  按 {dim.get('name', '?')}: {len(items)} 项")
    if contract.get("warnings"):
        print()
        print("[Warnings]")
        for w in contract["warnings"]:
            print(f"  ⚠ {w}")
    if contract.get("errors"):
        print()
        print("[Errors]")
        for e in contract["errors"]:
            print(f"  ❌ {e.get('message', '')}")
    artifacts = contract.get("artifacts", {})
    if any(v for v in artifacts.values()):
        print()
        print("[Output]")
        for k, v in artifacts.items():
            if v:
                print(f"  {k.upper()}: {v}")


def make_followup_context(
    metric: str,
    time_window: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    date: str | None = None,
    series: str | None = None,
    model: str | None = None,
    city: str | None = None,
    group_by: str | None = None,
    available_dimensions: list | None = None,
    top_entities: list | None = None,
) -> dict:
    """构建 followup_context，供下一轮追问继承。"""
    ctx: dict[str, Any] = {
        "metric": metric,
        "available_dimensions": available_dimensions or [],
        "top_entities": top_entities or [],
    }
    if date:
        ctx["date"] = date
    if time_window:
        ctx["time_window"] = time_window
    if start_date:
        ctx["start_date"] = start_date
    if end_date:
        ctx["end_date"] = end_date
    if series:
        ctx["series"] = series
    if model:
        ctx["model"] = model
    if city:
        ctx["city"] = city
    if group_by:
        ctx["group_by"] = group_by
    return ctx


def contract_to_terminal(contract: dict) -> str:
    """将 contract 转为标准终端输出字符串（[Summary] / [Scope] / [Result] / [Output]）。"""
    lines = []
    lines.append("[Summary]")
    r = contract.get("result", {})
    if r.get("summary"):
        lines.append(f"  {r['summary']}")
    metrics = r.get("metrics", {})
    for k, v in metrics.items():
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("[Scope]")
    s = contract.get("scope", {})
    lines.append(f"  数据源: {s.get('data_source', 'N/A')}")
    tw = s.get("time_window", {})
    if tw.get("date"):
        lines.append(f"  时间: {tw['date']}")
    else:
        lines.append(f"  时间: {tw.get('start_date', '')} ~ {tw.get('end_date', '')}")
    flt = s.get("filters", {})
    if flt:
        lines.append(f"  过滤: {flt}")
    if s.get("metric_definition"):
        lines.append(f"  口径: {s['metric_definition']}")
    lines.append("")

    lines.append("[Result]")
    if r.get("dimensions"):
        for dim in r["dimensions"]:
            items = dim.get("items", [])
            lines.append(f"  按 {dim.get('name', '?')}:")
            for item in items[:10]:
                v = item.get("value", "")
                m = item.get("metrics", {})
                parts = [f"{k}={v}" for k, v in m.items()]
                lines.append(f"    {v}: {', '.join(parts)}")
    lines.append("")

    artifacts = contract.get("artifacts", {})
    if any(v for v in artifacts.values()):
        lines.append("[Output]")
        for k, v in artifacts.items():
            if v:
                lines.append(f"  {k.upper()}: {v}")
    return "\n".join(lines)
