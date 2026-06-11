#!/usr/bin/env python
"""
Cohort 锁单预测回测 — 包装 lock_predict_backtest.py，统一 CLI + Result Contract

通过 subprocess 调用原脚本，从 stdout 解析 MAE/RMSE/MAPE 等指标。

用法:
    python mashang_workspace/research_scripts/lock_predict_backtest_cli.py
    python mashang_workspace/research_scripts/lock_predict_backtest_cli.py --start-date 2026-05-01 --end-date 2026-05-31
    python mashang_workspace/research_scripts/lock_predict_backtest_cli.py --format json
    python mashang_workspace/research_scripts/lock_predict_backtest_cli.py --help
"""

import sys, argparse, json, subprocess, re
from pathlib import Path

_WS_ROOT = Path(__file__).resolve().parents[1]
_PRJ_ROOT = _WS_ROOT.parent
for p in [str(_WS_ROOT), str(_PRJ_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from utils.result_contract import build_partial_contract, save_contract_json, contract_to_terminal


def parse_args():
    p = argparse.ArgumentParser(description="Cohort 锁单预测回测")
    p.add_argument("--start-date", type=str, help="开始日期 (YYYY-MM-DD)")
    p.add_argument("--end-date", type=str, help="结束日期 (YYYY-MM-DD)")
    p.add_argument("--series", type=str, help="忽略（原脚本不支持 series 过滤）")
    p.add_argument("--model", type=str, help="忽略")
    p.add_argument("--city", type=str, help="忽略")
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json", "csv"])
    p.add_argument("--date", type=str, help="忽略"); p.add_argument("--limit", type=int, default=0, help="忽略")
    return p.parse_args()


def _run_legacy(timeout: int = 300) -> subprocess.CompletedProcess:
    """运行原 lock_predict_backtest.py，捕获 stdout/stderr。"""
    script = _WS_ROOT / "scripts" / "lock_predict_backtest.py"
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, timeout=timeout,
    )


def _parse_metrics(stdout: str) -> dict:
    """从原脚本 stdout 中解析 MAE/RMSE/MAPE/n。"""
    mae = rmse = mape = n = None
    # Line: "  周期 ... MAE=xx.x  RMSE=xx.x  MAPE=xx.x%"
    m = re.search(r"MAE=([\d.]+)\s+RMSE=([\d.]+)\s+MAPE=([\d.]+)", stdout)
    if m:
        mae = round(float(m.group(1)), 2)
        rmse = round(float(m.group(2)), 2)
        mape = round(float(m.group(3)), 2)
    m = re.search(r"days=(\d+)", stdout)
    if m:
        n = int(m.group(1))
    return {"mae": mae, "rmse": rmse, "mape": mape, "n": n}


def main():
    args = parse_args()
    cmd = "python " + " ".join(sys.argv)

    out_dir = Path(args.output) if args.output else _WS_ROOT / "outputs" / "tables"

    if args.format != "json":
        print("[Summary]")
        print("  Cohort 锁单预测回测 (三段式成熟度)")
        print()
        print("[Scope]")
        print("  数据源: dataset/assign_data.csv")
        print("  方法: 三段式 (≥30d 原始值, 7-30d lock7/r7, <7d 加权平均)")
        print()

    try:
        result = _run_legacy(timeout=300)
        metrics = _parse_metrics(result.stdout)

        if metrics["mae"] is None:
            # partial success: can't extract metrics
            contract = build_partial_contract(
                script="mashang_workspace/research_scripts/lock_predict_backtest_cli.py", command=cmd,
                scope={"data_source": "dataset/assign_data.csv",
                       "time_window": {},
                       "metric_definition": "cohort forecast backtest based on lead-lock release logic"},
                result={"summary": "回测完成，但无法从原脚本 stdout 解析指标"},
                warnings=["无法解析 MAE/RMSE/MAPE", "请直接运行 lock_predict_backtest.py 获取完整报告"],
                followup_context={"metric": "cohort_forecast_backtest"},
            )
        else:
            m = metrics
            scope = {
                "data_source": "dataset/assign_data.csv",
                "time_window": {},
                "metric_definition": "cohort forecast backtest: MAE/RMSE/MAPE based on lead-lock release",
            }
            result = {
                "summary": f"回测完成: MAE={m['mae']}, RMSE={m['rmse']}, MAPE={m['mape']}%, days={m['n']}",
                "metrics": {"mae": m["mae"], "rmse": m["rmse"], "mape": m["mape"], "case_count": m["n"]},
            }
            contract = build_partial_contract(
                script="mashang_workspace/research_scripts/lock_predict_backtest_cli.py", command=cmd,
                scope=scope, result=result,
                warnings=["预测阶段 age<7d 使用加权平均，可能存在偏差"],
                followup_context={"metric": "cohort_forecast_backtest", "available_dimensions": ["cohort_date"]},
            )
        # Print legacy terminal (only in terminal mode)
        if args.format == "terminal" and hasattr(result, 'stdout'):
            print(result.stdout)

    except subprocess.TimeoutExpired:
        contract = build_partial_contract(
            script="mashang_workspace/research_scripts/lock_predict_backtest_cli.py", command=cmd,
            scope={"data_source": "dataset/assign_data.csv"},
            result={"summary": "原脚本执行超时"},
            warnings=["原脚本执行超时 (300s)，请直接运行 lock_predict_backtest.py"],
            followup_context={"metric": "cohort_forecast_backtest"},
        )
    except Exception as e:
        contract = build_partial_contract(
            script="mashang_workspace/research_scripts/lock_predict_backtest_cli.py", command=cmd,
            scope={"data_source": "dataset/assign_data.csv"},
            result={"summary": "执行异常"},
            warnings=[f"异常: {e}"],
            followup_context={"metric": "cohort_forecast_backtest"},
        )

    if args.format == "json":
        if args.output:
            save_contract_json(contract, out_dir / "lock_predict_backtest.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
        return

    print()
    print("[Output]")
    html_path = out_dir / "lock_predict_backtest.html"
    print(f"  HTML: {html_path}")


if __name__ == "__main__":
    main()
