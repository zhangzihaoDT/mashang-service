#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集团订单上市对比（智己L6 / MG 07 / 大众ID.ERA 5S）— 独立脚本。

从 launch_cumulative_lock_compare.py 模块 6 抽取独立成脚本：
上市后第 1..N 日每日 + 累计订单对比（观星台集团订单日报「重点车型(订单)」口径）。

- 数据源 = outputs/tables/重点车型（订单）.csv（saic_group_order_daily_parse.py 重刷的全历史快照合并，
  跨快照重叠日取最新快照值）；命名归一复用 model_order_monthly_compare_report.NAME2CANON。
- t0（各车上市基准日）：智己L6 = 2026-08-28（业务定义 DM2 上市日）；MG 07 / 大众ID.ERA 5S = 2026-08-21（用户近似对齐基准）。
- 口径为全渠道国内订单（含门店/预售/试驾锁定等全量进单），非内部零售锁单（order_data）；勿与内部零售口径直接横比。

用法：
  python research_scripts/group_order_launch_compare.py                # terminal
  python research_scripts/group_order_launch_compare.py --html         # HTML 报告
  python research_scripts/group_order_launch_compare.py --format json --output outputs/tables/
  python research_scripts/group_order_launch_compare.py --models "MG 07"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = REPO_ROOT / "mashang_workspace"
for p in (str(REPO_ROOT), str(_WS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from research_scripts.model_order_monthly_compare_report import NAME2CANON  # noqa: E402
from utils.plotly_theme import get_series_color  # noqa: E402

_GROUP_ORDER_CSV = _WS / "outputs" / "tables" / "重点车型（订单）.csv"
_DEFAULT_REPORT = _WS / "outputs" / "reports"
_DEFAULT_TABLE = _WS / "outputs" / "tables"

GROUP_ORDER_MODELS = [
    {"model": "智己L6", "t0": "2026-08-28", "label": "智己L6（上市 08-28）"},
    {"model": "MG 07", "t0": "2026-08-21", "label": "MG 07（以 08-21 对齐）"},
    {"model": "大众ID.ERA 5S", "t0": "2026-08-21", "label": "大众ID.ERA 5S（以 08-21 对齐）"},
]


def _fmt_int(v) -> str:
    return f"{int(round(float(v))):,}"


def load_group_order_daily(order_csv: str | Path | None = None) -> pd.DataFrame:
    """读重刷后的观星台重点车型(订单)宽表 → 长表（主体/日期/订单值/快照日）。

    命名先用 NAME2CANON 归一（与 model_order_monthly_compare_report 一致：智己L6/L6、
    大众ID.ERA 5S 空格变体等）；跨快照重叠日取最新快照值。
    """
    path = Path(order_csv) if order_csv else _GROUP_ORDER_CSV
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["主体"] = df["主体"].map(lambda x: NAME2CANON.get(x, x))
    daily_cols = [c for c in df.columns if c.startswith("每日_")]
    rows = []
    for _, r in df.iterrows():
        snap_year = str(r["数据日期"])[:4]
        for c in daily_cols:
            if pd.notna(r[c]):
                md = c.split("_")[1]
                m, dd = md.split("/")
                rows.append({
                    "主体": r["主体"],
                    "日期": f"{snap_year}-{int(m):02d}-{int(dd):02d}",
                    "订单": r[c],
                    "快照": str(r["数据日期"]),
                })
    long = pd.DataFrame(rows)
    if long.empty:
        return long
    long = long.sort_values("快照").groupby(["主体", "日期"], as_index=False).last()
    return long


def compute_group_order_launch(
    order_csv: str | Path | None = None,
    models: list[str] | None = None,
    as_of: str | None = None,
) -> dict | None:
    """集团订单上市对比：CAR 上市后第 1..N 日每日及累计订单。

    口径：观星台「重点车型(订单)」国内订单（含渠道/预售/试驾全量，非零售锁单，全代际汇总）；
    t0 内置（智己L6 = DM2 上市日；MG 07 / 大众ID.ERA 5S = 用户近似对齐基准）。
    返回与 launch_cumulative_lock_compare 模块 6 相同结构；数据不足返回 None。
    """
    long = load_group_order_daily(order_csv)
    if long.empty:
        return None
    specs = [s for s in GROUP_ORDER_MODELS
             if not models or s["model"] in models]
    if not specs:
        return None
    out = {"data_source": "观星台集团订单日报·重点车型(订单)", "models": []}
    for spec in specs:
        m = spec["model"]
        sub = long[long["主体"].eq(m)].copy()
        if sub.empty:
            continue
        sub["日期"] = pd.to_datetime(sub["日期"])
        t0 = pd.Timestamp(spec["t0"])
        end = sub["日期"].max()
        if as_of:
            end = min(end, pd.Timestamp(as_of))
        full = pd.date_range(t0, end, freq="D")
        s = sub.groupby("日期")["订单"].sum().reindex(full).fillna(0)
        daily = [int(v) for v in s]
        cum = []
        acc = 0
        for v in daily:
            acc += v
            cum.append(acc)
        out["models"].append({
            "model": m,
            "t0": spec["t0"],
            "label": spec["label"],
            "dates": [d.date().isoformat() for d in full],
            "day_offset": [i + 1 for i in range(len(full))],
            "daily": daily,
            "cum": cum,
            "latest_date": end.date().isoformat(),
        })
    return out


def render_group_order_table(gc: dict | None) -> str:
    """上市对比卡片片段（供本脚本独立报告与 launch_cumulative_lock_compare 复用）。"""
    if not gc or not gc.get("models"):
        return ""
    model_names = [m["model"] for m in gc["models"]]
    common_n = min(len(m["day_offset"]) for m in gc["models"])
    blocks = []
    for m in gc["models"]:
        rows = "".join(
            f"<tr><td class='num'>{t}</td><td class='num'>{d[5:]}</td>"
            f"<td class='num'>{int(m['daily'][t - 1]):,}</td>"
            f"<td class='num'><strong>{int(m['cum'][t - 1]):,}</strong></td></tr>"
            for t, d in zip(m["day_offset"], m["dates"])
        )
        blocks.append(f"""
        <h3 style="margin-top:18px;">{m['model']} <span class="text-muted" style="font-weight:400;font-size:0.9em;">— {m['label']}，t0 = {m['t0']}，数据至 {m['latest_date']}</span></h3>
        <div class="table-wrap">
        <table class="report-table">
          <thead><tr><th>上市后第 t 日</th><th>日期</th><th>每日订单</th><th>累计订单</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        </div>""")
    return f"""
    <div class="card">
      <h2>集团订单上市对比：{ ' / '.join(model_names) }（上市后 N 日 · 每日 + 累计订单）</h2>
      <p class="section-note">数据源 = 观星台集团订单日报「重点车型(订单)」国内订单（重刷至最新快照 {gc['models'][0]['latest_date']}）；口径为全渠道国内订单（含门店/预售/试驾锁定等全量进单）。第 1 日 = 各车 t0（上市基准日）：智己L6 = 2026-08-28（业务定义 DM2 上市日）；MG 07 / 大众ID.ERA 5S = 2026-08-21（近似对齐基准）。跨快照重叠日取最新快照值。<br/><br/><strong>口径对齐说明（集团 vs 内部 order_data）</strong>：集团「重点车型」为全代际 + 自预售试驾铺车即开始计 + 含试驾锁定等全量订单，与内部零售锁单（order_data，用户车口径）不同源。切勿直接横比——差异主要来自①全代际（含老款）②含预售试驾车铺车锁定③全渠道订单流 vs 零售锁单漏斗，而非数据口径缺陷。</p>
      <h3 style="margin-top:14px;">上市后累计订单收口对比（公共窗口：第 1..{common_n} 日）</h3>
      <div class="chart-box" id="chart-group-order-cum" style="height:440px;"></div>
      <div class="section-note">折线按各车型上市日 t0 对齐为第 1 天，仅展示公共窗口前 {common_n} 天（各车中数据覆盖最短者）；y = 上市以来累计订单。累计口径即下方每日订单逐日累加。</div>
      {''.join(blocks)}
    </div>"""


def render_group_order_chart_json(gc: dict | None) -> str | None:
    """上市累计订单收口对比 Plotly 图 JSON（公共窗口 = 各车型上市后第 1..common_n 日）。"""
    if not gc or not gc.get("models"):
        return None
    common_n = min(len(m["day_offset"]) for m in gc["models"])
    gdata = []
    for i, m in enumerate(gc["models"]):
        days = list(range(1, common_n + 1))
        cum = m["cum"][:common_n]
        dates = m["dates"][:common_n]
        role = "own" if i == 0 else "competitor"
        gdata.append({
            "x": days,
            "y": cum,
            "customdata": dates,
            "mode": "lines+markers",
            "name": m["model"],
            "line": {"width": 3.0 if i == 0 else 2.4,
                     "color": get_series_color("own") if i == 0 else get_series_color("competitor", i - 1),
                     "dash": None if i == 0 else ("dot" if i == 1 else "dash")},
            "marker": {"size": 5},
            "hovertemplate": f"<b>{m['model']}</b> · 上市后第 %{{x}} 天（%{{customdata}}）<br>累计订单 %{{y:,}} 单<extra></extra>",
        })
    return json.dumps({
        "data": gdata,
        "layout": {
            "title": {"text": f"上市后累计订单收口对比（第 1..{common_n} 日 · 集团订单口径）",
                      "x": 0.01, "xanchor": "left"},
            "xaxis": {"title": "上市后天数（第 1 天 = 各车上市日 t0）",
                      "range": [0.5, common_n + 0.5],
                      "tickmode": "array", "tickvals": list(range(1, common_n + 1))},
            "yaxis": {"title": "累计订单（单）", "rangemode": "tozero"},
            "legend": {"orientation": "h", "y": -0.25, "x": 0},
            "margin": {"l": 60, "r": 30, "t": 55, "b": 70},
            "height": 440,
        },
    }, ensure_ascii=False)


def render_html(gc: dict) -> str:
    models = gc["models"]
    common_n = min(len(m["day_offset"]) for m in models)
    latest_by = {m["model"]: m["cum"][-1] for m in models}
    top = max(latest_by, key=latest_by.get)
    fig_json = render_group_order_chart_json(gc)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>集团订单上市对比 · {' / '.join(latest_by)}</title>
<link rel="stylesheet" href="../../templates/report_style.css"/>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
</head>
<body>
<header>
  <div class="container">
    <div class="brand">
      <img class="brand-avatar" src="../../assets/brand/raccoon_avatar_light.png" alt=""/>
      <span class="brand-name">Raccoon Research</span>
    </div>
    <span class="header-meta">集团订单上市对比</span>
  </div>
</header>

<main class="container">
  <section class="hero">
    <h1>集团订单上市对比：{ ' / '.join(latest_by) }</h1>
    <p>各车上市日 t0 对齐为第 1 天，公共窗口前 {common_n} 日；数据源 = 观星台集团订单日报「重点车型(订单)」最新快照 {gc['models'][0]['latest_date']}。</p>
  </section>

  <div class="summary-grid">
    {''.join(
        f'<div class="summary-card"><div class="summary-value">{_fmt_int(m["cum"][-1])}</div>'
        f'<div class="summary-label">{m["model"]}</div><div class="summary-hint">上市 {m["cum"][-1] and len(m["day_offset"])} 天累计 · 至 {m["latest_date"]}</div></div>'
        for m in models)}
    <div class="summary-card"><div class="summary-value">{top}</div>
      <div class="summary-label">同窗口累计最高</div><div class="summary-hint">公共窗口 {common_n} 日</div></div>
  </div>

  {render_group_order_table(gc)}

  <div class="method-section">
    <h2 class="section-title">口径与数据来源</h2>
    <div class="method-grid">
      <div class="method-item"><div class="method-icon" style="background:var(--zh-blue-100);color:var(--zh-blue);">D</div>
        <div class="method-body"><strong>数据源</strong><br/>outputs/tables/重点车型（订单）.csv（saic_group_order_daily_parse.py 重刷）</div></div>
      <div class="method-item"><div class="method-icon" style="background:var(--zh-gold-100);color:var(--zh-gold-700);">T</div>
        <div class="method-body"><strong>时间窗口</strong><br/>各车上市日 t0 起第 1..N 日（公共窗口 {common_n} 日）</div></div>
      <div class="method-item"><div class="method-icon" style="background:#E8F8FD;color:#2D6FA3;">F</div>
        <div class="method-body"><strong>筛选口径</strong><br/>跨快照命名归一（NAME2CANON）+ 重叠日取最新快照</div></div>
      <div class="method-item"><div class="method-icon" style="background:#F3F6F8;color:#374151;">M</div>
        <div class="method-body"><strong>指标定义</strong><br/>每日订单 = 当日国内订单（全渠道）；累计 = t0 起逐日累加</div></div>
    </div>
  </div>
</main>

<footer>
  <img class="brand-sig" src="../../assets/brand/zihao_signature_transparent.png" alt="Raccoon Research"/>
  <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>

<script>
Plotly.newPlot('chart-group-order-cum', {fig_json});
</script>
</body>
</html>"""


def terminal(gc: dict) -> None:
    if not gc or not gc.get("models"):
        print("无集团订单数据（缺 outputs/tables/重点车型（订单）.csv）")
        return
    print(f"集团订单上市对比 · 数据至 {gc['models'][0]['latest_date']}")
    for m in gc["models"]:
        print(f"\n{m['model']}（t0 = {m['t0']}）")
        hdr = f"{'上市后天数':<8}{'日期':<12}{'每日订单':>10}{'累计订单':>12}"
        print(hdr)
        for t, d in zip(m["day_offset"], m["dates"]):
            print(f"{t:<8}{d:<12}{m['daily'][t - 1]:>10,}{m['cum'][t - 1]:>12,}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="集团订单上市对比（智己L6 / MG 07 / 大众ID.ERA 5S）")
    p.add_argument("--models", type=str, nargs="*", default=None,
                   help="限定车型（默认全部 GROUP_ORDER_MODELS，如 --models 'MG 07'）")
    p.add_argument("--as-of", type=str, default=None, help="统计截止日 YYYY-MM-DD（默认最新快照覆盖末）")
    p.add_argument("--format", choices=["terminal", "json", "html"], default="terminal")
    p.add_argument("--output", type=str, default=None, help="HTML/JSON 输出目录")
    p.add_argument("--html", action="store_true", help="生成 HTML 报告（等价 --format html）")
    args = p.parse_args(argv)

    fmt = "html" if args.html else args.format
    gc = compute_group_order_launch(models=args.models, as_of=args.as_of)
    if gc is None:
        print("❌ 无集团订单数据（缺 outputs/tables/重点车型（订单）.csv 或指定车型无数据）")
        return 1

    if fmt == "terminal":
        terminal(gc)
        return 0

    out_dir = Path(args.output) if args.output else (
        _DEFAULT_TABLE if fmt == "json" else _DEFAULT_REPORT)
    out_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        contract = {
            "status": "success",
            "script": "research_scripts/group_order_launch_compare.py",
            "scope": {
                "data_source": "outputs/tables/重点车型（订单）.csv（saic_group_order_daily_parse.py 重刷）",
                "time_window": {m["model"]: {"t0": m["t0"], "end": m["latest_date"]}
                                for m in gc["models"]},
                "filters": {"models": [m["model"] for m in gc["models"]],
                            "snapshot": "跨快照重叠日取最新快照，命名 NAME2CANON 归一",
                            "metric_definition": "累计订单 = 上市日 t0 起每日国内订单逐日累加（全渠道含预售/试驾）"},
            },
            "result": {
                "summary": f"集团订单上市后累计订单对比 → {' / '.join(m['model'] for m in gc['models'])}",
                "metrics": {m["model"]: {"cum": m["cum"][-1], "daily_last": m["daily"][-1],
                                         "latest_date": m["latest_date"]}
                            for m in gc["models"]},
                "models": gc["models"],
            },
            "artifacts": {},
            "followup_context": {"metric": "group_order_launch_cum",
                                 "models": [m["model"] for m in gc["models"]],
                                 "available_dimensions": ["day", "model"]},
            "warnings": [],
            "errors": [],
        }
        out = out_dir / f"group_order_launch_compare.json"
        out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已输出: {out}")
        return 0

    out = out_dir / f"group_order_launch_compare_{gc['models'][0]['latest_date'].replace('-', '')}.html"
    out.write_text(render_html(gc), encoding="utf-8")
    print(f"✅ HTML 报告已生成: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())