#!/usr/bin/env python3
"""
watchlist 异常品牌车型贡献拆解脚本。

识别 watchlist 中环比波动达到阈值的品牌（异常品牌），并拆解到车型层面，
看每个车型对本品牌环比变化的贡献，配合品牌月报做简单归因分析。

用法:
    python mashang_workspace/research_scripts/watchlist_brand_driver_decomposition.py
    python mashang_workspace/research_scripts/watchlist_brand_driver_decomposition.py --month 2026-07
    python mashang_workspace/research_scripts/watchlist_brand_driver_decomposition.py --threshold 0.15
    python mashang_workspace/research_scripts/watchlist_brand_driver_decomposition.py --brands 智界,特斯拉
    python mashang_workspace/research_scripts/watchlist_brand_driver_decomposition.py --format csv

输出:
    outputs/reports/watchlist_brand_driver_{month}.html
    outputs/tables/watchlist_brand_driver_{month}.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WS_ROOT = ROOT / "mashang_workspace"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WS_ROOT))

from utils.watchlist_brand_common import (
    DEFAULT_OWN_BRAND,
    fmt_pct,
    load_brand_sales,
    load_model_sales,
    load_watchlist,
    month_range,
    safe_int,
)

DEFAULT_THRESHOLD = 0.20


def default_month() -> str:
    now = datetime.now()
    prev = date(now.year, now.month, 1) - timedelta(days=1)
    return f"{prev.year}-{prev.month:02d}"


def find_anomaly_brands(brand_df: pd.DataFrame, months: dict,
                        threshold: float, only: list[str] | None,
                        own_brand: str = DEFAULT_OWN_BRAND) -> list[dict]:
    """识别需归因的 watchlist 品牌。

    规则：本品（own_brand）始终归因；其他品牌 |环比| ≥ threshold 才归因。
    返回 [{brand, cur, prev, mom, delta}]。
    """
    sub = brand_df[brand_df.date_month.isin({months["cur"], months["prev"]})]
    piv = sub.pivot_table(index="brand", columns="date_month", values="sales", aggfunc="sum")
    watch = load_watchlist()
    all_brands = [b for group in watch.values() for b in group]
    if own_brand not in all_brands:
        all_brands = all_brands + [own_brand]
    if only:
        all_brands = [b for b in all_brands if b in only]
    anomalies = []
    for b in all_brands:
        if b not in piv.index:
            continue
        cur = int(piv.loc[b, months["cur"]])
        prev = int(piv.loc[b, months["prev"]])
        mom = (cur - prev) / prev if prev else None
        if mom is not None and (b == own_brand or abs(mom) >= threshold):
            anomalies.append({"brand": b, "cur": cur, "prev": prev,
                              "delta": cur - prev, "mom": mom * 100})
    anomalies.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return anomalies


def decompose_brand(model_df: pd.DataFrame, months: dict, brand: str) -> list[dict]:
    """品牌车型环比拆解。返回 [{model, cur, prev, delta, mom, contribution}]。"""
    sub = model_df[(model_df.brand == brand)
                   & model_df.date_month.isin({months["cur"], months["prev"]})]
    piv = sub.pivot_table(index="model", columns="date_month", values="sales", aggfunc="sum")
    brand_cur = int(piv.loc[:, months["cur"]].sum())
    brand_prev = int(piv.loc[:, months["prev"]].sum())
    brand_delta = brand_cur - brand_prev
    rows = []
    for m in piv.index:
        cur = safe_int(piv.loc[m, months["cur"]])
        prev = safe_int(piv.loc[m, months["prev"]])
        delta = cur - prev
        mom = (cur - prev) / prev * 100 if prev else None
        contribution = (delta / abs(brand_delta) * 100) if brand_delta else None
        rows.append({"model": m, "cur": cur, "prev": prev, "delta": delta,
                     "mom": mom, "contribution": contribution})
    rows.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return rows


def build_attribution(a: dict, model_rows: list[dict], month: str) -> dict:
    """生成品牌归因 contract（供月报备注消费；月报不感知归因逻辑）。

    fields:
      brand / month / mom / direction / top_driver_model / top_driver_delta
      top_driver_contribution_pct / driver_pattern / summary
    """
    brand = a["brand"]
    mom = a["mom"] / 100
    direction = "growth" if mom >= 0 else "decline"
    if not model_rows:
        return {
            "brand": brand, "month": month, "mom": round(mom, 4),
            "direction": direction,
            "top_driver_model": None, "top_driver_delta": 0,
            "top_driver_contribution_pct": 0.0,
            "driver_pattern": "no_driver",
            "summary": "",
        }
    top = max(model_rows, key=lambda r: abs(r["delta"] or 0))
    top_cont = (top["contribution"] or 0) / 100  # 转小数，带符号
    pattern = "single_model_dominant" if abs(top_cont) >= 0.6 else "multi_driver"
    if pattern == "single_model_dominant":
        if direction == "growth":
            summary = f"{top['model']}贡献 +{abs(top_cont) * 100:.1f}%，为增长主因"
        else:
            summary = f"{top['model']}拖累 {abs(top_cont) * 100:.1f}%，为下滑主因"
    else:
        if direction == "growth":
            summary = f"多车型共同拉动（{top['model']}贡献 +{abs(top_cont) * 100:.1f}% 居首）"
        else:
            summary = f"多车型共同下滑（{top['model']}拖累 {abs(top_cont) * 100:.1f}% 居首）"
    return {
        "brand": brand,
        "month": month,
        "mom": round(mom, 4),
        "direction": direction,
        "top_driver_model": top["model"],
        "top_driver_delta": int(top["delta"]),
        "top_driver_contribution_pct": round(top_cont, 4),
        "driver_pattern": pattern,
        "summary": summary,
    }


def build_html(anomalies: list[dict], decomps: dict, months: dict,
               month_label: str, threshold: float, only: list[str] | None) -> str:
    cur_label = f"{int(months['cur'][:4])}年{int(months['cur'][5:7])}月"
    prev_label = f"{int(months['prev'][:4])}年{int(months['prev'][5:7])}月"

    if not anomalies:
        body = ('<div class="scope-box"><p style="margin:0;color:var(--zh-text)">'
                f'环比波动幅度达到阈值（|环比| ≥ {threshold:.0%}）的 watchlist 品牌：无。'
                '</p></div>')
    else:
        sections = []
        for a in anomalies:
            rows = decomps[a["brand"]]
            tr = []
            for r in rows:
                mom_cls = "delta-positive" if (r["mom"] or 0) >= 0 else "delta-negative"
                cont = (f'{r["contribution"]:+.1f}%' if r["contribution"] is not None else "—")
                cont_cls = "delta-positive" if (r["contribution"] or 0) >= 0 else "delta-negative"
                tr.append(
                    f'<tr><td class="label">{r["model"]}</td>'
                    f'<td class="num">{r["cur"]:,}</td>'
                    f'<td class="num">{r["prev"]:,}</td>'
                    f'<td class="num {mom_cls}">{fmt_pct(r["mom"])}</td>'
                    f'<td class="num {mom_cls}">{r["delta"]:+,}</td>'
                    f'<td class="num {cont_cls}">{cont}</td></tr>')
            sections.append(f"""
<div class="report-section">
  <h2 class="section-title">{a["brand"]} · 环比 {fmt_pct(a["mom"])}
    <span class="badge badge-muted">{a["cur"]:,} 台（上月 {a["prev"]:,}）</span>
    <span class="badge badge-gold">变化 {a["delta"]:+,} 台</span>
  </h2>
  <div class="table-wrap"><table class="report-table">
    <thead><tr><th>车型</th><th>{cur_label} 销量</th><th>{prev_label} 销量</th>
      <th>车型环比</th><th>变化量(台)</th><th>对品牌变化贡献</th></tr></thead>
    <tbody>{''.join(tr)}</tbody>
  </table></div>
</div>""")
        body = "".join(sections)

    scope = f'--brands {"、".join(only)}' if only else "watchlist 全量"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{month_label} watchlist 异常品牌 · 车型贡献拆解</title>
<link rel="stylesheet" href="../../templates/report_style.css">
<style>
  .report-page {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }}
  .report-section {{ margin-bottom: 28px; }}
  .scope-box {{ background: var(--zh-panel); border: 1px solid var(--zh-border); border-radius: 12px; padding: 16px 20px; }}
  .table-wrap {{ overflow-x: auto; }}
  td.label {{ font-weight: 600; color: var(--zh-text); }}
</style>
</head>
<body class="report-page">
<div class="report-container">

<h1 class="report-title">{month_label} watchlist 异常品牌 · 车型贡献拆解</h1>
<p class="report-subtitle">
  识别环比波动 ≥ {threshold:.0%} 的 watchlist 品牌并拆解到车型（{scope}）· 贡献 = 车型变化量 / 品牌变化量
</p>

{body}

<div class="report-section">
  <h2 class="section-title">口径说明</h2>
  <div class="scope-box"><ul style="margin:0;padding-left:18px;color:var(--zh-muted);font-size:13px;line-height:1.9;">
    <li>数据源：dataset/TP&MIX-ways/parquet/brand_monthly.parquet、model_monthly.parquet（经 shared/loaders/tp_and_mix_ways_loader 读取）</li>
    <li>时间窗口：{cur_label} 环比 {prev_label}（单月）</li>
    <li>异常判定：|环比| ≥ {threshold:.0%}（--threshold 可调，默认 0.20）；按 |变化量| 降序</li>
    <li>车型口径：model_monthly 的 model 维度（groupby-sum）；贡献% = 车型变化量 / 品牌变化量</li>
    <li>品牌映射：utils/brand_mapping.py + configs/brand_alias_map.yaml</li>
  </ul></div>
</div>

</div>
</body>
</html>"""


def write_csv(anomalies, decomps, months, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["品牌", "品牌本月销量", "品牌上月销量", "品牌环比%", "品牌变化量(台)",
                    "车型", "车型本月销量", "车型上月销量", "车型环比%", "车型变化量(台)", "对品牌变化贡献%"])
        for a in anomalies:
            rows = decomps[a["brand"]]
            for i, r in enumerate(rows):
                w.writerow([a["brand"] if i == 0 else "", a["cur"] if i == 0 else "",
                            a["prev"] if i == 0 else "", fmt_pct(a["mom"]) if i == 0 else "",
                            a["delta"] if i == 0 else "",
                            r["model"], r["cur"], r["prev"], fmt_pct(r["mom"]),
                            r["delta"], fmt_pct(r["contribution"])])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="watchlist 异常品牌车型贡献拆解（归因分析）")
    parser.add_argument("--month", default=default_month(), help="基准月 YYYY-MM（默认上月）")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="异常判定阈值 |环比|（默认 0.20）")
    parser.add_argument("--brands", default="", help="限定品牌，逗号分隔（默认 watchlist 全量）")
    parser.add_argument("--format", choices=["html", "csv", "all"], default="all")
    parser.add_argument("--output", default="outputs", help="输出目录（workspace 下，默认 outputs）")
    args = parser.parse_args(argv)

    months = month_range(args.month)
    only = [b.strip() for b in args.brands.split(",") if b.strip()] or None

    brand_df = load_brand_sales()
    anomalies = find_anomaly_brands(brand_df, months, args.threshold, only,
                                    DEFAULT_OWN_BRAND)

    model_df = load_model_sales()
    decomps = {a["brand"]: decompose_brand(model_df, months, a["brand"]) for a in anomalies}

    month_label = f"{int(args.month[:4])}年{int(args.month[5:7])}月"
    reports_dir = WS_ROOT / args.output / "reports"
    tables_dir = WS_ROOT / args.output / "tables"
    reports_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    # ── attribution contract（月报消费层只读 summary，不感知归因逻辑）──
    attributions = {
        a["brand"]: build_attribution(a, decomps[a["brand"]], args.month)
        for a in anomalies
    }
    out_json = tables_dir / f"watchlist_brand_attribution_{args.month}.json"
    out_json.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "month": args.month,
        "threshold": args.threshold,
        "own_brand": DEFAULT_OWN_BRAND,
        "attributions": attributions,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[JSON] {out_json}")

    if args.format in ("html", "all"):
        out_html = reports_dir / f"watchlist_brand_driver_{args.month}.html"
        out_html.write_text(build_html(anomalies, decomps, months, month_label,
                                       args.threshold, only), encoding="utf-8")
        print(f"[HTML] {out_html}")
    if args.format in ("csv", "all"):
        out_csv = tables_dir / f"watchlist_brand_driver_{args.month}.csv"
        write_csv(anomalies, decomps, months, out_csv)
        print(f"[CSV ] {out_csv}")
    print(f"异常品牌（|环比|≥{args.threshold:.0%}）: {len(anomalies)} 个 -> "
          + ", ".join(a["brand"] for a in anomalies) if anomalies else "无")
    return 0


if __name__ == "__main__":
    sys.exit(main())
