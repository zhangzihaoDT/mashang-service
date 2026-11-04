#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Staging, validation and transaction publish for the TP&MIX-ways dataset.

Formal ``raw_csv`` is the historical source of truth. A Tableau export is
date-window scoped (2026-11-03 exported only 2026-08..2026-09) and its column
order is not stable, so an export must never replace the formal raw files
directly. The update contract is::

    export                  -> staging/runs/<run_id>/increment/raw_csv
    formal raw + increment  -> staging/runs/<run_id>/merged/raw_csv
    merged raw              -> staging/runs/<run_id>/derived/{parquet,registry,quality}
    validate every staged layer (columns / keys / months / values / cross-layer)
    snapshot destinations   -> staging/backups/<run_id>/
    one transaction         -> replace raw_csv + parquet + registry + quality
    failure                 -> restore every file this transaction replaced

``os.replace`` is atomic **per file**; it does not give the whole dataset a
single atomic visibility point. The transaction manifest is the recovery
record: an incomplete ``publishing`` manifest is rolled back from the backup
snapshot by the next update before it starts.

Readers accept the stored UTF-8 (no BOM) comma-delimited format and legacy
UTF-16 LE / tab-delimited exports. Writers always emit UTF-8 (no BOM),
comma-delimited, CRLF, preserving every cell as text.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_tp_and_mix_ways_dataset import (  # noqa: E402
    COLUMN_ALIASES,
    COLUMN_MAP,
    GRAIN_DEFS,
    PARQUET_FILENAMES,
    SOURCE_MAP,
)

DATE_COLUMN = "日期 年/月"
MEASURE_NAME_COLUMN = "度量名称"
MEASURE_VALUE_COLUMN = "度量值"
REQUIRED_MEASURE = "销量"
KNOWN_MEASURES = {
    "销量",
    "TP重心",
    "加权长(mm)",
    "加权宽(mm)",
    "加权高(mm)",
    "加权轴距(mm)",
}
_MONTH_RE = re.compile(r"(\d{4})年(\d{1,2})月")

DEFAULT_MAX_MONTH_DELETION_RATIO = 0.5
LOCK_FILENAME = ".update.lock"
STALE_LOCK_SECONDS = 24 * 60 * 60
TRANSACTION_MANIFEST_NAME = "transaction_manifest.json"
EXPECTED_DERIVED_FILES = [
    *(f"parquet/{filename}" for filename in PARQUET_FILENAMES.values()),
    "registry/tp_and_mix_ways_tables.json",
    "quality/tp_and_mix_ways_dataset_quality.md",
    "quality/tp_and_mix_ways_dataset_quality.json",
]


class RawContractError(RuntimeError):
    """A staged or merged raw snapshot violates the dataset contract."""

    def __init__(
        self,
        message: str,
        *,
        table: str | None = None,
        issues: Sequence[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.table = table
        self.issues = list(issues or [])


@dataclass
class PivotSnapshot:
    path: Path
    header: List[str]
    rows: List[Dict[str, str]]
    encoding: str
    delimiter: str


@dataclass
class MergeResult:
    table_name: str
    filename: str
    header: List[str]
    rows: List[Dict[str, str]]
    stats: Dict[str, Any] = field(default_factory=dict)


# ── CSV IO ────────────────────────────────────────────────────────


def detect_csv_dialect(path: Path) -> tuple[str, str]:
    """Detect the stored raw format without decoding the whole file."""
    prefix = path.read_bytes()[:4]
    if prefix[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16", "\t"
    if prefix[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig", ","
    return "utf-8", ","


def normalize_header_cell(value: str) -> str:
    name = value.lstrip("\ufeff").strip()
    return COLUMN_ALIASES.get(name, name)


def read_pivot_csv(path: Path) -> PivotSnapshot:
    if not path.is_file():
        raise RawContractError(f"raw CSV 不存在: {path}")
    encoding, delimiter = detect_csv_dialect(path)
    with open(path, encoding=encoding, newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        try:
            raw_header = next(reader)
        except StopIteration:
            raise RawContractError(f"{path.name}: 文件为空") from None
        header = [normalize_header_cell(cell) for cell in raw_header]
        if len(set(header)) != len(header):
            raise RawContractError(f"{path.name}: 表头规范化后存在重复列: {header}")
        rows: List[Dict[str, str]] = []
        for line_no, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) != len(header):
                raise RawContractError(
                    f"{path.name}:{line_no}: 列数 {len(row)} 与表头 {len(header)} 不一致"
                )
            rows.append(dict(zip(header, row)))
    if not rows:
        raise RawContractError(f"{path.name}: 没有数据行")
    return PivotSnapshot(
        path=path,
        header=header,
        rows=rows,
        encoding=encoding,
        delimiter=delimiter,
    )


def write_pivot_csv(path: Path, header: Sequence[str], rows: Iterable[Mapping[str, str]]) -> None:
    """Write UTF-8 (no BOM), comma-delimited, CRLF via atomic replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)  # default lineterminator="\r\n"
        writer.writerow(list(header))
        for row in rows:
            writer.writerow([row.get(column, "") for column in header])
    os.replace(tmp_path, path)


def canonical_columns(table_name: str) -> List[str]:
    return [raw_name.strip() for raw_name, _ in COLUMN_MAP[table_name]]


@lru_cache(maxsize=None)
def raw_grain_columns(table_name: str) -> Tuple[str, ...]:
    """Map the English schema grain to the raw Chinese pivot headers."""
    grain = set(GRAIN_DEFS[table_name])
    return tuple(
        raw_name.strip()
        for raw_name, english_name in COLUMN_MAP[table_name]
        if english_name in grain
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ── month / value helpers ─────────────────────────────────────────


def month_key(raw: str) -> Tuple[int, int]:
    text = raw.strip()
    match = _MONTH_RE.fullmatch(text)
    if match is None:
        hyphen_match = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
        if hyphen_match is None:
            raise ValueError(f"无法解析月份: {raw!r}")
        match = hyphen_match
    year, month = int(match.group(1)), int(match.group(2))
    if not (2010 <= year <= 2100 and 1 <= month <= 12):
        raise ValueError(f"月份超出合理范围: {raw!r}")
    return year, month


def format_month(key: Tuple[int, int]) -> str:
    return f"{key[0]:04d}-{key[1]:02d}"


def _to_float(value: str) -> Optional[float]:
    cleaned = str(value).strip().replace(",", "").replace(" ", "")
    if cleaned in ("", "-"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _measure_values_equal(left: str, right: str) -> bool:
    if left.strip() == right.strip():
        return True
    left_num, right_num = _to_float(left), _to_float(right)
    return left_num is not None and right_num is not None and left_num == right_num


def _primary_key(table_name: str, row: Mapping[str, str]) -> Tuple[str, ...]:
    dims = tuple(row[column].strip() for column in raw_grain_columns(table_name))
    return dims + (row[MEASURE_NAME_COLUMN].strip(),)


def _normalize_required_months(
    required_months_by_table: Optional[Mapping[str, Iterable[Any]]],
) -> Dict[str, set[str]]:
    normalized: Dict[str, set[str]] = {}
    for table_name, months in (required_months_by_table or {}).items():
        keys: set[str] = set()
        for month in months:
            if isinstance(month, str):
                keys.add(format_month(month_key(month)))
            elif isinstance(month, (tuple, list)) and len(month) == 2:
                keys.add(format_month((int(month[0]), int(month[1]))))
            else:
                keys.add(format_month(month_key(str(month))))
        normalized[table_name] = keys
    return normalized


def required_months_from_parquet(
    parquet_dir: Path, *, require_complete: bool = True
) -> Dict[str, set[str]]:
    """Read baseline month coverage; incomplete baselines are an error."""
    parquet_dir = Path(parquet_dir)
    if not parquet_dir.is_dir():
        return {}
    missing_files = [
        filename
        for filename in PARQUET_FILENAMES.values()
        if not (parquet_dir / filename).is_file()
    ]
    if missing_files and require_complete:
        raise RawContractError(f"正式 parquet 基线不完整，缺少: {missing_files}")
    import pandas as pd  # local import: guard is also used by lightweight tests

    months_by_table: Dict[str, set[str]] = {}
    for table_name, filename in PARQUET_FILENAMES.items():
        parquet_path = parquet_dir / filename
        if not parquet_path.is_file():
            continue
        frame = pd.read_parquet(parquet_path, columns=["date_month"])
        months: set[str] = set()
        for value in frame["date_month"].dropna().unique():
            timestamp = pd.Timestamp(value)
            months.add(f"{timestamp.year:04d}-{timestamp.month:02d}")
        if not months:
            raise RawContractError(f"正式 parquet 基线为空: {parquet_path}")
        months_by_table[table_name] = months
    return months_by_table


def validate_derived_baseline(dataset_root: Path) -> Dict[str, Any]:
    """If any derived artifact exists, all expected baseline files must exist.

    A partial derived layer means the formal dataset is already inconsistent;
    silently skipping the missing files would hide that state.
    """
    dataset_root = Path(dataset_root)
    artifacts_present = any(
        (dataset_root / relative).exists() for relative in EXPECTED_DERIVED_FILES
    ) or any(
        (dataset_root / directory).exists()
        for directory in ("parquet", "registry", "quality")
    )
    if not artifacts_present:
        return {"present": False, "months": {}}

    missing = [
        relative
        for relative in EXPECTED_DERIVED_FILES
        if not (dataset_root / relative).is_file()
    ]
    if missing:
        raise RawContractError(f"正式派生层基线不完整，缺少: {missing}")
    return {
        "present": True,
        "months": required_months_from_parquet(dataset_root / "parquet"),
    }


def snapshot_months(raw_dir: Path) -> Dict[str, set[str]]:
    raw_dir = Path(raw_dir)
    months_by_table: Dict[str, set[str]] = {}
    for filename, table_name in SOURCE_MAP.items():
        snapshot = read_pivot_csv(raw_dir / filename)
        months_by_table[table_name] = {
            format_month(month_key(row[DATE_COLUMN])) for row in snapshot.rows
        }
    return months_by_table


def validate_raw_derived_consistency(
    raw_dir: Path, derived_dir: Path
) -> Dict[str, Any]:
    """Cross-layer gate: staged raw and staged parquet must cover the same months."""
    raw_dir = Path(raw_dir)
    derived_dir = Path(derived_dir)
    missing_files = [
        relative
        for relative in EXPECTED_DERIVED_FILES
        if not (derived_dir / relative).is_file()
    ]
    if missing_files:
        raise RawContractError(f"派生层产出不完整，缺少: {missing_files}")

    raw_months = snapshot_months(raw_dir)
    derived_months = required_months_from_parquet(derived_dir / "parquet")
    mismatches: Dict[str, Any] = {}
    for table_name, months in raw_months.items():
        staged = derived_months.get(table_name, set())
        if months != staged:
            mismatches[table_name] = {
                "raw_only": sorted(months - staged),
                "parquet_only": sorted(staged - months),
            }
    if mismatches:
        raise RawContractError(f"raw 与 parquet 月份不一致: {mismatches}")

    return {
        table_name: {"month_count": len(months), "months": sorted(months)}
        for table_name, months in raw_months.items()
    }


# ── validation ────────────────────────────────────────────────────


def _validate_table(
    table_name: str,
    snapshot: PivotSnapshot,
    required_months: Optional[set[str]],
) -> Dict[str, Any]:
    issues: List[str] = []
    expected_columns = set(canonical_columns(table_name))
    actual_columns = set(snapshot.header)
    missing_columns = sorted(expected_columns - actual_columns)
    extra_columns = sorted(actual_columns - expected_columns)
    if missing_columns:
        issues.append(f"缺少列 {missing_columns}")
    if extra_columns:
        issues.append(f"未知列 {extra_columns}")

    seen_keys: Dict[Tuple[str, ...], int] = {}
    duplicate_keys: List[Tuple[str, ...]] = []
    months: set[str] = set()
    invalid_dates: List[str] = []
    invalid_values: List[str] = []
    negative_sales: List[str] = []
    unknown_measures: set[str] = set()
    measures: set[str] = set()

    for line_no, row in enumerate(snapshot.rows, start=2):
        try:
            key = month_key(row[DATE_COLUMN])
            months.add(format_month(key))
        except (KeyError, ValueError):
            if len(invalid_dates) < 10:
                invalid_dates.append(f"line {line_no}: {row.get(DATE_COLUMN)!r}")

        measure_name = row.get(MEASURE_NAME_COLUMN, "").strip()
        measures.add(measure_name)
        if measure_name not in KNOWN_MEASURES:
            unknown_measures.add(measure_name)
        measure_value = row.get(MEASURE_VALUE_COLUMN, "")
        parsed = _to_float(measure_value)
        if parsed is not None and not math.isfinite(parsed):
            if len(invalid_values) < 10:
                invalid_values.append(f"line {line_no}: {measure_name}={measure_value!r}")
        elif measure_name == REQUIRED_MEASURE:
            if parsed is None:
                if len(invalid_values) < 10:
                    invalid_values.append(f"line {line_no}: {measure_name}={measure_value!r}")
            elif parsed < 0:
                negative_sales.append(f"line {line_no}: {parsed}")
        elif parsed is None and measure_value.strip() not in ("", "-"):
            if len(invalid_values) < 10:
                invalid_values.append(f"line {line_no}: {measure_name}={measure_value!r}")

        if expected_columns <= actual_columns:
            primary_key = _primary_key(table_name, row)
            if primary_key in seen_keys:
                if len(duplicate_keys) < 10:
                    duplicate_keys.append(primary_key)
            else:
                seen_keys[primary_key] = line_no

    if invalid_dates:
        issues.append(f"无法解析 date_month: {invalid_dates}")
    if unknown_measures:
        issues.append(f"未知度量名称 {sorted(unknown_measures)}")
    if REQUIRED_MEASURE not in measures:
        issues.append(f"缺少必需度量 {REQUIRED_MEASURE}")
    if invalid_values:
        issues.append(f"度量值无法解析: {invalid_values}")
    if negative_sales:
        issues.append(f"销量为负: {negative_sales}")
    if duplicate_keys:
        issues.append(f"主键冲突(重复 dims+度量): {duplicate_keys}")
    if required_months:
        missing_months = sorted(required_months - months)
        if missing_months:
            issues.append(f"历史月份缺失(对照 parquet 基线): {missing_months}")

    if issues:
        raise RawContractError(
            f"{table_name}: " + "; ".join(issues),
            table=table_name,
            issues=issues,
        )

    return {
        "table_name": table_name,
        "source_csv": snapshot.path.name,
        "rows": len(snapshot.rows),
        "months": sorted(months),
        "month_count": len(months),
        "measures": sorted(measures),
        "sha256": sha256_file(snapshot.path),
        "encoding": snapshot.encoding,
        "delimiter": snapshot.delimiter,
    }


def validate_snapshot(
    raw_dir: Path,
    *,
    required_months_by_table: Optional[Mapping[str, Iterable[Any]]] = None,
) -> Dict[str, Any]:
    """Validate a raw snapshot; raise RawContractError on any violation."""
    raw_dir = Path(raw_dir)
    if not raw_dir.is_dir():
        raise RawContractError(f"raw 快照目录不存在: {raw_dir}")

    required = _normalize_required_months(required_months_by_table)
    report: Dict[str, Any] = {"tables": {}, "required_months": {}}
    issues: List[str] = []

    for filename, table_name in SOURCE_MAP.items():
        path = raw_dir / filename
        if not path.is_file():
            issues.append(f"{table_name}: 缺少 {filename}")
            continue
        try:
            snapshot = read_pivot_csv(path)
            report["tables"][table_name] = _validate_table(
                table_name, snapshot, required.get(table_name)
            )
        except RawContractError as exc:
            issues.extend(exc.issues or [str(exc)])

    for table_name in required:
        if table_name not in report["tables"]:
            issues.append(f"{table_name}: 缺少基线月份校验所需的表")

    if issues:
        raise RawContractError("raw 快照校验失败: " + "; ".join(issues), issues=issues)

    report["required_months"] = {key: sorted(value) for key, value in required.items()}
    return report


# ── merge ─────────────────────────────────────────────────────────


def merge_pivot_tables(
    table_name: str,
    base: PivotSnapshot,
    increment: PivotSnapshot,
    *,
    max_month_deletion_ratio: float = DEFAULT_MAX_MONTH_DELETION_RATIO,
) -> MergeResult:
    """Merge base + increment with month-level replacement for exported months.

    A Tableau export is authoritative for the months it contains: all base rows
    in those months are replaced by the increment (so disappeared dimension
    combinations do not linger). Historical months **not** present in the
    increment are carried over unchanged. Row order is chronological (stable),
    so output is deterministic.

    A replaced month that loses more than ``max_month_deletion_ratio`` of its
    old rows is rejected: an incomplete Tableau export must not silently wipe
    most of a month.
    """
    if not 0.0 <= max_month_deletion_ratio <= 1.0:
        raise RawContractError(
            f"max_month_deletion_ratio 必须在 [0, 1]: {max_month_deletion_ratio}"
        )
    expected_columns = set(canonical_columns(table_name))
    for label, snapshot in (("formal raw", base), ("increment", increment)):
        missing = sorted(expected_columns - set(snapshot.header))
        extra = sorted(set(snapshot.header) - expected_columns)
        if missing or extra:
            raise RawContractError(
                f"{table_name}: {label} 列与契约不一致 "
                f"(missing={missing}, extra={extra})",
                table=table_name,
            )

    base_keys: set[Tuple[str, ...]] = set()
    for row in base.rows:
        key = _primary_key(table_name, row)
        if key in base_keys:
            raise RawContractError(
                f"{table_name}: formal raw 主键重复: {key}", table=table_name
            )
        base_keys.add(key)

    increment_keys: set[Tuple[str, ...]] = set()
    for row in increment.rows:
        key = _primary_key(table_name, row)
        if key in increment_keys:
            raise RawContractError(
                f"{table_name}: 增量导出主键冲突: {key}", table=table_name
            )
        increment_keys.add(key)

    increment_months = {
        format_month(month_key(row[DATE_COLUMN])) for row in increment.rows
    }
    increment_key_set = {_primary_key(table_name, row) for row in increment.rows}
    increment_keys_by_month: Dict[str, set[Tuple[str, ...]]] = {}
    for row in increment.rows:
        month = format_month(month_key(row[DATE_COLUMN]))
        increment_keys_by_month.setdefault(month, set()).add(
            _primary_key(table_name, row)
        )
    base_keys_by_month: Dict[str, set[Tuple[str, ...]]] = {}
    for row in base.rows:
        month = format_month(month_key(row[DATE_COLUMN]))
        base_keys_by_month.setdefault(month, set()).add(_primary_key(table_name, row))

    base_index = {_primary_key(table_name, row): row for row in base.rows}
    merged: Dict[Tuple[str, ...], Dict[str, str]] = {}
    for row in base.rows:
        if format_month(month_key(row[DATE_COLUMN])) in increment_months:
            continue
        merged[_primary_key(table_name, row)] = row
    kept_history_rows = len(merged)

    added_rows = 0
    restated_rows = 0
    unchanged_overlap_rows = 0
    for row in increment.rows:
        key = _primary_key(table_name, row)
        previous = base_index.get(key)
        if previous is not None:
            if _measure_values_equal(
                previous[MEASURE_VALUE_COLUMN], row[MEASURE_VALUE_COLUMN]
            ):
                unchanged_overlap_rows += 1
            else:
                restated_rows += 1
        else:
            added_rows += 1
        merged[key] = row

    replaced_base_rows = sum(
        len(base_keys_by_month.get(month, set())) for month in increment_months
    )
    removed_rows = sum(
        len(base_keys_by_month.get(month, set()) - increment_key_set)
        for month in increment_months
    )

    month_audit: List[Dict[str, Any]] = []
    large_deletions: List[Dict[str, Any]] = []
    for month in sorted(increment_months):
        base_keys = base_keys_by_month.get(month, set())
        increment_keys = increment_keys_by_month.get(month, set())
        removed = len(base_keys - increment_keys)
        ratio = removed / len(base_keys) if base_keys else 0.0
        record = {
            "month": month,
            "base_rows": len(base_keys),
            "increment_rows": len(increment_keys),
            "removed_rows": removed,
            "deletion_ratio": round(ratio, 6),
        }
        month_audit.append(record)
        if ratio > max_month_deletion_ratio:
            large_deletions.append(record)
    if large_deletions:
        raise RawContractError(
            f"{table_name}: 整月替换删除比例超过阈值 "
            f"{max_month_deletion_ratio:.2f}: {large_deletions}",
            table=table_name,
        )

    rows = list(merged.values())
    rows.sort(key=lambda row: month_key(row[DATE_COLUMN]))

    base_months = {format_month(month_key(row[DATE_COLUMN])) for row in base.rows}
    merged_months = {format_month(month_key(row[DATE_COLUMN])) for row in rows}
    lost_months = sorted(base_months - merged_months)
    if lost_months:  # pragma: no cover - month replacement cannot lose months
        raise RawContractError(
            f"{table_name}: 合并后丢失历史月份 {lost_months}", table=table_name
        )

    header = canonical_columns(table_name)

    stats = {
        "table_name": table_name,
        "source_csv": base.path.name,
        "base_rows": len(base.rows),
        "increment_rows": len(increment.rows),
        "merged_rows": len(rows),
        "kept_history_rows": kept_history_rows,
        "replaced_base_rows": replaced_base_rows,
        "removed_rows": removed_rows,
        "added_rows": added_rows,
        "restated_rows": restated_rows,
        "unchanged_overlap_rows": unchanged_overlap_rows,
        "base_month_count": len(base_months),
        "increment_months": sorted(increment_months),
        "merged_month_count": len(merged_months),
        "new_months": sorted(increment_months - base_months),
        "restated_months": sorted(increment_months & base_months),
        "max_month_deletion_ratio": max_month_deletion_ratio,
        "month_audit": month_audit,
        "large_deletions": large_deletions,
    }
    return MergeResult(
        table_name=table_name,
        filename=base.path.name,
        header=header,
        rows=rows,
        stats=stats,
    )


def merge_snapshot_to_staging(
    formal_raw_dir: Path,
    increment_raw_dir: Path,
    staging_raw_dir: Path,
    *,
    required_months_by_table: Optional[Mapping[str, Iterable[Any]]] = None,
    max_month_deletion_ratio: float = DEFAULT_MAX_MONTH_DELETION_RATIO,
) -> Dict[str, Any]:
    """Merge increment into a staging copy of the historical raw files."""
    formal_raw_dir = Path(formal_raw_dir)
    increment_raw_dir = Path(increment_raw_dir)
    staging_raw_dir = Path(staging_raw_dir)

    validate_snapshot(increment_raw_dir)

    reports: Dict[str, Any] = {}
    for filename, table_name in SOURCE_MAP.items():
        base = read_pivot_csv(formal_raw_dir / filename)
        increment = read_pivot_csv(increment_raw_dir / filename)
        result = merge_pivot_tables(
            table_name,
            base,
            increment,
            max_month_deletion_ratio=max_month_deletion_ratio,
        )
        write_pivot_csv(staging_raw_dir / filename, result.header, result.rows)
        reports[table_name] = result.stats

    validation = validate_snapshot(
        staging_raw_dir, required_months_by_table=required_months_by_table
    )
    return {
        "merged_dir": str(staging_raw_dir),
        "tables": reports,
        "validation": validation,
    }


# ── atomic publish ────────────────────────────────────────────────


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp_path, path)


def _publish_file_pairs(
    pairs: Sequence[Tuple[Path, Path, str]],
    *,
    backup_dir: Path,
    manifest_path: Path,
    manifest: Mapping[str, Any],
) -> Dict[str, Any]:
    """Snapshot destinations, then os.replace staged files with rollback."""
    file_records: Dict[str, Any] = {}
    for source, destination, key in pairs:
        if not source.is_file():
            raise RawContractError(f"待发布文件不存在: {source}")
        backup_path = backup_dir / key
        previous_sha = sha256_file(destination) if destination.is_file() else None
        if destination.is_file():
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup_path)
        file_records[key] = {
            "source": str(source),
            "destination": str(destination),
            "backup": str(backup_path) if destination.is_file() else None,
            "previous_sha256": previous_sha,
            "staged_sha256": sha256_file(source),
            "bytes": source.stat().st_size,
        }

    state: Dict[str, Any] = dict(manifest)
    state.update(
        {
            "status": "publishing",
            "started_at": datetime.now().isoformat(),
            "backup_dir": str(backup_dir),
            "files": file_records,
        }
    )
    _write_json(manifest_path, state)

    published: List[str] = []
    try:
        for source, destination, key in pairs:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            published.append(key)
    except Exception as exc:  # roll back what was already replaced
        restore_errors: List[str] = []
        for key in reversed(published):
            record = file_records[key]
            destination = Path(record["destination"])
            backup_path = Path(record["backup"]) if record["backup"] else None
            try:
                if backup_path is not None and backup_path.is_file():
                    shutil.copy2(backup_path, destination)
                elif record["previous_sha256"] is None and destination.is_file():
                    destination.unlink()
            except Exception as restore_exc:  # pragma: no cover - defensive
                restore_errors.append(f"{key}: {restore_exc}")
        state.update(
            {
                "status": "recovery_failed" if restore_errors else "failed",
                "error": repr(exc),
                "restore_errors": restore_errors,
                "published_before_failure": published,
                "finished_at": datetime.now().isoformat(),
            }
        )
        _write_json(manifest_path, state)
        raise

    state.update(
        {
            "status": "published",
            "published_files": published,
            "finished_at": datetime.now().isoformat(),
        }
    )
    _write_json(manifest_path, state)
    return state


# ── run lock / incomplete transaction recovery ────────────────────


def _read_lock(lock_path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # process exists but belongs to another user
        return True
    except OSError:
        return True
    return True


def _lock_is_live(payload: Mapping[str, Any], lock_path: Path) -> bool:
    pid = payload.get("pid")
    if isinstance(pid, int) and pid > 0:
        return _pid_alive(pid)
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        return False
    return age < STALE_LOCK_SECONDS


@contextmanager
def update_lock(staging_root: Path, run_id: str) -> Iterator[Dict[str, Any]]:
    """Prevent two update processes from touching the same dataset."""
    staging_root = Path(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    lock_path = staging_root / LOCK_FILENAME
    payload = {
        "run_id": run_id,
        "pid": os.getpid(),
        "created_at": datetime.now().isoformat(),
    }

    attempts = 0
    while True:
        attempts += 1
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            break
        except FileExistsError:
            existing = _read_lock(lock_path)
            if _lock_is_live(existing, lock_path) or attempts >= 3:
                raise RawContractError(
                    f"另一个更新任务正在运行（lock={lock_path}, "
                    f"run_id={existing.get('run_id')}, pid={existing.get('pid')}）"
                ) from None
            stale_dir = staging_root / "locks"
            stale_dir.mkdir(parents=True, exist_ok=True)
            stale_path = stale_dir / (
                f"stale-lock-{existing.get('run_id', 'unknown')}-{int(time.time())}.json"
            )
            os.replace(lock_path, stale_path)

    try:
        yield payload
    finally:
        current = _read_lock(lock_path)
        if current.get("run_id") == run_id and current.get("pid") == os.getpid():
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def _restore_manifest_files(manifest: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    files = manifest.get("files") or {}
    if not isinstance(files, Mapping):
        return [f"manifest files 格式错误: {type(files).__name__}"]
    for key, record in files.items():
        if not isinstance(record, Mapping):
            errors.append(f"{key}: 文件记录格式错误")
            continue
        destination = Path(record.get("destination", ""))
        backup = Path(record["backup"]) if record.get("backup") else None
        previous_sha = record.get("previous_sha256")
        try:
            if backup is not None and backup.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, destination)
            elif previous_sha is None:
                if destination.is_file():
                    destination.unlink()
            else:
                errors.append(f"{key}: 回滚备份缺失 {backup}")
                continue
            if previous_sha is not None and destination.is_file():
                if sha256_file(destination) != previous_sha:
                    errors.append(f"{key}: 回滚后 sha256 与发布前不一致")
        except Exception as exc:  # pragma: no cover - filesystem failure
            errors.append(f"{key}: {exc}")
    return errors


def recover_incomplete_transactions(staging_root: Path) -> List[Dict[str, Any]]:
    """Roll back manifests left in ``publishing``/``recovery_failed`` state.

    A crash between two per-file ``os.replace`` calls leaves the formal dataset
    in a mixed state. The backup snapshot plus manifest let the next update
    restore the pre-transaction content before doing anything else.
    """
    staging_root = Path(staging_root)
    runs_dir = staging_root / "runs"
    recovered: List[Dict[str, Any]] = []
    if not runs_dir.is_dir():
        return recovered

    for manifest_path in sorted(runs_dir.glob("*/*_manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RawContractError(f"无法读取未完成事务 manifest: {manifest_path}: {exc}") from exc
        status = manifest.get("status")
        if status not in {"publishing", "recovery_failed"}:
            continue

        errors = _restore_manifest_files(manifest)
        manifest["status"] = "recovered" if not errors else "recovery_failed"
        manifest["recovered_at"] = datetime.now().isoformat()
        manifest["restore_errors"] = errors
        _write_json(manifest_path, manifest)
        recovered.append(
            {
                "manifest": str(manifest_path),
                "status": manifest["status"],
                "restore_errors": errors,
            }
        )
        if errors:
            raise RawContractError(
                f"未完成事务恢复失败（需人工处理）: {manifest_path}: {errors}"
            )
    return recovered


# ── cross-layer transaction publish ───────────────────────────────


def publish_update_transaction(
    *,
    dataset_root: Path,
    run_dir: Path,
    staging_root: Path,
    raw_dir: Path | None,
    derived_dir: Path | None,
    validation: Mapping[str, Any],
    audit: Any = None,
) -> Dict[str, Any]:
    """Replace raw and derived files in one transaction.

    ``os.replace`` is atomic per file only; readers can observe a cross-file
    mixed state during the loop. Any failure restores every file already
    replaced by this transaction and records the outcome in the manifest.
    """
    dataset_root = Path(dataset_root)
    run_dir = Path(run_dir)
    staging_root = Path(staging_root)
    pairs: List[Tuple[Path, Path, str]] = []

    if raw_dir is not None:
        raw_dir = Path(raw_dir)
        missing_raw = [
            filename for filename in SOURCE_MAP if not (raw_dir / filename).is_file()
        ]
        if missing_raw:
            raise RawContractError(f"待发布 raw 不完整，缺少: {missing_raw}")
        pairs.extend(
            (
                raw_dir / filename,
                dataset_root / "raw_csv" / filename,
                f"raw_csv/{filename}",
            )
            for filename in SOURCE_MAP
        )

    if derived_dir is not None:
        derived_dir = Path(derived_dir)
        missing_derived = [
            relative
            for relative in EXPECTED_DERIVED_FILES
            if not (derived_dir / relative).is_file()
        ]
        if missing_derived:
            raise RawContractError(f"待发布派生层不完整，缺少: {missing_derived}")
        pairs.extend(
            (derived_dir / relative, dataset_root / relative, relative)
            for relative in EXPECTED_DERIVED_FILES
        )

    if not pairs:
        raise RawContractError("没有可发布的文件")

    run_id = run_dir.name
    layers = []
    if raw_dir is not None:
        layers.append("raw_csv")
    if derived_dir is not None:
        layers.append("parquet_registry_quality")
    return _publish_file_pairs(
        pairs,
        backup_dir=staging_root / "backups" / run_id,
        manifest_path=run_dir / TRANSACTION_MANIFEST_NAME,
        manifest={
            "run_id": run_id,
            "layers": layers,
            "validation": validation,
            "audit": audit,
        },
    )


def publish_raw_snapshot(
    *,
    formal_raw_dir: Path,
    staged_raw_dir: Path,
    staging_root: Path,
    run_id: str,
    required_months_by_table: Optional[Mapping[str, Iterable[Any]]] = None,
) -> Dict[str, Any]:
    """Validate a staged snapshot, snapshot formal raw, then publish atomically."""
    formal_raw_dir = Path(formal_raw_dir)
    staged_raw_dir = Path(staged_raw_dir)
    staging_root = Path(staging_root)

    validation = validate_snapshot(
        staged_raw_dir, required_months_by_table=required_months_by_table
    )
    pairs = [
        (
            staged_raw_dir / filename,
            formal_raw_dir / filename,
            f"raw_csv/{filename}",
        )
        for filename in SOURCE_MAP
    ]
    return _publish_file_pairs(
        pairs,
        backup_dir=staging_root / "backups" / run_id,
        manifest_path=staging_root / "runs" / run_id / "publish_manifest.json",
        manifest={
            "run_id": run_id,
            "layer": "raw_csv",
            "validation": validation,
        },
    )


def publish_derived_snapshot(
    *,
    derived_dir: Path,
    dataset_root: Path,
    staging_root: Path,
    run_id: str,
) -> Dict[str, Any]:
    """Publish a staged parquet/registry/quality tree with backup + rollback."""
    derived_dir = Path(derived_dir)
    dataset_root = Path(dataset_root)
    staging_root = Path(staging_root)

    relative_files = [
        *(f"parquet/{filename}" for filename in PARQUET_FILENAMES.values()),
        "registry/tp_and_mix_ways_tables.json",
        "quality/tp_and_mix_ways_dataset_quality.md",
        "quality/tp_and_mix_ways_dataset_quality.json",
    ]
    missing = [name for name in relative_files if not (derived_dir / name).is_file()]
    if missing:
        raise RawContractError(f"派生层产出不完整，缺少: {missing}")

    pairs = [
        (derived_dir / name, dataset_root / name, name) for name in relative_files
    ]
    return _publish_file_pairs(
        pairs,
        backup_dir=staging_root / "backups" / run_id,
        manifest_path=staging_root / "runs" / run_id / "derived_manifest.json",
        manifest={"run_id": run_id, "layer": "parquet_registry_quality"},
    )


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S_%f")
