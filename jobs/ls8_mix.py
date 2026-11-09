"""Query LS8 interior Mix from a published snapshot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "workspace"))
sys.path.insert(0, str(ROOT))
from jobs.snapshot import read_snapshot_inputs
from utils.config_semantics import get_attribute_spec, load_config_semantics
from utils.ls8_interior_mix import mix


def query_inputs(order_file: Path, config_file: Path) -> dict:
    definition = json.loads((ROOT / "shared/schema/business_definition.json").read_text())
    config_columns = ["Order Number", "Attribute", "value"]
    if "value_code" in pq.ParquetFile(config_file).schema.names:
        config_columns.append("value_code")
    config = pd.read_parquet(config_file, columns=config_columns)
    if "value_code" not in config:
        config["value_code"] = pd.NA

    return mix(
        pd.read_parquet(order_file, columns=[
            "series", "order_number", "product_name", "lock_time", "approve_refund_time",
        ]),
        config,
        definition,
        get_attribute_spec(load_config_semantics(), "LS8", "内饰"),
    )


def query_snapshot(manifest: Path) -> dict:
    started = perf_counter()
    version, inputs = read_snapshot_inputs(manifest, ["order_data", "config_attribute"])
    result = query_inputs(Path(inputs["order_data"]["path"]), Path(inputs["config_attribute"]["path"]))
    warnings = result.pop("warnings")
    checks = result.pop("checks")
    errors = [name for name, check in checks.items() if check["status"] != "passed"]
    return {
        "status": "error" if errors else "partial_success" if warnings else "success",
        "script": "jobs/ls8_mix.py",
        "scope": {
            "data_source": "ticket_snapshot",
            "snapshot_version": version,
            "inputs": inputs,
            "time_window": {"start": result["start"], "end": result["order_cutoff"], "field": "lock_time"},
            "filters": {"series": "LS8 (含 LS8Neo)", "approved_refund": False},
            "metric_definition": "按订单号去重；按版本字典划分动力；分母含缺配及冲突订单，未知动力单列",
        },
        "result": result,
        "checks": checks,
        "followup_context": {"metric": "LS8 内饰 Mix", "available_dimensions": ["动力", "内饰"]},
        "warnings": warnings,
        "errors": errors,
        "timing_ms": {"query": round((perf_counter() - started) * 1000)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True, help="Path to refresh_snapshot's snapshot.json")
    args = parser.parse_args()
    try:
        result = query_snapshot(args.snapshot)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"status": "error", "script": "jobs/ls8_mix.py", "scope": {},
                  "result": {}, "followup_context": {}, "warnings": [], "errors": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    if result["status"] == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
