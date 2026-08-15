#!/usr/bin/env python
"""Command line entry point for the isolated NEV-APEAL project."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def write_contracts() -> None:
    from analysis._common import load

    df, meta = load()
    contracts = ROOT / "contracts"
    contracts.mkdir(exist_ok=True)
    measurement = {
        "dataset": "data/source.sav",
        "questionnaire_map": "data/questionnaire_map.json",
        "rows": len(df),
        "columns": len(df.columns),
        "weight": "APEAL_WT",
        "missing_value_policy": "SPSS user-defined missing values are treated as missing",
        "scope": "cross-sectional sample; no year-over-year or market-share claims",
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


def research_command(action: str, topic: str, payload: str = "") -> None:
    from research.engine import append_evidence, evaluate_stop, next_action, read_state, write_state

    if action == "next":
        print(json.dumps(next_action(topic), ensure_ascii=False, indent=2, default=str))
    elif action == "state":
        print(yaml_dump(read_state(topic)))
    elif action == "stop-check":
        print(json.dumps(evaluate_stop(topic), ensure_ascii=False, indent=2, default=str))
    elif action == "add-evidence":
        evidence = json.loads(Path(payload).read_text(encoding="utf-8") if Path(payload).exists() else payload)
        print(json.dumps({"evidence_id": append_evidence(topic, evidence)}, ensure_ascii=False, indent=2))
    elif action == "update":
        state = read_state(topic)
        state.update(json.loads(payload))
        write_state(topic, state)
        print(yaml_dump(state))


def yaml_dump(value: object) -> str:
    import yaml
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="NEV-APEAL project CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("contracts", help="rebuild contract JSON from source.sav")
    run = sub.add_parser("run", help="run an analysis module")
    run.add_argument("script", choices=["describe", "compare", "segment", "regress", "control", "drilldown", "robustness", "correlate", "profile"])
    run.add_argument("args", nargs=argparse.REMAINDER)
    research = sub.add_parser("research", help="inspect and advance research state")
    research.add_argument("action", choices=["next", "state", "stop-check", "add-evidence", "update", "describe", "compare", "segment", "regress", "control", "drilldown", "robustness", "correlate", "profile"])
    research.add_argument("--topic", default="topic_x")
    research.add_argument("--input", default="")
    research.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "contracts":
        write_contracts()
    elif args.command == "run":
        run_analysis(args.script, args.args)
    elif args.action in {"next", "state", "stop-check", "add-evidence", "update"}:
        research_command(args.action, args.topic, args.input)
    else:
        run_analysis(args.action, args.args)


if __name__ == "__main__":
    main()
