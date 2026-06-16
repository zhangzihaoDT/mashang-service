#!/usr/bin/env python
"""
Cohort 锁单预测回测 — 三段式成熟度模型

通过 assign_data.csv 的历史线索数据，使用三段式成熟度模型预测 30 日锁单转化，
与真实值对比计算 MAE/RMSE/MAPE，生成 HTML 回测报告。

用法:
    python research_scripts/lock_predict_backtest.py
    python research_scripts/lock_predict_backtest.py --format json
    python research_scripts/lock_predict_backtest.py --format terminal
"""

import sys, argparse, json
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))
_RUNTIME_ROOT = REPO_ROOT / "mashang_runtime"
if str(_RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_ROOT))

from operators.mature_lock_prediction import run_mature_lock_prediction_operator
from operators.assign_conversion import _parse_cn_date
from utils.result_contract import build_partial_contract, save_contract_json

ASSIGN_CSV = REPO_ROOT / "dataset" / "assign_data.csv"
OUTPUT_HTML = _WS_ROOT / "outputs" / "reports" / "lock_predict_backtest.html"
PRED_AGE = 7

BRAND = {
    "pred": "#174A7C", "actual": "#D79A36", "daily": "#7ECDEB",
    "ratio": "#D79A36", "accent": "#06213D", "bg": "#FFF9EF",
}
BLUE = "\033[38;2;23;74;124m"
DEEP = "\033[38;2;6;33;61m"
CYAN = "\033[38;2;126;205;235m"
GOLD = "\033[38;2;215;154;54m"
MUTED = "\033[38;2;107;124;143m"
BOLD = "\033[1m"
RST = "\033[0m"


def _b(t): return f"{BOLD}{t}{RST}"
def _blue(t): return f"{BLUE}{t}{RST}"
def _deep(t): return f"{DEEP}{t}{RST}"
def _gold(t): return f"{GOLD}{t}{RST}"
def _muted(t): return f"{MUTED}{t}{RST}"
def _ruler(c="━", w=64): return f"{CYAN}{c*w}{RST}"


def parse_args():
    p = argparse.ArgumentParser(description="Cohort 锁单预测回测 (三段式成熟度)")
    p.add_argument("--format", default="terminal", choices=["terminal", "json"])
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--start-date", type=str, help="忽略")
    p.add_argument("--end-date", type=str, help="忽略")
    p.add_argument("--series", type=str, help="忽略")
    p.add_argument("--model", type=str, help="忽略")
    p.add_argument("--city", type=str, help="忽略")
    p.add_argument("--date", type=str, help="忽略")
    p.add_argument("--limit", type=int, default=0, help="忽略")
    return p.parse_args()


def load_data():
    df = pd.read_csv(str(ASSIGN_CSV))
    df["_date"] = _parse_cn_date(df["Assign Time 年/月/日"])
    df = df[df["_date"].notna()].sort_values("_date").reset_index(drop=True)
    n_fn = lambda c: pd.to_numeric(c.astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
    df["_leads"] = n_fn(df["下发线索数"])
    df["_lock0"] = n_fn(df["下发线索当日锁单数 (门店)"])
    df["_lock7"] = n_fn(df["下发线索 7 日锁单数"])
    df["_lock30"] = n_fn(df["下发线索 30 日锁单数"])
    return df


def build_baseline(df, cutoff):
    mature = df[df["_date"] <= cutoff - pd.Timedelta(days=30)]
    r0 = float(mature["_lock0"].sum()) / float(mature["_lock30"].sum())
    r7 = float(mature["_lock7"].sum()) / float(mature["_lock30"].sum())
    avg = float(mature["_lock30"].sum()) / float(mature["_leads"].sum())
    return r0, r7, avg


def run_prediction(df, bt_start, cutoff):
    results = []
    cohort_min = df[df["_date"] >= bt_start]["_date"].min()
    for _, row in df.iterrows():
        d = row["_date"]
        if d < cohort_min or d >= cutoff:
            continue
        leads, lock0, lock7, lock30 = (float(row[c]) for c in ["_leads", "_lock0", "_lock7", "_lock30"])
        snapshot = min(d + pd.Timedelta(days=PRED_AGE), cutoff)
        age = (snapshot - d).days
        mature = df[df["_date"] <= snapshot - pd.Timedelta(days=30)]
        has_mature = (not mature.empty) and (mature["_lock30"].sum() > 0)

        if age >= 30:
            pred, stage = lock30, "actual"
        elif age >= 7:
            if has_mature:
                r7_r = float(mature["_lock7"].sum()) / float(mature["_lock30"].sum())
                pred = lock7 / r7_r if r7_r > 0 else lock30
            else:
                pred = lock30
            stage = "lock7_proj"
        else:
            if has_mature:
                avg_r = float(mature["_lock30"].sum()) / float(mature["_leads"].sum())
                r0_r = float(mature["_lock0"].sum()) / float(mature["_lock30"].sum())
                est_avg = leads * avg_r
                pred = (0.5 * est_avg + 0.5 * lock0 / r0_r) if (r0_r > 0 and lock0 > 0) else est_avg
            else:
                pred = lock30
            stage = "weighted_avg"

        results.append({"date": d, "下发线索数": int(leads),
                         "cohort_pred_30_lock": round(pred, 1),
                         "cohort_actual_30_lock": int(lock30), "预测阶段": stage})
    return pd.DataFrame(results)


def compute_metrics(rd, bt_start, bt_end):
    rd_bt = rd[(rd["date"] >= bt_start) & (rd["date"] <= bt_end)].copy()
    rd_bt["cohort_error"] = rd_bt["cohort_pred_30_lock"] - rd_bt["cohort_actual_30_lock"]
    rd_bt["cohort_ape"] = rd_bt.apply(
        lambda r: abs(r["cohort_error"]) / r["cohort_actual_30_lock"] * 100 if r["cohort_actual_30_lock"] > 0 else np.nan, axis=1)
    n = len(rd_bt)
    mae = float(rd_bt["cohort_error"].abs().mean())
    rmse = float(np.sqrt((rd_bt["cohort_error"] ** 2).mean()))
    mape = float(rd_bt["cohort_ape"].dropna().mean())
    return n, mae, rmse, mape, rd_bt


def generate_html(rd, bt_start, bt_end, cutoff, n_bt, mae_bt, rmse_bt, mape_bt, r0, r7, avg):
    ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
    order_df = pd.read_parquet(str(ORDER_PARQUET))
    order_df["lock_date"] = pd.to_datetime(order_df["lock_time"], errors="coerce").dt.normalize()
    daily_lock = order_df[order_df["lock_date"].notna()].groupby("lock_date")["order_number"].nunique().reset_index()
    daily_lock.columns = ["date", "daily_lock_count"]
    daily_lock["date"] = pd.to_datetime(daily_lock["date"])

    rd_html = rd.copy()
    rd_html["cohort_error"] = rd_html["cohort_pred_30_lock"] - rd_html["cohort_actual_30_lock"]
    rd_html = rd_html.merge(daily_lock, on="date", how="left")
    rd_html["daily_lock_count"] = rd_html["daily_lock_count"].fillna(0).astype(int)
    rd_html["pred_actual_ratio"] = rd_html.apply(
        lambda r: r["daily_lock_count"] / r["cohort_pred_30_lock"] if r["cohort_pred_30_lock"] > 0 else np.nan, axis=1)

    series_json = json.dumps({
        "dates": rd_html["date"].dt.strftime("%Y-%m-%d").tolist(),
        "pred": [float(v) for v in rd_html["cohort_pred_30_lock"]],
        "actual": [int(v) for v in rd_html["cohort_actual_30_lock"]],
        "daily": [int(v) for v in rd_html["daily_lock_count"]],
        "error": [float(v) for v in rd_html["daily_lock_count"] - rd_html["cohort_pred_30_lock"]],
        "ratio": [float(v) if not np.isnan(v) else None for v in rd_html["pred_actual_ratio"]],
    })

    table_rows = ""
    last30 = rd_html.tail(30).iloc[::-1]
    total_pred = last30["cohort_pred_30_lock"].sum()
    total_daily = last30["daily_lock_count"].sum()
    overall_ratio = total_daily / total_pred * 100 if total_pred > 0 else float("nan")
    overall_ratio_str = f"{overall_ratio:.1f}%" if not np.isnan(overall_ratio) else "N/A"
    ratio_style_total = ' style="background:rgba(215,154,54,.12);font-weight:600"' if (not np.isnan(overall_ratio) and overall_ratio < 80) else ""

    for _, r in last30.iterrows():
        ratio_val = r["daily_lock_count"] / r["cohort_pred_30_lock"] * 100 if r["cohort_pred_30_lock"] > 0 else float("nan")
        ratio_str = f"{ratio_val:.1f}%" if not np.isnan(ratio_val) else "N/A"
        ratio_style = ' style="background:rgba(215,154,54,.12);font-weight:600"' if (not np.isnan(ratio_val) and ratio_val < 80) else ""
        stage_label = {"actual": "实际值", "lock7_proj": "7日投影", "weighted_avg": "加权平均"}.get(r["预测阶段"], r["预测阶段"])
        table_rows += f"""  <tr>
    <td>{r['date'].strftime('%Y-%m-%d')}</td>
    <td>{r['下发线索数']:,.0f}</td>
    <td>{r['cohort_pred_30_lock']:.1f}</td>
    <td>{r['cohort_actual_30_lock']:,}</td>
    <td>{r['daily_lock_count']:,}</td>
    <td{ratio_style}>{ratio_str}</td>
    <td>{stage_label}</td>
  </tr>"""

    table_rows += f"""  <tr style="background:var(--light);font-weight:600">
    <td>合计</td>
    <td>{last30['下发线索数'].sum():,}</td>
    <td>{total_pred:.1f}</td>
    <td>{last30['cohort_actual_30_lock'].sum():,}</td>
    <td>{total_daily:,}</td>
    <td{ratio_style_total}>{overall_ratio_str}</td>
    <td></td>
  </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cohort 锁单预测 — 回测报告</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root {{ --blue: #174A7C; --deep: #06213D; --cyan: #7ECDEB; --light: #DDEFF8; --cream: #FFF9EF; --gold: #D79A36; --text: #1F2D3D; --muted: #6B7C8F; --card: #FFFFFF; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: var(--cream); color: var(--text); line-height: 1.6; }}
.header {{ background: linear-gradient(135deg, var(--deep), var(--blue)); color: #fff; padding: 32px 24px 24px; text-align: center; }}
.header h1 {{ font-size: 24px; font-weight: 700; }}
.header p {{ font-size: 13px; opacity: .75; margin-top: 6px; }}
.stats {{ display: flex; gap: 12px; padding: 20px 24px; flex-wrap: wrap; }}
.stat-card {{ flex: 1; min-width: 110px; background: var(--card); border-radius: 12px; padding: 16px 14px; box-shadow: 0 1px 4px rgba(6,33,61,.06); text-align: center; }}
.stat-card .num {{ font-size: 24px; font-weight: 700; }}
.stat-card .label {{ font-size: 11px; color: var(--muted); margin-top: 4px; font-weight: 500; }}
.chart-section {{ padding: 0 24px 24px; }}
.chart-box {{ background: var(--card); border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(6,33,61,.06); }}
.chart-box h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 14px; color: var(--deep); padding-bottom: 8px; border-bottom: 2px solid var(--light); }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: var(--deep); color: #fff; padding: 10px 12px; text-align: left; font-weight: 500; }}
td {{ padding: 8px 12px; border-bottom: 1px solid var(--light); }}
tr:hover td {{ background: var(--light); }}
.footer {{ text-align: center; padding: 24px; font-size: 12px; color: var(--muted); border-top: 1px solid var(--light); margin-top: 8px; }}
</style>
</head>
<body>
<div class="header">
  <h1>Cohort 锁单预测 · 回测</h1>
  <p>{bt_start.date()} ~ {bt_end.date()} | {n_bt} 天 | 数据截止 {cutoff.date()}</p>
</div>
<div class="stats">
  <div class="stat-card"><div class="num" style="color:{BRAND['pred']}">{mae_bt:.1f}</div><div class="label">MAE</div></div>
  <div class="stat-card"><div class="num" style="color:{BRAND['pred']}">{rmse_bt:.1f}</div><div class="label">RMSE</div></div>
  <div class="stat-card"><div class="num" style="color:{BRAND['actual']}">{mape_bt:.1f}%</div><div class="label">MAPE</div></div>
  <div class="stat-card"><div class="num" style="color:var(--blue)">{avg:.4f}</div><div class="label">avg_30d_rate</div></div>
  <div class="stat-card"><div class="num" style="color:var(--blue)">{r7:.4f}</div><div class="label">r7</div></div>
  <div class="stat-card"><div class="num" style="color:var(--blue)">{r0:.4f}</div><div class="label">r0</div></div>
</div>
<div class="chart-section">
<div class="chart-box">
  <h2>CohortForecast · DailyLockCount · CohortActual_30d</h2>
  <div id="chart-cohort"></div>
</div>
<div class="chart-box">
  <h2>误差 (DailyLockCount - CohortForecast)</h2>
  <div id="chart-diff"></div>
</div>
<div class="chart-box">
  <h2>DailyLockCount / CohortForecast 比值</h2>
  <div id="chart-ratio"></div>
</div>
<div class="chart-box">
  <h2>近30日明细</h2>
  <div style="overflow-x:auto;">
  <table>
  <thead><tr><th>Date</th><th>下发线索数</th><th>CohortForecast</th><th>CohortActual_30d</th><th>DailyLockCount</th><th>Daily/Forecast</th><th>阶段</th></tr></thead>
  <tbody>{table_rows}</tbody>
  </table>
  </div>
</div>
</div>
<div class="footer">
  <img src="../../assets/brand/raccoon_avatar_light.png" style="height:28px;opacity:.5;margin-bottom:6px" /><br/>
  Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Raccoon Research
</div>
<script>
var S = {series_json};
Plotly.newPlot('chart-cohort', [
  {{x: S.dates, y: S.pred, type: 'scatter', mode: 'lines', name: 'CohortForecast', line: {{color: '{BRAND["pred"]}', width: 1.5}}}},
  {{x: S.dates, y: S.daily, type: 'scatter', mode: 'lines', name: 'DailyLockCount', line: {{color: '{BRAND["actual"]}', width: 1.5}}}},
  {{x: S.dates, y: S.actual, type: 'scatter', mode: 'lines', name: 'CohortActual_30d', line: {{color: '{BRAND["daily"]}', width: 1.2, dash: 'dot'}}}},
], {{
  height: 350, margin: {{t: 20, r: 20, b: 50, l: 60}},
  legend: {{orientation: 'h', y: 1.05, x: 0}},
  hovermode: 'x unified', yaxis: {{title: '30日锁单数', fixedrange: true}},
  xaxis: {{title: 'Assign Date', fixedrange: true}},
}}, {{displayModeBar: false}});
var diffColors = S.error.map(v => v >= 0 ? '#174A7C' : '#D79A36');
Plotly.newPlot('chart-diff', [
  {{x: S.dates, y: S.error, type: 'bar', name: 'cohort_error', marker: {{color: diffColors, opacity: 0.6}}}},
], {{
  height: 300, margin: {{t: 20, r: 20, b: 50, l: 60}},
  hovermode: 'x unified', yaxis: {{title: '误差 (DailyLockCount - CohortForecast)', fixedrange: true}},
  xaxis: {{title: 'Assign Date', fixedrange: true}},
}}, {{displayModeBar: false}});
Plotly.newPlot('chart-ratio', [
  {{x: S.dates, y: S.ratio, type: 'scatter', mode: 'markers', name: 'pred/actual', marker: {{color: '{BRAND["ratio"]}', size: 3, opacity: 0.4}}}},
], {{
  height: 250, margin: {{t: 20, r: 20, b: 50, l: 60}},
  hovermode: 'x unified', yaxis: {{title: 'DailyLockCount / CohortForecast', fixedrange: true}},
  xaxis: {{title: 'Assign Date', fixedrange: true}},
  shapes: [{{type: 'line', x0: S.dates[0], y0: 1, x1: S.dates[S.dates.length-1], y1: 1, line: {{color: '#888', width: 1, dash: 'dash'}}}}],
}}, {{displayModeBar: false}});
</script>
</body>
</html>"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    return OUTPUT_HTML


def main():
    args = parse_args()
    cmd = "python " + " ".join(sys.argv)

    cutoff = None
    mae_bt = rmse_bt = mape_bt = n_bt = None
    r0 = r7 = avg = None
    bt_start = bt_end = None

    contract = None

    try:
        df = load_data()
        cutoff = df["_date"].max()
        bt_end = cutoff - pd.Timedelta(days=PRED_AGE)
        bt_start = bt_end - pd.Timedelta(days=364)

        r0, r7, avg = build_baseline(df, cutoff)

        if args.format == "terminal":
            print(f"\n  {_ruler('━', 64)}")
            print(f"  {DEEP}{BOLD}Cohort 锁单预测回测 · 三段式成熟度模型{RST:^20}")
            print(f"  {_ruler('━', 64)}")

        if args.format == "terminal":
            print("Loading data ...")
        rd = run_prediction(df, bt_start, cutoff)
        n_bt, mae_bt, rmse_bt, mape_bt, rd_bt = compute_metrics(rd, bt_start, bt_end)

        if args.format == "terminal":
            print(f"\n  {GOLD}■{RST} {DEEP}{BOLD}回测精度指标{RST}")
            print(f"    {_b('MAE')}:  {_blue(f'{mae_bt:.2f}')}  {_muted('平均绝对误差')}")
            print(f"    {_b('RMSE')}:  {_blue(f'{rmse_bt:.2f}')}  {_muted('均方根误差')}")
            print(f"    {_b('MAPE')}:  {_blue(f'{mape_bt:.2f}%')}  {_muted('平均绝对百分比误差')}")
            print(f"    {_b('样本量')}:  {_blue(str(n_bt))}  {_muted('回测天数')}")
            print(f"    {_b('avg_30d_rate')}: {avg:.4f}  {_b('r7')}: {r7:.4f}  {_b('r0')}: {r0:.4f}")
            print(f"\n  {GOLD}■{RST} {DEEP}{BOLD}按月明细{RST}")
            print(f"CohortForecast vs CohortActual_30d (三段式, age={PRED_AGE} 预测)")
            print(f"  周期 {bt_start.date()} ~ {bt_end.date()} | days={n_bt}  MAE={mae_bt:.1f}  RMSE={rmse_bt:.1f}  MAPE={mape_bt:.1f}%")
            rd_bt["month"] = rd_bt["date"].dt.to_period("M").astype(str)
            for m, grp in sorted(rd_bt.groupby("month")):
                nm = len(grp)
                me = float(grp["cohort_error"].abs().mean())
                rms = float(np.sqrt((grp["cohort_error"] ** 2).mean()))
                ap = grp["cohort_ape"].dropna()
                mp = float(ap.mean()) if not ap.empty else 0.0
                print(f"    {m}: n={nm:3d}  MAE={me:>7.1f}  RMSE={rms:>7.1f}  MAPE={mp:>5.1f}%")

            print("\nLoading order_data ...")
        html_path = generate_html(rd, bt_start, bt_end, cutoff, n_bt, mae_bt, rmse_bt, mape_bt, r0, r7, avg)
        if args.format == "terminal":
            print(f"Report saved: {html_path}")

        scope = {
            "data_source": str(ASSIGN_CSV),
            "time_window": {"start_date": str(bt_start.date()), "end_date": str(bt_end.date())},
            "filters": {},
            "metric_definition": "cohort forecast backtest: MAE/RMSE/MAPE based on lead-lock release (三段式)",
        }
        result = {
            "summary": f"回测完成: MAE={mae_bt:.2f}, RMSE={rmse_bt:.2f}, MAPE={mape_bt:.2f}%, days={n_bt}",
            "metrics": {"mae": round(mae_bt, 2), "rmse": round(rmse_bt, 2), "mape": round(mape_bt, 2), "case_count": n_bt},
        }
        contract = build_partial_contract(
            script="research_scripts/lock_predict_backtest.py", command=cmd,
            scope=scope, result=result,
            warnings=["预测阶段 age<7d 使用加权平均，可能存在偏差"],
            followup_context={"metric": "cohort_forecast_backtest", "available_dimensions": ["cohort_date"]},
        )

    except Exception as e:
        contract = build_partial_contract(
            script="research_scripts/lock_predict_backtest.py", command=cmd,
            scope={"data_source": str(ASSIGN_CSV)},
            result={"summary": f"执行异常: {e}"},
            warnings=[str(e)],
            followup_context={"metric": "cohort_forecast_backtest"},
        )
        if args.format == "terminal":
            print(f"\n  {_gold('⚠')} 异常: {e}")

    if args.format == "json":
        if args.output:
            save_contract_json(contract, Path(args.output) / "lock_predict_backtest.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
        return

    if args.format == "terminal":
        if contract:
            print(f"\n  {_ruler('━', 64)}")
            print(f"  {GOLD}■{RST} {DEEP}{BOLD}数据信息{RST}")
            print(f"    {_b('数据源')}:  {contract['scope'].get('data_source', 'N/A')}")
            tw = contract.get("scope", {}).get("time_window", {})
            if tw.get("start_date"):
                print(f"    {_b('时间')}:    {tw['start_date']} ~ {tw['end_date']}")
            print(f"    {_b('方法')}:    三段式 (≥30d 原始值, 7-30d lock7/r7, <7d 加权平均)")
            print(f"    {_b('HTML')}:    {OUTPUT_HTML}")
            print(f"\n  {_ruler('━', 64)}\n")


if __name__ == "__main__":
    main()
