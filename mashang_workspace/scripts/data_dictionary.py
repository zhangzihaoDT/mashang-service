#!/usr/bin/env python
"""
数据字典生成 — 扫描目录下的数据文件，输出字段级元信息

用法:
    python scripts/data_dictionary.py                                             # 默认扫描 dataset/
    python scripts/data_dictionary.py --input dataset --output outputs/tables/data_dictionary.csv
    python scripts/data_dictionary.py --format json --output outputs/tables/

说明:
    - 支持 .parquet / .csv / .xlsx / .json 格式
    - 大文件只读取 schema 和前 1000 行样例，避免全量加载
"""

import sys
import argparse
import json
from pathlib import Path

# 确保 mashang_workspace/ 和 mashang-service/ 在 sys.path 中
_WS_DIR = Path(__file__).resolve().parents[1]
_PRJ_DIR = _WS_DIR.parent
for p in [str(_WS_DIR), str(_PRJ_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from utils.paths import PROJECT_ROOT, WORKSPACE_ROOT, OUTPUTS_DIR
    REPO_ROOT = PROJECT_ROOT
    _DEFAULT_OUTPUT = str(OUTPUTS_DIR / "tables")
except ImportError:
    REPO_ROOT = _PRJ_DIR
    _DEFAULT_OUTPUT = str(REPO_ROOT / "outputs" / "tables")

import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(description="数据字典生成")
    parser.add_argument("--input", type=str, default="dataset",
                        help="扫描目录 (默认 dataset)")
    parser.add_argument("--output", type=str, default=_DEFAULT_OUTPUT,
                        help=f"输出目录 (默认 {_DEFAULT_OUTPUT})")
    parser.add_argument("--format", type=str, default="terminal", choices=["terminal", "csv", "json"],
                        help="输出格式 (默认 terminal)")
    parser.add_argument("--max-sample", type=int, default=1000,
                        help="大文件最多读取的行数 (默认 1000)")
    return parser.parse_args()


SUPPORTED_EXTS = {".parquet", ".csv", ".xlsx", ".json"}


def _safe_read(path: Path, ext: str, max_sample: int) -> pd.DataFrame | None:
    """安全读取数据文件（只读 schema + 前 max_sample 行）。"""
    try:
        if ext == ".parquet":
            pf = pd.read_parquet(str(path))
            rows = len(pf)
            if rows > max_sample:
                cols = pf.columns.tolist()
                dtypes = pf.dtypes.to_dict()
                sample = pf.head(max_sample)
                # 只保留 schema 信息
                sample = sample.iloc[:0]  # empty but with columns
                for c in cols:
                    sample[c] = sample[c].astype(dtypes.get(c, "object"))
                return sample
            return pf
        elif ext == ".csv":
            return pd.read_csv(str(path), nrows=max_sample)
        elif ext == ".xlsx":
            return pd.read_excel(str(path), nrows=max_sample)
        elif ext == ".json":
            return pd.read_json(str(path), lines=True, nrows=max_sample)
    except Exception as e:
        print(f"  [Warn] 读取失败 {path.name}: {e}", file=sys.stderr)
        return None


def build_dictionary(input_dir: Path, max_sample: int) -> list[dict]:
    """扫描目录并构建数据字典条目列表。"""
    records = []
    if not input_dir.exists():
        print(f"[Error] 目录不存在: {input_dir}", file=sys.stderr)
        return records

    data_files = sorted(
        f for f in input_dir.rglob("*")
        if f.suffix.lower() in SUPPORTED_EXTS
        and not f.name.startswith(".")
        and "__pycache__" not in f.parts
    )

    for fpath in data_files:
        ext = fpath.suffix.lower()
        print(f"  扫描: {fpath.relative_to(input_dir.parent)} ...", file=sys.stderr)
        df = _safe_read(fpath, ext, max_sample)
        if df is None:
            continue

        row_count = len(df)  # may be truncated to max_sample
        for col in df.columns:
            series = df[col]
            non_null = int(series.notna().sum())
            null_count = int(series.isna().sum())
            dtype_str = str(series.dtype)
            sample_vals = series.dropna().unique()[:5].tolist()
            sample_str = ", ".join(str(v) for v in sample_vals) if sample_vals else ""

            records.append({
                "file_path": str(fpath),
                "file_name": fpath.name,
                "file_type": ext.lstrip("."),
                "row_count": row_count,
                "column_name": col,
                "dtype": dtype_str,
                "non_null_count": non_null,
                "null_count": null_count,
                "sample_values": sample_str,
            })
    return records


def main():
    args = parse_args()
    input_dir = (REPO_ROOT / args.input).resolve()
    out_dir = Path(args.output)
    if not out_dir.is_absolute():
        out_dir = (WORKSPACE_ROOT if 'WORKSPACE_ROOT' in dir() else REPO_ROOT / args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"数据字典生成", file=sys.stderr)
    print(f"  扫描目录: {input_dir}", file=sys.stderr)
    print(f"  文件格式: {', '.join(SUPPORTED_EXTS)}", file=sys.stderr)
    print(f"  最大采样: {args.max_sample} 行/文件", file=sys.stderr)
    print(file=sys.stderr)

    records = build_dictionary(input_dir, args.max_sample)

    if not records:
        print(f"[Warning] 未找到支持的数据文件", file=sys.stderr)
        return

    result_df = pd.DataFrame(records)

    # ── 输出 ──
    print(f"\n{'='*80}")
    print(f"数据字典生成完成: {len(records)} 条字段记录, {result_df['file_name'].nunique()} 个文件")
    print(f"{'='*80}")

    if args.format == "terminal":
        for fname in sorted(result_df["file_name"].unique()):
            sub = result_df[result_df["file_name"] == fname]
            print(f"\n--- {fname} ({sub.iloc[0]['file_type']}, {sub.iloc[0]['row_count']} rows) ---")
            print(f"  {'字段名':25s} {'类型':12s} {'非空':>6s} {'空值':>6s}  {'样例'}")
            print(f"  {'-'*25} {'-'*12} {'-'*6} {'-'*6}  {'-'*20}")
            for _, row in sub.iterrows():
                sample = row["sample_values"][:30] if row["sample_values"] else "-"
                print(f"  {row['column_name']:25s} {row['dtype']:12s} {row['non_null_count']:6d} {row['null_count']:6d}  {sample}")

    if args.format in ("csv", "terminal"):
        csv_path = out_dir / "data_dictionary.csv"
        result_df.to_csv(csv_path, index=False)
        print(f"\n[Output] CSV: {csv_path} ({len(records)} records)")

    if args.format == "json":
        json_path = out_dir / "data_dictionary.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print(f"\n[Output] JSON: {json_path} ({len(records)} records)")

    return records


if __name__ == "__main__":
    main()
