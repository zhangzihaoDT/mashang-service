"""Regression tests for the TP&MIX-ways raw staging / publish contract.

These tests are data-independent: every snapshot is generated in ``tmp_path``
so they can run in CI without the local ``dataset/TP&MIX-ways`` asset.

Coverage:
* incremental export cannot replace historical raw months
* column order / header alias / encoding changes are tolerated
* duplicate primary keys and column-set changes are rejected
* missing historical months block publish
* per-month deletion audit blocks abnormal mass deletion (configurable)
* cross-layer transaction rollback restores raw + derived files
* incomplete manifest recovery, recovery failure, run lock, repeated runs
* missing baseline files are errors
* rebuild from published raw is deterministic and preserves history
* corrected grain definitions remove false duplicate rows
"""

from __future__ import annotations

import csv
import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from dataset.updater import tp_and_mix_ways_raw_guard as guard
from dataset.updater import update_tp_and_mix_ways_tableau as updater
from scripts.build_tp_and_mix_ways_dataset import (
    COLUMN_MAP,
    GRAIN_DEFS,
    PARQUET_FILENAMES,
    SOURCE_MAP,
    build_tp_and_mix_ways_dataset,
)
from shared.schema.tp_and_mix_ways_schema import TP_AND_MIX_WAYS_TABLES

MEASURES = ("销量", "TP重心")
ALL_TABLES = [table.table_name for table in TP_AND_MIX_WAYS_TABLES]

# Default English dimension values, translated to raw Chinese headers below.
DIM_DEFAULTS = {
    "fuel_type_group": "新能源",
    "fuel_type": "纯电",
    "brand": "示例品牌",
    "brand_group": "自主",
    "brand_luxury_group": "非豪华",
    "oem": "示例厂商",
    "oem_group": "示例集团",
    "brand_country": "中国",
    "ownership_type": "个人",
    "domestic_import": "国产",
    "brand_series": "自主",
    "sub_model_id": "1001",
    "model": "示例车型",
    "sub_model": "示例子车型",
    "body_type": "SUV",
    "vehicle_level": "B",
    "vehicle_level_group": "B",
    "saic_segment": "B",
    "drive_type": "前轮驱动",
    "drive_type_group": "两驱",
    "province": "上海",
    "city": "上海",
    "region_group": "华东",
    "city_tier_2025": "一线",
    "city_tier_group": "一线",
    "tp_bucket_5w": "10-15万",
    "tp_bucket_10w": "10-20万",
}

# Legitimate Tableau splits that the old grain treated as duplicates.
VARIANTS = {
    "brand_monthly": [
        {"ownership_type": "个人", "oem": "合资厂商", "oem_group": "合资集团", "domestic_import": "合资"},
        {"ownership_type": "个人", "oem": "进口厂商", "oem_group": "进口集团", "domestic_import": "进口"},
    ],
    "model_monthly": [
        {"drive_type": "前轮驱动", "drive_type_group": "两驱", "fuel_type": "纯电", "fuel_type_group": "新能源"},
        {"drive_type": "前轮驱动", "drive_type_group": "两驱", "fuel_type": "插电混动", "fuel_type_group": "新能源"},
        {"drive_type": "全时四驱", "drive_type_group": "四驱", "fuel_type": "纯电", "fuel_type_group": "新能源"},
    ],
}


def _ym(month: str) -> str:
    year, rest = month.split("年")
    return f"{year}-{int(rest.replace('月', '')):02d}"


def _required(months: list[str]) -> dict[str, set[str]]:
    normalized = {_ym(month) for month in months}
    return {table: set(normalized) for table in ALL_TABLES}


def write_snapshot(
    root: Path,
    months: list[str],
    *,
    sales_override: dict[str, str] | None = None,
    duplicate_table: str | None = None,
    reorder: bool = False,
    alias_brand_header: bool = False,
    trailing_space: bool = False,
    encoding: str = "utf-8",
    delimiter: str = ",",
    drop_columns: tuple[str, str] | None = None,
) -> None:
    """Write a minimal but contract-valid 6-table pivot snapshot."""
    root.mkdir(parents=True, exist_ok=True)
    sales_override = sales_override or {}

    for table_name, mappings in COLUMN_MAP.items():
        if drop_columns and drop_columns[0] == table_name:
            mappings = [(raw, english) for raw, english in mappings if raw != drop_columns[1]]
        raw_header = [raw for raw, _ in mappings]
        english_by_raw = dict(mappings)
        rows: list[dict[str, str]] = []
        for month_index, month in enumerate(months):
            for variant_index, variant in enumerate(VARIANTS.get(table_name, [{}])):
                dims = dict(DIM_DEFAULTS)
                dims.update(variant)
                for measure in MEASURES:
                    if measure == "销量":
                        value = sales_override.get(
                            month, str(10 * (month_index + 1) + variant_index)
                        )
                    else:
                        value = str(100000 + month_index)
                    row = {}
                    for raw_column, english_column in mappings:
                        if english_column == "_measure_name":
                            row[raw_column] = measure
                        elif english_column == "_measure_value":
                            row[raw_column] = value
                        elif english_column == "date_month":
                            row[raw_column] = month
                        else:
                            row[raw_column] = dims[english_column]
                    rows.append(row)

        if duplicate_table == table_name:
            rows.append(dict(rows[0]))

        if alias_brand_header and table_name == "brand_monthly":
            for row in rows:
                row["自主/合资/进口"] = row.pop("国产/进口")
            raw_header = [
                "自主/合资/进口" if column == "国产/进口" else column
                for column in raw_header
            ]

        if trailing_space and table_name == "brand_monthly":
            target = "品牌 (新豪华分组)"
            actual = next(column for column in raw_header if column.strip() == target)
            for row in rows:
                row[target + " "] = row.pop(actual)
            raw_header = [
                target + " " if column == actual else column for column in raw_header
            ]

        write_header = list(reversed(raw_header)) if reorder else raw_header
        path = root / next(
            csv_name for csv_name, name in SOURCE_MAP.items() if name == table_name
        )

        with open(path, "w", encoding=encoding, newline="") as fh:
            writer = csv.writer(fh, delimiter=delimiter)
            writer.writerow(write_header)
            for row in rows:
                writer.writerow([row[column] for column in write_header])


def read_months(raw_dir: Path) -> dict[str, set[str]]:
    return {
        table_name: {
            guard.format_month(guard.month_key(row[guard.DATE_COLUMN]))
            for row in guard.read_pivot_csv(path).rows
        }
        for path, table_name in _table_files(raw_dir)
    }


def _table_files(raw_dir: Path):
    return [(raw_dir / filename, table_name) for filename, table_name in SOURCE_MAP.items()]


def assert_months(raw_dir: Path, months: set[str]) -> None:
    assert read_months(raw_dir) == {table: set(months) for table in ALL_TABLES}


def _publish_fixture(tmp_path: Path):
    dataset_root = tmp_path / "dataset"
    formal_raw = dataset_root / "raw_csv"
    write_snapshot(formal_raw, ["2026年1月", "2026年2月"])
    increment = tmp_path / "increment" / "raw_csv"
    write_snapshot(
        increment,
        ["2026年2月", "2026年3月"],
        sales_override={"2026年2月": "777"},
    )
    staging_root = dataset_root / "staging"
    run_id = "test-run"
    merged = staging_root / "runs" / run_id / "merged" / "raw_csv"
    guard.merge_snapshot_to_staging(
        formal_raw,
        increment,
        merged,
        required_months_by_table=_required(["2026年1月", "2026年2月"]),
    )
    manifest = guard.publish_raw_snapshot(
        formal_raw_dir=formal_raw,
        staged_raw_dir=merged,
        staging_root=staging_root,
        run_id=run_id,
        required_months_by_table=_required(["2026年1月", "2026年2月"]),
    )
    return dataset_root, formal_raw, staging_root, run_id, manifest


# ── raw history protection ───────────────────────────────────────


def test_incremental_export_cannot_replace_history(tmp_path: Path):
    dataset_root = tmp_path / "dataset"
    formal_raw = dataset_root / "raw_csv"
    write_snapshot(formal_raw, ["2026年1月", "2026年2月"])
    formal_before = {
        path.name: guard.sha256_file(path) for path in formal_raw.glob("*.csv")
    }

    increment = tmp_path / "increment" / "raw_csv"
    write_snapshot(increment, ["2026年3月"])
    staging_root = dataset_root / "staging"
    merged = staging_root / "runs" / "run-1" / "merged" / "raw_csv"

    plan = guard.merge_snapshot_to_staging(
        formal_raw,
        increment,
        merged,
        required_months_by_table=_required(["2026年1月", "2026年2月"]),
    )
    # merge itself never touches formal raw
    assert {path.name: guard.sha256_file(path) for path in formal_raw.glob("*.csv")} == formal_before
    for stats in plan["tables"].values():
        assert stats["merged_month_count"] == 3
        assert stats["new_months"] == ["2026-03"]

    manifest = guard.publish_raw_snapshot(
        formal_raw_dir=formal_raw,
        staged_raw_dir=merged,
        staging_root=staging_root,
        run_id="run-1",
        required_months_by_table=_required(["2026年1月", "2026年2月"]),
    )
    assert manifest["status"] == "published"
    assert_months(formal_raw, {"2026-01", "2026-02", "2026-03"})
    # the pre-publish snapshot keeps the old two-month history
    backup = staging_root / "backups" / "run-1" / "raw_csv"
    assert_months(backup, {"2026-01", "2026-02"})
    assert json.loads((staging_root / "runs" / "run-1" / "publish_manifest.json").read_text(encoding="utf-8"))["status"] == "published"


def test_exported_month_replaces_stale_keys(tmp_path: Path):
    formal_raw = tmp_path / "formal" / "raw_csv"
    write_snapshot(formal_raw, ["2026年1月", "2026年2月"])
    increment = tmp_path / "increment" / "raw_csv"
    write_snapshot(increment, ["2026年2月"])

    # Simulate a restated month where one previously present brand split vanished.
    brand_path = increment / "way2_brand_monthly_data.csv"
    snapshot = guard.read_pivot_csv(brand_path)
    kept = [row for row in snapshot.rows if row["厂商"] == "合资厂商"]
    assert kept
    guard.write_pivot_csv(brand_path, snapshot.header, kept)

    merged = tmp_path / "merged" / "raw_csv"
    plan = guard.merge_snapshot_to_staging(
        formal_raw,
        increment,
        merged,
        required_months_by_table=_required(["2026年1月", "2026年2月"]),
    )
    stats = plan["tables"]["brand_monthly"]
    assert stats["increment_rows"] == 2
    assert stats["removed_rows"] == 2
    assert stats["replaced_base_rows"] == 4

    merged_brand = guard.read_pivot_csv(merged / "way2_brand_monthly_data.csv")
    feb_rows = [row for row in merged_brand.rows if row[guard.DATE_COLUMN] == "2026年2月"]
    assert {row["厂商"] for row in feb_rows} == {"合资厂商"}
    jan_rows = [row for row in merged_brand.rows if row[guard.DATE_COLUMN] == "2026年1月"]
    assert len(jan_rows) == 4  # two historical splits x two measures, untouched


def test_overlapping_key_restatement_is_counted(tmp_path: Path):
    _, formal_raw, _, _, manifest = _publish_fixture(tmp_path)
    table = "market_energy_monthly"
    stats = manifest["validation"]["tables"][table]
    assert stats["rows"] > 0
    # the increment restated 2026-02 sales for one variant
    merged = guard.read_pivot_csv(formal_raw / next(
        name for name, value in guard.SOURCE_MAP.items() if value == table
    ))
    feb_sales = [
        row[guard.MEASURE_VALUE_COLUMN]
        for row in merged.rows
        if row[guard.DATE_COLUMN] == "2026年2月" and row[guard.MEASURE_NAME_COLUMN] == "销量"
    ]
    assert "777" in feb_sales
    # and the historical January value was carried over untouched
    jan_sales = [
        row[guard.MEASURE_VALUE_COLUMN]
        for row in merged.rows
        if row[guard.DATE_COLUMN] == "2026年1月" and row[guard.MEASURE_NAME_COLUMN] == "销量"
    ]
    assert jan_sales == ["10"]


def test_column_order_alias_and_utf16_increment(tmp_path: Path):
    formal_raw = tmp_path / "formal" / "raw_csv"
    write_snapshot(formal_raw, ["2026年1月"])
    increment = tmp_path / "increment" / "raw_csv"
    write_snapshot(
        increment,
        ["2026年2月"],
        reorder=True,
        alias_brand_header=True,
        trailing_space=True,
        encoding="utf-16",
        delimiter="\t",
    )
    merged = tmp_path / "merged" / "raw_csv"
    guard.merge_snapshot_to_staging(
        formal_raw,
        increment,
        merged,
        required_months_by_table=_required(["2026年1月"]),
    )
    for filename, table_name in SOURCE_MAP.items():
        snapshot = guard.read_pivot_csv(merged / filename)
        assert snapshot.header == guard.canonical_columns(table_name)
        assert snapshot.encoding == "utf-8"
        assert snapshot.delimiter == ","
    brand_bytes = (merged / "way2_brand_monthly_data.csv").read_bytes()
    assert not brand_bytes.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in brand_bytes


# ── rejection paths ──────────────────────────────────────────────


def test_duplicate_primary_key_blocks_merge(tmp_path: Path):
    formal_raw = tmp_path / "formal" / "raw_csv"
    write_snapshot(formal_raw, ["2026年1月"])
    increment = tmp_path / "increment" / "raw_csv"
    write_snapshot(increment, ["2026年2月"], duplicate_table="market_energy_monthly")
    before = {path.name: guard.sha256_file(path) for path in formal_raw.glob("*.csv")}
    with pytest.raises(guard.RawContractError, match="主键冲突"):
        guard.merge_snapshot_to_staging(
            formal_raw, increment, tmp_path / "merged" / "raw_csv"
        )
    assert {path.name: guard.sha256_file(path) for path in formal_raw.glob("*.csv")} == before


def test_column_set_change_is_rejected(tmp_path: Path):
    formal_raw = tmp_path / "formal" / "raw_csv"
    write_snapshot(formal_raw, ["2026年1月"])
    increment = tmp_path / "increment" / "raw_csv"
    write_snapshot(
        increment,
        ["2026年2月"],
        drop_columns=("brand_monthly", "厂商"),
    )
    with pytest.raises(guard.RawContractError, match="缺少列"):
        guard.merge_snapshot_to_staging(formal_raw, increment, tmp_path / "merged" / "raw_csv")


def test_missing_historical_month_blocks_publish(tmp_path: Path):
    formal_raw = tmp_path / "formal" / "raw_csv"
    write_snapshot(formal_raw, ["2026年1月"])
    increment = tmp_path / "increment" / "raw_csv"
    write_snapshot(increment, ["2026年2月"])
    merged = tmp_path / "merged" / "raw_csv"
    guard.merge_snapshot_to_staging(
        formal_raw,
        increment,
        merged,
        required_months_by_table=_required(["2026年1月"]),
    )
    before = {path.name: guard.sha256_file(path) for path in formal_raw.glob("*.csv")}
    with pytest.raises(guard.RawContractError, match="历史月份缺失"):
        guard.publish_raw_snapshot(
            formal_raw_dir=formal_raw,
            staged_raw_dir=merged,
            staging_root=tmp_path / "staging",
            run_id="missing-month",
            required_months_by_table=_required(["2025年12月"]),
        )
    assert {path.name: guard.sha256_file(path) for path in formal_raw.glob("*.csv")} == before
    assert not (tmp_path / "staging" / "backups").exists()


def test_atomic_publish_rolls_back_on_failure(tmp_path: Path, monkeypatch):
    formal_raw = tmp_path / "formal" / "raw_csv"
    write_snapshot(formal_raw, ["2026年1月"])
    increment = tmp_path / "increment" / "raw_csv"
    write_snapshot(increment, ["2026年2月"])
    merged = tmp_path / "merged" / "raw_csv"
    guard.merge_snapshot_to_staging(
        formal_raw,
        increment,
        merged,
        required_months_by_table=_required(["2026年1月"]),
    )
    before = {path.name: guard.sha256_file(path) for path in formal_raw.glob("*.csv")}
    real_replace = guard.os.replace

    def flaky_replace(source, destination):
        if Path(destination).name == "way3_model_monthly_data.csv":
            raise OSError("simulated publish failure")
        return real_replace(source, destination)

    monkeypatch.setattr(guard.os, "replace", flaky_replace)
    with pytest.raises(OSError, match="simulated publish failure"):
        guard.publish_raw_snapshot(
            formal_raw_dir=formal_raw,
            staged_raw_dir=merged,
            staging_root=tmp_path / "staging",
            run_id="flaky",
            required_months_by_table=_required(["2026年1月"]),
        )
    assert {path.name: guard.sha256_file(path) for path in formal_raw.glob("*.csv")} == before
    manifest = json.loads(
        (tmp_path / "staging" / "runs" / "flaky" / "publish_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "failed"
    assert (tmp_path / "staging" / "backups" / "flaky" / "raw_csv" / "way1_market_energy_monthly_data.csv").is_file()


# ── rebuild / grain ─────────────────────────────────────────────


def test_rebuild_preserves_history_and_is_deterministic(tmp_path: Path):
    formal_raw = tmp_path / "dataset" / "raw_csv"
    write_snapshot(formal_raw, ["2026年1月", "2026年2月"])
    base_out = tmp_path / "base_out"
    build_tp_and_mix_ways_dataset(
        raw_csv_dir=formal_raw,
        parquet_dir=base_out / "parquet",
        registry_dir=base_out / "registry",
        quality_dir=base_out / "quality",
    )

    increment = tmp_path / "increment" / "raw_csv"
    write_snapshot(
        increment,
        ["2026年2月", "2026年3月"],
        sales_override={"2026年2月": "888"},
    )
    merged = tmp_path / "dataset" / "staging" / "runs" / "r" / "merged" / "raw_csv"
    guard.merge_snapshot_to_staging(
        formal_raw,
        increment,
        merged,
        required_months_by_table=_required(["2026年1月", "2026年2月"]),
    )
    guard.publish_raw_snapshot(
        formal_raw_dir=formal_raw,
        staged_raw_dir=merged,
        staging_root=tmp_path / "dataset" / "staging",
        run_id="r",
        required_months_by_table=_required(["2026年1月", "2026年2月"]),
    )

    rebuilt_a = tmp_path / "rebuilt_a"
    rebuilt_b = tmp_path / "rebuilt_b"
    for output in (rebuilt_a, rebuilt_b):
        build_tp_and_mix_ways_dataset(
            raw_csv_dir=formal_raw,
            parquet_dir=output / "parquet",
            registry_dir=output / "registry",
            quality_dir=output / "quality",
        )

    for table_name in ALL_TABLES:
        filename = PARQUET_FILENAMES[table_name]
        before = pd.read_parquet(base_out / "parquet" / filename)
        after = pd.read_parquet(rebuilt_a / "parquet" / filename)
        again = pd.read_parquet(rebuilt_b / "parquet" / filename)
        dims = GRAIN_DEFS[table_name]
        before_jan = before[pd.to_datetime(before["date_month"]).dt.strftime("%Y-%m") == "2026-01"]
        after_jan = after[pd.to_datetime(after["date_month"]).dt.strftime("%Y-%m") == "2026-01"]
        assert before_jan.sort_values(dims).reset_index(drop=True).equals(
            after_jan.sort_values(dims).reset_index(drop=True)
        ), f"{table_name}: January history changed"
        assert set(pd.to_datetime(after["date_month"]).dt.strftime("%Y-%m")) == {
            "2026-01",
            "2026-02",
            "2026-03",
        }
        assert after.duplicated(subset=dims, keep=False).sum() == 0
        assert after.sort_values(dims).reset_index(drop=True).equals(
            again.sort_values(dims).reset_index(drop=True)
        ), f"{table_name}: rebuild is not deterministic"

    # restated February value is visible after the merge
    model_before = pd.read_parquet(base_out / "parquet" / "market_energy_monthly.parquet")
    model_after = pd.read_parquet(rebuilt_a / "parquet" / "market_energy_monthly.parquet")
    feb_before = model_before[pd.to_datetime(model_before["date_month"]).dt.strftime("%Y-%m") == "2026-02"]
    feb_after = model_after[pd.to_datetime(model_after["date_month"]).dt.strftime("%Y-%m") == "2026-02"]
    assert feb_before["sales"].max() != feb_after["sales"].max()


def test_corrected_grain_removes_false_duplicates(tmp_path: Path):
    raw = tmp_path / "raw_csv"
    write_snapshot(raw, ["2026年1月"])
    out = tmp_path / "out"
    build_tp_and_mix_ways_dataset(
        raw_csv_dir=raw,
        parquet_dir=out / "parquet",
        registry_dir=out / "registry",
        quality_dir=out / "quality",
    )
    brand = pd.read_parquet(out / "parquet" / "brand_monthly.parquet")
    assert brand.duplicated(subset=["date_month", "brand"], keep=False).any()
    assert not brand.duplicated(subset=GRAIN_DEFS["brand_monthly"], keep=False).any()

    model = pd.read_parquet(out / "parquet" / "model_monthly.parquet")
    old_model_grain = ["date_month", "brand", "model", "sub_model", "sub_model_id"]
    assert model.duplicated(subset=old_model_grain, keep=False).any()
    assert not model.duplicated(subset=GRAIN_DEFS["model_monthly"], keep=False).any()

    registry = json.loads(
        (out / "registry" / "tp_and_mix_ways_tables.json").read_text(encoding="utf-8")
    )
    registry_grain = {table["table_name"]: table["grain"] for table in registry["tables"]}
    assert registry_grain["brand_monthly"] == GRAIN_DEFS["brand_monthly"]
    assert registry_grain["model_monthly"] == GRAIN_DEFS["model_monthly"]
    quality = json.loads(
        (out / "quality" / "tp_and_mix_ways_dataset_quality.json").read_text(encoding="utf-8")
    )
    quality_by_table = {table["table_name"]: table for table in quality["tables"]}
    assert quality_by_table["brand_monthly"]["duplicate_grain_count"] == 0
    assert quality_by_table["model_monthly"]["duplicate_grain_count"] == 0


def test_schema_grain_matches_builder_and_is_dimensions():
    for table in TP_AND_MIX_WAYS_TABLES:
        assert GRAIN_DEFS[table.table_name] == list(table.grain)
        assert set(table.grain) <= set(table.dimensions)


def test_required_months_from_parquet(tmp_path: Path):
    raw = tmp_path / "raw_csv"
    write_snapshot(raw, ["2026年1月", "2026年2月"])
    out = tmp_path / "out"
    build_tp_and_mix_ways_dataset(
        raw_csv_dir=raw,
        parquet_dir=out / "parquet",
        registry_dir=out / "registry",
        quality_dir=out / "quality",
    )
    required = guard.required_months_from_parquet(out / "parquet")
    assert required == {table: {"2026-01", "2026-02"} for table in ALL_TABLES}


# ── updater wiring ──────────────────────────────────────────────


def test_rebuild_only_entrypoint_publishes_derived_layers(tmp_path: Path):
    dataset_root = tmp_path / "dataset"
    raw = dataset_root / "raw_csv"
    write_snapshot(raw, ["2026年1月"])
    before = {path.name: guard.sha256_file(path) for path in raw.glob("*.csv")}

    exit_code = updater.main(["--skip-export", "--dataset-root", str(dataset_root)])
    assert exit_code == 0
    assert (dataset_root / "parquet" / "brand_monthly.parquet").is_file()
    assert (dataset_root / "registry" / "tp_and_mix_ways_tables.json").is_file()
    assert (dataset_root / "quality" / "tp_and_mix_ways_dataset_quality.md").is_file()
    assert {path.name: guard.sha256_file(path) for path in raw.glob("*.csv")} == before
    manifests = list(
        (dataset_root / "staging" / "runs").glob("*/transaction_manifest.json")
    )
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "published"
    assert manifest["layers"] == ["parquet_registry_quality"]
    assert len(manifest["files"]) == 9


def test_dry_run_does_not_publish_derived_layers(tmp_path: Path):
    dataset_root = tmp_path / "dataset"
    write_snapshot(dataset_root / "raw_csv", ["2026年1月"])
    exit_code = updater.main(
        ["--skip-export", "--dry-run", "--dataset-root", str(dataset_root)]
    )
    assert exit_code == 0
    assert not (dataset_root / "parquet").exists()
    assert not (dataset_root / "registry").exists()


# ── cross-layer transaction / recovery / lock ───────────────────


def _build_baseline(raw_dir: Path, dataset_root: Path) -> None:
    build_tp_and_mix_ways_dataset(
        raw_csv_dir=raw_dir,
        parquet_dir=dataset_root / "parquet",
        registry_dir=dataset_root / "registry",
        quality_dir=dataset_root / "quality",
    )


def _dataset_files() -> list[str]:
    return [f"raw_csv/{filename}" for filename in SOURCE_MAP] + list(
        guard.EXPECTED_DERIVED_FILES
    )


def _hashes(dataset_root: Path) -> dict[str, str]:
    return {
        relative: guard.sha256_file(dataset_root / relative)
        for relative in _dataset_files()
    }


def test_build_failure_before_publish_leaves_formal_dataset_unchanged(
    tmp_path: Path, monkeypatch
):
    dataset_root = tmp_path / "dataset"
    raw_dir = dataset_root / "raw_csv"
    write_snapshot(raw_dir, ["2026年1月"])
    _build_baseline(raw_dir, dataset_root)
    before = _hashes(dataset_root)

    increment = tmp_path / "increment" / "raw_csv"
    write_snapshot(increment, ["2026年2月"])

    def fake_export(output_dir, mobile=False, timeout=600):
        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(increment, output_dir, dirs_exist_ok=True)
        return True

    def fail_build(**_kwargs):
        raise RuntimeError("simulated derived build failure")

    monkeypatch.setattr(updater, "step_export_all_views", fake_export)
    monkeypatch.setattr(updater, "_rebuild_derived_layers", fail_build)

    exit_code = updater.run_update(
        dataset_root=dataset_root, export=True, mobile=False, timeout=1, dry_run=False
    )
    assert exit_code == 1
    assert _hashes(dataset_root) == before
    assert not (dataset_root / "staging" / guard.LOCK_FILENAME).exists()
    assert not list(
        (dataset_root / "staging" / "runs").glob("*/transaction_manifest.json")
    )


def test_cross_layer_gate_rejects_missing_raw_month_in_parquet(tmp_path: Path):
    base_raw = tmp_path / "base" / "raw_csv"
    write_snapshot(base_raw, ["2026年1月"])
    derived = tmp_path / "derived"
    build_tp_and_mix_ways_dataset(
        raw_csv_dir=base_raw,
        parquet_dir=derived / "parquet",
        registry_dir=derived / "registry",
        quality_dir=derived / "quality",
    )

    staged_raw = tmp_path / "staged" / "raw_csv"
    write_snapshot(staged_raw, ["2026年1月", "2026年2月"])
    with pytest.raises(guard.RawContractError, match="月份不一致"):
        guard.validate_raw_derived_consistency(staged_raw, derived)


def test_cross_layer_publish_failure_rolls_back_every_modified_file(
    tmp_path: Path, monkeypatch
):
    dataset_root = tmp_path / "dataset"
    raw_dir = dataset_root / "raw_csv"
    write_snapshot(raw_dir, ["2026年1月"])
    _build_baseline(raw_dir, dataset_root)
    before = _hashes(dataset_root)

    staged_raw = tmp_path / "staged" / "raw_csv"
    write_snapshot(staged_raw, ["2026年1月", "2026年2月"])
    staged_derived = tmp_path / "staged_derived"
    build_tp_and_mix_ways_dataset(
        raw_csv_dir=staged_raw,
        parquet_dir=staged_derived / "parquet",
        registry_dir=staged_derived / "registry",
        quality_dir=staged_derived / "quality",
    )

    real_replace = guard.os.replace

    def flaky_replace(source, destination):
        if Path(destination).name == "model_monthly.parquet":
            raise OSError("simulated mid-transaction failure")
        return real_replace(source, destination)

    monkeypatch.setattr(guard.os, "replace", flaky_replace)
    staging_root = dataset_root / "staging"
    with pytest.raises(OSError, match="simulated mid-transaction failure"):
        guard.publish_update_transaction(
            dataset_root=dataset_root,
            run_dir=staging_root / "runs" / "tx1",
            staging_root=staging_root,
            raw_dir=staged_raw,
            derived_dir=staged_derived,
            validation={"raw": "ok", "derived": "ok"},
            audit={"merge": "ok"},
        )

    assert _hashes(dataset_root) == before
    manifest = json.loads(
        (
            staging_root / "runs" / "tx1" / guard.TRANSACTION_MANIFEST_NAME
        ).read_text(encoding="utf-8")
    )
    assert manifest["status"] == "failed"
    assert manifest["published_before_failure"]
    assert manifest["layers"] == ["raw_csv", "parquet_registry_quality"]


def _write_incomplete_manifest(
    dataset_root: Path,
    staging_root: Path,
    *,
    run_id: str = "crashed",
    with_backup: bool = True,
) -> tuple[Path, Path, Path | None]:
    relative = "raw_csv/way1_market_energy_monthly_data.csv"
    destination = dataset_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("new-content\n", encoding="utf-8")

    backup: Path | None = None
    if with_backup:
        backup = staging_root / "backups" / run_id / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text("old-content\n", encoding="utf-8")

    manifest_path = staging_root / "runs" / run_id / guard.TRANSACTION_MANIFEST_NAME
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "publishing",
                "files": {
                    relative: {
                        "destination": str(destination),
                        "backup": str(backup) if backup else None,
                        "previous_sha256": guard.sha256_file(backup) if backup else "missing",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest_path, destination, backup


def test_incomplete_publishing_manifest_is_recovered(tmp_path: Path):
    dataset_root = tmp_path / "dataset"
    staging_root = dataset_root / "staging"
    manifest_path, destination, _ = _write_incomplete_manifest(
        dataset_root, staging_root
    )

    recovered = guard.recover_incomplete_transactions(staging_root)
    assert len(recovered) == 1
    assert destination.read_text(encoding="utf-8") == "old-content\n"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "recovered"
    assert manifest["restore_errors"] == []


def test_failed_recovery_marks_manifest_and_raises(tmp_path: Path):
    dataset_root = tmp_path / "dataset"
    staging_root = dataset_root / "staging"
    manifest_path, destination, _ = _write_incomplete_manifest(
        dataset_root, staging_root, with_backup=False
    )

    with pytest.raises(guard.RawContractError, match="恢复失败"):
        guard.recover_incomplete_transactions(staging_root)
    assert destination.read_text(encoding="utf-8") == "new-content\n"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "recovery_failed"


def test_update_recovers_incomplete_manifest_before_publishing(tmp_path: Path):
    dataset_root = tmp_path / "dataset"
    raw_dir = dataset_root / "raw_csv"
    write_snapshot(raw_dir, ["2026年1月"])
    _build_baseline(raw_dir, dataset_root)

    relative = "raw_csv/way1_market_energy_monthly_data.csv"
    destination = dataset_root / relative
    original = destination.read_bytes()
    staging_root = dataset_root / "staging"
    backup = staging_root / "backups" / "crashed" / relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(original)
    destination.write_text("corrupted-after-crash\n", encoding="utf-8")
    manifest_path = staging_root / "runs" / "crashed" / guard.TRANSACTION_MANIFEST_NAME
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": "crashed",
                "status": "publishing",
                "files": {
                    relative: {
                        "destination": str(destination),
                        "backup": str(backup),
                        "previous_sha256": guard.sha256_file(backup),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    # The crash happened after the formal file was replaced; recovery must put
    # the pre-transaction content back before the next update proceeds.
    assert destination.read_bytes() != original

    exit_code = updater.main(["--skip-export", "--dataset-root", str(dataset_root)])
    assert exit_code == 0
    assert destination.read_bytes() == original
    recovered_manifest = json.loads(
        (staging_root / "runs" / "crashed" / guard.TRANSACTION_MANIFEST_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert recovered_manifest["status"] == "recovered"
    assert not (staging_root / guard.LOCK_FILENAME).exists()


def test_concurrent_update_is_blocked_by_run_lock(tmp_path: Path):
    dataset_root = tmp_path / "dataset"
    write_snapshot(dataset_root / "raw_csv", ["2026年1月"])
    staging_root = dataset_root / "staging"
    staging_root.mkdir(parents=True)
    lock_path = staging_root / guard.LOCK_FILENAME
    lock_path.write_text(
        json.dumps({"run_id": "other", "pid": os.getpid(), "created_at": "now"}),
        encoding="utf-8",
    )

    exit_code = updater.main(["--skip-export", "--dataset-root", str(dataset_root)])
    assert exit_code == 1
    assert lock_path.exists()
    assert not (dataset_root / "parquet").exists()


def test_stale_run_lock_is_preserved_and_update_proceeds(tmp_path: Path):
    dataset_root = tmp_path / "dataset"
    write_snapshot(dataset_root / "raw_csv", ["2026年1月"])
    staging_root = dataset_root / "staging"
    staging_root.mkdir(parents=True)
    lock_path = staging_root / guard.LOCK_FILENAME
    lock_path.write_text(
        json.dumps({"run_id": "crashed", "pid": 999999, "created_at": "old"}),
        encoding="utf-8",
    )

    exit_code = updater.main(["--skip-export", "--dataset-root", str(dataset_root)])
    assert exit_code == 0
    assert not lock_path.exists()
    assert list((staging_root / "locks").glob("stale-lock-*.json"))
    assert (dataset_root / "parquet" / "brand_monthly.parquet").is_file()


def test_repeated_sequential_updates_succeed(tmp_path: Path):
    dataset_root = tmp_path / "dataset"
    write_snapshot(dataset_root / "raw_csv", ["2026年1月"])

    assert updater.main(["--skip-export", "--dataset-root", str(dataset_root)]) == 0
    first = list(
        (dataset_root / "staging" / "runs").glob("*/transaction_manifest.json")
    )
    assert len(first) == 1

    assert updater.main(["--skip-export", "--dataset-root", str(dataset_root)]) == 0
    manifests = list(
        (dataset_root / "staging" / "runs").glob("*/transaction_manifest.json")
    )
    assert len(manifests) == 2
    assert all(
        json.loads(path.read_text(encoding="utf-8"))["status"] == "published"
        for path in manifests
    )
    assert not (dataset_root / "staging" / guard.LOCK_FILENAME).exists()


def test_mass_month_deletion_blocks_by_default_and_is_configurable(tmp_path: Path):
    formal_raw = tmp_path / "formal" / "raw_csv"
    write_snapshot(formal_raw, ["2026年1月", "2026年2月"])
    increment = tmp_path / "increment" / "raw_csv"
    write_snapshot(increment, ["2026年2月"])

    # Drop 2 of the 3 model splits in the replaced month: 4 of 6 measure rows
    # disappear, which must not pass silently.
    model_path = increment / "way3_model_monthly_data.csv"
    snapshot = guard.read_pivot_csv(model_path)
    kept = [
        row
        for row in snapshot.rows
        if row["燃料类型"] == "纯电" and row["驱动形式"] == "前轮驱动"
    ]
    assert len(kept) == 2
    guard.write_pivot_csv(model_path, snapshot.header, kept)

    with pytest.raises(guard.RawContractError, match="删除比例超过阈值"):
        guard.merge_snapshot_to_staging(
            formal_raw, increment, tmp_path / "merged" / "raw_csv"
        )

    plan = guard.merge_snapshot_to_staging(
        formal_raw,
        increment,
        tmp_path / "merged_ok" / "raw_csv",
        max_month_deletion_ratio=1.0,
    )
    stats = plan["tables"]["model_monthly"]
    assert stats["removed_rows"] == 4
    feb_audit = next(
        item for item in stats["month_audit"] if item["month"] == "2026-02"
    )
    assert feb_audit["base_rows"] == 6
    assert feb_audit["increment_rows"] == 2
    assert feb_audit["removed_rows"] == 4
    assert feb_audit["deletion_ratio"] == pytest.approx(4 / 6)


def test_missing_baseline_file_is_an_error(tmp_path: Path):
    dataset_root = tmp_path / "dataset"
    raw_dir = dataset_root / "raw_csv"
    write_snapshot(raw_dir, ["2026年1月"])
    _build_baseline(raw_dir, dataset_root)

    (dataset_root / "parquet" / "model_monthly.parquet").unlink()
    with pytest.raises(guard.RawContractError, match="parquet 基线不完整"):
        guard.required_months_from_parquet(dataset_root / "parquet")
    with pytest.raises(guard.RawContractError, match="基线不完整"):
        guard.validate_derived_baseline(dataset_root)

    assert updater.main(["--skip-export", "--dataset-root", str(dataset_root)]) == 1
    assert not (dataset_root / "staging" / guard.LOCK_FILENAME).exists()
    assert not list(
        (dataset_root / "staging" / "runs").glob("*/transaction_manifest.json")
    )
