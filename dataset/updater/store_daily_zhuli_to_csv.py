#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主理数据更新：从 Tableau 导出最新主理在岗统计 / 主理名册

说明:
    Tableau workbook「区域日报」(contentUrl 320) 的门店日报 dashboard 里含
    worksheet「门店日报_主理_当月」，但它是 dashboard 内嵌隐藏表（无独立 view），
    REST / tabcmd 取不到。可直出的等价主理数据源为:
      - 主理在岗统计 (workbook 1_-/sheet1 或 02_0915/sheet1): 主理 × 门店 × 度量
      - 主理信息表  (workbook 15_/sheet2): 主理名册（含门店/门店编码/入职时间）

输出（仓库 dataset/，该目录 .gitignore 不提交）:
    dataset/门店日报_主理_当月.csv   ← 主理在岗统计（长表）
    dataset/主理信息表.csv           ← 主理名册（--with-roster 时）

用法:
    python dataset/updater/store_daily_zhuli_to_csv.py                 # 更新主理在岗统计
    python dataset/updater/store_daily_zhuli_to_csv.py --with-roster   # 同时更新主理名册
    python dataset/updater/store_daily_zhuli_to_csv.py --timeout 600
    python dataset/updater/store_daily_zhuli_to_csv.py --dry-run
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"

ZHULI_VIEW = "https://tableau-hs.immotors.com/#/views/1_-/sheet1"
ROSTER_VIEW = "https://tableau-hs.immotors.com/#/views/15_/sheet2"
OUTPUT_ZHULI = DATASET_DIR / "门店日报_主理_当月.csv"
OUTPUT_ROSTER = DATASET_DIR / "主理信息表.csv"

ZHULI_REQUIRED_COLUMNS = ["门店名称", "门店编码", "姓名", "度量名称", "度量值"]
ROSTER_REQUIRED_COLUMNS = ["主理", "门店", "门店编码", "在职状态"]


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
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


def validate_csv(path: Path, required: list[str], min_rows: int, label: str) -> int:
    import pandas as pd

    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"{label} 缺少必需列: {missing}")
    total = len(df)
    if total < min_rows:
        raise RuntimeError(f"{label} 行数过少({total})，疑似视图不匹配")
    return total


def export_one(exporter, *, view: str, output: Path, tmp: Path, dry_run: bool,
               token_name: str, token_value: str, timeout: int, mobile: bool,
               required: list[str], min_rows: int, label: str) -> int:
    print(f"\n{'=' * 80}\n{label}\n{'=' * 80}")
    target_tmp = tmp if not dry_run else REPO_ROOT / "dataset" / f"{label}_export_check.csv"
    ok = exporter.export_tableau_csv_to_original(
        view=view,
        output_path=target_tmp,
        token_name=token_name,
        token_value=token_value,
        timeout=timeout,
        mobile=mobile,
    )
    if not ok or not target_tmp.exists():
        raise RuntimeError(f"{label} 导出失败，未做任何覆盖")
    rows = validate_csv(target_tmp, required, min_rows, label)
    print(f"  校验通过: {rows} 行")
    if dry_run:
        print(f"  dry-run：保留临时文件 {target_tmp}")
        return rows
    target_tmp.replace(output)
    size_kb = output.stat().st_size / 1024
    print(f"✅ 已覆盖 {output} ({size_kb:.0f} KB)")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="主理数据：Tableau → dataset/*.csv")
    parser.add_argument("--timeout", type=int, default=600, help="Tableau 导出超时（秒）")
    parser.add_argument("--mobile", action="store_true", help="使用移动端服务器地址导出")
    parser.add_argument("--dry-run", action="store_true", help="仅导出校验，不覆盖正式文件")
    parser.add_argument("--view", default=ZHULI_VIEW, help="主理在岗统计视图 URL")
    parser.add_argument("--with-roster", action="store_true", help="同时更新主理名册（主理信息表）")
    args = parser.parse_args(argv)

    load_env_file(REPO_ROOT / ".env")
    token_name = os.getenv("TABLEAU_TOKEN_NAME")
    token_value = os.getenv("TABLEAU_TOKEN_VALUE")
    if not token_name or not token_value:
        print("❌ 缺少 Tableau PAT：TABLEAU_TOKEN_NAME / TABLEAU_TOKEN_VALUE")
        return 1

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    exporter = import_lock_attribution_exporter()

    try:
        export_one(
            exporter, view=args.view, output=OUTPUT_ZHULI,
            tmp=OUTPUT_ZHULI.with_suffix(".csv.tmp"), dry_run=args.dry_run,
            token_name=token_name, token_value=token_value, timeout=args.timeout,
            mobile=args.mobile, required=ZHULI_REQUIRED_COLUMNS, min_rows=1000,
            label="主理在岗统计",
        )
        if args.with_roster:
            export_one(
                exporter, view=ROSTER_VIEW, output=OUTPUT_ROSTER,
                tmp=OUTPUT_ROSTER.with_suffix(".csv.tmp"), dry_run=args.dry_run,
                token_name=token_name, token_value=token_value, timeout=args.timeout,
                mobile=args.mobile, required=ROSTER_REQUIRED_COLUMNS, min_rows=500,
                label="主理信息表",
            )
    except Exception as e:
        print(f"❌ {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
