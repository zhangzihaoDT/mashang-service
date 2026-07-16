#!/usr/bin/env python
"""
Cohort 锁单预测回测 — 三段式成熟度模型（滚动原点回测）

通过 assign_data.csv 的历史线索数据，使用三段式成熟度模型预测 30 日锁单转化，
与真实值对比计算全面评估指标，包含基线对照、分层评估和异常分析。

用法:
    python research_scripts/lock_predict_backtest.py
    python research_scripts/lock_predict_backtest.py --format json
    python research_scripts/lock_predict_backtest.py --format terminal

Output:
    outputs/reports/lock_predict_backtest.html
"""

import sys, argparse, json, warnings
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
from scipy import stats as sp_stats

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

from utils.plotly_theme import ZH, apply_zh_theme
from utils.result_contract import build_success_contract, build_error_contract, save_contract_json

ASSIGN_CSV = REPO_ROOT / "dataset" / "assign_data.csv"
OUTPUT_HTML = _WS_ROOT / "outputs" / "reports" / "lock_predict_backtest.html"

# ── Acceptance Thresholds Config ──
THRESHOLDS = {
    "mape_max": 0.20,
    "wape_max": 0.22,
    "rmse_mae_ratio_max": 1.60,
    "within_20pct_min": 0.70,
    "within_30pct_min": 0.80,
    "r2_min": 0.70,
    "abs_bias_pct_max": 0.05,
    "median_actual_forecast_ratio_min": 0.95,
    "median_actual_forecast_ratio_max": 1.05,
}

# ── Launch Event Model Config ──
EVENT_SOURCE = REPO_ROOT / "shared" / "schema" / "business_definition.json"
EVENT_CONFIG = {
    "enabled": True,
    "source_path": "shared/schema/business_definition.json",
    "prior_strength": 30,
    "include_overlap_features": True,
    "max_multiplier": 3.0,
    "acceptance": {
        "overall_wape_relative_improvement_min": 0.03,
        "event_window_wape_relative_improvement_min": 0.10,
        "normal_window_wape_degradation_max_pp": 0.01,
    },
}
LIFECYCLE_PHASES = [
    "presale_day", "presale_active", "launch_day",
    "launch_post_d1_d3", "launch_post_d4_d7",
    "benefit_active", "benefit_countdown", "benefit_end_day",
    "post_benefit",
]
HAS_EVENTS = False

# ── Brand Colors ──
OWN = ZH["own"]
EVENT = ZH["event"]
ASH = ZH["ash"]
POSITIVE = ZH["positive"]
NEGATIVE = ZH["negative"]
MUTED_COLOR = ZH["neutral"]
SKY_MUTED = ZH["sky_muted"]
DEEP = "#06213D"
LIGHT = "#DDEFF8"

BLUE = "\033[38;2;23;74;124m"
DEEP_B = "\033[38;2;6;33;61m"
GOLD = "\033[38;2;215;154;54m"
CYAN = "\033[38;2;126;205;235m"
MUTED = "\033[38;2;107;124;143m"
BOLD = "\033[1m"
RST = "\033[0m"
GREEN = "\033[38;2;42;157;143m"
RED = "\033[38;2;217;95;89m"


def _b(t): return f"{BOLD}{t}{RST}"
def _blue(t): return f"{BLUE}{t}{RST}"
def _gold(t): return f"{GOLD}{t}{RST}"
def _green(t): return f"{GREEN}{t}{RST}"
def _red(t): return f"{RED}{t}{RST}"
def _muted(t): return f"{MUTED}{t}{RST}"
def _ruler(c="━", w=64): return f"{CYAN}{c*w}{RST}"


def parse_args():
    p = argparse.ArgumentParser(description="Cohort 锁单预测回测 (三段式成熟度, rolling-origin)")
    p.add_argument("--format", default="terminal", choices=["terminal", "json"])
    p.add_argument("--output", type=str, help="输出目录")
    return p.parse_args()


def _parse_cn_date(s: pd.Series) -> pd.Series:
    s = s.astype(str)
    parts = s.str.extract(r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日")
    dt = pd.to_datetime(parts["y"] + "-" + parts["m"] + "-" + parts["d"], errors="coerce").dt.normalize()
    if dt.notna().any():
        return dt
    return pd.to_datetime(s, errors="coerce").dt.normalize()


def load_assign_data():
    df = pd.read_csv(str(ASSIGN_CSV))
    df["_date"] = _parse_cn_date(df["Assign Time 年/月/日"])
    df = df[df["_date"].notna()].sort_values("_date").reset_index(drop=True)
    n_fn = lambda c: pd.to_numeric(c.astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
    df["_leads"] = n_fn(df["下发线索数"])
    df["_lock0"] = n_fn(df["下发线索当日锁单数 (门店)"])
    df["_lock7"] = n_fn(df["下发线索 7 日锁单数"])
    df["_lock30"] = n_fn(df["下发线索 30 日锁单数"])
    return df


def load_daily_lock_count():
    order_parquet = REPO_ROOT / "dataset" / "order_data.parquet"
    if not order_parquet.exists():
        return None
    order_df = pd.read_parquet(str(order_parquet))
    order_df["lock_date"] = pd.to_datetime(order_df["lock_time"], errors="coerce").dt.normalize()
    daily = order_df[order_df["lock_date"].notna()].groupby("lock_date")["order_number"].nunique().reset_index()
    daily.columns = ["date", "daily_lock_count"]
    daily["date"] = pd.to_datetime(daily["date"])
    return daily


# ── Launch Event Parsing ──

def parse_launch_events(source_path=None):
    global HAS_EVENTS
    path = Path(source_path or EVENT_SOURCE)
    if not path.exists():
        warnings.warn(f"事件定义文件不存在: {path}")
        HAS_EVENTS = False
        return pd.DataFrame()
    with open(str(path)) as f:
        data = json.load(f)
    periods = data.get("time_periods", {})
    if not periods:
        warnings.warn("事件定义文件中无 time_periods")
        HAS_EVENTS = False
        return pd.DataFrame()
    rows = []
    for eid, info in periods.items():
        # end is required
        if "end" not in info:
            raise ValueError(f"事件 {eid} 缺少必要字段 'end'")
        try:
            end_dt = pd.Timestamp(info["end"]).normalize()
        except Exception:
            raise ValueError(f"事件 {eid} 的 end 日期非法: {info['end']}")
        if pd.isna(end_dt):
            raise ValueError(f"事件 {eid} 的 end 无法解析为日期: {info['end']}")
        # start is optional
        start_dt = None
        if "start" in info and info["start"]:
            try:
                start_dt = pd.Timestamp(info["start"]).normalize()
            except Exception:
                raise ValueError(f"事件 {eid} 的 start 日期非法: {info['start']}")
        # finish is required
        if "finish" not in info:
            raise ValueError(f"事件 {eid} 缺少必要字段 'finish'")
        try:
            finish_dt = pd.Timestamp(info["finish"]).normalize()
        except Exception:
            raise ValueError(f"事件 {eid} 的 finish 日期非法: {info['finish']}")
        if pd.isna(finish_dt):
            raise ValueError(f"事件 {eid} 的 finish 无法解析为日期: {info['finish']}")
        row = {
            "event_id": eid, "event_name": eid, "event_type": "launch",
            "event_date": end_dt,  # keep for backward compat
            "presale_date": start_dt,
            "launch_date": end_dt,
            "benefit_end_date": finish_dt,
            "has_presale": start_dt is not None,
            "source": str(path),
        }
        rows.append(row)
    events = pd.DataFrame(rows).sort_values("event_date").reset_index(drop=True)
    HAS_EVENTS = len(events) > 0
    return events


def compute_event_features(rd, events, date_col="date"):
    if events.empty:
        for k in LIFECYCLE_PHASES:
            rd[f"{k}_count"] = 0
        rd["active_event_count"] = 0
        rd["has_event_overlap"] = 0
        rd["same_series_overlap"] = 0
        rd["in_lifecycle_window"] = False
        rd["active_lifecycle_ids"] = ""
        return rd

    rd = rd.copy()
    for k in LIFECYCLE_PHASES:
        rd[f"{k}_count"] = 0
    rd["active_event_count"] = 0
    rd["has_event_overlap"] = 0
    rd["same_series_overlap"] = 0
    rd["in_lifecycle_window"] = False
    rd["active_lifecycle_ids"] = ""

    def _get_phase(eid, cd, ev):
        """Determine lifecycle stage for a single model on a given date."""
        ld = ev["launch_date"]
        bd = ev["benefit_end_date"]
        has_ps = ev["has_presale"]
        sd = ev["presale_date"]

        if cd == bd:
            return "benefit_end_day"
        if has_ps and sd and (bd - pd.Timedelta(days=7) <= cd <= bd - pd.Timedelta(days=1)):
            return "benefit_countdown"
        if has_ps and sd and cd == sd:
            return "presale_day"
        if has_ps and sd and (sd < cd < ld):
            return "presale_active"
        if cd == ld:
            return "launch_day"
        if ld < cd <= ld + pd.Timedelta(days=3):
            return "launch_post_d1_d3"
        if ld + pd.Timedelta(days=3) < cd <= ld + pd.Timedelta(days=7):
            return "launch_post_d4_d7"
        if ld + pd.Timedelta(days=7) < cd <= bd - pd.Timedelta(days=8):
            return "benefit_active"
        if bd < cd <= bd + pd.Timedelta(days=7):
            return "post_benefit"
        # benefit_countdown for models without presale
        if not has_ps and bd - pd.Timedelta(days=7) <= cd <= bd - pd.Timedelta(days=1):
            return "benefit_countdown"
        return None

    for idx, row in rd.iterrows():
        cd = row[date_col]
        active_ids = []
        active_phases = []
        for _, ev in events.iterrows():
            phase = _get_phase(ev["event_id"], cd, ev)
            if phase:
                rd.at[idx, f"{phase}_count"] += 1
                active_ids.append(ev["event_id"])
                active_phases.append(phase)
        rd.at[idx, "active_event_count"] = len(active_ids)
        rd.at[idx, "has_event_overlap"] = 1 if len(active_ids) > 1 else 0
        rd.at[idx, "in_lifecycle_window"] = len(active_ids) > 0
        rd.at[idx, "active_lifecycle_ids"] = ",".join(active_ids)

    return rd


def compute_rolling_event_coefficients(rd, df, events):
    if events.empty:
        return None
    ps = EVENT_CONFIG["prior_strength"]
    dates = sorted(rd["date"].unique())
    df_events = compute_event_features(df, events, date_col="_date")
    coefficients = []
    for d in dates:
        available = df_events[df_events["_date"] < d]
        mature = available[available["_date"] <= d - pd.Timedelta(days=30)]
        if mature.empty or mature["_leads"].sum() <= 0:
            coefficients.append({k: 0.0 for k in LIFECYCLE_PHASES})
            continue
        phase_betas = {}
        for pk in LIFECYCLE_PHASES:
            in_phase = mature[mature[f"{pk}_count"] > 0]
            not_in = mature[mature[f"{pk}_count"] == 0]
            if len(in_phase) < 3:
                phase_betas[pk] = 0.0
                continue
            obs_rate = float(in_phase["_lock30"].sum()) / float(in_phase["_leads"].sum()) if in_phase["_leads"].sum() > 0 else 0
            base_rate = float(not_in["_lock30"].sum()) / float(not_in["_leads"].sum()) if not_in["_leads"].sum() > 0 else obs_rate
            if base_rate <= 0 or obs_rate <= 0:
                phase_betas[pk] = 0.0
                continue
            obs_log_ratio = np.log(obs_rate / base_rate)
            w = len(in_phase)
            posterior_beta = (w * obs_log_ratio + ps * 0.0) / (w + ps)
            phase_betas[pk] = posterior_beta
        coefficients.append(phase_betas)
    return coefficients


def apply_event_multiplier_log(control_pred, betas, count_features):
    if betas is None:
        return control_pred
    total_beta = 0.0
    for pk in LIFECYCLE_PHASES:
        count = count_features.get(pk, 0)
        if count > 0:
            total_beta += betas.get(pk, 0.0) * count
    total_beta = max(min(total_beta, np.log(EVENT_CONFIG["max_multiplier"])),
                     np.log(1.0 / EVENT_CONFIG["max_multiplier"]))
    return control_pred * np.exp(total_beta)


def compute_event_window_metrics(el):
    """Compute metrics for lifecycle window."""
    ew = el[el["in_lifecycle_window"]].copy() if "in_lifecycle_window" in el.columns else pd.DataFrame()
    if ew.empty:
        return None
    actual = ew["cohort_actual_30_lock"].values.astype(float)
    forecast = ew["cohort_pred_30_lock"].values.astype(float)
    error = actual - forecast
    abs_err = np.abs(error)
    sq_err = error ** 2
    sa = actual.sum()
    if sa <= 0:
        return {"n": len(ew), "mae": np.nan, "rmse": np.nan, "wape": np.nan, "mape": np.nan, "bias_pct": np.nan, "r2": np.nan}
    mae = float(abs_err.mean())
    rmse = float(np.sqrt(sq_err.mean()))
    wape = float(abs_err.sum() / sa)
    non_zero = actual > 0
    ape = abs_err[non_zero] / actual[non_zero]
    mape = float(ape.mean()) if len(ape) > 0 else np.nan
    bias = float((sa - forecast.sum()) / sa)
    if np.std(actual) > 0 and np.std(forecast) > 0:
        r2 = 1 - sq_err.sum() / ((actual - actual.mean()) ** 2).sum()
    else:
        r2 = np.nan
    return {"n": len(ew), "mae": mae, "rmse": rmse, "wape": wape, "mape": mape, "bias_pct": bias, "r2": r2}


def compute_normal_window_metrics(el):
    """Compute metrics for normal period (not in any lifecycle window)."""
    nw = el[~el["in_lifecycle_window"]].copy() if "in_lifecycle_window" in el.columns else el.copy()
    if nw.empty:
        return None
    actual = nw["cohort_actual_30_lock"].values.astype(float)
    if "cohort_pred_30_lock" in nw.columns:
        forecast = nw["cohort_pred_30_lock"].values.astype(float)
    else:
        forecast = np.zeros_like(actual)
    error = actual - forecast
    abs_err = np.abs(error)
    sa = actual.sum()
    if sa <= 0:
        return {"n": len(nw)}
    wape = float(abs_err.sum() / sa)
    return {"n": len(nw), "wape": wape}


def compute_rolling_rates(df, as_of_date):
    """从 as_of_date 当时可获得的数据计算 r0, r7, avg_30d_rate (24mo window)."""
    available = df[df["_date"] <= as_of_date]
    window_start = as_of_date - pd.DateOffset(months=24)
    mature = available[(available["_date"] <= as_of_date - pd.Timedelta(days=30))
                       & (available["_date"] >= window_start)]
    if mature.empty or mature["_leads"].sum() <= 0:
        return None
    tl = float(mature["_leads"].sum())
    t0 = float(mature["_lock0"].sum())
    t7 = float(mature["_lock7"].sum())
    t30 = float(mature["_lock30"].sum())
    if t30 <= 0:
        return None
    return {
        "r0": t0 / t30,
        "r7": t7 / t30,
        "avg_30d_rate": t30 / tl,
        "mature_cohorts": len(mature),
        "mature_leads": int(tl),
        "mature_lock30": int(t30),
    }


def predict_one_day_v3(row, rates, age):
    if rates is None:
        return float(row["_lock30"]), "no_mature_baseline"
    if age >= 30:
        return float(row["_lock30"]), "actual"
    if age >= 7:
        p = float(row["_lock7"]) / rates["r7"] if rates["r7"] > 0 else float(row["_lock30"])
        return p, "lock7_proj"
    est_avg = float(row["_leads"]) * rates["avg_30d_rate"]
    if rates["r0"] > 0 and float(row["_lock0"]) > 0:
        est_day0 = float(row["_lock0"]) / rates["r0"]
        p = 0.5 * est_avg + 0.5 * est_day0
        return p, "weighted_avg"
    return est_avg, "estimated_via_avg"


def rolling_origin_backtest(df):
    """Rolling-origin backtest: 每个 cohort date 只使用当时可获得的数据。"""
    cutoff = df["_date"].max()
    min_date = df["_date"].min() + pd.Timedelta(days=30)
    results = []
    for _, row in df.iterrows():
        d = row["_date"]
        if d < min_date or d >= cutoff:
            continue
        as_of = min(d + pd.Timedelta(days=7), cutoff)
        age = (as_of - d).days
        rates = compute_rolling_rates(df, as_of)
        pred, method = predict_one_day_v3(row, rates, age)
        results.append({
            "date": d,
            "cohort_assign_count": int(float(row["_leads"])),
            "cohort_pred_30_lock": round(pred, 1),
            "cohort_actual_30_lock": int(float(row["_lock30"])),
            "cohort_actual_observed": int(float(row["_lock0"])),
            "prediction_method": method,
            "as_of_date": as_of,
            "age_at_prediction": age,
        })
    rd = pd.DataFrame(results)
    rd["maturity_days"] = (cutoff - rd["date"]).dt.days
    rd["is_fully_matured"] = rd["maturity_days"] >= 30
    rd["evaluation_eligible"] = rd["date"] <= cutoff - pd.Timedelta(days=30)
    rd["exclusion_reason"] = "已成熟"
    rd.loc[rd["evaluation_eligible"] == False, "exclusion_reason"] = "观察窗口未满30日"
    # For fully matured cohorts, observed = final
    rd.loc[rd["evaluation_eligible"], "cohort_actual_observed"] = rd.loc[rd["evaluation_eligible"], "cohort_actual_30_lock"]
    return rd, cutoff


def compute_baseline_historical_weekday(df, rd):
    """Baseline: 使用预测日期之前最近 4 个相同星期几的成熟 CohortActual_30d 中位数。"""
    rd = rd.copy()
    rd["_weekday"] = rd["date"].dt.weekday
    baselines = []
    for _, r in rd.iterrows():
        d = r["date"]
        wd = d.weekday()
        available = df[df["_date"] < d]
        same_wd = available[available["_date"].dt.weekday == wd]
        mature_same_wd = same_wd[same_wd["_date"] <= d - pd.Timedelta(days=30)]
        last4 = mature_same_wd.tail(4)
        if len(last4) >= 2:
            bl = float(last4["_lock30"].median())
        elif len(mature_same_wd) > 0:
            bl = float(mature_same_wd["_lock30"].mean())
        else:
            bl = float(available["_lock30"].mean()) if not available.empty else float(r["cohort_actual_30_lock"])
        baselines.append(bl)
    rd["baseline_weekday"] = baselines
    return rd


def compute_baseline_rolling_rate(df, rd):
    """Baseline: 当日下发线索数 × 预测日期之前可获得的滚动 30 日成熟转化率。"""
    baselines = []
    for _, r in rd.iterrows():
        d = r["date"]
        available = df[df["_date"] < d]
        mature = available[available["_date"] <= d - pd.Timedelta(days=30)]
        if mature.empty or mature["_leads"].sum() <= 0:
            bl = float(r["cohort_actual_30_lock"])
        else:
            rate = float(mature["_lock30"].sum()) / float(mature["_leads"].sum())
            bl = float(r["cohort_assign_count"]) * rate
        baselines.append(round(bl, 1))
    rd["baseline_rolling_rate"] = baselines
    return rd


def compute_official_metrics(df):
    """计算正式的 cohort 模型精度指标（仅 evaluation_eligible）。"""
    el = df[df["evaluation_eligible"]].copy()
    n = len(el)
    if n == 0:
        return {"n": 0}
    actual = el["cohort_actual_30_lock"].values.astype(float)
    forecast = el["cohort_pred_30_lock"].values.astype(float)
    error = actual - forecast
    abs_error = np.abs(error)
    sq_error = error ** 2
    sum_actual = actual.sum()
    sum_forecast = forecast.sum()

    mae = float(abs_error.mean())
    rmse = float(np.sqrt(sq_error.mean()))
    wape = float(abs_error.sum() / sum_actual) if sum_actual > 0 else np.nan

    non_zero_actual = actual[actual > 0]
    non_zero_forecast = forecast[actual > 0]
    ape = np.abs(non_zero_actual - non_zero_forecast) / non_zero_actual
    mape = float(ape.mean()) if len(ape) > 0 else np.nan
    mape_excluded = n - len(ape)

    mean_error = float(error.mean())
    median_error = float(np.median(error))
    # bias_pct uses same sign as error: positive = underestimation (actual > forecast)
    bias_pct = (sum_actual - sum_forecast) / sum_actual if sum_actual > 0 else np.nan
    median_ratio = float(np.median(actual / forecast)) if np.all(forecast > 0) else np.nan

    over_count = int((error < 0).sum())
    under_count = int((error > 0).sum())

    median_ae = float(np.median(abs_error))
    p80_ae = float(np.percentile(abs_error, 80))
    p90_ae = float(np.percentile(abs_error, 90))
    p95_ae = float(np.percentile(abs_error, 95))
    max_ae = float(abs_error.max())

    within_10 = float((abs_error / actual <= 0.1).mean()) if np.all(actual > 0) else np.nan
    within_20 = float((abs_error / actual <= 0.2).mean()) if np.all(actual > 0) else np.nan
    within_30 = float((abs_error / actual <= 0.3).mean()) if np.all(actual > 0) else np.nan

    if np.std(actual) > 0 and np.std(forecast) > 0:
        corr = float(np.corrcoef(actual, forecast)[0, 1])
    else:
        corr = np.nan

    ss_res = (sq_error).sum()
    ss_tot = ((actual - actual.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

    top10_idx = np.argsort(abs_error)[-10:][::-1]
    top10_contribution_ae = abs_error[top10_idx].sum() / abs_error.sum() if abs_error.sum() > 0 else np.nan
    top5_contribution_ae = abs_error[top10_idx[:5]].sum() / abs_error.sum() if abs_error.sum() > 0 else np.nan
    top2_contribution_ae = abs_error[top10_idx[:2]].sum() / abs_error.sum() if abs_error.sum() > 0 else np.nan

    top10_contribution_se = sq_error[top10_idx].sum() / sq_error.sum() if sq_error.sum() > 0 else np.nan
    top5_contribution_se = sq_error[top10_idx[:5]].sum() / sq_error.sum() if sq_error.sum() > 0 else np.nan
    top2_contribution_se = sq_error[top10_idx[:2]].sum() / sq_error.sum() if sq_error.sum() > 0 else np.nan

    top10_df = el.iloc[top10_idx][["date", "cohort_pred_30_lock", "cohort_actual_30_lock",
                                    "cohort_assign_count", "prediction_method"]].copy()
    top10_df["error"] = error[top10_idx]
    top10_df["abs_error"] = abs_error[top10_idx]
    top10_df["relative_error"] = np.where(actual[top10_idx] > 0, abs_error[top10_idx] / actual[top10_idx], np.nan)
    top10_df = top10_df.sort_values("date")

    return {
        "n": n,
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "mape_excluded": mape_excluded,
        "wape": wape,
        "r2": r2,
        "correlation": corr,
        "mean_error": mean_error,
        "median_error": median_error,
        "bias_pct": bias_pct,
        "median_ratio": median_ratio,
        "over_count": over_count,
        "under_count": under_count,
        "median_ae": median_ae,
        "p80_ae": p80_ae,
        "p90_ae": p90_ae,
        "p95_ae": p95_ae,
        "max_ae": max_ae,
        "within_10pct": within_10,
        "within_20pct": within_20,
        "within_30pct": within_30,
        "top10_ae_contribution_pct": top10_contribution_ae,
        "top5_ae_contribution_pct": top5_contribution_ae,
        "top2_ae_contribution_pct": top2_contribution_ae,
        "top10_se_contribution_pct": top10_contribution_se,
        "top5_se_contribution_pct": top5_contribution_se,
        "top2_se_contribution_pct": top2_contribution_se,
        "top10_exceptions": top10_df.to_dict("records"),
        "sum_actual": int(sum_actual),
        "sum_forecast": round(sum_forecast, 1),
    }


def compute_baseline_metrics(el, metric_name):
    """Compute metrics for a baseline column that uses same naming convention."""
    col = metric_name
    if col not in el.columns:
        return None
    forecast = el[col].values.astype(float)
    actual = el["cohort_actual_30_lock"].values.astype(float)
    error = actual - forecast
    abs_error = np.abs(error)
    sq_error = error ** 2
    sum_actual = actual.sum()
    mae = float(abs_error.mean())
    rmse = float(np.sqrt(sq_error.mean()))
    wape = float(abs_error.sum() / sum_actual) if sum_actual > 0 else np.nan
    non_zero = actual > 0
    ape = abs_error[non_zero] / actual[non_zero]
    mape = float(ape.mean()) if len(ape) > 0 else np.nan
    bias = float((sum_actual - forecast.sum()) / sum_actual) if sum_actual > 0 else np.nan
    return {"mae": mae, "rmse": rmse, "mape": mape, "wape": wape, "bias_pct": bias}


def compute_stratified_metrics(el):
    results = {}

    # Monthly
    el_m = el.copy()
    el_m["month"] = el_m["date"].dt.to_period("M").astype(str)
    monthly = []
    for m, grp in sorted(el_m.groupby("month")):
        m_actual = grp["cohort_actual_30_lock"].values.astype(float)
        m_forecast = grp["cohort_pred_30_lock"].values.astype(float)
        m_ae = np.abs(m_actual - m_forecast)
        m_sum_actual = m_actual.sum()
        monthly.append({
            "month": m, "n": len(grp),
            "sum_actual": int(m_sum_actual),
            "sum_forecast": round(m_forecast.sum(), 1),
            "mae": round(float(m_ae.mean()), 1),
            "mape": round(float((m_ae[m_actual > 0] / m_actual[m_actual > 0]).mean()), 4) if (m_actual > 0).sum() > 0 else np.nan,
            "wape": round(float(m_ae.sum() / m_sum_actual), 4) if m_sum_actual > 0 else np.nan,
            "bias_pct": round(float((m_sum_actual - m_forecast.sum()) / m_sum_actual), 4) if m_sum_actual > 0 else np.nan,
        })
    results["monthly"] = monthly

    # Weekday vs Weekend
    el_w = el.copy()
    el_w["is_weekend"] = el_w["date"].dt.weekday.isin([5, 6])
    for label, grp in [("工作日", el_w[~el_w["is_weekend"]]), ("周末", el_w[el_w["is_weekend"]])]:
        if grp.empty:
            continue
        w_actual = grp["cohort_actual_30_lock"].values.astype(float)
        w_forecast = grp["cohort_pred_30_lock"].values.astype(float)
        w_ae = np.abs(w_actual - w_forecast)
        w_sum_actual = w_actual.sum()
        results[f"cal_{label}"] = {
            "n": len(grp),
            "mae": round(float(w_ae.mean()), 1),
            "wape": round(float(w_ae.sum() / w_sum_actual), 4) if w_sum_actual > 0 else np.nan,
            "bias_pct": round(float((w_sum_actual - w_forecast.sum()) / w_sum_actual), 4) if w_sum_actual > 0 else np.nan,
        }

    # Lead volume terciles
    qs = el["cohort_assign_count"].quantile([1 / 3, 2 / 3]).tolist()
    results["assign_tercile_thresholds"] = [round(q, 0) for q in qs]
    for label, lo, hi in [("低线索量", 0, qs[0]), ("中线索量", qs[0], qs[1]), ("高线索量", qs[1], el["cohort_assign_count"].max() + 1)]:
        grp = el[(el["cohort_assign_count"] >= lo) & (el["cohort_assign_count"] < hi)]
        if grp.empty:
            continue
        g_actual = grp["cohort_actual_30_lock"].values.astype(float)
        g_forecast = grp["cohort_pred_30_lock"].values.astype(float)
        g_ae = np.abs(g_actual - g_forecast)
        g_sum_actual = g_actual.sum()
        results[f"assign_{label}"] = {
            "n": len(grp),
            "range": f"{int(lo):,}~{int(hi):,}",
            "mae": round(float(g_ae.mean()), 1),
            "wape": round(float(g_ae.sum() / g_sum_actual), 4) if g_sum_actual > 0 else np.nan,
            "bias_pct": round(float((g_sum_actual - g_forecast.sum()) / g_sum_actual), 4) if g_sum_actual > 0 else np.nan,
        }

    results["event_note"] = "事件标签数据暂缺，尚未完成事件期精度评估。"
    return results


def check_thresholds(metrics):
    status = {}
    if metrics["n"] == 0:
        return {k: "无法评价" for k in THRESHOLDS}
    status["mape_max"] = "达标" if (not np.isnan(metrics["mape"]) and metrics["mape"] <= THRESHOLDS["mape_max"]) else ("接近阈值" if (not np.isnan(metrics["mape"]) and metrics["mape"] <= THRESHOLDS["mape_max"] * 1.25) else "未满足")
    status["wape_max"] = "达标" if (not np.isnan(metrics["wape"]) and metrics["wape"] <= THRESHOLDS["wape_max"]) else ("接近阈值" if (not np.isnan(metrics["wape"]) and metrics["wape"] <= THRESHOLDS["wape_max"] * 1.25) else "未满足")
    rmse_mae = metrics["rmse"] / metrics["mae"] if metrics["mae"] > 0 else np.nan
    status["rmse_mae_ratio_max"] = "达标" if (not np.isnan(rmse_mae) and rmse_mae <= THRESHOLDS["rmse_mae_ratio_max"]) else ("接近阈值" if (not np.isnan(rmse_mae) and rmse_mae <= THRESHOLDS["rmse_mae_ratio_max"] * 1.15) else "未满足")
    status["within_20pct_min"] = "达标" if (not np.isnan(metrics["within_20pct"]) and metrics["within_20pct"] >= THRESHOLDS["within_20pct_min"]) else ("接近阈值" if (not np.isnan(metrics["within_20pct"]) and metrics["within_20pct"] >= THRESHOLDS["within_20pct_min"] * 0.85) else "未满足")
    status["within_30pct_min"] = "达标" if (not np.isnan(metrics["within_30pct"]) and metrics["within_30pct"] >= THRESHOLDS["within_30pct_min"]) else ("接近阈值" if (not np.isnan(metrics["within_30pct"]) and metrics["within_30pct"] >= THRESHOLDS["within_30pct_min"] * 0.85) else "未满足")
    status["r2_min"] = "达标" if (not np.isnan(metrics["r2"]) and metrics["r2"] >= THRESHOLDS["r2_min"]) else ("接近阈值" if (not np.isnan(metrics["r2"]) and metrics["r2"] >= THRESHOLDS["r2_min"] * 0.85) else "未满足")
    status["abs_bias_pct_max"] = "达标" if (not np.isnan(metrics["bias_pct"]) and abs(metrics["bias_pct"]) <= THRESHOLDS["abs_bias_pct_max"]) else ("接近阈值" if (not np.isnan(metrics["bias_pct"]) and abs(metrics["bias_pct"]) <= THRESHOLDS["abs_bias_pct_max"] * 1.5) else "未满足")
    mr = metrics.get("median_ratio", np.nan)
    st = THRESHOLDS
    status["median_actual_forecast_ratio"] = "达标" if (not np.isnan(mr) and st["median_actual_forecast_ratio_min"] <= mr <= st["median_actual_forecast_ratio_max"]) else ("接近阈值" if (not np.isnan(mr) and st["median_actual_forecast_ratio_min"] * 0.95 <= mr <= st["median_actual_forecast_ratio_max"] * 1.05) else "未满足")
    return status


def build_executive_summary(metrics, bl_metrics, thresholds_status):
    n = metrics["n"]
    if n == 0:
        return "回测样本不足，无法生成执行摘要。"
    lines = []
    if not np.isnan(metrics["wape"]):
        lines.append(f"模型在完整成熟样本 (N={n}) 上的 WAPE 为 {metrics['wape']:.1%}")

    # Bias interpretation (bias_pct: positive = underestimation, same sign as error)
    if not np.isnan(metrics["bias_pct"]):
        if metrics["bias_pct"] > 0.02:
            lines.append(f"整体系统性低估 (bias_pct={metrics['bias_pct']:.1%})，需结合中位误差 ({metrics['median_error']:.1f}) 判断")
        elif metrics["bias_pct"] < -0.02:
            lines.append(f"整体系统性高估 (bias_pct={metrics['bias_pct']:.1%})")
        else:
            if metrics["over_count"] > 0 and metrics["under_count"] > 0 and abs(metrics["over_count"] - metrics["under_count"]) / n > 0.15:
                lines.append(f"总体 Bias 接近零，但高估天数 ({metrics['over_count']}) 与低估天数 ({metrics['under_count']}) 差异显著，存在方向性偏差抵消")
            else:
                lines.append(f"总体 Bias 接近零，高低估天数基本平衡")

    # Exception concentration
    if not np.isnan(metrics.get("top2_ae_contribution_pct", np.nan)) and metrics["top2_ae_contribution_pct"] > 0.15:
        lines.append(f"误差高度集中于少量异常日期 (Top 2 贡献 {metrics['top2_ae_contribution_pct']:.0%} 绝对误差)")

    # Baseline comparison — pick the BEST baseline (lowest WAPE), not the biggest improvement
    if bl_metrics:
        best_bl = None
        best_wape = np.inf
        for bl_name, bl_m in bl_metrics.items():
            if bl_m and not np.isnan(bl_m.get("wape", np.nan)):
                if bl_m["wape"] < best_wape:
                    best_wape = bl_m["wape"]
                    best_bl = bl_name
        if best_bl and not np.isnan(metrics["wape"]) and best_wape > 0:
            imp = (best_wape - metrics["wape"]) / best_wape
            if imp > 0:
                lines.append(f"当前模型相对最佳简单基线 ({best_bl}, WAPE={best_wape:.1%}) 的 WAPE 改善 {imp:.1%}")
            else:
                lines.append(f"模型未显著优于最佳基线 ({best_bl})")
        elif best_bl:
            lines.append(f"模型在部分场景下未显著优于基线")

    # Thresholds summary
    passed = sum(1 for v in thresholds_status.values() if v == "达标")
    total = len(thresholds_status)
    lines.append(f"验收阈值: {passed}/{total} 项达标")

    return "；".join(lines) if lines else "模型评估完成。"


def generate_html(rd, cutoff, metrics, bl_metrics, stratified, thresholds_status, summary,
                   events=None, metrics_tc1=None, metrics_tc2=None, metrics_tc3=None,
                   ev_metrics=None, nw_metrics=None, phase_metrics=None):
    if events is None or (isinstance(events, pd.DataFrame) and events.empty):
        events = pd.DataFrame()
    ev_metrics = ev_metrics or {}
    nw_metrics = nw_metrics or {}
    from plotly import graph_objects as go
    from plotly.subplots import make_subplots

    el = rd[rd["evaluation_eligible"]].copy()
    n_immature = len(rd[~rd["evaluation_eligible"]])

    # ── 1. Cohort Forecast vs Actual ──
    dates = el["date"].tolist()
    actual = el["cohort_actual_30_lock"].tolist()
    forecast = el["cohort_pred_30_lock"].tolist()
    error = [a - f for a, f in zip(actual, forecast)]
    ratio_af = [a / f if f > 0 else None for a, f in zip(actual, forecast)]

    fig1 = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                          subplot_titles=("CohortForecast vs CohortActual_30d",
                                          "Cohort 预测误差 (Actual - Forecast)",
                                          "CohortActual_30d / CohortForecast 比值",
                                          "实际值 vs 预测值散点图"))
    fig1.add_trace(go.Scatter(x=dates, y=forecast, mode="lines", name="CohortForecast",
                               line=dict(color=OWN, width=1.5)), row=1, col=1)
    fig1.add_trace(go.Scatter(x=dates, y=actual, mode="lines", name="CohortActual_30d",
                               line=dict(color=EVENT, width=1.2, dash="dot")), row=1, col=1)
    colors_err = [POSITIVE if v >= 0 else NEGATIVE for v in error]
    fig1.add_trace(go.Bar(x=dates, y=error, name="error", marker=dict(color=colors_err, opacity=0.6)), row=2, col=1)
    fig1.add_trace(go.Scatter(x=dates, y=ratio_af, mode="markers", name="Actual/Forecast",
                               marker=dict(color=ASH, size=3, opacity=0.4)), row=3, col=1)
    fig1.add_hline(y=1, line=dict(color=MUTED_COLOR, width=1, dash="dash"), row=3, col=1)
    fig1.add_hline(y=0.8, line=dict(color="#D8DEE6", width=1, dash="dot"), row=3, col=1)
    fig1.add_hline(y=1.2, line=dict(color="#D8DEE6", width=1, dash="dot"), row=3, col=1)
    fig1.add_trace(go.Scatter(x=actual, y=forecast, mode="markers", name="scatter",
                               marker=dict(color=OWN, size=4, opacity=0.5)), row=4, col=1)
    max_v = max(max(actual), max(forecast))
    fig1.add_trace(go.Scatter(x=[0, max_v], y=[0, max_v], mode="lines", name="y=x",
                               line=dict(color=NEGATIVE, width=1, dash="dash")), row=4, col=1)
    apply_zh_theme(fig1)
    fig1.update_layout(height=820, margin=dict(l=60, r=30, t=30, b=30),
                       hovermode="x unified", showlegend=True,
                       legend=dict(orientation="h", y=1.02, x=0))

    # ── 2. Error Distribution ──
    abs_err = [abs(v) for v in error]
    fig2 = make_subplots(rows=1, cols=2, subplot_titles=("绝对误差分布", "相对误差分布"))
    fig2.add_trace(go.Histogram(x=abs_err, nbinsx=40, marker=dict(color=OWN, opacity=0.7),
                                 name="abs_error"), row=1, col=1)
    rel_err = [abs(a - f) / a if a > 0 else None for a, f in zip(actual, forecast)]
    rel_err_clean = [v for v in rel_err if v is not None]
    fig2.add_trace(go.Histogram(x=rel_err_clean, nbinsx=40, marker=dict(color=EVENT, opacity=0.7),
                                 name="relative_error"), row=1, col=2)
    apply_zh_theme(fig2)
    fig2.update_layout(height=350, margin=dict(l=60, r=30, t=30, b=30), showlegend=False)

    # ── 3. Monthly Trend ──
    monthly = stratified.get("monthly", [])
    if monthly:
        m_dates = [m["month"] for m in monthly]
        m_wape = [m["wape"] for m in monthly]
        m_bias = [m["bias_pct"] for m in monthly]
        fig3 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                              subplot_titles=("月度 WAPE", "月度 Bias %"))
        fig3.add_trace(go.Bar(x=m_dates, y=m_wape, marker=dict(color=OWN, opacity=0.7), name="WAPE"),
                       row=1, col=1)
        fig3.add_hline(y=THRESHOLDS["wape_max"], line=dict(color=NEGATIVE, width=1, dash="dash"), row=1, col=1)
        colors_bias = [POSITIVE if v >= 0 else NEGATIVE for v in m_bias]
        fig3.add_trace(go.Bar(x=m_dates, y=m_bias, marker=dict(color=colors_bias, opacity=0.6), name="Bias"),
                       row=2, col=1)
        fig3.add_hline(y=0, line=dict(color=MUTED_COLOR, width=1), row=2, col=1)
        apply_zh_theme(fig3)
        fig3.update_layout(height=500, margin=dict(l=60, r=30, t=30, b=30), showlegend=False)
    else:
        fig3 = None

    # ── 4. Baseline Comparison Chart ──
    if bl_metrics:
        bl_names = []
        bl_mae = []
        bl_wape = []
        for name, bl_m in bl_metrics.items():
            if bl_m:
                bl_names.append(name)
                bl_mae.append(bl_m["mae"])
                bl_wape.append(bl_m["wape"])
        if bl_names:
            fig4 = make_subplots(rows=1, cols=2, subplot_titles=("MAE 对比", "WAPE 对比"))
            all_names = ["Current Model"] + bl_names
            all_mae = [metrics["mae"]] + bl_mae
            all_wape = [metrics["wape"]] + bl_wape
            colors_bar = [OWN] + [ASH] * len(bl_names)
            fig4.add_trace(go.Bar(x=all_names, y=all_mae, marker=dict(color=colors_bar, opacity=0.7)), row=1, col=1)
            fig4.add_trace(go.Bar(x=all_names, y=all_wape, marker=dict(color=colors_bar, opacity=0.7)), row=1, col=2)
            apply_zh_theme(fig4)
            fig4.update_layout(height=350, margin=dict(l=60, r=30, t=30, b=30), showlegend=False)
        else:
            fig4 = None
    else:
        fig4 = None

    # ── 5. Business Observation (Daily Lock Count) ──
    daily = load_daily_lock_count()
    rd_obs = rd.copy()
    if daily is not None:
        rd_obs = rd_obs.merge(daily, on="date", how="left")
        rd_obs["daily_lock_count"] = rd_obs["daily_lock_count"].fillna(0).astype(int)
    else:
        rd_obs["daily_lock_count"] = 0

    obs_dates = rd_obs["date"].tolist()
    obs_forecast = rd_obs["cohort_pred_30_lock"].tolist()
    obs_daily = rd_obs["daily_lock_count"].tolist()
    obs_ratio_daily = [d / f if f > 0 else None for d, f in zip(obs_daily, obs_forecast)]

    fig5 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                          subplot_titles=("自然日经营观察: DailyLockCount vs Cohort预测参考值",
                                          "自然日锁单 / Cohort预测参考值"))
    fig5.add_trace(go.Scatter(x=obs_dates, y=obs_forecast, mode="lines", name="Cohort预测参考值",
                               line=dict(color=OWN, width=1.2, dash="dot")), row=1, col=1)
    fig5.add_trace(go.Scatter(x=obs_dates, y=obs_daily, mode="lines", name="DailyLockCount",
                               line=dict(color=EVENT, width=1.5)), row=1, col=1)
    fig5.add_trace(go.Scatter(x=obs_dates, y=obs_ratio_daily, mode="markers", name="观察比值",
                               marker=dict(color=ASH, size=3, opacity=0.4)), row=2, col=1)
    fig5.add_hline(y=1, line=dict(color=MUTED_COLOR, width=1, dash="dash"), row=2, col=1)
    fig5.add_annotation(text="该比值的时间归属口径不同，仅作为经营节奏观察，不参与模型精度评价",
                        xref="paper", yref="paper", x=0.5, y=-0.25, showarrow=False,
                        font=dict(size=10, color=MUTED_COLOR))
    apply_zh_theme(fig5)
    fig5.update_layout(height=500, margin=dict(l=60, r=30, t=30, b=60),
                       hovermode="x unified", showlegend=True,
                       legend=dict(orientation="h", y=1.02, x=0))

        # ── Launch Event Experiment Section ──
    event_html = ""
    if HAS_EVENTS and metrics_tc1 is not None:
        models_def = [
            ("Control", "cohort_pred_30_lock", metrics),
            ("Treatment C1", "cohort_pred_treatment_c1", metrics_tc1),
            ("Treatment C2", "cohort_pred_treatment_c2", metrics_tc2) if metrics_tc2 else None,
            ("Treatment C3", "cohort_pred_treatment_c3", metrics_tc3) if metrics_tc3 else None,
        ]
        models_def = [m for m in models_def if m is not None]
        comp_rows = ""
        ev_key_map = {"Control": "control", "Treatment C1": "treatment_c1",
                       "Treatment C2": "treatment_c2", "Treatment C3": "treatment_c3"}
        for mname, _, mm in models_def:
            ev_key = ev_key_map.get(mname, "control")
            ew_val = (ev_metrics.get(ev_key) or {}).get("wape", np.nan)
            nw_val = (nw_metrics.get(ev_key) or {}).get("wape", np.nan)
            ew_s = f"{ew_val:.1%}" if not np.isnan(ew_val) else "N/A"
            nw_s = f"{nw_val:.1%}" if not np.isnan(nw_val) else "N/A"
            w20 = f"{mm.get('within_20pct', np.nan):.1%}" if not np.isnan(mm.get('within_20pct', np.nan)) else "N/A"
            comp_rows += f"""<tr>
<td>{mname}</td>
<td>{mm['mae']:.1f}</td>
<td>{mm['rmse']:.1f}</td>
<td>{mm['wape']:.1%}</td>
<td>{mm.get('mape', np.nan):.1%}</td>
<td>{mm.get('r2', np.nan):.3f}</td>
<td>{mm.get('bias_pct', np.nan):+.1%}</td>
<td>{w20}</td>
<td>{ew_s}</td>
<td>{nw_s}</td>
</tr>"""

        phase_rows = ""
        for pk in LIFECYCLE_PHASES:
            pm = phase_metrics.get(pk, {})
            if not pm:
                continue
            cw = f"{pm['control_wape']:.1%}"
            if "treatment_c1_wape" in pm:
                tw = f"{pm['treatment_c1_wape']:.1%}"
                imp = f"{pm['wape_improvement']:.1%}" if not np.isnan(pm.get('wape_improvement', np.nan)) else "N/A"
            else:
                tw = cw
                imp = "—"
            phase_rows += f"""<tr>
<td>{pk}</td>
<td>{pm['n']}</td>
<td>{pm['sum_actual']:,}</td>
<td>{pm.get('control_sum', 0):,.1f}</td>
<td>{pm.get('treatment_c1_sum', 0):,.1f}</td>
<td>{cw}</td>
<td>{tw}</td>
<td>{imp}</td>
</tr>"""

        event_plot_html = ""
        if not events.empty:
            from plotly import graph_objects as go
            el = rd[rd["evaluation_eligible"]].copy()
            aligned = []
            for _, ev in events.iterrows():
                ed = ev["event_date"]
                for _, r in el.iterrows():
                    e_day = (r["date"] - ed).days
                    if -7 <= e_day <= 30:
                        aligned.append({
                            "event_id": ev["event_id"],
                            "event_day": e_day,
                            "actual": r["cohort_actual_30_lock"],
                            "control_fc": r["cohort_pred_30_lock"],
                            "treatment_c1_fc": r.get("cohort_pred_treatment_c1", r["cohort_pred_30_lock"]),
                        })
            if aligned:
                adf = pd.DataFrame(aligned)
                by_day = adf.groupby("event_day").agg(
                    n=("actual", "count"),
                    avg_actual=("actual", "mean"),
                    avg_control=("control_fc", "mean"),
                    avg_treatment_c1=("treatment_c1_fc", "mean"),
                ).reset_index()
                by_day["ratio_control"] = by_day["avg_actual"] / by_day["avg_control"]
                by_day["ratio_treatment"] = by_day["avg_actual"] / by_day["avg_treatment_c1"]
                edates = by_day["event_day"].tolist()
                n_counts = by_day["n"].tolist()
                r_c = by_day["ratio_control"].tolist()
                r_t = by_day["ratio_treatment"].tolist()

                fig_ev = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                                        subplot_titles=("Actual / Control 比值 (对齐Day 0)", "Actual / Treatment C1 比值 (对齐Day 0)"))
                fig_ev.add_trace(go.Scatter(x=edates, y=r_c, mode="lines+markers",
                                             name="Actual/Control", line=dict(color=OWN, width=1.5),
                                             marker=dict(size=5)), row=1, col=1)
                fig_ev.add_trace(go.Bar(x=edates, y=n_counts, name="样本数",
                                        marker=dict(color=ASH, opacity=0.4), yaxis="y2"), row=1, col=1)
                fig_ev.add_trace(go.Scatter(x=edates, y=r_t, mode="lines+markers",
                                             name="Actual/Treatment", line=dict(color=EVENT, width=1.5),
                                             marker=dict(size=5)), row=2, col=1)
                fig_ev.add_hline(y=1, line=dict(color=MUTED_COLOR, width=1, dash="dash"), row=1, col=1)
                fig_ev.add_hline(y=1, line=dict(color=MUTED_COLOR, width=1, dash="dash"), row=2, col=1)
                apply_zh_theme(fig_ev)
                fig_ev.update_layout(
                    height=500, margin=dict(l=60, r=30, t=30, b=30),
                    hovermode="x unified", showlegend=True,
                    legend=dict(orientation="h", y=1.02, x=0),
                )
                fig_ev.update_yaxes(title_text="比值", row=1, col=1)
                fig_ev.update_yaxes(title_text="样本数", secondary_y=True, row=1, col=1)
                fig_ev.update_xaxes(title_text="Event Day", row=2, col=1)
                event_plot_html = f'<div class="chart-box"><h2>上市事件对齐时间图</h2><div id="chart-event-aligned"></div></div>'
                event_plot_script = f'var fig_ev = {fig_ev.to_json()};\nPlotly.newPlot("chart-event-aligned", fig_ev.data, fig_ev.layout, {{displayModeBar: false}});'
            else:
                event_plot_script = ""
        else:
            event_plot_script = ""

        imp_overall = (metrics["wape"] - metrics_tc1["wape"]) / metrics["wape"] if metrics["wape"] > 0 else 0
        ew_ctrl = (ev_metrics.get("control") or {}).get("wape", np.nan)
        ew_tc1 = (ev_metrics.get("treatment_c1") or {}).get("wape", np.nan)
        imp_ew = (ew_ctrl - ew_tc1) / ew_ctrl if (not np.isnan(ew_ctrl) and ew_ctrl > 0) else 0
        nw_ctrl = (nw_metrics.get("control") or {}).get("wape", np.nan)
        nw_tc1 = (nw_metrics.get("treatment_c1") or {}).get("wape", np.nan)
        nw_degrad = (nw_tc1 - nw_ctrl) if (not np.isnan(nw_ctrl) and not np.isnan(nw_tc1)) else 0
        acc = EVENT_CONFIG["acceptance"]
        checks = {
            "全样本WAPE改善 ≥ 3%": imp_overall >= acc["overall_wape_relative_improvement_min"],
            "生命周期窗口WAPE改善 ≥ 10%": imp_ew >= acc["event_window_wape_relative_improvement_min"],
            "常规期WAPE恶化 ≤ 1pp": nw_degrad <= acc["normal_window_wape_degradation_max_pp"],
        }
        check_rows = ""
        for label, passed in checks.items():
            icon = "✅" if passed else "❌"
            check_rows += f"<tr><td>{label}</td><td>{icon}</td></tr>"

        event_html = f"""
<div class="section-title">上市事件生命周期实验</div>
<div class="panel">
  <p style="font-size:13px;color:var(--muted);padding:4px 0">
    事件来源: {EVENT_SOURCE} | 事件数量: {len(events)} | 
    最早上市: {events['event_date'].min().date() if not events.empty else 'N/A'} | 
    最晚上市: {events['event_date'].max().date() if not events.empty else 'N/A'}
  </p>
  <p style="font-size:13px;color:var(--muted);padding:4px 0">
    生命周期: presale_day/presale_active/launch_day/launch_post_d1_d3/launch_post_d4_d7/benefit_active/benefit_countdown/benefit_end_day/post_benefit |
    先验强度: {EVENT_CONFIG["prior_strength"]}
  </p>
  <p style="font-size:13px;color:var(--text);padding:4px 0">
    正式回测可用: {len(el[el['in_lifecycle_window']])} 个Cohort | 
    当前未成熟: {int(rd.loc[~rd['evaluation_eligible'], 'in_lifecycle_window'].sum())} 个Cohort
  </p>
</div>
<div class="chart-box">
  <h2>Control / Treatment C 系列对比</h2>
  <div style="overflow-x:auto;">
  <table><thead><tr><th>模型</th><th>MAE</th><th>RMSE</th><th>WAPE</th><th>MAPE</th><th>R²</th><th>Bias%</th><th>±20%命中率</th><th>生命周期WAPE</th><th>常规期WAPE</th></tr></thead>
  <tbody>{comp_rows}</tbody></table>
  </div>
</div>
<div class="chart-box">
  <h2>生命周期阶段表现 (Control vs Treatment C1)</h2>
  <div style="overflow-x:auto;">
  <table><thead><tr><th>阶段</th><th>样本</th><th>实际总量</th><th>Control预测</th><th>Treatment预测</th><th>Control WAPE</th><th>Treatment WAPE</th><th>WAPE改善</th></tr></thead>
  <tbody>{phase_rows}</tbody></table>
  </div>
</div>
{event_plot_html}
<div class="chart-box">
  <h2>模型升级验收检查</h2>
  <div style="overflow-x:auto;">
  <table><thead><tr><th>条件</th><th>结果</th></tr></thead>
  <tbody>{check_rows}</tbody></table>
  </div>
</div>
<script>
{event_plot_script}
</script>
"""
    top10 = metrics.get("top10_exceptions", [])
    top10_rows = ""
    for r10 in top10:
        sign = "+" if r10["error"] >= 0 else ""
        top10_rows += f"""<tr>
<td>{r10['date'].strftime('%Y-%m-%d') if hasattr(r10['date'], 'strftime') else r10['date']}</td>
<td>{r10['cohort_pred_30_lock']:.1f}</td>
<td>{r10['cohort_actual_30_lock']:,}</td>
<td>{sign}{r10['error']:.1f}</td>
<td>{r10['abs_error']:.1f}</td>
<td>{r10['relative_error']:.1%}</td>
<td>{r10['cohort_assign_count']:,}</td>
<td>{r10['prediction_method']}</td>
</tr>"""

    # ── Stratification tables ──
    strat_rows_monthly = ""
    for m in monthly:
        wape_s = f"{m['wape']:.1%}" if not np.isnan(m['wape']) else "N/A"
        bias_s = f"{m['bias_pct']:+.1%}" if not np.isnan(m['bias_pct']) else "N/A"
        strat_rows_monthly += f"""<tr>
<td>{m['month']}</td>
<td>{m['n']}</td>
<td>{m['sum_actual']:,}</td>
<td>{m['sum_forecast']:,.1f}</td>
<td>{m['mae']:.1f}</td>
<td>{wape_s}</td>
<td>{bias_s}</td>
</tr>"""

    # ── Immature observation table ──
    immature = rd[~rd["evaluation_eligible"]].copy()
    imm_rows = ""
    for _, r in immature.tail(30).iterrows():
        final_30d = f"{r['cohort_actual_30_lock']:,}" if r["evaluation_eligible"] else "—"
        # For immature cohorts, the observed actual = lock0 (same-day lock)
        observed = r.get("cohort_actual_observed", r["cohort_actual_30_lock"])
        imm_rows += f"""<tr>
<td>{r['date'].strftime('%Y-%m-%d')}</td>
<td>{r['cohort_assign_count']:,}</td>
<td>{r['cohort_pred_30_lock']:.1f}</td>
<td>{observed:,}</td>
<td>{final_30d}</td>
<td>{r['maturity_days']}</td>
<td>{"是" if r['evaluation_eligible'] else "否"}</td>
</tr>"""

    # ── Status cards ──
    def mk_stat(num, label, color=OWN):
        return f"""<div class="stat-card"><div class="num" style="color:{color}">{num}</div><div class="label">{label}</div></div>"""

    stat_cards = ""
    if metrics["n"] > 0:
        stat_cards += mk_stat(f"{metrics['mae']:.1f}", "MAE", OWN)
        stat_cards += mk_stat(f"{metrics['wape']:.1%}", "WAPE", OWN)
        stat_cards += mk_stat(f"{metrics['mape']:.1%}" if not np.isnan(metrics['mape']) else "N/A", "MAPE", OWN)
        stat_cards += mk_stat(f"{metrics['rmse']:.1f}", "RMSE", OWN)
        stat_cards += mk_stat(f"{metrics['r2']:.3f}" if not np.isnan(metrics['r2']) else "N/A", "R²", OWN)
        stat_cards += mk_stat(f"{metrics['correlation']:.3f}" if not np.isnan(metrics['correlation']) else "N/A", "Correlation", OWN)
        stat_cards += mk_stat(f"{metrics['bias_pct']:+.1%}" if not np.isnan(metrics['bias_pct']) else "N/A", "Bias %", OWN)
        stat_cards += mk_stat(f"{metrics['n']}", "正式样本数", OWN)
        stat_cards += mk_stat(f"{n_immature}", "未成熟观察数", ASH)

    # Threshold status table
    thr_rows = ""
    label_map = {
        "mape_max": "MAPE ≤ 20%",
        "wape_max": "WAPE ≤ 22%",
        "rmse_mae_ratio_max": "RMSE/MAE ≤ 1.6",
        "within_20pct_min": "±20% 命中率 ≥ 70%",
        "within_30pct_min": "±30% 命中率 ≥ 80%",
        "r2_min": "R² ≥ 0.70",
        "abs_bias_pct_max": "|Bias%| ≤ 5%",
        "median_actual_forecast_ratio": "中位数比值 0.95~1.05",
    }
    for k, label in label_map.items():
        s = thresholds_status.get(k, "无法评价")
        icon = {"达标": "✅", "接近阈值": "⚠️", "未满足": "❌", "无法评价": "➖"}
        thr_rows += f"<tr><td>{label}</td><td>{icon.get(s, '➖')} {s}</td></tr>"

    # Executive summary
    summary_md = f"<p style='font-size:14px;line-height:1.7;color:var(--text);padding:12px 0'>{summary}</p>"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cohort 锁单预测 — 回测报告</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root {{ --blue: #174A7C; --deep: #06213D; --gold: #D79A36; --text: #1F2D3D; --muted: #6B7280; --border: #E5EAF0; --bg: #FAFBFC; --card: #FFFFFF; --panel: #F6F8FA; --row-alt: #FAFAFA; --positive: #2A9D8F; --negative: #D95F59; --light: #DDEFF8; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
.header {{ background: linear-gradient(135deg, var(--deep), var(--blue)); color: #fff; padding: 32px 24px 24px; text-align: center; }}
.header h1 {{ font-size: 24px; font-weight: 700; }}
.header p {{ font-size: 13px; opacity: .75; margin-top: 4px; }}
.header .meta {{ font-size: 12px; opacity: .6; margin-top: 2px; }}
.section-title {{ font-size: 18px; font-weight: 700; color: var(--deep); padding: 20px 24px 8px; }}
.panel {{ background: var(--card); border-radius: 12px; margin: 0 24px 20px; padding: 20px; box-shadow: 0 1px 4px rgba(6,33,61,.06); }}
.stats {{ display: flex; gap: 10px; flex-wrap: wrap; padding: 0 24px 16px; }}
.stat-card {{ flex: 1; min-width: 100px; background: var(--card); border-radius: 10px; padding: 14px 12px; box-shadow: 0 1px 4px rgba(6,33,61,.06); text-align: center; }}
.stat-card .num {{ font-size: 20px; font-weight: 700; }}
.stat-card .label {{ font-size: 11px; color: var(--muted); margin-top: 4px; font-weight: 500; }}
.chart-box {{ background: var(--card); border-radius: 12px; padding: 20px; margin: 0 24px 20px; box-shadow: 0 1px 4px rgba(6,33,61,.06); }}
.chart-box h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 14px; color: var(--deep); padding-bottom: 8px; border-bottom: 2px solid var(--light); }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: var(--deep); color: #fff; padding: 9px 10px; text-align: left; font-weight: 500; white-space: nowrap; }}
td {{ padding: 7px 10px; border-bottom: 1px solid var(--border); }}
tbody tr:nth-child(even) td {{ background: var(--row-alt); }}
tbody tr:hover td {{ background: var(--panel); }}
.note {{ font-size: 12px; color: var(--muted); padding: 4px 0; }}
.obs-note {{ display: block; font-size: 11px; color: var(--muted); text-align: center; padding: 6px 24px; }}
.footer {{ text-align: center; padding: 24px; font-size: 12px; color: var(--muted); border-top: 1px solid var(--border); margin-top: 8px; }}
</style>
</head>
<body>
<div class="header">
  <h1>Cohort 锁单预测 · 回测</h1>
  <p>数据截止 {cutoff.date()} | 模型目标: 30 日 Cohort 锁单 | 完整成熟样本截止: {(cutoff - timedelta(days=30)).date()}</p>
  <p class="meta">正式回测样本: {metrics["n"]} | 未成熟观察样本: {n_immature} | 回测方法: Rolling-Origin (无未来信息泄漏)</p>
</div>

<div class="section-title">执行摘要</div>
<div class="panel">{summary_md}
<div style="margin-top:12px"><table><thead><tr><th>验收指标</th><th>状态</th></tr></thead><tbody>{thr_rows}</tbody></table></div>
</div>

<div class="section-title">模型精度总览</div>
<div class="stats">{stat_cards}</div>
<div class="chart-box">
  <h2>Cohort 模型精度 (仅成熟样本, N={metrics["n"]})</h2>
  <div id="chart-precision"></div>
</div>

<div class="section-title">误差分布与异常日</div>
<div class="chart-box">
  <h2>误差分布</h2>
  <div id="chart-error-dist"></div>
</div>
<div class="chart-box">
  <h2>Top 10 异常日 (按绝对误差)</h2>
  <p class="note">Top 2 AE 贡献: {metrics.get('top2_ae_contribution_pct', np.nan):.1%} | Top 5: {metrics.get('top5_ae_contribution_pct', np.nan):.1%} | Top 10: {metrics.get('top10_ae_contribution_pct', np.nan):.1%}</p>
  <p class="note">Top 2 SE 贡献: {metrics.get('top2_se_contribution_pct', np.nan):.1%} | Top 5: {metrics.get('top5_se_contribution_pct', np.nan):.1%} | Top 10: {metrics.get('top10_se_contribution_pct', np.nan):.1%}</p>
  <div style="overflow-x:auto;">
  <table><thead><tr><th>日期</th><th>CohortForecast</th><th>CohortActual_30d</th><th>误差</th><th>绝对误差</th><th>相对误差</th><th>下发线索数</th><th>阶段</th></tr></thead>
  <tbody>{top10_rows}</tbody></table>
  </div>
</div>

<div class="section-title">分层稳定性评估</div>
<div class="chart-box">
  <h2>月度表现</h2>
  <div id="chart-monthly" style="height:520px"></div>
</div>
<div class="chart-box">
  <h2>分月明细</h2>
  <div style="overflow-x:auto;">
  <table><thead><tr><th>月份</th><th>样本</th><th>实际总量</th><th>预测总量</th><th>MAE</th><th>WAPE</th><th>Bias%</th></tr></thead>
  <tbody>{strat_rows_monthly}</tbody></table>
  </div>
</div>
<div class="chart-box">
  <h2>日历类型与线索规模</h2>
  <div style="overflow-x:auto;">
  <table><thead><tr><th>分组</th><th>样本</th><th>范围</th><th>MAE</th><th>WAPE</th><th>Bias%</th></tr></thead>
  <tbody>
{''.join(f"<tr><td>{k}</td><td>{v['n']}</td><td>{v.get('range', '-')}</td><td>{v['mae']}</td><td>{v['wape']:.1%}</td><td>{v['bias_pct']:+.1%}</td></tr>" for k, v in stratified.items() if k not in ('monthly', 'assign_tercile_thresholds', 'event_note'))}
  <tr><td colspan="6" style="color:var(--muted);font-size:12px">{stratified.get('event_note', '')}</td></tr>
  </tbody></table>
  </div>
</div>

<div class="section-title">基线模型对照</div>
<div class="panel">
<div style="overflow-x:auto;">
{'<table><thead><tr><th>模型</th><th>MAE</th><th>RMSE</th><th>MAPE</th><th>WAPE</th><th>Bias%</th><th>MAE提升</th><th>WAPE提升</th></tr></thead><tbody>' +
''.join(f"<tr><td>{'当前模型' if name == '三阶段成熟度模型' else name}</td><td>{m['mae']:.1f}</td><td>{m['rmse']:.1f}</td><td>{m['mape']:.1%}</td><td>{m['wape']:.1%}</td><td>{m['bias_pct']:+.1%}</td><td>—</td><td>—</td></tr>" if name == '三阶段成熟度模型'
else f"<tr><td>{name}</td><td>{m['mae']:.1f}</td><td>{m['rmse']:.1f}</td><td>{m['mape']:.1%}</td><td>{m['wape']:.1%}</td><td>{m['bias_pct']:+.1%}</td><td>{((m['mae'] - metrics['mae'])/m['mae']):+.1%}</td><td>{((m['wape'] - metrics['wape'])/m['wape']):+.1%}</td></tr>"
for name, m in bl_metrics.items()) + '</tbody></table>' if bl_metrics else '<p style="color:var(--muted)">基线模型数据暂缺。</p>'}
</div>
</div>
<div class="chart-box">{'<div id="chart-baseline"></div>' if fig4 else ''}</div>

{event_html}

<div class="section-title">经营观察: 自然日锁单节奏</div>
<div class="chart-box">
  <h2>自然日经营观察 (DailyLockCount vs Cohort预测参考值)</h2>
  <div id="chart-business"></div>
  <span class="obs-note">⚠ 该比值的时间归属口径不同 (DailyLockCount按自然日归属，CohortForecast按线索下发日归属)，仅作为经营节奏观察，不参与模型精度评价。</span>
</div>

<div class="section-title">最近 Cohort 成熟度与经营观察</div>
<div class="chart-box">
  <div style="overflow-x:auto;">
  <table><thead><tr><th>Date</th><th>AssignCount</th><th>CohortForecast</th><th>CohortActualObserved</th><th>CohortActualFinal30d</th><th>MaturityDays</th><th>IsFullyMatured</th></tr></thead>
  <tbody>{imm_rows}</tbody></table>
  </div>
  <p class="note">未成熟 Cohort 的 CohortActual_30d 可能尚未完整观察 30 日，不参与正式精度统计。</p>
</div>

<div class="footer">
  <img src="../../assets/brand/raccoon_avatar_light.png" style="height:28px;opacity:.5;margin-bottom:6px" /><br/>
  Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Raccoon Research · Rolling-Origin Backtest
</div>
<script>
var fig1 = {fig1.to_json()};
Plotly.newPlot('chart-precision', fig1.data, fig1.layout, {{displayModeBar: false}});
var fig2 = {fig2.to_json()};
Plotly.newPlot('chart-error-dist', fig2.data, fig2.layout, {{displayModeBar: false}});
{'var fig3 = ' + fig3.to_json() + ';\nPlotly.newPlot(\"chart-monthly\", fig3.data, fig3.layout, {displayModeBar: false});' if fig3 else ''}
{'var fig4 = ' + fig4.to_json() + ';\nPlotly.newPlot(\"chart-baseline\", fig4.data, fig4.layout, {displayModeBar: false});' if fig4 else ''}
var fig5 = {fig5.to_json()};
Plotly.newPlot('chart-business', fig5.data, fig5.layout, {{displayModeBar: false}});
</script>
</body>
</html>"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    return OUTPUT_HTML


def print_terminal(metrics, bl_metrics, stratified, thresholds_status, summary, bt_start, bt_end, cutoff, n_immature):
    print(f"\n  {_ruler('━', 64)}")
    print(f"  {DEEP_B}{BOLD}Cohort 锁单预测回测 · 三段式成熟度模型 (Rolling-Origin){RST:^20}")
    print(f"  {_ruler('━', 64)}")

    m = metrics
    if m["n"] == 0:
        print(f"\n  {GOLD}⚠ 正式回测样本不足{RST}")
        return

    def fmt(v, spec): return format(v, spec)
    def fmt_or_na(v, spec): return format(v, spec) if not np.isnan(v) else "N/A"

    print(f"\n  {GOLD}■{RST} {DEEP_B}{BOLD}执行摘要{RST}")
    print(f"    {summary}")

    print(f"\n  {GOLD}■{RST} {DEEP_B}{BOLD}正式回测信息{RST}")
    print(f"    {_b('数据截止')}:      {cutoff.date()}")
    print(f"    {_b('完整成熟截止')}:  {(cutoff - timedelta(days=30)).date()}")
    print(f"    {_b('正式回测样本')}:  {_blue(str(m['n']))}")
    print(f"    {_b('未成熟观察')}:    {n_immature}")

    print(f"\n  {GOLD}■{RST} {DEEP_B}{BOLD}总体精度{RST}")
    print(f"    {_b('MAE')}:    {_blue(fmt(m['mae'], '.2f'))}  {_muted('平均绝对误差')}")
    print(f"    {_b('RMSE')}:   {_blue(fmt(m['rmse'], '.2f'))}  {_muted('均方根误差')}")
    exc_cnt = m['mape_excluded']
    print(f"    {_b('MAPE')}:   {_blue(fmt_or_na(m['mape'], '.1%'))}  {_muted(f'平均绝对百分比误差, 排除 {exc_cnt} 零值')}")
    print(f"    {_b('WAPE')}:   {_blue(fmt(m['wape'], '.1%'))}  {_muted('加权绝对百分比误差')}")
    print(f"    {_b('R²')}:     {_blue(fmt_or_na(m['r2'], '.3f'))}")
    print(f"    {_b('Corr')}:   {_blue(fmt_or_na(m['correlation'], '.3f'))}")

    print(f"\n  {GOLD}■{RST} {DEEP_B}{BOLD}系统性偏差{RST}")
    bias_sign = "低估" if m["mean_error"] > 0 else "高估"
    print(f"    {_b('Mean Error')}: {_blue(fmt(m['mean_error'], '.2f'))}  {_muted(f'({bias_sign})')}")
    print(f"    {_b('Median Error')}: {_blue(fmt(m['median_error'], '.2f'))}")
    print(f"    {_b('Bias %')}:     {_blue(fmt_or_na(m['bias_pct'], '+.1%'))}  {_muted('>0: 低估 (actual>forecast), <0: 高估')}")
    print(f"    {_b('高估天数')}:     {_blue(str(m['over_count']))} / {_b('低估天数')}: {_blue(str(m['under_count']))}")

    print(f"\n  {GOLD}■{RST} {DEEP_B}{BOLD}误差分布{RST}")
    print(f"    {_b('Median AE')}:  {_blue(fmt(m['median_ae'], '.1f'))}")
    print(f"    {_b('P80 AE')}:     {_blue(fmt(m['p80_ae'], '.1f'))}")
    print(f"    {_b('P90 AE')}:     {_blue(fmt(m['p90_ae'], '.1f'))}")
    print(f"    {_b('P95 AE')}:     {_blue(fmt(m['p95_ae'], '.1f'))}")
    print(f"    {_b('Max AE')}:     {_blue(fmt(m['max_ae'], '.1f'))}")
    print(f"    {_b('±10%')}:       {_blue(fmt_or_na(m['within_10pct'], '.1%'))}")
    print(f"    {_b('±20%')}:       {_blue(fmt_or_na(m['within_20pct'], '.1%'))}")
    print(f"    {_b('±30%')}:       {_blue(fmt_or_na(m['within_30pct'], '.1%'))}")

    print(f"\n  {GOLD}■{RST} {DEEP_B}{BOLD}异常日贡献{RST}")
    print(f"    AE: Top2={m['top2_ae_contribution_pct']:.1%}  Top5={m['top5_ae_contribution_pct']:.1%}  Top10={m['top10_ae_contribution_pct']:.1%}")
    print(f"    SE: Top2={m['top2_se_contribution_pct']:.1%}  Top5={m['top5_se_contribution_pct']:.1%}  Top10={m['top10_se_contribution_pct']:.1%}")

    if bl_metrics:
        print(f"\n  {GOLD}■{RST} {DEEP_B}{BOLD}基线模型对照{RST}")
        for bl_name, bl_m in bl_metrics.items():
            if bl_m:
                mae_imp = (bl_m["mae"] - m["mae"]) / bl_m["mae"]
                wape_imp = (bl_m["wape"] - m["wape"]) / bl_m["wape"]
                print(f"    {_b(bl_name)}:")
                print(f"      MAE={bl_m['mae']:.1f}  WAPE={bl_m['wape']:.1%}  Bias={bl_m['bias_pct']:+.1%}")
                print(f"      MAE提升={mae_imp:+.1%}  WAPE提升={wape_imp:+.1%}")

    print(f"\n  {GOLD}■{RST} {DEEP_B}{BOLD}验收阈值{RST}")
    for k, v in thresholds_status.items():
        icon = {"达标": "✅", "接近阈值": "⚠️", "未满足": "❌", "无法评价": "➖"}
        print(f"    {icon.get(v, '➖')} {k}: {v}")

    print(f"\n  {_ruler('━', 64)}\n")


def main():
    args = parse_args()
    cmd = "python " + " ".join(sys.argv)
    contract = None

    try:
        df = load_assign_data()
        cutoff = df["_date"].max()
        bt_end = cutoff - pd.Timedelta(days=7)
        bt_start = bt_end - pd.Timedelta(days=364)

        rd, cutoff = rolling_origin_backtest(df)
        n_immature = len(rd[~rd["evaluation_eligible"]])

        # Baselines
        rd = compute_baseline_historical_weekday(df, rd)
        rd = compute_baseline_rolling_rate(df, rd)

        # ── Launch Event Experiment ──
        events = parse_launch_events()
        rd = compute_event_features(rd, events)
        coeffs_list = compute_rolling_event_coefficients(rd, df, events)
        rd["cohort_pred_treatment_c1"] = rd["cohort_pred_30_lock"]
        rd["cohort_pred_treatment_c2"] = rd["cohort_pred_30_lock"]
        rd["cohort_pred_treatment_c3"] = rd["cohort_pred_30_lock"]

        if HAS_EVENTS and coeffs_list is not None:
            sorted_dates = sorted(rd["date"].unique())
            coeff_map = dict(zip(sorted_dates, coeffs_list))
            for idx, r in rd.iterrows():
                betas = coeff_map.get(r["date"], {k: 0.0 for k in LIFECYCLE_PHASES})
                cf = {k: r[f"{k}_count"] for k in LIFECYCLE_PHASES}
                cf["has_event_overlap"] = r.get("has_event_overlap", 0)
                cf["active_event_count"] = r.get("active_event_count", 0)

                # C1: lifecycle only
                c1 = apply_event_multiplier_log(r["cohort_pred_30_lock"], betas, cf)
                rd.at[idx, "cohort_pred_treatment_c1"] = round(c1, 1)

                # C2: lifecycle + overlap
                cf2 = dict(cf)
                overlap_beta = 0.0
                if cf2.get("has_event_overlap", 0):
                    overlap_beta = -0.05
                total_beta = sum(betas.get(k, 0.0) * cf2.get(k, 0) for k in LIFECYCLE_PHASES)
                total_beta += overlap_beta * cf2.get("has_event_overlap", 0)
                total_beta = max(min(total_beta, np.log(EVENT_CONFIG["max_multiplier"])),
                                 np.log(1.0 / EVENT_CONFIG["max_multiplier"]))
                c2 = r["cohort_pred_30_lock"] * np.exp(total_beta)
                rd.at[idx, "cohort_pred_treatment_c2"] = round(c2, 1)

                # C3: same as C2 (series overlap not implemented without series data)
                rd.at[idx, "cohort_pred_treatment_c3"] = round(c2, 1)

        el = rd[rd["evaluation_eligible"]].copy()
        metrics = compute_official_metrics(rd)

        # Treatment metrics (using same evaluation_eligible set)
        def _metrics_for_treat_col(treat_col):
            """Compute official metrics using treat_col as forecast, avoiding duplicate column."""
            el_t = rd[rd["evaluation_eligible"]].copy()
            # Build forecast array directly
            fc = el_t[treat_col].values.astype(float)
            ac = el_t["cohort_actual_30_lock"].values.astype(float)
            error = ac - fc
            abs_error = np.abs(error)
            sq_error = error ** 2
            sum_actual = ac.sum()
            n = len(el_t)
            mae = float(abs_error.mean())
            rmse = float(np.sqrt(sq_error.mean()))
            wape = float(abs_error.sum() / sum_actual) if sum_actual > 0 else np.nan
            non_zero = ac > 0
            ape = np.abs(ac[non_zero] - fc[non_zero]) / ac[non_zero]
            mape = float(ape.mean()) if len(ape) > 0 else np.nan
            mape_excluded = n - len(ape)
            mean_error = float(error.mean())
            median_error = float(np.median(error))
            bias_pct = (sum_actual - fc.sum()) / sum_actual if sum_actual > 0 else np.nan
            over_count = int((error < 0).sum())
            under_count = int((error > 0).sum())
            median_ae = float(np.median(abs_error))
            p80_ae = float(np.percentile(abs_error, 80))
            p90_ae = float(np.percentile(abs_error, 90))
            p95_ae = float(np.percentile(abs_error, 95))
            max_ae = float(abs_error.max())
            within_10 = float((abs_error / ac <= 0.1).mean()) if np.all(ac > 0) else np.nan
            within_20 = float((abs_error / ac <= 0.2).mean()) if np.all(ac > 0) else np.nan
            within_30 = float((abs_error / ac <= 0.3).mean()) if np.all(ac > 0) else np.nan
            corr = float(np.corrcoef(ac, fc)[0, 1]) if np.std(ac) > 0 and np.std(fc) > 0 else np.nan
            r2 = 1 - sq_error.sum() / ((ac - ac.mean()) ** 2).sum() if ((ac - ac.mean()) ** 2).sum() > 0 else np.nan

            top10_idx = np.argsort(abs_error)[-10:][::-1]
            top10_ae_contrib = abs_error[top10_idx].sum() / abs_error.sum() if abs_error.sum() > 0 else np.nan
            top5_ae_contrib = abs_error[top10_idx[:5]].sum() / abs_error.sum() if abs_error.sum() > 0 else np.nan
            top2_ae_contrib = abs_error[top10_idx[:2]].sum() / abs_error.sum() if abs_error.sum() > 0 else np.nan
            top10_se_contrib = sq_error[top10_idx].sum() / sq_error.sum() if sq_error.sum() > 0 else np.nan
            top5_se_contrib = sq_error[top10_idx[:5]].sum() / sq_error.sum() if sq_error.sum() > 0 else np.nan
            top2_se_contrib = sq_error[top10_idx[:2]].sum() / sq_error.sum() if sq_error.sum() > 0 else np.nan

            top10_df = el_t.iloc[top10_idx][["date", "cohort_assign_count", "prediction_method"]].copy()
            top10_df["cohort_pred_30_lock"] = fc[top10_idx]
            top10_df["cohort_actual_30_lock"] = ac[top10_idx].astype(int)
            top10_df["error"] = error[top10_idx]
            top10_df["abs_error"] = abs_error[top10_idx]
            top10_df["relative_error"] = np.where(ac[top10_idx] > 0, abs_error[top10_idx] / ac[top10_idx], np.nan)
            top10_df = top10_df.sort_values("date")

            return {
                "n": n, "mae": mae, "rmse": rmse, "mape": mape, "mape_excluded": mape_excluded,
                "wape": wape, "r2": r2, "correlation": corr,
                "mean_error": mean_error, "median_error": median_error,
                "bias_pct": bias_pct, "over_count": over_count, "under_count": under_count,
                "median_ae": median_ae, "p80_ae": p80_ae, "p90_ae": p90_ae, "p95_ae": p95_ae, "max_ae": max_ae,
                "within_10pct": within_10, "within_20pct": within_20, "within_30pct": within_30,
                "top10_ae_contribution_pct": top10_ae_contrib, "top5_ae_contribution_pct": top5_ae_contrib,
                "top2_ae_contribution_pct": top2_ae_contrib,
                "top10_se_contribution_pct": top10_se_contrib, "top5_se_contribution_pct": top5_se_contrib,
                "top2_se_contribution_pct": top2_se_contrib,
                "top10_exceptions": top10_df.to_dict("records"),
                "sum_actual": int(sum_actual), "sum_forecast": round(fc.sum(), 1),
            }
        metrics_tc1 = _metrics_for_treat_col("cohort_pred_treatment_c1") if HAS_EVENTS else None
        metrics_tc2 = _metrics_for_treat_col("cohort_pred_treatment_c2") if HAS_EVENTS else None
        metrics_tc3 = _metrics_for_treat_col("cohort_pred_treatment_c3") if HAS_EVENTS else None

        bl_metrics = {}
        for bl_name in ["baseline_weekday", "baseline_rolling_rate"]:
            bl_m = compute_baseline_metrics(el, bl_name)
            if bl_m:
                label = {"baseline_weekday": "历史同星期基线", "baseline_rolling_rate": "滚动转化率基线"}
                bl_metrics[label.get(bl_name, bl_name)] = bl_m

        # Lifecycle window metrics for Control and Treatment
        ev_metrics = {"control": compute_event_window_metrics(el)}
        nw_metrics = {"control": compute_normal_window_metrics(el)}
        if HAS_EVENTS:
            ev_mask = rd.loc[rd["evaluation_eligible"], "in_lifecycle_window"].values
            for treat_col, key in [("cohort_pred_treatment_c1", "treatment_c1"),
                                    ("cohort_pred_treatment_c2", "treatment_c2"),
                                    ("cohort_pred_treatment_c3", "treatment_c3")]:
                if treat_col not in rd.columns:
                    continue
                sub = rd[rd["evaluation_eligible"]][["cohort_actual_30_lock", treat_col]].copy()
                sub.columns = ["cohort_actual_30_lock", "cohort_pred_30_lock"]
                sub["in_lifecycle_window"] = ev_mask
                ev_metrics[key] = compute_event_window_metrics(sub)
                nw_metrics[key] = compute_normal_window_metrics(sub)

        # Phase-level breakdown
        phase_metrics = {}
        if HAS_EVENTS:
            for pk in LIFECYCLE_PHASES:
                in_p = el[el[f"{pk}_count"] > 0]
                if in_p.empty:
                    continue
                ac = in_p["cohort_actual_30_lock"].values.astype(float)
                fc = in_p["cohort_pred_30_lock"].values.astype(float)
                sa = ac.sum()
                if sa <= 0:
                    continue
                pm = {
                    "n": len(in_p),
                    "sum_actual": int(sa),
                    "control_sum": round(fc.sum(), 1),
                    "control_wape": round(float(np.abs(ac - fc).sum() / sa), 4),
                    "control_bias": round(float((sa - fc.sum()) / sa), 4),
                }
                if metrics_tc1:
                    fc_tc1 = in_p["cohort_pred_treatment_c1"].values.astype(float)
                    pm["treatment_c1_sum"] = round(fc_tc1.sum(), 1)
                    pm["treatment_c1_wape"] = round(float(np.abs(ac - fc_tc1).sum() / sa), 4)
                    pm["treatment_c1_bias"] = round(float((sa - fc_tc1.sum()) / sa), 4)
                    pm["wape_improvement"] = round(
                        (pm["control_wape"] - pm["treatment_c1_wape"]) / pm["control_wape"], 4
                    ) if pm["control_wape"] > 0 else np.nan
                phase_metrics[pk] = pm

        stratified = compute_stratified_metrics(el)
        thresholds_status = check_thresholds(metrics)
        summary = build_executive_summary(metrics, bl_metrics, thresholds_status)

        # Update the event_note in stratified
        if HAS_EVENTS:
            stratified["event_note"] = "已加载上市事件生命周期特征。详见上市事件生命周期实验模块。"

        if args.format == "terminal":
            print_terminal(metrics, bl_metrics, stratified, thresholds_status, summary, bt_start, bt_end, cutoff, n_immature)
            if HAS_EVENTS and metrics_tc1:
                print(f"\n  {GOLD}■{RST} {DEEP_B}{BOLD}上市事件实验摘要{RST}")
                print(f"    Control WAPE:  {metrics['wape']:.1%}")
                print(f"    Treatment C1:  {metrics_tc1['wape']:.1%}  (相对改善 {(metrics['wape'] - metrics_tc1['wape']) / metrics['wape']:.1%})")
                if metrics_tc2:
                    print(f"    Treatment C2:  {metrics_tc2['wape']:.1%}  (相对改善 {(metrics['wape'] - metrics_tc2['wape']) / metrics['wape']:.1%})")
                if metrics_tc3:
                    print(f"    Treatment C3:  {metrics_tc3['wape']:.1%}  (相对改善 {(metrics['wape'] - metrics_tc3['wape']) / metrics['wape']:.1%})")

        html_path = generate_html(rd, cutoff, metrics, bl_metrics, stratified, thresholds_status, summary,
                                   events=events, metrics_tc1=metrics_tc1, metrics_tc2=metrics_tc2, metrics_tc3=metrics_tc3,
                                   ev_metrics=ev_metrics, nw_metrics=nw_metrics, phase_metrics=phase_metrics)

        if args.format == "terminal":
            print(f"\n  {GOLD}■{RST} {DEEP_B}{BOLD}输出{RST}")
            print(f"    HTML: {html_path}")

        scope = {
            "data_source": str(ASSIGN_CSV),
            "time_window": {"start_date": str(bt_start.date()), "end_date": str(bt_end.date())},
            "filters": {"evaluation_eligible_only": True, "mature_window_months": 24},
            "metric_definition": "rolling-origin backtest: MAE/RMSE/MAPE/WAPE/R²/Bias/分层评估/双基线对照/上市事件生命周期实验",
        }
        result_metrics = {
            "n": metrics["n"], "mae": round(metrics["mae"], 2), "rmse": round(metrics["rmse"], 2),
            "mape": round(metrics["mape"], 4) if not np.isnan(metrics["mape"]) else None,
            "wape": round(metrics["wape"], 4), "r2": round(metrics["r2"], 4) if not np.isnan(metrics["r2"]) else None,
            "correlation": round(metrics["correlation"], 4) if not np.isnan(metrics["correlation"]) else None,
            "bias_pct": round(metrics["bias_pct"], 4) if not np.isnan(metrics["bias_pct"]) else None,
            "immature_count": n_immature,
        }
        if metrics_tc1:
            result_metrics["treatment_c1_wape"] = round(metrics_tc1["wape"], 4)
        summary_str = f"回测完成: N={metrics['n']}, Control WAPE={metrics['wape']:.1%}"
        if metrics_tc1:
            summary_str += f", Treatment C1 WAPE={metrics_tc1['wape']:.1%}"
        result = {"summary": summary_str, "metrics": result_metrics}

        warnings_list = ["模型基于三段式成熟度假设", "节假日日历暂未实现", "生命周期模型为 log-additive 近似"]
        if not HAS_EVENTS:
            warnings_list.append("上市事件生命周期数据暂缺")
        contract = build_success_contract(
            script="research_scripts/lock_predict_backtest.py", command=cmd,
            scope=scope, result=result,
            warnings=warnings_list,
            followup_context={"metric": "cohort_forecast_backtest", "available_dimensions": ["cohort_date", "month", "weekday"]},
        )

    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        contract = build_error_contract(
            script="research_scripts/lock_predict_backtest.py", command=cmd,
            error_message=str(e),
            warnings=[tb_str],
        )
        if args.format == "terminal":
            print(f"\n  {GOLD}⚠ 异常: {e}{RST}")
            print(tb_str[-2000:])

    if args.format == "json":
        if args.output:
            save_contract_json(contract, Path(args.output) / "lock_predict_backtest.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
        return

    if args.format == "terminal" and contract:
        print(f"\n  {_ruler('━', 64)}")
        print(f"  {GOLD}■{RST} {DEEP_B}{BOLD}数据信息{RST}")
        print(f"    {_b('数据源')}:  {contract['scope'].get('data_source', 'N/A')}")
        print(f"    {_b('方法')}:    三段式 (rolling-origin, 24mo 窗口)")
        print(f"    {_b('基线')}:    历史同星期 + 滚动转化率")
        print(f"    {_b('HTML')}:    {OUTPUT_HTML}")
        print(f"  {_ruler('━', 64)}\n")


if __name__ == "__main__":
    main()
