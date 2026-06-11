#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Lock Release Curve (锁单释放曲线独立研究)

从 order_data 中提取每批线索(按分配日 cohort)的逐日锁单释放模式，
分析释放曲线的形态、稳定性、趋势变化，并尝试曲线拟合。

输出: reports/lock_release_curve.html (交互式报告)

计算逻辑详见: lock_release_analysis.md
结构速览:
  step_1~2  数据加载 & 逐 cohort 曲线
  step_3    加权平均释放曲线 (avg_curve, daily_marginal)
  step_4    逐年对比 (year_over_year)
  step_5    百分位分析 (percentiles)
  step_6    Logistic 曲线拟合 (纯 numpy LM)
  step_7    星期效应 (day_of_week)
  step_8    边际衰减 (marginal_decay)
  step_9    HTML 报告 (Plotly.js)
  step_10    Lead→Lock 传导时滞分布 (mean/P50/P80/P90)
设计决策: 60d窗口 / 按规模加权 / 归一化30d / 手动LM
"""

import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import json
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
OUTPUT_HTML = REPO_ROOT / "scripts" / "reports" / "lock_release_curve.html"
MAX_DAY = 60  # 分析窗口：分配后 60 天

print("=" * 60)
print("锁单释放曲线分析 Release Curve Analysis")
print("=" * 60)

# ── 1. Load Data ──
print("\n[1/7] Loading order_data ...")
order_df = pd.read_parquet(str(ORDER_PARQUET))
print(f"  Total orders: {len(order_df):,}")

rc_raw = order_df[order_df["first_assign_time"].notna() & order_df["lock_time"].notna()].copy()
rc_raw["assign_date"] = pd.to_datetime(rc_raw["first_assign_time"], errors="coerce").dt.normalize()
rc_raw["lock_date"] = pd.to_datetime(rc_raw["lock_time"], errors="coerce").dt.normalize()
rc_raw = rc_raw[rc_raw["assign_date"].notna() & rc_raw["lock_date"].notna()]
rc_raw["day_after"] = (rc_raw["lock_date"] - rc_raw["assign_date"]).dt.days
rc_raw = rc_raw[rc_raw["day_after"].between(0, MAX_DAY)]

print(f"  Orders with assign + lock: {len(rc_raw):,}")
print(f"  Date range: {rc_raw['assign_date'].min().date()} ~ {rc_raw['assign_date'].max().date()}")

# ── 2. Per-Cohort Release Curves ──
print("\n[2/7] Computing per-cohort release curves ...")

cutoff_date = rc_raw["assign_date"].max()
mature_cutoff = cutoff_date - pd.Timedelta(days=MAX_DAY)

cohort_curves = []
for a_date, grp in rc_raw.groupby("assign_date"):
    if a_date > mature_cutoff:
        continue
    total_30 = len(grp)
    if total_30 < 5:
        continue
    cum_pct = np.array([(grp["day_after"] <= d).sum() / total_30 for d in range(MAX_DAY + 1)])
    cohort_curves.append({
        "assign_date": a_date,
        "total_30": total_30,
        "cum_pct": cum_pct,
    })

print(f"  Matured cohorts: {len(cohort_curves)}")

# ── 3. Weighted Average Release Curve ──
print("\n[3/7] Computing average release curve ...")

avg_curve = np.zeros(MAX_DAY + 1)
total_weight = sum(cc["total_30"] for cc in cohort_curves)
for cc in cohort_curves:
    avg_curve += cc["cum_pct"] * (cc["total_30"] / total_weight)
daily_marginal = np.diff(avg_curve, prepend=0)
cum_at_30 = avg_curve[30]

print(f"  Total orders in curve: {int(total_weight):,}")
print(f"  Release curve (cumulative % of 30-day total):")
print(f"    {'Day':>4s}  {'Cum%':>7s}  {'Marg%':>7s}")
for d in [0, 1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60]:
    c = avg_curve[d] / cum_at_30 * 100
    m = daily_marginal[d] / cum_at_30 * 100
    print(f"    {d:4d}  {c:6.1f}%  {m:6.2f}%")

print(f"\n  Key insights:")
print(f"    Day 0 lock share: {avg_curve[0]/cum_at_30*100:.1f}%")
print(f"    Day 7 lock share: {avg_curve[7]/cum_at_30*100:.1f}%")
print(f"    Day 30 = 100% baseline (avg_curve[30] = {cum_at_30:.4f})")
print(f"    Day 0-7 concentration: {(avg_curve[7]-avg_curve[0])/cum_at_30*100:.1f}%")

# ── 4. Year-over-Year Trend ──
print("\n[4/7] Year-over-year trend analysis ...")

year_curves: dict[int, list] = defaultdict(list)
for cc in cohort_curves:
    y = cc["assign_date"].year
    year_curves[y].append(cc)

year_avg = {}
for y in sorted(year_curves.keys()):
    ccs = year_curves[y]
    w_sum = np.zeros(MAX_DAY + 1)
    w_total = sum(cc["total_30"] for cc in ccs)
    for cc in ccs:
        w_sum += cc["cum_pct"] * (cc["total_30"] / w_total)
    year_avg[y] = {"curve": w_sum, "cohorts": len(ccs), "orders": int(w_total)}

print(f"  {'Year':>6s}  {'Cohorts':>8s}  {'Orders':>8s}  {'D0%':>6s}  {'D7%':>6s}  {'D30%':>6s}")
for y, ya in sorted(year_avg.items()):
    d0 = ya["curve"][0] / cum_at_30 * 100
    d7 = ya["curve"][7] / cum_at_30 * 100
    d30 = ya["curve"][30] / cum_at_30 * 100
    print(f"  {y:6d}  {ya['cohorts']:8d}  {ya['orders']:8,d}  {d0:5.1f}%  {d7:5.1f}%  {d30:5.1f}%")

# ── 5. Percentile Analysis ──
print("\n[5/7] Percentile analysis (cohort-level variability) ...")

# Collect all cohort curves into a matrix
curve_matrix = np.array([cc["cum_pct"] for cc in cohort_curves])
percentiles = {}
for p in [5, 10, 25, 50, 75, 90, 95]:
    percentiles[p] = np.percentile(curve_matrix, p, axis=0)

# Normalize to 30-day total
for p in percentiles:
    percentiles[p] = percentiles[p] / cum_at_30 * 100

print(f"  Percentile bands at key days (normalized to 30d=100%):")
print(f"    {'Day':>4s}  {'P10':>6s}  {'P25':>6s}  {'P50':>6s}  {'P75':>6s}  {'P90':>6s}")
for d in [0, 1, 3, 7, 14, 30]:
    vals = [percentiles[p][d] for p in [10, 25, 50, 75, 90]]
    print(f"    {d:4d}  {vals[0]:5.1f}%  {vals[1]:5.1f}%  {vals[2]:5.1f}%  {vals[3]:5.1f}%  {vals[4]:5.1f}%")

# P90-P10 spread as a measure of variability
spread = percentiles[90] - percentiles[10]
print(f"\n  P90-P10 spread:")
for d in [0, 1, 3, 7, 14, 30]:
    print(f"    Day {d:2d}: {spread[d]:.1f}pp")

# ── 6. Logistic Curve Fitting ──
print("\n[6/7] Logistic curve fitting ...")

x_data = np.arange(MAX_DAY + 1, dtype=float)
y_data = avg_curve / cum_at_30 * 100  # Normalize to %

print("  Fitting with Levenberg-Marquardt (3-param, pure numpy) ...")

# Step 1: linearization for initial guess
# z = ln(L/y - 1) = -k*x + k*x0
# Use L_guess = y_data[-1] (asymptote)
L_init = min(float(y_data[-1]) * 1.05, 120.0)  # slightly above 60d value

mask = (y_data > 5) & (y_data < L_init * 0.95)
x_mid = x_data[mask]
y_mid = y_data[mask]

if len(x_mid) >= 3:
    z = np.log(L_init / y_mid - 1)
    coeffs = np.polyfit(x_mid, z, 1)  # a*x + b
    k_init = -coeffs[0]               # k = -a
    x0_init = coeffs[1] / k_init if abs(k_init) > 1e-10 else 3.0
else:
    k_init, x0_init = 0.3, 3.0

def _logistic(x, L, k, x0):
    return L / (1 + np.exp(-k * (x - x0)))

def _lm_3p(x, y, p0, max_iter=200, tol=1e-10):
    """Levenberg-Marquardt for 3-param logistic: [L, k, x0]."""
    p = np.array(p0, dtype=float)
    lam = 1e-3
    best_p = p.copy()
    best_cost = np.inf
    for _ in range(max_iter):
        L, k, x0 = p
        e = np.exp(-k * (x - x0))
        denom = 1 + e
        y_pred = L / denom
        resid = y - y_pred
        cost = np.sum(resid ** 2)
        if cost < best_cost:
            best_cost = cost
            best_p = p.copy()
        if np.sqrt(cost / len(y)) < tol:
            break
        # Jacobian
        jL = 1 / denom
        jk = L * x * e / denom ** 2 - L * x0 * e / denom ** 2
        jx0 = -L * k * e / denom ** 2
        J = np.column_stack([jL, jk, jx0])
        H = J.T @ J
        g = J.T @ resid
        H_reg = H + lam * np.diag(np.diag(H) + 1e-8)
        try:
            dp = np.linalg.solve(H_reg, g)
        except np.linalg.LinAlgError:
            dp = np.linalg.lstsq(H_reg, g, rcond=None)[0]
        p_new = p + dp
        # enforce constraints
        p_new[0] = max(50.0, min(150.0, p_new[0]))  # L in [50, 150]
        p_new[1] = max(0.001, min(5.0, p_new[1]))   # k in [0.001, 5]
        p_new[2] = max(0.0, min(60.0, p_new[2]))    # x0 in [0, 60]
        resid_new = y - _logistic(x, *p_new)
        cost_new = np.sum(resid_new ** 2)
        if cost_new < cost:
            p = p_new
            lam *= 0.3
        else:
            lam *= 3
        if np.linalg.norm(dp) < tol * np.linalg.norm(p) + tol:
            break
    L, k, x0 = best_p
    y_fit = _logistic(x, L, k, x0)
    return L, k, x0, y_fit

try:
    L_fit, k_fit, x0_fit, y_fit = _lm_3p(x_data, y_data, p0=[L_init, k_init, x0_init])
    fit_rmse = float(np.sqrt(np.mean((y_fit - y_data) ** 2)))

    # Try a second start if first fit is poor
    if fit_rmse > 5.0:
        L2, k2, x02, y2 = _lm_3p(x_data, y_data, p0=[min(L_init * 1.2, 120), k_init * 1.5, max(x0_init - 1, 0)])
        rmse2 = float(np.sqrt(np.mean((y2 - y_data) ** 2)))
        if rmse2 < fit_rmse:
            L_fit, k_fit, x0_fit, y_fit, fit_rmse = L2, k2, x02, y2, rmse2

    print(f"  Logistic model:  y = {L_fit:.1f} / (1 + exp(-{k_fit:.4f} * (x - {x0_fit:.2f})))")
    print(f"  Fit RMSE: {fit_rmse:.2f}pp")
    for d in [0, 1, 3, 7, 14, 30]:
        print(f"    Day {d:2d}: actual={y_data[d]:.1f}%  fitted={y_fit[d]:.1f}%")
except Exception as e:
    print(f"  Logistic fit failed: {e}")
    L_fit = k_fit = x0_fit = None
    y_fit = None
    fit_rmse = None

# ── 7. Day-of-Week Analysis ──
print("\n[7/7] Day-of-week analysis ...")

dow_curves: dict[int, list] = defaultdict(list)
for cc in cohort_curves:
    dow = cc["assign_date"].dayofweek
    dow_curves[dow].append(cc)

dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
dow_avg = {}
for dow in range(7):
    ccs = dow_curves.get(dow, [])
    if not ccs:
        continue
    w_sum = np.zeros(MAX_DAY + 1)
    w_total = sum(cc["total_30"] for cc in ccs)
    for cc in ccs:
        w_sum += cc["cum_pct"] * (cc["total_30"] / w_total)
    dow_avg[dow] = {"curve": w_sum, "cohorts": len(ccs), "orders": int(w_total)}

print(f"  {'DOW':>5s}  {'Cohorts':>8s}  {'Orders':>8s}  {'D0%':>6s}  {'D7%':>6s}  {'D30%':>6s}")
for dow in sorted(dow_avg.keys()):
    da = dow_avg[dow]
    d0 = da["curve"][0] / cum_at_30 * 100
    d7 = da["curve"][7] / cum_at_30 * 100
    d30 = da["curve"][30] / cum_at_30 * 100
    print(f"  {dow_names[dow]:>5s}  {da['cohorts']:8d}  {da['orders']:8,d}  {d0:5.1f}%  {d7:5.1f}%  {d30:5.1f}%")

# ── 8. Marginal Decay Analysis ──
print("\n  Marginal decay analysis (daily release rate):")
print(f"    Day 0: {daily_marginal[0]/cum_at_30*100:.2f}%/d")
half_life_candidates = []
for d in range(1, MAX_DAY + 1):
    if daily_marginal[d] > 0 and daily_marginal[d] <= daily_marginal[0] / 2:
        half_life_candidates.append(d)
if half_life_candidates:
    print(f"    Marginal rate halves around day {half_life_candidates[0]}")
# Days to reach 50%, 80%, 90% of 30-day total
for target_pct in [50, 80, 90]:
    target = target_pct / 100 * cum_at_30
    day_reached = np.searchsorted(avg_curve, target)
    print(f"    Day to reach {target_pct}% of 30d total: day {day_reached}")

# ── 10. Lead→Lock Transmission Lag Distribution ──
print("\n[10/10] Lead→Lock transmission lag distribution ...")

lags = rc_raw["day_after"].values

mean_lag = float(np.mean(lags))
p50 = float(np.median(lags))
p80 = float(np.percentile(lags, 80))
p90 = float(np.percentile(lags, 90))
p95 = float(np.percentile(lags, 95))

print(f"  Total orders: {len(lags):,}")
print(f"\n  {'Metric':>10s}  {'Value':>8s}")
print(f"  {'Mean':>10s}  {mean_lag:7.2f}d")
print(f"  {'P50':>10s}  {p50:7.2f}d")
print(f"  {'P80':>10s}  {p80:7.2f}d")
print(f"  {'P90':>10s}  {p90:7.2f}d")
print(f"  {'P95':>10s}  {p95:7.2f}d")

# Full histogram [0, MAX_DAY]
hist, _ = np.histogram(lags, bins=range(MAX_DAY + 2), density=False)
hist_pct = (hist / len(lags) * 100).tolist()

# Year-over-year breakdown
rc_raw["assign_year"] = rc_raw["assign_date"].dt.year
year_lag_stats: dict[int, dict] = {}
for year, grp in sorted(rc_raw.groupby("assign_year")):
    vals = grp["day_after"].values
    year_lag_stats[int(year)] = {
        "orders": len(vals),
        "mean": round(float(np.mean(vals)), 2),
        "p50": round(float(np.median(vals)), 2),
        "p80": round(float(np.percentile(vals, 80)), 2),
        "p90": round(float(np.percentile(vals, 90)), 2),
    }

print(f"\n  Year-over-year:")
print(f"  {'Year':>6s}  {'Orders':>8s}  {'Mean':>6s}  {'P50':>6s}  {'P80':>6s}  {'P90':>6s}")
for y, ys in year_lag_stats.items():
    print(f"  {y:6d}  {ys['orders']:8,d}  {ys['mean']:5.1f}d  {ys['p50']:5.1f}d  {ys['p80']:5.1f}d  {ys['p90']:5.1f}d")

# ── 9. HTML Report ──
print(f"\nGenerating HTML report ...")

# Prepare per-cohort scatter for visualization (sample for performance)
sample_size = min(500, len(cohort_curves))
rng = np.random.default_rng(42)
sampled_indices = rng.choice(len(cohort_curves), sample_size, replace=False)
scatter_dates = []
scatter_d0 = []
scatter_d7 = []
scatter_d14 = []
scatter_d30 = []
for idx in sampled_indices:
    cc = cohort_curves[idx]
    scatter_dates.append(str(cc["assign_date"].date()))
    scatter_d0.append(cc["cum_pct"][0] / cum_at_30 * 100)
    scatter_d7.append(cc["cum_pct"][7] / cum_at_30 * 100)
    scatter_d14.append(cc["cum_pct"][14] / cum_at_30 * 100)
    scatter_d30.append(100.0)

day_axis = list(range(MAX_DAY + 1))
avg_curve_pct = [float(v / cum_at_30 * 100) for v in avg_curve]
daily_marginal_pct = [float(v / cum_at_30 * 100) for v in daily_marginal]

# Year-over-year series
year_series = {}
for y in sorted(year_avg.keys()):
    year_series[str(y)] = [float(v / cum_at_30 * 100) for v in year_avg[y]["curve"]]

# Percentile series
p_series = {}
for p in [10, 25, 50, 75, 90]:
    p_series[f"p{p}"] = [float(v) for v in percentiles[p]]

# DOW series
dow_series = {}
for dow in sorted(dow_avg.keys()):
    dow_series[dow_names[dow]] = [float(v / cum_at_30 * 100) for v in dow_avg[dow]["curve"]]

fit_rmse_str = f"{fit_rmse:.2f}pp" if fit_rmse is not None else "N/A"

# Table data for key days
key_days = [0, 1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60]
table_rows = ""
for d in key_days:
    c = avg_curve[d] / cum_at_30 * 100
    m = daily_marginal[d] / cum_at_30 * 100
    table_rows += f"""  <tr>
    <td>{d}</td>
    <td>{c:.1f}%</td>
    <td>{m:.2f}%</td>
    <td>{percentiles[10][d]:.1f}%</td>
    <td>{percentiles[50][d]:.1f}%</td>
    <td>{percentiles[90][d]:.1f}%</td>
  </tr>
"""

series_json = json.dumps({
    "day_axis": day_axis,
    "avg_curve": avg_curve_pct,
    "daily_marginal": daily_marginal_pct,
    "year_curves": year_series,
    "percentiles": p_series,
    "dow_curves": dow_series,
    "dow_names": list(dow_avg.keys()),
    "dow_labels": [dow_names[d] for d in sorted(dow_avg.keys())],
    "scatter": {
        "dates": scatter_dates,
        "d0": scatter_d0,
        "d7": scatter_d7,
        "d14": scatter_d14,
    },
    "logistic_fit": {
        "L": round(L_fit, 2) if L_fit is not None else None,
        "k": round(k_fit, 4) if k_fit is not None else None,
        "x0": round(x0_fit, 2) if x0_fit is not None else None,
        "curve": [round(float(v), 2) for v in y_fit] if y_fit is not None else None,
    },
    "lag_hist_x": list(range(MAX_DAY + 1)),
    "lag_hist_y": hist_pct,
    "lag_stats": {"mean": mean_lag, "p50": p50, "p80": p80, "p90": p90, "p95": p95},
    "lag_year_stats": {str(k): v for k, v in year_lag_stats.items()},
    "lag_total_orders": int(len(lags)),
    "metadata": {
        "total_orders": int(total_weight),
        "total_cohorts": len(cohort_curves),
        "max_day": MAX_DAY,
        "date_range": f"{rc_raw['assign_date'].min().date()} ~ {rc_raw['assign_date'].max().date()}",
    },
})

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>锁单释放曲线分析 — Release Curve Analysis</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; color: #333; }}
.header {{ background: linear-gradient(135deg, #1a237e, #283593); color: #fff; padding: 28px 24px 20px; text-align: center; }}
.header h1 {{ font-size: 24px; font-weight: 600; }}
.header p {{ font-size: 13px; opacity: .8; margin-top: 6px; }}
.stats {{ display: flex; gap: 10px; padding: 16px 24px; flex-wrap: wrap; }}
.stat-card {{ flex: 1; min-width: 120px; background: #fff; border-radius: 10px; padding: 14px 12px; box-shadow: 0 1px 3px rgba(0,0,0,.08); text-align: center; }}
.stat-card .num {{ font-size: 24px; font-weight: 700; }}
.stat-card .label {{ font-size: 11px; color: #888; margin-top: 3px; }}
.chart-section {{ padding: 0 24px 24px; }}
.chart-box {{ background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
.chart-box h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 12px; color: #1a237e; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: #1a237e; color: #fff; padding: 10px 12px; text-align: left; font-weight: 500; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
tr:hover td {{ background: #f0f2ff; }}
.footer {{ text-align: center; padding: 20px; font-size: 12px; color: #aaa; }}
.accent-purple {{ color: #9467bd; }}
.accent-green {{ color: #2ca02c; }}
</style>
</head>
<body>

<div class="header">
  <h1>锁单释放曲线分析</h1>
  <p>基于 {int(total_weight):,} 个订单 / {len(cohort_curves)} 个成熟 cohort | {rc_raw['assign_date'].min().date()} ~ {rc_raw['assign_date'].max().date()}</p>
</div>

<div class="stats">
  <div class="stat-card"><div class="num" style="color:#9467bd">{avg_curve_pct[0]:.1f}%</div><div class="label">当日释放 (D0)</div></div>
  <div class="stat-card"><div class="num" style="color:#9467bd">{avg_curve_pct[7]:.1f}%</div><div class="label">7日累计释放</div></div>
  <div class="stat-card"><div class="num" style="color:#9467bd">{avg_curve_pct[14]:.1f}%</div><div class="label">14日累计释放</div></div>
  <div class="stat-card"><div class="num">{int(total_weight):,}</div><div class="label">有效订单数</div></div>
  <div class="stat-card"><div class="num">{len(cohort_curves):,}</div><div class="label">成熟 Cohort 数</div></div>
  <div class="stat-card"><div class="num">{fit_rmse_str}</div><div class="label">Logistic 拟合 RMSE</div></div>
</div>

<div class="chart-section">

<div class="chart-box">
  <h2>平均释放曲线 (累计% + 每日边际%)</h2>
  <div id="chart-main"></div>
</div>

<div class="chart-box">
  <h2>逐年对比 — 释放曲线稳定性</h2>
  <div id="chart-year"></div>
</div>

<div class="chart-box">
  <h2>Cohort 级释放率分布 (D0 / D7 / D14)</h2>
  <div id="chart-scatter"></div>
</div>

<div class="chart-box">
  <h2>百分位带 (P10 / P50 / P90) — 曲线不确定性</h2>
  <div id="chart-percentile"></div>
</div>

<div class="chart-box">
  <h2>Logistic 曲线拟合</h2>
  <div id="chart-logistic"></div>
</div>

<div class="chart-box">
  <h2>周内各分配日释放曲线对比</h2>
  <div id="chart-dow"></div>
</div>

<div class="chart-box">
  <h2>关键天数释放明细表</h2>
  <div style="overflow-x:auto;">
  <table>
  <thead><tr><th>分配后天数</th><th>平均累计%</th><th>平均边际%</th><th>P10</th><th>P50</th><th>P90</th></tr></thead>
  <tbody>
{table_rows}
  </tbody>
  </table>
  </div>
</div>

<div class="chart-box">
  <h2>Lead→Lock 传导时滞分布 (assign→lock 天数分布)</h2>
  <div id="chart-lag-dist"></div>
</div>

<div class="chart-box">
  <h2>逐年 Lead→Lock 传导时滞对比</h2>
  <div id="chart-lag-year"></div>
</div>

</div>

<div class="footer">Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Max Day = {MAX_DAY}</div>

<script>
var S = {series_json};

// ── Chart 1: Main Release Curve ──
Plotly.newPlot('chart-main', [
  {{x: S.day_axis, y: S.avg_curve, type: 'scatter', mode: 'lines+markers', name: '累计释放 %', line: {{color: '#9467bd', width: 2.5}}, marker: {{size: 3, color: '#9467bd'}}}},
  {{x: S.day_axis, y: S.daily_marginal, type: 'bar', name: '每日边际 %', marker: {{color: 'rgba(148,103,189,0.25)'}}, yaxis: 'y2'}},
], {{
  height: 380, margin: {{t: 20, r: 20, b: 60, l: 60}},
  legend: {{orientation: 'h', y: 1.05, x: 0}},
  hovermode: 'x unified',
  yaxis: {{title: '累计释放 %', range: [0, 120], fixedrange: true}},
  yaxis2: {{title: '每日边际 %', overlaying: 'y', side: 'right', range: [0, 120], fixedrange: true}},
  xaxis: {{title: '分配后天数', dtick: 5, fixedrange: true}},
}}, {{displayModeBar: false}});

// ── Chart 2: Year-over-Year ──
var yearTraces = [];
var yearColors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728'];
Object.keys(S.year_curves).forEach(function(y, i) {{
  yearTraces.push({{
    x: S.day_axis, y: S.year_curves[y], type: 'scatter', mode: 'lines',
    name: y + '年', line: {{color: yearColors[i % yearColors.length], width: 2}}
  }});
}});
Plotly.newPlot('chart-year', yearTraces, {{
  height: 350, margin: {{t: 20, r: 20, b: 60, l: 60}},
  legend: {{orientation: 'h', y: 1.05, x: 0}},
  hovermode: 'x unified',
  yaxis: {{title: '累计释放 %', range: [0, 120], fixedrange: true}},
  xaxis: {{title: '分配后天数', dtick: 5, fixedrange: true}},
}}, {{displayModeBar: false}});

// ── Chart 3: Scatter ──
Plotly.newPlot('chart-scatter', [
  {{x: S.scatter.dates, y: S.scatter.d0, type: 'scatter', mode: 'markers', name: 'D0释放率', marker: {{color: '#d62728', size: 4, opacity: 0.5}}}},
  {{x: S.scatter.dates, y: S.scatter.d7, type: 'scatter', mode: 'markers', name: 'D7释放率', marker: {{color: '#1f77b4', size: 4, opacity: 0.5}}}},
  {{x: S.scatter.dates, y: S.scatter.d14, type: 'scatter', mode: 'markers', name: 'D14释放率', marker: {{color: '#2ca02c', size: 4, opacity: 0.5}}}},
], {{
  height: 350, margin: {{t: 20, r: 20, b: 60, l: 60}},
  legend: {{orientation: 'h', y: 1.05, x: 0}},
  hovermode: 'x unified',
  yaxis: {{title: '释放率 (% of 30d total)', range: [0, 120], fixedrange: true}},
  xaxis: {{title: '分配日期', fixedrange: true}},
}}, {{displayModeBar: false}});

// ── Chart 4: Percentile ──
Plotly.newPlot('chart-percentile', [
  {{x: S.day_axis, y: S.percentiles.p90, type: 'scatter', mode: 'lines', name: 'P90',
    line: {{color: 'rgba(148,103,189,0.15)', width: 0}}, showlegend: false}},
  {{x: S.day_axis, y: S.percentiles.p10, type: 'scatter', mode: 'lines', name: 'P10',
    line: {{color: 'rgba(148,103,189,0.15)', width: 0}}, fill: 'tonexty', fillcolor: 'rgba(148,103,189,0.15)', showlegend: false}},
  {{x: S.day_axis, y: S.percentiles.p75, type: 'scatter', mode: 'lines', name: 'P75',
    line: {{color: 'rgba(148,103,189,0.25)', width: 0}}, showlegend: false}},
  {{x: S.day_axis, y: S.percentiles.p25, type: 'scatter', mode: 'lines', name: 'P25',
    line: {{color: 'rgba(148,103,189,0.25)', width: 0}}, fill: 'tonexty', fillcolor: 'rgba(148,103,189,0.25)', showlegend: false}},
  {{x: S.day_axis, y: S.percentiles.p50, type: 'scatter', mode: 'lines', name: 'P50 (中位数)',
    line: {{color: '#9467bd', width: 2.5, dash: 'dash'}}}},
  {{x: S.day_axis, y: S.avg_curve, type: 'scatter', mode: 'lines', name: '加权平均',
    line: {{color: '#d62728', width: 2}}}},
], {{
  height: 350, margin: {{t: 20, r: 20, b: 60, l: 60}},
  legend: {{orientation: 'h', y: 1.05, x: 0}},
  hovermode: 'x unified',
  yaxis: {{title: '累计释放 %', range: [0, 120], fixedrange: true}},
  xaxis: {{title: '分配后天数', dtick: 5, fixedrange: true}},
}}, {{displayModeBar: false}});

// ── Chart 5: Logistic Fit ──
if (S.logistic_fit.curve) {{
  Plotly.newPlot('chart-logistic', [
    {{x: S.day_axis, y: S.avg_curve, type: 'scatter', mode: 'markers', name: '实际值',
      marker: {{color: '#9467bd', size: 3, opacity: 0.6}}}},
    {{x: S.day_axis, y: S.logistic_fit.curve, type: 'scatter', mode: 'lines', name: 'Logistic拟合',
      line: {{color: '#d62728', width: 2}}}},
  ], {{
    height: 300, margin: {{t: 20, r: 20, b: 60, l: 60}},
    legend: {{orientation: 'h', y: 1.05, x: 0}},
    hovermode: 'x unified',
    yaxis: {{title: '累计释放 %', range: [0, 120], fixedrange: true}},
    xaxis: {{title: '分配后天数', dtick: 5, fixedrange: true}},
    annotations: [{{
      x: 25, y: 20, xref: 'x', yref: 'y',
      text: 'y = ' + S.logistic_fit.L.toFixed(1) + ' / (1 + exp(-' + S.logistic_fit.k.toFixed(4) + ' * (x - ' + S.logistic_fit.x0.toFixed(2) + ')))',
      showarrow: false, font: {{size: 11, color: '#666'}}
    }}],
  }}, {{displayModeBar: false}});
}} else {{
  document.getElementById('chart-logistic').innerHTML = '<p style="color:#999;padding:20px;">Logistic fit failed</p>';
}}

// ── Chart 6: DOW ──
var dowColors = ['#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd','#8c564b','#e377c2'];
var dowTraces = [];
S.dow_labels.forEach(function(label, i) {{
  dowTraces.push({{
    x: S.day_axis, y: S.dow_curves[label], type: 'scatter', mode: 'lines',
    name: label, line: {{color: dowColors[i % dowColors.length], width: 1.8}}
  }});
}});
Plotly.newPlot('chart-dow', dowTraces, {{
  height: 350, margin: {{t: 20, r: 20, b: 60, l: 60}},
  legend: {{orientation: 'h', y: 1.05, x: 0}},
  hovermode: 'x unified',
  yaxis: {{title: '累计释放 %', range: [0, 120], fixedrange: true}},
  xaxis: {{title: '分配后天数', dtick: 5, fixedrange: true}},
}}, {{displayModeBar: false}});

// ── Chart 7A: Lag Distribution Histogram ──
var lagStats = S.lag_stats;
Plotly.newPlot('chart-lag-dist', [
  {{x: S.lag_hist_x, y: S.lag_hist_y, type: 'bar', name: '占比 %',
    marker: {{color: 'rgba(148,103,189,0.5)'}}}},
], {{
  height: 350, margin: {{t: 20, r: 20, b: 60, l: 80}},
  hovermode: 'x unified',
  yaxis: {{title: '占全部锁单 %', fixedrange: true}},
  xaxis: {{title: '分配→锁单天数 (day_after)', dtick: 5, fixedrange: true}},
  shapes: [
    {{type: 'line', x0: lagStats.mean, y0: 0, x1: lagStats.mean, y1: 1, yref: 'paper',
      line: {{color: '#d62728', width: 2, dash: 'dash'}}}},
    {{type: 'line', x0: lagStats.p50, y0: 0, x1: lagStats.p50, y1: 1, yref: 'paper',
      line: {{color: '#1f77b4', width: 2, dash: 'dot'}}}},
    {{type: 'line', x0: lagStats.p80, y0: 0, x1: lagStats.p80, y1: 1, yref: 'paper',
      line: {{color: '#ff7f0e', width: 2, dash: 'dot'}}}},
    {{type: 'line', x0: lagStats.p90, y0: 0, x1: lagStats.p90, y1: 1, yref: 'paper',
      line: {{color: '#2ca02c', width: 2, dash: 'dot'}}}},
  ],
  annotations: [
    {{x: lagStats.mean, y: 0.95, xref: 'x', yref: 'paper', text: 'Mean=' + lagStats.mean.toFixed(1) + 'd',
      showarrow: false, font: {{size: 10, color: '#d62728'}}}},
    {{x: lagStats.p50, y: 0.88, xref: 'x', yref: 'paper', text: 'P50=' + lagStats.p50.toFixed(1) + 'd',
      showarrow: false, font: {{size: 10, color: '#1f77b4'}}}},
    {{x: lagStats.p80, y: 0.81, xref: 'x', yref: 'paper', text: 'P80=' + lagStats.p80.toFixed(1) + 'd',
      showarrow: false, font: {{size: 10, color: '#ff7f0e'}}}},
    {{x: lagStats.p90, y: 0.74, xref: 'x', yref: 'paper', text: 'P90=' + lagStats.p90.toFixed(1) + 'd',
      showarrow: false, font: {{size: 10, color: '#2ca02c'}}}},
  ],
}}, {{displayModeBar: false}});

// ── Chart 7B: Year-over-Year Lag Stats ──
var yearLabels = Object.keys(S.lag_year_stats).sort();
var yearMeans = yearLabels.map(function(y) {{ return S.lag_year_stats[y].mean; }});
var yearP50s = yearLabels.map(function(y) {{ return S.lag_year_stats[y].p50; }});
var yearP80s = yearLabels.map(function(y) {{ return S.lag_year_stats[y].p80; }});
var yearP90s = yearLabels.map(function(y) {{ return S.lag_year_stats[y].p90; }});
Plotly.newPlot('chart-lag-year', [
  {{x: yearLabels, y: yearP90s, type: 'scatter', mode: 'lines+markers', name: 'P90',
    line: {{color: '#2ca02c', width: 2}}, marker: {{size: 6}}}},
  {{x: yearLabels, y: yearP80s, type: 'scatter', mode: 'lines+markers', name: 'P80',
    line: {{color: '#ff7f0e', width: 2}}, marker: {{size: 6}}}},
  {{x: yearLabels, y: yearMeans, type: 'scatter', mode: 'lines+markers', name: 'Mean',
    line: {{color: '#d62728', width: 2}}, marker: {{size: 6}}}},
  {{x: yearLabels, y: yearP50s, type: 'scatter', mode: 'lines+markers', name: 'P50 (中位数)',
    line: {{color: '#1f77b4', width: 2, dash: 'dash'}}, marker: {{size: 6}}}},
], {{
  height: 350, margin: {{t: 20, r: 20, b: 60, l: 60}},
  legend: {{orientation: 'h', y: 1.05, x: 0}},
  hovermode: 'x unified',
  yaxis: {{title: '传导时滞 (天)', fixedrange: true}},
  xaxis: {{title: '分配年份', fixedrange: true}},
}}, {{displayModeBar: false}});

</script>
</body>
</html>
"""

with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)

print(f"  Report saved: {OUTPUT_HTML} ({len(html):,} bytes)")
print("\nDone!")
