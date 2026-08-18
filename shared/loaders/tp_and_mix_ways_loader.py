from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pandas as pd
except ImportError:
    pd = None


def get_service_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_tp_and_mix_ways_dataset_root() -> Path:
    return get_service_root() / "dataset" / "TP&MIX-ways"


def get_raw_csv_root() -> Path:
    return get_tp_and_mix_ways_dataset_root() / "raw_csv"


def get_parquet_root() -> Path:
    return get_tp_and_mix_ways_dataset_root() / "parquet"


def get_registry_root() -> Path:
    return get_tp_and_mix_ways_dataset_root() / "registry"


def get_quality_root() -> Path:
    return get_tp_and_mix_ways_dataset_root() / "quality"


def load_tp_and_mix_ways_registry() -> Dict[str, Any]:
    registry_path = get_registry_root() / "tp_and_mix_ways_tables.json"
    if not registry_path.exists():
        return {"tables": [], "build_info": {}}
    return json.loads(registry_path.read_text(encoding="utf-8"))


def list_tp_and_mix_ways_tables() -> List[str]:
    registry = load_tp_and_mix_ways_registry()
    return [t["table_name"] for t in registry.get("tables", [])]


def load_tp_and_mix_ways_table(table_name: str) -> Optional["pd.DataFrame"]:
    if pd is None:
        raise ImportError("pandas is required to load TP&MIX-ways tables")
    registry = load_tp_and_mix_ways_registry()
    for t in registry.get("tables", []):
        if t["table_name"] == table_name:
            parquet_path = get_parquet_root() / t["parquet_path"]
            if parquet_path.exists():
                return pd.read_parquet(parquet_path)
            return None
    return None


def load_tp_and_mix_ways_table_duckdb(table_name: str, duckdb_conn=None):
    registry = load_tp_and_mix_ways_registry()
    for t in registry.get("tables", []):
        if t["table_name"] == table_name:
            parquet_path = get_parquet_root() / t["parquet_path"]
            if not parquet_path.exists():
                return None
            parquet_abs = str(parquet_path.resolve())
            if duckdb_conn is not None:
                return duckdb_conn.execute(f"SELECT * FROM read_parquet('{parquet_abs}')").fetchdf()
            import duckdb
            con = duckdb.connect()
            result = con.execute(f"SELECT * FROM read_parquet('{parquet_abs}')").fetchdf()
            con.close()
            return result
    return None
