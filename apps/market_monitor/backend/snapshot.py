"""Project upstream assets into the app's versioned monthly read models."""

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]
SOURCES = json.loads((APP / "configs/sources.json").read_text(encoding="utf-8"))
VERSION = 1
MONTH_PATTERN = re.compile(r"[0-9]{4}-(?:0[1-9]|1[0-2])")
INSURANCE_TABLES = ("market_energy_monthly", "brand_monthly")
MIIT_FIELDS = (
    "vehicle_record_id", "batch_no", "model_code", "brand", "manufacturer",
    "product_name", "common_name", "publish_date", "source", "stage", "detail_url",
)


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def snapshot_dir():
    return Path(os.environ.get("MARKET_MONITOR_SNAPSHOT_DIR", APP / "var"))


def miit_file():
    return Path(os.environ.get(
        "MARKET_MONITOR_MIIT_FILE", ROOT.parent / SOURCES["miit"]["artifact"],
    ))


def build_insurance():
    import pandas as pd

    from shared.loaders.tp_and_mix_ways_loader import (
        load_tp_and_mix_ways_registry,
        load_tp_and_mix_ways_table,
    )
    from workspace.research_scripts.market_report.generate_monthly_brief import (
        ReportData,
        build_brand_landscape,
        build_overall_market,
    )

    registry = load_tp_and_mix_ways_registry()
    entries = {row["table_name"]: row for row in registry["tables"]}
    frames = {}
    coverage = {}
    for table in INSURANCE_TABLES:
        entry = entries[table]
        frame = load_tp_and_mix_ways_table(table)
        if frame is None or frame.empty or len(frame) != entry["row_count"]:
            raise ValueError(f"{table} 缺失或行数与 registry 不一致")
        dates = pd.to_datetime(frame["date_month"], errors="raise")
        if (dates.isna().any() or (dates.dt.day != 1).any()
                or dates.min().date().isoformat() != entry["date_min"]
                or dates.max().date().isoformat() != entry["date_max"]):
            raise ValueError(f"{table} 月份与 registry 不一致")
        if (frame.duplicated(entry["grain"]).any() or frame["sales"].isna().any()
                or (frame["sales"] < 0).any() or frame["weighted_tp"].isna().any()):
            raise ValueError(f"{table} 有重复粒度、缺失或异常数值")
        frames[table] = frame.assign(date_month=dates)
        coverage[table] = set(dates.dt.strftime("%Y-%m"))
    if registry != load_tp_and_mix_ways_registry():
        raise ValueError("上险 registry 在读取期间更新，请重试")
    market_months, brand_months = (coverage[table] for table in INSURANCE_TABLES)
    if market_months != brand_months:
        raise ValueError("上险总量表和品牌表的月份覆盖不一致")

    months = {}
    for month in sorted(market_months):
        report_data = ReportData(month, frames=frames)
        overall = build_overall_market(report_data)
        brands = build_brand_landscape(report_data)
        if overall["total_sales"] != brands["total_sales"]:
            raise ValueError(f"{month} 上险总量表与品牌表未对齐")
        months[month] = {
            "metrics": {key: overall[key] for key in (
                "total_sales", "mom_pct", "yoy_pct", "nev_penetration", "weighted_tp",
            )},
            "energy": [
                {key: row[key] for key in ("group", "type", "sales", "share_pct")}
                for row in sorted(overall["energy_breakdown"], key=lambda row: -row["sales"])
            ],
            "brands": [
                {key: row[key] for key in ("brand", "sales", "share_pct")}
                for row in brands["top20"][:10]
            ],
        }
    return envelope("insurance", months, registry.get("build_timestamp"))


def build_miit(path: Path):
    with path.open("rb") as upstream:
        records = json.load(upstream)
        modified_at = datetime.fromtimestamp(os.fstat(upstream.fileno()).st_mtime, timezone.utc)
    if not isinstance(records, list) or not records:
        raise ValueError("MIIT product_master 应为非空记录数组")
    months = {}
    seen = set()
    for record in records:
        if not isinstance(record, dict) or record.get("vehicle_category") != "passenger_vehicle":
            raise ValueError("MIIT product_master 乘用车契约不符")
        batch, code, identity = (record[key] for key in ("batch_no", "model_code", "vehicle_record_id"))
        if not isinstance(batch, str) or not re.fullmatch(r"[0-9]+", batch) or not isinstance(code, str) or not code:
            raise ValueError("MIIT 记录缺少批次号或型号")
        if identity != f"{batch}:{code}" or identity in seen:
            raise ValueError("MIIT 批次与型号的 canonical 身份不唯一或不匹配")
        if record["stage"] not in {"proposed", "confirmed"} or record["source"] not in {"eidc", "miit_gov"}:
            raise ValueError("MIIT 发布阶段或来源不符合契约")
        seen.add(identity)
        published = date.fromisoformat(record["publish_date"]).isoformat()
        if published != record["publish_date"]:
            raise ValueError("MIIT 发布日期应为 YYYY-MM-DD")
        row = {key: record.get(key, "") for key in MIIT_FIELDS}
        months.setdefault(published[:7], []).append(row)
    for rows in months.values():
        rows.sort(key=lambda row: (row["publish_date"], int(row["batch_no"]), row["model_code"]), reverse=True)
    return envelope("miit", months, modified_at.isoformat(timespec="seconds"))


def envelope(source, months, upstream_updated_at):
    return {
        "schema_version": VERSION,
        "source": source,
        "refreshed_at": stamp(),
        "upstream_updated_at": upstream_updated_at,
        "latest_month": max(months),
        "months": months,
    }


def read_snapshot(directory: Path, source: str):
    path = directory / f"{source}.json"
    try:
        snapshot = json.loads(path.read_bytes())
    except FileNotFoundError:
        return None
    if (not isinstance(snapshot, dict) or snapshot.get("schema_version") != VERSION
            or snapshot.get("source") != source or not isinstance(snapshot.get("months"), dict)
            or not isinstance(snapshot.get("latest_month"), str)
            or snapshot["latest_month"] not in snapshot["months"]
            or not isinstance(snapshot.get("refreshed_at"), str)
            or "upstream_updated_at" not in snapshot):
        raise ValueError(f"{source} 快照格式不符")
    return snapshot


def publish(directory: Path, source: str, snapshot):
    content = encode(snapshot)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as temporary:
            name = temporary.name
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(name, directory / f"{source}.json")
    finally:
        if name:
            Path(name).unlink(missing_ok=True)


@contextmanager
def snapshot_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".refresh.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def import_snapshot(directory: Path, source: str, snapshot):
    """Accept the versioned app projection from a trusted deployment operator."""
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != VERSION or snapshot.get("source") != source:
        raise ValueError("快照版本或来源不符")
    months = snapshot.get("months")
    if (not isinstance(months, dict) or not months
            or any(not MONTH_PATTERN.fullmatch(key) or key.startswith("0000") for key in months)
            or snapshot.get("latest_month") != max(months) or "upstream_updated_at" not in snapshot):
        raise ValueError("快照月份或来源元数据不符")
    refreshed_at = datetime.fromisoformat(snapshot["refreshed_at"])
    if refreshed_at.tzinfo is None:
        raise ValueError("快照生成时间缺少时区")
    for data in months.values():
        if source == "insurance":
            if (not isinstance(data, dict) or not isinstance(data.get("metrics"), dict)
                    or not isinstance(data.get("energy"), list) or not isinstance(data.get("brands"), list)
                    or "total_sales" not in data["metrics"]):
                raise ValueError("上险快照缺少所需字段")
        elif not isinstance(data, list) or not data or any(
            not isinstance(row, dict) or not set(MIIT_FIELDS).issubset(row) for row in data
        ):
            raise ValueError("MIIT 快照缺少所需字段")
    with snapshot_lock(directory):
        previous = read_snapshot(directory, source)
        if previous and (
            refreshed_at < datetime.fromisoformat(previous["refreshed_at"])
            or snapshot["latest_month"] < previous["latest_month"]
        ):
            raise ValueError("快照时间或最新覆盖月早于线上版本")
        publish(directory, source, snapshot)
