#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下发线索（全局渠道级）更新：Tableau → dataset/assign_data.csv

- Tableau 视图：`core_metric_observation/assign`
- 输出：`dataset/assign_data.csv`（含门店/平台/APP/快慢闪/直播渠道拆分 + 当日/7/30 日转化）
- 这是 Daily pipeline 的每日下发线索数据源。

用法:
    python dataset/updater/assign_data_to_csv.py
    python dataset/updater/assign_data_to_csv.py --mobile
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
    VIEW_ASSIGN,
    export_tableau_csv_to_original,
    load_env_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"
OUTPUT_CSV = DATASET_DIR / "assign_data.csv"


def export_assign(*, view: str = VIEW_ASSIGN, mobile: bool = False, timeout: int = 600) -> bool:
    print("\n" + "=" * 60)
    print("更新下发线索 (assign_data.csv)")
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
    parser = argparse.ArgumentParser(description="下发线索（全局渠道级）：Tableau → dataset/assign_data.csv")
    parser.add_argument("--timeout", type=int, default=600, help="Tableau 导出超时（秒）")
    parser.add_argument("--mobile", action="store_true", help="使用移动端/非办公网络服务器地址导出")
    parser.add_argument(
        "--view",
        default=f"{DEFAULT_TABLEAU_URL}/#/views/{VIEW_ASSIGN}",
        help="Tableau 下发线索视图 URL",
    )
    args = parser.parse_args(argv)

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    load_env_file(REPO_ROOT / ".env")

    ok = export_assign(view=args.view, mobile=args.mobile, timeout=args.timeout)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
