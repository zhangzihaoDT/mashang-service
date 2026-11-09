import json
from datetime import datetime

import pandas as pd
import pytest

from jobs.ls8_mix import query_snapshot
from jobs.snapshot import copy_snapshot, verified_files


def test_generic_snapshot_feeds_ls8_mix_and_rejects_unverified_inputs(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    config = dataset / "config_attribute.parquet"
    pd.DataFrame([("a", "内饰", "大象灰黑", "IN2-ASH"), ("b", "内饰", "大象灰米", "IN2-AMA")],
                 columns=["Order Number", "Attribute", "value", "value_code"]).to_parquet(config)
    pd.DataFrame([
        ("LS8", "a", "智己LS8 52 Max+", "2026-04-16", None),
        ("LS8", "a", "智己LS8 52 Max+", "2026-04-16", None),
        ("LS8", "b", "智己LS8 93 RWD", "2026-04-18", None),
    ], columns=["series", "order_number", "product_name", "lock_time", "approve_refund_time"]
    ).to_parquet(dataset / "order_data.parquet")
    run_id = "dsh-" + "a" * 32
    receipt = tmp_path / "logs/production-jobs/records" / f"{run_id}.json"
    receipt.parent.mkdir(parents=True)
    record = {
        "run_id": run_id, "job": "data-refresh-config-attribute", "status": "verification_failed",
        "after": {"config_attribute": {"exists": True, "size_bytes": config.stat().st_size,
                                       "file_mtime": datetime.fromtimestamp(config.stat().st_mtime).isoformat()}},
    }
    receipt.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="did not pass verification"):
        verified_files(tmp_path, [run_id])
    record["status"] = "no_new_data"
    receipt.write_text(json.dumps(record))
    evidence = verified_files(tmp_path, [run_id])
    dest = tmp_path / "version"
    dest.mkdir()
    inputs = copy_snapshot(tmp_path, dest, ["config_attribute", "order_data"], evidence)
    assert inputs["order_data"]["data_asof"] == "2026-04-18T00:00:00"
    assert inputs["config_attribute"]["data_asof"] is None
    assert all((file.stat().st_mode & 0o222) == 0 for file in dest.glob("*.parquet"))

    manifest = dest / "snapshot.json"
    manifest.write_text(json.dumps({"version": dest.name, "datasets": inputs}))
    contract = query_snapshot(manifest)
    assert contract["status"] == "success"
    result = contract["result"]
    assert result["groups"]["增程"]["total_orders"] == result["groups"]["纯电"]["total_orders"] == 1
    assert result["groups"]["增程"]["colors"][0]["share"] == result["groups"]["纯电"]["colors"][0]["share"] == 1

    rejected = tmp_path / "rejected"
    rejected.mkdir()
    evidence["config_attribute"]["file_mtime"] = "changed"
    with pytest.raises(ValueError, match="does not match the verified refresh"):
        copy_snapshot(tmp_path, rejected, ["config_attribute", "order_data"], evidence)
    assert not list(rejected.iterdir())
