#!/usr/bin/env python
"""
ATP 价格月报 — 包装 skills_atp_price.py，统一 CLI + Result Contract

用法:
    python mashang_workspace/runtime_scripts/atp_price_report.py --month 2026-05
    python mashang_workspace/runtime_scripts/atp_price_report.py --month 2026-05 --format json
    python mashang_workspace/runtime_scripts/atp_price_report.py --month 2026-05 --format json --output outputs/tables/
    python mashang_workspace/runtime_scripts/atp_price_report.py --help
"""

import sys, argparse, json
from pathlib import Path

_WS_ROOT = Path(__file__).resolve().parents[1]
_PRJ_ROOT = _WS_ROOT.parent
_RUNTIME_DIR = _PRJ_ROOT / "mashang_runtime"
for p in [str(_WS_ROOT), str(_PRJ_ROOT), str(_RUNTIME_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd
from datetime import datetime, timedelta
from utils.paths import ensure_shared_on_path
ensure_shared_on_path()
from utils.result_contract import build_success_contract, build_partial_contract, save_contract_json, contract_to_terminal

from operators.atp_analysis import run_atp_operator, apply_business_logic, _load_business_definition

ORDER_PARQUET = _PRJ_ROOT / "dataset" / "order_data.parquet"


def parse_args():
    p = argparse.ArgumentParser(description="ATP 价格月报")
    p.add_argument("--month", type=str, help="报告月份 YYYY-MM（默认前一个月）")
    p.add_argument("--start-date", type=str, help="开始日期 (YYYY-MM-DD)")
    p.add_argument("--end-date", type=str, help="结束日期 (YYYY-MM-DD)")
    p.add_argument("--series", type=str, help="车系过滤")
    p.add_argument("--model", type=str, help="具体车型过滤")
    p.add_argument("--city", type=str, help="忽略")
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json", "csv", "html"])
    p.add_argument("--date", type=str, help="忽略"); p.add_argument("--limit", type=int, default=0, help="忽略")
    return p.parse_args()


def _resolve_month(args):
    """解析月份或日期范围。"""
    if args.start_date and args.end_date:
        s = pd.Timestamp(args.start_date)
        e = pd.Timestamp(args.end_date)
        return s, e, f"{args.start_date}~{args.end_date}", "range"
    month = args.month
    if not month:
        today = datetime.now()
        prev = today.replace(day=1) - timedelta(days=1)
        month = prev.strftime("%Y-%m")
    parts = month.split("-")
    y, m = int(parts[0]), int(parts[1])
    t_start = datetime(y, m, 1)
    t_end = (t_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return t_start, t_end, month, "month"


def main():
    args = parse_args()
    cmd = "python " + " ".join(sys.argv)
    t_start, t_end, t_label, tw_type = _resolve_month(args)

    d_start = t_start.strftime("%Y-%m-%d")
    d_end = t_end.strftime("%Y-%m-%d")
    d_end_excl = (t_end + timedelta(days=1)).strftime("%Y-%m-%d")

    df = pd.read_parquet(str(ORDER_PARQUET))
    bdef = _load_business_definition()
    df_wl = apply_business_logic(df, bdef)

    if args.series:
        df_wl = df_wl[df_wl["series"] == args.series]
    if args.model:
        df_wl = df_wl[df_wl["product_name"].str.contains(args.model, na=False)]

    time_periods = bdef.get("time_periods", {})
    target_year = t_start.year
    new_groups = {g for g, p in time_periods.items() if pd.to_datetime(p["end"]).year >= target_year}
    old_groups = {g for g, p in time_periods.items() if pd.to_datetime(p["end"]).year < target_year}
    all_groups = new_groups | old_groups

    def _suv(d): return d[d["series_derived"].isin(["LS6", "LS7", "LS8", "LS9"])]
    def _sedan(d): return d[d["series_derived"].isin(["L6", "L7"])]
    def _old(d): return d[d["series_group_logic"].isin(old_groups) | ~d["series_group_logic"].isin(all_groups)]
    def _new(d): return d[d["series_group_logic"].isin(new_groups)]

    segments = [
        ("所有车型", None), ("已有车型", _old), ("当年新车型(含改款)", _new),
        ("SUV", _suv), ("SUV 已有车型", lambda d: _old(_suv(d))),
        ("LS6", lambda d: d[d["series_derived"] == "LS6"]),
        ("LS9", lambda d: d[d["series_derived"] == "LS9"]),
        ("Sedan", _sedan), ("Sedan 已有车型", lambda d: _old(_sedan(d))),
        ("L6", lambda d: d[d["series_derived"] == "L6"]),
        ("SUV 当年新车型", lambda d: _new(_suv(d))),
    ]

    dim_items = []
    totals_orders = 0
    totals_amount = 0.0

    for name, fn in segments:
        seg_df = df_wl if fn is None else fn(df_wl.copy())
        r = run_atp_operator(seg_df, d_start, d_end_excl)
        orders = r.get("total_orders", 0)
        price = r.get("avg_price")
        if orders > 0 and price is not None:
            totals_orders += orders
            totals_amount += price * orders
            dim_items.append({"value": name, "metrics": {"vehicle_count": orders, "avg_atp": round(price, 2)}})

    avg_atp = round(totals_amount / totals_orders, 2) if totals_orders > 0 else None

    scope = {
        "data_source": str(ORDER_PARQUET),
        "time_window": {"type": tw_type, "month": t_label, "start_date": d_start, "end_date": d_end},
        "filters": {"series": args.series, "model": args.model},
        "metric_definition": "ATP = mean(invoice_amount) WHERE order_type='用户车' AND invoice_amount > 0",
    }
    result = {
        "summary": f"ATP 月报 {t_label}: total_amount={totals_amount:,.0f}, vehicle_count={totals_orders}, avg_atp={avg_atp}",
        "metrics": {"total_amount": round(totals_amount, 2), "vehicle_count": totals_orders, "avg_atp": avg_atp},
        "dimensions": [{"name": "series", "items": dim_items}],
    }
    artifacts = {}
    out_dir = Path(args.output) if args.output else _WS_ROOT / "outputs" / "tables"
    if args.format in ("csv", "html") or args.output:
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.format == "html":
            artifacts["html"] = str(out_dir / f"atp_{t_label}.html")

    ctx = {"metric": "atp_price", "month": t_label, "start_date": d_start, "end_date": d_end,
           "available_dimensions": ["series", "product_name"],
           "top_entities": dim_items[:5] if dim_items else []}

    contract = build_success_contract(
        script="mashang_workspace/runtime_scripts/atp_price_report.py", command=cmd,
        scope=scope, result=result, artifacts=artifacts, followup_context=ctx,
    )

    # Also output legacy terminal format
    if args.format == "terminal" or (args.format == "json" and args.output):
        _print_legacy(t_label, dim_items, totals_orders, avg_atp)

    if args.format == "json":
        if args.output:
            save_contract_json(contract, out_dir / f"atp_{t_label}.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))


def _print_legacy(month: str, items: list, total_orders: int, avg_atp: float):
    print("[Summary]")
    print(f"  ATP 月报: {month}")
    print()
    print("[Scope]")
    print(f"  数据源: dataset/order_data.parquet")
    print(f"  月份: {month}")
    print(f"  指标口径: mean(invoice_amount) WHERE order_type='用户车' AND invoice_amount > 0")
    print()
    print("[Result]")
    print(f"  {'系别':30s} {'用户车锁单':>10s} {'ATP':>12s}")
    print(f"  {'-'*30} {'-'*10} {'-'*12}")
    for item in items:
        name = item["value"]
        count = item["metrics"]["vehicle_count"]
        price = item["metrics"]["avg_atp"]
        print(f"  {name:30s} {count:10d} ¥{price:>10,.0f}")
    print(f"  {'汇总':30s} {total_orders:10d} ¥{avg_atp:>10,.0f}" if avg_atp else "")
    print()


if __name__ == "__main__":
    main()
