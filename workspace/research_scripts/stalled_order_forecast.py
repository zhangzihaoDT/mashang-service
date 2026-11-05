#!/usr/bin/env python
"""
Stalled Orders 分析 — 悬置锁单的有效开票概率与有效锁单当量（Effective Locked Order Equivalent, ELOE）

背景:
    待开票未退订锁单（锁单 & 未开票 & 未退订）并不等价于"有效待交付"。
    锁单账龄越久，最终开票概率越低，部分订单实际已沦为僵尸订单。

    本脚本用历史锁单估计条件开票概率（landmark / conditional outcome probability）:
        P(最终开票 | Lock Age = t)                          # v1: Age-only
        P(最终开票 | Lock Age = t, Series = s)              # v2: Age × Series
    其中 v2 对样本量做 shrinkage（向全局曲线回缩），避免小样本下的 0%/100% 假精确。
    然后对当前悬置池逐单累加概率，得到:
        ELOE = Σ P_i(最终开票 | 当前仍悬置)
    这是更接近真实未来交付 Backlog 的预测指标。

    方法与命名说明（严谨性）:
        本方法的经验比例是 conditional outcome curve / landmark probability，
        尚未完成 cause-specific hazard / CIF 的动态竞争风险估计，因此
        在文档与代码注释中不使用"竞争风险生存模型"的正式称谓。

    生产核心与共享层:
        条件开票曲线估计与 ELOE 累加逻辑已沉淀为共享算子
        `shared/operators/effective_locked_orders.py`（metrics.json 中
        "有效锁单当量" 的 operator 即指向它）。本脚本作为研究层消费者导入其
        纯函数；研究专属能力（--validate 验证、--chart 图表、Result Contract CLI）保留于此。

    评估:
        --validate 触发 out-of-time 验证：按 lock_time 时间切分 train/val，
        比较 Age-only vs Age×Series 在 Brier Score / Log Loss / Calibration 上的表现，
        为后续是否加入 Configuration / Channel 提供增量价值判断依据。

用法:
    python research_scripts/stalled_order_forecast.py
    python research_scripts/stalled_order_forecast.py --as-of 2026-08-16
    python research_scripts/stalled_order_forecast.py --series LS8
    python research_scripts/stalled_order_forecast.py --validate
    python research_scripts/stalled_order_forecast.py --format json --output outputs/tables/
    python research_scripts/stalled_order_forecast.py --chart

依赖:
    order_data.parquet（lock_time / invoice_upload_time / apply_refund_time / actual_refund_time）
"""

import sys, argparse, json
from pathlib import Path
from datetime import timedelta

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
import numpy as np
from utils.result_contract import build_success_contract, save_contract_json, contract_to_terminal
from utils.paths import ensure_shared_on_path

# 生产核心（条件开票曲线 + ELOE 累加）已沉淀为共享算子 shared/operators/effective_locked_orders.py，
# 本脚本作为研究层消费者，导入并使用其纯函数；研究专属能力（验证/图表/CLI/Result Contract）保留于此。
ensure_shared_on_path()
from operators.effective_locked_orders import (  # noqa: E402
    SERIES_ALL, BUCKETS, build_outcome_frame, estimate_curve_global,
    estimate_curve_by_series, predict_p, bucket_probabilities, score_current_pool,
    _open_stats,
)

from utils.data_loader import ORDER_DATA_PARQUET, load_order_data as load_data

LANDMARK_AGES = [7, 30, 60, 90]


def parse_args():
    p = argparse.ArgumentParser(description="Stalled Orders — 悬置锁单有效开票概率与有效锁单当量 (ELOE)")
    p.add_argument("--as-of", type=str, default=None, help="观察日期 (YYYY-MM-DD，默认今天)")
    p.add_argument("--train-window-days", type=int, default=365,
                   help="训练样本锁单窗口（当前观察日前 N 天内，默认 365）")
    p.add_argument("--maturity-days", type=int, default=120,
                   help="结局观察成熟期（锁单距今 >= 该天数才纳入训练，默认 120）")
    p.add_argument("--current-start", type=str, default=None,
                   help="当前悬置池起始日期（默认 as-of 前 365 天）")
    p.add_argument("--series", type=str, default=None, help="车系过滤 (LS6/L6/LS8/LS9)")
    p.add_argument("--model", type=str, default="series", choices=["age", "series"],
                   help="概率模型: age=Age-only(v1), series=Age×Series with shrinkage(v2，默认)")
    p.add_argument("--shrinkage", type=float, default=30.0,
                   help="Age×Series 的样本收缩强度 k（n/(n+k) 向全局回缩，默认 30）")
    p.add_argument("--validate", action="store_true", help="运行 out-of-time 验证（对比 age vs series）")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json", "csv"])
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--chart", action="store_true", help="同时输出 PNG 概率曲线与悬置账龄分布图")
    return p.parse_args()


# ── 生产核心已委托共享算子 ─────────────────────────────────────────────
# build_outcome_frame / estimate_curve_global / estimate_curve_by_series /
# predict_p / bucket_probabilities / score_current_pool 均为 shared/operators/
# effective_locked_orders.py 的 re-export（见文件头部 import），单一事实来源。


def _clip01(x: float) -> float:
    return min(max(x, 1e-6), 1 - 1e-6)


def evaluate_landmark(val: pd.DataFrame, model_curve_fn) -> dict:
    """在给定 landmark 账龄上评估模型：Brier / LogLoss / Calibration。"""
    total_n = 0
    brier_num = 0.0
    logloss_num = 0.0
    pred_sum = 0.0
    actual_sum = 0.0
    per_age = []
    for t in LANDMARK_AGES:
        n, _ = _open_stats(val, t)
        if n == 0:
            per_age.append({"age": t, "n": 0})
            continue
        open_mask = val["event_gap"].to_numpy(dtype=float) > t
        sub = val[open_mask]
        preds = [model_curve_fn(int(t), s) for s in sub["series"]]
        actuals = sub["invoiced_final"].astype(float).to_numpy()
        preds = np.array([_clip01(p) for p in preds], dtype=float)
        brier = float(np.mean((preds - actuals) ** 2))
        logloss = float(-np.mean(actuals * np.log(preds) + (1 - actuals) * np.log(1 - preds)))
        cal = float(np.mean(preds) - np.mean(actuals))
        per_age.append({"age": t, "n": int(n),
                        "brier": round(brier, 5), "logloss": round(logloss, 5),
                        "predicted_rate": round(float(np.mean(preds)), 4),
                        "actual_rate": round(float(np.mean(actuals)), 4),
                        "calibration_diff": round(cal, 4)})
        total_n += int(n)
        brier_num += brier * int(n)
        logloss_num += logloss * int(n)
        pred_sum += float(np.mean(preds)) * int(n)
        actual_sum += float(np.mean(actuals)) * int(n)
    if total_n == 0:
        return {"n": 0, "brier": None, "logloss": None, "calibration_diff": None, "per_age": per_age}
    return {
        "n": total_n,
        "brier": round(brier_num / total_n, 5),
        "logloss": round(logloss_num / total_n, 5),
        "calibration_diff": round((pred_sum - actual_sum) / total_n, 4),
        "per_age": per_age,
    }


def run_out_of_time_validation(df, as_of: pd.Timestamp, train_start: pd.Timestamp,
                               max_lock_train: pd.Timestamp, max_age: int,
                               shrinkage: float, series: str | None) -> dict:
    """out-of-time 验证：在训练窗口内按 lock_time 切 80/20，评估两种模型。"""
    fit_end = train_start + 0.8 * (max_lock_train - train_start)
    val_start = fit_end
    val_end = max_lock_train

    fit = build_outcome_frame(df, train_start, fit_end)
    val = build_outcome_frame(df, val_start, val_end)
    if series:
        fit = fit[fit["series"] == series]
        val = val[val["series"] == series]
    if fit.empty or val.empty:
        return {"error": "out-of-time 验证样本不足", "fit_n": len(fit), "val_n": len(val)}

    fit_global = estimate_curve_global(fit, max_age)
    fit_series = estimate_curve_by_series(fit, max_age, shrinkage)

    def age_fn(t, s):
        return predict_p(t, s, fit_global, None, max_age)

    def series_fn(t, s):
        return predict_p(t, s, fit_global, fit_series, max_age)

    res_age = evaluate_landmark(val, age_fn)
    res_series = evaluate_landmark(val, series_fn)
    return {
        "fit_n": len(fit), "val_n": len(val),
        "age_only": res_age,
        "age_x_series": res_series,
        "improvement_brier": (res_age["brier"] - res_series["brier"]) if res_age.get("brier") is not None and res_series.get("brier") is not None else None,
        "improvement_logloss": (res_age["logloss"] - res_series["logloss"]) if res_age.get("logloss") is not None and res_series.get("logloss") is not None else None,
    }


def build_chart(global_curve: dict, series_curves: dict[str, dict] | None,
                pool: dict, out_path: Path, model_name: str) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for _fp in ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",
                "/System/Library/Fonts/Supplemental/Songti.ttc"]:
        try:
            font_manager.fontManager.addfont(_fp)
        except Exception:
            pass
    plt.rcParams["font.sans-serif"] = ["PingFang SC", "Hiragino Sans GB", "Songti SC"]
    plt.rcParams["axes.unicode_minus"] = False

    ages = [t for t in sorted(global_curve) if global_curve[t] is not None]

    fig, axes = plt.subplots(1, 2, figsize=(16, 6), dpi=120)
    ax = axes[0]
    ax.plot(ages, [global_curve[t] * 100 for t in ages], color="#174A7C", lw=2, label="全局")
    if series_curves is not None:
        for s in ["LS6", "L6", "LS8", "LS9"]:
            if s in series_curves and any(series_curves[s].get(t) is not None for t in ages):
                ax.plot(ages, [series_curves[s].get(t, 0) * 100 if series_curves[s].get(t) is not None else np.nan
                               for t in ages], lw=1.2, ls="--", label=f"{s}")
    ax.axhline(80, color="#D79A36", ls=":", lw=1)
    ax.set_title(f"P(最终开票 | Lock Age) — {model_name}", fontsize=14, pad=12, color="#06213D")
    ax.set_xlabel("锁单账龄（天）", fontsize=12)
    ax.set_ylabel("最终开票概率（%）", fontsize=12)
    ax.grid(axis="y", ls="--", alpha=0.3)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=9)

    ax2 = axes[1]
    sub1 = pool.get("_pool_df")
    if sub1 is not None and len(sub1):
        ax2.hist(sub1["age"], bins=range(0, 96, 5), color="#7ECDEB", edgecolor="white")
        ax2.axvline(90, color="#D79A36", ls="--", lw=1.5)
        ax2.set_title("当前悬置池账龄分布（90 天为界）", fontsize=14, pad=12, color="#06213D")
        ax2.set_xlabel("锁单账龄（天）", fontsize=12)
        ax2.set_ylabel("订单数", fontsize=12)
        ax2.grid(axis="y", ls="--", alpha=0.3)
        ax2.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    return out_path


def main():
    args = parse_args()
    cmd = "python " + " ".join(sys.argv)

    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp.now().normalize()
    min_lock_train = as_of - pd.Timedelta(days=args.train_window_days)
    max_lock_train = as_of - pd.Timedelta(days=args.maturity_days)
    current_start = pd.Timestamp(args.current_start) if args.current_start else (
        as_of - pd.Timedelta(days=365))

    df = load_data()

    train_start = max(min_lock_train, df["lock_time"].min())
    train_end = min(max_lock_train, as_of)
    train = build_outcome_frame(df, train_start, train_end)
    if args.series:
        train = train[train["series"] == args.series]
    if train.empty:
        sys.exit("❌ 训练样本为空，请检查 as-of 与训练窗口参数")

    max_age = args.maturity_days
    global_curve = estimate_curve_global(train, max_age)
    series_curves = estimate_curve_by_series(train, max_age, args.shrinkage) if args.model == "series" else None

    pool = score_current_pool(df, as_of, global_curve, series_curves, args.series,
                              current_start, max_age)

    val_result = None
    if args.validate:
        val_result = run_out_of_time_validation(df, as_of, train_start, train_end,
                                                max_age, args.shrinkage, args.series)

    model_label = "Age×Series" if series_curves is not None else "Age-only"
    summary = (
        f"当前悬置池 {pool['total_orders']} 单 → 有效锁单当量 {pool['effective_orders']:.0f} 单 "
        f"(有效率 {pool['effective_orders']/pool['total_orders']:.1%})；"
        f">90 天僵尸订单 {pool['zombie_orders']} 单，当量仅 {pool['zombie_effective']:.0f}；模型={model_label}"
    )

    metrics = {
        "悬置订单数": pool["total_orders"],
        "有效锁单当量": pool["effective_orders"],
        "僵尸订单(>90d)": pool["zombie_orders"],
        "僵尸当量": pool["zombie_effective"],
        "有效率": round(pool["effective_orders"] / pool["total_orders"], 4) if pool["total_orders"] else None,
    }

    result_data = {
        "summary": summary,
        "metrics": metrics,
        "model": model_label,
        "prob_curve": {"days": list(range(1, max_age + 1)),
                       "p_invoice": [global_curve.get(t) for t in range(1, max_age + 1)]},
        "series_curves": {s: [series_curves[s].get(t) if s in series_curves else None
                              for t in range(1, max_age + 1)]
                          for s in SERIES_ALL} if series_curves else {},
        "buckets": bucket_probabilities(global_curve, series_curves, args.series, max_age),
        "current_pool": pool["buckets"],
        "by_series": pool["by_series"],
    }
    if val_result:
        result_data["out_of_time_validation"] = val_result

    contract = build_success_contract(
        script="research_scripts/stalled_order_forecast.py",
        command=cmd,
        scope={
            "data_source": str(ORDER_DATA_PARQUET),
            "time_window": {"as_of": str(as_of.date()), "train_window": f"last {args.train_window_days}d",
                            "maturity": f"{args.maturity_days}d", "current_start": str(current_start.date())},
            "filters": {"series": args.series},
            "metric_definition": "ELOE=ΣP(最终开票|Lock Age,Series)；conditional outcome curve / landmark probability，v2 带 shrinkage",
        },
        result=result_data,
        followup_context={
            "metric": "effective_locked_orders",
            "as_of": str(as_of.date()),
            "available_dimensions": ["series", "bucket", "city", "model"],
            "top_entities": [{"field": "series", "value": r["series"], "metrics": {"effective": r["effective_orders"]}}
                             for r in pool["by_series"]],
        },
    )

    artifacts = {}
    if args.format in ("json", "csv") or args.output:
        out_dir = Path(args.output) if args.output else _WS_ROOT / "outputs" / "tables"
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.format == "json":
            path = save_contract_json(contract, out_dir / f"stalled_order_forecast_{as_of:%Y%m%d}.json")
            artifacts["json"] = str(path)
        else:
            out_csv = out_dir / f"stalled_order_forecast_{as_of:%Y%m%d}.csv"
            rows = []
            for b in result_data["buckets"]:
                rows.append({"维度": "概率曲线", "区间": b["bucket"], "代表概率": b["prob"]})
            for b in pool["buckets"]:
                rows.append({"维度": "当前悬置池", "区间": b["bucket"],
                             "订单数": b["n_orders"], "有效当量": b["effective_orders"],
                             "均值概率": b["p_invoice_mean"]})
            pd.DataFrame(rows).to_csv(out_csv, index=False, encoding="utf-8-sig")
            artifacts["csv"] = str(out_csv)
    if args.chart:
        chart_dir = _WS_ROOT / "outputs" / "charts"
        chart_dir.mkdir(parents=True, exist_ok=True)
        chart_path = chart_dir / f"stalled_order_forecast_{as_of:%Y%m%d}.png"
        p = build_chart(global_curve, series_curves, pool, chart_path, model_label)
        artifacts["chart"] = str(p)
    contract["artifacts"] = artifacts

    if args.format == "terminal":
        print(contract_to_terminal(contract))
        print("\n[Prob Curve 分段]")
        for b in result_data["buckets"]:
            print(f"  {b['bucket']:<12} P(最终开票) = {b['prob']:.1%}")
        print("\n[当前悬置池]")
        for b in pool["buckets"]:
            print(f"  {b['bucket']:<12} {b['n_orders']:>5} 单 | 当量 {b['effective_orders']:>7.1f} | 均值 {b['p_invoice_mean']:.1%}")
        if pool["by_series"]:
            print("\n[分车系]")
            for s in pool["by_series"]:
                print(f"  {s['series']:<5} {s['n_orders']:>5} 单 | 当量 {s['effective_orders']:>7.1f}")
        if val_result:
            print("\n[Out-of-Time 验证]")
            if "error" in val_result:
                print(f"  ⚠ {val_result['error']}")
            else:
                a, sres = val_result["age_only"], val_result["age_x_series"]
                print(f"  fit_n={val_result['fit_n']} val_n={val_result['val_n']}")
                print(f"  {'模型':<14}{'Brier':>9}{'LogLoss':>10}{'Calibration':>13}")
                print(f"  {'Age-only':<14}{a['brier'] or 0:>9.4f}{a['logloss'] or 0:>10.4f}{(a['calibration_diff'] or 0):>13.4f}")
                print(f"  {'Age×Series':<14}{sres['brier'] or 0:>9.4f}{sres['logloss'] or 0:>10.4f}{(sres['calibration_diff'] or 0):>13.4f}")
                if val_result.get("improvement_brier") is not None:
                    print(f"  Brier 改善: {val_result['improvement_brier']:+.4f}  LogLoss 改善: {val_result['improvement_logloss']:+.4f}（正=Age×Series 更优）")
    elif args.format == "json":
        print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(summary)


if __name__ == "__main__":
    main()
