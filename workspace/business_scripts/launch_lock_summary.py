"""Query the official cumulative launch lock metrics on a verified copy snapshot."""

import sys
from pathlib import Path

import pandas as pd

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from workspace.utils.paths import ensure_workspace_on_path

ensure_workspace_on_path()

from jobs.snapshot import read_verified_snapshot
from utils.monitors import launch
from utils.orders.classification import apply_series_group_logic
from utils.snapshot_query import QueryError, calendar_date, run_cli, validate_request

SCRIPT = "workspace.business_scripts.launch_lock_summary"
DATE_COLUMNS = (
    "lock_time", "approve_refund_time", "intention_payment_time",
    "intention_refund_time", "deposit_payment_time", "deposit_refund_time",
)
ORDER_COLUMNS = (
    *DATE_COLUMNS, "order_number", "product_name", "order_type",
    "buyer_identity_no", "owner_identity_no", "store_name",
)


def query(manifest: Path, request: dict, definition_version: str | None = None) -> tuple[dict, dict, list]:
    validate_request(request, {"generation"}, {"as_of", "retention_basis"})
    generation = request["generation"]
    as_of = pd.Timestamp(calendar_date(request["as_of"])) if "as_of" in request else None
    basis = request.get("retention_basis", launch.SNAPSHOT_REFUND_STATUS)
    if basis not in {launch.SNAPSHOT_REFUND_STATUS, launch.REFUND_APPROVAL_AS_OF}:
        raise QueryError("INVALID_RETENTION_BASIS", f"Unsupported retention basis: {basis}")
    scope, inputs, rules = read_verified_snapshot(manifest, ["order_data"], ["business_definition"], definition_version)
    bdef = rules["business_definition"]
    if generation == "其他" or generation not in bdef.get("series_group_logic", {}):
        raise QueryError("UNKNOWN_GENERATION", f"Expected one registered generation: {generation}")
    listing = (bdef.get("time_periods", {}).get(generation) or {}).get("end")
    if not listing:
        raise QueryError("LAUNCH_DATE_UNCONFIRMED", f"No confirmed launch date: {generation}")
    launch_date = pd.Timestamp(calendar_date(listing))
    if as_of is not None and as_of < launch_date:
        raise QueryError("NOT_LAUNCHED", f"{generation} launches on {listing}")

    orders = pd.read_parquet(inputs["order_data"], columns=list(ORDER_COLUMNS))
    for column in DATE_COLUMNS:
        orders[column] = pd.to_datetime(orders[column], errors="raise")
    if not orders["lock_time"].notna().any():
        raise QueryError("DATA_NOT_COVERED", "No valid lock timestamps in snapshot")
    orders = apply_series_group_logic(orders, bdef)
    try:
        metrics = launch.compute(orders, bdef, as_of, generation, include_checks=True, retention_basis=basis)
    except ValueError as exc:
        if str(exc) != "No valid lock timestamps in snapshot":
            raise
        raise QueryError("DATA_NOT_COVERED", str(exc)) from exc

    source_cutoff = pd.Timestamp(metrics["lock_data_cutoff"])
    source_start = pd.Timestamp(metrics["lock_data_start"])
    if source_cutoff < launch_date or source_start.normalize() > launch_date:
        raise QueryError("DATA_NOT_COVERED", f"Snapshot lock data does not cover launch on {listing}")
    if pd.Timestamp(metrics["lock_cutoff"]) < pd.Timestamp(metrics["launch_open_at"]):
        raise QueryError("LAUNCH_NOT_OPEN", "The observation window ends before launch opening")
    if any(check["status"] != "passed" for check in metrics["checks"].values()):
        raise QueryError("METRIC_CHECK_FAILED", "Official launch denominator checks failed")

    scope.update(
        time_window={"start": metrics["launch_open_at"], "end": metrics["lock_cutoff"], "timezone": "Asia/Shanghai"},
        filters={"generation": generation, "internal_test_orders": "exclude"},
        metric_definition="Distinct order_number locked in the official launch window",
    )
    warnings = []
    if as_of is not None and as_of > source_cutoff.normalize():
        warnings.append({"code": "AS_OF_CAPPED", "message": "Requested day is newer than the latest available lock data"})
    total = metrics["cumulative_lock_count"]
    user_cars = metrics["cumulative_user_car_lock_count"]
    fill = metrics["order_type_filled_ratio"] if total else None
    fully_reportable = total and fill >= launch.ORDER_TYPE_FILL_SUPPRESS_RATIO
    if total and fill < 1:
        warnings.append({"code": "ORDER_TYPE_INCOMPLETE", "message": "Some cumulative locks have no order type"})

    result = {
        "generation": generation,
        "launch_date": listing,
        "launch_open_at": metrics["launch_open_at"],
        "launch_open_source": metrics["launch_open_source"],
        "requested_as_of": metrics["run_date"],
        "lock_data_cutoff": metrics["lock_data_cutoff"],
        "lock_cutoff": metrics["lock_cutoff"],
        "cumulative_lock_count": total,
        "user_car_lock_count": user_cars,
        "user_car_share": user_cars / total if fully_reportable else None,
        "retained_lock_count": metrics["retention_kept"],
        "retention_basis": basis,
        "order_type_filled_count": metrics["order_type_filled_count"],
        "order_type_filled_ratio": fill,
        "test_orders_excluded": metrics["test_orders_excluded"],
        "checks": metrics["checks"],
    }
    return scope, result, warnings


if __name__ == "__main__":
    raise SystemExit(run_cli(SCRIPT, query))
