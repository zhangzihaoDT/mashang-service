import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib
matplotlib.rcParams["font.family"] = "Heiti TC"
matplotlib.rcParams["axes.unicode_minus"] = False

from operators.assign_conversion import _parse_cn_date, _sum_col, _sum_any
from operators.mature_lock_prediction import run_mature_lock_prediction_operator

ROOT = os.path.join(os.path.dirname(__file__), "..")

# ── 1. 加载数据 ──
print("Loading data ...")
df_assign = pd.read_csv(os.path.join(ROOT, "dataset", "assign_data.csv"))
odf = pd.read_parquet(os.path.join(ROOT, "dataset", "order_data.parquet"))

odf = odf[odf["first_assign_time"].notna() & odf["lock_time"].notna()].copy()
odf["assign_date"] = odf["first_assign_time"].dt.normalize()
odf["lock_date"] = odf["lock_time"].dt.normalize()

# ── 2. 解析 assign_data ──
work = df_assign.copy()
work["_date"] = _parse_cn_date(work["Assign Time 年/月/日"])
work = work[work["_date"].notna()].sort_values("_date").reset_index(drop=True)
snapshot_date = work["_date"].max()

# ── 3. 构建每日指标 ──
print("Building daily metrics ...")
rows = []
for _, r in work.iterrows():
    day_df = pd.DataFrame([r])
    col_map = {str(c).strip(): c for c in day_df.columns}
    leads = float(_sum_col(day_df, col_map, "下发线索数"))
    lock0 = float(_sum_any(day_df, col_map, ["下发线索当日锁单数 (门店)", "下发线索当日锁单数"]))
    lock7 = float(_sum_col(day_df, col_map, "下发线索 7 日锁单数"))
    lock30 = float(_sum_col(day_df, col_map, "下发线索 30 日锁单数"))
    rows.append({
        "date": r["_date"],
        "leads": leads,
        "lock0": lock0,
        "lock7": lock7,
        "lock30": lock30,
    })
metrics = pd.DataFrame(rows)

# ── 4. 计算历史基准（用全部成熟 cohort） ──
mature = metrics[metrics["lock30"] > 0].copy()
avg_30d_rate = mature["lock30"].sum() / mature["leads"].sum()
r7 = mature["lock7"].sum() / mature["lock30"].sum()
r0 = mature["lock0"].sum() / mature["lock30"].sum()
print(f"  avg_30d_rate = {avg_30d_rate:.4f}  r7 = {r7:.4f}  r0 = {r0:.4f}")

# ── 5. 回测窗口：1年 ──
BT_START = "2025-04-19"
BT_END = "2026-04-20"
bt_metrics = metrics[
    (metrics["date"] >= pd.Timestamp(BT_START)) &
    (metrics["date"] < pd.Timestamp(BT_END))
].copy().reset_index(drop=True)

# 预测：核心公式 pred30 = lock7 / r7
bt_metrics["pred30"] = np.where(
    bt_metrics["lock7"] > 0,
    bt_metrics["lock7"] / r7,
    bt_metrics["leads"] * avg_30d_rate,
)

# order_data 实际锁单数
print("Computing order_data actuals ...")
date_to_actual = {}
for d_ts in bt_metrics["date"]:
    mask = odf["assign_date"] == d_ts
    date_to_actual[d_ts] = int(mask.sum())
bt_metrics["actual"] = bt_metrics["date"].map(date_to_actual)

bt_dates_str = bt_metrics["date"].dt.strftime("%Y-%m-%d").tolist()
bt_dates_dt  = bt_metrics["date"].tolist()
bt_leads     = bt_metrics["leads"].tolist()
bt_pred30    = bt_metrics["pred30"].tolist()
bt_actual    = bt_metrics["actual"].tolist()
bt_lock7     = bt_metrics["lock7"].tolist()
bt_lock30    = bt_metrics["lock30"].tolist()

# ── 6. 误差统计 ──
errors_abs = [abs(p - a) for p, a in zip(bt_pred30, bt_actual)]
errors_pct = [abs(p - a) / a if a > 0 else None for p, a in zip(bt_pred30, bt_actual)]
mae  = np.mean(errors_abs)
rmse = np.sqrt(np.mean([e**2 for e in errors_abs]))
valid_pct = [e for e in errors_pct if e is not None]
mape = np.mean(valid_pct) * 100 if valid_pct else 0

# 按月聚合误差
bt_metrics["month"] = bt_metrics["date"].dt.to_period("M")
monthly_err = bt_metrics.groupby("month").apply(
    lambda g: pd.Series({
        "count": len(g),
        "MAE": abs(g["pred30"] - g["actual"]).mean(),
        "MAPE": (abs(g["pred30"] - g["actual"]) / g["actual"].replace(0, np.nan)).mean() * 100,
        "RMSE": np.sqrt(((g["pred30"] - g["actual"]) ** 2).mean()),
    }), include_groups=False
)

print(f"\n  1年回测: days={len(bt_metrics)}  MAE={mae:.1f}  RMSE={rmse:.1f}  MAPE={mape:.1f}%")
print(f"\n  按月误差:")
for m, row in monthly_err.iterrows():
    print(f"    {m}: n={int(row['count']):3d}  MAE={row['MAE']:6.1f}  RMSE={row['RMSE']:6.1f}  MAPE={row['MAPE']:5.1f}%")

# ── 7. 也跑一个 30 天完整算子回测 ──
SIM_SNAPSHOT = "2026-04-19"
OP_START, OP_END = "2026-03-21", "2026-04-20"
df_trunc = df_assign[
    _parse_cn_date(df_assign["Assign Time 年/月/日"]) < pd.Timestamp(SIM_SNAPSHOT)
].copy()
op_result = run_mature_lock_prediction_operator(df_trunc, OP_START, OP_END)
op_rows = op_result["daily_rows"]
op_dates  = [r["date"]            for r in op_rows]
op_pred30 = [r["预测30日锁单数"]    for r in op_rows]
op_ages   = [r["cohort年龄"]       for r in op_rows]
op_methods = [r["预测方法"]        for r in op_rows]
op_actual = []
for d_str in op_dates:
    d_ts = pd.Timestamp(d_str)
    mask = odf["assign_date"] == d_ts
    op_actual.append(int(mask.sum()))
op_mae = np.mean([abs(p - a) for p, a in zip(op_pred30, op_actual)])

# ── 8. 绘图 ──
fig = plt.figure(figsize=(20, 14))
gs = fig.add_gridspec(3, 4, height_ratios=[1.3, 0.3, 1], width_ratios=[2, 1, 1, 1])

# ── 主图：1年回测 ──
ax1 = fig.add_subplot(gs[0, :])
ax1b = ax1.twinx()
ax1b.bar(bt_dates_dt, bt_leads, alpha=0.12, color="#9E9E9E", width=0.6, label="下发线索数")
ax1b.set_ylabel("下发线索数", fontsize=11, color="#666666")
ax1b.tick_params(axis="y", colors="#666666")

ax1.plot(bt_dates_dt, bt_actual, label="实际锁单数（order_data）",
         marker=".", linestyle="-", linewidth=1.5, color="#4CAF50", alpha=0.8)
ax1.plot(bt_dates_dt, bt_pred30, label="预测30日锁单数（lock7 / r7）",
         marker=".", linestyle="--", linewidth=1.5, color="#FF5722", alpha=0.7)
ax1.fill_between(bt_dates_dt, bt_pred30, bt_actual, alpha=0.08, color="#FF5722")

ax1.axvline(pd.Timestamp("2026-03-21"), color="blue", linestyle=":", linewidth=1, alpha=0.5,
            label="完整算子回测区间→")
ax1.axvline(pd.Timestamp("2026-04-19"), color="blue", linestyle=":", linewidth=1, alpha=0.5)

ax1.set_ylabel("锁单数", fontsize=12)
ax1.set_title(f"1年回测 ({BT_START} ~ {BT_END[:-3]})  实际 vs 预测 (core: lock7/r7)",
              fontsize=14, fontweight="bold")
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax1b.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc="upper left")
ax1.grid(True, alpha=0.3)
ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=8)

info_text = (
    f"历史基准 (全量成熟cohort):\n"
    f"  avg_30d_rate = {avg_30d_rate:.2%}\n"
    f"  r7 (7d/30d)  = {r7:.2%}\n"
    f"  r0 (0d/30d)  = {r0:.2%}\n\n"
    f"1年回测 ({len(bt_metrics)}天):\n"
    f"  MAE  = {mae:.1f}\n"
    f"  RMSE = {rmse:.1f}\n"
    f"  MAPE = {mape:.1f}%\n\n"
    f"核心假设: lock30 ≈ lock7 / r7\n"
    f"预测值 = lock7 / r7 (lock7>0时)\n"
    f"       = leads × avg_rate (lock7=0时)"
)
ax1.annotate(info_text, xy=(0.015, 0.97), xycoords="axes fraction",
             fontsize=8.5, va="top", ha="left",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="wheat", alpha=0.85),
             fontfamily="Heiti TC")

# ── 月度误差折线 ──
ax_m = fig.add_subplot(gs[1, :])
months_str = [str(m) for m in monthly_err.index]
ax_m.plot(months_str, monthly_err["MAPE"], marker="o", linestyle="-", linewidth=2, color="#FF5722")
ax_m.axhline(mape, color="red", linestyle="--", linewidth=1, alpha=0.6, label=f"全年MAPE={mape:.1f}%")
ax_m.set_ylabel("MAPE(%)", fontsize=11, color="#FF5722")
ax_m.set_title("月度预测误差 MAPE", fontsize=12, fontweight="bold")
ax_m.grid(True, alpha=0.3)
ax_m.legend(fontsize=9)
ax_m.set_xticks(range(len(months_str)))
ax_m.set_xticklabels(months_str, rotation=45, ha="right", fontsize=7.5)

# ── 散点图 ──
ax2 = fig.add_subplot(gs[2, 0])
ax2.scatter(bt_actual, bt_pred30, c="#FF5722", s=8, alpha=0.5, edgecolors="none", zorder=3)
lims = [min(min(bt_actual), min(bt_pred30)) * 0.9,
        max(max(bt_actual), max(bt_pred30)) * 1.1]
ax2.plot(lims, lims, "k--", linewidth=1, alpha=0.4, label="perfect")
ax2.set_xlim(lims)
ax2.set_ylim(lims)
ax2.set_xlabel("实际锁单数", fontsize=11)
ax2.set_ylabel("预测30日锁单数", fontsize=11)
ax2.set_title(f"散点 (n={len(bt_actual)})", fontsize=12, fontweight="bold")
ax2.grid(True, alpha=0.3)
ax2.legend(fontsize=8)
ax2.set_aspect("equal")

# ── 误差分布 ──
ax3 = fig.add_subplot(gs[2, 1])
ax3.hist(errors_abs, bins=20, color="#FF5722", alpha=0.7, edgecolor="white")
ax3.axvline(mae, color="red", linestyle="--", linewidth=1.5, label=f"MAE={mae:.1f}")
ax3.axvline(rmse, color="darkred", linestyle=":", linewidth=1.5, label=f"RMSE={rmse:.1f}")
ax3.set_xlabel("绝对误差", fontsize=11)
ax3.set_ylabel("频次", fontsize=11)
ax3.set_title(f"误差分布 (MAPE={mape:.1f}%)", fontsize=12, fontweight="bold")
ax3.legend(fontsize=8)
ax3.grid(True, alpha=0.3)

# ── 误差 vs 线索量 ──
ax4 = fig.add_subplot(gs[2, 2])
ax4.scatter(bt_leads, [abs(p - a) for p, a in zip(bt_pred30, bt_actual)],
            c="#FF5722", s=8, alpha=0.5, edgecolors="none")
ax4.set_xlabel("下发线索数", fontsize=11)
ax4.set_ylabel("|预测误差|", fontsize=11)
ax4.set_title("误差 vs 线索量", fontsize=12, fontweight="bold")
ax4.grid(True, alpha=0.3)

# ── 完整算子回测（30天）对比 ──
ax5 = fig.add_subplot(gs[2, 3])
ax5.plot(op_dates, op_actual, label="实际", marker="^", linestyle="-", linewidth=2, color="#4CAF50")
ax5.plot(op_dates, op_pred30, label="算子预测", marker="s", linestyle="--", linewidth=2, color="#FF5722")
ax5.set_title(f"完整算子回测 (MAE={op_mae:.1f})", fontsize=11, fontweight="bold")
ax5.legend(fontsize=8)
ax5.grid(True, alpha=0.3)
ax5.set_xticks(range(len(op_dates)))
ax5.set_xticklabels(op_dates, rotation=45, ha="right", fontsize=6)

plt.tight_layout()
out_path = os.path.join(os.path.dirname(__file__), "predicted_lock_comparison.png")
plt.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"\nChart saved: {out_path}")

# ── 9. 近30日锁单数曲线 ──
print("\n近30日锁单数曲线 ...")
RECENT_START, RECENT_END = "2026-04-19", "2026-05-20"
recent_result = run_mature_lock_prediction_operator(df_assign, RECENT_START, RECENT_END)
recent_rows = recent_result["daily_rows"]
recent_dates  = [r["date"]            for r in recent_rows]
recent_pred30 = [r["预测30日锁单数"]    for r in recent_rows]
recent_raw30  = [r["原始30日锁单数"]   for r in recent_rows]
recent_ages   = [r["cohort年龄"]       for r in recent_rows]
recent_methods = [r["预测方法"]        for r in recent_rows]
recent_leads  = [r["下发线索数"]       for r in recent_rows]

recent_actual = []
for d_str in recent_dates:
    d_ts = pd.Timestamp(d_str)
    mask = odf["lock_date"] == d_ts
    recent_actual.append(int(mask.sum()))

fig2, ax_r = plt.subplots(figsize=(16, 6))
ax_rb = ax_r.twinx()
ax_rb.bar(recent_dates, recent_leads, alpha=0.15, color="#9E9E9E", width=0.6, label="下发线索数")
ax_rb.set_ylabel("下发线索数", fontsize=11, color="#666666")
ax_rb.tick_params(axis="y", colors="#666666")

ax_r.plot(recent_dates, recent_actual, label="实际锁单数（order_data, 按lock_time日汇总）",
          marker="^", linestyle="-", linewidth=2.5, color="#4CAF50")
ax_r.plot(recent_dates, recent_raw30, label="原始30日锁单数（assign_data, 右删失）",
          marker="o", linestyle="--", linewidth=1.5, color="#888888", alpha=0.6)
ax_r.plot(recent_dates, recent_pred30, label="预测30日锁单数（成熟度修正）",
          marker="s", linestyle="--", linewidth=2, color="#FF5722")
ax_r.fill_between(recent_dates, recent_pred30, recent_actual, alpha=0.1, color="#FF5722")

method_colors_r = {
    "actual": "#27ae60",
    "projected_via_7d": "#f39c12",
    "weighted_avg_and_day0": "#e74c3c",
    "estimated_via_avg": "#e74c3c",
}
for i, (age, m) in enumerate(zip(recent_ages, recent_methods)):
    c = method_colors_r.get(m, "#999")
    ax_r.annotate(str(age), (i, recent_pred30[i]),
                  textcoords="offset points", xytext=(0, 10),
                  fontsize=7, color=c, ha="center", fontweight="bold")

ax_r.set_ylabel("锁单数", fontsize=13)
ax_r.set_title(f"近30日锁单数曲线 ({RECENT_START} ~ {RECENT_END[:-3]})\n"
               f"点上数字=cohort年龄  绿=actual  橙=projected_via_7d  红=age<7d",
               fontsize=14, fontweight="bold")
lines1_r, labels1_r = ax_r.get_legend_handles_labels()
lines2_r, labels2_r = ax_rb.get_legend_handles_labels()
ax_r.legend(lines1_r + lines2_r, labels1_r + labels2_r, fontsize=10, loc="upper left")
ax_r.grid(True, alpha=0.3)
ax_r.set_xticks(range(len(recent_dates)))
ax_r.set_xticklabels(recent_dates, rotation=45, ha="right", fontsize=7.5)

r_mae = np.mean([abs(p - a) for p, a in zip(recent_pred30, recent_actual)])
r_info = (
    f"快照日期: {recent_result['snapshot_date']}\n"
    f"历史基准:\n"
    f"  avg_30d_rate = {recent_result['mature_cohort_stats']['历史平均30日锁单率']:.2%}\n"
    f"  r7 = {recent_result['mature_cohort_stats']['7日占30日比例(r7)']:.2%}\n"
    f"  r0 = {recent_result['mature_cohort_stats']['当日占30日比例(r0)']:.2%}\n\n"
    f"近30日 MAE = {r_mae:.1f}\n\n"
    f"预测规则:\n"
    f"  ≥30d: 原始30日锁单数\n"
    f"  ≥7d:  lock7 / r7\n"
    f"  <7d:  0.5×avg + 0.5×lock0/r0"
)
ax_r.annotate(r_info, xy=(0.015, 0.97), xycoords="axes fraction",
              fontsize=8.5, va="top", ha="left",
              bbox=dict(boxstyle="round,pad=0.5", facecolor="wheat", alpha=0.85),
              fontfamily="Heiti TC")

plt.tight_layout()
recent_out = os.path.join(os.path.dirname(__file__), "predicted_lock_recent_30d.png")
plt.savefig(recent_out, dpi=150, bbox_inches="tight")
print(f"Recent chart saved: {recent_out}")

# ── 终端 ──
print(f"\n{'='*60}")
print(f"1年回测结果 ({BT_START}~{BT_END[:-3]}, n={len(bt_metrics)})")
print(f"{'':-^80}")
print(f"{'月份':<8} {'n':>4} {'MAE':>8} {'RMSE':>8} {'MAPE':>7}")
for m, row in monthly_err.iterrows():
    print(f"{str(m):<8} {int(row['count']):>4} {row['MAE']:>8.1f} {row['RMSE']:>8.1f} {row['MAPE']:>6.1f}%")
print(f"{'全年':<8} {len(bt_metrics):>4} {mae:>8.1f} {rmse:>8.1f} {mape:>6.1f}%")

print(f"\n完整算子回测 (模拟快照={SIM_SNAPSHOT}, 窗口={OP_START}~{OP_END[:-3]})")
print(f"{'日期':<12} {'actual':>8} {'pred30':>8} {'diff':>8} {'age':>3} {'方法':<22}")
for i in range(len(op_dates)):
    diff = op_pred30[i] - op_actual[i]
    print(f"{op_dates[i]:<12} {op_actual[i]:>8} {op_pred30[i]:>8.1f} {diff:>+8.1f} {op_ages[i]:>3} {op_methods[i]:<22}")
print(f"  MAE = {op_mae:.1f}")
