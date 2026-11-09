import json

import pandas as pd

from jobs.ls8_mix import ROOT, mix
from utils.config_semantics import get_attribute_spec, load_config_semantics


def test_mix_deduplicates_orders_and_includes_missing_configuration_in_denominator():
    definition = json.loads((ROOT / "shared/schema/business_definition.json").read_text())
    orders = pd.DataFrame([
        ("a", "智己LS8 52 Max+", "2026-04-16", None),
        ("a", "智己LS8 52 Max+", "2026-04-16", None),
        ("b", "智己LS8 66 Ultra", "2026-05-01", None),
        ("c", "智己LS8 93 RWD", "2026-06-01", None),
        ("old", "智己LS8 93 RWD", "2026-04-15", None),
        ("refunded", "智己LS8 93 RWD", "2026-05-01", "2026-05-02"),
    ], columns=["order_number", "product_name", "lock_time", "approve_refund_time"]).assign(series="LS8")
    configs = pd.DataFrame([
        ("a", "内饰", "大象灰黑", "IN2-ASH"), ("a", "内饰", "大地象灰 深", None),
        ("b", "外饰", "红色", None), ("c", "内饰", "棕色", None),
    ], columns=["Order Number", "Attribute", "value", "value_code"])
    result = mix(orders, configs, definition, get_attribute_spec(load_config_semantics(), "LS8", "内饰"))
    assert result["start"] == "2026-04-16"
    assert result["groups"]["增程"]["total_orders"] == 2
    assert {r["color"]: r["share"] for r in result["groups"]["增程"]["colors"]} == {
        "大象灰黑": 0.5, "缺少内饰配置": 0.5,
    }
    assert result["groups"]["纯电"] == {
        "total_orders": 1, "colors": [{"color": "棕色", "orders": 1, "share": 1.0}],
    }

def test_query_reads_generic_snapshot_and_rejects_missing_or_replaced_inputs(tmp_path):
    import os

    import pytest

    from jobs import ls8_mix

    orders = tmp_path / "order_data.parquet"
    config = tmp_path / "config_attribute.parquet"
    pd.DataFrame([
        ("LS8", "a", "智己LS8 52 Max+", "2026-04-16", None),
        ("LS8", "a", "智己LS8 52 Max+", "2026-04-16", None),
        ("LS8", "b", "智己LS8 93 RWD", "2026-05-01", None),
    ], columns=["series", "order_number", "product_name", "lock_time", "approve_refund_time"]).to_parquet(orders)
    pd.DataFrame([("a", "内饰", "大象灰黑")],
                 columns=["Order Number", "Attribute", "value"]).to_parquet(config)
    inputs = {p.stem: {"path": str(p), "size_bytes": p.stat().st_size} for p in (orders, config)}
    inputs["order_data"]["data_asof"] = "2026-05-01T00:00:00"
    manifest = tmp_path / "snapshot.json"
    snapshot = {"version": tmp_path.name, "datasets": inputs}
    manifest.write_text(json.dumps(snapshot))

    result = ls8_mix.query_snapshot(manifest)
    assert result["status"] == "success"
    assert result["scope"]["snapshot_version"] == tmp_path.name
    assert result["scope"]["inputs"]["order_data"]["data_asof"] == "2026-05-01T00:00:00"
    assert result["scope"]["time_window"]["end"] == "2026-05-01T00:00:00"
    assert result["result"]["latest_matched_config_lock_time"] == "2026-04-16T00:00:00"
    assert result["checks"]["deduplication"] == {"status": "passed", "eligible_rows": 3, "distinct_orders": 2}
    assert result["checks"]["denominators"]["status"] == "passed"
    assert result["result"]["groups"]["纯电"]["colors"][0]["color"] == "缺少内饰配置"
    assert result["timing_ms"]["query"] >= 0

    outside = tmp_path.parent / ("outside-" + tmp_path.name + ".parquet")
    os.replace(config, outside)
    config.symlink_to(outside)
    with pytest.raises(ValueError, match="invalid or changed"):
        ls8_mix.query_snapshot(manifest)
    inputs.pop("config_attribute")
    manifest.write_text(json.dumps(snapshot))
    with pytest.raises(ValueError, match="missing required dataset"):
        ls8_mix.query_snapshot(manifest)
