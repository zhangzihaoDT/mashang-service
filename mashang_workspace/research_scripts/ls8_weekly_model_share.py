#!/usr/bin/env python3
"""
LS8 上市以来每周分车型锁单数占比走势

用法:
    python research_scripts/ls8_weekly_model_share.py                                   # 终端输出
    python research_scripts/ls8_weekly_model_share.py --format csv --output outputs/tables/
    python research_scripts/ls8_weekly_model_share.py --format json
    python research_scripts/ls8_weekly_model_share.py --limit 5                         # Top5 车型
"""

import sys, argparse, json
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = REPO_ROOT / "mashang_workspace"
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
from utils.result_contract import build_success_contract, save_contract_json, contract_to_terminal

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
SERIES = "LS8"

LAUNCH_DATE = "2026-04-16"


def load_launch_date() -> str:
    try:
        with open(BUSINESS_DEF) as f:
            bd = json.load(f)
        return bd["time_periods"][SERIES]["end"]
    except Exception:
        return LAUNCH_DATE


def simplify_product(name: str) -> str:
    for prefix in ["智己LS8 ", "智己LS8"]:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def parse_args():
    p = argparse.ArgumentParser(description="LS8 上市以来每周分车型锁单数占比走势")
    p.add_argument("--output", type=str, help="输出目录 (默认 outputs/tables/)")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "csv", "json"])
    p.add_argument("--limit", type=int, default=0, help="限制展示车型数 (0=全部)")
    return p.parse_args()


def main():
    args = parse_args()
    launch_date = load_launch_date()
    t_start = pd.Timestamp(launch_date)
    t_end = pd.Timestamp(datetime.now().date()) + pd.Timedelta(days=1)

    df = pd.read_parquet(str(ORDER_PARQUET))
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = df[df["lock_time"].notna()].copy()

    df_ls8 = df[df["series"] == SERIES].copy()
    df_ls8 = df_ls8[(df_ls8["lock_time"] >= t_start) & (df_ls8["lock_time"] < t_end)]

    iso = df_ls8["lock_time"].dt.isocalendar()
    df_ls8["week_year"] = iso["year"].astype(int)
    df_ls8["week_num"] = iso["week"].astype(int)
    df_ls8["week_label"] = df_ls8["week_year"].astype(str) + "-W" + df_ls8["week_num"].astype(str).str.zfill(2)
    df_ls8.sort_values("lock_time", inplace=True)

    weekly_total = df_ls8.groupby("week_label")["order_number"].nunique()
    weekly_model = df_ls8.groupby(["week_label", "product_name"])["order_number"].nunique().reset_index()
    weekly_model.rename(columns={"order_number": "lock_count"}, inplace=True)
    weekly_model["share"] = weekly_model.apply(
        lambda r: round(r["lock_count"] / weekly_total.get(r["week_label"], 1), 4), axis=1
    )
    weekly_model["model_short"] = weekly_model["product_name"].apply(simplify_product)

    all_weeks = sorted(weekly_model["week_label"].unique())
    models_in_order = (
        weekly_model.groupby("product_name")["lock_count"].sum().sort_values(ascending=False).index.tolist()
    )
    if args.limit > 0:
        top_models = models_in_order[:args.limit]
        weekly_model = weekly_model[weekly_model["product_name"].isin(top_models)]
        models_in_order = top_models

    pivot = weekly_model.pivot_table(
        index="week_label", columns="model_short", values="lock_count", aggfunc="sum", fill_value=0
    )
    pivot_share = weekly_model.pivot_table(
        index="week_label", columns="model_short", values="share", aggfunc="sum", fill_value=0
    )
    pivot = pivot.reindex(columns=[simplify_product(m) for m in models_in_order], fill_value=0)
    pivot_share = pivot_share.reindex(columns=[simplify_product(m) for m in models_in_order], fill_value=0)

    total_lock = int(weekly_total.sum())
    week_count = len(all_weeks)

    rows = []
    for week in all_weeks:
        week_total = int(weekly_total.get(week, 0))
        for _, r in weekly_model[weekly_model["week_label"] == week].iterrows():
            rows.append({
                "week": week, "model": r["model_short"],
                "lock_count": int(r["lock_count"]), "share": r["share"],
            })

    scope = {
        "data_source": str(ORDER_PARQUET),
        "time_window": {"start_date": launch_date, "end_date": datetime.now().strftime("%Y-%m-%d"), "type": "since_launch"},
        "filters": {"series": SERIES},
        "metric_definition": "lock_count = COUNTD(order_number) per week per product_name; share = lock_count / weekly_total",
    }
    result = {
        "summary": f"LS8 上市({launch_date})以来共 {week_count} 周，累计锁单 {total_lock} 单",
        "metrics": {"total_lock_count": total_lock, "week_count": week_count},
        "tables": [
            {
                "name": "weekly_lock_count",
                "columns": ["week", "model", "lock_count", "share"],
                "rows": rows,
            },
            {
                "name": "weekly_lock_count_pivot",
                "columns": ["week_label"] + [simplify_product(m) for m in models_in_order],
                "rows": [{"week": idx, **{c: int(v) for c, v in row.items()}} for idx, row in pivot.iterrows()],
            },
            {
                "name": "weekly_share_pivot",
                "columns": ["week_label"] + [simplify_product(m) for m in models_in_order],
                "rows": [{"week": idx, **{c: round(v, 4) for c, v in row.items()}} for idx, row in pivot_share.iterrows()],
            },
        ],
    }

    cmd = "python " + " ".join(sys.argv)
    ctx = {"metric": "lock_count", "series": SERIES, "group_by": "product_name",
           "time_window": {"start_date": launch_date, "end_date": datetime.now().strftime("%Y-%m-%d")},
           "available_dimensions": ["product_name", "license_city"]}

    contract = build_success_contract(
        script="research_scripts/ls8_weekly_model_share.py", command=cmd,
        scope=scope, result=result, followup_context=ctx,
    )

    out_dir = Path(args.output) if args.output else REPO_ROOT / "outputs" / "tables"

    if args.format == "terminal":
        print(contract_to_terminal(contract))
        print()
        print("  [Weekly Lock Count Pivot Table]")
        print(f"  {'Week':<14}", end="")
        for m in pivot.columns:
            print(f"{m:>28}", end="")
        print()
        for idx, row in pivot.iterrows():
            print(f"  {idx:<14}", end="")
            for v in row:
                print(f"{int(v):>28}", end="")
            print()
        print()
        print("  [Weekly Share Pivot Table]")
        print(f"  {'Week':<14}", end="")
        for m in pivot_share.columns:
            print(f"{m:>28}", end="")
        print()
        for idx, row in pivot_share.iterrows():
            print(f"  {idx:<14}", end="")
            for v in row:
                print(f"{v:>28.1%}", end="")
            print()

    elif args.format == "csv":
        out_dir.mkdir(parents=True, exist_ok=True)
        pivot.to_csv(out_dir / "LS8_weekly_lock_count.csv")
        pivot_share.to_csv(out_dir / "LS8_weekly_share.csv")
        contract["artifacts"] = {
            "csv_lock_count": str(out_dir / "LS8_weekly_lock_count.csv"),
            "csv_share": str(out_dir / "LS8_weekly_share.csv"),
        }
        print(contract_to_terminal(contract))

    elif args.format == "json":
        if args.output:
            out_dir.mkdir(parents=True, exist_ok=True)
            save_contract_json(contract, out_dir / "LS8_weekly_model_share.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
