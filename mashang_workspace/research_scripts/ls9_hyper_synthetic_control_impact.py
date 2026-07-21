"""
name: ls9_hyper_synthetic_control_impact
use: python research_scripts/ls9_hyper_synthetic_control_impact.py

summary:
  探索性评估 LS9 Hyper 上市后 LS9 锁单的变化。

  第一部分使用 LS6、L6、LS8 等车系的日锁单序列构造合成对照，
  估计 LS9 在 Hyper 上市后的反事实锁单，并计算处理后日均估计增量
  与累计估计增量。

  第二部分对实际前后观察期的 LS9 锁单变化进行经营因子分解：
  LS9 锁单 = 全量下发线索 × LS9 线索捕获率。

  注意：
  该经营分解是描述性的前后期恒等式分解，并非对合成控制因果效应
  的中介机制识别。

analysis_steps:
  1. 合成控制反事实估计
  2. 处理后锁单增量测算
  3. 前后期经营因子分解
"""

import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
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
    target_series: str = "LS9",
    donor_series: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    if donor_series is None:
        donor_series = ["LS6", "L6", "LS8"]
    all_series = [target_series] + donor_series

    daily = odf.groupby(["lock_date", "series"]).size().unstack(fill_value=0)
    for s in all_series:
        if s not in daily.columns:
            daily[s] = 0
    daily = daily[all_series].copy()
    daily.index = pd.to_datetime(daily.index)
    daily = daily.sort_index()
    daily["dow"] = daily.index.dayofweek  # Mon=0, Sun=6

    if start:
        daily = daily[daily.index >= pd.Timestamp(start)]
    if end:
        daily = daily[daily.index <= pd.Timestamp(end)]

    daily.columns.name = None
    return daily


def _deseasonalize(
    panel: pd.DataFrame, series_list: list[str], base_start: date, base_end: date
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """按星期去季节化：计算各车系各星期的因子，除以因子得到去季节化序列。

    返回 (去季节化 panel, {车系: dow_factors})，dow_factors[0]=周一因子。
    """
    base = panel.loc[pd.Timestamp(base_start):pd.Timestamp(base_end)]
    panel = panel.copy()
    factors: dict[str, np.ndarray] = {}
    for s in series_list:
        dow_mean = np.array([base.loc[base["dow"] == d, s].mean() for d in range(7)])
        overall = base[s].mean()
        # Avoid division by zero; minimum factor = 0.3
        dow_factor = np.maximum(dow_mean / max(overall, 1), 0.3)
        factors[s] = dow_factor
        panel[s] = panel[s].values / panel["dow"].map({d: factors[s][d] for d in range(7)}).values
    return panel, factors


def synthetic_control(
    panel: pd.DataFrame,
    target: str = "LS9",
    donor_cols: list[str] | None = None,
    treatment_date: date = date(2026, 7, 16),
    weight_base_start: date = date(2026, 6, 21),
    weight_base_end: date = date(2026, 7, 15),
) -> dict:
    """合成控制：星期去季节化 + 基期比例赋权 + 量级缩放。

    步骤：
      1. 在基期内计算各车系的星期因子（dow_factor）
      2. 用因子去除各序列的季节性
      3. 在去季节化数据上计算权重和反事实
      4. 用 LS9 的星期因子将反事实加回季节性
    """
    if donor_cols is None:
        donor_cols = ["LS6", "L6", "LS8"]
    all_series = [target] + donor_cols

    # 1. Deseasonalize
    panel_ds, dow_factors = _deseasonalize(panel, all_series, weight_base_start, weight_base_end)
    ls9_factor = dow_factors[target]

    base = panel_ds.loc[pd.Timestamp(weight_base_start):pd.Timestamp(weight_base_end)]
    pre = panel_ds[panel_ds.index < pd.Timestamp(treatment_date)].copy()
    post = panel_ds[panel_ds.index >= pd.Timestamp(treatment_date)].copy()
    post_dates = post.index

    # 2. Weights from deseasonalized base
    target_base = base[target].mean()
    donor_base = {c: base[c].mean() for c in donor_cols}
    ratios = np.array([target_base / max(donor_base[c], 1) for c in donor_cols])
    weights = ratios / ratios.sum()
    weight_dict = dict(zip(donor_cols, weights))

    # 3. Counterfactual on deseasonalized data
    def _cf(period):
        cf = np.zeros(len(period))
        for i, c in enumerate(donor_cols):
            cf += weights[i] * period[c].values / donor_base[c] * target_base
        return cf

    # 4. Re-seasonalize using LS9's own dow factors
    def _resea(cf_values, period):
        dow = period["dow"].values
        return cf_values * np.array([ls9_factor[int(d)] for d in dow])

    cf_pre_ds = _cf(pre)
    cf_post_ds = _cf(post)
    cf_pre = _resea(cf_pre_ds, pre)
    cf_post = _resea(cf_post_ds, post)

    actual_pre = pre[target].values * np.array([ls9_factor[int(d)] for d in pre["dow"].values])
    actual_post = post[target].values * np.array([ls9_factor[int(d)] for d in post["dow"].values])

    mse = np.mean((actual_pre - cf_pre) ** 2)
    rmse = np.sqrt(mse)

    ate = actual_post - cf_post
    avg_ate = np.mean(ate)
    cumulative_ate = np.cumsum(ate)

    dow_desc = {0:"周一",1:"周二",2:"周三",3:"周四",4:"周五",5:"周六",6:"周日"}

    return {
        "weights": weight_dict,
        "weight_method": "星期去季节化 + 基期比例赋权 + 量级缩放",
        "weight_base": f"{weight_base_start} ~ {weight_base_end}",
        "target_base_mean": round(target_base, 1),
        "donor_base_means": {c: round(donor_base[c], 1) for c in donor_cols},
        "dow_factors": {dow_desc[k]: round(float(v), 3) for k, v in enumerate(dow_factors[target])},
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
                      color=C_GOLD, alpha=0.15, label=f"反事实（基期比例赋权）")
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
    ax2.annotate(f"累计估计增量: {total:.0f}",
                 xy=(result["post_dates"][-1], total),
                 xytext=(8, 0), textcoords="offset points",
                 fontsize=11, color=C_GOLD, fontweight="bold", va="center")
    ax2.set_ylabel("累计估计增量（锁单数）", fontsize=11, color=C_BLUE)
    ax2.set_xlabel("日期", fontsize=11, color="#6B7C8F")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax2.grid(True, alpha=0.1, color="#6B7C8F")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    plt.suptitle(f"{target} 锁单 — 合成控制效果估计", fontsize=15, color=C_BLUE, fontweight="bold", y=1.01)
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
    """描述性分解：前后期 LS9 锁单变化 = 线索量效应 × LS9 捕获率效应 × 交互"""
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
    d_str = "  ".join(f"{k}={v}" for k, v in sorted(sc_result.get("donor_base_means", {}).items()))
    dow_str = "  ".join(f"{k}={v}" for k, v in sc_result.get("dow_factors", {}).items())
    lines = [
        "=" * 60,
        "  LS9 Hyper 上市锁单效果评估 — 合成控制",
        "=" * 60,
        "",
        f"  预处理期: {sc_result['pre_period']}",
        f"  处理期:   {sc_result['post_period']}",
        "",
        "  ── 方法 ──",
        f"  {sc_result.get('weight_method', '')}",
        f"  权重基期: {sc_result.get('weight_base', '')}",
        "",
        f"  基期日均锁单:  LS9={sc_result.get('target_base_mean', '')}  {d_str}",
        "",
        "  ── LS9 星期因子 (去季节化用) ──",
        f"  {dow_str}",
        "",
        "  ── Donor Weights ──",
        f"  {w_str}",
        "",
        "  ── 合成控制效果估计 ──",
        f"  处理后日均估计增量: {sc_result['avg_ate']:+.1f} 锁单/日",
    ]

    if len(sc_result["actual"]) > 0:
        total_actual = sc_result["actual"].sum()
        total_cf = sc_result["counterfactual"].sum()
        total_ate = sc_result["cumulative_ate"][-1]
        lift_pct = (total_actual / total_cf - 1) * 100 if total_cf else 0
        lines += [
            f"  实际合计:  {total_actual:.0f} 锁单",
            f"  反事实合计: {total_cf:.0f} 锁单",
            f"  处理后累计估计增量: {total_ate:+.0f} 锁单 ({lift_pct:+.1f}%)",
            "",
            f"  ── 对照: 预处理期均值法 ──",
            f"  预处理日均: {sc_result.get('pre_mean', 0):.1f}",
            f"  后处理期日均: {sc_result['actual'].mean():.1f}",
            f"  处理后日均估计增量(均值法): {sc_result['actual'].mean() - sc_result.get('pre_mean', 0):+.1f}/日",
        ]

    if mech:
        lines += [
            "",
            "  ── 实际前后期锁单变化分解 ──",
            "  注：本部分为观察值分解，不代表因果机制贡献。",
            f"  LS9 锁单 = 全量下发线索 × LS9 线索捕获率",
            "",
            f"  前后期日均总增量: {mech['total_delta']:+.1f} 锁单/日",
            f"    ① 线索量效应: +{mech['leads_effect']:.1f} ({mech['leads_pct']}%)",
            f"    ② LS9捕获率效应: +{mech['conv_effect']:.1f} ({mech['conv_pct']}%)",
            f"    ③ 交互效应:     +{mech['interaction']:.1f} ({mech['interact_pct']}%)",
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
    panel = build_daily_panel(odf, target_series=args.target, donor_series=args.donors, start=start)
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

    print("=" * 60)
    print("  注意：合成控制为探索性准实验分析，结果仅供趋势参考，")
    print("  不构成确定的因果推断。")
    print("")
    print("  已知偏差来源：")
    print("  1. Donor 与 target 同属上汽品牌，可能存在同品牌")
    print("     流量带动或替代效应，使估计存在偏差。")
    print("=" * 60)
    print()
    print(format_output(sc_result, mech))

    if args.output_chart:
        plot_results(sc_result, target=args.target, output=args.output_chart)

