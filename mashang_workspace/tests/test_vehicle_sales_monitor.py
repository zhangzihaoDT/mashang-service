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
    launch_open_hour,
    load_business_definition,
    open_hour,
    phase_of,
)
from utils.monitors.presale import compute as presale_compute  # noqa: E402
from utils.monitors.order_filter import is_fake_identity, flag_test_orders  # noqa: E402

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


def test_open_hour_calibration(bdef):
    # 预售开放时刻按代际校准（数据驱动）
    assert open_hour(bdef, "CM3") == 19
    assert open_hour(bdef, "CM0") == 10
    assert open_hour(bdef, "CM1") == 11
    assert open_hour(bdef, "CM2") == 20
    assert open_hour(bdef, "DM2") == 20
    # 上市开放时刻历史对标默认 20:00
    assert launch_open_hour(bdef, "CM1") == 20
    assert launch_open_hour(bdef, "CM0") == 20


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
    df["intention_payment_time"] = pd.to_datetime(df["intention_payment_time"], format="mixed")
    df["intention_refund_time"] = pd.to_datetime(df["intention_refund_time"], format="mixed")
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


# ── 测试单过滤 ─────────────────────────────────────────────────────


def test_is_fake_identity():
    assert is_fake_identity("310101199001011234") is False
    assert is_fake_identity("31010119900101567X") is False
    assert is_fake_identity("123456") is True
    assert is_fake_identity("1111") is True
    assert is_fake_identity(None) is False
    assert is_fake_identity("") is False


def test_flag_test_orders_requires_hq_and_fake(bdef):
    df = pd.DataFrame(
        {
            "store_name": ["总部主理店", "总部主理店", "门店A", "门店A"],
            "buyer_identity_no": ["123456", "310101199001011234", "123456", "310101199001011234"],
        }
    )
    assert flag_test_orders(df, bdef).tolist() == [True, False, False, False]


def test_presale_compute_excludes_test_orders(bdef):
    today = pd.Timestamp("2026-09-10")
    df = _presale_df(
        [
            ("o1", "2026-09-10 19:05", None, "CM3", "LS6 M3 92 RWD"),
            ("o2", "2026-09-10 19:06", None, "CM3", "全新一代智己LS6"),
        ]
    )
    df.loc[df["order_number"] == "o2", "store_name"] = "总部主理店"
    df.loc[df["order_number"] == "o2", "buyer_identity_no"] = "123456"
    m = presale_compute(df, bdef, today, "CM3")
    assert m["cum"] == 1
    assert m["test_orders_excluded"] == 1


def test_presale_obs_capped_at_data_latest(bdef):
    """obs = min(当日 23:59:59, 数据最新 intention_payment_time)"""
    today = pd.Timestamp("2026-09-11")
    df = _presale_df(
        [
            ("o1", "2026-09-10 20:00", None, "CM3", "LS6 M3 92 RWD"),
            ("o2", "2026-09-10 23:50", None, "CM3", "LS6 M3 92 RWD"),  # 数据最新
        ]
    )
    m = presale_compute(df, bdef, today, "CM3")
    assert m["obs"] == "2026-09-10T23:50:00"  # 数据最新 < 23:59:59
    assert m["cum"] == 2
    assert m["elapsed_hours"] == round(
        (pd.Timestamp("2026-09-10 23:50:00") - pd.Timestamp("2026-09-10 19:00")).total_seconds() / 3600, 1
    )


def test_presale_obs_defaults_to_end_of_day(bdef):
    """若数据最新 ≥ 23:59:59，obs = 当日 23:59:59"""
    today = pd.Timestamp("2026-09-11")
    df = _presale_df(
        [
            ("o1", "2026-09-10 20:00", None, "CM3", "LS6 M3 92 RWD"),
            ("o2", "2026-09-10T23:59:59", None, "CM3", "LS6 M3 92 RWD"),  # ISO 格式含秒
        ]
    )
    m = presale_compute(df, bdef, today, "CM3")
    assert m["obs"] == "2026-09-10T23:59:59"
    assert m["cum"] == 2


def test_presale_compare_window_matches_elapsed(bdef):
    """对标窗口长度应与目标 elapsed 完全对齐（同 elapsed 小时）"""
    today = pd.Timestamp("2026-09-10")
    rows = [
        # 目标 CM3: 2 笔
        ("t1", "2026-09-10 20:00", None, "CM3", "LS6 M3 92 RWD"),
        ("t2", "2026-09-10 22:00", None, "CM3", "LS6 M3 92 RWD"),
        # CM2: 1 笔在 22:00 前（elapsed 内），1 笔在次日（elapsed 外）
        ("c1", "2025-08-15 21:00", None, "CM2", "LS6"),
        ("c2", "2025-08-16 21:00", None, "CM2", "LS6"),
    ]
    df = _presale_df(rows)
    m = presale_compute(df, bdef, today, "CM3")
    # obs = min(23:59:59, max intention=22:00) = 22:00
    assert m["obs"] == "2026-09-10T22:00:00"
    assert m["cum"] == 2
    # elapsed = 22:00 - 19:00 = 3h; compare 窗口 = [2025-08-15 20:00, +3h]
    assert m["compare"]["CM2"] == 1  # c1 在 3h 内，c2 不在


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


def _scheduler_args(**overrides):
    import argparse
    sched = _load_scheduler()
    base = dict(dry_run=False, as_of=None, series=None, phase="presale")
    base.update(overrides)
    return sched, argparse.Namespace(**base)


def test_scheduler_monitor_cmd_defaults_to_presale(bdef):
    """常驻/--once 默认只推 presale，避免混入 launch（如 DM2）。"""
    sched, args = _scheduler_args(dry_run=True)
    cmd = sched._monitor_cmd(args)
    assert "--phase" in cmd
    assert cmd[cmd.index("--phase") + 1] == "presale"
    assert "--series" not in cmd

    # 显式覆盖时透传
    sched, args = _scheduler_args(phase="launch,presale", series="DM2,CM3", dry_run=True)
    cmd = sched._monitor_cmd(args)
    assert cmd[cmd.index("--phase") + 1] == "launch,presale"
    assert cmd[cmd.index("--series") + 1] == "DM2,CM3"


def test_scheduler_due_actions_key_day_gating(bdef):
    sched = _load_scheduler()
    # 每日 09:00 数据管道：全量刷新 + 校验 + 每日观察同步；09:30 日报
    acts = sched.due_actions(datetime(2026, 9, 15, 9, 0), bdef)
    assert "refresh_full" in acts
    assert "dataset_validate" in acts
    assert "daily_observation_sync" in acts
    assert sched.due_actions(datetime(2026, 9, 15, 9, 30), bdef) == ["monitor"]
    # key day 19:00 刷新+监控串行（:30 不再单独触发 monitor）
    assert sched.due_actions(datetime(2026, 9, 10, 19, 0), bdef) == ["refresh_order_data", "monitor"]
    assert sched.due_actions(datetime(2026, 9, 10, 19, 30), bdef) == []
    # 非 key day 晚间不触发
    assert sched.due_actions(datetime(2026, 9, 15, 19, 0), bdef) == []
    assert sched.due_actions(datetime(2026, 9, 15, 19, 30), bdef) == []


def test_scheduler_daily_pipeline_serial_order(bdef):
    """09:00 数据管道顺序 = 刷新 → 校验 → 同步（对应 make daily-data-pipeline 依赖序）。"""
    sched = _load_scheduler()
    assert sched.due_actions(datetime(2026, 9, 15, 9, 0), bdef) == [
        "refresh_full", "dataset_validate", "daily_observation_sync",
    ]


def test_scheduler_pipeline_runs_all_in_order(monkeypatch, bdef):
    """validate 成功后同步正常执行。"""
    sched = _load_scheduler()
    now = datetime(2026, 9, 15, 9, 0)
    calls: list[str] = []

    def fake_run(cmd, label, dry_run, t):
        calls.append(label)
        return 0

    monkeypatch.setattr(sched, "_run", fake_run)
    sched.process_batch(now, bdef, _scheduler_args()[1], set())
    assert calls == ["refresh_full", "dataset_validate", "daily_observation_sync"]


def test_scheduler_validate_failure_blocks_daily_observation_sync(monkeypatch, bdef):
    """dataset_validate 失败时跳过 daily_observation_sync，不写外部系统。"""
    sched = _load_scheduler()
    now = datetime(2026, 9, 15, 9, 0)
    calls: list[str] = []

    def fake_run(cmd, label, dry_run, t):
        calls.append(label)
        return 1 if label == "dataset_validate" else 0

    monkeypatch.setattr(sched, "_run", fake_run)
    sched.process_batch(now, bdef, _scheduler_args()[1], set())
    assert calls == ["refresh_full", "dataset_validate"]
