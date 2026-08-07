#!/usr/bin/env python
"""
ATP 价格月报 — 统一 CLI + Result Contract，含月度窗口与当年累计(YTD)窗口

用法:
    python mashang_workspace/runtime_scripts/atp_price_report.py --month 2026-05
    python mashang_workspace/runtime_scripts/atp_price_report.py --month 2026-05 --format json
    python mashang_workspace/runtime_scripts/atp_price_report.py --month 2026-05 --format json --output outputs/tables/
    python mashang_workspace/runtime_scripts/atp_price_report.py --month 2026-05 --format html
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
        ("所有车型", None, "all"),
        ("已有车型", _old, "all"),
        ("当年新车型(含改款)", _new, "all"),
        ("Sedan (L6+L7)", _sedan, "sedan"),
        ("Sedan 已有车型", lambda d: _old(_sedan(d)), "sedan"),
        ("L6", lambda d: d[d["series_derived"] == "L6"], "sedan"),
        ("Sedan 当年新车型(含改款)", lambda d: _new(_sedan(d)), "sedan"),
        ("SUV (LS6+LS7+LS8+LS9)", _suv, "suv"),
        ("SUV 已有车型", lambda d: _old(_suv(d)), "suv"),
        ("LS6", lambda d: d[d["series_derived"] == "LS6"], "suv"),
        ("LS9", lambda d: d[d["series_derived"] == "LS9"], "suv"),
        ("SUV 当年新车型(含改款)", lambda d: _new(_suv(d)), "suv"),
    ]

    ytd_start = f"{t_start.year}-01-01"

    dim_items = []
    overall_orders = 0
    overall_amount = 0.0

    for name, fn, group in segments:
        seg_df = df_wl if fn is None else fn(df_wl.copy())
        r_m = run_atp_operator(seg_df, d_start, d_end_excl)
        r_y = run_atp_operator(seg_df, ytd_start, d_end_excl)
        m_orders = r_m.get("total_orders", 0)
        m_price = r_m.get("avg_price")
        y_orders = r_y.get("total_orders", 0)
        y_price = r_y.get("avg_price")
        dim_items.append({
            "value": name,
            "group": group,
            "metrics": {
                "vehicle_count": m_orders,
                "avg_atp": round(float(m_price), 2) if m_price is not None else None,
                "ytd_vehicle_count": y_orders,
                "ytd_avg_atp": round(float(y_price), 2) if y_price is not None else None,
            },
        })
        if name == "所有车型":
            overall_orders = m_orders
            overall_amount = float(m_price) * m_orders if m_price is not None else 0.0

    avg_atp = round(overall_amount / overall_orders, 2) if overall_orders > 0 else None
    total_amount = round(overall_amount, 2)
    vehicle_count = overall_orders

    scope = {
        "data_source": str(ORDER_PARQUET),
        "time_window": {"type": tw_type, "month": t_label, "start_date": d_start, "end_date": d_end},
        "filters": {"series": args.series, "model": args.model},
        "metric_definition": "ATP = mean(invoice_amount) WHERE order_type='用户车' AND invoice_amount > 0",
    }
    result = {
        "summary": f"ATP 月报 {t_label}: total_amount={total_amount:,.0f}, vehicle_count={vehicle_count}, avg_atp={avg_atp}",
        "metrics": {"total_amount": total_amount, "vehicle_count": vehicle_count, "avg_atp": avg_atp},
        "dimensions": [{"name": "series", "items": dim_items}],
    }
    artifacts = {}
    out_dir = Path(args.output) if args.output else _WS_ROOT / "outputs" / "tables"
    html_path = None
    if args.format in ("csv", "html") or args.output:
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.format == "html":
            html_path = out_dir / f"atp_{t_label}.html"
            artifacts["html"] = str(html_path)

    ctx = {"metric": "atp_price", "month": t_label, "start_date": d_start, "end_date": d_end,
           "available_dimensions": ["series", "product_name"],
           "top_entities": dim_items[:5] if dim_items else []}

    contract = build_success_contract(
        script="mashang_workspace/runtime_scripts/atp_price_report.py", command=cmd,
        scope=scope, result=result, artifacts=artifacts, followup_context=ctx,
    )

    if args.format in ("terminal", "html") or (args.format == "json" and args.output):
        _print_legacy(t_label, dim_items, vehicle_count, avg_atp)

    if args.format == "html" and html_path is not None:
        try:
            _render_html(html_path, t_label, t_start, t_end, dim_items)
        except Exception as e:
            print(f"  HTML render failed: {e}", file=sys.stderr)

    if args.format == "json":
        if args.output:
            save_contract_json(contract, out_dir / f"atp_{t_label}.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))


def _print_legacy(month: str, items: list, total_orders: int, avg_atp: float):
    print(f"报告月份: {month}")
    print()
    labels = ["系别", "用户车锁单", "ATP", "累计用户车锁单", "累计ATP"]
    header = "  ".join(f"{l:>{w}}" for l, w in zip(labels, [30, 10, 10, 14, 10]))
    print(header)
    print("-" * len(header))
    for item in items:
        m = item["metrics"]
        m_ps = f"¥{m['avg_atp']:>,.0f}" if m["avg_atp"] is not None else "N/A"
        y_ps = f"¥{m['ytd_avg_atp']:>,.0f}" if m["ytd_avg_atp"] is not None else "N/A"
        print(f"{item['value']:30s} {m['vehicle_count']:>8d} {m_ps:>10s} {m['ytd_vehicle_count']:>10d} {y_ps:>10s}")
    print()


def _render_html(html_path: Path, t_label: str, t_start: datetime, t_end: datetime, items: list):
    start_display = t_start.strftime("%Y-%m-%d")
    end_display = t_end.strftime("%Y-%m-%d")
    bg_map = {"all": "#ffffff", "suv": "#f0f7ff", "sedan": "#fff8f0"}
    tbody = ""
    for item in items:
        bg = bg_map.get(item.get("group", "all"), "#ffffff")
        m = item["metrics"]
        m_ps = f"¥{m['avg_atp']:>,.0f}" if m["avg_atp"] is not None else "N/A"
        y_ps = f"¥{m['ytd_avg_atp']:>,.0f}" if m["ytd_avg_atp"] is not None else "N/A"
        tbody += (
            f"        <tr>"
            f"<td style=\"text-align:left;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};\">{item['value']}</td>"
            f"<td style=\"text-align:right;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};color:#888;\">{m['vehicle_count']:,}</td>"
            f"<td style=\"text-align:right;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};\">{m_ps}</td>"
            f"<td style=\"text-align:right;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};color:#888;\">{m['ytd_vehicle_count']:,}</td>"
            f"<td style=\"text-align:right;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};\">{y_ps}</td>"
            f"</tr>\n"
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ATP 月报 {t_label}</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:24px;">
<h2 style="margin:0 0 8px 0;">ATP 月报 — {t_label}</h2>
<p style="margin:0 0 4px 0;color:#555;font-size:14px;">月份窗口: {start_display} ~ {end_display}</p>
<p style="margin:0 0 16px 0;color:#555;font-size:14px;">累计窗口: {t_start.year}年1月~{t_start.month}月（{t_start.year}-01-01 ~ {end_display}）</p>
<table style="border-collapse:collapse;font-size:14px;width:auto;">
<thead>
<tr style="background:#1f2a3a;color:#fff;">
<th style="text-align:left;padding:8px 12px;border:1px solid #1f2a3a;">系别</th>
<th style="text-align:right;padding:8px 12px;border:1px solid #1f2a3a;color:#ccc;">用户车锁单</th>
<th style="text-align:right;padding:8px 12px;border:1px solid #1f2a3a;">ATP</th>
<th style="text-align:right;padding:8px 12px;border:1px solid #1f2a3a;color:#ccc;">累计用户车锁单</th>
<th style="text-align:right;padding:8px 12px;border:1px solid #1f2a3a;">累计ATP</th>
</tr>
</thead>
<tbody>
{tbody}</tbody>
</table>
</body></html>"""
    html_path.write_text(html, encoding="utf-8")
    print(f"  HTML: {html_path.resolve()}")


if __name__ == "__main__":
    main()
