"""vehicle_sales_monitor / monitors / scheduler 回归测试。

覆盖：
  - phase 判定（presale / launch / normal）与多 active 代际
  - open_hour 按代际（CM3=19:45）
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
    launch_open_minute,
    load_business_definition,
    open_hour,
    open_minute,
    phase_of,
)
from utils.monitors.launch import build_card as launch_build_card  # noqa: E402
from utils.monitors.launch import compute as launch_compute  # noqa: E402
from utils.monitors.presale import build_card as presale_build_card  # noqa: E402
from utils.monitors.presale import build_waiting_card as presale_build_waiting_card  # noqa: E402
from utils.monitors.presale import compute as presale_compute  # noqa: E402
from utils.monitors.order_filter import is_fake_identity, flag_test_orders  # noqa: E402

_BUSINESS_DEF = _PRJ_DIR / "shared" / "schema" / "business_definition.json"


@pytest.fixture(scope="module")
def bdef() -> dict:
    return json.loads(_BUSINESS_DEF.read_text(encoding="utf-8"))


def _load_scheduler():
    spec = importlib.util.spec_from_file_location(
        "sales_scheduler", _WS_DIR / "utility_scripts" / "sales_scheduler.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("无法加载 scheduler")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── phase ──────────────────────────────────────────────────────────


def test_cm3_presale_phase(bdef):
    assert phase_of(bdef, "CM3", pd.Timestamp("2026-09-10")) == "presale"
    assert phase_of(bdef, "CM3", pd.Timestamp("2026-09-22")) == "presale"
    assert phase_of(bdef, "CM3", pd.Timestamp("2026-09-23")) == "launch"  # end = 上市日
    assert phase_of(bdef, "CM3", pd.Timestamp("2026-09-24")) == "launch"
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
    # 非整点开放：CM2=20:55、CM3=19:45
    assert open_minute(bdef, "CM2") == 55
    assert open_minute(bdef, "CM3") == 45
    # 上市开放时刻历史对标默认 20:00（小时），分钟按代际实测校准
    assert launch_open_hour(bdef, "CM1") == 20
    assert launch_open_hour(bdef, "CM0") == 20
    assert launch_open_minute(bdef, "CM2") == 51
    assert launch_open_minute(bdef, "CM1") == 42
    assert launch_open_minute(bdef, "CM0") == 32
    assert launch_open_minute(bdef, "LS8") == 23
    assert launch_open_minute(bdef, "LS9") == 12
    # 未配置代际回退默认 0
    assert launch_open_minute(bdef, "LS9Hyper") == 0


def test_key_day(bdef):
    assert is_key_day(bdef, pd.Timestamp("2026-09-10"))  # CM3 预售首日
    assert is_key_day(bdef, pd.Timestamp("2026-09-23"))  # CM3 上市日
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
            ("o1", "2026-09-10 19:44", None, "CM3", "LS6 M3 92 RWD"),      # 开放前 → 不计
            ("o2", "2026-09-10 19:46", None, "CM3", "LS6 M3 92 RWD"),      # 开放后 → 计
            ("o3", "2026-09-10 19:50", None, "CM3", "全新一代智己LS6 Max"),  # 开放后 → 计
        ]
    )
    m = presale_compute(df, bdef, today, "CM3")
    assert m["cum"] == 2
    assert m["today_count"] == 2
    assert m["retention"] == 2
    assert m["open_hour"] == 19
    assert m["open_minute"] == 45


def test_presale_today_count_only_counts_current_day(bdef):
    """当日小订只统计观察当日新增，不含开放日/历史日。"""
    today = pd.Timestamp("2026-09-11")
    df = _presale_df(
        [
            ("o1", "2026-09-10 20:00", None, "CM3", "全新一代智己LS6"),  # 开放日
            ("o2", "2026-09-11 10:00", None, "CM3", "全新一代智己LS6"),  # 当日
            ("o3", "2026-09-11 12:00", None, "CM3", "全新一代智己LS6"),  # 当日
        ]
    )
    m = presale_compute(df, bdef, today, "CM3")
    assert m["cum"] == 3
    assert m["today_count"] == 2


def test_presale_compute_uses_generation_open_minute(bdef):
    """CM2 非整点开放 20:55：20:54 的单不计，20:56 起计入。"""
    today = pd.Timestamp("2025-08-15")
    df = _presale_df(
        [
            ("o1", "2025-08-15 20:54", None, "CM2", "新一代智己LS6 Max"),  # 开放前 → 不计
            ("o2", "2025-08-15 20:56", None, "CM2", "新一代智己LS6 Max"),  # 开放后 → 计
            ("o3", "2025-08-15 21:05", None, "CM2", "新一代智己LS6 Max"),  # 开放后 → 计
        ]
    )
    m = presale_compute(df, bdef, today, "CM2")
    assert m["cum"] == 2
    assert m["retention"] == 2
    assert m["open_hour"] == 20
    assert m["open_minute"] == 55


def test_presale_compute_flags_data_before_open(bdef):
    """数据未更新到开放时刻 → data_before_open=True（不渲染 0 指标）。"""
    today = pd.Timestamp("2026-09-10")  # CM3 open 19:45
    before = _presale_df([("o1", "2026-09-10 19:30", None, "CM3", "全新一代智己LS6 Max")])
    after = _presale_df([("o1", "2026-09-10 20:30", None, "CM3", "全新一代智己LS6 Max")])
    assert presale_compute(before, bdef, today, "CM3")["data_before_open"] is True
    assert presale_compute(after, bdef, today, "CM3")["data_before_open"] is False


def test_presale_waiting_card_content():
    """等待卡：不渲染 0 指标，提示开放时刻与数据最新时间。"""
    m = _presale_metrics()
    m["open_hour"], m["open_minute"] = 19, 0
    m["obs"] = "2026-09-10 18:30:41"
    m["data_before_open"] = True
    body = presale_build_waiting_card(m)["card"]["elements"][0]["text"]["content"]
    assert "暂不推送指标" in body
    assert "开放时刻：19:00" in body
    assert "数据最新：2026-09-10 18:30" in body
    assert "预售小订" not in body


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
            ("o1", "2026-09-10 20:05", None, "CM3", "LS6 M3 92 RWD"),
            ("o2", "2026-09-10 20:06", None, "CM3", "全新一代智己LS6"),
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
        (pd.Timestamp("2026-09-10 23:50:00") - pd.Timestamp("2026-09-10 19:45")).total_seconds() / 3600, 1
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
    # elapsed = 22:00 - 19:45 = 2.25h; compare 窗口 = [2025-08-15 20:55, +2.25h]
    assert m["compare"]["CM2"] == 1  # c1 在窗口内，c2 不在


def test_presale_compare_window_uses_exact_elapsed(bdef):
    """elapsed < 3min 时 round(...,1)=0.0；对标窗口必须按精确时长算，否则会塌成 0。"""
    today = pd.Timestamp("2026-09-10")
    df = _presale_df(
        [
            ("t1", "2026-09-10 19:45:30", None, "CM3", "全新一代智己LS6"),  # obs=19:45:30 → elapsed=30s
            ("c1", "2025-08-15 20:55:10", None, "CM2", "新一代智己LS6"),  # 落在 [20:55:00, +30s]
            ("c2", "2025-08-15 20:56:30", None, "CM2", "新一代智己LS6"),  # 窗口外
        ]
    )
    m = presale_compute(df, bdef, today, "CM3")
    assert m["elapsed_hours"] == 0.0  # 展示值仍四舍五入到 0.0
    assert m["compare"]["CM2"] == 1  # 但 c1 应计入


def test_presale_prelaunch_compare_aligns_days_before_launch(bdef):
    """历史上市前累计留存：按「距上市天数」对齐，各代际取上市日前相同天数 [open, hist_end-days_before+1d)。"""
    rows = [
        ("t1", "2026-09-22 10:00", None, "CM3", "全新一代智己LS6"),  # 目标，obs 当天
        ("c1", "2025-08-15 21:00", None, "CM2", "新一代智己LS6"),                       # 预售期内、未退 → 计
        ("c2", "2025-09-01 21:00", None, "CM2", "新一代智己LS6"),                       # 预售期内、未退 → 计
        ("c3", "2025-09-20 21:00", None, "CM2", "新一代智己LS6"),                       # 上市后 → 不计
        ("c4", "2025-08-16 21:00", "2025-09-11 10:00", "CM2", "新一代智己LS6"),         # 退订晚于截止 → 计
        ("c5", "2025-08-16 22:00", "2025-08-20 10:00", "CM2", "新一代智己LS6"),         # 截止前已退 → 不计
        ("c6", "2025-09-10 19:00", None, "CM2", "新一代智己LS6"),                       # 上市日 → 不计（截止为 end-1 末）
        ("c7", "2025-09-10 21:00", None, "CM2", "新一代智己LS6"),                       # 上市日 → 不计
        ("c8", "2025-09-05 21:00", None, "CM2", "新一代智己LS6"),                       # 截止日附近
    ]
    df = _presale_df(rows)

    # 上市前 1 天（今日=上市前一日）：CM2 截止 = 2025-09-10 → 计 c1/c2/c4/c8 = 4
    m1 = presale_compute(df, bdef, pd.Timestamp("2026-09-22"), "CM3")
    assert m1["days_before_launch"] == 1
    assert m1["prelaunch_compare"]["CM2"] == 4

    # 上市前 8 天：CM2 截止 = 2025-09-03 → c8(09-05) 落在窗口外，计 c1/c2/c4 = 3
    m8 = presale_compute(df, bdef, pd.Timestamp("2026-09-15"), "CM3")
    assert m8["days_before_launch"] == 8
    assert m8["prelaunch_compare"]["CM2"] == 3


# ── freshness ──────────────────────────────────────────────────────


def test_freshness_uses_scheduler_refresh_ts(bdef):
    """调度器传入 refresh_ts 时以其为准：2 分钟内 fresh，超时 stale。"""
    now = pd.Timestamp("2026-09-10 19:17:00")
    fresh = freshness.check(now=now, refresh_ts=now - pd.Timedelta(minutes=1), bdef=bdef)
    assert fresh["fresh"], fresh
    assert fresh["refresh_source"] == "scheduler"

    stale = freshness.check(now=now, refresh_ts=now - pd.Timedelta(minutes=10), bdef=bdef)
    assert not stale["fresh"]
    assert "数据刷新于" in stale["reason"]
    assert "> 2min" in stale["reason"]


def test_freshness_falls_back_to_mtime(bdef):
    """未传 refresh_ts 时回退 parquet mtime 判定。"""
    mtime = pd.Timestamp.fromtimestamp(freshness.ORDER_DATA_PARQUET.stat().st_mtime)
    fresh = freshness.check(now=mtime + pd.Timedelta(minutes=1), bdef=bdef)
    assert fresh["fresh"], fresh
    assert fresh["refresh_source"] == "mtime"

    stale = freshness.check(now=mtime + pd.Timedelta(hours=1), bdef=bdef)
    assert not stale["fresh"]


# ── scheduler ──────────────────────────────────────────────────────


def _scheduler_args(**overrides):
    import argparse
    sched = _load_scheduler()
    base = dict(dry_run=False, as_of=None, series=None, phase="presale,launch")
    base.update(overrides)
    return sched, argparse.Namespace(**base)


def test_scheduler_monitor_cmd_default_phase_launch_presale(bdef):
    """常驻/--once 默认推送全部 active 阶段（presale,launch），支持显式收窄。"""
    sched, args = _scheduler_args(dry_run=True)
    cmd = sched._monitor_cmd(args)
    assert "--phase" in cmd
    assert cmd[cmd.index("--phase") + 1] == "presale,launch"
    assert "--series" not in cmd

    # 显式收窄到仅预售
    sched, args = _scheduler_args(phase="presale", dry_run=True)
    cmd = sched._monitor_cmd(args)
    assert cmd[cmd.index("--phase") + 1] == "presale"

    # 显式覆盖时透传
    sched, args = _scheduler_args(phase="launch,presale", series="DM2,CM3", dry_run=True)
    cmd = sched._monitor_cmd(args)
    assert cmd[cmd.index("--phase") + 1] == "launch,presale"
    assert cmd[cmd.index("--series") + 1] == "DM2,CM3"


def test_scheduler_monitor_cmd_includes_refresh_ts(bdef):
    """有 refresh_ts 时注入 --refresh-ts；缺省不注入。"""
    sched, args = _scheduler_args(dry_run=True)
    assert "--refresh-ts" not in sched._monitor_cmd(args)
    ts = datetime(2026, 9, 10, 19, 0, 1)
    cmd = sched._monitor_cmd(args, refresh_ts=ts)
    assert cmd[cmd.index("--refresh-ts") + 1] == ts.isoformat()


def test_scheduler_pipeline_passes_refresh_ts_to_monitor(bdef):
    """刷新成功后，管道把本轮刷新完成时刻透传给 monitor。"""
    sched = _load_scheduler()
    cmds: dict[str, list[str]] = {}

    def fake_run(cmd, label, dry_run, t):
        cmds[label] = cmd
        return 0

    mp = pytest.MonkeyPatch()
    mp.setattr(sched, "_run", fake_run)
    try:
        sched.process_batch(datetime(2026, 9, 15, 9, 0), bdef, _scheduler_args()[1], set())
    finally:
        mp.undo()
    assert "--refresh-ts" in cmds["monitor"]


def test_scheduler_refresh_failure_no_refresh_ts_and_skips_monitor(bdef):
    """刷新失败 → monitor 被跳过，不会带 refresh_ts 执行。"""
    sched = _load_scheduler()
    cmds: dict[str, list[str]] = {}

    def fake_run(cmd, label, dry_run, t):
        cmds[label] = cmd
        return 1 if label == "refresh_full" else 0

    mp = pytest.MonkeyPatch()
    mp.setattr(sched, "_run", fake_run)
    try:
        sched.process_batch(datetime(2026, 9, 15, 9, 0), bdef, _scheduler_args()[1], set())
    finally:
        mp.undo()
    assert "monitor" not in cmds


def test_scheduler_due_actions_key_day_gating(bdef):
    sched = _load_scheduler()
    # 每日 09:00 数据管道末步含 monitor（09:30 不再独立触发）
    assert sched.due_actions(datetime(2026, 9, 15, 9, 0), bdef) == [
        "refresh_full", "dataset_validate", "daily_observation_sync", "monitor",
    ]
    assert sched.due_actions(datetime(2026, 9, 15, 9, 30), bdef) == []
    # key day 19:00 刷新+监控串行（:30 不再单独触发 monitor）
    assert sched.due_actions(datetime(2026, 9, 10, 19, 0), bdef) == ["refresh_order_data", "monitor"]
    assert sched.due_actions(datetime(2026, 9, 10, 19, 30), bdef) == []
    # 非 key day 晚间不触发
    assert sched.due_actions(datetime(2026, 9, 15, 19, 0), bdef) == []
    assert sched.due_actions(datetime(2026, 9, 15, 19, 30), bdef) == []


def test_scheduler_daily_pipeline_serial_order(bdef):
    """09:00 数据管道顺序 = 刷新 → 校验 → 同步 → 监控。"""
    sched = _load_scheduler()
    assert sched.due_actions(datetime(2026, 9, 15, 9, 0), bdef) == [
        "refresh_full", "dataset_validate", "daily_observation_sync", "monitor",
    ]


def _run_chain(sched, now, bdef, result_map):
    calls: list[str] = []

    def fake_run(cmd, label, dry_run, t):
        calls.append(label)
        return result_map.get(label, 0)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(sched, "_run", fake_run)
    try:
        sched.process_batch(now, bdef, _scheduler_args()[1], set())
    finally:
        monkeypatch.undo()
    return calls


def test_scheduler_pipeline_runs_all_in_order(bdef):
    """全链路成功后 monitor 作为末步执行。"""
    sched = _load_scheduler()
    now = datetime(2026, 9, 15, 9, 0)
    assert _run_chain(sched, now, bdef, {}) == [
        "refresh_full", "dataset_validate", "daily_observation_sync", "monitor",
    ]


def test_scheduler_refresh_failure_halts_pipeline(bdef):
    """refresh_full 失败即中止整批（validate/sync/monitor 都不执行）。"""
    sched = _load_scheduler()
    now = datetime(2026, 9, 15, 9, 0)
    assert _run_chain(sched, now, bdef, {"refresh_full": 1}) == ["refresh_full"]


def test_scheduler_validate_failure_blocks_sync_and_monitor(bdef):
    """dataset_validate 失败 → 跳过 daily_observation_sync 与 monitor。"""
    sched = _load_scheduler()
    now = datetime(2026, 9, 15, 9, 0)
    assert _run_chain(sched, now, bdef, {"dataset_validate": 1}) == [
        "refresh_full", "dataset_validate",
    ]


def test_scheduler_sync_failure_blocks_monitor(bdef):
    """daily_observation_sync 失败 → 跳过末步 monitor。"""
    sched = _load_scheduler()
    now = datetime(2026, 9, 15, 9, 0)
    assert _run_chain(sched, now, bdef, {"daily_observation_sync": 1}) == [
        "refresh_full", "dataset_validate", "daily_observation_sync",
    ]


def test_scheduler_keyday_refresh_failure_blocks_monitor(bdef):
    """key day 高频 refresh_order_data 失败 → 跳过 monitor。"""
    sched = _load_scheduler()
    now = datetime(2026, 9, 10, 19, 0)
    assert _run_chain(sched, now, bdef, {"refresh_order_data": 1}) == ["refresh_order_data"]


def test_scheduler_run_once_refresh_failure_skips_monitor(bdef):
    """--once：刷新失败 → 返回失败码且不执行 monitor（freshness gate，不用陈旧数据）。"""
    sched = _load_scheduler()
    calls: list[str] = []

    def fake_run(cmd, label, dry_run, t):
        calls.append(label)
        return 1 if label == "refresh_order_data" else 0

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(sched, "_run", fake_run)
    try:
        rc = sched.run_once(_scheduler_args()[1], bdef)
    finally:
        monkeypatch.undo()
    assert rc == 1
    assert calls == ["refresh_order_data"]


# ── presale card 结构（参照 launch 精简） ────────────────────────────


def _presale_metrics() -> dict:
    return {
        "generation": "CM3",
        "label": "全新一代 LS6",
        "open_hour": 19,
        "test_orders_excluded": 2,
        "today": "2026-09-10",
        "series_start": "2026-09-10",
        "series_end": "2026-09-23",
        "obs": "2026-09-10 15:30:01",
        "elapsed_hours": 20.5,
        "cum": 2480,
        "today_count": 123,
        "retention": 2415,
        "retention_users": 2380,
        "peak_hour": 18,
        "peak_count": 1200,
        "next_hour_count": 380,
        "start_day_total": 2050,
        "start_day_retained": 1980,
        "launch_day_total": 1700,
        "launch_day_retention": 1600,
        "retention_by_product": [
            {"product_name": "66 Ultra 限量版", "count": 120, "share": 5.0, "limited": True},
            {"product_name": "66 Ultra", "count": 1500, "share": 62.1, "limited": False},
            {"product_name": "48 Ultra", "count": 795, "share": 32.9, "limited": False},
        ],
        "retention_by_region": [
            {"region_name": "上海", "count": 1200, "share": 49.7, "cr5": 88.1},
            {"region_name": "北京", "count": 450, "share": 18.6, "cr5": None},
            {"region_name": "杭州", "count": 300, "share": 12.4, "cr5": None},
        ],
        "retention_no_region": 10,
        "compare": {"CM2": 2000, "CM1": 900, "CM0": 1500, "LS8": 1100, "LS9": 700},
        "prelaunch_compare": {"CM2": 37165, "CM1": 18696, "CM0": 18235, "LS8": 13814, "LS9": 7635},
        "days_before_launch": 1,
    }


def _presale_card_body(show_notes: bool) -> str:
    return presale_build_card(_presale_metrics(), show_notes=show_notes)["card"]["elements"][0]["text"]["content"]


def test_presale_card_slim_no_notes_in_production():
    """生产推送（show_notes=False）不带附注/口径/数据源，保留核心指标与固定信息行。"""
    body = _presale_card_body(show_notes=False)
    assert "①" not in body and "附注" not in body and "口径" not in body and "数据源" not in body
    assert "当日小订：**123**（当日新增）" in body
    assert "预售小订：**2,480**（预售至今累计）" in body
    assert "累计留存订单：**2,415**（唯一订单用户 2,380）" in body
    assert "峰值小时：**1,200**（18:00）｜峰值后 1h **380**" in body
    assert "开放后 24h 累计留存：**1,980**" in body
    assert "发布会当日留存：**1,600**（小订 1,700）" in body
    assert "历史对比（自开放起同期留存，相同时长）：**CM2（2,000） / CM1（900） / CM0（1,500） / LS8（1,100） / LS9（700）**" in body
    assert "历史上市前累计留存（上市前相同天数）：**CM2（37,165） / CM1（18,696） / CM0（18,235） / LS8（13,814） / LS9（7,635）**" in body
    assert "预售期：2026-09-10 ~ 2026-09-23" in body
    assert "观察时间：2026-09-10 15:30" in body


def test_presale_card_region_compressed_to_one_line():
    """分大区压成一行，同一行内多区域以｜分隔。"""
    body = _presale_card_body(show_notes=False)
    assert "分大区：" in body
    first_line = next(l for l in body.splitlines() if l.startswith("分大区："))
    assert first_line == "分大区：上海 49.7%｜北京 18.6%｜杭州 12.4%｜无大区 0.4%"


def test_presale_card_notes_only_in_dry_run():
    """注释块仅 show_notes=True（dry-run）展示。"""
    body = _presale_card_body(show_notes=True)
    assert "口径：" in body
    assert "数据源：" in body
    assert "已剔除测试单：2 笔" in body


def test_presale_card_no_limited_skips_split():
    """无「限量版」命中的代际（如 CM3）不渲染限量/非限量二分，直接列留存明细。"""
    m = _presale_metrics()
    m["retention_by_product"] = [
        {"product_name": "全新一代智己LS6 Max", "count": 1500, "share": 66.7, "limited": False},
        {"product_name": "全新一代智己LS6 Ultra", "count": 750, "share": 33.3, "limited": False},
    ]
    body = presale_build_card(m, show_notes=False)["card"]["elements"][0]["text"]["content"]
    assert "限量版 **0**" not in body
    assert "留存明细：" in body
    assert "　· 全新一代智己LS6 Max：1,500（66.7%）" in body
    assert "全新一代智己LS6 Ultra：750（33.3%）" in body


# ── launch compare 历史对标窗口 ─────────────────────────────────────


def _launch_df(rows) -> pd.DataFrame:
    df = pd.DataFrame(
        rows,
        columns=["order_number", "lock_time", "intention_payment_time",
                 "series_group_logic", "product_name", "order_type"],
    )
    for c in ["lock_time", "intention_payment_time"]:
        df[c] = pd.to_datetime(df[c], format="mixed")
    for c in ["approve_refund_time", "intention_refund_time", "deposit_refund_time", "deposit_payment_time"]:
        df[c] = pd.NaT
    df["owner_identity_no"] = "310101199001011234"
    df["buyer_identity_no"] = "310101199001011234"
    df["store_name"] = "s1"
    return df


def test_launch_compare_window_uses_generation_launch_open_minute(bdef):
    """历史对标窗口按各代际实测上市开放分钟起算（与目标 CM3 首笔 real lock 对称）。

    CM2 实测锚点 = 20:51；窗口 = [20:51, +elapsed]。20:30 的订单应被排除 ——
    若仍按 20:00 锚点（忽略分钟），它会被错误计入。
    """
    today = pd.Timestamp("2026-09-23")
    df = _launch_df(
        [
            # 目标 CM3：首笔 real lock 20:00（=open_t），22:00 决定 obs → elapsed=2h
            ("t1", "2026-09-23 20:00", "2026-09-23 19:00", "CM3", "全新一代智己LS6 Max", None),
            ("t2", "2026-09-23 22:00", "2026-09-23 19:30", "CM3", "全新一代智己LS6 Max", None),
            # CM2 锚点 20:51：c1(21:00) 在窗口内，c2(20:30) 早于锚点应排除
            ("c1", "2025-09-10 21:00", None, "CM2", "新一代智己LS6", None),
            ("c2", "2025-09-10 20:30", None, "CM2", "新一代智己LS6", None),
        ]
    )
    m = launch_compute(df, bdef, today, "CM3")
    assert m["compare"]["CM2"] == 1  # c2 早于 CM2 的 20:51 锚点，不计入


# ── launch card 留存明细（按 product_name，不做代际无关的限定分类）────


def _launch_metrics(products: list[dict]) -> dict:
    return {
        "generation": "CM3",
        "label": "全新一代 LS6",
        "series": "CM3",
        "as_of_date": "2026-09-23",
        "run_date": "2026-09-23",
        "launch": "2026-09-23",
        "obs": "2026-09-23 16:23",
        "cumulative_lock_count": 0,
        "cumulative_user_car_lock_count": 0,
        "daily_lock_count": 0,
        "daily_user_car_lock_count": 0,
        "cumulative_intention_conv": 0,
        "presale_retained": 0,
        "presale_pool_total": 0,
        "presale_refunded": 0,
        "cumulative_direct_lock": 0,
        "retention": 10,
        "retention_kept": 8,
        "retention_kept_by_product": products,
        "peak_hour": None,
        "peak_count": 0,
        "compare": {"CM2": 1},
        "test_orders_excluded": 0,
    }


def _launch_card_body(products: list[dict], extra: dict | None = None) -> str:
    m = _launch_metrics(products)
    if extra:
        m.update(extra)
    return launch_build_card(m, show_notes=False)["card"]["elements"][0]["text"]["content"]


def test_launch_card_no_limited_lists_by_product_only():
    """无高定限量版的代际（如 CM3）：不渲染限定/非限定分类，按 product_name 平铺。"""
    body = _launch_card_body(
        [
            {"product_name": "全新一代智己LS6 Max", "count": 5, "share": 62.5, "limited": False},
            {"product_name": "全新一代智己LS6 Ultra", "count": 3, "share": 37.5, "limited": False},
        ]
    )
    assert "留存锁单明细：" in body
    assert "留存锁单分类" not in body
    assert "Jimmy" not in body and "限定" not in body and "非限定" not in body
    assert "　· 全新一代智己LS6 Max：5（62.5%）" in body


def test_launch_card_splits_when_limited_present():
    """确有高定限量版（如 DM2 的 Jimmy Choo）时保留限定/非限定二分。"""
    body = _launch_card_body(
        [
            {"product_name": "L6 JimmyChoo 高定限量版", "count": 2, "share": 40.0, "limited": True},
            {"product_name": "L6 Max", "count": 3, "share": 60.0, "limited": False},
        ],
        extra={"retention_kept_limited": 2, "retention_kept_non_limited": 3},
    )
    assert "留存锁单分类：限定 **2** ｜ 非限定 **3**" in body
    assert "　· 限定：L6 JimmyChoo 高定限量版：2（40.0%）" in body
    assert "　· 非限定：L6 Max：3（60.0%）" in body


def test_launch_card_no_retention_shows_empty():
    body = _launch_card_body([])
    assert "留存锁单明细：暂无留存锁单" in body
    assert "留存锁单分类" not in body


def test_launch_card_order_type_unfilled_annotates_instead_of_zero_user_car():
    """新上市代际 order_type 未回填时，不显示误导性的「用户车 0」，改为标注未回填。"""
    body = _launch_card_body(
        [],
        extra={"cumulative_lock_count": 249, "cumulative_user_car_lock_count": 0, "order_type_filled_ratio": 0.0},
    )
    assert "上市至今累计锁单：**249**（order_type 未回填）" in body
    assert "用户车" not in body


def test_launch_card_shows_daily_and_cumulative_lock_rows():
    """当日锁单与上市至今累计锁单分两行展示，当日在上。"""
    body = _launch_card_body(
        [],
        extra={
            "daily_lock_count": 42,
            "daily_user_car_lock_count": 40,
            "cumulative_lock_count": 3234,
            "cumulative_user_car_lock_count": 3226,
            "order_type_filled_ratio": 1.0,
        },
    )
    assert "当日锁单：**42**（用户车 40）" in body
    assert "上市至今累计锁单：**3,234**（用户车 3,226）" in body
    assert body.index("当日锁单") < body.index("上市至今累计锁单")


def test_launch_card_shows_refunded_over_presale_pool():
    """新增「已退订：退订数/总小订数（比例）」行，位于「小订转大定」之后。

    分母取漏斗脚本口径的固定小订池（总小订数），而非动态的留存小订。
    """
    body = _launch_card_body(
        [],
        extra={"presale_pool_total": 16623, "presale_refunded": 238},
    )
    assert "　已退订：**238**/16,623（退订/小订池 1.4%）" in body
    assert body.index("小订转大定") < body.index("已退订") < body.index("直接锁单数")


def test_launch_card_refunded_line_zero_pool_safe():
    """小订池为 0 时不除零，显示 0.0%。"""
    body = _launch_card_body([], extra={"presale_pool_total": 0, "presale_refunded": 0})
    assert "　已退订：**0**/0（退订/小订池 0.0%）" in body


def test_launch_card_order_type_filled_keeps_user_car_breakdown():
    """order_type 正常回填时，保留「用户车 N」子计数。"""
    body = _launch_card_body(
        [],
        extra={"cumulative_lock_count": 100, "cumulative_user_car_lock_count": 87, "order_type_filled_ratio": 1.0},
    )
    assert "上市至今累计锁单：**100**（用户车 87）" in body
    assert "order_type 未回填" not in body
