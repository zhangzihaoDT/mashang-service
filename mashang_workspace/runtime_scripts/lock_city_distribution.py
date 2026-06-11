#!/usr/bin/env python
"""
按城市/大区拆分锁单分布

用法:
    python scripts/lock_city_distribution.py                                   # 昨天城市分布
    python scripts/lock_city_distribution.py --date 2026-06-01
    python scripts/lock_city_distribution.py --series LS8 --limit 5
    python scripts/lock_city_distribution.py --by-region
    python scripts/lock_city_distribution.py --format csv --output outputs/tables/
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

def parse_args():
    p = argparse.ArgumentParser(description="按城市/大区拆分锁单分布")
    p.add_argument("--date", type=str, help="单日查询 (YYYY-MM-DD)")
    p.add_argument("--start-date", type=str, help="开始日期 (YYYY-MM-DD)")
    p.add_argument("--end-date", type=str, help="结束日期 (YYYY-MM-DD)")
    p.add_argument("--series", type=str, help="车系过滤")
    p.add_argument("--model", type=str, help="具体车型过滤")
    p.add_argument("--city", type=str, help="城市过滤")
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "csv", "json"])
    p.add_argument("--limit", type=int, default=10, help="返回 TopN (默认 10)")
    p.add_argument("--by-region", action="store_true", help="按大区分组")
    return p.parse_args()

def resolve_time_range(args):
    if args.date:
        d = pd.Timestamp(args.date)
        return d, d + timedelta(days=1), args.date, "date"
    if args.start_date and args.end_date:
        s, e = pd.Timestamp(args.start_date), pd.Timestamp(args.end_date)
        return s, e, f"{args.start_date}~{args.end_date}", "range"
    yesterday = datetime.now() - timedelta(days=1)
    d = pd.Timestamp(yesterday.date())
    return d, d + timedelta(days=1), yesterday.strftime("%Y-%m-%d"), "date"

def main():
    args = parse_args()
    t_start, t_end, t_label, tw_type = resolve_time_range(args)

    df = pd.read_parquet(str(ORDER_PARQUET))
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = df[df["lock_time"].notna()].copy()
    mask = (df["lock_time"] >= t_start) & (df["lock_time"] < t_end)
    df_f = df[mask]

    if args.series: df_f = df_f[df_f["series"] == args.series]
    if args.model: df_f = df_f[df_f["product_name"].str.contains(args.model, na=False)]
    if args.city: df_f = df_f[df_f["license_city"] == args.city]

    group_by = "parent_region_name" if args.by_region else "license_city"
    group_label = "大区" if args.by_region else "城市"
    grouped = df_f.groupby(group_by)["order_number"].nunique().sort_values(ascending=False)
    total = int(grouped.sum())
    top = grouped.head(args.limit)
    cmd = "python " + " ".join(sys.argv)

    items = []
    for name, count in top.items():
        items.append({"value": str(name), "metrics": {"lock_count": int(count), "share": round(count / total, 4)}})

    time_window = {"type": tw_type}
    if tw_type == "date":
        time_window["date"] = t_label; time_window["start_date"] = t_label; time_window["end_date"] = t_label
    else:
        time_window["start_date"] = args.start_date; time_window["end_date"] = args.end_date

    scope = {
        "data_source": str(ORDER_PARQUET),
        "time_window": time_window,
        "filters": {"series": args.series, "model": args.model, "city": args.city},
        "metric_definition": f"lock_count = COUNTD(order_number), grouped by {group_by}",
    }
    result = {
        "summary": f"{t_label} 锁单数 (按{group_label}): {total}",
        "metrics": {"total_lock_count": total},
        "dimensions": [{"name": group_by, "items": items}],
        "tables": [{"name": "lock_by_city", "columns": [group_by, "lock_count", "share"],
                     "rows": [{group_by: i["value"], "lock_count": i["metrics"]["lock_count"], "share": i["metrics"]["share"]} for i in items]}],
    }
    artifacts = {}
    out_dir = Path(args.output) if args.output else REPO_ROOT / "outputs" / "tables"
    if args.format == "csv" or (args.output and args.format == "terminal"):
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{t_label}_lock_by_{group_label}.csv"
        grouped.reset_index().to_csv(out_dir / fname, index=False)
        artifacts["csv"] = str(out_dir / fname)

    top_entities = [{"field": group_by, "value": str(v), "metrics": {"lock_count": int(c)}}
                    for v, c in top.head(5).items()]
    ctx = {"metric": "lock_count", "group_by": group_by,
           "available_dimensions": ["series", "product_name", "license_city", "store_city", "parent_region_name"],
           "top_entities": top_entities}
    if tw_type == "date": ctx["date"] = t_label
    else: ctx.update({"start_date": args.start_date, "end_date": args.end_date})
    if args.series: ctx["series"] = args.series

    contract = build_success_contract(
        script="scripts/lock_city_distribution.py", command=cmd, scope=scope,
        result=result, artifacts=artifacts, followup_context=ctx,
    )

    if args.format == "json":
        if args.output:
            save_contract_json(contract, out_dir / f"{t_label}_lock_by_{group_label}.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(contract_to_terminal(contract))

    return grouped

if __name__ == "__main__":
    main()
