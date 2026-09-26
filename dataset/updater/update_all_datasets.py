#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键更新 dataset 目录下的核心数据集（dataset update-all）。

数据集清单由 dataset/updater/dataset_registry.py 统一维护（唯一 source of truth），
本脚本负责按 step 刷新，并在结束（无论成败）打印逐数据集结论：

- 本次是否更新 / 状态 / 行数 / 文件更新时间 / 数据最新时点

行为约定：
- 单个 step 失败不再中断全链路（continue-on-error），最终整体返回非 0。
- `--fail-fast` 可恢复「首个失败即停」的旧行为。
- `--status-only` 只读查看现状，不触发任何数据源/写操作。

覆盖数据集（见 registry）：
- order_data.parquet / config_attribute.parquet
- assign_data.csv / test_drive_data.csv / lock_attribution_data.parquet
- delivery_inventory.parquet / store_info.csv / store_daily_leads.csv
"""

from __future__ import annotations

import os
import sys
import argparse
import subprocess
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dataset_registry import describe_all, format_report  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"
UPDATER_DIR = DATASET_DIR / "updater"


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        return


def office_tableau_reachable(timeout: float = 8.0) -> bool:
    """探测办公网 Tableau 主机是否可达（DNS 解析 + TCP 连接）。

    命中 DNS/连接失败时返回 False，供编排层整体回退移动链路（--mobile）。
    """
    import socket
    from urllib.parse import urlparse

    base_url = os.getenv("TABLEAU_SERVER_URL") or "https://tableau-hs.immotors.com"
    parsed = urlparse(base_url)
    host = parsed.hostname
    if not host:
        return True
    port = parsed.port or (80 if parsed.scheme == "http" else 443)
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


def run(cmd: list[str], cwd: Path, step_timeout: int | None = None) -> int:
    """执行子进程并返回退出码；不再因失败抛 SystemExit，便于 continue-on-error。

    超时返回 124（沿用 shell timeout 约定）。
    """
    kwargs: dict = {"cwd": str(cwd), "env": os.environ.copy()}
    if step_timeout is not None:
        kwargs["timeout"] = step_timeout
    try:
        p = subprocess.run(cmd, **kwargs)
    except subprocess.TimeoutExpired:
        print(f"❌ 子进程超时 ({step_timeout}s): {' '.join(str(x) for x in cmd[:3])}...")
        return 124
    return p.returncode


def _header(title: str) -> None:
    print("\n" + "=" * 80, flush=True)
    print(title, flush=True)
    print("=" * 80, flush=True)


def build_steps(args: argparse.Namespace, mobile: bool) -> list[dict]:
    """按 step 组织更新命令；cmd=None 表示跳过。"""
    steps: list[dict] = []

    steps.append(
        {
            "id": "1",
            "title": "STEP 1: 更新订单数据 (order_data.parquet)",
            "cmd": [
                sys.executable,
                str(UPDATER_DIR / "order_data_to_parquet.py"),
                "--timeout",
                str(int(args.timeout)),
                *(["--mobile"] if mobile else []),
            ],
        }
    )

    steps.append(
        {
            "id": "2",
            "title": "STEP 2: 更新选配信息 (config_attribute.parquet)",
            "cmd": [
                sys.executable,
                str(UPDATER_DIR / "order_config_to_parquet.py"),
                "--force",
                "--timeout",
                str(int(args.timeout)),
                *(["--mobile"] if mobile else []),
            ],
        }
    )

    lock_cmd = [
        sys.executable,
        str(UPDATER_DIR / "lock_attribution_data_to_parquet.py"),
        "--timeout",
        str(int(args.timeout)),
    ]
    if mobile:
        lock_cmd.append("--mobile")
    if args.lock_view:
        lock_cmd.extend(["--view", args.lock_view, "--with-assign-test-drive"])
    steps.append(
        {
            "id": "3",
            "title": "STEP 3: 更新每日 Tableau 运营数据集 (assign / test_drive / lock attribution)",
            "cmd": lock_cmd,
        }
    )

    steps.append(
        {
            "id": "4",
            "title": "STEP 4: 更新交付-库存数据 (delivery_inventory.parquet)",
            "cmd": [
                sys.executable,
                str(UPDATER_DIR / "delivery_inventory_to_parquet.py"),
                "--timeout",
                str(int(args.timeout)),
                *(["--mobile"] if mobile else []),
            ],
        }
    )

    steps.append(
        {
            "id": "5",
            "title": "STEP 5: 更新门店信息主数据 (store_info.csv)",
            "cmd": None
            if args.skip_store_info
            else [
                sys.executable,
                str(UPDATER_DIR / "store_info_to_csv.py"),
                "--timeout",
                str(int(args.timeout)),
                *(["--mobile"] if mobile else []),
            ],
        }
    )

    steps.append(
        {
            "id": "6",
            "title": "STEP 6: 增量更新每日下发线索（by门店）(store_daily_leads.csv)",
            "cmd": None
            if args.skip_store_leads
            else [
                sys.executable,
                str(UPDATER_DIR / "store_daily_leads_to_csv.py"),
                "--timeout",
                str(int(args.timeout)),
                *(["--mobile"] if mobile else []),
            ],
        }
    )

    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="一键更新 dataset 下的核心数据集（dataset update-all）")
    parser.add_argument("--timeout", type=int, default=600, help="Tableau 导出超时（秒）")
    parser.add_argument("--step-timeout", type=int, default=None, help="每个步骤的总超时（秒），默认 timeout+1800")
    parser.add_argument("--mobile", action="store_true", help="使用移动端/非办公网络服务器地址导出")
    parser.add_argument(
        "--lock-view",
        default=None,
        help="锁单归因 Tableau 视图（不传则使用 lock_attribution_data_to_parquet.py 默认值）",
    )
    parser.add_argument(
        "--skip-store-info",
        action="store_true",
        help="跳过 STEP 5：门店信息主数据导出（store_info.csv）",
    )
    parser.add_argument(
        "--skip-store-leads",
        action="store_true",
        help="跳过 STEP 6：每日下发线索（by门店）增量更新（store_daily_leads.csv）",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="首个 step 失败即停止（默认 continue-on-error，跑完全部 step 再汇总）",
    )
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="只读查看各数据集现状（行数 / 文件更新时间 / 数据最新时点），不触发更新",
    )
    args = parser.parse_args(argv)

    if args.status_only:
        print(format_report(describe_all(), status_only=True), flush=True)
        return 0

    step_timeout = args.step_timeout or (args.timeout + 1800)

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    load_env_file(REPO_ROOT / ".env")

    mobile = args.mobile
    if not mobile and not office_tableau_reachable():
        print("⚠️ 办公网 Tableau 不可达，自动回退到移动链路（--mobile）", flush=True)
        mobile = True

    run_started = time.time()
    failed_steps: list[str] = []

    for step in build_steps(args, mobile):
        if step["cmd"] is None:
            _header(f"{step['title']} —— 跳过")
            continue
        _header(step["title"])
        rc = run(step["cmd"], cwd=REPO_ROOT, step_timeout=step_timeout)
        if rc != 0:
            failed_steps.append(step["id"])
            print(f"⚠️ {step['title']} 失败 (rc={rc})", flush=True)
            if args.fail_fast:
                print("⏹ --fail-fast：停止后续步骤", flush=True)
                break

    print("\n" + format_report(describe_all(), run_started=run_started, failed_steps=failed_steps), flush=True)

    if failed_steps:
        print(f"\n❌ 失败 step: {', '.join(failed_steps)}", flush=True)
        return 1
    print("\n✅ 全部 step 完成", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
