#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""常驻定时器：预售/上市监控刷新 + 推送（标准库实现，无第三方依赖）。

调度（key day = 任一 active 代际的预售首日 start 或上市日 end）：
  每日 09:00                     dataset 全量刷新 + 校验 + 每日观察同步（串行；校验失败则跳过同步）
  key day 17:00–23:00 每小时 :00  order_data 刷新 + 监控（串行）
  每日 09:30                     监控（日报）

监控默认只推送 presale 阶段代际（--phase presale）；
需要 launch 监控时显式传 --phase launch,presale 或 --series。

启动方式：
    source .venv/bin/activate
    # 方式一：两个终端
    caffeinate -i
    python schedule_launch_lock_evening_updates.py
    # 方式二：合并
    caffeinate -i python schedule_launch_lock_evening_updates.py
    # 后台
    nohup caffeinate -i .venv/bin/python schedule_launch_lock_evening_updates.py \\
        > logs/scheduler/stdout.log 2>&1 &

用法:
    python schedule_launch_lock_evening_updates.py --once --dry-run   # 立即跑一轮监控后退出
    python schedule_launch_lock_evening_updates.py --once --as-of 2026-09-10 --dry-run
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
_WS_ROOT = REPO_ROOT / "mashang_workspace"
for _p in (str(REPO_ROOT), str(_WS_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from utils.monitors.phase import is_key_day, load_business_definition  # noqa: E402

LOG_DIR = REPO_ROOT / "logs" / "scheduler"
FULL_REFRESH_TIME = (9, 0)
MONITOR_DAILY_TIME = (9, 30)
DEFAULT_KEY_HOURS = [17, 18, 19, 20, 21, 22, 23]

_STOP = False


def _key_hours(bdef: dict) -> list[int]:
    mon = (bdef.get("monitor") or {}).get("freshness") or {}
    hours = mon.get("key_day_hours") or DEFAULT_KEY_HOURS
    return sorted(int(h) for h in hours)


def due_actions(now: datetime, bdef: dict) -> list[str]:
    """返回当前分钟应执行的动作名列表（纯函数，便于测试）。"""
    hm = (now.hour, now.minute)
    key = is_key_day(bdef, now.date())
    actions: list[str] = []
    if hm == FULL_REFRESH_TIME:
        actions += ["refresh_full", "dataset_validate", "daily_observation_sync"]
    if now.minute == 0 and now.hour in _key_hours(bdef) and key:
        actions += ["refresh_order_data", "monitor"]
    if hm == MONITOR_DAILY_TIME:
        actions.append("monitor")
    return actions


def _log_path(now: datetime) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"{now:%Y-%m-%d}.log"


def log(msg: str, now: datetime | None = None) -> None:
    now = now or datetime.now()
    line = f"[{now:%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        with open(_log_path(now), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _run(cmd: list[str], label: str, dry_run: bool, now: datetime) -> int:
    if dry_run:
        log(f"[dry-run] {label}: {' '.join(cmd)}", now)
        return 0
    log(f"▶ {label}: {' '.join(cmd)}", now)
    with open(_log_path(now), "a", encoding="utf-8") as f:
        p = subprocess.run(cmd, cwd=str(REPO_ROOT), env=os.environ.copy(), stdout=f, stderr=subprocess.STDOUT)
    log(f"■ {label} exit={p.returncode}", now)
    return p.returncode


def _monitor_cmd(args) -> list[str]:
    cmd = [sys.executable, str(_WS_ROOT / "runtime_scripts" / "vehicle_sales_monitor.py")]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.as_of:
        cmd += ["--as-of", args.as_of]
    if args.series:
        cmd += ["--series", args.series]
    if args.phase:
        cmd += ["--phase", args.phase]
    return cmd


def _dispatch(action: str, args, now: datetime) -> int:
    """按动作名执行对应子进程，返回 exit code。"""
    if action == "refresh_full":
        return _run([sys.executable, str(REPO_ROOT / "dataset" / "updater" / "update_all_datasets.py")],
                    "refresh_full", args.dry_run, now)
    if action == "dataset_validate":
        return _run([sys.executable, str(_WS_ROOT / "utility_scripts" / "dataset_validate.py")],
                    "dataset_validate", args.dry_run, now)
    if action == "daily_observation_sync":
        return _run([sys.executable, str(_WS_ROOT / "utility_scripts" / "skills_order_observation_daily.py")],
                    "daily_observation_sync", args.dry_run, now)
    if action == "refresh_order_data":
        return _run([sys.executable, str(REPO_ROOT / "dataset" / "updater" / "order_data_to_parquet.py")],
                    "refresh_order_data", args.dry_run, now)
    if action == "monitor":
        return _run(_monitor_cmd(args), "monitor", args.dry_run, now)
    return 0


def process_batch(now: datetime, bdef: dict, args, fired: set[str]) -> None:
    """按序执行当前时刻 due_actions 的全部动作；dataset_validate 失败时跳过 daily_observation_sync。"""
    validate_ok: bool | None = None
    for action in due_actions(now, bdef):
        token = f"{now:%Y-%m-%d} {action} {now.hour}:{now.minute}"
        if token in fired:
            continue
        fired.add(token)
        if action == "daily_observation_sync" and validate_ok is False:
            log("跳过 daily_observation_sync：dataset_validate 失败，不写外部系统", now)
            continue
        rc = _dispatch(action, args, now)
        if action == "dataset_validate":
            validate_ok = rc == 0


def run_once(args, bdef: dict) -> int:
    now = datetime.now()
    log("--once：执行一轮完整链路（刷新 + 监控）", now)
    _run([sys.executable, str(REPO_ROOT / "dataset" / "updater" / "order_data_to_parquet.py")],
         "refresh_order_data", args.dry_run, now)
    _run(_monitor_cmd(args), "monitor", args.dry_run, now)
    return 0


def run_loop(args, bdef: dict) -> int:
    log("调度器启动", datetime.now())
    log(f"  key_day_hours={_key_hours(bdef)}  数据管道={FULL_REFRESH_TIME}  日报={MONITOR_DAILY_TIME}  monitor_phase={args.phase}", datetime.now())
    fired: set[str] = set()
    last_minute: tuple[int, int] | None = None

    while not _STOP:
        now = datetime.now()
        minute_key = (now.hour, now.minute)
        if minute_key != last_minute:
            last_minute = minute_key
            # 每分钟重置一次去重集合（按动作名 + 当日）
            fired = {k for k in fired if k.startswith(f"{now:%Y-%m-%d} ")}
            process_batch(now, bdef, args, fired)
        time.sleep(5)

    log("调度器停止", datetime.now())
    return 0


def _handle_signal(signum, frame):  # noqa: ARG001
    global _STOP
    _STOP = True


def main() -> int:
    parser = argparse.ArgumentParser(description="预售/上市监控常驻调度器")
    parser.add_argument("--once", action="store_true", help="立即执行一轮监控后退出（便于测试）")
    parser.add_argument("--dry-run", action="store_true", help="不真正刷新/发送，只打印/写日志")
    parser.add_argument("--as-of", default=None, help="传给监控的统计基准日 YYYY-MM-DD")
    parser.add_argument("--series", default=None, help="过滤代际，逗号分隔")
    parser.add_argument("--phase", default="presale", help="过滤阶段 presale/launch（默认 presale）")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    bdef = load_business_definition()
    if args.once:
        return run_once(args, bdef)
    return run_loop(args, bdef)


if __name__ == "__main__":
    raise SystemExit(main())
