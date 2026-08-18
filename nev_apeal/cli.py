#!/usr/bin/env python
"""Command line entry point for the isolated NEV-APEAL project."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def write_contracts() -> None:
    from analysis._common import detect_artifact_values, load

    df, meta = load()
    contracts = ROOT / "contracts"
    contracts.mkdir(exist_ok=True)
    # 测量伪影自动检测：值标签命中拒答/不知道/不适用/Other 语义的取值
    excluded_values = []
    for name in df.columns:
        artifacts = detect_artifact_values(meta, name)
        if artifacts:
            excluded_values.append({"variable": name, "values": artifacts})
    measurement = {
        "dataset": "data/source.sav",
        "questionnaire_map": "data/questionnaire_map.json",
        "rows": len(df),
        "columns": len(df.columns),
        "weight": "APEAL_WT",
        "missing_value_policy": "SPSS user-defined missing values are treated as missing",
        "scope": "cross-sectional sample; no year-over-year or market-share claims",
        "excluded_values": excluded_values,
    }
    variables = []
    for name in df.columns:
        variables.append({
            "name": name,
            "label": (dict(zip(meta.column_names, meta.column_labels)).get(name) or ""),
            "dtype": str(df[name].dtype),
            "missing_rate": float(df[name].isna().mean()),
            "value_labels": {str(k): str(v) for k, v in (meta.variable_value_labels.get(name) or {}).items()},
        })
    modules = {
        "coverage_rule": {"FULL": ">=0.90", "PARTIAL": "0.75-0.89", "LIMITED": "<0.75"},
        "modules": [
            {"id": "M1", "name": "车辆属性", "prefixes": ["SCR_"]},
            {"id": "M4", "name": "座舱内装", "prefixes": ["AINT_", "ACMFT_"]},
            {"id": "M7", "name": "驾驶感受", "prefixes": ["ADRV_", "APERF_"]},
            {"id": "M8", "name": "安全感知", "prefixes": ["ASFTY_"]},
            {"id": "M10", "name": "补能续航", "prefixes": ["AFUEL_", "ACHAR_"]},
            {"id": "M11", "name": "品牌感知", "prefixes": ["ABRAND_"]},
        ],
    }
    for path, payload in [("measurement.json", measurement), ("variables.json", variables), ("modules.json", modules)]:
        (contracts / path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"contracts written to {contracts}")


def run_analysis(script: str, args: list[str]) -> None:
    module = f"analysis.{script.removesuffix('.py')}"
    subprocess.run([sys.executable, "-m", module, *args], cwd=ROOT, check=True)


def _load_json(payload: str) -> Any:
    if payload.lstrip().startswith("{"):
        return json.loads(payload)
    try:
        if payload and Path(payload).exists():
            return json.loads(Path(payload).read_text(encoding="utf-8"))
    except OSError:
        pass
    return json.loads(payload or sys.stdin.read())


def research_command(action: str, topic: str, payload: str = "", apply: bool = False) -> None:
    from research.engine import append_evidence, derive_questions, enqueue, evaluate_stop, load_queue, next_action, read_state, write_state

    if action == "next":
        print(json.dumps(next_action(topic), ensure_ascii=False, indent=2, default=str))
    elif action == "state":
        print(yaml_dump(read_state(topic)))
    elif action == "stop-check":
        print(json.dumps(evaluate_stop(topic), ensure_ascii=False, indent=2, default=str))
    elif action == "add-evidence":
        evidence = _load_json(payload)
        print(json.dumps({"evidence_id": append_evidence(topic, evidence)}, ensure_ascii=False, indent=2))
    elif action == "update":
        state = read_state(topic)
        state.update(_load_json(payload))
        write_state(topic, state)
        print(yaml_dump(state))
    elif action == "derive-questions":
        result = _load_json(payload)
        state = read_state(topic)
        queue = load_queue()
        questions = derive_questions(result, state, queue.get("items", []))
        if apply and questions:
            added = enqueue(topic, questions)
            print(json.dumps({"derived": questions, "added_to_queue": added}, ensure_ascii=False, indent=2, default=str))
        else:
            print(json.dumps({"derived": questions, "apply_hint": "re-run with --apply to enqueue"}, ensure_ascii=False, indent=2, default=str))


def yaml_dump(value: object) -> str:
    import yaml
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="NEV-APEAL project CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("contracts", help="rebuild contract JSON from source.sav")
    run = sub.add_parser("run", help="run an analysis module")
    run.add_argument("script", choices=["describe", "compare", "segment", "regress", "control", "drilldown", "robustness", "correlate", "profile", "diagnostics", "nonlinear", "config_compare", "config_match"])
    run.add_argument("args", nargs=argparse.REMAINDER)
    research = sub.add_parser("research", help="inspect and advance research state")
    research.add_argument("action", choices=["next", "state", "stop-check", "add-evidence", "update", "derive-questions", "describe", "compare", "segment", "regress", "control", "drilldown", "robustness", "correlate", "profile", "diagnostics", "nonlinear", "config_compare", "config_match"])
    research.add_argument("--topic", default="topic_x")
    research.add_argument("--input", default="")
    research.add_argument("--apply", action="store_true")
    research.add_argument("args", nargs=argparse.REMAINDER)
    # REMAINDER would swallow --topic/--input/--apply after the action; hoist them before parsing
    argv = sys.argv[1:]
    if argv[:1] == ["research"]:
        hoisted, tail, i = ["research"], [], 1
        while i < len(argv):
            if argv[i] in ("--topic", "--input", "--apply"):
                if argv[i] == "--apply":
                    hoisted.append(argv[i])
                    i += 1
                elif i + 1 < len(argv):
                    hoisted.extend([argv[i], argv[i + 1]])
                    i += 2
                else:
                    tail.append(argv[i])
                    i += 1
            else:
                tail.append(argv[i])
                i += 1
        argv = hoisted + tail
    args = parser.parse_args(argv)
    if args.command == "contracts":
        write_contracts()
    elif args.command == "run":
        run_analysis(args.script, args.args)
    elif args.action in {"next", "state", "stop-check", "add-evidence", "update", "derive-questions"}:
        research_command(args.action, args.topic, args.input, getattr(args, "apply", False))
    else:
        run_analysis(args.action, args.args)


if __name__ == "__main__":
    main()
