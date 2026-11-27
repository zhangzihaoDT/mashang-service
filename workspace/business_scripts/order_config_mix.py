"""Order configuration shares by generation or family on a verified copy snapshot."""

import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from workspace.utils.paths import ensure_shared_on_path, ensure_workspace_on_path

ensure_workspace_on_path()
ensure_shared_on_path()

from jobs.snapshot import read_verified_snapshot
from operators.product_attributes import NO_SEAT, UNCLASSIFIED, UNKNOWN, resolve_product_attributes
from utils.config_semantics import collapse_order_values, get_attribute_spec, resolve_value_code
from utils.monitors.launch import resolve_launch_open_from_data
from utils.orders.classification import apply_series_group_logic
from utils.orders.filters import flag_test_orders
from utils.snapshot_query import QueryError, calendar_date, run_cli, validate_request

SCRIPT = "workspace.business_scripts.order_config_mix"
METRICS = {
    "locked_orders": ("锁单量", "lock_time"),
    "retained_locked_orders": ("锁单量", "lock_time"),
    "delivered_orders": ("交付数", "delivery_date"),
    "invoiced_orders": ("开票数", "invoice_upload_time"),
}
WINDOWS = {"since_launch", "since_launch_open", "range", "all", "last_7_days", "last_30_days", "mtd", "ytd"}
DIMENSIONS = {"seat_count", "power_type", "product_version", "order_type"}
ORDER_TYPES = {"员工", "用户车", "享道", "集团员工", "试驾车", "大客户", "经销商员工", "仅批售", "项目", "展车", "海外"}
CONFIG_COLUMNS = ("Order Number", "Attribute", "value")
CONFIG_CODES = ("attribute_code", "value_code")
TEST_COLUMNS = ("store_name", "buyer_identity_no", "owner_identity_no")
SHARED_DEFINITIONS = ["business_definition", "metrics", "config_semantics"]


def _selection(request: dict, bdef: dict) -> list[str]:
    generations = bdef["series_group_logic"]
    if "family" in request:
        family = request["family"]
        if family not in bdef["model_series_mapping"]:
            raise QueryError("UNKNOWN_FAMILY", f"Unknown family: {family}")
        keys = bdef["model_series_mapping"][family]
    else:
        keys = [request["generation"]]
    if not keys or any(key == "其他" or key not in generations for key in keys):
        raise QueryError("UNKNOWN_GENERATION", f"Unknown generation selection: {keys}")
    return keys


def _window(orders, bdef, request, generations, field):
    window = request.get("time_window", "since_launch")
    times = orders[field]
    cutoff = times.max()
    if pd.isna(cutoff):
        raise QueryError("DATA_NOT_COVERED", f"No {field} timestamps for selected vehicle")
    last_day = cutoff.normalize()
    end = pd.Timestamp(calendar_date(request["end_date"])) if "end_date" in request else last_day
    end_exclusive = end + pd.Timedelta(days=1)
    observed = min(end_exclusive - pd.Timedelta(nanoseconds=1), cutoff)
    starts = {}
    if window == "range":
        start = pd.Timestamp(calendar_date(request["start_date"]))
    elif window in {"since_launch", "since_launch_open"}:
        for key in generations:
            launch = (bdef.get("time_periods", {}).get(key) or {}).get("end")
            if not launch:
                raise QueryError("LAUNCH_DATE_UNCONFIRMED", f"No confirmed launch date: {key}")
            start_day = pd.Timestamp(calendar_date(launch))
            starts[key] = (
                resolve_launch_open_from_data(orders, key, start_day, bdef=bdef)
                if window == "since_launch_open" else start_day
            )
        start = min(starts.values())
        if window == "since_launch":
            # Historical family Mix starts on the earliest launch day of the family.
            starts = dict.fromkeys(generations, start)
    elif window == "all":
        start = times.min().normalize()
    elif window in {"last_7_days", "last_30_days"}:
        start = last_day - pd.Timedelta(days=6 if window == "last_7_days" else 29)
    else:
        start = last_day.replace(day=1, month=1 if window == "ytd" else last_day.month)
    if start >= end_exclusive:
        code = "NOT_LAUNCHED" if starts else "INVALID_WINDOW"
        raise QueryError(code, "Window ends before its start")
    mask = times.le(observed) & times.ge(start)
    if starts:
        mask &= times.ge(orders["series_group_logic"].map(starts))
    scope = {
        "type": window, "field": field, "start": start.isoformat(),
        "end_inclusive": observed.isoformat(), "requested_end_date": end.date().isoformat(),
        "event_data_cutoff": cutoff.isoformat(), "timezone": "Asia/Shanghai",
        "generation_starts": {key: stamp.isoformat() for key, stamp in starts.items()},
    }
    return orders.loc[mask], scope, end > last_day


def _validate_options(request: dict) -> tuple[str, str, str]:
    validate_request(request, {"dimension"}, {
        "family", "generation", "metric", "time_window", "start_date", "end_date",
        "order_type", "test_drives", "internal_test_orders", "group_by", "power_type",
    })
    if ("family" in request) == ("generation" in request):
        raise QueryError("INVALID_REQUEST", "Provide exactly one of generation and family")
    metric = request.get("metric", "locked_orders")
    if metric not in METRICS:
        raise QueryError("UNKNOWN_METRIC", f"Unsupported metric: {metric}")
    window = request.get("time_window", "since_launch")
    if window not in WINDOWS:
        raise QueryError("INVALID_WINDOW", f"Unsupported window: {window}")
    if ("start_date" in request) != (window == "range") or (window == "range" and "end_date" not in request):
        raise QueryError("INVALID_WINDOW", "A range requires both dates; only range accepts start_date")
    if "end_date" in request and window not in {"range", "since_launch", "since_launch_open"}:
        raise QueryError("INVALID_WINDOW", "end_date only applies to range or a launch-based window")
    dates = {key: calendar_date(request[key]) for key in ("start_date", "end_date") if key in request}
    if window == "range" and dates["start_date"] > dates["end_date"]:
        raise QueryError("INVALID_WINDOW", "Start date is later than end date")
    test_drives = request.get("test_drives", "include")
    internal = request.get("internal_test_orders", "exclude" if window == "since_launch_open" else "include")
    if test_drives not in {"include", "exclude"} or internal not in {"include", "exclude"}:
        raise QueryError("INVALID_REQUEST", "Order exclusion enums are include or exclude")
    if window == "since_launch_open" and (metric not in {"locked_orders", "retained_locked_orders"} or internal != "exclude"):
        raise QueryError("INVALID_WINDOW", "Launch opening requires a lock metric and internal-test exclusion")
    order_type = request.get("order_type")
    if order_type is not None and (order_type not in ORDER_TYPES or order_type == "试驾车" and test_drives == "exclude"):
        raise QueryError("INVALID_ORDER_TYPE", f"Unsupported or conflicting order type: {order_type}")
    if "group_by" in request and request["group_by"] != "power_type":
        raise QueryError("INVALID_GROUPING", "Only power_type grouping is supported")
    if "power_type" in request and request["power_type"] not in {"增程", "纯电"}:
        raise QueryError("INVALID_GROUPING", "power_type must be 增程 or 纯电")
    if request["dimension"] != "seat_count" and ("group_by" in request or "power_type" in request):
        raise QueryError("INVALID_GROUPING", "Power grouping and filtering apply to seat_count")
    return metric, test_drives, internal


def _read_config(path: Path, order_ids) -> pd.DataFrame:
    schema = pq.ParquetFile(path).schema_arrow
    if missing := set(CONFIG_COLUMNS) - set(schema.names):
        raise QueryError("INVALID_INPUT_DATA", f"Configuration is missing fields: {sorted(missing)}")
    columns = [*CONFIG_COLUMNS, *(name for name in CONFIG_CODES if name in schema.names)]
    key_type = schema.field("Order Number").type
    filters = [("Order Number", "in", order_ids.tolist())] if (
        pa.types.is_string(key_type) or pa.types.is_large_string(key_type)
    ) else None
    config = pd.read_parquet(path, columns=columns, filters=filters)
    config = config.reindex(columns=[*CONFIG_COLUMNS, *CONFIG_CODES]).astype("string")
    config = config.loc[config["Order Number"].isin(order_ids)].drop_duplicates()
    for column in ("Attribute", "value", *CONFIG_CODES):
        config[column] = config[column].str.strip().replace("", pd.NA)
    return config


def _attribute_rows(config: pd.DataFrame, dimension: str, registered_names: set[str]):
    if dimension.startswith("config:"):
        name = dimension.removeprefix("config:")
        if not config["attribute_code"].eq(name).any():
            raise QueryError("UNKNOWN_DIMENSION", f"Unobserved attribute code: {name}")
        code = name
    else:
        name, code = dimension, None
    if code is None:
        named = config["Attribute"].eq(name)
        codes = config.loc[named, "attribute_code"].dropna().unique()
        if len(codes) > 1:
            raise QueryError("AMBIGUOUS_DIMENSION", f"{name} has multiple attribute codes: {sorted(codes)}")
        if not named.any() and name not in registered_names:
            raise QueryError("UNKNOWN_DIMENSION", f"Unregistered or unobserved configuration dimension: {dimension}")
        code = codes[0] if len(codes) else None
    if code is None:
        return config.loc[config["Attribute"].eq(name)], name, None

    coded = config["attribute_code"].eq(code)
    aliases = config.loc[coded, "Attribute"].dropna().unique()
    ambiguous_aliases = config.loc[config["attribute_code"].notna() & ~coded, "Attribute"]
    safe_aliases = set(aliases) - set(ambiguous_aliases)
    legacy = config["attribute_code"].isna() & config["Attribute"].isin(safe_aliases)
    return config.loc[coded | legacy], name, str(code)


def _seat_label(code: str, value: str) -> str | None:
    code = code.casefold()
    if code in {"five", "5", "f"}:
        return "五座"
    if code in {"six", "6", "s"}:
        return "六座"
    if "五座" in value or "5座" in value:
        return "五座"
    if "六座" in value or "6座" in value:
        return "六座"
    return None


def _config_values(rows: pd.DataFrame, seats: bool, definitions: dict):
    """Normalize by generation-specific semantics and then by stable value code."""
    result = []
    for row in rows.fillna("").itertuples(index=False, name=None):
        order, attribute, value, code, generation = row
        if seats:
            label = _seat_label(code, value)
            if label:
                result.append((order, label, label))
            continue
        spec = get_attribute_spec(definitions, generation, attribute)
        if spec.get("semantic") == "noise":
            continue
        normalized_code, label = resolve_value_code(spec, code or None, value)
        if code and value and not normalized_code:
            guessed, display = resolve_value_code(spec, None, value)
            if guessed:
                normalized_code, label = guessed, display
        if spec.get("semantic") == "boolean" and normalized_code:
            label = "含" if spec["codes"][normalized_code].get("included", True) else "不含"
            result.append((order, label, label))
        elif code.casefold() in {"y", "yes", "true", "1"} or value == "是":
            result.append((order, "含", "含"))
        elif code.casefold() in {"n", "no", "false", "0"} or value in {"否", "无", "未选", "不选"}:
            result.append((order, "不含", "不含"))
        elif label or value or code:
            key = normalized_code or code or value
            result.append((order, key, label or value or code))

    values = pd.DataFrame(result, columns=["order", "key", "label"])
    by_order, conflicts = collapse_order_values(values["order"], values["key"])
    # Pick the most frequent display for a code, breaking ties lexically.
    display = values.groupby("key")["label"].agg(lambda labels: labels.mode().min())
    return by_order.map(display), conflicts


def _summary(labels: pd.Series, conflicts: pd.Series) -> dict:
    counts = labels.loc[~conflicts].dropna().value_counts()
    pairs = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    total, known = len(labels), int(counts.sum())
    conflict_count = int(conflicts.sum())
    return {
        "total_orders": total,
        "known_orders": known,
        "missing_orders": total - known - conflict_count,
        "conflict_orders": conflict_count,
        "coverage": known / total if total else None,
        "groups": [
            {"value": value, "count": int(count), "share_of_known": count / known, "share_of_total": count / total}
            for value, count in pairs
        ],
    }


def query(manifest: Path, request: dict, definition_version: str | None = None) -> tuple[dict, dict, list]:
    metric, test_drives, internal = _validate_options(request)
    dimension = request["dimension"]
    config_needed = dimension not in DIMENSIONS or dimension == "seat_count"
    datasets = ["order_data", "config_attribute"] if config_needed else ["order_data"]
    scope, paths, definitions = read_verified_snapshot(manifest, datasets, SHARED_DEFINITIONS, definition_version)
    bdef = definitions["business_definition"]
    generations = _selection(request, bdef)
    metric_name, field = METRICS[metric]
    metric_spec = definitions["metrics"]["metrics"][metric_name]
    if metric_spec.get("agg") != "count" or metric_spec.get("field") != "order_number" or metric_spec.get("dataset") != "order_data":
        raise QueryError("INVALID_INPUT_DATA", "Pinned metric must count order numbers")
    if metric_spec.get("time_field") != field or metric_spec.get("extra_filters") != [
        {"field": field, "op": "!=", "value": None}
    ]:
        raise QueryError("DEFINITION_VERSION_MISMATCH", "Pinned metric event or filters differ from the V1 contract")
    columns = ["order_number", "product_name", "order_type", field]
    if metric == "retained_locked_orders":
        columns.append("approve_refund_time")
    if internal == "exclude":
        columns.extend(TEST_COLUMNS)
    if request.get("time_window") == "since_launch_open":
        columns.append("intention_payment_time")
    orders = pd.read_parquet(paths["order_data"], columns=columns)
    if orders.empty:
        raise QueryError("DATA_NOT_COVERED", "Order data is empty")
    orders["order_number"] = orders["order_number"].astype("string").str.strip()
    for column in (field, "intention_payment_time", "approve_refund_time"):
        if column in orders:
            orders[column] = pd.to_datetime(orders[column], errors="raise")
    orders = apply_series_group_logic(orders, bdef)
    orders = orders.loc[orders["series_group_logic"].isin(generations)]
    if internal == "exclude":
        orders = orders.loc[~flag_test_orders(orders, bdef)]
    eligible, time_scope, capped = _window(orders, bdef, request, generations, field)
    if metric == "retained_locked_orders":
        eligible = eligible.loc[eligible["approve_refund_time"].isna()]
    if "order_type" in request:
        eligible = eligible.loc[eligible["order_type"].astype("string").eq(request["order_type"])]
    if test_drives == "exclude":
        eligible = eligible.loc[~eligible["order_type"].astype("string").eq("试驾车").fillna(False)]
    eligible = eligible.loc[eligible["order_number"].notna() & eligible["order_number"].ne("")]
    scoped = eligible.drop_duplicates("order_number").copy()
    if scoped.empty:
        raise QueryError("NO_ORDERS", "No orders satisfy the requested window and filters")

    warnings = []
    attrs = None
    if dimension in {"seat_count", "power_type", "product_version"}:
        attrs = resolve_product_attributes(scoped, bdef)
    if request.get("power_type"):
        scoped = scoped.loc[attrs.power_type.eq(request["power_type"])]
    if scoped.empty:
        raise QueryError("NO_ORDERS", "No orders match the requested power type")

    conflict_ids = set()
    matched_cutoff = None
    attribute_code = None
    if config_needed:
        config = _read_config(paths["config_attribute"], pd.Index(scoped["order_number"]))
        seats = dimension == "seat_count"
        if seats:
            coded = config["attribute_code"].eq("OP-Seat").fillna(False)
            legacy = config["attribute_code"].isna() & config["Attribute"].eq("座椅")
            rows = config.loc[coded | legacy]
            attribute_code = "OP-Seat"
        else:
            registered = set().union(*(series["attributes"].keys() for key, series in definitions["config_semantics"]["series"].items()
                if key in generations or set(bdef["model_series_mapping"].get(key, ())) & set(generations)))
            rows, dimension, attribute_code = _attribute_rows(config, dimension, registered)
        rows = rows[["Order Number", "Attribute", "value", "value_code"]].copy()
        rows["generation"] = rows["Order Number"].map(scoped.set_index("order_number")["series_group_logic"])
        cfg_labels, conflict_ids = _config_values(rows, seats, definitions["config_semantics"])
        labels = scoped["order_number"].map(cfg_labels)
        matched = labels.notna() | scoped["order_number"].isin(conflict_ids)
        matched_time = scoped.loc[matched, field].max()
        matched_cutoff = matched_time.isoformat() if pd.notna(matched_time) else None
        if seats:
            labels = labels.fillna(attrs.seat_count.reindex(scoped.index).replace(NO_SEAT, pd.NA))
    elif dimension == "order_type":
        labels = scoped["order_type"].astype("string").str.strip().replace("", pd.NA)
    elif dimension == "power_type":
        labels = attrs.power_type.replace(UNKNOWN, pd.NA)
    else:
        labels = attrs.version.replace(UNCLASSIFIED, pd.NA)

    conflicts = scoped["order_number"].isin(conflict_ids)
    result = _summary(labels, conflicts)
    if request.get("group_by"):
        result["by_power_type"] = [
            {"power_type": power, **_summary(labels.loc[group.index], conflicts.loc[group.index])}
            for power, group in scoped.groupby(attrs.power_type, sort=True)
        ]
    result.update(
        dimension=dimension, attribute_code=attribute_code,
        latest_matched_config_event_time=matched_cutoff,
        config_file_mtime=scope["inputs"].get("config_attribute", {}).get("file_mtime"),
        duplicate_order_rows_removed=len(eligible) - len(eligible.drop_duplicates("order_number")),
    )
    if result["missing_orders"] or result["conflict_orders"]:
        warnings.append({"code": "CONFIG_INCOMPLETE", "message": "Some dimension values are missing or conflicting"})
    if capped:
        warnings.append({"code": "AS_OF_CAPPED", "message": "End date exceeds the selected vehicle event cutoff day"})
    scope.update(
        time_window=time_scope,
        filters={**request, "generation_keys": generations, "test_drives": test_drives, "internal_test_orders": internal},
        metric_definition={"id": metric, "event_field": field,
                           "retention_basis": "snapshot_refund_status" if metric == "retained_locked_orders" else None},
    )
    return scope, result, warnings


if __name__ == "__main__":
    raise SystemExit(run_cli(SCRIPT, query))
