#!/usr/bin/env python
"""
开票月度预估 — 基于锁单→开票条件概率模型

方法:
  1. 从成熟队列 (2024-2025H1) 构建条件概率表:
     P(在接下来 r 天内开票 | 已等待 w 天尚未开票)
  2. 锁单预估来源 (三选一):
     a) --lock-forecast-json: 结构化预测输出
     b) --lock-regime: 预定义场景 ("mode", "p50", "p10", "p90")
     c) 近 N 日日均 (fallback)
  3. 开票推算 = 已发生开票 + 历史锁单延续开票 + 未来锁单当月开票

用法:
    python research_scripts/invoice_monthly_forecast.py
    python research_scripts/invoice_monthly_forecast.py --target-month 2026-07 --as-of 2026-07-13
    python research_scripts/invoice_monthly_forecast.py --lock-regime mode
    python research_scripts/invoice_monthly_forecast.py --lock-forecast-json outputs/forecast.json
    python research_scripts/invoice_monthly_forecast.py --format json
"""

import argparse, json, sys, calendar
from pathlib import Path
from datetime import date, timedelta

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
import numpy as np
from utils.paths import ensure_shared_on_path
ensure_shared_on_path()

ORDER_DATA = REPO_ROOT / "dataset" / "order_data.parquet"

# Structured forecast regime prior reference (raw, before posterior correction)
REGIME_REF = {
    "mode": {"weekday": 195.86, "weekend": 205.83},
    "p50":  {"weekday": 185.03, "weekend": 207.35},
    "p10":  {"weekday": 124.84, "weekend": 136.41},
    "p90":  {"weekday": 358.79, "weekend": 428.02},
}
# Historical effective sample size per regime (from structured forecast's regime_inputs)
REGIME_HIST_N = {"weekday": 156, "weekend": 63}
DEFAULT_PRIOR_STRENGTH = 30.0


def parse_args():
    p = argparse.ArgumentParser(description="开票月度预估（条件概率模型）")
    p.add_argument("--target-month", type=str, default=None,
                    help="目标月份，如 2026-07（默认：当前月）")
    p.add_argument("--as-of", type=str, default=None,
                    help="基准日期（默认：今天）")
    p.add_argument("--lock-forecast-json", type=str, default=None,
                    help="结构化锁单预测 JSON 路径（优先提取后验校正值）")
    p.add_argument("--lock-regime", type=str, default=None,
                    choices=["mode", "p50", "p10", "p90"],
                    help="锁单预测场景（不传则按近30日均值）")
    p.add_argument("--prior-strength", type=float, default=None,
                    help="锁单 prior 有效样本量。默认=min(raw_n, 30)。"
                         "与 structured_business_forecast.py 的 --prior-strength 一致。")
    p.add_argument("--matured-start", type=str, default="2024-01-01",
                    help="条件概率模型训练起始日期（默认：2024-01-01）")
    p.add_argument("--matured-end", type=str, default="2025-06-30",
                    help="条件概率模型训练截止日期（默认：2025-06-30）")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    p.add_argument("--output", type=str, default=None,
                    help="JSON 输出路径")
    return p.parse_args()


def build_cond_prob_model(
    df: pd.DataFrame,
    train_start: date,
    train_end: date,
    max_wait: int = 365,
    max_remain: int = 93,
) -> np.ndarray:
    """Build conditional probability table from matured cohort.
    
    cond_table[w, r] = P(invoice in next r days | waited w days, no invoice yet)
    """
    mature = df[(df["lock_date"] >= train_start) & (df["lock_date"] <= train_end)].copy()
    N = len(mature)
    inv = mature["has_invoice"].values
    lag = mature["lag_days"].values

    table = np.zeros((max_wait + 1, max_remain + 1))
    for w in range(max_wait + 1):
        risk_set = N - (inv & (lag <= w)).sum()
        if risk_set == 0:
            continue
        for r in range(max_remain + 1):
            events = (inv & (lag > w) & (lag <= w + r)).sum()
            table[w, r] = events / risk_set
    return table


def p_cond(table: np.ndarray, w: int, r: int) -> float:
    """P(invoice in next r days | waited w days, no invoice yet)."""
    max_wait, max_remain = table.shape[0] - 1, table.shape[1] - 1
    if w > max_wait:
        w = max_wait
    if r < 0:
        return 0.0
    if r > max_remain:
        r = max_remain
    return float(table[int(w), int(r)])


def load_data() -> tuple[pd.DataFrame, pd.Series]:
    """Load order data; return (all_locks, lock_daily_series)."""
    df = pd.read_parquet(ORDER_DATA)
    lk = df[df["lock_time"].notna()].copy()
    lk["lock_dt"] = pd.to_datetime(lk["lock_time"])
    lk["lock_date"] = lk["lock_dt"].dt.date
    lk["has_invoice"] = lk["invoice_upload_time"].notna()
    lk["lag_days"] = np.nan
    mask = lk["has_invoice"]
    lk.loc[mask, "lag_days"] = (
        pd.to_datetime(lk.loc[mask, "invoice_upload_time"]) - lk.loc[mask, "lock_dt"]
    ).dt.total_seconds() / 86400
    lock_daily = lk.groupby("lock_date").size()
    return lk, lock_daily


def resolve_lock_forecast(
    lock_daily: pd.Series,
    lk: pd.DataFrame,
    as_of: date,
    args,
) -> dict:
    """Return daily lock forecast dict for remaining days of target month.
    
    Returns dict with:
      - "forecast": {date: daily_locks}
      - "source": description of how values were derived
    """
    year, month = map(int, args.target_month.split("-"))
    month_start = date(year, month, 1)
    month_days = calendar.monthrange(year, month)[1]
    month_end = date(year, month, month_days)
    
    remaining_start = as_of + timedelta(days=1)
    if remaining_start > month_end:
        return {"forecast": {}, "source": "no_remaining_days"}
    
    remaining_dates = []
    d = remaining_start
    while d <= month_end:
        remaining_dates.append(d)
        d += timedelta(days=1)
    
    rem_wkd = sum(1 for d_ in remaining_dates if d_.weekday() < 5)
    rem_wke = sum(1 for d_ in remaining_dates if d_.weekday() >= 5)
    
    source = ""
    prior_wkd = prior_wke = 0.0
    
    if args.lock_forecast_json:
        with open(args.lock_forecast_json) as f:
            fc = json.load(f)
        mf = fc.get("scenario_forecast", {}).get("month_forecast", {})
        
        # Priority 1: posterior-corrected regime values from calendar correction
        cc = mf.get("month_totals", {}).get("calendar_regime_posterior_correction", {})
        if cc.get("enabled"):
            post = cc.get("posterior", {})
            cprior = cc.get("prior", {})
            prior_wkd = cprior.get("weekday", {}).get("mean", 195.86)
            prior_wke = cprior.get("weekend", {}).get("mean", 205.83)
            wkd = post.get("weekday", {}).get("mean", prior_wkd)
            wke = post.get("weekend", {}).get("mean", prior_wke)
            source = f"posterior_corrected(prior_strength={cc.get('prior_strength_source','?')})"
        else:
            # Fallback: prior regime reference from bayesian calibration
            cal = mf.get("bayesian_calibration", {})
            regime_ref = cal.get("regime_daily_lock_orders_reference", {})
            prior_wkd = regime_ref.get("weekday", {}).get("mode", 195.86)
            prior_wke = regime_ref.get("weekend", {}).get("mode", 205.83)
            wkd, wke = prior_wkd, prior_wke
            source = "bias_corrected_prior(no_posterior_available)"
    
    elif args.lock_regime:
        r = REGIME_REF[args.lock_regime]
        prior_wkd, prior_wke = r["weekday"], r["weekend"]
        ps = args.prior_strength if args.prior_strength is not None else DEFAULT_PRIOR_STRENGTH
        
        # Calendar-regime posterior correction inline
        obs = lk[(lk["lock_date"] >= month_start) & (lk["lock_date"] <= as_of)].copy()
        obs_wkd = obs[obs["lock_dt"].dt.dayofweek < 5]
        obs_wke = obs[obs["lock_dt"].dt.dayofweek >= 5]
        # n = number of calendar DAYS observed (not lock rows)
        n_wkd = obs_wkd["lock_date"].nunique() if len(obs_wkd) > 0 else 0
        n_wke = obs_wke["lock_date"].nunique() if len(obs_wke) > 0 else 0
        # S = total lock count over those days
        S_wkd = float(len(obs_wkd))
        S_wke = float(len(obs_wke))
        
        eff_n_wkd = min(REGIME_HIST_N["weekday"], ps)
        eff_n_wke = min(REGIME_HIST_N["weekend"], ps)
        
        if n_wkd > 0:
            alpha = prior_wkd * eff_n_wkd + S_wkd
            beta = eff_n_wkd + n_wkd
            wkd = alpha / beta
        else:
            wkd = prior_wkd
        
        if n_wke > 0:
            alpha = prior_wke * eff_n_wke + S_wke
            beta = eff_n_wke + n_wke
            wke = alpha / beta
        else:
            wke = prior_wke
        
        source = f"posterior_corrected_inline(regime={args.lock_regime}, prior_strength={ps})"
    
    else:
        # Fallback: compute from recent N days
        cutoff = as_of - timedelta(days=30)
        recent = lock_daily[lock_daily.index >= cutoff]
        recent_df = recent.reset_index()
        recent_df.columns = ["date", "count"]
        recent_df["dow"] = pd.to_datetime(recent_df["date"].astype(str)).dt.dayofweek
        wkd = recent_df[recent_df["dow"] < 5]["count"].mean()
        wke = recent_df[recent_df["dow"] >= 5]["count"].mean()
        source = "recent_30d_avg"
    
    forecast = {}
    for d_ in remaining_dates:
        forecast[d_] = wkd if d_.weekday() < 5 else wke
    
    adj = {}
    if "posterior_corrected" in source:
        prior_total = rem_wkd * prior_wkd + rem_wke * prior_wke
        post_total = rem_wkd * wkd + rem_wke * wke
        adj = {
            "adjustment_vs_baseline": round(post_total - prior_total, 2),
            "adjustment_rate": round((post_total - prior_total) / prior_total, 4) if prior_total > 0 else 0.0,
        }

    return {
        "forecast": forecast,
        "source": source,
        "regime_values": {"weekday": round(wkd, 2), "weekend": round(wke, 2)},
        "remaining_weekdays": rem_wkd,
        "remaining_weekends": rem_wke,
        **adj,
    }


def main():
    args = parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    args.target_month = args.target_month or as_of.strftime("%Y-%m")
    year, month = map(int, args.target_month.split("-"))
    month_start = date(year, month, 1)
    month_days = calendar.monthrange(year, month)[1]
    month_end = date(year, month, month_days)

    # Load data
    lk, lock_daily = load_data()

    # Build conditional probability model
    train_start = date.fromisoformat(args.matured_start)
    train_end = date.fromisoformat(args.matured_end)
    cond_table = build_cond_prob_model(lk, train_start, train_end)

    # Actual invoices to date in target month
    inv_data = lk[lk["has_invoice"]].copy()
    inv_data["invoice_date"] = pd.to_datetime(inv_data["invoice_upload_time"]).dt.date
    actual_inv = inv_data[
        (inv_data["invoice_date"] >= month_start) & (inv_data["invoice_date"] <= as_of)
    ]
    actual_sum = len(actual_inv)
    actual_days = (as_of - month_start).days + 1

    # Remaining days in month
    remaining_start = as_of + timedelta(days=1)
    remaining_days = max(0, (month_end - remaining_start).days + 1)

    # 1) Historical locks (pending) → invoices in remaining days
    hist_inv = 0
    hist_breakdown = {}
    # Go back far enough: any lock that could still invoice in remaining window
    lookback = date(2024, 1, 1)
    d = lookback
    while d <= as_of:
        n = int(lock_daily.get(d, 0))
        if n > 0:
            w = max(0, (as_of - d).days)
            prob = p_cond(cond_table, w, remaining_days)
            if prob > 0:
                est = n * prob
                hist_inv += est
                mk = f"{d.year}-{d.month:02d}"
                hist_breakdown[mk] = hist_breakdown.get(mk, 0) + est
        d += timedelta(days=1)

    # 2) Future projected locks → invoices in remaining days
    lock_fc_result = resolve_lock_forecast(lock_daily, lk, as_of, args)
    lock_fc = lock_fc_result["forecast"]
    future_inv = 0
    future_breakdown = {}
    for fc_date, fc_locks in lock_fc.items():
        r = max(0, (month_end - fc_date).days)
        prob = p_cond(cond_table, 0, r)
        est = fc_locks * prob
        future_inv += est
        future_breakdown[str(fc_date)] = round(est)

    total_estimate = actual_sum + hist_inv + future_inv

    # Build result
    result = {
        "target_month": args.target_month,
        "as_of": str(as_of),
        "method": "conditional_probability",
        "model": {
            "training_range": f"{train_start} ~ {train_end}",
            "conversion_rate_at_lock": round(p_cond(cond_table, 0, 180) * 100, 1),
        },
        "actual": {
            "days": actual_days,
            "range": f"{month_start} ~ {as_of}",
            "total_invoices": actual_sum,
        },
        "remaining": {
            "days": remaining_days,
            "range": f"{remaining_start} ~ {month_end}",
        },
        "lock_forecast_source": lock_fc_result.get("source", ""),
        "lock_regime_values": lock_fc_result.get("regime_values", {}),
        "projection": {
            "from_historical_locks": round(hist_inv),
            "from_future_locks": round(future_inv),
            "lock_forecast_daily": {str(k): round(v) for k, v in lock_fc.items()},
            "future_invoice_breakdown": future_breakdown,
            "adjustment_vs_baseline": lock_fc_result.get("adjustment_vs_baseline"),
            "adjustment_rate": lock_fc_result.get("adjustment_rate"),
        },
        "total_estimate": round(total_estimate),
    }

    if args.format == "json":
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"已写入 {args.output}")
        else:
            print(output)
        return

    # Terminal output: compute actual conversion rate from matured data
    mature_mask = (lk["lock_date"] >= train_start) & (lk["lock_date"] <= train_end)
    conv_rate = lk.loc[mature_mask, "has_invoice"].mean() * 100
    print()
    print(f"开票月度预估: {args.target_month}")
    print(f"{'=' * 52}")
    print(f"  基准日期:              {as_of}")
    print(f"  模型训练窗口:          {train_start} ~ {train_end}")
    print(f"  锁单终局转化率:        {conv_rate:.1f}%")
    print(f"  ────────────────────────────────────")
    print(f"  已发生开票 ({month_start}~{as_of}):  {actual_sum:>6d} 台（{actual_days}天）")
    print()
    
    if hist_breakdown:
        print(f"  历史锁单延续开票 ({remaining_start}~{month_end}):")
        for mk in sorted(hist_breakdown.keys()):
            v = hist_breakdown[mk]
            if v > 1:
                print(f"    {mk}: {v:>8.0f} 台")
        print(f"    {'小计':>12s}: {hist_inv:>8.0f} 台")
    
    print()
    print(f"  未来锁单当月开票:")
    for d_, est in future_breakdown.items():
        print(f"    {d_}: {est:>5d} 台")
    print(f"    {'小计':>12s}: {future_inv:>6.0f} 台")
    print(f"  ────────────────────────────────────")
    
    lock_total_fc = round(sum(lock_fc.values()))
    lk_src = lock_fc_result.get("source", "")
    rv = lock_fc_result.get("regime_values", {})
    print(f"  锁单预估 (剩余{remaining_days}天):       {lock_total_fc:>6d} 台")
    if rv:
        print(f"    工作日={rv.get('weekday','?'):>5}/天, 周末={rv.get('weekend','?'):>5}/天")
    if lk_src:
        print(f"    来源: {lk_src}")
    print(f"  {'预估 2026-07 开票合计':>24s}:  {total_estimate:>6.0f} 台")
    print()


if __name__ == "__main__":
    main()
