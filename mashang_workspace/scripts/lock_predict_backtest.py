#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

from operators.mature_lock_prediction import run_mature_lock_prediction_operator
from operators.assign_conversion import _parse_cn_date

ASSIGN_CSV = REPO_ROOT / "dataset" / "assign_data.csv"
OUTPUT_HTML = REPO_ROOT / "scripts" / "reports" / "lock_predict_backtest.html"

PRED_AGE = 7

print("Loading data ...")
df = pd.read_csv(str(ASSIGN_CSV))
df["_date"] = _parse_cn_date(df["Assign Time 年/月/日"])
df = df[df["_date"].notna()].sort_values("_date").reset_index(drop=True)

cutoff = df["_date"].max()                     # 2026-05-28
bt_end = cutoff - pd.Timedelta(days=PRED_AGE)  # 2026-05-21
bt_start = bt_end - pd.Timedelta(days=364)     # 2025-05-22

n_fn = lambda c: pd.to_numeric(c.astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
df["_leads"] = n_fn(df["下发线索数"])
df["_lock0"] = n_fn(df["下发线索当日锁单数 (门店)"])
df["_lock7"] = n_fn(df["下发线索 7 日锁单数"])
df["_lock30"] = n_fn(df["下发线索 30 日锁单数"])

# ── Build maturity baseline ──
mature = df[df["_date"] <= cutoff - pd.Timedelta(days=30)]
R0 = float(mature["_lock0"].sum()) / float(mature["_lock30"].sum())
R7 = float(mature["_lock7"].sum()) / float(mature["_lock30"].sum())
AVG = float(mature["_lock30"].sum()) / float(mature["_leads"].sum())

print("Building daily metrics ...")
print(f"  avg_30d_rate = {AVG:.4f}  r7 = {R7:.4f}  r0 = {R0:.4f}")

# ── Three-stage rolling prediction for ALL days ──

results = []
cohort_min = df[df["_date"] >= bt_start]["_date"].min()
for _, row in df.iterrows():
    d = row["_date"]
    if d < cohort_min or d >= cutoff:
        continue

    leads = float(row["_leads"])
    lock0 = float(row["_lock0"])
    lock7 = float(row["_lock7"])
    lock30 = float(row["_lock30"])

    snapshot = min(d + pd.Timedelta(days=PRED_AGE), cutoff)
    age = (snapshot - d).days

    mature = df[df["_date"] <= snapshot - pd.Timedelta(days=30)]
    has_mature = (not mature.empty) and (mature["_lock30"].sum() > 0)

    if age >= 30:
        pred = lock30
        stage = "actual"
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

    results.append({
        "date": d,
        "下发线索数": int(leads),
        "cohort_pred_30_lock": round(pred, 1),
        "cohort_actual_30_lock": int(lock30),
        "预测阶段": stage,
    })

rd = pd.DataFrame(results)

# ── CLI: backtest on bt_start ~ bt_end ──
rd_bt = rd[(rd["date"] >= bt_start) & (rd["date"] <= bt_end)].copy()
rd_bt["cohort_error"] = rd_bt["cohort_pred_30_lock"] - rd_bt["cohort_actual_30_lock"]
rd_bt["cohort_ape"] = rd_bt.apply(
    lambda r: abs(r["cohort_error"]) / r["cohort_actual_30_lock"] * 100
    if r["cohort_actual_30_lock"] > 0 else np.nan, axis=1,
)

n_bt = len(rd_bt)
mae_bt = float(rd_bt["cohort_error"].abs().mean())
rmse_bt = float(np.sqrt((rd_bt["cohort_error"] ** 2).mean()))
mape_bt = float(rd_bt["cohort_ape"].dropna().mean())

print(f"\nCohortForecast vs CohortActual_30d (三段式, age={PRED_AGE} 预测)")
print(f"  周期 {bt_start.date()} ~ {bt_end.date()} | days={n_bt}  MAE={mae_bt:.1f}  RMSE={rmse_bt:.1f}  MAPE={mape_bt:.1f}%")

rd_bt["month"] = rd_bt["date"].dt.to_period("M").astype(str)
print("  按月:")
for m, grp in sorted(rd_bt.groupby("month")):
    nm = len(grp)
    me = float(grp["cohort_error"].abs().mean())
    rms = float(np.sqrt((grp["cohort_error"] ** 2).mean()))
    ap = grp["cohort_ape"].dropna()
    mp = float(ap.mean()) if not ap.empty else 0.0
    print(f"    {m}: n={nm:3d}  MAE={me:>7.1f}  RMSE={rms:>7.1f}  MAPE={mp:>5.1f}%")

# ── Daily lock count from order_data ──
ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
print("\nLoading order_data ...")
order_df = pd.read_parquet(str(ORDER_PARQUET))
order_df["lock_date"] = pd.to_datetime(order_df["lock_time"], errors="coerce").dt.normalize()
daily_lock = (
    order_df[order_df["lock_date"].notna()]
    .groupby("lock_date")["order_number"]
    .nunique()
    .reset_index()
)
daily_lock.columns = ["date", "daily_lock_count"]
daily_lock["date"] = pd.to_datetime(daily_lock["date"])

# ── HTML: show ALL predicted days (up to cutoff) ──
html_start = rd["date"].min()
html_end = rd["date"].max()
rd_html = rd.copy()
rd_html["cohort_error"] = rd_html["cohort_pred_30_lock"] - rd_html["cohort_actual_30_lock"]
rd_html["cohort_ape"] = rd_html.apply(
    lambda r: abs(r["cohort_error"]) / r["cohort_actual_30_lock"] * 100
    if r["cohort_actual_30_lock"] > 0 else np.nan, axis=1,
)
rd_html = rd_html.merge(daily_lock, on="date", how="left")
rd_html["daily_lock_count"] = rd_html["daily_lock_count"].fillna(0).astype(int)
n_html = len(rd_html)
mae_html = float(rd_html["cohort_error"].abs().mean())
rmse_html = float(np.sqrt((rd_html["cohort_error"] ** 2).mean()))
mape_html = float(rd_html["cohort_ape"].dropna().mean())

# ── HTML report (显示全部预测天数，含最近数据) ──
print(f"\nGenerating HTML report ...")

rd_html["pred_actual_ratio"] = rd_html.apply(
    lambda r: r["daily_lock_count"] / r["cohort_pred_30_lock"]
    if r["cohort_pred_30_lock"] > 0 else np.nan, axis=1,
)

COLORS = {"pred": "#d62728", "actual": "#2ca02c", "daily": "#1f77b4", "ratio": "#ff7f0e", "accent": "#1a237e", "bg": "#f5f7fa"}

series = {
    "dates": rd_html["date"].dt.strftime("%Y-%m-%d").tolist(),
    "pred": [float(v) for v in rd_html["cohort_pred_30_lock"]],
    "actual": [int(v) for v in rd_html["cohort_actual_30_lock"]],
    "daily": [int(v) for v in rd_html["daily_lock_count"]],
    "error": [float(v) for v in rd_html["daily_lock_count"] - rd_html["cohort_pred_30_lock"]],
    "ratio": [float(v) if not np.isnan(v) else None for v in rd_html["pred_actual_ratio"]],
}
series_json = json.dumps(series)

table_rows = ""
last30 = rd_html.tail(30).iloc[::-1]
total_leads = last30["下发线索数"].sum()
total_pred = last30["cohort_pred_30_lock"].sum()
total_actual = last30["cohort_actual_30_lock"].sum()
total_daily = last30["daily_lock_count"].sum()
overall_ratio = total_daily / total_pred * 100 if total_pred > 0 else float("nan")
overall_ratio_str = f"{overall_ratio:.1f}%" if not np.isnan(overall_ratio) else "N/A"
ratio_style_total = f' style="background:#ffebee;font-weight:600"' if (not np.isnan(overall_ratio) and overall_ratio < 80) else ""

for _, r in rd_html.tail(30).iloc[::-1].iterrows():
    ratio_val = r["daily_lock_count"] / r["cohort_pred_30_lock"] * 100 if r["cohort_pred_30_lock"] > 0 else float("nan")
    ratio_str = f"{ratio_val:.1f}%" if not np.isnan(ratio_val) else "N/A"
    ratio_style = f' style="background:#ffebee;font-weight:600"' if (not np.isnan(ratio_val) and ratio_val < 80) else ""
    stage_label = {"actual":"实际值","lock7_proj":"7日投影","weighted_avg":"加权平均"}.get(r["预测阶段"], r["预测阶段"])
    table_rows += f"""  <tr>
    <td>{r['date'].strftime('%Y-%m-%d')}</td>
    <td>{r['下发线索数']:,.0f}</td>
    <td>{r['cohort_pred_30_lock']:.1f}</td>
    <td>{r['cohort_actual_30_lock']:,}</td>
    <td>{r['daily_lock_count']:,}</td>
    <td{ratio_style}>{ratio_str}</td>
    <td>{stage_label}</td>
  </tr>
"""

table_rows += f"""  <tr style="background:#e8eaf6;font-weight:600">
    <td>合计</td>
    <td>{total_leads:,}</td>
    <td>{total_pred:.1f}</td>
    <td>{total_actual:,}</td>
    <td>{total_daily:,}</td>
    <td{ratio_style_total}>{overall_ratio_str}</td>
    <td></td>
  </tr>
"""

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cohort 锁单预测 — 回测报告</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: {COLORS["bg"]}; color: #333; }}
.header {{ background: linear-gradient(135deg, {COLORS["accent"]}, #283593); color: #fff; padding: 28px 24px 20px; text-align: center; }}
.header h1 {{ font-size: 24px; font-weight: 600; }}
.header p {{ font-size: 13px; opacity: .8; margin-top: 6px; }}
.stats {{ display: flex; gap: 10px; padding: 16px 24px; flex-wrap: wrap; }}
.stat-card {{ flex: 1; min-width: 110px; background: #fff; border-radius: 10px; padding: 14px 12px; box-shadow: 0 1px 3px rgba(0,0,0,.08); text-align: center; }}
.stat-card .num {{ font-size: 22px; font-weight: 700; }}
.stat-card .label {{ font-size: 11px; color: #888; margin-top: 3px; }}
.chart-section {{ padding: 0 24px 24px; }}
.chart-box {{ background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
.chart-box h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 12px; color: {COLORS["accent"]}; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: {COLORS["accent"]}; color: #fff; padding: 10px 12px; text-align: left; font-weight: 500; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
tr:hover td {{ background: #f0f2ff; }}
.footer {{ text-align: center; padding: 20px; font-size: 12px; color: #aaa; }}
</style>
</head>
<body>

<div class="header">
  <h1>Cohort 锁单预测 — 回测</h1>
  <p>{bt_start.date()} ~ {bt_end.date()} | {n_bt} 天 | 数据截止 {cutoff.date()}</p>
</div>

<div class="stats">
  <div class="stat-card"><div class="num" style="color:{COLORS['pred']}">{mae_bt:.1f}</div><div class="label">MAE</div></div>
  <div class="stat-card"><div class="num" style="color:{COLORS['pred']}">{rmse_bt:.1f}</div><div class="label">RMSE</div></div>
  <div class="stat-card"><div class="num" style="color:{COLORS['actual']}">{mape_bt:.1f}%</div><div class="label">MAPE</div></div>
  <div class="stat-card"><div class="num">{AVG:.4f}</div><div class="label">avg_30d_rate</div></div>
  <div class="stat-card"><div class="num">{R7:.4f}</div><div class="label">r7</div></div>
  <div class="stat-card"><div class="num">{R0:.4f}</div><div class="label">r0</div></div>
</div>

<div class="chart-section">

<div class="chart-box">
  <h2>CohortForecast / DailyLockCount / CohortActual_30d</h2>
  <div id="chart-cohort"></div>
</div>

<div class="chart-box">
  <h2>误差 (DailyLockCount - CohortForecast)</h2>
  <div id="chart-diff"></div>
</div>

<div class="chart-box">
  <h2>DailyLockCount/CohortForecast 比值</h2>
  <div id="chart-ratio"></div>
</div>

<div class="chart-box">
  <h2>近30日明细</h2>
  <div style="overflow-x:auto;">
  <table>
  <thead><tr><th>Date</th><th>下发线索数</th><th>CohortForecast</th><th>CohortActual_30d</th><th>DailyLockCount</th><th>Daily/Forecast</th><th>阶段</th></tr></thead>
  <tbody>
{table_rows}
  </tbody>
  </table>
  </div>
</div>

</div>

<div class="footer">Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>

<script>
var S = {series_json};

Plotly.newPlot('chart-cohort', [
  {{x: S.dates, y: S.pred, type: 'scatter', mode: 'lines', name: 'CohortForecast', line: {{color: '{COLORS["pred"]}', width: 1.5}}}},
  {{x: S.dates, y: S.daily, type: 'scatter', mode: 'lines', name: 'DailyLockCount', line: {{color: '{COLORS["actual"]}', width: 1.5}}}},
  {{x: S.dates, y: S.actual, type: 'scatter', mode: 'lines', name: 'CohortActual_30d', line: {{color: '{COLORS["daily"]}', width: 1.2, dash: 'dot'}}}},
], {{
  height: 350, margin: {{t: 20, r: 20, b: 50, l: 60}},
  legend: {{orientation: 'h', y: 1.05, x: 0}},
  hovermode: 'x unified',
  yaxis: {{title: '30日锁单数', fixedrange: true}},
  xaxis: {{title: 'Assign Date', fixedrange: true}},
}}, {{displayModeBar: false}});

var diffColors = S.error.map(v => v >= 0 ? '#2ca02c' : '#d62728');
Plotly.newPlot('chart-diff', [
  {{x: S.dates, y: S.error, type: 'bar', name: 'cohort_error', marker: {{color: diffColors, opacity: 0.6}}}},
], {{
  height: 300, margin: {{t: 20, r: 20, b: 50, l: 60}},
  hovermode: 'x unified',
  yaxis: {{title: '误差 (DailyLockCount - CohortForecast)', fixedrange: true}},
  xaxis: {{title: 'Assign Date', fixedrange: true}},
}}, {{displayModeBar: false}});

Plotly.newPlot('chart-ratio', [
  {{x: S.dates, y: S.ratio, type: 'scatter', mode: 'markers', name: 'pred/actual', marker: {{color: '{COLORS["ratio"]}', size: 3, opacity: 0.4}}}},
], {{
  height: 250, margin: {{t: 20, r: 20, b: 50, l: 60}},
  hovermode: 'x unified',
  yaxis: {{title: 'DailyLockCount / CohortForecast', fixedrange: true}},
  xaxis: {{title: 'Assign Date', fixedrange: true}},
  shapes: [{{type: 'line', x0: S.dates[0], y0: 1, x1: S.dates[S.dates.length-1], y1: 1, line: {{color: '#888', width: 1, dash: 'dash'}}}}],
}}, {{displayModeBar: false}});
</script>
</body>
</html>
"""

with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Report saved: {OUTPUT_HTML} ({len(html):,} bytes)")
