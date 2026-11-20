#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
订单-手机号映射更新流水线（order_phone_map）

背景
----
`order_data.parquet` 不含任何手机号字段，`lock_attribution_data.parquet` 只有
`lc_user_phone_md5` 而无订单维度，两者无法按客户关联。本数据集补上这一缺口：
以 `order_number` 为粒度，提供订单侧手机号（哈希化），从而打通
「手机号 → 订单明细 → 线索渠道」。

隐私约束（重要）
----------------
- 输出 **只保留哈希**，不落明文手机号；明文仅在内存中短暂存在。
- 哈希算法与 `lock_attribution_data.lc_user_phone_md5` **严格对齐**：
  `md5(纯 11 位手机号)`，无盐、无前缀、小写 32 位十六进制。
  对齐之后两张表可直接等值关联。
- ⚠️ 无盐 MD5 可被穷举还原，不提供实质匿名保护，按个人信息同等级别管控。

1. 从 Tableau 导出最新视图数据到 dataset/tableau-hs/orders/order_phone_map.csv
2. 读取该 CSV（兼容全量导出与滚动增量），哈希化手机号后与现有 Parquet 合并
3. 以 order_number 去重，输出 dataset/order_phone_map.parquet

默认运行:
    python dataset/updater/order_phone_map_to_parquet.py

仅整理本地 CSV（不联网）:
    python dataset/updater/order_phone_map_to_parquet.py --no-export

指定已有输入文件:
    python dataset/updater/order_phone_map_to_parquet.py --no-export --input <path>

Tableau PAT 从仓库根目录 .env 读取:
- TABLEAU_TOKEN_NAME="..."
- TABLEAU_TOKEN_VALUE="..."

输入: dataset/tableau-hs/orders/order_phone_map.csv
输出: dataset/order_phone_map.parquet
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

_UPDATER_DIR = Path(__file__).resolve().parent
if str(_UPDATER_DIR) not in sys.path:
    sys.path.insert(0, str(_UPDATER_DIR))

from tableau_export import (  # noqa: E402
    DEFAULT_TABLEAU_URL,
    export_tableau_csv_to_original,
    load_env_file,
)

if TYPE_CHECKING:
    import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"
ORIGINAL_DIR = DATASET_DIR / "tableau-hs" / "orders"
INPUT_CSV = ORIGINAL_DIR / "order_phone_map.csv"
OUTPUT_FILE = DATASET_DIR / "order_phone_map.parquet"

# Tableau 视图：订单-手机号映射（W14 / sheet 2）
ORDER_PHONE_MAP_VIEW = f"{DEFAULT_TABLEAU_URL}/#/views/W14/2"

# 明文手机号列 -> 输出哈希列名
PHONE_COLUMNS = {
    "buyer_cell_phone": "buyer_phone_md5",
    "lead_phone_number": "lead_phone_md5",
    "capp_order_phone": "capp_phone_md5",
}

# 列名别名的归一化映射（兼容 Tableau 可能导出的不同写法）
COLUMN_ALIASES = {
    "order_number": "order_number",
    "order number": "order_number",
    "order_no": "order_number",
    "buyer_cell_phone": "buyer_cell_phone",
    "buyer cell phone": "buyer_cell_phone",
    "lead_phone_number": "lead_phone_number",
    "lead phone number": "lead_phone_number",
    "capp_order_phone": "capp_order_phone",
    "capp order phone": "capp_order_phone",
}

# 合法的中国大陆手机号：11 位、1 开头、第二位 3-9
PHONE_PATTERN = r"^1[3-9]\d{9}$"


def read_csv_smart(file_path: Path) -> "pd.DataFrame":
    """读取 Tableau 导出 CSV，自动探测编码与分隔符（UTF-16/Tab 是常见导出形态）。"""
    import pandas as pd

    if not file_path.exists():
        print(f"⚠️ 文件不存在: {file_path}")
        return pd.DataFrame()

    try:
        if file_path.stat().st_size == 0:
            print(f"❌ 文件为空(0字节): {file_path}")
            return pd.DataFrame()
    except Exception:
        pass

    print(f"📖 正在读取: {file_path.name} ...")

    encodings = ["utf-16", "utf-8-sig", "utf-8", "gb18030", "gbk"]
    separators = ["\t", ","]

    for enc in encodings:
        for sep in separators:
            try:
                df = pd.read_csv(file_path, encoding=enc, sep=sep, dtype=str)
                # 分隔符猜错时整行会挤进单列
                if df.shape[1] < 2:
                    continue
                print(
                    f"✅ 读取成功 (编码: {enc}, 分隔符: "
                    f"'{sep if sep != chr(9) else chr(92) + 't'}') - 形状: {df.shape}"
                )
                return df
            except Exception:
                continue

    try:
        print("⚠️ 尝试默认参数读取...")
        return pd.read_csv(file_path, dtype=str)
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        return pd.DataFrame()


def normalize_columns(df: "pd.DataFrame") -> "pd.DataFrame":
    """表头归一化：去空白、统一小写别名到标准列名。"""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    rename = {}
    for c in df.columns:
        key = c.strip().lower().replace("__", "_")
        if key in COLUMN_ALIASES:
            rename[c] = COLUMN_ALIASES[key]
    df = df.rename(columns=rename)
    return df


def normalize_phone(series: "pd.Series") -> "pd.Series":
    """把原始手机号清洗成纯 11 位数字，非法值置 NA（不静默保留脏值）。"""
    import pandas as pd

    s = series.astype("string").str.strip()
    # 去掉常见国家码前缀、分隔符
    s = s.str.replace(r"[\s\-()]", "", regex=True)
    s = s.str.replace(r"^(?:\+?86|0086)", "", regex=True)
    # Excel 可能导出成科学计数法/带小数，先剔除
    s = s.str.replace(r"\.0$", "", regex=True)
    valid = s.str.match(PHONE_PATTERN, na=False)
    return s.where(valid, pd.NA).astype("string")


def hash_phone(series: "pd.Series") -> "pd.Series":
    """无盐 MD5，与 lock_attribution_data.lc_user_phone_md5 算法严格一致。"""
    import pandas as pd

    s = normalize_phone(series)
    hashed = s.map(
        lambda v: hashlib.md5(v.encode("utf-8")).hexdigest() if pd.notna(v) else pd.NA
    )
    return hashed.astype("string")


def build_frame(df: "pd.DataFrame") -> "pd.DataFrame":
    """明文 CSV → 哈希 Parquet 帧（一行一 order_number）。"""
    import pandas as pd

    df = normalize_columns(df)

    if "order_number" not in df.columns:
        raise ValueError(
            f"输入缺少 order_number 列，无法建立映射。实际列: {list(df.columns)}"
        )

    out = pd.DataFrame()
    out["order_number"] = df["order_number"].astype("string").str.strip()
    out = out[out["order_number"].notna() & (out["order_number"] != "")]

    for src, dst in PHONE_COLUMNS.items():
        if src in df.columns:
            out[dst] = hash_phone(df[src])
        else:
            print(f"⚠️ 输入缺少列 {src}，输出 {dst} 将全部为空")
            out[dst] = pd.NA
            out[dst] = out[dst].astype("string")

    # 至少要有一种手机号，否则该行无关联价值
    phone_cols = list(PHONE_COLUMNS.values())
    any_phone = out[phone_cols].notna().any(axis=1)
    dropped = int((~any_phone).sum())
    if dropped:
        print(f"🧹 丢弃无任何有效手机号的行: {dropped}")
    out = out[any_phone]

    # order_number 唯一
    before = len(out)
    out = out.drop_duplicates(subset=["order_number"], keep="last")
    if before != len(out):
        print(f"✂️  按 order_number 去重: {before} -> {len(out)}")

    return out.reset_index(drop=True)


def merge_with_existing(df_new: "pd.DataFrame") -> "pd.DataFrame":
    """与现有 Parquet 合并：新数据覆盖同 order_number 的旧值（增量为权威）。"""
    import pandas as pd

    if not OUTPUT_FILE.exists():
        print("📝 未发现现有 Parquet 文件，创建新文件...")
        return df_new

    print(f"📚 发现现有 Parquet 文件: {OUTPUT_FILE}")
    try:
        df_existing = pd.read_parquet(OUTPUT_FILE)
    except Exception as e:
        print(f"⚠️ 读取现有 Parquet 失败（{e}），将仅使用新数据")
        return df_new

    print(f"   现有数据: {df_existing.shape[0]} 行")

    all_cols = list(dict.fromkeys(list(df_existing.columns) + list(df_new.columns)))
    df_existing = df_existing.reindex(columns=all_cols)
    df_new = df_new.reindex(columns=all_cols)

    before = len(df_existing) + len(df_new)
    df_final = pd.concat([df_existing, df_new], ignore_index=True)
    df_final = df_final.drop_duplicates(subset=["order_number"], keep="last")
    print(
        f"🔀 合并后按 order_number 去重: {before} -> {len(df_final)} "
        f"(移除 {before - len(df_final)})"
    )
    return df_final


def attach_flags(df: "pd.DataFrame") -> "pd.DataFrame":
    """附加可解释性字段：是否存在买家/线索/CAPP 手机号。"""
    import pandas as pd

    df = df.copy()
    for col in ["buyer_phone_md5", "lead_phone_md5", "capp_phone_md5"]:
        if col in df.columns:
            df[col] = df[col].astype("string")
    df["has_phone"] = (
        df[[c for c in ["buyer_phone_md5", "lead_phone_md5", "capp_phone_md5"] if c in df.columns]]
        .notna()
        .any(axis=1)
        .astype(bool)
    )
    return df


def process_order_phone_map(input_file: Path = INPUT_CSV) -> int:
    import pandas as pd  # noqa: F401

    raw = read_csv_smart(input_file)
    if raw.empty:
        print(f"❌ 输入为空或不可读: {input_file}")
        return 1

    try:
        df_new = build_frame(raw)
    except ValueError as e:
        print(f"❌ {e}")
        return 1

    print(f"✅ 本次输入有效行: {len(df_new)}")

    df_final = merge_with_existing(df_new)
    df_final = attach_flags(df_final)

    # 列顺序稳定，便于 diff 与消费方引用
    preferred = [
        "order_number",
        "buyer_phone_md5",
        "lead_phone_md5",
        "capp_phone_md5",
        "has_phone",
    ]
    cols = [c for c in preferred if c in df_final.columns] + [
        c for c in df_final.columns if c not in preferred
    ]
    df_final = df_final[cols]

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_FILE.with_name(OUTPUT_FILE.name + ".tmp")
    df_final.to_parquet(tmp, index=False)
    tmp.replace(OUTPUT_FILE)

    print(f"💾 写入成功: {OUTPUT_FILE}")
    print(f"   最终: {len(df_final)} 行, {df_final.shape[1]} 列")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="订单-手机号映射（哈希）更新：Tableau 导出 -> 增量合并 -> Parquet"
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="跳过 Tableau 导出，直接用已有本地 CSV 整理",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=f"指定输入 CSV（默认 {INPUT_CSV.relative_to(REPO_ROOT)}）",
    )
    parser.add_argument(
        "--view",
        type=str,
        default=ORDER_PHONE_MAP_VIEW,
        help="Tableau 视图 URL 或 Workbook/Sheet",
    )
    parser.add_argument("--timeout", type=int, default=180, help="HTTP 超时秒数")
    parser.add_argument(
        "--mobile",
        action="store_true",
        help="非办公网链路（使用移动端 Tableau 地址）",
    )
    args = parser.parse_args()

    input_file = args.input or INPUT_CSV

    if not args.no_export:
        load_env_file(REPO_ROOT / ".env")
        token_name = os.getenv("TABLEAU_TOKEN_NAME", "")
        token_value = os.getenv("TABLEAU_TOKEN_VALUE", "")
        if not token_name or not token_value:
            print("❌ 缺少 TABLEAU_TOKEN_NAME / TABLEAU_TOKEN_VALUE（见仓库根 .env）")
            return 1
        INPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        ok = export_tableau_csv_to_original(
            view=args.view,
            output_path=INPUT_CSV,
            token_name=token_name,
            token_value=token_value,
            timeout=args.timeout,
            mobile=args.mobile,
        )
        if not ok:
            print("❌ Tableau 导出失败，终止更新（不覆盖现有 Parquet）")
            return 1
        input_file = INPUT_CSV

    return process_order_phone_map(input_file)


if __name__ == "__main__":
    raise SystemExit(main())
