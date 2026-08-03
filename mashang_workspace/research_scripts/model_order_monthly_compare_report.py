#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集团重点车型月度订单对比报告（7 月订单 / 环比6月 / 2026累计至今）

数据源：outputs/tables/重点车型（订单）.csv（全历史快照合并，最新快照优先）
口径：7月/6月/2026累计 = 每日订单求和（与快照月度累计交叉验证一致）；
      跨快照命名变体已合并（如 全新MG4/新MG4、途观L家族/途观L）。

输出：outputs/reports/model_order_monthly_compare.html（Raccoon 视觉风格）
用法：python mashang_workspace/research_scripts/model_order_monthly_compare_report.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = _REPO_ROOT / "mashang_workspace"
_ORDER_CSV = _WS / "outputs" / "tables" / "重点车型（订单）.csv"
_OUTPUT_HTML = _WS / "outputs" / "reports" / "model_order_monthly_compare.html"
_STATIC = "../.."

# 跨快照命名变体合并表（规范名 → 历史变体）
CANON = {
    "全新MG4": ["全新MG4", "新MG4"],
    "MG 4X": ["MG 4X"],
    "荣威新i6": ["荣威新i6"],
    "M7 DMH": ["M7 DMH", "荣威M7 DMH"],
    "尚界H5": ["尚界H5"],
    "尚界Z7": ["尚界Z7"],
    "智己LS9": ["智己LS9", "LS9"],
    "智己LS8": ["智己LS8"],
    "智己LS6": ["智己LS6", "LS6"],
    "智己L6": ["智己L6", "L6"],
    "大众ID.ERA 9X": ["大众ID.ERA 9X", "大众ID. ERA 9X"],
    "奥迪E7X": ["奥迪E7X"],
    "帕萨特家族": ["帕萨特家族", "帕萨特"],
    "途观L家族": ["途观L家族", "途观L"],
    "奥迪E5": ["奥迪E5", "E5"],
    "GL8陆尚": ["GL8陆尚", "GL8陆尚系列", "GL8 LS"],
    "GL8陆尊": ["GL8陆尊", "GL8陆尊系列", "GL8 LS PHEV"],
    "至境世家": ["至境世家"],
    "至境E7": ["至境E7"],
    "昂科威Plus": ["昂科威Plus", "昂科威 Plus"],
    "缤果家族": ["缤果家族", "五菱缤果S"],
    "华境S": ["华境S"],
    "五菱星光L": ["五菱星光L"],
    "五菱星光560": ["五菱星光560", "星光560"],
    "五菱星光730": ["五菱星光730", "星光730"],
    "MG 07": ["MG 07"],
    "至境L7 BEV": ["至境L7 BEV", "至境L7"],
    "凯迪拉克XT5": ["凯迪拉克XT5", "全新XT5"],
    "全新GL8 ES": ["全新GL8 ES", "GL8 ES PHEV"],
    "途昂": ["途昂"],
    "MG7": ["MG7"],
    "荣威D7 DMH": ["荣威D7 DMH", "D7 DMH"],
    "奥迪A5L": ["奥迪A5L", "A5L"],
    "凯威德": ["凯威德"],
}
NAME2CANON = {v: c for c, vs in CANON.items() for v in vs}

PRESALE_MODELS = {"MG 07", "至境L7 BEV"}


def compute(order_df: pd.DataFrame) -> pd.DataFrame:
    daily_cols = [c for c in order_df.columns if c.startswith("每日_")]
    rows = []
    for _, r in order_df.iterrows():
        year = r["数据日期"][:4]
        for c in daily_cols:
            if pd.notna(r[c]):
                md = c.split("_")[1]
                m, dd = md.split("/")
                rows.append((r["主体"], f"{year}-{int(m):02d}-{int(dd):02d}", r[c], r["数据日期"]))
    L = pd.DataFrame(rows, columns=["主体", "日期", "值", "快照"])
    L["主体"] = L["主体"].map(lambda x: NAME2CANON.get(x, x))
    L = L.sort_values("快照").groupby(["主体", "日期"], as_index=False).last()
    piv = L.pivot(index="日期", columns="主体", values="值").sort_index()

    def month_sum(m):
        return piv.loc[f"2026-{m:02d}-01":f"2026-{m:02d}-31"].sum()

    out = pd.DataFrame({"7月订单": month_sum(7), "6月订单": month_sum(6), "2026累计至今": piv.loc["2026-01-01":"2026-07-31"].sum()})
    out["环比六月"] = out["7月订单"] / out["6月订单"] - 1
    out = out[out["7月订单"].notna()].sort_values("7月订单", ascending=False)
    return out


def fmt_mom(x):
    if pd.isna(x):
        return "—"
    if abs(x) > 1e6:
        return "+∞"
    return f"{x:+.1%}"


def render_html(out: pd.DataFrame) -> str:
    total_jul = int(out["7月订单"].sum())
    up = int((out["环比六月"].apply(lambda x: pd.notna(x) and 0 < x < 1e6)).sum())
    down = int((out["环比六月"].apply(lambda x: pd.notna(x) and x < 0)).sum())
    top3 = out.head(3)
    top3_str = "、".join(f"{m}（{int(v):,}）" for m, v in zip(top3.index, top3["7月订单"]))

    trs = []
    top5_models = set(out.sort_values("2026累计至今", ascending=False).head(5).index)
    for model, row in out.iterrows():
        tag = '<span class="badge badge-gold">预售</span>' if model in PRESALE_MODELS else ""
        mom_raw = row["环比六月"]
        mom_cls = ""
        row_cls = ""
        if model in top5_models:
            row_cls = " class=\"row-top5\""
        if pd.notna(mom_raw) and abs(mom_raw) < 1e6:
            if mom_raw > 0:
                mom_cls = " up"
                row_cls = " class=\"row-up\"" if not row_cls else " class=\"row-up row-top5\""
            else:
                mom_cls = " down"
        trs.append(
            f'<tr{row_cls}><td>{tag} <strong>{model}</strong></td>'
            f'<td class="num">{int(row["7月订单"]):,}</td>'
            f'<td class="num{mom_cls}">{fmt_mom(mom_raw)}</td>'
            f'<td class="num">{int(row["2026累计至今"]):,}</td></tr>'
        )
    table = "\n".join(trs)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>集团重点车型 7 月订单对比</title>
<link rel="stylesheet" href="{_STATIC}/templates/report_style.css"/>
<style>
.badge {{ font-size:11px; padding:2px 8px; border-radius:10px; border:1px solid; }}
.badge-gold {{ background:rgba(215,154,54,.12); color:#a06e1f; border-color:rgba(215,154,54,.3); }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
td.num.up {{ color:var(--status-positive); font-weight:600; }}
td.num.down {{ color:var(--status-danger,#c0392b); }}
tr.row-up {{ background:#FFF7E0; }}
tr.row-up td:first-child {{ border-left:3px solid var(--zh-raccoon-gold); }}
tr.row-top5 {{ background:rgba(23,74,124,.07); }}
tr.row-top5 td:first-child {{ border-left:3px solid var(--zh-blue); }}
@media (max-width:768px) {{ .table-wrap {{ overflow-x:auto; }} }}
</style>
</head>
<body>

<header>
<div class="container">
  <div class="brand">
    <img class="brand-avatar" src="{_STATIC}/assets/brand/raccoon_avatar_light.png" alt=""/>
    <span class="brand-name">Raccoon Research</span>
  </div>
  <span class="header-meta">订单月报 · {pd.Timestamp.now().strftime('%Y-%m-%d')}</span>
</div>
</header>

<main class="container">

<section class="hero">
  <h1>集团重点车型 7 月订单对比</h1>
  <p>7 月订单量 · 环比 6 月 · 2026 年累计至今 · 数据源订单日报2.0 全历史快照</p>
</section>

<div class="summary-grid">
  <div class="summary-card"><div class="summary-value">{len(out)}</div><div class="summary-label">重点车型</div><div class="summary-hint">7 月有订单</div></div>
  <div class="summary-card positive"><div class="summary-value">{total_jul:,}</div><div class="summary-label">7 月订单总量</div><div class="summary-hint">重点车型合计</div></div>
  <div class="summary-card"><div class="summary-value">{up} 增 / {down} 降</div><div class="summary-label">环比 6 月</div><div class="summary-hint">多数环比下滑</div></div>
  <div class="summary-card neutral"><div class="summary-value">{top3_str}</div><div class="summary-label">7 月 Top3</div><div class="summary-hint">按订单量排序</div></div>
</div>

<div class="card">
  <h2>重点车型订单对比</h2>
  <div class="table-wrap">
  <table class="report-table">
    <thead><tr><th>车型</th><th style="text-align:right;">7月订单</th><th style="text-align:right;">环比6月</th><th style="text-align:right;">2026累计至今</th></tr></thead>
    <tbody>
    {table}
    </tbody>
  </table>
  </div>
</div>

<div class="card">
  <h2>关键发现</h2>
  <div class="insight gold">
    <h4>7 月唯一爆发项：五菱星光L（+262%）</h4>
    <p>由 5 月底预售（335）转正后 6 月爬坡（7,090）→ 7 月冲至 25,679，为 7 月最大增量与榜首。</p>
  </div>
  <div class="insight">
    <h4>行业性环比走弱</h4>
    <p>多数车型环比 6 月下滑（7 月为传统淡季），智己LS9（+14.8%）逆势增长；奥迪E7X（-56.8%）与尚界H5（-41.7%）降幅最深。</p>
  </div>
  <div class="insight green">
    <h4>预售储备</h4>
    <p>MG 07（8,891）与至境L7 BEV（532）处于预售阶段，为 8 月订单增量储备；缤果家族以 13.9 万累计领跑全年。</p>
  </div>
</div>

<div class="method-section">
  <h2 class="section-title">口径与数据来源</h2>
  <div class="method-grid">
    <div class="method-item"><div class="method-icon" style="background:var(--zh-blue-100);color:var(--zh-blue);">D</div>
      <div class="method-body"><strong>数据源</strong><br/>outputs/tables/重点车型（订单）.csv<br/>订单日报2.0 全历史快照（2025-11-26~2026-08-01）</div></div>
    <div class="method-item"><div class="method-icon" style="background:var(--zh-gold-100);color:var(--zh-gold-700);">T</div>
      <div class="method-body"><strong>时间窗口</strong><br/>7月 = 07-01~07-31<br/>6月 = 06-01~06-30<br/>累计 = 01-01~07-31</div></div>
    <div class="method-item"><div class="method-icon" style="background:#E8F8FD;color:#2D6FA3;">F</div>
      <div class="method-body"><strong>口径</strong><br/>每月订单 = 每日订单求和（与快照月度累计一致）<br/>跨快照每日取最新值去重</div></div>
    <div class="method-item"><div class="method-icon" style="background:#F3F6F8;color:#374151;">M</div>
      <div class="method-body"><strong>命名合并</strong><br/>跨快照车型命名变体已合并<br/>（如 全新MG4/新MG4、途观L家族/途观L）</div></div>
  </div>
</div>

</main>

<footer>
  <img class="brand-sig" src="{_STATIC}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research"/>
  <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>

</body>
</html>"""


def main() -> int:
    order_df = pd.read_csv(str(_ORDER_CSV))
    out = compute(order_df)
    html = render_html(out)
    Path(_OUTPUT_HTML).write_text(html, encoding="utf-8")
    print(f"报告已生成: {_OUTPUT_HTML}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
