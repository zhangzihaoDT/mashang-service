"""
Tests for passenger_insurance dataset build, schema, and loader.

Usage:
    pytest tests/test_passenger_insurance_dataset_build.py -q
"""

from __future__ import annotations
import inspect
import json
from pathlib import Path

import pytest

from shared.schema.passenger_insurance_schema import (
    PASSENGER_INSURANCE_TABLES,
    get_table_def,
    list_table_names,
)
from shared.loaders.passenger_insurance_loader import (
    get_service_root,
    get_passenger_insurance_dataset_root,
    get_registry_root,
    get_raw_csv_root,
    get_parquet_root,
    load_passenger_insurance_registry,
)


# ── Schema Tests ──────────────────────────────────────────────────


class TestSchema:
    def test_six_tables_defined(self):
        assert len(PASSENGER_INSURANCE_TABLES) == 6

    def test_table_names(self):
        names = list_table_names()
        assert names == [
            "market_energy_monthly",
            "brand_monthly",
            "model_monthly",
            "geo_monthly",
            "price_segment_monthly",
            "product_segment_monthly",
        ]

    def test_every_table_has_grain(self):
        for t in PASSENGER_INSURANCE_TABLES:
            assert len(t.grain) > 0, f"{t.table_name} has empty grain"

    def test_every_table_has_dimensions(self):
        for t in PASSENGER_INSURANCE_TABLES:
            assert len(t.dimensions) > 0, f"{t.table_name} has empty dimensions"

    def test_every_table_has_metrics(self):
        for t in PASSENGER_INSURANCE_TABLES:
            assert len(t.metrics) > 0, f"{t.table_name} has empty metrics"

    def test_every_table_has_purpose(self):
        for t in PASSENGER_INSURANCE_TABLES:
            assert t.purpose, f"{t.table_name} has empty purpose"

    def test_get_table_def(self):
        t = get_table_def("brand_monthly")
        assert t is not None
        assert t.table_name == "brand_monthly"

    def test_get_table_def_nonexistent(self):
        assert get_table_def("nonexistent") is None

    def test_source_csv_not_empty(self):
        for t in PASSENGER_INSURANCE_TABLES:
            assert t.source_csv, f"{t.table_name} missing source_csv"

    def test_parquet_path_not_empty(self):
        for t in PASSENGER_INSURANCE_TABLES:
            assert t.parquet_path, f"{t.table_name} missing parquet_path"


# ── Loader Tests ──────────────────────────────────────────────────


class TestLoader:
    def test_get_service_root(self):
        root = get_service_root()
        assert root.exists()
        assert (root / "Makefile").exists()

    def test_get_passenger_insurance_dataset_root(self):
        dset_root = get_passenger_insurance_dataset_root()
        assert dset_root.exists()
        assert dset_root.name == "passenger_insurance"

    def test_get_registry_root(self):
        reg_root = get_registry_root()
        assert reg_root.exists()

    def test_get_raw_csv_root(self):
        raw_root = get_raw_csv_root()
        assert raw_root.exists()

    def test_get_parquet_root(self):
        par_root = get_parquet_root()
        assert par_root.exists()


# ── Registry Tests ────────────────────────────────────────────────


class TestRegistry:
    def test_registry_json_exists(self):
        registry_path = get_registry_root() / "passenger_insurance_tables.json"
        assert registry_path.exists(), (
            f"Registry not found at {registry_path}. "
            "Run `make build-passenger-insurance-dataset` first."
        )

    def test_registry_can_be_read(self):
        registry = load_passenger_insurance_registry()
        assert "tables" in registry
        assert registry["dataset_name"] == "passenger_insurance"

    def test_registry_has_six_tables(self):
        registry = load_passenger_insurance_registry()
        assert len(registry["tables"]) == 6

    def test_each_table_has_required_keys(self):
        registry = load_passenger_insurance_registry()
        for t in registry["tables"]:
            assert "table_name" in t
            assert "parquet_path" in t
            assert "grain" in t
            assert "build_status" in t

    def test_non_error_tables_have_row_count(self):
        registry = load_passenger_insurance_registry()
        for t in registry["tables"]:
            if t.get("build_status") == "success":
                assert t.get("row_count", 0) > 0, f"{t['table_name']} has 0 rows"


# ── Build Script Tests ────────────────────────────────────────────


class TestBuildScript:
    def test_field_mappings_not_empty(self):
        from scripts.build_passenger_insurance_dataset import COLUMN_MAP
        assert len(COLUMN_MAP) == 6
        for table_name, mappings in COLUMN_MAP.items():
            assert len(mappings) > 0, f"{table_name} has empty column mapping"

    def test_grain_defs_not_empty(self):
        from scripts.build_passenger_insurance_dataset import GRAIN_DEFS
        assert len(GRAIN_DEFS) == 6
        for table_name, grain in GRAIN_DEFS.items():
            assert len(grain) > 0, f"{table_name} has empty grain def"

    def test_no_merge_into_wide_table(self):
        from scripts.build_passenger_insurance_dataset import build_passenger_insurance_dataset
        source = inspect.getsource(build_passenger_insurance_dataset)
        assert "merge" not in source.lower(), (
            "Build script appears to merge tables into a wide table"
        )
        assert "concat" not in source.lower() or "pd.concat" not in source, (
            "Build script appears to concatenate tables"
        )

    def test_raw_csv_exists(self):
        from scripts.build_passenger_insurance_dataset import RAW_CSV_DIR, SOURCE_MAP
        for csv_name in SOURCE_MAP:
            csv_path = RAW_CSV_DIR / csv_name
            assert csv_path.exists(), (
                f"Required raw CSV not found: {csv_path}. "
                "Ensure Tableau exports are placed in dataset/passenger_insurance/raw_csv/."
            )

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parent.parent / "dataset" / "passenger_insurance" / "raw_csv").exists(),
        reason="raw_csv directory does not exist",
    )
    def test_can_build_if_raw_csv_has_files(self):
        from scripts.build_passenger_insurance_dataset import RAW_CSV_DIR, SOURCE_MAP
        raw_files = {f.name for f in RAW_CSV_DIR.iterdir() if f.is_file() and f.name.endswith(".csv")}
        expected = set(SOURCE_MAP.keys())
        if expected.issubset(raw_files):
            from scripts.build_passenger_insurance_dataset import build_passenger_insurance_dataset
            reports = build_passenger_insurance_dataset()
            assert len(reports) == 6
            for r in reports:
                assert r["build_status"] in ("success", "error"), f"{r['table_name']} unexpected status"

    def test_error_if_raw_csv_missing(self):
        from scripts.build_passenger_insurance_dataset import RAW_CSV_DIR, SOURCE_MAP
        raw_files = {f.name for f in RAW_CSV_DIR.iterdir() if f.is_file() and f.name.endswith(".csv")}
        expected = set(SOURCE_MAP.keys())
        missing = expected - raw_files
        if missing:
            with pytest.raises(SystemExit):
                from scripts.build_passenger_insurance_dataset import main
                main()


# ── Parquet Output Tests ──────────────────────────────────────────


class TestParquetOutput:
    def test_parquet_files_exist(self):
        from scripts.build_passenger_insurance_dataset import PARQUET_DIR
        expected_parquets = [
            "market_energy_monthly.parquet",
            "brand_monthly.parquet",
            "model_monthly.parquet",
            "geo_monthly.parquet",
            "price_segment_monthly.parquet",
            "product_segment_monthly.parquet",
        ]
        for name in expected_parquets:
            path = PARQUET_DIR / name
            assert path.exists(), (
                f"Parquet file not found: {path}. "
                "Run `make build-passenger-insurance-dataset` first."
            )

    def test_parquet_can_be_read(self):
        import pandas as pd
        from scripts.build_passenger_insurance_dataset import PARQUET_DIR
        for name in PARQUET_DIR.iterdir():
            if name.suffix == ".parquet":
                df = pd.read_parquet(name)
                assert len(df) > 0, f"{name.name} is empty"
                break
