#!/usr/bin/env python
"""
Backlog 有效率历史分析 HTML 报告 — 悬置池规模 × 有效率 散点图

分析 2023-01 起每月初观察点的 Backlog 有效率（ELOE / 待开票未退订锁单数），
探索悬置池规模与有效率两个指标之间的潜在关系。

依赖方向：ELOE 生产核心直接消费 shared/operators/effective_locked_orders.py
（经 utils/data_loader 加载 order_data），不依赖 stalled_order_forecast.py。

指标口径速览（全部指标详见 METRIC_DEFINITIONS，渲染为报告「指标口径速览」卡片）:
    落定率          多少锁单已经有结果？  → 1 − 悬置率
    实际交付率      到今天已经兑现多少？  → 累计已交付 ÷ 累计锁单
    30/98 日交付率  锁单兑现有多快？      → Cohort N 日内开票 ÷ Cohort 锁单（以开票作为交付兑现时点）
    预测最终交付率  最终预计兑现多少？    → (已交付 + ELOE) ÷ 总锁单 = 实际交付率 + ELOE ÷ 累计锁单
    悬置池          还有多少锁单没有结果？ → 锁单 & 未开票 & 未退订
    有效锁单当量 ELOE  悬置池还值多少单？ → Σ P_i(最终开票 | Lock Age, Series)
    Backlog 有效率  悬置池还有多少含金量？ → ELOE ÷ 悬置池
    风险暴露量      悬置池预计损失多少？  → 悬置池 − ELOE
    >90 天僵尸占比  悬置池老化有多严重？  → >90 天悬置 ÷ 悬置池

核心恒等式（Backlog Balance Sheet）:
    悬置池 = ELOE + 风险暴露量  (Nominal Backlog = Effective Backlog + At-risk Backlog)
    预测最终交付率 = 实际交付率 + ELOE ÷ 累计锁单

point-in-time 口径（重要）:
    历史观察点按 as-of 状态重建，而非使用今天的订单状态：
    - 悬置池：开票/退订时间晚于观察点的订单，在观察点当时仍计入池子。
    - ELOE：已知最终结局的订单取确定值（最终开票→1，最终退订→0），
            仅仍悬置（至今未开票未退订）的订单用模型概率。
    修复前该逻辑把观察点之后才开票/退订的订单错误排除，历史池子被系统性低估。

用法:
    python research_scripts/backlog_rate_trend_report.py
    python research_scripts/backlog_rate_trend_report.py --as-of 2026-08-16
    python research_scripts/backlog_rate_trend_report.py --output outputs/reports/
"""

import sys, json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
import numpy as np
import argparse
from utils.paths import ensure_shared_on_path
from utils.data_loader import load_order_data as load_data

# ELOE 生产核心直接消费共享算子，不再经由 stalled_order_forecast.py 中转
ensure_shared_on_path()
from operators.effective_locked_orders import (  # noqa: E402
    build_outcome_frame, estimate_curve_global, predict_p,
)

try:
    from statsmodels.nonparametric.smoothers_lowess import lowess as _lowess
    _HAS_LOWESS = True
except ImportError:
    _HAS_LOWESS = False

ASOF_START = pd.Timestamp("2023-01-01")
TRAIN_WINDOW = 365
MATURITY = 120
CURRENT_WINDOW = 365

COLOR_OWN = "#174A7C"
COLOR_EVENT = "#D79A36"
COLOR_ASH = "#9AA3AD"
COLOR_NEG = "#D95F59"
COLOR_POS = "#2A9D8F"


# 本报告全部指标口径（一句话回答 + 计算口径），渲染为报告「指标口径速览」卡片。
# 指标体系结构 = Locked Order Health / 锁单健康度：
#   结果(落定率) · 速度(30/98日交付率) · 存量(悬置池/ELOE/有效率) ·
#   预测(实际交付率/预测最终交付率) · 风险(风险暴露量/>90天僵尸占比)
# 核心恒等式（Backlog Balance Sheet）：
#   悬置池 = ELOE + 风险暴露量   (Nominal Backlog = Effective Backlog + At-risk Backlog)
#   预测最终交付率 = 实际交付率 + ELOE ÷ 累计锁单
METRIC_DEFINITIONS = [
    {
        "metric": "落定率（Resolution Rate）",
        "meaning": "多少锁单已经有结果？",
        "definition": "1 − 悬置率 = (累计锁单 − 待开票未退订) ÷ 累计锁单；"
                     "落定 = 已开票 或 已退订，订单生命周期已走到结局。",
    },
    {
        "metric": "实际交付率",
        "meaning": "到今天已经兑现多少？",
        "definition": "累计已交付（delivery_date ≤ 观察日）÷ 累计锁单。",
    },
    {
        "metric": "30/98 日交付率",
        "meaning": "锁单兑现有多快？",
        "definition": "Cohort N 日内开票 ÷ Cohort 锁单（以开票 invoice_upload_time 作为交付兑现时点；"
                     "无成熟窗口过滤，LOWESS 平滑呈现）。",
    },
    {
        "metric": "预测最终交付率",
        "meaning": "最终预计兑现多少？",
        "definition": "(已交付 + ELOE) ÷ 总锁单 = 实际交付率 + ELOE ÷ 累计锁单；"
                     "以 ELOE 补足未成熟订单的尾部，预计最终交付水平。",
    },
    {
        "metric": "悬置池（名义 Backlog）",
        "meaning": "还有多少锁单没有结果？",
        "definition": "锁单 & 未开票 & 未退订。历史观察点按 as-of 状态重建（point-in-time："
                     "开票/退订晚于观察点的订单仍计入当时池子）；cumulative = 当年 1 月 1 日起累计，"
                     "rolling = 观察点前 365 天。",
    },
    {
        "metric": "有效锁单当量 ELOE",
        "meaning": "悬置池还值多少单？",
        "definition": "Σ P_i(最终开票 | Lock Age, Series)；条件概率来自历史 landmark 曲线"
                     "（v2 带 sample-size shrinkage）。历史观察点逐单重建：已知最终开票→1，"
                     "已退订→0，仍悬置→模型概率。",
    },
    {
        "metric": "Backlog 有效率",
        "meaning": "悬置池还有多少含金量？",
        "definition": "ELOE ÷ 悬置池（Backlog realization rate）。",
    },
    {
        "metric": "风险暴露量（At-Risk Backlog）",
        "meaning": "悬置池预计损失多少？",
        "definition": "悬置池 − ELOE = 名义 Backlog × (1 − 有效率)。",
    },
    {
        "metric": ">90 天僵尸订单占比",
        "meaning": "悬置池老化有多严重？",
        "definition": ">90 天悬置订单 ÷ 悬置池。",
    },
]

# 指标体系三句话总结（渲染在「指标口径速览」卡片下方）
METRIC_SUMMARY = [
    "实际交付率看已经兑现多少；30/98 日交付率看兑现速度；预测最终交付率看最终能兑现多少。",
    "悬置池看还有多少没结果；ELOE 看这些订单还值多少；风险暴露量看其中可能损失多少。",
    "落定率负责描述整个订单生命周期走到了什么程度。",
]


def parse_args():
    p = argparse.ArgumentParser(description="Backlog 有效率历史分析 HTML 报告")
    p.add_argument("--as-of", type=str, default=None, help="报告截止观察点（默认最新数据日）")
    p.add_argument("--pool-window", type=str, default="cumulative", choices=["cumulative", "rolling"],
                   help="悬置池口径: cumulative=当年1月1日起累计(默认), rolling=前365天")
    p.add_argument("--frequency", type=str, default="hybrid", choices=["hybrid", "monthly", "daily"],
                   help="观察点粒度: hybrid=历史月度+近一年日度(默认), monthly=全月度, daily=全日度")
    p.add_argument("--output", type=str, default=str(_WS_ROOT / "outputs" / "reports"), help="输出目录")
    p.add_argument("--format", type=str, default="html", choices=["html", "terminal", "json"])
    p.add_argument("--years", nargs="+", type=int, default=None, help="头对头对比年份（默认 2024 2025 2026）")
    return p.parse_args()


def _build_observation_dates(as_of: pd.Timestamp, frequency: str = "monthly") -> list[pd.Timestamp]:
    """构造统一观察点：历史月度，近一年可切换为日度。"""
    if frequency == "monthly":
        dates = list(pd.date_range(ASOF_START, as_of, freq="MS"))
    elif frequency == "daily":
        dates = list(pd.date_range(ASOF_START, as_of, freq="D"))
    else:
        cutoff = max(ASOF_START, as_of - pd.Timedelta(days=365))
        dates = list(pd.date_range(ASOF_START, cutoff, freq="MS"))
        dates.extend(pd.date_range(cutoff + pd.Timedelta(days=1), as_of, freq="D"))
    if not dates or dates[-1] != as_of:
        dates.append(as_of)
    return sorted(set(dates))


def compute_history(as_of: pd.Timestamp, pool_window: str = "cumulative",
                    frequency: str = "monthly",
                    df: pd.DataFrame | None = None) -> pd.DataFrame:
    if df is None:
        df = load_data()
    dates = _build_observation_dates(as_of, frequency)
    rows = []
    for obs in dates:
        obs_end = obs + pd.Timedelta(days=1)
        min_lock_train = obs - pd.Timedelta(days=TRAIN_WINDOW)
        max_lock_train = obs - pd.Timedelta(days=MATURITY)
        if pool_window == "rolling":
            current_start = obs - pd.Timedelta(days=CURRENT_WINDOW)
        else:
            current_start = pd.Timestamp(year=obs.year, month=1, day=1)

        train_start = max(min_lock_train, df["lock_time"].min())
        train_end = min(max_lock_train, obs)
        if train_end <= train_start:
            continue
        train = build_outcome_frame(df, train_start, train_end)
        if len(train) < 500:
            continue
        global_curve = estimate_curve_global(train, MATURITY)

        # point-in-time as-of 悬置池：以 obs 当日状态判定，而非今天状态。
        # 开票/退订时间为空或 >= obs_end 的订单，在 obs 当时仍是悬置。
        stalled_mask = (
            df["lock_time"].notna()
            & (df["invoice_upload_time"].isna() | (df["invoice_upload_time"] >= obs_end))
            & (df["apply_refund_time"].isna() | (df["apply_refund_time"] >= obs_end))
            & (df["actual_refund_time"].isna() | (df["actual_refund_time"] >= obs_end))
            & (df["lock_time"] >= current_start)
            & (df["lock_time"] < obs_end)
        )
        stalled = df[stalled_mask].copy()
        if stalled.empty:
            continue
        stalled["age"] = (obs - stalled["lock_time"]).dt.days.clip(lower=1)
        stalled["p_model"] = [predict_p(int(a), s, global_curve, None, MATURITY)
                              for a, s in zip(stalled["age"], stalled["series"])]
        # PIT ELOE 逐单重建：已知最终结局取确定值，仍悬置用模型概率
        final_inv = stalled["invoice_upload_time"].notna().astype(int)
        final_ref = (stalled["apply_refund_time"].notna()
                     | stalled["actual_refund_time"].notna()).astype(int)
        stalled["p"] = np.where(final_inv == 1, 1.0,
                                np.where(final_ref == 1, 0.0, stalled["p_model"]))
        sub = stalled.groupby("order_number", as_index=False).first()
        n = len(sub)
        if n < 100:
            continue
        eloe = float(sub["p"].sum())
        rows.append({
            "as_of": str(obs.date()),
            "month": obs.strftime("%Y-%m"),
            "year": obs.year,
            "n_orders": int(n),
            "eloe": round(eloe, 1),
            "at_risk": round(float(n - eloe), 1),
            "rate": round(eloe / n, 4),
            "zombie_share": round(float((sub["age"] > 90).mean()), 4),
        })
    return pd.DataFrame(rows)


def _corr(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 3:
        return float("nan")
    return round(float(np.corrcoef(a, b)[0, 1]), 4)


def compute_delivery_snapshot(obs_dates: list, as_of: pd.Timestamp,
                              effective_rates: list | None = None) -> dict:
    """在给定观察点序列上计算落定率、实际交付率及 2026 预测交付率。

    与 ② 模块共用同一观察点（当年累计口径，rdf['as_of']），每个观察点统计：
        累计锁单数   = 该观察点年份内 lock_time < obs+1天 的锁单数
        待开票未退订 = 其中未开票且未退订的数量
        落定率       = (累计锁单数 − 待开票未退订) ÷ 累计锁单数 = 1 − 悬置率

    这是观察 ELOE 的正向互补视角：ELOE 从仍悬置的池子预测未来兑现，
    本指标从总锁单看已经落定（已交付或已退订）的比例。

    返回 resolution、actual_delivery_by_year、forecast_delivery_2026 三类曲线。
    """
    df = load_data()
    locked = df[df["lock_time"].notna()].copy()
    locked["lock_dt"] = pd.to_datetime(locked["lock_time"])
    locked["del_dt"] = pd.to_datetime(locked["delivery_date"], errors="coerce")
    locked["year"] = locked["lock_dt"].dt.year
    locked = locked[locked["lock_dt"] < as_of + pd.Timedelta(days=1)]
    locked["invoice_dt"] = pd.to_datetime(locked["invoice_upload_time"], errors="coerce")
    locked["refund_dt"] = locked[["apply_refund_time", "actual_refund_time"]].min(axis=1)

    x, resolution, actual_by_year = [], [], {"2024": [], "2025": [], "2026": []}
    forecast_2026 = []
    for obs_idx, obs in enumerate(obs_dates):
        obs_end = obs + pd.Timedelta(days=1)
        in_year = locked["year"] == obs.year
        total_mask = in_year & (locked["lock_dt"] < obs_end)
        total = int(total_mask.sum())
        if total == 0:
            continue
        resolved_mask = ((locked["invoice_dt"] < obs_end) | (locked["refund_dt"] < obs_end))
        open_cnt = int((total_mask & ~resolved_mask).sum())
        x.append(obs.strftime("%Y-%m-%d"))
        resolution.append(round((total - open_cnt) / total, 4))

        delivered_mask = total_mask & (locked["del_dt"] < obs_end)
        for year in actual_by_year:
            year_mask = (locked["year"] == int(year)) & (locked["lock_dt"] < obs_end)
            year_total = int(year_mask.sum())
            if year_total:
                actual_by_year[year].append({
                    "x": obs.strftime("%Y-%m-%d"),
                    "y": round(int((year_mask & (locked["del_dt"] < obs_end)).sum()) / year_total, 4),
                })

        # 2026: 用当前时点仍悬置订单的 ELOE 补足实际交付率的尾部预测。
        if obs.year == 2026:
            year_mask = (locked["year"] == 2026) & (locked["lock_dt"] < obs_end)
            year_total = int(year_mask.sum())
            delivered = int((year_mask & (locked["del_dt"] < obs_end)).sum())
            effective_rate = float(effective_rates[obs_idx]) if effective_rates and obs_idx < len(effective_rates) else 0.0
            forecast_2026.append({
                "x": obs.strftime("%Y-%m-%d"),
                "y": round((delivered + open_cnt * effective_rate) / year_total, 4)
                if year_total else None,
            })
    return {
        "resolution": {"x": x, "y": resolution},
        "actual_delivery_by_year": actual_by_year,
        "forecast_delivery_2026": forecast_2026,
    }


def compute_delivery_head_to_head(as_of: pd.Timestamp,
                                  effective_by_date: dict | None = None,
                                  years: tuple[int, ...] = (2024, 2025, 2026)) -> dict:
    """按年内天数对齐各年度锁单的落定率/交付率快照。"""
    df = load_data()
    locked = df[df["lock_time"].notna()].copy()
    locked["lock_dt"] = pd.to_datetime(locked["lock_time"])
    locked["invoice_dt"] = pd.to_datetime(locked["invoice_upload_time"], errors="coerce")
    locked["refund_dt"] = locked[["apply_refund_time", "actual_refund_time"]].min(axis=1)
    locked["delivery_dt"] = pd.to_datetime(locked["delivery_date"], errors="coerce")
    locked["year"] = locked["lock_dt"].dt.year
    locked = locked[(locked["lock_dt"] < as_of + pd.Timedelta(days=1)) & locked["year"].isin(years)]

    out = {}
    for year in years:
        g = locked[locked["year"] == year]
        if g.empty:
            continue
        end = min(as_of, pd.Timestamp(year=year, month=12, day=31))
        days = pd.date_range(pd.Timestamp(year=year, month=1, day=1), end, freq="D")
        rows = {"resolution": [], "actual_delivery": [], "forecast_delivery": []}
        for obs in days:
            obs_end = obs + pd.Timedelta(days=1)
            total_mask = g["lock_dt"] < obs_end
            total = int(total_mask.sum())
            if total == 0:
                continue
            resolved = (g["invoice_dt"] < obs_end) | (g["refund_dt"] < obs_end)
            open_count = int((total_mask & ~resolved).sum())
            delivered = int((total_mask & (g["delivery_dt"] < obs_end)).sum())
            day = int(obs.dayofyear)
            rate = float(effective_by_date.get(obs.strftime("%Y-%m-%d"), 0.0)) if effective_by_date else 0.0
            rows["resolution"].append({"x": day, "y": round((total - open_count) / total, 4)})
            rows["actual_delivery"].append({"x": day, "y": round(delivered / total, 4)})
            if year == 2026:
                rows["forecast_delivery"].append({
                    "x": day,
                    "y": round((delivered + open_count * rate) / total, 4),
                })
        out[str(year)] = {"n": int(len(g)), **rows}
    return out


def compute_delivery_age_snapshot(obs_dates: list, as_of: pd.Timestamp,
                                  thresholds: tuple[int, ...] = (30, 98)) -> dict:
    """按每日锁单 cohort 计算 N 日交付率，完全对齐 analyze-2025 §3.1/§9 delivery_trend 口径。

    口径（与 analyze_2025.py §9 逐字一致）：
        rate_Nd(锁单日 d) = 当日锁单中 (invoice_upload_time − lock_time) ≤ N 天的订单数
                            ÷ 当日唯一锁单数
    - 交付事件 = invoice_upload_time（未开票订单 duration 为 NaN → 计为 N 日内未交付）。
    - 无成熟窗口过滤（与参考趋势图一致；近期锁单 cohort 天然偏低，由 LOWESS 平滑呈现）。
    - 分母 = 当日全部锁单（含后续退订但未开票的订单）。

    返回 {str(n): {"x": [锁单日], "y": [rate], "count": [N日内开票数], "total": [当日锁单数]}}。
    取值范围与其他图表一致：仅覆盖锁单日 >= ASOF_START(2023-01-01)。
    """
    df = load_data()
    locked = df[df["lock_time"].notna()].copy()
    locked["lock_dt"] = pd.to_datetime(locked["lock_time"])
    locked["inv_dt"] = pd.to_datetime(locked["invoice_upload_time"], errors="coerce")
    locked["inv_gap"] = (locked["inv_dt"] - locked["lock_dt"]).dt.days
    locked = locked[(locked["lock_dt"] >= ASOF_START)
                    & (locked["lock_dt"] < as_of + pd.Timedelta(days=1))].set_index("lock_dt").sort_index()

    out = {str(n): {"x": [], "y": [], "count": [], "total": []} for n in thresholds}
    for n in thresholds:
        total = locked["order_number"].resample("D").nunique()
        cnt = (locked["inv_gap"] <= n).resample("D").sum()
        for d, t in total.items():
            if t == 0:
                continue
            c = int(cnt.get(d, 0))
            out[str(n)]["x"].append(d.strftime("%Y-%m-%d"))
            out[str(n)]["y"].append(round(c / t, 4))
            out[str(n)]["count"].append(c)
            out[str(n)]["total"].append(int(t))
    return out


def render_html(rdf: pd.DataFrame, stats: dict, as_of: str, static_prefix: str, pool_window: str = "cumulative", delivery_df: dict | None = None, delivery_age_df: dict | None = None) -> str:
    dates = rdf["as_of"].tolist()
    sizes = rdf["n_orders"].tolist()
    rates = [f"{v:.4f}" for v in rdf["rate"].tolist()]
    eloes = rdf["eloe"].tolist()

    metric_rows = "".join(
        f"<tr><td><strong>{m['metric']}</strong></td><td>{m['meaning']}</td><td>{m['definition']}</td></tr>"
        for m in METRIC_DEFINITIONS
    )

    # 头对头：每年 1 月 1 日对齐，横轴为年内第几天
    resolution_traces = []
    delivery_traces = []
    colors = {"2023": "#7A8B76", "2024": COLOR_ASH, "2025": COLOR_OWN, "2026": "#6A93B8"}
    if delivery_df:
        for year, data in delivery_df.items():
            color = colors.get(year, COLOR_OWN)
            for key, label, dash in (("resolution", "落定率", "solid"), ("actual_delivery", "实际交付率", "solid")):
                points = data.get(key) or []
                if points:
                    target = resolution_traces if key == "resolution" else delivery_traces
                    target.append(
                        f"{{x: {json.dumps([p['x'] for p in points])}, y: {json.dumps([p['y'] for p in points])}, "
                        f"type: 'scatter', mode: 'lines', name: '{year} {label}', line: {{color: '{color}', width: 2, dash: '{dash}'}}, "
                        f"hovertemplate: '锁单后第 %{{x}} 天<br>{year} {label} %{{y:.1%}}<extra></extra>'}}"
                    )
            if year == "2026" and data.get("forecast_delivery"):
                points = data["forecast_delivery"]
                delivery_traces.append(
                    f"{{x: {json.dumps([p['x'] for p in points])}, y: {json.dumps([p['y'] for p in points])}, "
                    f"type: 'scatter', mode: 'lines', name: '2026 预测交付率（ELOE补足）', line: {{color: '{COLOR_EVENT}', width: 2, dash: 'dash'}}, "
                    f"hovertemplate: '锁单后第 %{{x}} 天<br>2026 预测交付率 %{{y:.1%}}<extra></extra>'}}"
                )
    resolution_traces_html = ",\n".join(resolution_traces)
    delivery_traces_html = ",\n".join(delivery_traces)
    # 对齐 analyze-2025: 30/98 日交付率 = 半透明散点 + LOWESS 平滑曲线（frac=0.2）
    # 配色遵循品牌风格：30 日=蓝(COLOR_OWN)，98 日=金(COLOR_EVENT)
    age_traces = []
    age_series_spec = [
        ("30", COLOR_OWN, "rgba(23, 74, 124, 0.3)", "y"),
        ("98", COLOR_EVENT, "rgba(215, 154, 54, 0.3)", "y2"),
    ]
    for n, line_color, scatter_rgba, yaxis in age_series_spec:
        points = (delivery_age_df or {}).get(n, {})
        xs = points.get("x") or []
        ys = points.get("y") or []
        counts = points.get("count") or []
        if not xs:
            continue
        age_traces.append(
            f"{{x: {json.dumps(xs)}, y: {json.dumps(ys)}, type: 'scatter', mode: 'markers', "
            f"name: '{n} 日交付率（日度）', yaxis: '{yaxis}', "
            f"marker: {{size: 6, color: '{scatter_rgba}'}}, "
            f"customdata: {json.dumps(counts)}, "
            f"hovertemplate: '%{{x}}<br>{n} 日内交付率 %{{y:.1%}}<br>(%{{customdata}} 单)<extra></extra>'}}"
        )
        if _HAS_LOWESS and len(xs) >= 10:
            base = pd.Timestamp(xs[0])
            x_num = np.array([(pd.Timestamp(v) - base).days for v in xs], dtype=float)
            y_arr = np.array([float(v) for v in ys], dtype=float)
            valid = np.isfinite(y_arr)
            if int(valid.sum()) > 10:
                sm = _lowess(y_arr[valid], x_num[valid], frac=0.2)
                smooth_x = [v for i, v in enumerate(xs) if valid[i]]
                age_traces.append(
                    f"{{x: {json.dumps(smooth_x)}, y: {json.dumps([f'{float(v):.4f}' for v in sm[:, 1]])}, "
                    f"type: 'scatter', mode: 'lines', name: '{n} 日趋势 (LOWESS)', yaxis: '{yaxis}', "
                    f"line: {{color: '{line_color}', width: 3}}, "
                    f"hovertemplate: '%{{x}}<br>{n} 日趋势 %{{y:.1%}}<extra></extra>'}}"
                )
    age_traces_html = ",\n".join(age_traces)

    pool_label = "当年 1 月 1 日起的存量（未开票未退订）" if pool_window == "cumulative" else "观察点前 365 天锁单（未开票未退订）"

    current_day = int(pd.Timestamp(as_of).dayofyear)

    def num(v):
        return f"{v:,}"

    # 表格行
    table_rows = []
    for _, r in rdf.iterrows():
        rate_pct = f"{r['rate']:.1%}"
        table_rows.append(
            f"<tr><td>{r['as_of']}</td><td class='num'>{num(r['n_orders'])}</td>"
            f"<td class='num'>{num(int(r['eloe']))}</td><td class='num'>{num(int(r['at_risk']))}</td>"
            f"<td class='num'>{rate_pct}</td>"
            f"<td class='num'>{r['zombie_share']:.1%}</td></tr>"
        )
    table_rows_html = "\n".join(table_rows)

    # 年份均值卡片
    yearly_cards = ""
    for y, m in stats["yearly_mean"].items():
        yearly_cards += (
            f'<div class="kpi-card"><div class="label">{y} 平均有效率</div>'
            f'<div class="value">{m:.1%}</div></div>'
        )

    kpis = (
        f'<div class="kpi-card"><div class="label">历史最高有效率</div>'
        f'<div class="value">{stats["max_rate"]:.1%}</div>'
        f'<div class="change neutral">{stats["max_date"]} · 悬置池 {num(stats["max_n"])}</div></div>'
        f'<div class="kpi-card"><div class="label">历史最低有效率</div>'
        f'<div class="value">{stats["min_rate"]:.1%}</div>'
        f'<div class="change neutral">{stats["min_date"]} · 悬置池 {num(stats["min_n"])}</div></div>'
        f'<div class="kpi-card"><div class="label">最新观察点有效率</div>'
        f'<div class="value">{stats["latest_rate"]:.1%}</div>'
        f'<div class="change neutral">{stats["latest_date"]} · 悬置池 {num(stats["latest_n"])}</div></div>'
        f'<div class="kpi-card"><div class="label">相关性（规模 × 有效率）</div>'
        f'<div class="value">r = {stats["corr_size_rate"]:.2f}</div>'
        f'<div class="change neutral">年份控制后偏相关</div></div>'
        f'<div class="kpi-card"><div class="label">最新风险暴露量</div>'
        f'<div class="value">{num(int(rdf["at_risk"].iloc[-1]))} 单</div>'
        f'<div class="change neutral">历史均值 {num(int(rdf["at_risk"].mean()))} · '
        f'P25~P75 {num(int(rdf["at_risk"].quantile(0.25)))}~{num(int(rdf["at_risk"].quantile(0.75)))}</div></div>'
    )

    # 散点图 traces（按年份着色）
    year_traces = []
    year_colors = ["#174A7C", "#4F6F82", "#D79A36", "#C06F45"]
    for i, (y, g) in enumerate(rdf.groupby("year")):
        color = year_colors[i % len(year_colors)]
        year_traces.append(
            f"{{x: {json.dumps(g['n_orders'].tolist())}, y: {json.dumps([f'{v:.4f}' for v in g['rate']])}, "
            f"mode: 'markers', name: '{y}', text: {json.dumps(g['as_of'].tolist())}, "
            f"hovertemplate: '%{{text}}<br>悬置池 %{{x:,}} 单<br>有效率 %{{y:.1%}}<extra></extra>', "
            f"marker: {{size: 12, color: '{color}', opacity: 0.85, line: {{width: 1, color: 'white'}}}}}}"
        )
    scatter_traces = ",\n".join(year_traces)

    # LOWESS 趋势线（悬置池规模 × 有效率 关系平滑）
    lowess_trace = ""
    if _HAS_LOWESS and len(rdf) >= 5:
        x_pts = rdf["n_orders"].to_numpy(dtype=float)
        y_pts = rdf["rate"].to_numpy(dtype=float)
        sm = _lowess(y_pts, x_pts, frac=0.4, it=3)
        sm = sm[np.isfinite(sm[:, 1])]
        if len(sm) >= 2:
            lowess_trace = (
                f"{{x: {json.dumps([float(v) for v in sm[:, 0]])}, "
                f"y: {json.dumps([f'{float(v):.4f}' for v in sm[:, 1]])}, "
                f"type: 'scatter', mode: 'lines', name: 'LOWESS 趋势', "
                f"line: {{color: '{COLOR_NEG}', width: 2.5}}, "
                f"hovertemplate: '悬置池 %{{x:,}} 单<br>LOWESS 有效率 %{{y:.1%}}<extra></extra>'}}"
            )

    # 时间趋势 traces
    trend_lines = [
        f"{{x: {json.dumps(dates)}, y: {json.dumps(sizes)}, name: '悬置池规模', yaxis: 'y', "
        f"mode: 'lines+markers', line: {{color: '{COLOR_OWN}', width: 2}}, "
        f"marker: {{size: 6, color: '{COLOR_OWN}'}}, hovertemplate: '%{{x}}<br>悬置池 %{{y:,}} 单<extra></extra>'}}",
        f"{{x: {json.dumps(dates)}, y: {json.dumps(rates)}, name: '有效率', yaxis: 'y2', "
        f"mode: 'lines+markers', line: {{color: '{COLOR_EVENT}', width: 2}}, "
        f"marker: {{size: 6, color: '{COLOR_EVENT}'}}, hovertemplate: '%{{x}}<br>有效率 %{{y:.1%}}<extra></extra>'}}",
    ]
    trend_traces = ",\n".join(trend_lines)

    # 僵尸占比 trace（第三张图）
    zombie_trace = (
        f"{{x: {json.dumps(dates)}, y: {json.dumps([f'{v:.4f}' for v in rdf['zombie_share']])}, "
        f"mode: 'lines+markers', line: {{color: '{COLOR_NEG}', width: 2}}, "
        f"marker: {{size: 6, color: '{COLOR_NEG}'}}, hovertemplate: '%{{x}}<br>>90天占比 %{{y:.1%}}<extra></extra>'}}"
    )

    # 风险暴露量 trace（第四张图）
    risk_vals = rdf["at_risk"].tolist()
    risk_q25 = float(np.percentile(risk_vals, 25))
    risk_q75 = float(np.percentile(risk_vals, 75))
    risk_mean = float(np.mean(risk_vals))
    risk_latest = float(risk_vals[-1])
    risk_traces = (
        f"{{x: {json.dumps(dates)}, y: {json.dumps(risk_vals)}, type: 'scatter', mode: 'lines', "
        f"name: '风险暴露量', fill: 'tozeroy', line: {{color: '{COLOR_EVENT}', width: 2}}, "
        f"hovertemplate: '%{{x}}<br>风险暴露量 %{{y:,.0f}} 单<extra></extra>'}},"
        f"{{x: {json.dumps(dates)}, y: {json.dumps([round(risk_mean,1)]*len(dates))}, type: 'scatter', mode: 'lines', "
        f"name: '历史均值', line: {{color: '{COLOR_ASH}', width: 1, dash: 'dot'}}, hovertemplate: '均值 %{{y:,.0f}}<extra></extra>'}}"
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Backlog 有效率历史分析 | {as_of}</title>
<link rel="stylesheet" href="{static_prefix}/templates/report_style.css" />
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
</head>
<body>
<header>
  <div class="container">
    <div class="brand">
      <img class="brand-avatar" src="{static_prefix}/assets/brand/raccoon_avatar_light.png" alt="" />
      <span class="brand-name">Raccoon Research</span>
    </div>
    <span class="header-meta">有效锁单当量 (ELOE) | 截至 {as_of}</span>
  </div>
</header>

<main class="container">
  <section class="hero">
    <h1>Backlog 有效率历史分析</h1>
    <p>Nominal Backlog is a system state; Effective Backlog is a forecast.</p>
    <p>2023-01 起每月初观察点（含最新数据日）· 悬置池 = {pool_label} · 有效率 = ELOE ÷ 悬置池（已剔除池子 &lt;100 单的噪声观察点）</p>
  </section>

  <section class="card">
    <h2>指标口径速览 · Locked Order Health / 锁单健康度</h2>
    <div class="table-wrap"><table class="report-table">
      <thead><tr><th>指标</th><th>一句话回答</th><th>计算口径</th></tr></thead>
      <tbody>
        {metric_rows}
      </tbody>
    </table></div>
    <div class="section-note">
      <strong>Backlog Balance Sheet 恒等式：</strong>
      悬置池 = ELOE + 风险暴露量（Nominal Backlog = Effective Backlog + At-risk Backlog）；
      预测最终交付率 = 实际交付率 + ELOE ÷ 累计锁单。
    </div>
    <div class="section-note">
      三句话理解指标体系：<br>
      ① 实际交付率看已经兑现多少；30/98 日交付率看兑现速度；预测最终交付率看最终能兑现多少。<br>
      ② 悬置池看还有多少没结果；ELOE 看这些订单还值多少；风险暴露量看其中可能损失多少。<br>
      ③ 落定率负责描述整个订单生命周期走到了什么程度。
    </div>
  </section>

  <section class="card">
    <h2>⓪ 锁单交付率（落定率）年度头对头趋势</h2>
    <div class="chart-box" id="chart-resolution" style="height:380px;"></div>
    <div class="section-note">落定率 = (当年累计锁单 − 待开票未退订锁单) ÷ 当年累计锁单 = 1 − 悬置率。每年 1 月 1 日对齐，比较各年度锁单离开悬置状态的节奏。</div>
  </section>

  <section class="card">
    <h2>⓪-b 实际交付率与预测交付率</h2>
    <div class="chart-box" id="chart-delivery" style="height:420px;"></div>
    <div class="section-note">实线为累计实际交付率；2026 虚线为预测最终交付率 = (已交付 + ELOE) ÷ 总锁单 = 实际交付率 + ELOE ÷ 累计锁单，用于补足近期订单尚未完成交付造成的尾部低估。</div>
  </section>

  <section class="card">
    <h2>⓪-c 30 日与 98 日交付率趋势</h2>
    <div class="chart-box" id="chart-delivery-age" style="height:380px;"></div>
    <div class="section-note">口径与 analyze-2025 §3.1 完全一致：按每日锁单 cohort 计算，rate_Nd = 当日锁单中 (开票时间 − 锁单时间) ≤ N 天的订单数 ÷ 当日唯一锁单数；交付事件 = 开票（invoice_upload_time），无成熟窗口过滤（近期 cohort 天然偏低，由 LOWESS 平滑呈现）。半透明散点为日度观察值，实线为 LOWESS 平滑趋势（frac=0.2）；30 日（品牌蓝，左轴）与 98 日（品牌金，右轴）分轴展示。取值范围与其他图表一致，自 2023-01-01 起。</div>
  </section>

  <section class="kpi-grid">
    {kpis}
  </section>

  <section class="card">
    <h2>① 悬置池规模 × 有效率 散点图</h2>
    <div class="chart-box" id="chart-scatter" style="height:480px;"></div>
    <div class="section-note">横轴 = 悬置池规模（单），纵轴 = 有效率。不同颜色代表年份；深红实线为 LOWESS 平滑趋势（frac=0.4），反映规模与效率的整体关系形态。hover 可查看具体观察点。</div>
  </section>

  <section class="card">
    <h2>② 时间趋势：悬置池规模 vs 有效率（双轴）</h2>
    <div class="chart-box" id="chart-trend" style="height:420px;"></div>
    <div class="section-note">蓝色 = 悬置池规模（左轴），金色 = 有效率（右轴）。观察两者在时间上的同步/背离关系。</div>
  </section>

  <section class="card">
    <h2>③ >90 天僵尸订单占比（悬置池质量构成）</h2>
    <div class="chart-box" id="chart-zombie" style="height:360px;"></div>
    <div class="section-note">>90 天订单占比越高，池子越"老"，有效率越低。这是解释散点图关系的关键中间变量。</div>
  </section>

  <section class="card">
    <h2>④ Backlog 风险暴露量（At-Risk Backlog）</h2>
    <div class="chart-box" id="chart-risk" style="height:420px;"></div>
    <div class="section-note">
      风险暴露量 = 名义 Backlog × (1 − 有效率) = 悬置池 − ELOE。衡量当前池子里预计最终无法兑现的订单规模（订单口径）。
      金色实线为最新风险暴露量，灰色虚线为历史均值，阴影区间为历史 25%~75% 分位带。风险暴露量上升 = 名义池扩大或池子质量恶化。
    </div>
  </section>

  <section class="card">
    <h2>全量观察点明细</h2>
    <div class="table-wrap"><table class="report-table">
      <thead><tr><th>观察点</th><th>悬置池（单）</th><th>ELOE</th><th>风险暴露量</th><th>有效率</th><th>>90天占比</th></tr></thead>
      <tbody>
        {table_rows_html}
      </tbody>
    </table></div>
  </section>
</main>

<footer>
  <img class="brand-sig" src="{static_prefix}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />
  <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>

<script>
Plotly.newPlot('chart-resolution', [
  {resolution_traces_html}
], {{
  title: {{text: '锁单落定率年度头对头趋势'}},
  xaxis: {{title: '年内第几天', range: [1, 366]}},
  yaxis: {{title: '落定率', tickformat: '.0%', range: [0, 1]}},
  margin: {{l: 60, r: 30, t: 50, b: 50}},
  paper_bgcolor: 'white', plot_bgcolor: 'white',
  font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
  legend: {{orientation: 'h', y: -0.25}},
  shapes: [{{type: 'line', x0: {current_day}, x1: {current_day}, y0: 0, y1: 1,
            line: {{color: '{COLOR_NEG}', width: 1.5, dash: 'dot'}}}}],
  annotations: [{{x: {current_day}, y: 0.97, xanchor: 'left', xref: 'x', yref: 'y',
                  text: '当前观察点 {as_of}', showarrow: false,
                  font: {{color: '{COLOR_NEG}', size: 12}},
                  bgcolor: '#FFFFFF', bordercolor: '{COLOR_NEG}', borderwidth: 1}}]
}});
Plotly.newPlot('chart-delivery', [
  {delivery_traces_html}
], {{
  title: {{text: '实际交付率与预测交付率年度头对头趋势'}},
  xaxis: {{title: '年内第几天', range: [1, 366]}},
  yaxis: {{title: '交付率', tickformat: '.0%', range: [0, 1]}},
  margin: {{l: 60, r: 30, t: 50, b: 50}},
  paper_bgcolor: 'white', plot_bgcolor: 'white',
  font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
  legend: {{orientation: 'h', y: -0.25}},
  shapes: [{{type: 'line', x0: {current_day}, x1: {current_day}, y0: 0, y1: 1,
            line: {{color: '{COLOR_NEG}', width: 1.5, dash: 'dot'}}}}]
}});
Plotly.newPlot('chart-delivery-age', [
  {age_traces_html}
], {{
  title: {{text: '30 日与 98 日交付率时间趋势'}},
  xaxis: {{title: '观察点', type: 'date', range: ['2023-01-01', '{as_of}']}},
  yaxis: {{title: '30 日交付率', tickformat: '.0%', range: [0, 1]}},
  yaxis2: {{title: '98 日交付率', overlaying: 'y', side: 'right', tickformat: '.0%', range: [0, 1]}},
  margin: {{l: 60, r: 60, t: 50, b: 50}},
  paper_bgcolor: 'white', plot_bgcolor: 'white',
  font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
  legend: {{orientation: 'h', y: -0.25}}
}});
Plotly.newPlot('chart-scatter', [
  {scatter_traces},
  {lowess_trace}
], {{
  title: {{text: '悬置池规模 vs 有效率（按年份着色）'}},
  xaxis: {{title: '悬置池规模（单）'}},
  yaxis: {{title: '有效率', tickformat: '.0%', range: [0, {stats['y_max_rate']:.05f}]}},
  margin: {{l: 60, r: 40, t: 50, b: 50}},
  paper_bgcolor: 'white', plot_bgcolor: 'white',
  font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
  legend: {{orientation: 'h', y: -0.25}},
  shapes: [{{type: 'line', x0: 0, x1: {int(rdf['n_orders'].max())*1.1}, y0: {stats['mean_rate']:.4f}, y1: {stats['mean_rate']:.4f},
            line: {{color: '{COLOR_ASH}', width: 1, dash: 'dot'}}}},
    {{type: 'line', x0: {int(rdf['n_orders'].mean())}, x1: {int(rdf['n_orders'].mean())}, y0: 0, y1: {stats['y_max_rate']:.05f},
            line: {{color: '{COLOR_ASH}', width: 1, dash: 'dot'}}}}]
}});
Plotly.newPlot('chart-trend', [
  {trend_traces}
], {{
  title: {{text: '悬置池规模与有效率时间趋势'}},
  xaxis: {{title: '观察点'}},
  yaxis: {{title: '悬置池规模（单）'}},
  yaxis2: {{title: '有效率', overlaying: 'y', side: 'right', tickformat: '.0%', range: [0, {stats['y_max_rate']:.05f}]}},
  margin: {{l: 60, r: 60, t: 50, b: 50}},
  paper_bgcolor: 'white', plot_bgcolor: 'white',
  font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
  legend: {{orientation: 'h', y: -0.25}}
}});
Plotly.newPlot('chart-zombie', [
  {zombie_trace}
], {{
  title: {{text: '>90 天僵尸订单占比'}},
  xaxis: {{title: '观察点'}},
  yaxis: {{title: '>90 天订单占比', tickformat: '.0%'}},
  margin: {{l: 60, r: 30, t: 50, b: 50}},
  paper_bgcolor: 'white', plot_bgcolor: 'white',
  font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}}
}});
Plotly.newPlot('chart-risk', [
  {risk_traces}
], {{
  title: {{text: 'Backlog 风险暴露量（At-Risk Backlog）'}},
  xaxis: {{title: '观察点'}},
  yaxis: {{title: '风险暴露量（单）'}},
  margin: {{l: 60, r: 30, t: 50, b: 50}},
  paper_bgcolor: 'white', plot_bgcolor: 'white',
  font: {{family: '-apple-system, sans-serif', color: '#1F2D3D'}},
  legend: {{orientation: 'h', y: -0.25}},
  shapes: [{{type: 'line', x0: '{dates[0]}', x1: '{dates[-1]}', y0: {risk_mean:.1f}, y1: {risk_mean:.1f},
            line: {{color: '{COLOR_ASH}', width: 1, dash: 'dot'}}}}]
}});
</script>
</body>
</html>
"""


def format_terminal(rdf: pd.DataFrame, stats: dict) -> str:
    lines = []
    lines.append(f"Backlog 有效率历史分析（{rdf['as_of'].min()} ~ {rdf['as_of'].max()}，共 {len(rdf)} 个观察点）")
    lines.append(f"  最高: {stats['max_rate']:.1%} @ {stats['max_date']} (n={stats['max_n']:,})")
    lines.append(f"  最低: {stats['min_rate']:.1%} @ {stats['min_date']} (n={stats['min_n']:,})")
    lines.append(f"  最新: {stats['latest_rate']:.1%} @ {stats['latest_date']} (n={stats['latest_n']:,})")
    latest_risk = int(rdf['at_risk'].iloc[-1])
    lines.append(f"  最新风险暴露量: {latest_risk:,} 单（历史均值 {int(rdf['at_risk'].mean()):,}，P25~P75 {int(rdf['at_risk'].quantile(0.25)):,}~{int(rdf['at_risk'].quantile(0.75)):,}）")
    lines.append(f"  相关性(规模×有效率): r = {stats['corr_size_rate']:.3f}")
    lines.append(f"  僵尸占比(>90d) 与有效率相关: r = {stats['corr_zombie_rate']:.3f}")
    for y, m in stats["yearly_mean"].items():
        lines.append(f"  {y} 平均有效率: {m:.1%}")
    return "\n".join(lines)


def _static_prefix(output_dir: Path) -> str:
    try:
        return str(Path(_WS_ROOT).resolve().relative_to(output_dir.resolve())).replace("\\", "/")
    except ValueError:
        return "../.."

def main():
    args = parse_args()
    cmd = "python " + " ".join(sys.argv)
    df_all = load_data()
    as_of_default = df_all["lock_time"].max().normalize()
    as_of = pd.Timestamp(args.as_of) if args.as_of else as_of_default

    rdf = compute_history(as_of, args.pool_window, args.frequency)
    if rdf.empty:
        sys.exit("❌ 无历史观察点数据")

    effective_by_date = dict(zip(
        rdf["as_of"].tolist(),
        (rdf["eloe"] / rdf["n_orders"]).tolist(),
    ))
    years = tuple(args.years) if args.years else (2024, 2025, 2026)
    delivery_df = compute_delivery_head_to_head(as_of, effective_by_date, years=years)
    delivery_age_df = compute_delivery_age_snapshot(
        [pd.Timestamp(s) for s in rdf["as_of"].tolist()], as_of)

    yearly_mean = {str(y): rdf[rdf["year"] == y]["rate"].mean() for y in sorted(rdf["year"].unique())}
    stats = {
        "max_rate": rdf["rate"].max(),
        "max_date": rdf.loc[rdf["rate"].idxmax(), "as_of"],
        "max_n": int(rdf.loc[rdf["rate"].idxmax(), "n_orders"]),
        "min_rate": rdf["rate"].min(),
        "min_date": rdf.loc[rdf["rate"].idxmin(), "as_of"],
        "min_n": int(rdf.loc[rdf["rate"].idxmin(), "n_orders"]),
        "latest_rate": rdf["rate"].iloc[-1],
        "latest_date": rdf["as_of"].iloc[-1],
        "latest_n": int(rdf["n_orders"].iloc[-1]),
        "mean_rate": float(rdf["rate"].mean()),
        "y_max_rate": float(np.ceil(rdf["rate"].max() * 20) / 20),
        "corr_size_rate": _corr(rdf["n_orders"], rdf["rate"]),
        "corr_zombie_rate": _corr(rdf["zombie_share"], rdf["rate"]),
        "yearly_mean": yearly_mean,
    }

    if args.format == "terminal":
        print(format_terminal(rdf, stats))
        print()
        print("锁单交付率（落定率）年度头对头曲线：")
        for year, data in delivery_df.items():
            latest = data["resolution"][-1]["y"] if data["resolution"] else None
            actual = data["actual_delivery"][-1]["y"] if data["actual_delivery"] else None
            forecast = data["forecast_delivery"][-1]["y"] if data["forecast_delivery"] else None
            print(f"  {year} 年：第 1~{data['resolution'][-1]['x']} 天 | 落定率 {latest:.1%} | 实际交付率 {actual:.1%}"
                  + (f" | 预测交付率 {forecast:.1%}" if forecast is not None else ""))
        return
    if args.format == "json":
        print(json.dumps({k: v for k, v in stats.items() if k not in ("yearly_mean",)} | {"yearly_mean": {str(k): round(v, 4) for k, v in yearly_mean.items()}, "rows": rdf.to_dict("records"), "delivery_snapshot": delivery_df}, ensure_ascii=False, indent=2))
        return

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    html = render_html(rdf, stats, str(as_of.date()), _static_prefix(out_dir), args.pool_window, delivery_df, delivery_age_df)
    out_path = out_dir / f"backlog_rate_history_{as_of:%Y%m%d}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"✅ 报告已生成: {out_path}")


if __name__ == "__main__":
    main()
