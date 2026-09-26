#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日下发线索（by门店）：增量更新

粒度：门店 × 日期 → 下发线索数（非渠道/全局聚合）

来源视图:
    https://tableau-hs.immotors.com/#/views/165/leads_assign_city_store2_1
    workbook「线索推演」(contentUrl 165)，门店级：门店 × 日 × 下发线索数

注意:
    该视图只返回**滚动窗口**（约最近 10 天），所以本脚本做**增量合并**：
    每次拉取窗口数据 → 与已有 dataset 去重合并 → 逐日扩长历史。

输出（仓库 dataset/，.gitignore 不提交）:
    dataset/store_daily_leads.csv    列: 门店 / 日期 / 下发线索数

用法:
    python dataset/updater/store_daily_leads_to_csv.py            # 增量更新
    python dataset/updater/store_daily_leads_to_csv.py --dry-run  # 只拉取校验，不合并写盘
    python dataset/updater/store_daily_leads_to_csv.py --rebuild  # 忽略历史，全量重建（仅窗口）
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"

LEADS_VIEW = "https://tableau-hs.immotors.com/#/views/165/leads_assign_city_store2_1"
OUTPUT_CSV = DATASET_DIR / "store_daily_leads.csv"

SRC_STORE_COL = "lc_assign_1st2sales_dealer_name"
SRC_DATE_COL = "日(lc_assign_time_min)"
SRC_VALUE_COL = "下发线索数"
OUT_COLUMNS = ["门店", "日期", "下发线索数"]


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
    updater_dir = REPO_ROOT / "dataset" / "updater"
    if str(updater_dir) not in sys.path:
        sys.path.insert(0, str(updater_dir))
    import lock_attribution_data_to_parquet as _mod

    return _mod


def _parse_date(v: str):
    import pandas as pd

    s = str(v).strip()
    if "年" in s:
        s = s.replace("年", "-").replace("月", "-").replace("日", "")
    return pd.to_datetime(s, errors="coerce")


def normalize(src_path: Path):
    """把导出的视图 CSV 规范成 [门店, 日期, 下发线索数]。"""
    import pandas as pd

    df = pd.read_csv(src_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    missing = [c for c in (SRC_STORE_COL, SRC_DATE_COL, SRC_VALUE_COL) if c not in df.columns]
    if missing:
        raise RuntimeError(f"视图缺少必需列: {missing}（实际列: {list(df.columns)}）")
    out = pd.DataFrame({
        "门店": df[SRC_STORE_COL].astype(str).str.strip(),
        "日期": df[SRC_DATE_COL].map(_parse_date),
        "下发线索数": pd.to_numeric(df[SRC_VALUE_COL], errors="coerce").fillna(0).astype(int),
    })
    out = out[out["门店"].ne("") & out["日期"].notna()]
    return out


def export_view(exporter, *, tmp: Path, token_name: str, token_value: str,
                timeout: int, mobile: bool) -> None:
    ok = exporter.export_tableau_csv_to_original(
        view=LEADS_VIEW, output_path=tmp,
        token_name=token_name, token_value=token_value, timeout=timeout, mobile=mobile,
    )
    if not ok or not tmp.exists():
        raise RuntimeError("视图导出失败")


def main(argv: list[str] | None = None) -> int:
    import pandas as pd

    parser = argparse.ArgumentParser(description="每日下发线索（by门店）：Tableau → dataset（增量）")
    parser.add_argument("--timeout", type=int, default=600, help="Tableau 导出超时（秒）")
    parser.add_argument("--mobile", action="store_true", help="使用移动端服务器地址导出")
    parser.add_argument("--dry-run", action="store_true", help="只拉取校验，不合并写盘")
    parser.add_argument("--rebuild", action="store_true", help="忽略历史，仅用本次窗口重建")
    args = parser.parse_args(argv)

    load_env_file(REPO_ROOT / ".env")
    token_name = os.getenv("TABLEAU_TOKEN_NAME")
    token_value = os.getenv("TABLEAU_TOKEN_VALUE")
    if not token_name or not token_value:
        print("❌ 缺少 Tableau PAT：TABLEAU_TOKEN_NAME / TABLEAU_TOKEN_VALUE")
        return 1

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    exporter = import_lock_attribution_exporter()

    tmp = DATASET_DIR / "store_daily_leads.csv.tmp"
    try:
        export_view(exporter, tmp=tmp, token_name=token_name, token_value=token_value,
                    timeout=args.timeout, mobile=args.mobile)
        fresh = normalize(tmp)
    except Exception as e:
        print(f"❌ {e}")
        return 1
    finally:
        if tmp.exists() and not args.dry_run:
            tmp.unlink()

    if fresh.empty:
        print("❌ 拉取到 0 行，疑似视图不匹配，未写盘")
        return 1

    print(f"本次窗口: {fresh['日期'].min().date()} ~ {fresh['日期'].max().date()}，"
          f"{fresh['门店'].nunique()} 门店 / {len(fresh)} 行")

    if args.rebuild or not OUTPUT_CSV.exists():
        merged = fresh
    else:
        old = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")
        old["日期"] = pd.to_datetime(old["日期"], errors="coerce")
        before = len(old)
        merged = pd.concat([old, fresh], ignore_index=True)
        merged = merged.dropna(subset=["日期"])
        merged = merged.drop_duplicates(subset=["门店", "日期"], keep="last")
        print(f"历史 {before} 行 → 合并后 {len(merged)} 行（新增/更新 {len(merged) - before}）")

    merged = merged.sort_values(["日期", "门店"]).reset_index(drop=True)
    merged["日期"] = merged["日期"].dt.strftime("%Y-%m-%d")
    merged = merged[OUT_COLUMNS]

    if args.dry_run:
        print(f"✅ dry-run 通过：{len(merged)} 行，未写盘")
        return 0

    out_tmp = OUTPUT_CSV.with_suffix(".csv.write")
    merged.to_csv(out_tmp, index=False, encoding="utf-8-sig")
    out_tmp.replace(OUTPUT_CSV)
    print(f"✅ 已更新 {OUTPUT_CSV}（{len(merged)} 行，"
          f"{merged['日期'].min()} ~ {merged['日期'].max()}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
