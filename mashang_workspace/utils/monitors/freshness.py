"""order_data 新鲜度 gate — 按小时判断数据是否覆盖到当前时刻。

`latest_ts = max(max(lock_time), max(intention_payment_time))`。
`now - latest_ts > max_staleness_hours` 即视为 stale，监控应跳过指标推送并告警。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from utils.paths import DATASET_DIR

ORDER_DATA_PARQUET = DATASET_DIR / "order_data.parquet"
DEFAULT_MAX_STALENESS_HOURS = 2


def max_staleness_hours(bdef: dict | None = None) -> float:
    mon = (bdef or {}).get("monitor") or {}
    return float((mon.get("freshness") or {}).get("max_staleness_hours", DEFAULT_MAX_STALENESS_HOURS))


def latest_data_ts(order_parquet: Path | str | None = None) -> pd.Timestamp | None:
    p = Path(order_parquet) if order_parquet else ORDER_DATA_PARQUET
    if not p.exists():
        return None
    cols = [c for c in ("lock_time", "intention_payment_time") if c in _columns(p)]
    if not cols:
        return None
    df = pd.read_parquet(p, columns=cols)
    stamps: list[pd.Timestamp] = []
    for c in cols:
        m = pd.to_datetime(df[c], errors="coerce").max()
        if pd.notna(m):
            stamps.append(pd.Timestamp(m))  # type: ignore[arg-type]
    return max(stamps) if stamps else None


def _columns(path: Path) -> list[str]:
    try:
        import pyarrow.parquet as pq

        return list(pq.ParquetFile(path).schema.names)
    except Exception:
        return []


def check(
    now: pd.Timestamp | None = None,
    max_hours: float | None = None,
    bdef: dict | None = None,
    order_parquet: Path | str | None = None,
) -> dict:
    p = Path(order_parquet) if order_parquet else ORDER_DATA_PARQUET
    now_ts = pd.Timestamp(now) if now is not None else pd.Timestamp.now()
    if max_hours is None:
        max_hours = max_staleness_hours(bdef)
    mtime = pd.Timestamp(p.stat().st_mtime, unit="s") if p.exists() else None
    latest = latest_data_ts(p)
    if latest is None:
        return {
            "latest_ts": None,
            "mtime": mtime,
            "age_hours": None,
            "max_staleness_hours": max_hours,
            "fresh": False,
            "reason": "无法读取 order_data 最新时间",
        }
    age_hours = (now_ts - latest).total_seconds() / 3600.0
    fresh = age_hours <= max_hours
    reason = (
        "ok"
        if fresh
        else f"最新数据 {latest:%Y-%m-%d %H:%M}，距今 {age_hours:.1f}h > {max_hours:g}h"
    )
    return {
        "latest_ts": latest,
        "mtime": mtime,
        "age_hours": age_hours,
        "max_staleness_hours": max_hours,
        "fresh": fresh,
        "reason": reason,
    }
