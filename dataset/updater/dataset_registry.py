#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dataset 数据集唯一清单（single source of truth）。

被两处共同消费，避免「更新清单 / 校验清单 / 汇总清单」三处漂移：

- dataset/updater/update_all_datasets.py（刷新 + 逐数据集汇总）
- mashang_workspace/utility_scripts/dataset_validate.py（完整性校验）

每个数据集声明：所属更新 step、是否必需、关键字段、用于表示「数据最新时点」的日期列。
"""

from __future__ import annotations

import csv
import os
import unicodedata
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"

# 门店主数据落在仓库外的 original 目录；允许用环境变量覆盖，默认保持历史路径。
STORE_INFO_CSV = Path(
    os.getenv(
        "STORE_INFO_CSV",
        "/Users/zihao_/Documents/coding/dataset/original/store_info.csv",
    )
)


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    label: str
    path: Path
    step_id: str
    required: bool = False
    key_fields: tuple[str, ...] = ()
    date_columns: tuple[str, ...] = ()
    note: str = ""

    @property
    def display_path(self) -> str:
        try:
            return str(self.path.relative_to(REPO_ROOT))
        except ValueError:
            return str(self.path)


DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        "order_data",
        "订单数据",
        DATASET_DIR / "order_data.parquet",
        "1",
        required=True,
        key_fields=("order_number", "lock_time"),
        date_columns=(
            "lock_time",
            "deposit_payment_time",
            "intention_payment_time",
            "order_create_date",
        ),
    ),
    DatasetSpec(
        "config_attribute",
        "选配信息",
        DATASET_DIR / "config_attribute.parquet",
        "2",
        required=True,
        key_fields=("Order Number",),
    ),
    DatasetSpec(
        "assign_data",
        "下发线索",
        DATASET_DIR / "assign_data.csv",
        "3",
        required=True,
        key_fields=("Assign Time 年/月/日",),
        date_columns=("Assign Time 年/月/日",),
    ),
    DatasetSpec(
        "test_drive_data",
        "试驾数据",
        DATASET_DIR / "test_drive_data.csv",
        "3",
        date_columns=("create_date 年/月/日",),
    ),
    DatasetSpec(
        "lock_attribution",
        "锁单归因",
        DATASET_DIR / "lock_attribution_data.parquet",
        "3",
        date_columns=("lc_order_lock_time_min",),
    ),
    DatasetSpec(
        "delivery_inventory",
        "交付-库存",
        DATASET_DIR / "delivery_inventory.parquet",
        "4",
        date_columns=("attribute_dealer_date",),
    ),
    DatasetSpec(
        "store_info",
        "门店主数据",
        STORE_INFO_CSV,
        "5",
    ),
    DatasetSpec(
        "store_daily_leads",
        "每日下发线索（by门店）",
        DATASET_DIR / "store_daily_leads.csv",
        "6",
        date_columns=("日期",),
    ),
)

DATASETS_BY_KEY = {spec.key: spec for spec in DATASETS}


def _columns(path: Path) -> list[str]:
    """只读 schema/表头，避免为拿列名加载全量数据。"""
    try:
        if path.suffix == ".parquet":
            import pyarrow.parquet as pq

            return list(pq.ParquetFile(path).schema_arrow.names)
        if path.suffix == ".csv":
            with open(path, newline="", encoding="utf-8", errors="ignore") as f:
                return [c.strip() for c in next(csv.reader(f))]
    except Exception:
        return []
    return []


def _row_count(path: Path) -> int | None:
    try:
        if path.suffix == ".parquet":
            import pyarrow.parquet as pq

            return pq.ParquetFile(path).metadata.num_rows
        if path.suffix == ".csv":
            with open(path, encoding="utf-8", errors="ignore") as f:
                return max(sum(1 for _ in f) - 1, 0)
    except Exception:
        return None
    return None


def _parse_dates(series):
    import pandas as pd

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        parsed = pd.to_datetime(series, errors="coerce")
        if parsed.notna().any():
            return parsed
        # 兼容 Tableau 导出的中文日期（2026年9月25日）
        cleaned = (
            series.astype(str)
            .str.replace("年", "-", regex=False)
            .str.replace("月", "-", regex=False)
            .str.replace("日", "", regex=False)
        )
        return pd.to_datetime(cleaned, errors="coerce")


def _latest_date(path: Path, date_columns: Iterable[str]):
    """返回 (最新时点 Timestamp | None, 命中的列名 | None)。"""
    cols = list(date_columns)
    if not cols:
        return None, None
    try:
        import pandas as pd

        if path.suffix == ".parquet":
            present = [c for c in cols if c in _columns(path)]
            if not present:
                return None, None
            df = pd.read_parquet(path, columns=present)
        elif path.suffix == ".csv":
            header = _columns(path)
            present = [c for c in cols if c in header]
            if not present:
                return None, None
            df = pd.read_csv(path, usecols=present, low_memory=False)
        else:
            return None, None
    except Exception:
        return None, None

    best = None
    best_col = None
    for c in df.columns:
        s = _parse_dates(df[c])
        if s.notna().any():
            m = s.max()
            if best is None or m > best:
                best, best_col = m, c
    return best, best_col


def describe(spec: DatasetSpec) -> dict:
    """读取单个数据集的现状：是否存在、行数、文件更新时间、数据最新时点。"""
    path = spec.path
    out = {
        "key": spec.key,
        "label": spec.label,
        "path": spec.display_path,
        "step_id": spec.step_id,
        "required": spec.required,
        "exists": path.exists(),
        "rows": None,
        "size_bytes": None,
        "file_mtime": None,
        "data_asof": None,
        "data_asof_column": None,
        "columns": [],
    }
    if not path.exists():
        return out
    stat = path.stat()
    out["size_bytes"] = stat.st_size
    out["file_mtime"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
    out["rows"] = _row_count(path)
    out["columns"] = _columns(path)
    asof, col = _latest_date(path, spec.date_columns)
    if asof is not None:
        out["data_asof"] = asof.isoformat()
        out["data_asof_column"] = col
    return out


def describe_all() -> list[dict]:
    return [describe(spec) for spec in DATASETS]


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(width - _width(text), 0)


def _fmt_ts(iso: str | None, *, with_date: bool = True) -> str:
    if not iso:
        return "-"
    dt = datetime.fromisoformat(iso)
    return dt.strftime("%m-%d %H:%M") if with_date else dt.strftime("%H:%M")


def format_report(
    descs: list[dict],
    *,
    run_started: float | None = None,
    failed_steps: Iterable[str] = frozenset(),
    status_only: bool = False,
) -> str:
    """逐数据集结论表：本次是否更新、状态、行数、文件更新时间、数据最新时点。"""
    failed_steps = set(failed_steps)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = []
    lines.append("=" * 96)
    lines.append(f"数据集汇总（{len(descs)} 个，截至 {now}）")
    lines.append("=" * 96)
    header = [
        ("数据集", 18),
        ("本次", 10),
        ("状态", 8),
        ("行数", 10),
        ("文件更新", 14),
        ("数据最新时点", 28),
    ]
    lines.append("  ".join(_pad(h, w) for h, w in header))
    lines.append("-" * 96)
    updated = 0
    for d in descs:
        if not d["exists"]:
            refreshed = False
            status = "缺失"
        elif status_only or run_started is None:
            refreshed = False
            status = "OK"
        else:
            mtime = d["file_mtime"]
            refreshed = (
                run_started is not None
                and mtime is not None
                and datetime.fromisoformat(mtime).timestamp() >= run_started
            )
            if refreshed:
                status = "OK"
            elif d["step_id"] in failed_steps:
                status = "失败"
            else:
                status = "未更新"
        if refreshed:
            updated += 1
        this_run = "-" if status_only or run_started is None else ("已更新" if refreshed else "未更新")
        rows = f"{d['rows']:,}" if d["rows"] is not None else "-"
        if d["data_asof"]:
            asof = f"{_fmt_ts(d['data_asof'])} ({d['data_asof_column']})"
        elif d["exists"]:
            asof = "无日期列"
        else:
            asof = "-"
        row = [
            (_pad(d["label"], 18)),
            (_pad(this_run, 10)),
            (_pad(status, 8)),
            (_pad(rows, 10)),
            (_pad(_fmt_ts(d["file_mtime"]) if d["file_mtime"] else "-", 14)),
            (_pad(asof, 28)),
        ]
        lines.append("  ".join(row))
    lines.append("-" * 96)
    if status_only or run_started is None:
        lines.append("只读现状（未执行刷新）。")
    else:
        lines.append(f"本次已更新 {updated}/{len(descs)} 个数据集。")
    return "\n".join(lines)



