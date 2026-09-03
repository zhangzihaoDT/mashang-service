#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
门店信息主数据更新：从 Tableau 导出最新 store_info.csv

数据来源视图（Tableau REST API）:
    https://tableau-hs.immotors.com/#/views/7/store_info_1

输出文件（外部 original 目录，与 data_path.md 登记一致）:
    ~/Documents/coding/dataset/original/store_info.csv

门店主数据包含字段: Bloc Name / Dealer Code / Dealer Name Fc / Dealer_type /
Province / City / Region / Store Create Status（开业/暂停/在建/停业）/ 开业时间等。
注意：该视图是门店状态主数据（非慢闪档期报表），慢闪档期（如 popup 0901-1007）
需另从门店明细表获取。

用法:
    python dataset/updater/store_info_to_csv.py            # 导出并覆盖 external store_info.csv
    python dataset/updater/store_info_to_csv.py --timeout 600
    python dataset/updater/store_info_to_csv.py --dry-run  # 只导出校验不写盘
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

STORE_INFO_VIEW = "https://tableau-hs.immotors.com/#/views/7/store_info_1"
STORE_INFO_OUTPUT_CSV = Path(
    "/Users/zihao_/Documents/coding/dataset/original/store_info.csv"
)

# 校验时必需的列（缺失任一列视为视图不匹配，拒绝覆盖）
REQUIRED_COLUMNS = [
    "Bloc Name",
    "Dealer Code",
    "Dealer Name Fc",
    "Dealer_type",
    "City Name",
    "Province Name",
    "Store Create Status Desc",
]


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


def import_lock_attribution_exporter():
    """复用 lock_attribution_data_to_parquet 的 Tableau REST 导出实现。"""
    updater_dir = REPO_ROOT / "dataset" / "updater"
    if str(updater_dir) not in sys.path:
        sys.path.insert(0, str(updater_dir))
    import lock_attribution_data_to_parquet as _mod

    return _mod


def validate_csv(path: Path) -> int:
    """校验导出的 CSV 是否符合门店主数据预期结构，返回数据行数。"""
    import pandas as pd

    df = pd.read_csv(path, encoding="utf-8", dtype=str, keep_default_na=False)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(f"导出的 CSV 缺少必需列: {missing}")
    total = len(df)
    if total < 100:
        raise RuntimeError(f"导出的 CSV 行数过少({total})，疑似视图不匹配")
    status_counts = df["Store Create Status Desc"].value_counts().to_dict()
    print(f"  校验通过: {total} 行, 状态分布 {status_counts}")
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="门店信息主数据：Tableau → external store_info.csv")
    parser.add_argument("--timeout", type=int, default=600, help="Tableau 导出超时（秒）")
    parser.add_argument("--mobile", action="store_true", help="使用移动端/非办公网络服务器地址导出")
    parser.add_argument("--dry-run", action="store_true", help="仅导出到临时文件校验，不覆盖 external store_info.csv")
    parser.add_argument(
        "--view",
        default=STORE_INFO_VIEW,
        help="Tableau 门店信息视图 URL（默认 store_info_1）",
    )
    args = parser.parse_args(argv)

    load_env_file(REPO_ROOT / ".env")
    token_name = os.getenv("TABLEAU_TOKEN_NAME")
    token_value = os.getenv("TABLEAU_TOKEN_VALUE")
    if not token_name or not token_value:
        print("❌ 缺少 Tableau PAT：TABLEAU_TOKEN_NAME / TABLEAU_TOKEN_VALUE")
        return 1

    exporter = import_lock_attribution_exporter()

    if args.dry_run:
        tmp_path = REPO_ROOT / "dataset" / "store_info_export_check.csv"
        print("🧪 dry-run 模式：导出到临时文件，不覆盖正式文件")
    else:
        tmp_path = STORE_INFO_OUTPUT_CSV.with_suffix(".csv.tmp")

    ok = exporter.export_tableau_csv_to_original(
        view=args.view,
        output_path=tmp_path,
        token_name=token_name,
        token_value=token_value,
        timeout=args.timeout,
        mobile=args.mobile,
    )
    if not ok or not tmp_path.exists():
        print("❌ 导出失败，未做任何覆盖")
        return 1

    print(f"  校验导出的 CSV: {tmp_path}")
    try:
        validate_csv(tmp_path)
    except Exception as e:
        print(f"❌ 校验失败，拒绝覆盖: {e}")
        if args.dry_run and tmp_path.exists():
            tmp_path.unlink()
        return 1

    if args.dry_run:
        print(f"✅ dry-run 通过。临时文件保留: {tmp_path}")
        print("  如需真正覆盖，去掉 --dry-run 重新运行。")
        return 0

    # 校验通过后原子覆盖正式文件
    tmp_path.replace(STORE_INFO_OUTPUT_CSV)
    size_kb = STORE_INFO_OUTPUT_CSV.stat().st_size / 1024
    print(f"✅ 已覆盖 {STORE_INFO_OUTPUT_CSV} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
