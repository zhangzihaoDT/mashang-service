#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键更新 dataset 目录下的核心数据集：

- assign_data.csv
- test_drive_data.csv
- lock_attribution_data.parquet
- order_data.parquet
- config_attribute.parquet
- store_info.csv（外部 original 目录，门店主数据）
"""

from __future__ import annotations

import os
import sys
import argparse
import subprocess
from pathlib import Path


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


def run(cmd: list[str], cwd: Path, step_timeout: int | None = None) -> None:
    kwargs: dict = {"cwd": str(cwd), "env": os.environ.copy()}
    if step_timeout is not None:
        kwargs["timeout"] = step_timeout
    try:
        p = subprocess.run(cmd, **kwargs)
    except subprocess.TimeoutExpired:
        raise SystemExit(
            f"❌ 子进程超时 ({step_timeout}s): {' '.join(str(x) for x in cmd[:3])}..."
        )
    if p.returncode != 0:
        raise SystemExit(p.returncode)


def show_outputs() -> None:
    targets = [
        DATASET_DIR / "assign_data.csv",
        DATASET_DIR / "test_drive_data.csv",
        DATASET_DIR / "lock_attribution_data.parquet",
        DATASET_DIR / "order_data.parquet",
        DATASET_DIR / "config_attribute.parquet",
        Path("/Users/zihao_/Documents/coding/dataset/original/store_info.csv"),
    ]
    for p in targets:
        if not p.exists():
            print(f"❌ missing: {p}")
            continue
        size_mb = p.stat().st_size / (1024 * 1024)
        mtime = p.stat().st_mtime
        print(f"✅ {p.name}  size={size_mb:.2f}MB  mtime={mtime:.0f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="一键更新 dataset 下的核心数据集")
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
    args = parser.parse_args(argv)
    step_timeout = args.step_timeout or (args.timeout + 1800)

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    load_env_file(REPO_ROOT / ".env")

    print("\n" + "=" * 80)
    print("STEP 1: 更新订单数据 (order_data.parquet)")
    print("=" * 80)
    run(
        [
            sys.executable,
            str(UPDATER_DIR / "order_data_to_parquet.py"),
            "--timeout",
            str(int(args.timeout)),
            *(["--mobile"] if args.mobile else []),
        ],
        cwd=REPO_ROOT,
        step_timeout=step_timeout,
    )

    print("\n" + "=" * 80)
    print("STEP 2: 更新选配信息 (config_attribute.parquet)")
    print("=" * 80)
    run(
        [
            sys.executable,
            str(UPDATER_DIR / "order_config_to_parquet.py"),
            "--force",
            "--timeout",
            str(int(args.timeout)),
            *(["--mobile"] if args.mobile else []),
        ],
        cwd=REPO_ROOT,
        step_timeout=step_timeout,
    )

    print("\n" + "=" * 80)
    print("STEP 3: 更新每日 Tableau 运营数据集")
    print("  3a  assign / test_drive")
    print("  3b  lock attribution")
    print("=" * 80)
    lock_cmd = [
        sys.executable,
        str(UPDATER_DIR / "lock_attribution_data_to_parquet.py"),
        "--timeout",
        str(int(args.timeout)),
    ]
    if args.mobile:
        lock_cmd.append("--mobile")
    if args.lock_view:
        lock_cmd.extend(["--view", args.lock_view, "--with-assign-test-drive"])
    run(lock_cmd, cwd=REPO_ROOT, step_timeout=step_timeout)

    print("\n" + "=" * 80)
    print("STEP 4: 更新交付-库存数据 (delivery_inventory.parquet)")
    print("=" * 80)
    run(
        [
            sys.executable,
            str(UPDATER_DIR / "delivery_inventory_to_parquet.py"),
            "--timeout",
            str(int(args.timeout)),
            *(["--mobile"] if args.mobile else []),
        ],
        cwd=REPO_ROOT,
        step_timeout=step_timeout,
    )

    if not args.skip_store_info:
        print("\n" + "=" * 80)
        print("STEP 5: 更新门店信息主数据 (store_info.csv)")
        print("=" * 80)
        run(
            [
                sys.executable,
                str(UPDATER_DIR / "store_info_to_csv.py"),
                "--timeout",
                str(int(args.timeout)),
                *(["--mobile"] if args.mobile else []),
            ],
            cwd=REPO_ROOT,
            step_timeout=step_timeout,
        )
    else:
        print("\n" + "=" * 80)
        print("STEP 5: 跳过门店信息主数据导出 (--skip-store-info)")
        print("=" * 80)

    print("\n" + "=" * 80)
    print("DONE: 输出文件")
    print("=" * 80)
    show_outputs()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

