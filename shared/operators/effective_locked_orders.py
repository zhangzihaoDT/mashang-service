"""
有效锁单当量 (Effective Locked Order Equivalent, ELOE) — Shared Operator

对当前悬置池（待开票未退订锁单）逐单估计条件开票概率，累加为有效锁单当量：

    ELOE = Σ P_i(最终开票 | 当前仍悬置)

方法：
    用历史锁单估计 conditional outcome curve / landmark probability：
        v1: P(最终开票 | Lock Age = t)                      # Age-only
        v2: P(最终开票 | Lock Age = t, Series = s)          # Age × Series，带 shrinkage
    v2 对样本量做 shrinkage（向全局曲线回缩，n/(n+k)），避免小样本下的 0%/100% 假精确。

严谨性说明：
    本算子的经验比例是 conditional outcome curve / landmark probability，
    尚未完成 cause-specific hazard / CIF 的动态竞争风险估计，因此
    在文档与代码注释中不使用「竞争风险生存模型」的正式称谓。

派生指标（本算子直接产出）：
    Backlog 有效率   = ELOE ÷ 悬置池
    风险暴露量        = 悬置池 − ELOE   （At-Risk Backlog）

入口：
    run_effective_locked_orders_operator(df, as_of, ...)

数据集：
    order_data（lock_time / invoice_upload_time / apply_refund_time / actual_refund_time）
"""

from __future__ import annotations

import pandas as pd
import numpy as np

SERIES_ALL = ["LS6", "L6", "LS8", "LS9", "LS7", "L7"]

BUCKETS = [
    (0, 7, "0–7 天"),
    (8, 30, "8–30 天"),
    (31, 60, "31–60 天"),
    (61, 90, "61–90 天"),
    (91, None, ">90 天"),
]


def build_outcome_frame(df: pd.DataFrame, min_lock, max_lock) -> pd.DataFrame:
    """构造历史锁单的结局帧：每个锁单 → 开票间隔 / 退订间隔 / 最终是否开票。"""
    m = df[df["lock_time"].notna()].copy()
    m = m[(m["lock_time"] >= min_lock) & (m["lock_time"] < max_lock)]

    m["inv_gap"] = (m["invoice_upload_time"] - m["lock_time"]).dt.days
    ref = m[["apply_refund_time", "actual_refund_time"]].min(axis=1)
    m["ref_gap"] = (ref - m["lock_time"]).dt.days

    # 退出事件 = 开票或退订中更早发生；最终是否开票
    m["event_gap"] = m[["inv_gap", "ref_gap"]].min(axis=1)
    m["invoiced_final"] = m["inv_gap"].notna().astype(int)
    # 仍悬置订单（观察期内既未开票也未退订）：视为观察窗口内不开票，event_gap 设为足够大
    max_obs = int((max_lock - min_lock).days) + 365 * 2
    m["event_gap"] = m["event_gap"].fillna(max_obs).astype(float)
    return m


def _open_stats(frame: pd.DataFrame, t: int) -> tuple[int, int]:
    """返回在账龄 t 天仍有效（未开票未退订）的样本数，及其中最终开票数。"""
    open_mask = frame["event_gap"].to_numpy(dtype=float) > t
    if open_mask.sum() == 0:
        return 0, 0
    inv = int(frame.loc[open_mask, "invoiced_final"].sum())
    return int(open_mask.sum()), inv


def estimate_curve_global(frame: pd.DataFrame, max_age: int) -> dict:
    """v1: P(最终开票 | Lock Age = t)，t=1..max_age（全局曲线）。"""
    curve = {}
    for t in range(1, max_age + 1):
        n, k = _open_stats(frame, t)
        curve[t] = (float(k) / n) if n else None
    return curve


def estimate_curve_by_series(frame: pd.DataFrame, max_age: int, shrinkage: float) -> dict:
    """v2: P(最终开票 | Lock Age=t, Series=s)，带样本量收缩（向全局回缩）。

    shrinkage: p_shrunk = w*p_series + (1-w)*p_global，其中 w = n/(n+shrinkage)。
    当某车系某账龄样本为 0 时直接取全局曲线；样本越小越贴近全局。
    """
    global_curve = estimate_curve_global(frame, max_age)
    series_curves: dict[str, dict] = {s: {} for s in SERIES_ALL}
    for s in SERIES_ALL:
        sub = frame[frame["series"] == s]
        if sub.empty:
            continue
        for t in range(1, max_age + 1):
            n, k = _open_stats(sub, t)
            if n == 0:
                series_curves[s][t] = global_curve.get(t)
                continue
            p_series = k / n
            p_global = global_curve.get(t)
            if p_global is None:
                series_curves[s][t] = p_series
                continue
            w = n / (n + shrinkage)
            series_curves[s][t] = w * p_series + (1 - w) * p_global
    return series_curves


def predict_p(age: int, series: str | None, global_curve: dict,
              series_curves: dict[str, dict] | None, max_curve_age: int) -> float:
    """按模型取概率，越界账龄回退到曲线末端。"""
    t = min(max(age, 1), max_curve_age)
    if series_curves is not None and series in series_curves:
        v = series_curves[series].get(t)
        if v is not None:
            return float(v)
    v = global_curve.get(t)
    return float(v) if v is not None else 0.0


def bucket_probabilities(global_curve: dict, series_curves: dict[str, dict] | None,
                         series: str | None, max_age: int) -> list[dict]:
    """将逐日概率汇总为账龄分段的代表概率（取各段内天数均值）。"""
    out = []
    for lo, hi, label in BUCKETS:
        hi_eff = min(hi, max_age) if hi is not None else max_age
        vals = [predict_p(t, series, global_curve, series_curves, max_age)
                for t in range(lo, hi_eff + 1)]
        out.append({"bucket": label, "days": f"{lo}~{'Inf' if hi is None else hi}",
                    "prob": round(float(np.mean(vals)), 4), "n_days": hi_eff - lo + 1})
    return out


def score_current_pool(df: pd.DataFrame, as_of: pd.Timestamp,
                       global_curve: dict, series_curves: dict[str, dict] | None,
                       series: str | None, current_start: pd.Timestamp,
                       max_curve_age: int) -> dict:
    """对当前悬置池逐单应用条件开票概率，计算有效锁单当量 (ELOE)。

    返回 dict 含 "_pool_df"（逐单明细 DataFrame，供上层图表使用）；
    对外 JSON 结果应剔除该键。
    """
    stalled = df[(df["lock_time"].notna())
                 & (df["invoice_upload_time"].isna())
                 & (df["apply_refund_time"].isna())
                 & (df["actual_refund_time"].isna())
                 & (df["lock_time"] >= current_start)
                 & (df["lock_time"] < as_of + pd.Timedelta(days=1))].copy()
    if series:
        stalled = stalled[stalled["series"] == series]

    stalled["age"] = (as_of - stalled["lock_time"]).dt.days.clip(lower=1)
    stalled["p_invoice"] = [predict_p(int(a), s, global_curve, series_curves, max_curve_age)
                            for a, s in zip(stalled["age"], stalled["series"])]

    total_n = int(stalled["order_number"].nunique())
    sub1 = stalled.groupby("order_number", as_index=False).first()
    eff_n = float(sub1["p_invoice"].sum())
    zombie_n = int((sub1["age"] > 90).sum())
    zombie_eff = float(sub1.loc[sub1["age"] > 90, "p_invoice"].sum())

    rows = []
    for lo, hi, label in BUCKETS:
        hi_eff = hi if hi is not None else 10 ** 9
        sub = sub1[(sub1["age"] >= lo) & (sub1["age"] <= hi_eff)]
        if sub.empty:
            continue
        rows.append({
            "bucket": label,
            "n_orders": int(len(sub)),
            "effective_orders": round(float(sub["p_invoice"].sum()), 1),
            "p_invoice_mean": round(float(sub["p_invoice"].mean()), 4),
        })

    by_series = []
    for s in SERIES_ALL:
        sub = sub1[sub1["series"] == s]
        if sub.empty:
            continue
        by_series.append({
            "series": s,
            "n_orders": int(len(sub)),
            "effective_orders": round(float(sub["p_invoice"].sum()), 1),
            "implied_share": round(float(sub["p_invoice"].sum()) / eff_n, 4) if eff_n else None,
        })

    return {
        "total_orders": total_n,
        "effective_orders": round(eff_n, 1),
        "zombie_orders": zombie_n,
        "zombie_effective": round(zombie_eff, 1),
        "buckets": rows,
        "by_series": by_series,
        "_pool_df": sub1,
    }


def run_effective_locked_orders_operator(
    df: pd.DataFrame,
    as_of: str,
    train_window_days: int = 365,
    maturity_days: int = 120,
    current_start: str | None = None,
    series: str | None = None,
    model: str = "series",
    shrinkage: float = 30.0,
) -> dict:
    """共享算子入口：给定 order_data 与观察日 as_of，输出 ELOE 体系结果。

    model: "age"=Age-only(v1), "series"=Age×Series with shrinkage(v2，默认)。
    """
    if df is None or df.empty:
        return {
            "type": "effective_locked_orders",
            "error": "no_data",
            "message": "无可用数据。",
        }

    try:
        as_of_ts = pd.Timestamp(as_of).normalize()
    except Exception:
        return {
            "type": "effective_locked_orders",
            "error": "invalid_as_of",
            "message": f"as_of 格式错误: {as_of}",
        }
    if train_window_days <= 0 or maturity_days <= 0:
        return {
            "type": "effective_locked_orders",
            "error": "invalid_parameter",
            "message": "train_window_days 与 maturity_days 必须为正。",
        }
    if model not in ("age", "series"):
        return {
            "type": "effective_locked_orders",
            "error": "invalid_parameter",
            "message": f"model 仅支持 age / series，收到: {model}",
        }

    work = df.copy()
    for c in ["lock_time", "invoice_upload_time", "apply_refund_time", "actual_refund_time"]:
        if c in work.columns:
            work[c] = pd.to_datetime(work[c], errors="coerce")

    min_lock_train = as_of_ts - pd.Timedelta(days=train_window_days)
    max_lock_train = as_of_ts - pd.Timedelta(days=maturity_days)
    current_start_ts = (pd.Timestamp(current_start).normalize()
                        if current_start else as_of_ts - pd.Timedelta(days=365))

    train_start = max(min_lock_train, work["lock_time"].min())
    train_end = min(max_lock_train, as_of_ts)
    if train_end <= train_start:
        return {
            "type": "effective_locked_orders",
            "error": "invalid_train_window",
            "message": "训练窗口无效（train_end <= train_start）。",
        }

    train = build_outcome_frame(work, train_start, train_end)
    if series:
        train = train[train["series"] == series]
    if train.empty:
        return {
            "type": "effective_locked_orders",
            "error": "no_training_sample",
            "message": "训练样本为空，请检查 as-of 与训练窗口参数。",
        }

    max_age = maturity_days
    global_curve = estimate_curve_global(train, max_age)
    series_curves = (estimate_curve_by_series(train, max_age, shrinkage)
                     if model == "series" else None)

    pool = score_current_pool(work, as_of_ts, global_curve, series_curves, series,
                              current_start_ts, max_age)

    model_label = "Age×Series" if series_curves is not None else "Age-only"
    return {
        "type": "effective_locked_orders",
        "as_of": as_of_ts.strftime("%Y-%m-%d"),
        "model": model_label,
        "scope": {
            "data_source": "order_data",
            "train_window": {
                "start": train_start.strftime("%Y-%m-%d"),
                "end": train_end.strftime("%Y-%m-%d"),
            },
            "maturity_days": maturity_days,
            "current_start": current_start_ts.strftime("%Y-%m-%d"),
            "series": series,
        },
        "summary": {
            "悬置订单数": pool["total_orders"],
            "有效锁单当量ELOE": pool["effective_orders"],
            "僵尸订单(>90d)": pool["zombie_orders"],
            "僵尸当量": pool["zombie_effective"],
            "有效率": round(pool["effective_orders"] / pool["total_orders"], 4)
            if pool["total_orders"] else None,
            "风险暴露量": round(pool["total_orders"] - pool["effective_orders"], 1),
        },
        "prob_curve": {
            "days": list(range(1, max_age + 1)),
            "p_invoice": [global_curve.get(t) for t in range(1, max_age + 1)],
        },
        "series_curves": {s: [series_curves[s].get(t) if s in series_curves else None
                              for t in range(1, max_age + 1)]
                          for s in SERIES_ALL} if series_curves else {},
        "buckets": bucket_probabilities(global_curve, series_curves, series, max_age),
        "current_pool": pool["buckets"],
        "by_series": pool["by_series"],
    }
