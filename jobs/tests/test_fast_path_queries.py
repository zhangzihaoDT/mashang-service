import json
import subprocess
import sys
from pathlib import Path
from shutil import copyfile

import pandas as pd
import pytest

from jobs.snapshot import file_sha256
from workspace.business_scripts import launch_lock_summary, order_config_mix
from utils.snapshot_query import QueryError

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def snapshot(tmp_path):
    root = tmp_path / "edition1"
    root.mkdir()
    manifest = root / "snapshot.json"
    definition_dir = root / "definitions"
    definition_dir.mkdir()
    entries = {"version": root.name, "manifest_version": 1, "mode": "copy", "datasets": {}, "definitions": {}}

    def pin(path):
        path.chmod(0o444)
        return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": file_sha256(path)}

    for key in ("business_definition", "config_semantics", "metrics"):
        target = definition_dir / f"{key}.json"
        copyfile(ROOT / "shared" / "schema" / target.name, target)
        entries["definitions"][key] = pin(target)

    def build(orders, config=None):
        frame = pd.DataFrame(orders, columns=["order_number", "lock_time", "product_name", "order_type",
                                              "approve_refund_time", "intention_payment_time", "store_name", "buyer_identity_no"])
        for column in ("lock_time", "approve_refund_time", "intention_payment_time"):
            frame[column] = pd.to_datetime(frame[column], format="mixed")
        for column in ("intention_refund_time", "deposit_refund_time", "deposit_payment_time"):
            frame[column] = pd.NaT
        frame["owner_identity_no"] = "310101199001011234"
        orders_path = root / "order_data.parquet"
        frame.to_parquet(orders_path, index=False)
        entries["datasets"]["order_data"] = pin(orders_path)
        if config is not None:
            config_path = root / "config_attribute.parquet"
            pd.DataFrame(config, columns=["Order Number", "Attribute", "attribute_code", "value_code", "value"]).to_parquet(config_path)
            entries["datasets"]["config_attribute"] = pin(config_path)
        manifest.write_text(json.dumps(entries))
        return manifest

    return build


def order(key, timestamp, product="智己LS8 52 Ultra", order_type="用户车", approved=None, intention=None, test=False):
    return (key, timestamp, product, order_type, approved, intention, "总部主理店" if test else "fixture",
            "123" if test else "310101199001011234")


def test_mix_counts_events_and_distinguishes_internal_test_drive_and_conflicts(snapshot):
    manifest = snapshot([
        order("a", "2026-04-16 13:00:00", approved="2026-04-20"),
        order("b", "2026-04-17 22:23:00", order_type="试驾车"),
        order("c", "2026-04-17 22:24:00", test=True),
        order("d", "2026-04-17 22:26:00"),
        order("e", "2026-04-17 22:27:00"),
        order("e", "2026-04-17 22:27:00"),
    ], [
        ("a", "内饰", "INCOLOR", "IN2-AMA", "象灰米"),
        ("b", "内饰", "INCOLOR", "IN2-AMA", "象灰米"),
        ("c", "客舱内饰", "INCOLOR", "IN2-AMA", "象灰米"),
        ("d", "内饰", "INCOLOR", "IN2-AMA", "象灰米"),
        ("d", "客舱内饰", "INCOLOR", "IN2-BLJ", "全黑"),
    ])
    params = {"generation": "LS8", "dimension": "config:INCOLOR", "time_window": "range",
              "start_date": "2026-04-16", "end_date": "2026-04-17"}
    scope, result, _ = order_config_mix.query(manifest, params)
    assert result["total_orders"] == 5
    assert result["known_orders"] == 3
    assert result["conflict_orders"] == result["missing_orders"] == 1
    assert result["coverage"] == 0.6
    assert result["groups"][0]["share_of_known"] == 1
    assert result["groups"][0]["share_of_total"] == 0.6
    assert result["duplicate_order_rows_removed"] == 1
    assert scope["time_window"]["end_inclusive"] == "2026-04-17T22:27:00"

    for filter_name in ("test_drives", "internal_test_orders"):
        _, filtered, _ = order_config_mix.query(manifest, {**params, filter_name: "exclude"})
        assert filtered["known_orders"] == 2
        assert filtered["total_orders"] == 4
    scope, retained, _ = order_config_mix.query(manifest, {**params, "metric": "retained_locked_orders"})
    assert retained["total_orders"] == 4
    assert scope["metric_definition"]["retention_basis"] == "snapshot_refund_status"


def test_mix_family_and_opening_are_explicit(snapshot):
    manifest = snapshot([
        order("early", "2026-04-16 12:00:00"),
        order("open", "2026-04-16 20:00:00", intention="2026-04-16 19:00:00"),
        order("neo", "2026-11-05 21:00:00", product="智己LS8 NEO 103 Max", intention="2026-11-04"),
    ], [
        ("early", "座椅", "OP-Seat", "Five", "5座"),
        ("open", "座椅布局", "OP-Seat", "Six", "六座"),
        ("neo", "座椅", None, "Five", "五座"),
    ])
    _, natural, _ = order_config_mix.query(manifest, {"generation": "LS8", "dimension": "seat_count"})
    assert natural["total_orders"] == 2
    scope, opened, _ = order_config_mix.query(
        manifest, {"family": "LS8", "dimension": "seat_count", "time_window": "since_launch_open"}
    )
    assert opened["total_orders"] == 2
    assert scope["time_window"]["generation_starts"]["LS8"] == "2026-04-16T20:00:00"
    assert {row["value"] for row in opened["groups"]} == {"五座", "六座"}


def test_launch_contract_retention_and_fill(snapshot):
    manifest = snapshot([
        order("prior", "2025-11-11 16:00:00", product="智己LS8"),
        order("before_open", "2025-11-12 12:00:00", product="智己LS9"),
        order("open", "2025-11-12 16:53:23", product="智己LS9", intention="2025-11-12"),
        order("refund_later", "2026-01-05 10:00:00", product="智己LS9", approved="2026-02-03", order_type=None),
        order("refund_on_day", "2026-01-06 10:00:00", product="智己LS9", approved="2026-01-31 23:59:59", order_type=None),
        order("test", "2026-01-06 11:00:00", product="智己LS9", test=True),
        order("unrelated", "2026-02-10 12:00:00", product="智己LS8"),
    ])
    request = {"generation": "LS9", "as_of": "2026-01-31"}
    scope, result, warnings = launch_lock_summary.query(manifest, request)
    assert result["launch_open_at"] == "2025-11-12T16:53:23"
    assert result["launch_open_source"] == "first_qualifying_lock"
    assert result["lock_cutoff"] == "2026-01-31T23:59:59"
    assert result["cumulative_lock_count"] == 3
    assert result["user_car_lock_count"] == 1
    assert result["order_type_filled_ratio"] == pytest.approx(1 / 3)
    assert result["user_car_share"] is None
    assert warnings[0]["code"] == "ORDER_TYPE_INCOMPLETE"
    assert result["retained_lock_count"] == 1
    assert result["retention_basis"] == "snapshot_refund_status"
    assert launch_lock_summary.query(manifest, request, scope["definition_version"])[1] == result
    _, pit, _ = launch_lock_summary.query(manifest, {**request, "retention_basis": "refund_approval_as_of"})
    assert pit["retained_lock_count"] == 2


@pytest.mark.parametrize(("parameters", "code"), [
    ({"generation": "BOGUS"}, "UNKNOWN_GENERATION"),
    ({"generation": "LS9", "as_of": "2025-11-11"}, "NOT_LAUNCHED"),
    ({"generation": "LS9", "as_of": "2026-02-30"}, "INVALID_DATE"),
    ({"generation": "LS9", "refresh": True}, "INVALID_REQUEST"),
    ({"generation": "LS9M1", "as_of": "2026-12-18"}, "DATA_NOT_COVERED"),
])
def test_launch_rejects_invalid_or_uncovered(snapshot, parameters, code):
    manifest = snapshot([order("one", "2025-11-11"), order("two", "2026-01-02")])
    with pytest.raises(QueryError) as error:
        launch_lock_summary.query(manifest, parameters)
    assert error.value.code == code


def test_launch_true_zero_has_valid_window(snapshot):
    manifest = snapshot([order("before", "2025-11-11"), order("after", "2025-11-13")])
    _, result, warnings = launch_lock_summary.query(manifest, {"generation": "LS9", "as_of": "2025-11-12"})
    assert result["cumulative_lock_count"] == 0 and result["user_car_share"] is None
    assert result["launch_open_source"] == "launch_day_start_fallback"
    assert warnings == []


@pytest.mark.parametrize(("change", "code"), [
    ("missing_config", "SNAPSHOT_DEPENDENCY_MISSING"),
    ("same_size_mutation", "SNAPSHOT_HASH_MISMATCH"),
    ("writable", "SNAPSHOT_INVALID"),
    ("wrong_version", "DEFINITION_VERSION_MISMATCH"),
    ("bad_metric", "UNKNOWN_METRIC"),
    ("bad_date", "INVALID_DATE"),
    ("extra_key", "INVALID_REQUEST"),
])
def test_mix_cli_errors_are_structured(snapshot, change, code):
    config = [] if change != "missing_config" else None
    manifest = snapshot([order("order", "2026-04-17")], config)
    request = {"generation": "LS8", "dimension": "seat_count"}
    args = []
    if change in {"same_size_mutation", "writable"}:
        file = manifest.parent / "config_attribute.parquet"
        file.chmod(0o644)
        if change == "same_size_mutation":
            file.write_bytes(b"!" + file.read_bytes()[1:])
            file.chmod(0o444)
    elif change == "wrong_version":
        args = ["--definition-version", "0" * 64]
    elif change == "bad_metric":
        request["metric"] = "retained_locked_orders_typo"
    elif change == "bad_date":
        request.update(time_window="range", start_date="2026-04-32", end_date="2026-05-01")
    elif change == "extra_key":
        request["snapshot_dir"] = "/tmp"
    finished = subprocess.run(
        [sys.executable, "-B", "-m", order_config_mix.SCRIPT, "--snapshot", str(manifest),
         "--request", json.dumps(request), *args], cwd=ROOT, capture_output=True, text=True,
    )
    assert finished.returncode == 1
    assert json.loads(finished.stdout)["errors"][0]["code"] == code
