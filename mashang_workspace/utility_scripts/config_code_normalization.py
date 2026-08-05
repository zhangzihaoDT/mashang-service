#!/usr/bin/env python
"""
config_code_normalization.py — 配置 value_code 归一化工具

基于 config_attribute.parquet 的 value_code 列（Tableau 视图新增的配置 code），
对配置显示名做统一：同一 (Attribute, value_code) 下的多个显示名视为同一配置，
输出规范映射（canonical name = 出现最多的显示名），并可输出归一化后的配置表。

背景:
    value_code 是配置的唯一稳定标识。示例: 内饰 IN2-ASF 同时显示为"大地橘色"/"橙黑色"，
    实为同一内饰颜色配置；IN1-ASH 同时显示为"深色内饰（麂皮）"/"大地象灰 深"。
    通过 value_code 可统一这些显示名差异。

用法:
    python utility_scripts/config_code_normalization.py                 # 终端输出归一化映射
    python utility_scripts/config_code_normalization.py --format json   # JSON
    python utility_scripts/config_code_normalization.py --format csv    # CSV 映射表
"""

import sys, json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd

CONFIG_PARQUET = REPO_ROOT / "dataset" / "config_attribute.parquet"


def build_mapping(config_df):
    """从配置表构建 (Attribute, value_code) -> 显示名列表 + 规范名。"""
    coded = config_df[config_df["value_code"].notna()].copy()
    coded["value_code"] = coded["value_code"].astype(str).str.strip()
    coded["value"] = coded["value"].astype(str).str.strip()
    coded = coded[coded["value_code"].ne("") & coded["value"].ne("")]

    items = []
    for (attr, code), g in coded.groupby(["Attribute", "value_code"]):
        counts = g["value"].value_counts()
        names = list(counts.index)
        canonical = counts.idxmax()
        items.append({
            "attribute": str(attr),
            "value_code": str(code),
            "display_names": names,
            "display_count": int(len(counts)),
            "canonical_name": str(canonical),
            "row_count": int(len(g)),
            "order_count": int(g["Order Number"].nunique()),
            "need_unify": len(counts) > 1,
        })
    df = pd.DataFrame(items).sort_values(["attribute", "value_code"]).reset_index(drop=True)
    return df


def main():
    import argparse
    p = argparse.ArgumentParser(description="配置 value_code 归一化")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json", "csv"])
    p.add_argument("--output", type=str, help="CSV/JSON 输出路径")
    args = p.parse_args()

    config_df = pd.read_parquet(str(CONFIG_PARQUET))
    mapping = build_mapping(config_df)

    if args.format == "json":
        out = {
            "total_codes": len(mapping),
            "need_unify_codes": int(mapping["need_unify"].sum()),
            "coded_rows": int(config_df["value_code"].notna().sum()),
            "mapping": mapping.to_dict(orient="records"),
        }
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  JSON: {args.output}")
        else:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if args.format == "csv":
        out = mapping[["attribute", "value_code", "canonical_name", "display_names", "need_unify"]]
        out["display_names"] = out["display_names"].apply(lambda x: ";".join(x))
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            out.to_csv(args.output, index=False)
            print(f"  CSV: {args.output}")
        else:
            print(out.to_csv(index=False))
        return

    # terminal
    total_codes = len(mapping)
    need = mapping[mapping["need_unify"]]
    print(f"value_code 归一化映射（共 {total_codes} 个 code，{len(need)} 个存在多显示名需统一）")
    print(f"带 value_code 的行数: {config_df['value_code'].notna().sum():,} / {len(config_df):,}")
    print("=" * 80)
    for _, r in mapping.iterrows():
        names = "; ".join(r["display_names"])
        flag = " ⚠ 多显示名" if r["need_unify"] else ""
        print(f"  {r['attribute']:<8} {r['value_code']:<12} → {r['canonical_name']}{flag}")
        if r["need_unify"]:
            print(f"            别名: {names}")


if __name__ == "__main__":
    main()
