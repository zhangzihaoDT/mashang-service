"""预售/上市阶段判定 — 全部口径来自 shared/schema/business_definition.json。

phase 规则：
  presale : start <= today < presale_close
            presale_close = end（已确认上市日）or (start + presale_open_ended_window_days)
            —— 只有 start、上市日（end）未定时，预售监控仍持续输出固定天数，
               默认 start 起 3 个自然日（start、start+1、start+2）；确认上市日后
               自动按 end 收口，无需删配置。
  launch  : end <= today <= launch_end
            launch_end = monitor_until_by_series[gen] or finish or (end + launch_window_days)
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
# 上市日（end）未确认时的预售监控兜底窗口：start 起连续 N 个自然日持续输出
DEFAULT_PRESALE_OPEN_ENDED_WINDOW_DAYS = 3
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
    """预售开放时刻（按代际，默认 default_open_hour）。"""
    mon = bdef.get("monitor") or {}
    by = mon.get("open_hour_by_series") or {}
    return int(by.get(generation, mon.get("default_open_hour", DEFAULT_OPEN_HOUR)))


def open_minute(bdef: dict, generation: str) -> int:
    """预售开放分钟（按代际，默认 0）。用于非整点开放，如 CM2=20:55。"""
    mon = bdef.get("monitor") or {}
    by = mon.get("open_minute_by_series") or {}
    return int(by.get(generation, 0))


def presale_cohort_start_parts(bdef: dict, generation: str) -> tuple[int, int]:
    """返回预售 cohort 起点时分，不改变官方预售开放时刻。"""
    mode = ((bdef.get("monitor") or {}).get("presale_cohort_start_by_series") or {}).get(generation)
    if mode == "start_of_day":
        return 0, 0
    return open_hour(bdef, generation), open_minute(bdef, generation)


def launch_open_hour(bdef: dict, generation: str) -> int:
    """上市开放时刻（历史对标用，默认 default_open_hour=20）。"""
    mon = bdef.get("monitor") or {}
    by = mon.get("launch_open_hour_by_series") or {}
    return int(by.get(generation, mon.get("default_open_hour", DEFAULT_OPEN_HOUR)))


def launch_open_minute(bdef: dict, generation: str) -> int:
    """上市开放分钟（历史对标用，默认 0）。"""
    mon = bdef.get("monitor") or {}
    by = mon.get("launch_open_minute_by_series") or {}
    return int(by.get(generation, 0))


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


def monitor_until(bdef: dict, generation: str) -> date | None:
    """按代际显式监控截止日（monitor.monitor_until_by_series）；未配置返回 None。"""
    mon = bdef.get("monitor") or {}
    by = mon.get("monitor_until_by_series") or {}
    return _as_date(by.get(generation))


def presale_open_ended_window_days(bdef: dict) -> int:
    """上市日（end）未确认时的预售监控窗口天数（默认 3）。"""
    mon = bdef.get("monitor") or {}
    return int(mon.get("presale_open_ended_window_days", DEFAULT_PRESALE_OPEN_ENDED_WINDOW_DAYS))


def presale_close_date(bdef: dict, generation: str) -> date | None:
    """预售阶段收口日（不含）。

    - 已确认上市日（end）：收口日 = end；
    - 仅有 start、end 未定：收口日 = start + presale_open_ended_window_days（默认 3 天）。
    返回 None 表示无法确定预售窗口（无 start 且无 end）。
    """
    tp = (bdef.get("time_periods") or {}).get(generation) or {}
    end = _as_date(tp.get("end"))
    if end is not None:
        return end
    start = _as_date(tp.get("start"))
    if start is None:
        return None
    return start + timedelta(days=presale_open_ended_window_days(bdef))


def phase_of(bdef: dict, generation: str, today) -> str | None:
    tp = (bdef.get("time_periods") or {}).get(generation) or {}
    today_d = _as_date(today)
    if today_d is None:
        return None
    start = _as_date(tp.get("start"))
    end = _as_date(tp.get("end"))
    finish = _as_date(tp.get("finish"))
    presale_close = presale_close_date(bdef, generation)
    if start and presale_close and start <= today_d < presale_close:
        return "presale"
    if end:
        launch_end = monitor_until(bdef, generation) or finish or (end + timedelta(days=launch_window_days(bdef)))
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
        presale_close = presale_close_date(bdef, generation)
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
                # 预售阶段为收口日（不含）；上市阶段为上市日（= end）
                "presale_close": presale_close.isoformat() if presale_close else None,
                # 上市日未确认时，预售窗口由 start + 兜底天数给出，供推送标注
                "open_ended": bool(tp.get("start") and not tp.get("end")),
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
