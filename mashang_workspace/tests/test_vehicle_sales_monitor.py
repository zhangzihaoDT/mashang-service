"""vehicle_sales_monitor / monitors / scheduler 回归测试。

覆盖：
  - phase 判定（presale / launch / normal）与多 active 代际
  - open_hour 按代际（CM3=19）
  - freshness 按小时 gate
  - presale compute 使用代际 open_hour
  - scheduler due_actions 的 key day 门控
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

_WS_DIR = Path(__file__).resolve().parents[1]
_PRJ_DIR = _WS_DIR.parent
for _p in (str(_PRJ_DIR), str(_WS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.monitors import freshness  # noqa: E402
from utils.monitors.phase import (  # noqa: E402
    detect_active,
    is_key_day,
    load_business_definition,
    open_hour,
    phase_of,
)
from utils.monitors.presale import compute as presale_compute  # noqa: E402

_BUSINESS_DEF = _PRJ_DIR / "shared" / "schema" / "business_definition.json"


@pytest.fixture(scope="module")
def bdef() -> dict:
    return json.loads(_BUSINESS_DEF.read_text(encoding="utf-8"))


def _load_scheduler():
    spec = importlib.util.spec_from_file_location(
        "schedule_launch_lock_evening_updates", _PRJ_DIR / "schedule_launch_lock_evening_updates.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("无法加载 scheduler")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── phase ──────────────────────────────────────────────────────────


def test_cm3_presale_phase(bdef):
    assert phase_of(bdef, "CM3", pd.Timestamp("2026-09-10")) == "presale"
    assert phase_of(bdef, "CM3", pd.Timestamp("2026-09-23")) == "presale"
    assert phase_of(bdef, "CM3", pd.Timestamp("2026-09-24")) == "launch"  # end = 上市日
    assert phase_of(bdef, "CM3", pd.Timestamp("2026-09-25")) == "launch"
    assert phase_of(bdef, "CM3", pd.Timestamp("2026-11-01")) is None


def test_dm2_launch_phase(bdef):
    assert phase_of(bdef, "DM2", pd.Timestamp("2026-09-10")) == "launch"


def test_multi_active_on_20260910(bdef):
    active = detect_active(bdef, pd.Timestamp("2026-09-10"))
    by_gen = {a["generation"]: a["phase"] for a in active}
    assert by_gen.get("CM3") == "presale"
    assert by_gen.get("DM2") == "launch"


def test_cm3_open_hour_is_19(bdef):
    assert open_hour(bdef, "CM3") == 19
    assert open_hour(bdef, "DM2") == 20


def test_key_day(bdef):
    assert is_key_day(bdef, pd.Timestamp("2026-09-10"))  # CM3 预售首日
    assert is_key_day(bdef, pd.Timestamp("2026-09-24"))  # CM3 上市日
    assert not is_key_day(bdef, pd.Timestamp("2026-09-15"))


# ── presale compute ────────────────────────────────────────────────


def _presale_df(rows) -> pd.DataFrame:
    df = pd.DataFrame(
        rows,
        columns=["order_number", "intention_payment_time", "intention_refund_time",
                 "series_group_logic", "product_name"],
    )
    df["intention_payment_time"] = pd.to_datetime(df["intention_payment_time"])
    df["intention_refund_time"] = pd.to_datetime(df["intention_refund_time"])
    df["parent_region_name"] = None
    df["buyer_identity_no"] = "u1"
    df["store_name"] = "s1"
    return df


def test_presale_compute_uses_generation_open_hour(bdef):
    today = pd.Timestamp("2026-09-10")
    df = _presale_df(
        [
            ("o1", "2026-09-10 18:59", None, "CM3", "LS6 M3 92 RWD"),      # 开放前 → 不计
            ("o2", "2026-09-10 19:01", None, "CM3", "LS6 M3 92 RWD"),      # 开放后 → 计
            ("o3", "2026-09-10 19:05", None, "CM3", "全新一代智己LS6 Max"),  # 开放后 → 计
        ]
    )
    m = presale_compute(df, bdef, today, "CM3")
    assert m["cum"] == 2
    assert m["retention"] == 2
    assert m["open_hour"] == 19


# ── freshness ──────────────────────────────────────────────────────


def test_freshness_flags_stale_and_fresh():
    latest = freshness.latest_data_ts()
    if latest is None:
        pytest.skip("dataset/order_data.parquet 不存在")
    fresh = freshness.check(now=latest + pd.Timedelta(minutes=30), max_hours=2)
    assert fresh["fresh"], fresh
    stale = freshness.check(now=latest + pd.Timedelta(hours=5), max_hours=2)
    assert not stale["fresh"]
    assert "最新数据" in stale["reason"]


# ── scheduler ──────────────────────────────────────────────────────


def test_scheduler_due_actions_key_day_gating(bdef):
    sched = _load_scheduler()
    # 每日 09:00 全量刷新 / 09:30 日报
    assert "refresh_full" in sched.due_actions(datetime(2026, 9, 15, 9, 0), bdef)
    assert sched.due_actions(datetime(2026, 9, 15, 9, 30), bdef) == ["monitor"]
    # key day 19:00 / 19:30 日内刷新与监控
    assert sched.due_actions(datetime(2026, 9, 10, 19, 0), bdef) == ["refresh_order_data"]
    assert sched.due_actions(datetime(2026, 9, 10, 19, 30), bdef) == ["monitor"]
    # 非 key day 晚间不触发
    assert sched.due_actions(datetime(2026, 9, 15, 19, 0), bdef) == []
    assert sched.due_actions(datetime(2026, 9, 15, 19, 30), bdef) == []
