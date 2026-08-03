#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集团订单日报 2.0 解析与数据重组脚本

将「订单日报2.0」Excel 解析为结构化宽表 CSV。支持：
  - 单文件模式：解析单个 Excel → 4 个口径 CSV（企业/重点车型 × 订单/成交）
  - 批量模式（--batch-dir）：解析目录下全部历史 Excel（自动检测新旧两种布局），
    合并为 4 个纵向数据集（叠加所有快照，含「数据日期」列）

Sheet 结构（多行表头）：
  - 企业 (订单)    企业 × 订单口径
  - 重点车型 (订单)  车型 × 订单口径
  - 企业 (成交)    企业 × 开票口径
  - 重点车型 (成交)  车型 × 开票口径

布局差异：
  - 新布局（2026-03 起）：周度日均列=5、每日订单列=10（重点车型）/ 7（企业）
  - 旧布局（2025-12 ~ 2026-02）：周度日均列=8、每日订单列=13（重点车型）/ 10（企业）
  本脚本通过表头标签自动检测，无需硬编码列位置。

用法:
  python mashang_workspace/research_scripts/saic_group_order_daily_parse.py \
      --input <xlsx路径> [--all]
  python mashang_workspace/research_scripts/saic_group_order_daily_parse.py \
      --batch-dir <目录> --output <输出目录> [--all]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = _REPO_ROOT / "mashang_workspace"
_DEFAULT_INPUT = Path("/Users/zihao_/Documents/coding/dataset/original/订单日报2.0.xlsx")
_DEFAULT_OUTPUT = _WS / "outputs" / "tables"

SHEETS = ["企业 (订单)", "重点车型 (订单)", "企业 (成交)", "重点车型 (成交)"]
OUTPUT_FILENAMES = {
    "企业 (订单)": "企业（订单）.csv",
    "重点车型 (订单)": "重点车型（订单）.csv",
    "企业 (成交)": "企业（成交）.csv",
    "重点车型 (成交)": "重点车型（成交）.csv",
}


def _cell(row, i):
    v = row[i]
    return "" if pd.isna(v) else str(v).strip()


def _year_from_month_label(label: str) -> int | None:
    m = re.search(r"(20\d{2})年", str(label))
    return int(m.group(1)) if m else None


def detect_layout(raw: pd.DataFrame) -> dict:
    """从多行表头自动检测列位置（兼容新旧布局）。"""
    r1, r2, r3 = raw.iloc[1], raw.iloc[2], raw.iloc[3]
    ncols = raw.shape[1]

    def find_row1(pred):
        for i in range(ncols):
            if pd.notna(r1[i]) and pred(str(r1[i])):
                return i
        return None

    def find_row3(exact=None, contains=None):
        for i in range(ncols):
            s = _cell(r3, i)
            if exact and s == exact:
                return i
            if contains and contains in s:
                return i
        return None

    metric = "订单" if any(pd.notna(v) and "国内订单" in str(v) for v in r1) else "成交"

    month_label = None
    for i in range(ncols):
        s = _cell(r1, i)
        if "年" in s and "月" in s and "20" in s:
            month_label = s
            break

    mt_col = find_row3(exact="月累计")
    ma_col = find_row3(exact="月日均")
    name_col = mt_col - 1 if mt_col is not None else 0

    d_start = find_row1(lambda s: "每日" in s)
    daily_cols = []
    if d_start is not None:
        for i in range(d_start, ncols):
            if pd.isna(r2[i]):
                break
            daily_cols.append(i)

    weekly_cols = [
        i for i in range(ncols) if re.fullmatch(r"\d+~\d+", _cell(r3, i))
    ]

    after = (daily_cols[-1] + 1) if daily_cols else (d_start or 0)
    nm_mt = nm_ma = None
    for i in range(after, ncols):
        s = _cell(r3, i)
        if s == "月累计" and nm_mt is None:
            nm_mt = i
        elif s == "月日均" and nm_ma is None:
            nm_ma = i

    yoy_col = find_row3(exact="同比")
    mom_col = find_row3(exact="环比")
    overdue_col = find_row3(contains="逾期")

    return {
        "metric": metric,
        "month_label": month_label,
        "name_col": name_col,
        "mt_col": mt_col,
        "ma_col": ma_col,
        "daily_cols": daily_cols,
        "weekly_cols": weekly_cols,
        "nm_mt_col": nm_mt,
        "nm_ma_col": nm_ma,
        "yoy_col": yoy_col,
        "mom_col": mom_col,
        "overdue_col": overdue_col,
    }


def snapshot_date(filepath: Path, month_label: str, daily_cols: list, r2) -> str | None:
    """快照数据日期 = 最后一个每日日期 + 年份。

    年份优先级：文件名中的 YYYYMMDD > 报表月标签年份。
    报表月标签年份可能比每日日期早一年（如 2025年12月 报表的每日日期在 2026 年 1 月）。
    """
    if not daily_cols:
        return None
    last_date = _cell(r2, daily_cols[-1])
    if not last_date or "/" not in last_date:
        return None
    mm, dd = last_date.split("/", 1)

    m_fname = re.search(r"(20\d{2})", filepath.name)
    if m_fname:
        year = int(m_fname.group(1))
    else:
        year = _year_from_month_label(month_label)
    if year is None:
        return None
    return f"{year}-{int(mm):02d}-{int(dd):02d}"


def parse_sheet(raw: pd.DataFrame, filepath: Path | None = None) -> pd.DataFrame:
    lay = detect_layout(raw)
    r2, r3 = raw.iloc[2], raw.iloc[3]

    daily_col_names = []
    for i in lay["daily_cols"]:
        date = _cell(r2, i)
        dow = _cell(r3, i)
        daily_col_names.append(f"每日_{date}_{dow}".rstrip("_"))

    week_col_names = []
    for i in lay["weekly_cols"]:
        label = _cell(r2, i) or f"周度{len(week_col_names) + 1}"
        rng = _cell(r3, i)
        week_col_names.append(f"{label}({rng})" if rng else label)

    cols = ["主体", "月度累计", "月日均"] + week_col_names + daily_col_names

    rows = []
    for i in range(4, raw.shape[0]):
        name = _cell(raw.iloc[i], lay["name_col"])
        if not name or name.startswith("备注"):
            continue
        row = raw.iloc[i]
        core = [name, row[lay["mt_col"]], row[lay["ma_col"]]]
        core += [row[c] for c in lay["weekly_cols"]]
        core += [row[c] for c in lay["daily_cols"]]
        # 跳过纯分区标签行（如「预售期小订」，所有数值为空）
        if all(pd.isna(v) for v in core[1:]):
            continue
        rows.append(core)

    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return df

    if lay["nm_mt_col"] is not None:
        df["下月累计"] = raw.iloc[4:, lay["nm_mt_col"]].reset_index(drop=True).values[: len(df)]
    if lay["nm_ma_col"] is not None:
        df["下月日均"] = raw.iloc[4:, lay["nm_ma_col"]].reset_index(drop=True).values[: len(df)]
    if lay["yoy_col"] is not None:
        df["同比"] = raw.iloc[4:, lay["yoy_col"]].reset_index(drop=True).values[: len(df)]
    if lay["mom_col"] is not None:
        df["环比"] = raw.iloc[4:, lay["mom_col"]].reset_index(drop=True).values[: len(df)]
    if lay["overdue_col"] is not None:
        df["逾期订单(>28天未交付)"] = raw.iloc[4:, lay["overdue_col"]].reset_index(drop=True).values[: len(df)]

    sdate = snapshot_date(filepath, lay["month_label"], lay["daily_cols"], r2) if filepath else None
    if sdate:
        df.insert(0, "数据日期", sdate)
    return df


def process_file(path: Path, include_invoice: bool) -> dict[str, pd.DataFrame]:
    xl = pd.ExcelFile(str(path))
    out = {}
    for sheet in SHEETS:
        if sheet.endswith("(成交)") and not include_invoice:
            continue
        raw = xl.parse(sheet, header=None)
        out[sheet] = parse_sheet(raw, filepath=path)
    return out


def _sheet_cell_map(df: pd.DataFrame) -> dict:
    """快照的每日单元格映射 {(主体, 日期): 值}，用于冗余检测。"""
    daily_cols = [c for c in df.columns if c.startswith("每日_")]
    if "数据日期" not in df.columns or not daily_cols:
        return {}
    cmap = {}
    for _, r in df.iterrows():
        for c in daily_cols:
            if pd.notna(r[c]):
                md = c.split("_")[1]
                m, dd = md.split("/")
                key = (
                    str(r["主体"]),
                    f"{str(r['数据日期'])[:4]}-{int(m):02d}-{int(dd):02d}",
                )
                cmap[key] = r[c]
    return cmap


def _dedup_snapshots(snaps: list[tuple[Path, pd.DataFrame]]) -> tuple[list, list]:
    """去除因新系列补充而冗余的旧系列快照（每日窗口被其他快照完全覆盖）。

    规则：
      - 旧系列文件（无 '-' 分隔）：当其每日窗口被其他快照完全覆盖，且至少一个覆盖者
        属于新系列（'-' 分隔，如 订单日报2.0-0504）时，判定为冗余。
      - 新系列文件：仅当其被其他新系列快照完全覆盖时才判定冗余（避免被旧系列替代）。
    对重叠的冗余快照，优先保留新系列，其次保留数据日期较新者。
    """

    def is_new(i):
        return "-" in snaps[i][0].name

    maps = [_sheet_cell_map(df) for _, df in snaps]
    n = len(snaps)
    redundant = set()
    for i in range(n):
        ci = maps[i]
        if not ci:
            continue
        all_covered = all(any(key in maps[j] for j in range(n) if j != i) for key in ci)
        if not all_covered:
            continue
        covered_by_new = any(
            any(key in maps[j] for j in range(n) if j != i and is_new(j)) for key in ci
        )
        if is_new(i):
            if all(any(key in maps[j] for j in range(n) if j != i and is_new(j)) for key in ci):
                redundant.add(i)
        elif covered_by_new:
            redundant.add(i)

    if not redundant:
        return snaps, []

    old_redundant = [i for i in redundant if not is_new(i)]
    new_redundant = [i for i in redundant if is_new(i)]

    drop = set(old_redundant)
    if new_redundant:
        keep_new = max(
            new_redundant,
            key=lambda i: snaps[i][1]["数据日期"].iloc[0]
            if "数据日期" in snaps[i][1].columns
            else "",
        )
        drop |= set(new_redundant) - {keep_new}

    result = [snaps[i] for i in range(n) if i not in drop]
    return result, [snaps[i][0].name for i in sorted(drop)]


def process_batch(batch_dir: Path, output_dir: Path, include_invoice: bool) -> dict:
    files = sorted(batch_dir.glob("*.xlsx"))
    panels = {s: [] for s in SHEETS}
    per_file = {}
    dedup_log = {}

    for f in files:
        try:
            tables = process_file(f, include_invoice)
        except Exception as e:
            print(f"⚠️ 跳过 {f.name}: {e}")
            continue
        per_file[f.name] = {s: len(t) for s, t in tables.items()}
        for s, df in tables.items():
            if not df.empty:
                panels[s].append((f, df))

    output_files = {}
    for s, snap_list in panels.items():
        fname = OUTPUT_FILENAMES[s]
        if not snap_list:
            continue
        deduped, dropped = _dedup_snapshots(snap_list)
        dedup_log[fname] = dropped
        merged = pd.concat([df for _, df in deduped], axis=0, ignore_index=True, sort=False)
        # 数据日期列前置
        if "数据日期" in merged.columns:
            cols = ["数据日期"] + [c for c in merged.columns if c != "数据日期"]
            merged = merged[cols]
        out_path = output_dir / fname
        merged.to_csv(out_path, index=False, encoding="utf-8-sig")
        output_files[fname] = {
            "rows": len(merged),
            "files": len(deduped),
            "path": str(out_path),
        }

    return {"output_files": output_files, "per_file": per_file, "dedup_log": dedup_log}


def main() -> int:
    parser = argparse.ArgumentParser(description="集团订单日报 2.0 解析与数据重组")
    parser.add_argument("--input", type=str, default=str(_DEFAULT_INPUT), help="单个 Excel 路径")
    parser.add_argument("--batch-dir", type=str, default=None, help="批量处理目录下全部 Excel")
    parser.add_argument("--output", type=str, default=str(_DEFAULT_OUTPUT), help="CSV 输出目录")
    parser.add_argument("--all", action="store_true", help="同时输出成交口径")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.batch_dir:
        batch_dir = Path(args.batch_dir)
        if not batch_dir.is_dir():
            print(f"❌ 目录不存在: {batch_dir}")
            return 1
        res = process_batch(batch_dir, output_dir, args.all)
        print("=" * 70)
        print("集团订单日报 2.0 批量解析完成")
        print("=" * 70)
        for fname, info in res["output_files"].items():
            print(f"[{fname}] {info['rows']} 行（{info['files']} 个快照）")
            print(f"  → {info['path']}")
        print("-" * 70)
        for fname, dropped in res["dedup_log"].items():
            if dropped:
                print(f"⚠️ 去重（{fname}）: 丢弃完全冗余快照 {dropped}")
        print("-" * 70)
        print("各文件解析行数:")
        for fname, sheets in res["per_file"].items():
            detail = ", ".join(f"{s.split()[0]}{s.split()[-1]}:{n}" for s, n in sheets.items())
            print(f"  {fname:<30} {detail}")
        print("=" * 70)
        return 0

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 数据源不存在: {input_path}")
        return 1

    tables = process_file(input_path, args.all)
    print("=" * 70)
    print("集团订单日报 2.0 数据解析")
    print("=" * 70)
    for sheet, df in tables.items():
        fname = OUTPUT_FILENAMES[sheet]
        out_path = output_dir / fname
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"\n[{sheet}] {len(df)} 行")
        print(f"  输出: {out_path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
