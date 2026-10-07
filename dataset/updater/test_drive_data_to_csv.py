#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""试驾数据更新：Tableau → dataset/test_drive_data.csv

- Tableau 视图：`core_metric_observation/7`
- 输出：`dataset/test_drive_data.csv`
- 试驾数据不在 Daily pipeline 内，仅在 `make allupdate`（全量更新）或本独立入口维护。

用法:
    python dataset/updater/test_drive_data_to_csv.py
    python dataset/updater/test_drive_data_to_csv.py --mobile
"""

from __future__ import annotations

import sys
import os
import argparse
from pathlib import Path

_UPDATER_DIR = Path(__file__).resolve().parent
if str(_UPDATER_DIR) not in sys.path:
    sys.path.insert(0, str(_UPDATER_DIR))

from tableau_export import (  # noqa: E402
    DEFAULT_TABLEAU_URL,
    VIEW_TEST_DRIVE,
    export_tableau_csv_to_original,
    load_env_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"
OUTPUT_CSV = DATASET_DIR / "test_drive_data.csv"


def export_test_drive(*, view: str = VIEW_TEST_DRIVE, mobile: bool = False, timeout: int = 600) -> bool:
    print("\n" + "=" * 60)
    print("更新试驾数据 (test_drive_data.csv)")
    print("=" * 60)

    token_name = os.getenv("TABLEAU_TOKEN_NAME")
    token_value = os.getenv("TABLEAU_TOKEN_VALUE")
    if not token_name or not token_value:
        print("❌ 缺少 Tableau PAT。请在 .env 配置 TABLEAU_TOKEN_NAME / TABLEAU_TOKEN_VALUE")
        return False

    return export_tableau_csv_to_original(
        view=view,
        output_path=OUTPUT_CSV,
        token_name=token_name,
        token_value=token_value,
        timeout=timeout,
        mobile=mobile,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="试驾数据：Tableau → dataset/test_drive_data.csv")
    parser.add_argument("--timeout", type=int, default=600, help="Tableau 导出超时（秒）")
    parser.add_argument("--mobile", action="store_true", help="使用移动端/非办公网络服务器地址导出")
    parser.add_argument(
        "--view",
        default=f"{DEFAULT_TABLEAU_URL}/#/views/{VIEW_TEST_DRIVE}",
        help="Tableau 试驾视图 URL",
    )
    args = parser.parse_args(argv)

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    load_env_file(REPO_ROOT / ".env")

    ok = export_test_drive(view=args.view, mobile=args.mobile, timeout=args.timeout)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
