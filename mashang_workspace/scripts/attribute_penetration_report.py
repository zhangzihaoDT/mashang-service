#!/usr/bin/env python
"""
配置渗透率分析 — 选装率/属性分布

用法:
    python scripts/attribute_penetration_report.py                            # 默认分析激光雷达
    python scripts/attribute_penetration_report.py --model "LS8" --attribute "激光雷达"
    python scripts/attribute_penetration_report.py --format csv --output outputs/tables/
"""

import sys, argparse, json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
from datetime import datetime, timedelta
from utils.result_contract import build_success_contract, save_contract_json, contract_to_terminal

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
CONFIG_PARQUET = REPO_ROOT / "dataset" / "config_attribute.parquet"

def parse_args():
    p = argparse.ArgumentParser(description="配置渗透率分析")
    p.add_argument("--date", type=str, help="单日查询")
    p.add_argument("--start-date", type=str, help="开始日期")
    p.add_argument("--end-date", type=str, help="结束日期")
    p.add_argument("--series", type=str, help="车系过滤")
    p.add_argument("--model", type=str, help="具体车型过滤")
    p.add_argument("--city", type=str, help="忽略")
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "csv", "json"])
    p.add_argument("--limit", type=int, default=10, help="TopN 属性值 (默认 10)")
    p.add_argument("--attribute", type=str, default="激光雷达", help="配置属性名称")
    return p.parse_args()

def resolve_time_range(args):
    if args.date:
        d = pd.Timestamp(args.date); return d, d + timedelta(days=1), args.date, "date"
    if args.start_date and args.end_date:
        s, e = pd.Timestamp(args.start_date), pd.Timestamp(args.end_date)
        return s, e, f"{args.start_date}~{args.end_date}", "range"
    yesterday = datetime.now() - timedelta(days=1)
    return (yesterday - timedelta(days=29)), yesterday + timedelta(days=1), "近30天", "range"

def main():
    args = parse_args()
    t_start, t_end, t_label, tw_type = resolve_time_range(args)
    cmd = "python " + " ".join(sys.argv)

    order_df = pd.read_parquet(str(ORDER_PARQUET))
    order_df["lock_time"] = pd.to_datetime(order_df["lock_time"], errors="coerce")
    order_df = order_df[order_df["lock_time"].notna()].copy()
    mask = (order_df["lock_time"] >= t_start) & (order_df["lock_time"] < t_end)
    filtered = order_df[mask]

    if args.series: filtered = filtered[filtered["series"] == args.series]
    if args.model: filtered = filtered[filtered["product_name"].str.contains(args.model, na=False)]

    order_ids = set(filtered["order_number"].dropna().unique())
    total_orders = len(order_ids)

    config_df = pd.read_parquet(str(CONFIG_PARQUET))
    config_in_scope = config_df[config_df["Order Number"].isin(order_ids)]
    attr_filtered = config_in_scope[config_in_scope["Attribute"].str.contains(args.attribute, na=False)]

    value_counts = attr_filtered["value"].value_counts().head(args.limit)
    penetrated_orders = attr_filtered["Order Number"].nunique()
    penetration_rate = round(penetrated_orders / total_orders * 100, 1) if total_orders else 0

    items = []
    dim_items = []
    for val, cnt in value_counts.items():
        pct = round(cnt / total_orders * 100, 1)
        items.append({"value": str(val), "metrics": {"count": int(cnt), "pct": pct}})
        dim_items.append({"value": str(val), "metrics": {"count": int(cnt), "share": round(cnt / total_orders, 4)}})

    time_window = {"type": tw_type}
    if tw_type == "date": time_window["date"] = t_label
    else: time_window.update({"start_date": str(t_start.date()), "end_date": str((t_end - timedelta(days=1)).date())})

    scope = {
        "data_source": f"{ORDER_PARQUET} ⋈ {CONFIG_PARQUET}",
        "time_window": time_window,
        "filters": {"series": args.series, "model": args.model, "attribute": args.attribute},
        "metric_definition": f"{args.attribute} 渗透率 = 含该配置的订单数 / 总订单数",
    }
    result = {
        "summary": f"{args.attribute} 渗透率: {penetration_rate}% ({penetrated_orders}/{total_orders})",
        "metrics": {"total_orders": total_orders, "penetrated_orders": penetrated_orders, "penetration_rate_pct": penetration_rate},
        "dimensions": [{"name": "value", "items": dim_items}],
    }
    artifacts = {}
    out_dir = Path(args.output) if args.output else REPO_ROOT / "outputs" / "tables"
    if args.format == "csv" or (args.output and args.format == "terminal"):
        out_dir.mkdir(parents=True, exist_ok=True)
        value_counts.reset_index().to_csv(out_dir / f"{t_label}_attribute_{args.attribute}.csv", index=False)
        artifacts["csv"] = str(out_dir / f"{t_label}_attribute_{args.attribute}.csv")

    contract = build_success_contract(
        script="scripts/attribute_penetration_report.py", command=cmd, scope=scope,
        result=result, artifacts=artifacts,
        followup_context={"metric": "attribute_penetration", "attribute": args.attribute,
                          "available_dimensions": ["series", "product_name"],
                          "top_entities": [{"field": "value", "value": str(v), "metrics": {"count": int(c)}}
                                           for v, c in value_counts.head(5).items()]},
    )

    if args.format == "json":
        if args.output:
            save_contract_json(contract, out_dir / f"{t_label}_attribute_{args.attribute}.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(contract_to_terminal(contract))

if __name__ == "__main__":
    main()
