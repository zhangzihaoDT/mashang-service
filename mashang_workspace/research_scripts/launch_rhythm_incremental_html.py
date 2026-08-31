#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上市节奏增量贡献研究 — 品牌化 HTML 报告渲染
被 launch_rhythm_incremental_analysis.py --html 调用。

视觉体系：mashang_workspace/docs/report_visual_system.md（Raccoon Research）
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_STATIC = "../.."


def _fmt(v, nd: int = 1) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v * 100:.{nd}f}%"


def _bar(v: float | None, max_v: float, neg: bool = False) -> str:
    if v is None or pd.isna(v):
        return '<span class="barcell"><span class="txt">—</span></span>'
    ratio = max(0.0, min(v / max_v, 1.0)) if max_v else 0.0
    cls = "negative" if (neg and v < 0) else "positive"
    return (
        f'<span class="barcell"><span class="bar {cls}" style="width:{ratio * 100:.1f}%"></span>'
        f'<span class="txt">{v * 100:.1f}%</span></span>'
    )


def _delta_cls(v: float | None) -> str:
    if v is None or pd.isna(v):
        return "delta-neutral"
    return "delta-positive" if v >= 0 else "delta-negative"


def _phase_rows(rows: list[dict]) -> str:
    out = []
    for r in rows:
        share = r["share_rhythm"]
        inc = r["increment_median"]
        inc_share = r["share_median"]
        total = r["total_lock"]
        row = (
            f"<tr>"
            f"<td><strong>{r['generation']}</strong></td>"
            f"<td><span class='badge badge-blue'>{r['family']}</span></td>"
            f"<td class='num'>{r['rhythm_days']}d</td>"
            f"<td class='num'>{r['presale_lock']:,}</td>"
            f"<td class='num'>{r['launch_burst']:,}</td>"
            f"<td class='num'>{r['benefit']:,}</td>"
            f"<td class='num'>{r['steady']:,}</td>"
            f"<td class='num'>{r['rhythm_lock']:,}</td>"
            f"<td class='num'>{total:,}</td>"
            f"<td class='num'>{_fmt(share)}</td>"
        )
        if inc is None:
            row += "<td class='num'>—</td><td class='num'>—</td>"
        else:
            row += (
                f"<td class='num {_delta_cls(inc)}'>{inc:,.0f}</td>"
                f"<td class='num {_delta_cls(inc_share)}'>{_fmt(inc_share)}</td>"
            )
        row += "</tr>"
        out.append(row)
    return "\n".join(out)


def _share_table(rows: list[dict], label: str) -> str:
    max_share = max((r["share_rhythm"] for r in rows if r["share_rhythm"] is not None), default=1.0) or 1.0
    body = []
    for r in rows:
        body.append(
            f"<tr>"
            f"<td><strong>{r['generation']}</strong> <span class='badge badge-blue'>{r['family']}</span></td>"
            f"<td class='num'>{r['rhythm_lock']:,} / {r['total_lock']:,}</td>"
            f"<td>{_bar(r['share_rhythm'], max_share)}</td>"
            f"<td class='num'>{_fmt(r['share_rhythm'])}</td>"
            f"</tr>"
        )
    return f"""
    <div class="card">
      <h2>节奏窗口贡献率（{label}）</h2>
      <p class="section-note">节奏窗口 = [预售 start, 权益结束 finish]；总量 = [start, end+窗口] 累计零售锁单。贡献率 = 窗口内锁单 ÷ 总量。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>代际</th><th style="text-align:right;">窗口 / 总量</th><th>窗口贡献率</th><th style="text-align:right;">占比</th></tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
      </div>
    </div>"""


def _increment_table(rows: list[dict], label: str) -> str:
    max_inc = max((abs(r["increment_median"]) for r in rows if r["increment_median"] is not None), default=1.0) or 1.0
    body = []
    for r in rows:
        inc = r["increment_median"]
        share = r["share_median"]
        prev = r["prev_baseline_daily"]
        brand = r["brand_baseline_daily"]
        baseline_note = f"上代 {prev:.1f}/d" if prev > 0 else "—"
        baseline_note += f" ｜ 品牌 {brand:.1f}/d" if brand > 0 else ""
        inc_disp = "—" if inc is None else f"{inc:,.0f}"
        share_disp = "—" if share is None else _fmt(share)
        bar = (
            '<span class="barcell"><span class="txt">—</span></span>'
            if inc is None
            else f'<span class="barcell"><span class="bar {"negative" if inc < 0 else "positive"}" style="width:{min(abs(inc) / max_inc, 1) * 100:.1f}%"></span><span class="txt">{inc:,.0f}</span></span>'
        )
        body.append(
            f"<tr>"
            f"<td><strong>{r['generation']}</strong> <span class='badge badge-blue'>{r['family']}</span></td>"
            f"<td class='num'>{r['rhythm_lock']:,}</td>"
            f"<td class='num'>{baseline_note}</td>"
            f"<td>{bar}</td>"
            f"<td class='num {_delta_cls(inc)}'>{inc_disp}</td>"
            f"<td class='num {_delta_cls(share)}'>{share_disp}</td>"
            f"</tr>"
        )
    return f"""
    <div class="card">
      <h2>基线差值法增量（{label}）</h2>
      <p class="section-note">增量 = 节奏窗口实际锁单 − 基线日均 × 窗口天数；双基线取中位。基线1 = 上一代际成熟期（finish→+180d）；基线2 = 品牌上市前 180 天自然日均（剔除各上市活动窗口）。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>代际</th><th style="text-align:right;">窗口实际</th><th style="text-align:right;">基线(上代/品牌)</th><th>增量</th><th style="text-align:right;">增量(单)</th><th style="text-align:right;">占总量</th></tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
      </div>
    </div>"""


def _presale_pool_table(rows: list[dict]) -> str:
    body = []
    for r in rows:
        body.append(
            f"<tr>"
            f"<td><strong>{r['generation']}</strong></td>"
            f"<td class='num'>{r['presale_pool']:,}</td>"
            f"<td class='num'>{r['pool_locked']:,}</td>"
            f"<td class='num'>{_fmt(r['conv_rate'])}</td>"
            f"<td class='num'>{r['pool_delivered']:,}</td>"
            f"<td class='num'>{r['direct_lock']:,}</td>"
            f"</tr>"
        )
    return f"""
    <div class="card">
      <h2>预售池转化追踪</h2>
      <p class="section-note">预售池 = 预售期 [start, end) 内支付意向金、零售口径；转锁单 = 预售池中最终 lock_time 非空（含上市后转大定）；直接锁单 = 节奏窗口内锁单但无预售小订。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>代际</th><th style="text-align:right;">预售小订池</th><th style="text-align:right;">转锁单</th><th style="text-align:right;">转化率</th><th style="text-align:right;">转交付</th><th style="text-align:right;">窗口内直接锁单</th></tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
      </div>
    </div>"""


def _family_summary(rows: list[dict]) -> str:
    fams: dict = {}
    for r in rows:
        fams.setdefault(r["family"], []).append(r)
    body = []
    for fam, members in fams.items():
        total = sum(r["total_lock"] for r in members)
        rhythm = sum(r["rhythm_lock"] for r in members)
        incs = [r["increment_median"] for r in members if r["increment_median"] is not None]
        inc_total = sum(r["increment_median"] for r in members if r["increment_median"] is not None)
        share = rhythm / total if total else None
        share_inc = inc_total / total if total and incs else None
        gens = " / ".join(m["generation"] for m in members)
        body.append(
            f"<tr>"
            f"<td><strong>{fam}</strong></td>"
            f"<td>{gens}</td>"
            f"<td class='num'>{rhythm:,}</td>"
            f"<td class='num'>{total:,}</td>"
            f"<td class='num'>{_fmt(share)}</td>"
            f"<td class='num {_delta_cls(inc_total)}'>{inc_total:,.0f}</td>"
            f"<td class='num {_delta_cls(share_inc)}'>{_fmt(share_inc)}</td>"
            f"</tr>"
        )
    return f"""
    <div class="card">
      <h2>车系家族汇总（12M）</h2>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>车系</th><th>代际</th><th style="text-align:right;">窗口锁单</th><th style="text-align:right;">总量</th><th style="text-align:right;">窗口贡献率</th><th style="text-align:right;">增量合计</th><th style="text-align:right;">增量占总量</th></tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
      </div>
    </div>"""


def _insights(rows: list[dict], gen_dm2: dict | None, as_of: pd.Timestamp) -> str:
    valid_share = sorted((r["share_rhythm"] for r in rows if r["share_rhythm"] is not None))
    med_share = valid_share[len(valid_share) // 2] if valid_share else None
    positive = [r for r in rows if (r["increment_median"] or 0) > 0]
    top = (
        max(positive, key=lambda r: r["increment_median"] or 0)
        if positive
        else max(rows, key=lambda r: r["share_rhythm"] or 0)
    )
    top_caveat = "" if top["full_window_obs"] else f"（{top['generation']} 的 12M 总量窗口未满，占比略被抬高）"
    dm1 = next((r for r in rows if r["generation"] == "DM1"), None)
    incs = [(r, r["increment_median"]) for r in rows if r["increment_median"] is not None]
    incs.sort(key=lambda x: x[1], reverse=True)
    inc_pos = [v for _, v in incs if v > 0]
    inc_neg = [(r["generation"], v) for r, v in incs if v < 0]
    dm2_line = ""
    if gen_dm2:
        dm2_line = (
            f"<div class='insight'>"
            f"<h4>DM2 当前对照</h4>"
            f"<p>{gen_dm2['generation']} 上市 {gen_dm2['launch_days']} 天，上市至今累计零售锁单 <strong>{gen_dm2['lock_cum']:,}</strong>（留存 {gen_dm2['kept_cum']:,}），"
            f"尚处上市节奏窗口（权益结束 {gen_dm2['finish']}）早期，未纳入主对比。</p>"
            f"</div>"
        )
    neg_line = ""
    if inc_neg:
        neg_txt = "、".join(f"{g}（{v:,.0f}）" for g, v in inc_neg)
        neg_line = f"<p>弱代际（{neg_txt}）上市节奏未跑赢自然基线，其中 DM1（全新 L6）是最弱一届——集中运营失效时节奏窗口反而低于自然流量。</p>"
    return f"""
    <div class="card">
      <h2>关键发现</h2>
      <div class="insight gold">
        <h4>上市节奏是车系放量的主引擎，而非补充</h4>
        <p>{len(rows)} 个历史代际中，节奏窗口（预售→上市→权益结束）锁单贡献率中位约 <strong>{_fmt(med_share)}</strong>；
        除弱代际外，基线差值法增量占总量 <strong>10%–34%</strong>，说明集中爆发式运营创造的是「额外量」而非「前置量」。</p>
      </div>
      <div class="insight">
        <h4>最强案例：{top['generation']}（{top['family']}）</h4>
        <p>窗口贡献率 <strong>{_fmt(top['share_rhythm'])}</strong>，基线差值增量 <strong>{top['increment_median']:,.0f}</strong> 单（占总量 {_fmt(top['share_median'])}），
        上市首周锁单 {top['launch_burst']:,}、权益期 {top['benefit']:,}，是历次上市中节奏运营收益最高的一次{top_caveat}。</p>
      </div>
      {f'<div class="insight"><h4>弱代际警示</h4>{neg_line}</div>' if neg_line else ''}
      {dm2_line}
    </div>"""


def _method_section(as_of: pd.Timestamp) -> str:
    return f"""
    <div class="method-section">
      <h2 class="section-title">口径与数据来源</h2>
      <div class="method-grid">
        <div class="method-item"><div class="method-icon" style="background:var(--zh-blue-100);color:var(--zh-blue);">D</div>
          <div class="method-body"><strong>数据源</strong><br/>dataset/order_data.parquet<br/>shared/schema/business_definition.json</div></div>
        <div class="method-item"><div class="method-icon" style="background:var(--zh-gold-100);color:var(--zh-gold-700);">T</div>
          <div class="method-body"><strong>时间窗口</strong><br/>预售 [start,end) ｜ 上市爆发 [end,end+7d) ｜ 权益 [end+7d,finish] ｜ 常态 (finish,end+12M]</div></div>
        <div class="method-item"><div class="method-icon" style="background:#E8F8FD;color:#2D6FA3;">F</div>
          <div class="method-body"><strong>筛选口径</strong><br/>零售 = order_type ∈ {{用户车, NaN}}，排除试驾车/员工/大客户/批售等全部非零售单</div></div>
        <div class="method-item"><div class="method-icon" style="background:#F3F6F8;color:#374151;">M</div>
          <div class="method-body"><strong>指标定义</strong><br/>窗口贡献率 = 节奏窗口锁单 ÷ 总量（12M/6M）<br/>增量 = 窗口实际 − 基线日均 × 窗口天数</div></div>
      </div>
      <p class="section-note" style="margin-top:12px;">as-of {as_of.date()}；CM2/LS9/LS8 的 12M 窗口未完全观测（LS8 连 6M 亦未满），总量为至今累计，占比略被抬高；DM1 为负增量案例，基线方法对弱代际更敏感。</p>
    </div>"""


def render_html_report(
    rows_12: list[dict],
    rows_6: list[dict],
    gen_dm2: dict | None,
    as_of: pd.Timestamp,
    output: Path,
) -> None:
    valid_share = sorted((r["share_rhythm"] for r in rows_12 if r["share_rhythm"] is not None))
    med_share = valid_share[len(valid_share) // 2] if valid_share else None
    incs = [r["increment_median"] for r in rows_12 if r["increment_median"] is not None]
    inc_sum = sum(incs)
    total_lock = sum(r["total_lock"] for r in rows_12)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>上市节奏增量贡献研究 · 预售-上市-权益结束</title>
<link rel="stylesheet" href="{_STATIC}/templates/report_style.css"/>
<style>
.table-wrap {{ overflow-x: auto; }}
.badge-blue {{ font-weight: 600; }}
.delta-positive {{ color: var(--status-positive); font-weight: 600; }}
.delta-negative {{ color: var(--status-negative); font-weight: 600; }}
.insight h4 {{ font-size: 14px; margin-bottom: 4px; color: var(--zh-deep-blue); }}
@media (max-width:768px) {{ .hero h1 {{ font-size: 24px; }} }}
</style>
</head>
<body>

<header>
<div class="container">
  <div class="brand">
    <img class="brand-avatar" src="{_STATIC}/assets/brand/raccoon_avatar_light.png" alt=""/>
    <span class="brand-name">Raccoon Research</span>
  </div>
  <span class="header-meta">上市节奏增量贡献研究 · as-of {as_of.date()}</span>
</div>
</header>

<main class="container">

<section class="hero">
  <h1>上市节奏：预售–上市–权益结束 的增量贡献</h1>
  <p>评估集中爆发式销售运营（预售小订 → 上市转大定 → 权益窗口兑现）对车系销量的增量与重要性。</p>
</section>

<div class="summary-grid">
  <div class="summary-card"><div class="summary-value">{_fmt(med_share)}</div><div class="summary-label">节奏窗口贡献率中位</div><div class="summary-hint">7 代际 · 12M 总量口径</div></div>
  <div class="summary-card"><div class="summary-value">{inc_sum:,.0f}</div><div class="summary-label">增量合计(中位)</div><div class="summary-hint">基线差值法 · 7 代际</div></div>
  <div class="summary-card"><div class="summary-value">{total_lock:,}</div><div class="summary-label">7 代际 12M 锁单合计</div><div class="summary-hint">零售口径</div></div>
  <div class="summary-card"><div class="summary-value">7</div><div class="summary-label">分析代际</div><div class="summary-hint">CM0/CM1/CM2/DM0/DM1/LS9/LS8</div></div>
</div>

{_share_table(rows_12, "12M 总量窗口")}

{_share_table(rows_6, "6M 对照窗口")}

{_increment_table(rows_12, "12M 总量窗口")}

{_presale_pool_table(rows_12)}

{_family_summary(rows_12)}

{_insights(rows_12, gen_dm2, as_of)}

{_method_section(as_of)}

</main>

<footer>
  <img class="brand-sig" src="{_STATIC}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research"/>
  <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>

</body>
</html>"""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"✅ HTML 报告已生成: {output}")
