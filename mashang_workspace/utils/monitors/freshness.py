"""order_data 新鲜度 gate — 以「数据刷新时间」判断数据是否可用。

参考时刻 `refresh_ts` 来源：
  - 调度器在本轮刷新成功后传入的完成时刻（优先）；
  - 手动运行回退 `order_data.parquet` 的 mtime。

`now - refresh_ts > max_refresh_age_minutes` 即视为 stale，监控应跳过指标推送并告警。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from utils.paths import DATASET_DIR

ORDER_DATA_PARQUET = DATASET_DIR / "order_data.parquet"
DEFAULT_MAX_REFRESH_AGE_MINUTES = 2


def max_refresh_age_minutes(bdef: dict | None = None) -> float:
    mon = (bdef or {}).get("monitor") or {}
    fresh = mon.get("freshness") or {}
    return float(fresh.get("max_refresh_age_minutes", DEFAULT_MAX_REFRESH_AGE_MINUTES))


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
    max_minutes: float | None = None,
    bdef: dict | None = None,
    order_parquet: Path | str | None = None,
    refresh_ts: pd.Timestamp | str | None = None,
) -> dict:
    p = Path(order_parquet) if order_parquet else ORDER_DATA_PARQUET
    now_ts = pd.Timestamp(now) if now is not None else pd.Timestamp.now()
    if max_minutes is None:
        max_minutes = max_refresh_age_minutes(bdef)
    mtime = pd.Timestamp.fromtimestamp(p.stat().st_mtime) if p.exists() else None
    latest = latest_data_ts(p)

    if refresh_ts is not None:
        ref = pd.Timestamp(refresh_ts)
        source = "scheduler"
    else:
        ref = mtime
        source = "mtime"

    if ref is None:
        return {
            "refresh_ts": None,
            "refresh_source": source,
            "mtime": mtime,
            "latest_ts": latest,
            "refresh_age_minutes": None,
            "max_refresh_age_minutes": max_minutes,
            "fresh": False,
            "reason": "无法获取数据刷新时间",
        }

    age_minutes = (now_ts - ref).total_seconds() / 60.0
    fresh = age_minutes <= max_minutes
    reason = (
        "ok"
        if fresh
        else f"数据刷新于 {ref:%Y-%m-%d %H:%M}，距今 {age_minutes:.0f}min > {max_minutes:g}min"
    )
    return {
        "refresh_ts": ref,
        "refresh_source": source,
        "mtime": mtime,
        "latest_ts": latest,
        "refresh_age_minutes": age_minutes,
        "max_refresh_age_minutes": max_minutes,
        "fresh": fresh,
        "reason": reason,
    }
