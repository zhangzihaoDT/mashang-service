#!/usr/bin/env python
"""
下发线索转化率分析

用法:
    python scripts/assign_conversion_analysis.py                               # 默认近7天
    python scripts/assign_conversion_analysis.py --start-date 2026-06-01 --end-date 2026-06-10
    python scripts/assign_conversion_analysis.py --format csv --output outputs/tables/
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
from utils.paths import ensure_shared_on_path
ensure_shared_on_path()
from utils.result_contract import build_success_contract, save_contract_json, contract_to_terminal

ASSIGN_CSV = REPO_ROOT / "dataset" / "assign_data.csv"

def parse_args():
    p = argparse.ArgumentParser(description="下发线索转化率分析")
    p.add_argument("--date", type=str, help="单日查询 (YYYY-MM-DD)")
    p.add_argument("--start-date", type=str, help="开始日期 (YYYY-MM-DD)")
    p.add_argument("--end-date", type=str, help="结束日期 (YYYY-MM-DD)")
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "csv", "json"])
    p.add_argument("--series", type=str, help="忽略"); p.add_argument("--model", type=str, help="忽略")
    p.add_argument("--city", type=str, help="忽略"); p.add_argument("--limit", type=int, default=10, help="忽略")
    return p.parse_args()

def resolve_time_range(args):
    if args.date:
        d = pd.Timestamp(args.date); return d, d + timedelta(days=1), args.date, "date"
    if args.start_date and args.end_date:
        s, e = pd.Timestamp(args.start_date), pd.Timestamp(args.end_date)
        return s, e, f"{args.start_date}~{args.end_date}", "range"
    yesterday = datetime.now() - timedelta(days=1)
    return (yesterday - timedelta(days=6)), yesterday + timedelta(days=1), "近7天", "range"

def main():
    args = parse_args()
    t_start, t_end, t_label, tw_type = resolve_time_range(args)
    cmd = "python " + " ".join(sys.argv)

    df = pd.read_csv(str(ASSIGN_CSV))
    from operators.assign_conversion import _parse_cn_date
    df["_date"] = _parse_cn_date(df["Assign Time 年/月/日"])
    df = df[df["_date"].notna()].copy()
    mask = (df["_date"] >= t_start) & (df["_date"] < t_end)
    w = df[mask]

    total_leads = int(w["下发线索数"].sum())
    store_leads = int(w["下发线索数 (门店)"].sum())
    test_drive = int(w["下发线索当日试驾数"].sum())
    lock_7d = int(w["下发线索 7 日锁单数"].sum())
    lock_30d = int(w["下发线索 30 日锁单数"].sum())

    store_ratio = round(store_leads / total_leads * 100, 1) if total_leads else 0
    drive_rate = round(test_drive / total_leads * 100, 1) if total_leads else 0
    lock7_rate = round(lock_7d / total_leads * 100, 1) if total_leads else 0
    lock30_rate = round(lock_30d / total_leads * 100, 1) if total_leads else 0

    scope = {
        "data_source": str(ASSIGN_CSV),
        "time_window": {"type": tw_type, "start_date": str(t_start.date()), "end_date": str((t_end - timedelta(days=1)).date())},
        "filters": {},
        "metric_definition": "下发线索 → 试驾/7日锁单/30日锁单",
    }
    result = {
        "summary": f"{t_label} 下发线索转化率",
        "metrics": {
            "total_leads": total_leads, "store_ratio_pct": store_ratio,
            "drive_rate_pct": drive_rate, "lock7_rate_pct": lock7_rate, "lock30_rate_pct": lock30_rate,
        },
    }
    artifacts = {}
    out_dir = Path(args.output) if args.output else REPO_ROOT / "outputs" / "tables"
    if args.format == "csv" or (args.output and args.format == "terminal"):
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{t_label}_assign_conversion.csv"
        pd.DataFrame([{"time": t_label, "total_leads": total_leads, "store_ratio_pct": store_ratio,
                       "drive_rate_pct": drive_rate, "lock7_rate_pct": lock7_rate, "lock30_rate_pct": lock30_rate}]
        ).to_csv(out_dir / fname, index=False)
        artifacts["csv"] = str(out_dir / fname)

    contract = build_success_contract(
        script="scripts/assign_conversion_analysis.py", command=cmd, scope=scope,
        result=result, artifacts=artifacts,
        followup_context={"metric": "assign_conversion", "available_dimensions": ["渠道", "门店"]},
    )

    if args.format == "json":
        if args.output:
            save_contract_json(contract, out_dir / f"{t_label}_assign_conversion.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(contract_to_terminal(contract))

if __name__ == "__main__":
    main()
