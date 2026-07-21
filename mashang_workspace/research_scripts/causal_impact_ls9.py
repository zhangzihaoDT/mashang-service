"""
name: causal_impact_ls9
use: python research_scripts/causal_impact_ls9.py
summary: 合成控制法评估 LS9 Hyper 上市对 LS9 锁单的因果效应。
  用 LS6、L6、LS8 等车系的日锁单构成 donor pool，
  在预处理期（LS9 上市 ~ Hyper 上市前）拟合权重，
  预测 Hyper 上市后的反事实锁单量，计算 ATE。

两步走：
  1. 总效果识别 — 合成控制 ATE
  2. 机制分解 — 线索效应 / 份额效应 / 交互效应
"""

import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

plt.rcParams["font.family"] = "PingFang HK"
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[1]

# ── 颜色 ──
C_BLUE = "#174A7C"
C_GOLD = "#D79A36"
C_CYAN = "#7ECDEB"
C_CREAM = "#FFF9EF"


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    odf = pd.read_parquet(ROOT.parent / "dataset" / "order_data.parquet")
    odf["lock_date"] = odf["lock_time"].dt.date
    adf = pd.read_csv(ROOT.parent / "dataset" / "assign_data.csv")
    adf["date"] = pd.to_datetime(adf["Assign Time 年/月/日"], format="%Y年%m月%d日")
    return odf, adf


def build_daily_panel(
    odf: pd.DataFrame,
    adf: pd.DataFrame,
    target_series: str = "LS9",
    donor_series: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    if donor_series is None:
        donor_series = ["LS6", "L6", "LS8"]
    all_series = [target_series] + donor_series

    # Daily locks per series
    daily = odf.groupby(["lock_date", "series"]).size().unstack(fill_value=0)
    for s in all_series:
        if s not in daily.columns:
            daily[s] = 0
    daily = daily[all_series].copy()
    daily.index = pd.to_datetime(daily.index)
    daily = daily.sort_index()

    # Add total leads as predictor
    adf_daily = adf.set_index("date")["下发线索数"]
    daily["leads"] = adf_daily.reindex(daily.index).ffill()

    if start:
        daily = daily[daily.index >= pd.Timestamp(start)]
    if end:
        daily = daily[daily.index <= pd.Timestamp(end)]

    daily.columns.name = None
    return daily


def synthetic_control(
    panel: pd.DataFrame,
    target: str = "LS9",
    donor_cols: list[str] | None = None,
    treatment_date: date = date(2026, 7, 16),
) -> dict:
    if donor_cols is None:
        donor_cols = ["LS6", "L6", "LS8"]

    pre = panel[panel.index < pd.Timestamp(treatment_date)].copy()
    post = panel[panel.index >= pd.Timestamp(treatment_date)].copy()

    # Scale: divide each donor by its pre-treatment mean so all are ~1
    scales = {c: pre[c].mean() for c in donor_cols + [target]}
    for c in donor_cols + [target]:
        if scales[c] > 0:
            pre[c] = pre[c] / scales[c]
            if c in post.columns:
                post[c] = post[c] / scales[c]

    y_pre = pre[target].values
    X_pre = pre[donor_cols].values
    y_post = post[target].values
    X_post = post[donor_cols].values
    post_dates = post.index

    n_donors = len(donor_cols)

    def objective(w):
        pred = X_pre @ w
        return np.sum((y_pre - pred) ** 2) + 1e-6 * np.sum(w ** 2)  # small ridge

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = [(0, 1)] * n_donors
    w0 = np.ones(n_donors) / n_donors

    # Try multiple starting points for robustness
    best_result = None
    best_val = np.inf
    for seed_offset in range(5):
        np.random.seed(42 + seed_offset)
        w0_r = np.random.dirichlet(np.ones(n_donors))
        res = minimize(objective, w0_r, bounds=bounds, constraints=constraints, method="SLSQP", options={"maxiter": 2000})
        if res.fun < best_val:
            best_val = res.fun
            best_result = res

    weights = best_result.x
    # Rescale weights back to original scale
    raw_weights = weights / scales[target]
    for i, c in enumerate(donor_cols):
        raw_weights[i] = raw_weights[i] * scales[c]

    # Counterfactual on original scale
    cf_pre = X_pre @ weights * scales[target]
    cf_post = X_post @ weights * scales[target]
    actual_pre = y_pre * scales[target]
    actual_post = y_post * scales[target]

    mse = np.mean((actual_pre - cf_pre) ** 2)
    rmse = np.sqrt(mse)

    ate = actual_post - cf_post
    avg_ate = np.mean(ate)
    cumulative_ate = np.cumsum(ate)

    return {
        "weights": dict(zip(donor_cols, weights)),
        "pre_mse": mse,
        "pre_rmse": rmse,
        "pre_period": f"{pre.index[0].date()} ~ {pre.index[-1].date()}",
        "post_period": f"{post_dates[0].date()} ~ {post_dates[-1].date()}",
        "post_dates": post_dates,
        "actual": actual_post,
        "counterfactual": cf_post,
        "ate": ate,
        "avg_ate": avg_ate,
        "cumulative_ate": cumulative_ate,
        "pre_actual": actual_pre,
        "pre_pred": cf_pre,
        "pre_mean": actual_pre.mean(),
    }


def plot_results(result: dict, target: str = "LS9", output: str | None = None):
    treatment_date = date(2026, 7, 16)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.patch.set_facecolor(C_CREAM)

    # Top: actual vs counterfactual
    ax1.set_facecolor(C_CREAM)
    pre_dates = pd.date_range(
        end=pd.Timestamp(treatment_date) - pd.Timedelta(days=1),
        periods=len(result["pre_actual"]),
        freq="D",
    )
    ax1.plot(pre_dates, result["pre_actual"], color=C_BLUE, linewidth=1.2, alpha=0.7)
    ax1.plot(result["post_dates"], result["actual"], color=C_BLUE, linewidth=1.8, label="实际值")
    ax1.plot(result["post_dates"], result["counterfactual"], color=C_GOLD, linewidth=1.8, linestyle="--", label="反事实（合成控制）")
    ax1.axvline(pd.Timestamp(treatment_date), color="#999", linewidth=1, linestyle=":", alpha=0.6)
    ax1.text(pd.Timestamp(treatment_date), ax1.get_ylim()[1] * 0.95, "Hyper 上市", fontsize=9, color="#999", ha="right")
    ax1.fill_between(result["post_dates"], result["actual"], result["counterfactual"],
                      color=C_GOLD, alpha=0.15, label=f"ATE(日均)={result['avg_ate']:.1f}")
    ax1.set_ylabel(f"{target} 日锁单数", fontsize=11, color=C_BLUE)
    ax1.legend(fontsize=10, framealpha=0.8)
    ax1.grid(True, alpha=0.1, color="#6B7C8F")
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    # Bottom: cumulative ATE
    ax2.set_facecolor(C_CREAM)
    ax2.fill_between(result["post_dates"], 0, result["cumulative_ate"],
                      color=C_GOLD, alpha=0.3)
    ax2.plot(result["post_dates"], result["cumulative_ate"], color=C_GOLD, linewidth=1.8)
    ax2.axhline(0, color="#999", linewidth=0.8, linestyle="--")
    total = result["cumulative_ate"][-1]
    ax2.annotate(f"累计ATE: {total:.0f}",
                 xy=(result["post_dates"][-1], total),
                 xytext=(8, 0), textcoords="offset points",
                 fontsize=11, color=C_GOLD, fontweight="bold", va="center")
    ax2.set_ylabel("累计 ATE（锁单数）", fontsize=11, color=C_BLUE)
    ax2.set_xlabel("日期", fontsize=11, color="#6B7C8F")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax2.grid(True, alpha=0.1, color="#6B7C8F")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    plt.suptitle(f"{target} 锁单 — 合成控制法因果效应", fontsize=15, color=C_BLUE, fontweight="bold", y=1.01)
    plt.tight_layout()

    if output:
        plt.savefig(output, dpi=150, bbox_inches="tight")
        print(f"图表已保存: {output}")
    else:
        plt.show()
    plt.close()


def decompose_mechanism(
    odf: pd.DataFrame,
    adf: pd.DataFrame,
    target: str = "LS9",
    base_start: date = date(2026, 6, 21),
    base_end: date = date(2026, 7, 15),
    near_start: date = date(2026, 7, 16),
    near_end: date = date(2026, 7, 20),
) -> dict:
    """ATE 确认后，分解机制：线索效应 × LS9 份额效应 × 交互"""
    def period_stats(s, e):
        leads = adf[(adf["date"].dt.date >= s) & (adf["date"].dt.date <= e)]["下发线索数"]
        locks = len(odf[(odf["lock_date"] >= s) & (odf["lock_date"] <= e) & (odf["series"] == target) & (odf["order_type"] == "用户车")])
        days = (e - s).days + 1
        dl = leads.sum() / days
        ll = locks / days
        return dl, ll, ll / dl if dl else 0

    dl_b, ll_b, cv_b = period_stats(base_start, base_end)
    dl_n, ll_n, cv_n = period_stats(near_start, near_end)

    delta = ll_n - ll_b
    le = (dl_n - dl_b) * cv_b
    ce = (cv_n - cv_b) * dl_b
    ia = (dl_n - dl_b) * (cv_n - cv_b)

    return {
        "period_base": f"{base_start} ~ {base_end}",
        "period_near": f"{near_start} ~ {near_end}",
        "base_daily_leads": round(dl_b),
        "base_daily_locks": round(ll_b, 1),
        "base_conv": round(cv_b * 100, 4),
        "near_daily_leads": round(dl_n),
        "near_daily_locks": round(ll_n, 1),
        "near_conv": round(cv_n * 100, 4),
        "total_delta": round(delta, 1),
        "leads_effect": round(le, 1),
        "conv_effect": round(ce, 1),
        "interaction": round(ia, 1),
        "leads_pct": round(le / delta * 100, 1),
        "conv_pct": round(ce / delta * 100, 1),
        "interact_pct": round(ia / delta * 100, 1),
    }


def format_output(sc_result: dict, mech: dict | None = None) -> str:
    w = sc_result["weights"]
    w_str = "  ".join(f"{k}={v:.3f}" for k, v in sorted(w.items(), key=lambda x: -x[1]))
    lines = [
        "=" * 60,
        "  合成控制法因果推断 — LS9 Hyper 上市效应",
        "=" * 60,
        "",
        f"  预处理期: {sc_result['pre_period']}",
        f"  处理期:   {sc_result['post_period']}",
        "",
        "  ── Donor Weights ──",
        f"  {w_str}",
        f"  预处理 RMSE: {sc_result['pre_rmse']:.2f}",
        "",
        "  ── ATE ──",
        f"  日均 ATE: {sc_result['avg_ate']:+.1f} 锁单/日",
    ]

    if len(sc_result["actual"]) > 0:
        total_actual = sc_result["actual"].sum()
        total_cf = sc_result["counterfactual"].sum()
        total_ate = sc_result["cumulative_ate"][-1]
        lift_pct = (total_actual / total_cf - 1) * 100 if total_cf else 0
        lines += [
            f"  实际合计:  {total_actual:.0f} 锁单",
            f"  反事实合计: {total_cf:.0f} 锁单",
            f"  ATE(累计): {total_ate:+.0f} 锁单 ({lift_pct:+.1f}%)",
            "",
            f"  ── 对照: 预处理期均值法 ──",
            f"  预处理日均: {sc_result.get('pre_mean', 0):.1f}",
            f"  后处理期日均: {sc_result['actual'].mean():.1f}",
            f"  ATE(均值法): {sc_result['actual'].mean() - sc_result.get('pre_mean', 0):+.1f}/日",
        ]

    if mech:
        lines += [
            "",
            "  ── 机制分解 (D0~D4 vs 06-21~07-15) ──",
            f"  总增量: {mech['total_delta']:+.1f} 锁单/日",
            f"    ① 线索量效应: +{mech['leads_effect']:.1f} ({mech['leads_pct']}%)",
            f"    ② LS9份额效应: +{mech['conv_effect']:.1f} ({mech['conv_pct']}%)",
            f"    ③ 交互效应:   +{mech['interaction']:.1f} ({mech['interact_pct']}%)",
        ]
    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="LS9")
    p.add_argument("--donors", nargs="*", default=["LS6", "L6", "LS8"])
    p.add_argument("--treatment-date", default="2026-07-16")
    p.add_argument("--start", default="2026-01-01",
                    help="预处理期起始日（默认 2026-01-01 排除上市初期的极端峰值）")
    p.add_argument("--output-chart", default=str(ROOT / "outputs" / "charts" / "causal_impact_ls9.png"))
    p.add_argument("--decompose", action="store_true", default=True)
    args = p.parse_args()

    odf, adf = load_data()
    treatment = date.fromisoformat(args.treatment_date)
    start = date.fromisoformat(args.start)

    # Step 1: Synthetic control
    panel = build_daily_panel(odf, adf, target_series=args.target, donor_series=args.donors, start=start)
    sc_result = synthetic_control(panel, target=args.target, treatment_date=treatment)

    # Step 2: Mechanism decomposition
    mech = None
    if args.decompose:
        base_start = treatment - timedelta(days=25)
        base_end = treatment - timedelta(days=1)
        near_end = treatment + timedelta(days=4)
        mech = decompose_mechanism(odf, adf, target=args.target,
                                    base_start=base_start, base_end=base_end,
                                    near_start=treatment, near_end=near_end)

    print(format_output(sc_result, mech))

    if args.output_chart:
        plot_results(sc_result, target=args.target, output=args.output_chart)

