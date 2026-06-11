#!/usr/bin/env python
"""
Cohort 预测锁单分析 — 基于成熟度曲线

用法:
    python scripts/cohort_forecast.py                                            # 默认近30天
    python scripts/cohort_forecast.py --start-date 2026-05-01 --end-date 2026-06-01
    python scripts/cohort_forecast.py --format csv --output outputs/tables/
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
from utils.result_contract import build_partial_contract, build_success_contract, save_contract_json, contract_to_terminal

ASSIGN_CSV = REPO_ROOT / "dataset" / "assign_data.csv"

def parse_args():
    p = argparse.ArgumentParser(description="Cohort 预测锁单分析")
    p.add_argument("--start-date", type=str, help="开始日期 (YYYY-MM-DD，默认近30天)")
    p.add_argument("--end-date", type=str, help="结束日期 (YYYY-MM-DD，默认今天)")
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "csv", "json"])
    p.add_argument("--date", type=str, help="忽略"); p.add_argument("--series", type=str, help="暂不支持")
    p.add_argument("--model", type=str, help="忽略"); p.add_argument("--city", type=str, help="忽略")
    p.add_argument("--limit", type=int, default=0, help="忽略")
    return p.parse_args()

def main():
    args = parse_args()
    cmd = "python " + " ".join(sys.argv)
    today = datetime.now()
    start = args.start_date or (today - timedelta(days=30)).strftime("%Y-%m-%d")
    end = args.end_date or today.strftime("%Y-%m-%d")

    from operators.mature_lock_prediction import run_mature_lock_prediction_operator
    from operators.assign_conversion import _parse_cn_date

    df = pd.read_csv(str(ASSIGN_CSV))
    df["_date"] = _parse_cn_date(df["Assign Time 年/月/日"])
    df = df[df["_date"].notna()].sort_values("_date").reset_index(drop=True)

    scope = {
        "data_source": str(ASSIGN_CSV),
        "time_window": {"type": "range", "start_date": start, "end_date": end},
        "filters": {"series": None},
        "metric_definition": "三段式: age>=30d 原始值, 7-30d lock7/r7, <7d 加权平均",
    }

    from operators import run_registered_operator
    plan = {"time": {"start": start, "end": end}, "filters": []}
    try:
        op_result = run_registered_operator(plan=plan, user_query="预测锁单数", query_tool=None)
        result_data = {"summary": f"Cohort 预测锁单: {start} ~ {end}", "metrics": {}}
        if isinstance(op_result, dict):
            for k, v in op_result.items():
                if isinstance(v, (int, float)):
                    result_data["metrics"][k] = v
        warnings = []
        if not op_result:
            warnings.append("预测算子返回空结果，请使用 python scripts/lock_predict_backtest.py")
        contract = build_partial_contract(
            script="scripts/cohort_forecast.py", command=cmd, scope=scope,
            result=result_data, warnings=warnings,
            followup_context={"metric": "lock_forecast", "start_date": start, "end_date": end},
        )
    except Exception as e:
        contract = build_partial_contract(
            script="scripts/cohort_forecast.py", command=cmd, scope=scope,
            result={"summary": "预测算子执行异常"}, warnings=[f"降级到 lock_predict_backtest.py: {e}"],
            followup_context={"metric": "lock_forecast", "start_date": start, "end_date": end},
        )

    out_dir = Path(args.output) if args.output else REPO_ROOT / "outputs" / "tables"
    artifacts = {}
    if args.format == "csv" or args.output:
        out_dir.mkdir(parents=True, exist_ok=True)
        artifacts["csv"] = str(out_dir / f"{start}_cohort_forecast.csv")
    contract["artifacts"] = artifacts

    if args.format == "json":
        if args.output:
            save_contract_json(contract, out_dir / f"{start}_cohort_forecast.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(contract_to_terminal(contract))

if __name__ == "__main__":
    main()
