#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ATP价格及用户车锁单数月报脚本
计算指定月份内，已锁单（lock_time 非空）且 order_type='用户车' 的各系别锁单数与 ATP（avg invoice_amount）
同时输出同年 1~N 月累计值

系别分组：
  - 所有车型
  - 已有车型（time_periods end < 目标年）
  - 当年新车型(含改款)（time_periods end >= 目标年）
  - SUV (LS6+LS7+LS8+LS9) + SUV 已有/新车型
  - LS6, LS7, LS8, LS9
  - Sedan (L6+L7) + Sedan 已有/新车型
  - L6, L7
"""

import sys
import argparse
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta
import json

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from operators.atp_analysis import run_atp_operator, apply_business_logic, _load_business_definition


def main():
    parser = argparse.ArgumentParser(description="ATP价格及锁单数月报")
    parser.add_argument("month", nargs="?", type=str, default=None, help="报告月份 YYYY-MM（默认前一个月）")
    parser.add_argument("--output", "-o", type=str, default=None, help="HTML 报告输出路径（默认 scripts/reports/atp_YYYY-MM.html）")
    args = parser.parse_args()

    if args.month:
        parts = args.month.split("-")
        year, month = int(parts[0]), int(parts[1])
        target_start = datetime(year, month, 1)
        target_end = datetime(year, month, 1) + timedelta(days=32)
        target_end = target_end.replace(day=1) - timedelta(days=1)
    else:
        today = datetime.now()
        target_end = today.replace(day=1) - timedelta(days=1)
        target_start = target_end.replace(day=1)

    start = target_start.strftime("%Y-%m-%d")
    start_display = start
    end_display = target_end.strftime("%Y-%m-%d")
    end = (target_end + timedelta(days=1)).strftime("%Y-%m-%d")

    ytd_start = f"{target_start.year}-01-01"
    ytd_end = end

    print(f"报告月份: {target_start.year}-{target_start.month:02d}")
    print(f"月份窗口: {start_display} ~ {end_display}")
    print(f"累计窗口: {ytd_start} ~ {end_display}")
    print()

    df = pd.read_parquet(str(REPO_ROOT / "dataset" / "order_data.parquet"))
    bdef = _load_business_definition()

    df_with_logic = apply_business_logic(df, bdef)

    time_periods = bdef.get("time_periods", {})
    target_year = target_start.year
    new_model_groups = set()
    old_model_groups = set()
    for group, period in time_periods.items():
        end_year = pd.to_datetime(period["end"]).year
        if end_year >= target_year:
            new_model_groups.add(group)
        else:
            old_model_groups.add(group)
    all_mapped_groups = new_model_groups | old_model_groups

    def _suv(d): return d[d["series_derived"].isin(["LS6", "LS7", "LS8", "LS9"])]
    def _sedan(d): return d[d["series_derived"].isin(["L6", "L7"])]
    def _old(d): return d[d["series_group_logic"].isin(old_model_groups) | ~d["series_group_logic"].isin(all_mapped_groups)]
    def _new(d): return d[d["series_group_logic"].isin(new_model_groups)]

    segments: list[tuple[str, object, str]] = [
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

    def get_metrics(seg_df, s, e):
        r = run_atp_operator(seg_df, s, e)
        return r.get("total_orders", 0), r.get("avg_price")

    rows = []
    for name, filter_fn, group in segments:
        seg_df = df_with_logic if filter_fn is None else filter_fn(df_with_logic.copy())
        m_orders, m_price = get_metrics(seg_df, start, end)
        y_orders, y_price = get_metrics(seg_df, ytd_start, ytd_end)
        rows.append({
            "seg": name,
            "group": group,
            "m_orders": m_orders,
            "m_price": m_price,
            "y_orders": y_orders,
            "y_price": y_price,
        })

    labels = ["系别", "用户车锁单", "ATP", "累计用户车锁单", "累计ATP"]
    col_widths = [30, 10, 10, 14, 10]
    header = "  ".join(f"{l:>{w}}" for l, w in zip(labels, [30, 10, 10, 14, 10]))
    print(header)
    print("-" * len(header))
    for r in rows:
        m_ps = f"¥{r['m_price']:>,.0f}" if r["m_price"] is not None else "N/A"
        y_ps = f"¥{r['y_price']:>,.0f}" if r["y_price"] is not None else "N/A"
        print(f"{r['seg']:30s} {r['m_orders']:>8d} {m_ps:>10s} {r['y_orders']:>10d} {y_ps:>10s}")

    month_label = f"{target_start.year}-{target_start.month:02d}"
    ytd_label = f"{target_start.year}年1~{target_start.month}月"
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = REPO_ROOT / "scripts" / "reports" / f"atp_{month_label}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    bg_map = {"all": "#ffffff", "suv": "#f0f7ff", "sedan": "#fff8f0"}
    tbody = ""
    for r in rows:
        bg = bg_map.get(r["group"], "#ffffff")
        m_ps = f"¥{r['m_price']:>,.0f}" if r["m_price"] is not None else "N/A"
        y_ps = f"¥{r['y_price']:>,.0f}" if r["y_price"] is not None else "N/A"
        tbody += (
            f"        <tr>"
            f"<td style=\"text-align:left;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};\">{r['seg']}</td>"
            f"<td style=\"text-align:right;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};color:#888;\">{r['m_orders']:,}</td>"
            f"<td style=\"text-align:right;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};\">{m_ps}</td>"
            f"<td style=\"text-align:right;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};color:#888;\">{r['y_orders']:,}</td>"
            f"<td style=\"text-align:right;padding:6px 12px;border:1px solid #d0d5dd;background:{bg};\">{y_ps}</td>"
            f"</tr>\n"
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ATP 月报 {month_label}</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:24px;">
<h2 style="margin:0 0 8px 0;">ATP 月报 — {month_label}</h2>
<p style="margin:0 0 4px 0;color:#555;font-size:14px;">月份窗口: {start_display} ~ {end_display}</p>
<p style="margin:0 0 16px 0;color:#555;font-size:14px;">累计窗口: {ytd_start[:4]}年1月~{target_start.month}月（{ytd_start[:4]}-01-01 ~ {end_display}）</p>
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

    out_path.write_text(html, encoding="utf-8")
    print(f"\nHTML 报告已保存: {out_path}")


if __name__ == "__main__":
    main()
