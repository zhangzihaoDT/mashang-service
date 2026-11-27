"""Validate managed refresh outputs before publishing and when reading a receipt."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

try:
    from .dataset_registry import _parse_dates
except ImportError:  # Updaters are also invoked as standalone scripts.
    from dataset_registry import _parse_dates

ASSIGN_DATE = "Assign Time 年/月/日"
DATA_CONTRACTS = {
    "order_data": (("order_number",), "lock_time", ("order_create_date", "product_name", "series", "order_type",
                   "approve_refund_time", "intention_payment_time", "intention_refund_time", "deposit_payment_time",
                   "deposit_refund_time", "buyer_identity_no", "owner_identity_no", "store_name")),
    "assign_data": ((ASSIGN_DATE,), ASSIGN_DATE, ("下发线索数",)),
    "lock_attribution": (("lc_user_phone_md5", "lc_main_code"), "lc_order_lock_time_min", ()),
}
MANAGED_VALIDATION = {
    "data-refresh-order-data": ("order_data",),
    "data-refresh-daily": ("order_data", "assign_data"),
    "data-refresh-lock-attribution": ("lock_attribution",),
}


def inspect_dataset(dataset: str, path: Path) -> dict:
    """Give structured, content-addressed evidence, including failures to read a file."""
    keys, date_field, extra = DATA_CONTRACTS[dataset]
    result = {"valid": False, "sha256": None, "validated_rows": None, "validated_cutoff": None,
              "validated_cutoff_column": date_field, "validation_error": None}
    try:
        if not path.is_file() or path.is_symlink():
            raise ValueError("Expected a regular data file")
        with path.open("rb") as stream:
            result["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
            stream.seek(0)
            frame = pd.read_csv(stream, low_memory=False) if dataset == "assign_data" else pd.read_parquet(stream)
        result["validated_rows"] = len(frame)
        if missing := set((*keys, date_field, *extra)) - set(frame.columns):
            raise ValueError(f"Missing required fields: {sorted(missing)}")
        if frame.empty:
            raise ValueError("Data file has no rows")
        dates = _parse_dates(frame[date_field])
        if not dates.notna().any() or (dates.isna() & frame[date_field].notna()).any():
            raise ValueError(f"Invalid or missing business cutoff in {date_field}")
        result["validated_cutoff"] = dates.max().isoformat()
        key_values = frame[list(keys)].astype("string").apply(lambda values: values.str.strip().replace("", pd.NA))
        if dataset == "assign_data":
            key_values[ASSIGN_DATE] = dates.dt.normalize()
        # Legacy attribution includes an unattributed row with a null phone hash.
        required_keys = keys[1:] if dataset == "lock_attribution" else keys
        if key_values[list(required_keys)].isna().any().any() or key_values.duplicated().any():
            raise ValueError(f"Primary key is empty or duplicated: {', '.join(keys)}")
        result["valid"] = True
    except Exception as exc:
        result["validation_error"] = f"{type(exc).__name__}: {exc}"
    return result


def validate_output(dataset: str, before: dict, after: dict) -> list[str]:
    if not after.get("valid"):
        return [f"{dataset}: {after.get('validation_error') or 'missing verification evidence'}"]
    findings = []
    for key, label in (("validated_rows", "row count"), ("validated_cutoff", "business cutoff")):
        if before.get(key) is not None and after[key] < before[key]:
            findings.append(f"{dataset}: {label} regressed ({before[key]} -> {after[key]})")
    return findings


def publish_dataset(dataset: str, path: Path, write) -> bool:
    """Stage a complete file beside its destination, validate, then atomically replace."""
    if path.is_symlink():
        raise ValueError(f"{dataset}: the published path must not be a symlink")
    before = inspect_dataset(dataset, path) if path.exists() else {}
    with TemporaryDirectory(prefix=f".{path.stem}-", dir=path.parent) as directory:
        staged = Path(directory) / path.name
        if write(staged) is False:
            return False
        after = inspect_dataset(dataset, staged)
        if problems := validate_output(dataset, before, after):
            raise ValueError("; ".join(problems))
        if before.get("sha256") == after["sha256"]:
            return True
        staged.chmod(stat.S_IMODE(path.stat().st_mode) if path.is_file() else 0o640)
        with staged.open("rb") as stream:
            os.fsync(stream.fileno())
        staged.replace(path)
    return True
