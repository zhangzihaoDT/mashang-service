#!/usr/bin/env python
"""
当前业务状态排查 — 库存 × Backlog × 风险暴露

对任意观察日（含历史时点）输出三个核心水位指标（分车系 + 合计）:
    1. 库存数        = 国内 DC 在库_未开票（delivery_inventory 快照，排除海外/上汽国际）
    2. 待开票未退订  = 锁单 & 未开票 & 未退订
    3. 风险暴露      = (1 − 有效率) × 待开票未退订 = 悬置池 − ELOE

另补充三项经营水位指标:
    4. 30 日日均下发线索 = 过去 30 日下发线索数 / 30（assign_data，整体口径）
    5. 有效门店数 × 单店日均 = 近 30 日日均下发门店数 × 日均线索/门店（assign_data，整体口径）
    6. 库存覆盖天数 MOS = 库存数 / 近 30 日日均开票销量（零售开票剔除对公）

point-in-time 口径（重要）:
    --as-of 支持任意历史时点；Backlog/风险暴露按 as-of 状态重建（与 backlog_rate_trend_report
    同口径）：观察点之后才开票/退订的订单仍计入当时池子；PIT ELOE 对已知结局取确定值
    （最终开票→1，已退订→0），仅仍悬置订单用模型概率（Age-only / Age×Series）。
    库存快照用 real_in_dc_time / 出库·开票时间戳按观察日重建。

用法:
    python runtime_scripts/current_state_diagnosis.py                          # 最新数据日
    python runtime_scripts/current_state_diagnosis.py --as-of 2025-04-17       # 历史时点
    python runtime_scripts/current_state_diagnosis.py --series LS8
    python runtime_scripts/current_state_diagnosis.py --format json --output outputs/tables/

依赖:
    dataset/delivery_inventory.parquet, dataset/order_data.parquet
    shared/operators/dealer_unsold_inventory.py, shared/operators/effective_locked_orders.py
"""

import sys, argparse, json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
import numpy as np
from utils.paths import ensure_shared_on_path
from utils.data_loader import load_order_data
from utils.result_contract import build_success_contract, save_contract_json, contract_to_terminal

ensure_shared_on_path()
from operators.dealer_unsold_inventory import compute as compute_inventory  # noqa: E402
from operators.effective_locked_orders import (  # noqa: E402
    build_outcome_frame, estimate_curve_global, estimate_curve_by_series, predict_p,
)
from operators.assign_conversion import _parse_cn_date  # noqa: E402
from utils.business import is_corporate_owner  # noqa: E402

INVENTORY_PARQUET = REPO_ROOT / "dataset" / "delivery_inventory.parquet"
ASSIGN_CSV = REPO_ROOT / "dataset" / "assign_data.csv"
LEAD_WINDOW_DAYS = 30
OVERSEAS = {"上汽国际", "海外"}
SERIES_MAP = {"LSJEL": "LS8", "LSJEH": "LS9", "LSJWL": "LS7",
              "LSJWR": "LS6", "LSJWT": "L6", "LSJE3": "L7"}
SERIES_ORDER = ["LS6", "LS8", "LS9", "L6", "LS7", "L7"]
TRAIN_WINDOW = 365
MATURITY = 120
SHRINKAGE = 30.0


def compute_pit_backlog(odf: pd.DataFrame, as_of: pd.Timestamp,
                        pool_window: str = "rolling", model: str = "series",
                        series: str | None = None) -> dict | None:
    """point-in-time Backlog 重建（任意观察日，非当前状态）。

    池子成员按 as-of 判定：开票/退订时间为空或晚于观察日的订单仍计入当时池子。
    PIT ELOE 逐单重建：已知最终开票→1、已退订→0、仍悬置→模型概率（Age-only / Age×Series）。
    训练曲线只用观察日之前的锁单（out-of-sample），避免 look-ahead。
    """
    as_of = pd.Timestamp(as_of).normalize()
    obs_end = as_of + pd.Timedelta(days=1)

    if series:
        odf = odf[odf["series"] == series]

    train_start = max(as_of - pd.Timedelta(days=TRAIN_WINDOW), odf["lock_time"].min())
    train_end = min(as_of - pd.Timedelta(days=MATURITY), as_of)
    if train_end <= train_start:
        return None
    train = build_outcome_frame(odf, train_start, train_end)
    if len(train) < 500:
        return None
    global_curve = estimate_curve_global(train, MATURITY)
    series_curves = (estimate_curve_by_series(train, MATURITY, SHRINKAGE)
                     if model == "series" else None)

    if pool_window == "rolling":
        current_start = as_of - pd.Timedelta(days=365)
    else:
        current_start = pd.Timestamp(year=as_of.year, month=1, day=1)

    mask = (odf["lock_time"].notna()
            & (odf["invoice_upload_time"].isna() | (odf["invoice_upload_time"] >= obs_end))
            & (odf["apply_refund_time"].isna() | (odf["apply_refund_time"] >= obs_end))
            & (odf["actual_refund_time"].isna() | (odf["actual_refund_time"] >= obs_end))
            & (odf["lock_time"] >= current_start)
            & (odf["lock_time"] < obs_end))
    pool = odf[mask].copy()
    if pool.empty:
        return None
    pool["age"] = (as_of - pool["lock_time"]).dt.days.clip(lower=1)
    pool["p_model"] = [predict_p(int(a), s, global_curve, series_curves, MATURITY)
                       for a, s in zip(pool["age"], pool["series"])]
    final_inv = pool["invoice_upload_time"].notna().astype(int)
    final_ref = (pool["apply_refund_time"].notna()
                 | pool["actual_refund_time"].notna()).astype(int)
    pool["p"] = np.where(final_inv == 1, 1.0,
                         np.where(final_ref == 1, 0.0, pool["p_model"]))
    sub = pool.groupby("order_number", as_index=False).first()

    total = int(len(sub))
    eloe = float(sub["p"].sum())
    by_series = {}
    for s in SERIES_ORDER:
        ss = sub[sub["series"] == s]
        if ss.empty:
            continue
        eff = float(ss["p"].sum())
        by_series[s] = {
            "pending": int(len(ss)),
            "effective": round(eff, 1),
            "at_risk": round(len(ss) - eff, 1),
            "rate": round(eff / len(ss), 4),
        }
    return {
        "as_of": str(as_of.date()),
        "pool_window": pool_window,
        "model": "Age×Series" if model == "series" else "Age-only",
        "pending": total,
        "eloe": round(eloe, 1),
        "at_risk": round(total - eloe, 1),
        "rate": round(eloe / total, 4),
        "by_series": by_series,
    }


def parse_args():
    p = argparse.ArgumentParser(description="当前业务状态排查 — 库存 × Backlog × 风险暴露")
    p.add_argument("--as-of", type=str, default=None, help="观察日 (YYYY-MM-DD，默认最新数据日)")
    p.add_argument("--series", type=str, default=None, help="车系过滤 (LS6/L6/LS8/LS9/LS7/L7)")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json", "csv"])
    p.add_argument("--output", type=str, help="输出目录 (csv/json 需要)")
    return p.parse_args()


def compute_inventory_snapshot(df_inv: pd.DataFrame, odf: pd.DataFrame,
                               as_of: pd.Timestamp, series: str | None) -> dict:
    """国内 DC 在库_未开票快照：real_in_dc_time < obs_end 且未出库未开票。"""
    inv = compute_inventory(df_inv, odf)
    domestic = inv[~inv["bloc_name"].isin(OVERSEAS)].copy()
    obs_end = as_of + pd.Timedelta(days=1)
    domestic["arrival"] = pd.to_datetime(domestic["real_in_dc_time"])
    domestic["exit_event"] = domestic[["out_delivery_center_time", "order_invoice_upload_time"]].min(axis=1)
    mask = (domestic["arrival"] < obs_end) & (domestic["exit_event"].isna() | (domestic["exit_event"] >= obs_end))
    cur = domestic[mask].copy()
    cur["series"] = cur["vin"].str[:5].map(SERIES_MAP).fillna("其他")
    if series:
        cur = cur[cur["series"] == series]
    by_series = {m: int((cur["series"] == m).sum()) for m in SERIES_ORDER}
    return {"total": int(len(cur)), "by_series": by_series}


def compute_leads_metrics(assign_df: pd.DataFrame, as_of: pd.Timestamp) -> dict | None:
    """30 日日均下发线索 + 有效门店数 + 单店日均（assign_data，整体口径）。

    30 日日均下发线索 = 过去 30 日下发线索数 / 30；
    有效门店数 = 近 30 日下发门店数日均（日均接收线索的门店规模）；
    单店日均 = 30 日日均下发线索 / 有效门店数。
    """
    as_of = pd.Timestamp(as_of).normalize()
    start = as_of - pd.Timedelta(days=LEAD_WINDOW_DAYS)
    w = assign_df[(assign_df["_date"] > start) & (assign_df["_date"] <= as_of)]
    if w.empty:
        return None
    leads_sum = float(w["下发线索数"].sum())
    stores_avg = float(w["下发门店数"].mean())
    leads_avg = leads_sum / LEAD_WINDOW_DAYS
    return {
        "window_start": (start + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "window_end": as_of.strftime("%Y-%m-%d"),
        "days": LEAD_WINDOW_DAYS,
        "leads_30d_sum": int(round(leads_sum)),
        "leads_30d_avg": round(leads_avg, 1),
        "effective_stores_avg": round(stores_avg, 1),
        "leads_per_store_daily": round(leads_avg / stores_avg, 1) if stores_avg > 0 else None,
    }


def compute_sales_30d(odf: pd.DataFrame, as_of: pd.Timestamp,
                      series: str | None) -> dict:
    """近 30 日开票销量（零售开票剔除对公），用于库存覆盖天数分母。"""
    as_of = pd.Timestamp(as_of).normalize()
    start = as_of - pd.Timedelta(days=LEAD_WINDOW_DAYS)
    inv = odf[pd.to_datetime(odf["invoice_upload_time"]).between(start, as_of)]
    inv = inv[inv["lock_time"].notna()]
    if "owner_identity_no" in inv.columns:
        corp = inv["owner_identity_no"].apply(
            lambda x: is_corporate_owner(x) if pd.notna(x) else False)
        inv = inv[~corp]
    if series:
        inv = inv[inv["series"] == series]
    out = {m: int((inv["series"] == m).sum()) for m in SERIES_ORDER}
    out["total"] = int(len(inv))
    return out


def coverage_days(inventory: int, sales_30d: int) -> float | None:
    """库存覆盖天数 MOS = 库存数 / 近 30 日日均开票销量。"""
    if not sales_30d:
        return None
    return round(inventory * LEAD_WINDOW_DAYS / sales_30d, 1)


def main():
    args = parse_args()
    cmd = "python " + " ".join(sys.argv)

    odf = load_order_data()
    as_of_default = odf["lock_time"].max().normalize()
    as_of = pd.Timestamp(args.as_of) if args.as_of else as_of_default

    # ── 库存 ──
    df_inv = pd.read_parquet(INVENTORY_PARQUET)
    inventory = compute_inventory_snapshot(df_inv, odf, as_of, args.series)

    # ── 下发线索 / 有效门店 / 库存覆盖天数（经营水位指标）──
    assign_df = None
    try:
        _a = pd.read_csv(ASSIGN_CSV)
        _a["_date"] = _parse_cn_date(_a["Assign Time 年/月/日"])
        assign_df = _a[_a["_date"].notna()]
    except Exception:
        assign_df = None
    leads = compute_leads_metrics(assign_df, as_of) if assign_df is not None else None
    sales_30d = compute_sales_30d(odf, as_of, args.series)

    # ── Backlog（待开票未退订）+ ELOE / 风险暴露：point-in-time 重建（任意观察日）──
    roll = compute_pit_backlog(odf, as_of, pool_window="rolling", model="series",
                               series=args.series)
    ytd = compute_pit_backlog(odf, as_of, pool_window="cumulative", model="age",
                              series=args.series)
    if roll is None or ytd is None:
        sys.exit(f"❌ {as_of.date()} 时点训练样本或观察池不足，无法重建")

    pending_by_series = {s: v["pending"] for s, v in roll["by_series"].items()}
    eff_by_series = {s: v["effective"] for s, v in roll["by_series"].items()}
    at_risk_ytd_by_series = {s: v["at_risk"] for s, v in ytd["by_series"].items()}
    at_risk_ytd = ytd["at_risk"]
    pending_ytd = ytd["pending"]
    rate_ytd = ytd["rate"]
    ytd_start = f"{as_of.year}-01-01"

    rows = []
    for m in SERIES_ORDER:
        if args.series and m != args.series:
            continue
        inv_c = inventory["by_series"].get(m, 0)
        pend = pending_by_series.get(m, 0)
        eff = eff_by_series.get(m, 0.0)
        rate = round(eff / pend, 4) if pend else None
        at_risk = round(pend - eff, 1) if pend else None
        sales_c = int(sales_30d.get(m, 0))
        rows.append({
            "series": m,
            "inventory": inv_c,
            "sales_30d": sales_c,
            "coverage_days": coverage_days(inv_c, sales_c),
            "pending": int(pend),
            "effective_rate": rate,
            "at_risk": at_risk,
            "at_risk_ytd": at_risk_ytd_by_series.get(m),
        })

    total_inventory = sum(r["inventory"] for r in rows)
    total_pending = sum(r["pending"] for r in rows)
    total_at_risk = round(sum(r["at_risk"] or 0 for r in rows), 1)
    total_rate = round((total_pending - total_at_risk) / total_pending, 4) if total_pending else None
    total_sales_30d = sum(r["sales_30d"] for r in rows)
    total_coverage = coverage_days(total_inventory, total_sales_30d)

    summary = (f"库存 {total_inventory:,} 台 · 待开票未退订 {total_pending:,} 单 · "
               f"有效率 {total_rate:.1%} · 风险暴露(滚动365d) {total_at_risk:,.0f} 单 · "
               f"风险暴露({as_of.year}当年累计) {at_risk_ytd:,.0f} 单"
               if at_risk_ytd is not None else
               f"库存 {total_inventory:,} 台 · 待开票未退订 {total_pending:,} 单 · "
               f"有效率 {total_rate:.1%} · 风险暴露(滚动365d) {total_at_risk:,.0f} 单")
    if leads:
        summary += (f"\n下发线索(近30日) 日均 {leads['leads_30d_avg']:,.1f} 条 · "
                    f"有效门店日均 {leads['effective_stores_avg']:,.1f} 家 · "
                    f"单店日均 {leads['leads_per_store_daily']:,.1f} 条")
    if total_coverage is not None:
        summary += f"\n库存覆盖天数(近30日开票口径) {total_coverage:,.1f} 天"

    # ── 输出 ──
    if args.format == "terminal":
        print(f"当前业务状态排查（截至 {as_of.date()}）")
        print(f"  {summary}")
        print()
        hdr = (f"{'车型':<5}{'库存数':>8}{'近30日销量':>10}{'覆盖天数':>8}"
               f"{'待开票未退订':>12}{'有效率':>9}{'风险暴露(滚动)':>12}{'风险暴露(当年)':>12}")
        print(hdr)
        print("-" * len(hdr))
        for r in rows:
            rate_s = f"{r['effective_rate']:.1%}" if r["effective_rate"] is not None else "—"
            atr_s = f"{r['at_risk']:,.0f}" if r["at_risk"] is not None else "—"
            atr_ytd_s = f"{r['at_risk_ytd']:,.0f}" if r["at_risk_ytd"] is not None else "—"
            cov_s = f"{r['coverage_days']:,.1f}" if r["coverage_days"] is not None else "—"
            print(f"{r['series']:<5}{r['inventory']:>8,}{r['sales_30d']:>10,}{cov_s:>8}"
                  f"{r['pending']:>12,}{rate_s:>9}{atr_s:>12}{atr_ytd_s:>12}")
        print("-" * len(hdr))
        total_rate_s = f"{total_rate:.1%}" if total_rate is not None else "—"
        total_at_risk_ytd_s = f"{at_risk_ytd:,.0f}" if at_risk_ytd is not None else "—"
        total_cov_s = f"{total_coverage:,.1f}" if total_coverage is not None else "—"
        print(f"{'合计':<5}{total_inventory:>8,}{total_sales_30d:>10,}{total_cov_s:>8}"
              f"{total_pending:>12,}{total_rate_s:>9}{total_at_risk:>12,.0f}{total_at_risk_ytd_s:>12}")
        if at_risk_ytd is not None:
            print(f"\n风险暴露（{as_of.year} 当年累计，Age-only，与 backlog_rate_trend_report 同口径）"
                  f"：{at_risk_ytd:,.0f} 单（待开票未退订 {pending_ytd:,} 单，有效率 {rate_ytd:.1%}）")
        return

    result_data = {
        "as_of": str(as_of.date()),
        "summary": summary,
        "metrics": {
            "inventory_total": total_inventory,
            "pending_total": total_pending,
            "effective_rate": total_rate,
            "at_risk_total": total_at_risk,
            "at_risk_ytd": at_risk_ytd,
            "leads_30d_avg": leads["leads_30d_avg"] if leads else None,
            "effective_stores_avg": leads["effective_stores_avg"] if leads else None,
            "leads_per_store_daily": leads["leads_per_store_daily"] if leads else None,
            "sales_30d_total": total_sales_30d,
            "inventory_coverage_days": total_coverage,
        },
        "inventory": {"total": total_inventory, "by_series": inventory["by_series"]},
        "backlog": {
            "pending_total": total_pending,
            "effective_rate": total_rate,
            "at_risk_total": total_at_risk,
            "ytd": {
                "start": ytd_start,
                "pending": pending_ytd,
                "effective_rate": rate_ytd,
                "at_risk": at_risk_ytd,
                "model": "age",
            },
        },
        "leads": leads,
        "mos": {
            "window_days": LEAD_WINDOW_DAYS,
            "sales_30d_total": total_sales_30d,
            "inventory_coverage_days": total_coverage,
        },
        "rows": rows,
    }
    contract = build_success_contract(
        script="runtime_scripts/current_state_diagnosis.py",
        command=cmd,
        scope={
            "data_source": f"{INVENTORY_PARQUET}; dataset/order_data.parquet; {ASSIGN_CSV}",
            "time_window": {"as_of": str(as_of.date())},
            "filters": {"series": args.series},
            "metric_definition": (
                "库存=国内DC在库_未开票快照(按观察日时间戳重建); "
                "待开票未退订=锁单&未开票&未退订(point-in-time as-of重建); "
                "风险暴露=(1−有效率)×待开票未退订=悬置池−ELOE; "
                "滚动365d=Age×Series; 当年累计=当年1月1日起+Age-only(与backlog_rate_trend_report同口径); "
                "30日日均下发线索=过去30日下发线索数/30(assign_data整体口径,窗口不跨as-of); "
                "有效门店数=近30日下发门店数日均; 单店日均=30日日均下发线索/有效门店数; "
                "库存覆盖天数=库存数/近30日日均开票销量(零售开票剔除对公)"
            ),
        },
        result=result_data,
        followup_context={
            "metric": "current_state_diagnosis",
            "as_of": str(as_of.date()),
            "available_dimensions": ["series", "city", "model"],
            "top_entities": [{"field": "series", "value": r["series"],
                              "metrics": {"at_risk": r["at_risk"]}} for r in rows],
        },
    )

    if args.format == "json":
        print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        out_dir = Path(args.output) if args.output else _WS_ROOT / "outputs" / "tables"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_csv = out_dir / f"current_state_diagnosis_{as_of:%Y%m%d}.csv"
        pd.DataFrame(rows).to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(summary)
        print(f"CSV: {out_csv}")


if __name__ == "__main__":
    main()
