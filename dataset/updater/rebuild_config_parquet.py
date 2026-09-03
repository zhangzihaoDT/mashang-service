#!/usr/bin/env python
"""
rebuild_config_parquet.py — 用带 Value(配置 code) 列的年度快照重组 config_attribute.parquet

输入（dataset/）:
    config_attribute_data.csv      (≈2023 快照，含 Value code)
    config_attribute_data2024.csv
    config_attribute_data2025.csv
    config_attribute_data2026.csv

输出: dataset/config_attribute.parquet (替换现有)
列: Order Number, Attribute, value(显示名), value_code(配置 code), option_flag, required, price, order_type, vin
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
DATASET_DIR = REPO_ROOT / "dataset"

import pandas as pd

FILES = [
    "config_attribute_data.csv",
    "config_attribute_data2024.csv",
    "config_attribute_data2025.csv",
    "config_attribute_data2026.csv",
]
OUT = DATASET_DIR / "config_attribute.parquet"


def read_csv_multi(path):
    for enc in ["utf-8-sig", "utf-16", "utf-8", "gb18030", "gbk"]:
        for sep in ["\t", ","]:
            try:
                df = pd.read_csv(path, encoding=enc, sep=sep, low_memory=False)
                if df.shape[1] >= 3:
                    return df
            except Exception:
                continue
    return None


def normalize(df_raw):
    oc = next(c for c in df_raw.columns if c.lower().replace(" ", "_") in ["order_number", "ordernumber", "order_no"])
    ac = next(c for c in df_raw.columns if "attribute" in c.lower() and "name" in c.lower())
    vc = next(c for c in df_raw.columns if "value" in c.lower() and "display" in c.lower())
    code_c = next((c for c in df_raw.columns if c.strip().lower() == "value"), None)
    opt = next((c for c in df_raw.columns if c.lower().replace(" ", "_") == "option_flag"), None)
    req = next((c for c in df_raw.columns if c.lower().replace(" ", "_") == "required"), None)
    prc = next((c for c in df_raw.columns if c.lower().replace(" ", "_") == "price"), None)
    extra = [c for c in [opt, req, prc, code_c] if c]
    cols = [oc, ac, vc] + extra
    df = df_raw[cols].dropna(subset=[oc, ac, vc]).copy()
    df[vc] = df[vc].astype(str).str.strip()
    df = df[df[vc].ne("")]
    rename = {oc: "Order Number", ac: "Attribute", vc: "value"}
    if opt:
        rename[opt] = "option_flag"
    if req:
        rename[req] = "required"
    if prc:
        rename[prc] = "price"
        df[prc] = df[prc].astype(str).str.replace(",", "", regex=False)
        df[prc] = pd.to_numeric(df[prc], errors="coerce").astype("Int64")
    if code_c:
        rename[code_c] = "value_code"
        df[code_c] = df[code_c].astype(str).str.strip()
        df[code_c] = df[code_c].replace({"nan": None, "<NA>": None, "None": None, "": None})
    return df.rename(columns=rename)


def main():
    parts = []
    for f in FILES:
        p = DATASET_DIR / f
        if not p.exists():
            print(f"⚠️ 缺文件: {f}")
            continue
        df_raw = read_csv_multi(p)
        if df_raw is None:
            print(f"❌ 无法读取: {f}")
            continue
        df = normalize(df_raw)
        parts.append(df)
        print(f" - {f}: {len(df_raw):,} 行 → {len(df):,} 行（含 Value code: {df['value_code'].notna().sum():,}）")

    if not parts:
        print("❌ 无可用文件")
        return
    cfg = pd.concat(parts, ignore_index=True)
    print(f"合并总行数: {len(cfg):,} | 唯一订单: {cfg['Order Number'].nunique():,}")
    print(f"value_code 覆盖: {cfg['value_code'].notna().sum():,} 行 ({cfg['value_code'].notna().mean()*100:.1f}%)")

    enrich = pd.read_parquet(DATASET_DIR / "order_data.parquet")[["order_number", "order_type", "vin"]].drop_duplicates(subset=["order_number"])
    enrich["order_number"] = enrich["order_number"].astype(str)
    cfg = cfg.merge(enrich, left_on="Order Number", right_on="order_number", how="left").drop(columns=["order_number"])

    cfg.to_parquet(OUT, index=False)
    print(f"✅ 已写入 {OUT}: {len(cfg):,} 行, 列={cfg.columns.tolist()}")


if __name__ == "__main__":
    main()
