"""预售/上市阶段判定 — 全部口径来自 shared/schema/business_definition.json。

phase 规则：
  presale : start <= today < end
  launch  : end <= today <= (finish or end + launch_window_days)
  normal  : 其他（不监控）

`detect_active` 支持多代际同时 active（例如 DM2 上市窗口 + CM3 预售窗口）。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from utils.paths import BUSINESS_DEFINITION_PATH

DEFAULT_OPEN_HOUR = 20
DEFAULT_LAUNCH_WINDOW_DAYS = 14
MONITOR_PHASES = ("presale", "launch")


def load_business_definition(path: Path | str | None = None) -> dict:
    p = Path(path) if path else BUSINESS_DEFINITION_PATH
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _as_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def model_series_of(bdef: dict, generation: str) -> str | None:
    for series, gens in (bdef.get("model_series_mapping") or {}).items():
        if generation in gens:
            return series
    return None


def open_hour(bdef: dict, generation: str) -> int:
    mon = bdef.get("monitor") or {}
    by = mon.get("open_hour_by_series") or {}
    return int(by.get(generation, mon.get("default_open_hour", DEFAULT_OPEN_HOUR)))


def series_label(bdef: dict, generation: str) -> str:
    mon = bdef.get("monitor") or {}
    return (mon.get("series_labels") or {}).get(generation, generation)


def compare_keys(bdef: dict, generation: str) -> list[str]:
    mon = bdef.get("monitor") or {}
    series = model_series_of(bdef, generation)
    by = mon.get("compare_by_series") or {}
    if series and series in by:
        return [g for g in by[series] if g != generation]
    periods = bdef.get("time_periods") or {}
    return [g for g, tp in periods.items() if g != generation and (tp or {}).get("start")]


def launch_window_days(bdef: dict) -> int:
    mon = bdef.get("monitor") or {}
    return int(mon.get("launch_window_days", DEFAULT_LAUNCH_WINDOW_DAYS))


def phase_of(bdef: dict, generation: str, today) -> str | None:
    tp = (bdef.get("time_periods") or {}).get(generation) or {}
    today_d = _as_date(today)
    if today_d is None:
        return None
    start = _as_date(tp.get("start"))
    end = _as_date(tp.get("end"))
    finish = _as_date(tp.get("finish"))
    if start and end and start <= today_d < end:
        return "presale"
    if end:
        launch_end = finish or (end + timedelta(days=launch_window_days(bdef)))
        if end <= today_d <= launch_end:
            return "launch"
    return None


def detect_active(bdef: dict, today, phases=MONITOR_PHASES) -> list[dict]:
    today_d = _as_date(today)
    out: list[dict] = []
    for generation, tp in (bdef.get("time_periods") or {}).items():
        phase = phase_of(bdef, generation, today_d)
        if phase is None or phase not in phases:
            continue
        tp = tp or {}
        out.append(
            {
                "generation": generation,
                "model_series": model_series_of(bdef, generation),
                "phase": phase,
                "label": series_label(bdef, generation),
                "open_hour": open_hour(bdef, generation),
                "start": tp.get("start"),
                "end": tp.get("end"),
                "finish": tp.get("finish"),
            }
        )
    out.sort(key=lambda x: (x.get("start") or ""), reverse=True)
    return out


def key_days(bdef: dict, today) -> list[dict]:
    today_d = _as_date(today)
    hits: list[dict] = []
    for generation, tp in (bdef.get("time_periods") or {}).items():
        tp = tp or {}
        if _as_date(tp.get("start")) == today_d:
            hits.append({"generation": generation, "kind": "presale_start"})
        if _as_date(tp.get("end")) == today_d:
            hits.append({"generation": generation, "kind": "launch"})
    return hits


def is_key_day(bdef: dict, today) -> bool:
    return bool(key_days(bdef, today))
