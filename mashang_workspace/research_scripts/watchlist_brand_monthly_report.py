#!/usr/bin/env python3
"""
2026 起每月复用的 watchlist 品牌销量月报生成脚本。

基于 dataset/TP&MIX-ways（乘用车上险数据）的 brand_monthly 表，按
MIIT/workflow/brand_watchlist.yaml 的品牌分类，对齐本品（智己）与行业整体
benchmark，输出各品牌销量环比/同比及相对行业的跑赢/跑输标注。

用法:
    python mashang_workspace/research_scripts/watchlist_brand_monthly_report.py
    python mashang_workspace/research_scripts/watchlist_brand_monthly_report.py --month 2026-07
    python mashang_workspace/research_scripts/watchlist_brand_monthly_report.py --format csv
    python mashang_workspace/research_scripts/watchlist_brand_monthly_report.py --output outputs/tables

依赖:
    - shared/loaders/tp_and_mix_ways_loader   (TP&MIX-ways 数据)
    - utils/brand_mapping                      (watchlist 品牌名 → 数据集品牌值)

输出:
    outputs/reports/watchlist_brand_sales_{month}.html
    outputs/tables/watchlist_brand_sales_{month}.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import yaml
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WS_ROOT = ROOT / "mashang_workspace"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WS_ROOT))

from utils.brand_mapping import normalize_watchlist_brands
from shared.loaders.tp_and_mix_ways_loader import load_tp_and_mix_ways_table

WATCHLIST_PATH = ROOT / "MIIT" / "workflow" / "brand_watchlist.yaml"
DEFAULT_OWN_BRAND = "智己"


def month_range(month: str) -> dict:
    """由报告月份推导 环比/同比 三个月份。"""
    cur = pd.Timestamp(month + "-01")
    prev = cur - pd.DateOffset(months=1)
    yoy = cur - pd.DateOffset(years=1)
    return {
        "cur": cur.strftime("%Y-%m-01"),
        "prev": prev.strftime("%Y-%m-01"),
        "yoy": yoy.strftime("%Y-%m-01"),
    }


def fmt_pct(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:+.1f}%"


def run_mark(v: float | None, bench: float) -> str:
    if v is None:
        return ""
    return "run" if v > bench else "fail"


def load_brand_sales() -> pd.DataFrame:
    """brand × month 销量，按 grain 聚合（brand_monthly 存在重复 grain，须 sum）。"""
    df = load_tp_and_mix_ways_table("brand_monthly")
    assert df is not None, "brand_monthly 未构建"
    return (
        df.groupby(["brand", "date_month"], as_index=False)["sales"].sum()
    )


def load_market(months: dict) -> dict:
    """大盘销量（market_energy_monthly 全燃料合计）。"""
    df = load_tp_and_mix_ways_table("market_energy_monthly")
    assert df is not None, "market_energy_monthly 未构建"
    df = df[df.date_month.isin(set(months.values()))]
    m = df.groupby("date_month")["sales"].sum().to_dict()
    return {k: int(m.get(v, 0)) for k, v in months.items()}


def note_for(r: dict, attribution_map: dict) -> str:
    """备注规则：月报层不感知归因逻辑，只读 attribution contract 的 summary。

    本品由 driver 无条件归因；其他品牌仅 |环比|≥阈值 时 driver 会生成归因。
    无数据 / 新品牌 走固定文案。
    """
    if r["cur"] is None:
        return "数据集无此品牌"
    if r["yoy"] == 0:
        return "新品牌爬坡"
    return attribution_map.get(r["brand"], {}).get("summary", "")


def build_rows(brand_df: pd.DataFrame, months: dict, attribution_map: dict,
               own_brand: str = DEFAULT_OWN_BRAND) -> tuple[list[dict], dict]:
    watchlist = yaml.safe_load(WATCHLIST_PATH.read_text(encoding="utf-8"))
    norm = normalize_watchlist_brands(watchlist)
    sub = brand_df[brand_df.date_month.isin(set(months.values()))]
    piv = sub.pivot_table(index="brand", columns="date_month", values="sales", aggfunc="sum")

    def calc(brand: str) -> dict:
        if brand not in piv.index:
            return {"brand": brand, "cur": None, "prev": None, "yoy": None,
                    "mom": None, "yoy_pct": None}
        cur = int(piv.loc[brand, months["cur"]])
        prev = int(piv.loc[brand, months["prev"]])
        yoy_raw = piv.loc[brand, months["yoy"]]
        yoy = int(yoy_raw) if pd.notna(yoy_raw) else 0
        return {
            "brand": brand,
            "cur": cur,
            "prev": prev,
            "yoy": yoy,
            "mom": (cur - prev) / prev * 100 if prev else None,
            "yoy_pct": (cur - yoy) / yoy * 100 if yoy else None,
        }

    rows = []
    for group, brands in norm.items():
        for b in brands:
            r = calc(b)
            r["group"] = group
            r["note"] = note_for(r, attribution_map)
            rows.append(r)

    own = calc(own_brand)
    own["group"] = f"本品 · {own_brand}"
    own["note"] = attribution_map.get(own_brand, {}).get("summary", "")
    return rows, own


def write_csv(rows: list[dict], own: dict, path: Path, bench_mom: float, bench_yoy: float) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["分组", "品牌", "报告月销量", "上月销量", "去年同期销量",
                    "环比%", "同比%", "环比vs行业", "同比vs行业", "备注"])
        for r in [own] + rows:
            w.writerow([r["group"], r["brand"],
                        r["cur"] if r["cur"] is not None else "",
                        r["prev"] if r["prev"] is not None else "",
                        r["yoy"] if r["yoy"] is not None else "",
                        fmt_pct(r["mom"]), fmt_pct(r["yoy_pct"]),
                        run_mark(r["mom"], bench_mom), run_mark(r["yoy_pct"], bench_yoy),
                        r["note"]])


def vs_cell(mom, yoy_pct, bench_mom, bench_yoy) -> str:
    parts = []
    if mom is not None:
        m = run_mark(mom, bench_mom)
        parts.append(f'<span class="badge badge-{m}">环比{"跑赢" if m=="run" else "跑输"}</span>')
    if yoy_pct is not None:
        m = run_mark(yoy_pct, bench_yoy)
        parts.append(f'<span class="badge badge-{m}">同比{"跑赢" if m=="run" else "跑输"}</span>')
    return "<br>".join(parts)


def group_rows(items, bench_mom, bench_yoy, own_brand: str) -> str:
    body = []
    for r in items:
        if r["cur"] is None:
            body.append(
                f'<tr><td class="label">{r["brand"]}</td>'
                f'<td class="num" style="color:var(--zh-muted)">—</td>'
                f'<td class="num" style="color:var(--zh-muted)">—</td>'
                f'<td class="num" style="color:var(--zh-muted)">—</td>'
                f'<td style="color:var(--zh-muted)">—</td>'
                f'<td><span class="badge badge-muted">{r["note"]}</span></td></tr>')
            continue
        own = ('<span class="badge badge-key">本品</span> '
               if r["brand"] == own_brand else "")
        if r["note"] == "新品牌爬坡":
            note = f'<span class="badge badge-gold">{r["note"]}</span>'
        elif r["note"]:
            note = f'<span style="color:var(--zh-muted);font-size:12px">{r["note"]}</span>'
        else:
            note = ""
        mom_cls = "delta-positive" if (r["mom"] or 0) >= 0 else "delta-negative"
        yoy_cls = "delta-positive" if (r["yoy_pct"] or 0) >= 0 else "delta-negative"
        body.append(
            f'<tr><td class="label">{own}{r["brand"]}</td>'
            f'<td class="num">{r["cur"]:,}</td>'
            f'<td class="num {mom_cls}">{fmt_pct(r["mom"])}</td>'
            f'<td class="num {yoy_cls}">{fmt_pct(r["yoy_pct"])}</td>'
            f'<td>{vs_cell(r["mom"], r["yoy_pct"], bench_mom, bench_yoy)}</td>'
            f'<td>{note}</td></tr>')
    return "\n".join(body)


def build_html(rows, own, market, bench_mom, bench_yoy, month_label: str) -> str:
    groups = {}
    for r in rows:
        groups.setdefault(r["group"], []).append(r)
    ordered = [(own["group"], [own])] + [(g, items) for g, items in groups.items()]

    wl_total = sum(r["cur"] for r in rows if r["cur"] is not None)
    wl_count = sum(1 for r in rows if r["cur"] is not None)
    up_mom = sum(1 for r in rows if r["mom"] is not None and r["mom"] > bench_mom)
    up_yoy = sum(1 for r in rows if r["yoy_pct"] is not None and r["yoy_pct"] > bench_yoy)
    n_yoy = sum(1 for r in rows if r["yoy_pct"] is not None)
    n_neg = sum(1 for r in rows if r["mom"] is not None and r["mom"] < 0)

    if own["mom"] is None or own["yoy_pct"] is None:
        own_tag = "本品销量待查"
    elif own["mom"] <= bench_mom and own["yoy_pct"] <= bench_yoy:
        own_tag = "双指标跑输行业"
    elif own["mom"] > bench_mom and own["yoy_pct"] > bench_yoy:
        own_tag = "双指标跑赢行业"
    else:
        own_tag = (f"环比{'跑赢' if own['mom'] > bench_mom else '跑输'} · "
                   f"同比{'跑赢' if own['yoy_pct'] > bench_yoy else '跑输'}")

    summary = [
        (f"{market['cur']:,}", f"{month_label} 乘用车总销量（行业整体）",
         f"环比 {fmt_pct(bench_mom)} · 同比 {fmt_pct(bench_yoy)}"),
        (f"{own['cur']:,}", f"本品 {own['brand']} · {own_tag}",
         f"环比 {fmt_pct(own['mom'])}（行业 {fmt_pct(bench_mom)}）· "
         f"同比 {fmt_pct(own['yoy_pct'])}（行业 {fmt_pct(bench_yoy)}）"),
        (f"{n_neg}/{wl_count}", "watchlist 品牌环比负增长",
         f"{wl_count} 个有数据品牌中 {n_neg} 个环比下滑"),
        (f"{up_mom}/{wl_count}", "环比跑赢行业",
         f"跑赢 = 环比优于行业（{fmt_pct(bench_mom)}）· 同比跑赢 {up_yoy}/{n_yoy}"),
    ]
    summary_cards = "".join(
        f'<div class="summary-card"><div class="summary-value">{v}</div>'
        f'<div class="summary-label">{l}</div><div class="summary-hint">{h}</div></div>'
        for v, l, h in summary)

    sections = []
    for g, items in ordered:
        total = sum(i["cur"] for i in items if i["cur"] is not None)
        up = [i["brand"] for i in items if i["mom"] is not None and i["mom"] > bench_mom]
        up_str = "、".join(up) if up else "无"
        bench_row = (
            '<tr class="bench-row"><td class="label">行业整体</td>'
            f'<td class="num">{market["cur"]:,}</td>'
            f'<td class="num delta-negative">{fmt_pct(bench_mom)}</td>'
            f'<td class="num delta-negative">{fmt_pct(bench_yoy)}</td>'
            '<td class="bench-mark">benchmark</td><td></td></tr>')
        sections.append(f"""
<div class="report-section">
  <h2 class="section-title">{g}
    <span class="badge badge-muted">合计 {total:,}</span>
    <span class="badge badge-blue">环比跑赢行业: {up_str}</span>
  </h2>
  <div class="table-wrap"><table class="report-table">
    <thead><tr><th>品牌</th><th>{month_label} 销量</th><th>环比上月</th><th>同比去年</th><th>vs 行业整体</th><th>备注</th></tr></thead>
    <tbody>
{bench_row}
{group_rows(items, bench_mom, bench_yoy, own["brand"])}
    </tbody>
  </table></div>
</div>""")

    insights = f"""
<div class="report-section">
  <h2 class="section-title">洞察</h2>
  <div class="scope-box"><ul style="margin:0;padding-left:18px;color:var(--zh-text);font-size:13.5px;line-height:2.0;">
    <li><b>本品 {own['brand']}</b>：{month_label} {own['cur']:,} 台，环比 {fmt_pct(own['mom'])}、同比 {fmt_pct(own['yoy_pct'])}，
      相对行业（环比 {fmt_pct(bench_mom)} / 同比 {fmt_pct(bench_yoy)}）<b>{own_tag}</b>。</li>
    <li><b>大盘与整体走势</b>：{month_label} 全市场 {market['cur']:,} 台，环比 {fmt_pct(bench_mom)}、同比 {fmt_pct(bench_yoy)}；
      watchlist {wl_count} 个有数据品牌中 <span class="delta-negative">{n_neg} 个环比负增长</span>，
      环比跑赢行业 {up_mom}/{wl_count}、同比跑赢行业 {up_yoy}/{n_yoy}。</li>
    <li>跑赢代表与跑输代表由下表 vs 行业整体列标注，可结合新品放量（环比高增）与品牌生命周期综合判断。</li>
  </ul></div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{month_label} 乘用车市场 · watchlist 品牌销量月报（本品对标）</title>
<link rel="stylesheet" href="../../templates/report_style.css">
<style>
  .report-page {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }}
  .report-section {{ margin-bottom: 28px; }}
  .scope-box {{ background: var(--zh-panel); border: 1px solid var(--zh-border); border-radius: 12px; padding: 16px 20px; }}
  .table-wrap {{ overflow-x: auto; }}
  td.label {{ font-weight: 600; color: var(--zh-text); }}
  tr.bench-row td {{ background: #EEF2F6; color: var(--zh-muted); }}
  td.bench-mark {{ font-size: 11px; color: var(--zh-muted); letter-spacing: .05em; }}
  .badge-run {{ color:#2A9D8F; border:1px solid rgba(42,157,143,.45); background:rgba(42,157,143,.08); border-radius:4px; padding:1px 6px; font-size:11px; white-space:nowrap; }}
  .badge-fail {{ color:#D95F59; border:1px solid rgba(217,95,89,.45); background:rgba(217,95,89,.08); border-radius:4px; padding:1px 6px; font-size:11px; white-space:nowrap; }}
</style>
</head>
<body class="report-page">
<div class="report-container">

<h1 class="report-title">{month_label} 乘用车市场 · watchlist 品牌销量月报</h1>
<p class="report-subtitle">
  环比 / 同比窗口按报告月自动推导 · 行业整体为 benchmark · 品牌经 brand_alias_map.yaml 归一化到数据集品牌值
</p>

<div class="report-section">
  <div class="summary-grid">{summary_cards}</div>
</div>

{"".join(sections)}

{insights}

<div class="report-section">
  <h2 class="section-title">口径说明</h2>
  <div class="scope-box"><ul style="margin:0;padding-left:18px;color:var(--zh-muted);font-size:13px;line-height:1.9;">
    <li>数据源：dataset/TP&MIX-ways/parquet/brand_monthly.parquet、market_energy_monthly.parquet（经 shared/loaders/tp_and_mix_ways_loader 读取）</li>
    <li>时间窗口：报告月 / 上月 / 去年同期（如 2026-07 → 2026-06 / 2025-07）</li>
    <li>指标口径：品牌维度销量合计（sales，含全燃料类型）；benchmark = 行业整体环比/同比；跑赢 = 品牌指标优于行业整体</li>
    <li>品牌映射：utils/brand_mapping.py + configs/brand_alias_map.yaml（问界→AITO、爱咖→iCAR）</li>
    <li>"新品牌" = 去年同期无上险数据，备注显示"新品牌爬坡"；"数据集无此品牌" = 数据集中无对应值</li>
    <li>归因备注：消费 driver 输出的 attribution contract（outputs/tables/watchlist_brand_attribution_&lt;报告月&gt;.json）的 summary 字段；本品始终归因，其他品牌 |环比| ≥ 20% 归因</li>
  </ul></div>
</div>

</div>
</body>
</html>"""


def default_month() -> str:
    now = datetime.now()
    first = date(now.year, now.month, 1)
    prev = first - timedelta(days=1)
    return f"{prev.year}-{prev.month:02d}"


def load_attribution_map(tables_dir: Path, month: str) -> dict:
    """读取 driver 输出的 attribution contract（品牌 -> summary）。缺失则空。"""
    p = tables_dir / f"watchlist_brand_attribution_{month}.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("attributions", {})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="watchlist 品牌销量月报（本品对标 + 行业 benchmark）")
    parser.add_argument("--month", default=default_month(),
                        help="报告月份 YYYY-MM（默认上月）")
    parser.add_argument("--own-brand", default=DEFAULT_OWN_BRAND, help="本品品牌（默认智己）")
    parser.add_argument("--format", choices=["html", "csv", "all"], default="all")
    parser.add_argument("--output", default="outputs", help="输出目录（workspace 下，默认 outputs）")
    args = parser.parse_args(argv)

    months = month_range(args.month)
    brand_df = load_brand_sales()
    market = load_market(months)
    bench_mom = (market["cur"] - market["prev"]) / market["prev"] * 100 if market["prev"] else 0.0
    bench_yoy = (market["cur"] - market["yoy"]) / market["yoy"] * 100 if market["yoy"] else 0.0

    month_label = f"{int(args.month[:4])}年{int(args.month[5:7])}月"
    reports_dir = WS_ROOT / args.output / "reports"
    tables_dir = WS_ROOT / args.output / "tables"
    reports_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    # 备注消费层：只读 attribution contract 的 summary，不感知归因逻辑
    attribution_map = load_attribution_map(tables_dir, args.month)
    rows, own = build_rows(brand_df, months, attribution_map, args.own_brand)

    if args.format in ("html", "all"):
        out_html = reports_dir / f"watchlist_brand_sales_{args.month}.html"
        out_html.write_text(build_html(rows, own, market, bench_mom, bench_yoy, month_label),
                            encoding="utf-8")
        print(f"[HTML] {out_html}")
    if args.format in ("csv", "all"):
        out_csv = tables_dir / f"watchlist_brand_sales_{args.month}.csv"
        write_csv(rows, own, out_csv, bench_mom, bench_yoy)
        print(f"[CSV ] {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
