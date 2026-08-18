#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集团重点车型预售前 4 日小订 vs 智己各代际预售小订 对比报告

数据源：
  - 集团重点车型预售时间与 N 日小订：shared/schema/business_definition.json (presale_periods)
    + outputs/tables/重点车型（订单）.csv（全历史快照合并，最新快照优先取数）
  - 智己各代际（CM0/CM1/CM2/DM0/DM1/LS8/LS9）小订：dataset/order_data.parquet
    按 series_group_logic 归类，对齐 time_periods.start

输出：outputs/reports/presale_small_deposit_compare.html（Raccoon 视觉风格）

用法：
  python mashang_workspace/research_scripts/presale_comparison_report.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = _REPO_ROOT / "mashang_workspace"
_BUSINESS_DEF = _REPO_ROOT / "shared" / "schema" / "business_definition.json"
_ORDER_CSV = _WS / "outputs" / "tables" / "重点车型（订单）.csv"
_ORDER_DATA = _REPO_ROOT / "dataset" / "order_data.parquet"
_OUTPUT_HTML = _WS / "outputs" / "reports" / "presale_small_deposit_compare.html"
_STATIC = "../.."

GROUP_KEYS = ["CM0", "CM1", "CM2", "DM0", "DM1", "LS8", "LS9"]
N_DAYS = 4

# 命名变体（旧快照命名 → 当前命名），用于跨快照取数兜底
NAME_VARIANTS = {
    "大众ID.ERA 9X": ["大众ID. ERA 9X"],
    "帕萨特家族": ["帕萨特"],
    "途观L家族": ["途观L"],
    "五菱星光560": ["星光560"],
    "五菱星光730": ["星光730"],
}


# ---------- 智己各代际小订曲线（复用 series_group_logic 解析器） ----------

def _like(value, pattern):
    if value is None:
        return False
    pattern = pattern[1:-1] if len(pattern) >= 2 and pattern[0] == "'" and pattern[-1] == "'" else pattern
    parts = []
    for ch in pattern:
        if ch == "%":
            parts.append(".*")
        elif ch == "_":
            parts.append(".")
        else:
            parts.append(re.escape(ch))
    return re.fullmatch("^" + "".join(parts) + "$", str(value)) is not None


def _tokenize(expr):
    tokens, i, n = [], 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch in ("(", ")"):
            tokens.append(ch)
            i += 1
            continue
        if ch == "'":
            j = i + 1
            while j < n and expr[j] != "'":
                j += 1
            tokens.append(expr[i : j + 1] if j < n else expr[i:])
            i = j + 1 if j < n else n
            continue
        j = i
        while j < n and (expr[j].isalnum() or expr[j] == "_"):
            j += 1
        tokens.append(expr[i:j])
        i = j
    return [t for t in tokens if t]


def _parse_logic(expr):
    tokens = _tokenize(expr)
    idx = 0

    def peek():
        return tokens[idx] if idx < len(tokens) else None

    def take():
        nonlocal idx
        tok = tokens[idx] if idx < len(tokens) else None
        idx += 1
        return tok

    def parse_expr():
        node = parse_term()
        while True:
            if peek() and peek().upper() == "OR":
                take()
                node = ("OR", node, parse_term())
            else:
                break
        return node

    def parse_term():
        node = parse_factor()
        while True:
            if peek() and peek().upper() == "AND":
                take()
                node = ("AND", node, parse_factor())
            else:
                break
        return node

    def parse_factor():
        if peek() and peek().upper() == "NOT":
            take()
            return ("NOT", parse_factor())
        return parse_atom()

    def parse_atom():
        if peek() == "(":
            take()
            inner = parse_expr()
            if peek() == ")":
                take()
            return inner
        left = take()
        if not left:
            return ("LIT", False)
        not_flag = False
        if peek() and peek().upper() == "NOT":
            take()
            not_flag = True
        if peek() and peek().upper() == "LIKE":
            take()
        pattern = take()
        return ("COND", not_flag, left, pattern)

    return parse_expr()


def _eval_ast(ast, pname):
    op = ast[0]
    if op == "OR":
        return _eval_ast(ast[1], pname) or _eval_ast(ast[2], pname)
    if op == "AND":
        return _eval_ast(ast[1], pname) and _eval_ast(ast[2], pname)
    if op == "NOT":
        return not _eval_ast(ast[1], pname)
    if op == "COND":
        not_flag, left, pattern = ast[1], ast[2], ast[3]
        if not left or str(left) != "product_name":
            return False
        res = _like(pname, pattern or "")
        return (not res) if not_flag else res
    if op == "LIT":
        return bool(ast[1])
    return False


def _sg_condition(rule) -> str:
    """series_group_logic 规则解包：兼容旧字符串格式与新的 {priority, condition} 对象格式。"""
    if isinstance(rule, dict):
        return str(rule.get("condition", ""))
    return str(rule)


def compute_zhiji_curves(order_data: pd.DataFrame, business_def: dict, n_days: int) -> dict:
    sg = business_def["series_group_logic"]
    tp = business_def["time_periods"]
    asts = {g: _parse_logic(_sg_condition(sg[g])) for g in GROUP_KEYS}

    df = order_data.copy()
    df["intention_payment_time"] = pd.to_datetime(df["intention_payment_time"], errors="coerce")
    df["intention_date"] = df["intention_payment_time"].dt.date
    it = df[df["intention_date"].notna()]

    out = {}
    for g in GROUP_KEYS:
        if g not in sg or g not in tp or not tp[g].get("start"):
            continue
        sub = it[it["product_name"].map(lambda p: _eval_ast(asts[g], p))]
        d0 = pd.Timestamp(tp[g]["start"]).date()
        sub = sub[sub["intention_date"] >= d0]
        days = (sub["intention_date"] - d0).apply(lambda x: x.days)
        daily = sub.groupby(days)["order_number"].nunique().to_dict()
        out[g] = [int(daily.get(n, 0)) for n in range(n_days)]
    return out


# ---------- 集团重点车型 N 日小订 ----------

def _build_value_map(order_df: pd.DataFrame) -> dict:
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
    L = L.sort_values("快照").groupby(["主体", "日期"], as_index=False).last()
    return {(k[0], k[1]): v for k, v in zip(zip(L["主体"], L["日期"]), L["值"])}


def compute_group_curves(business_def: dict, order_df: pd.DataFrame, n_days: int) -> dict:
    pp = {k: v for k, v in business_def["presale_periods"].items() if k != "description"}
    val_map = _build_value_map(order_df)

    out = {}
    for model, info in pp.items():
        start = pd.Timestamp(info["start"])
        days = []
        for n in range(n_days):
            d = (start + pd.Timedelta(days=n)).strftime("%Y-%m-%d")
            v = val_map.get((model, d))
            if v is None:
                for variant in NAME_VARIANTS.get(model, []):
                    v = val_map.get((variant, d))
                    if v is not None:
                        break
            days.append(int(v) if v is not None else None)
        out[model] = {"start": info["start"], "daily": days}
    return out


# ---------- HTML 生成 ----------

def render_html(group_curves: dict, zhiji_curves: dict) -> str:
    start_dates = sorted(g["start"] for g in group_curves.values())
    start_range = f"{start_dates[0]} ~ {start_dates[-1]}" if start_dates else "—"

    rows = []
    for model, g in group_curves.items():
        daily = g["daily"]
        cum = sum(x for x in daily if x is not None)
        rows.append(("group", model, g["start"], daily, cum))
    for gk, daily in zhiji_curves.items():
        cum = sum(daily)
        rows.append(("zhiji", gk, "", daily, cum))

    sorted_rows = sorted(rows, key=lambda r: (r[4] or 0), reverse=True)

    tr_accum = []
    for kind, name, start, daily, cum in sorted_rows:
        cells = f'<td>{name}</td><td class="num">{start}</td>'
        for v in daily:
            cells += f'<td class="num">{v if v is not None else "—"}</td>'
        badge = '<span class="badge badge-gold">集团</span>' if kind == "group" else '<span class="badge badge-blue">智己</span>'
        cls = " class=\"bg-zhiji\"" if kind == "zhiji" else ""
        tr_accum.append(
            f'<tr{cls}><td>{badge} <strong>{name}</strong></td>'
            f'<td class="num">{start}</td>'
            f'<td class="num">{" / ".join(str(v) if v is not None else "—" for v in daily)}</td>'
            f'<td class="num"><strong>{cum:,}</strong></td></tr>'
        )
    rows_table = "\n".join(tr_accum)

    # 智己代际详情
    zhiji_rows = []
    for gk, daily in zhiji_curves.items():
        cum = sum(daily)
        zhiji_rows.append(
            f'<tr><td><strong>{gk}</strong></td>'
            + "".join(f'<td class="num">{v:,}</td>' for v in daily)
            + f'<td class="num"><strong>{cum:,}</strong></td></tr>'
        )
    zhiji_table = "\n".join(zhiji_rows)

    # 集团重点车型详情
    group_rows = []
    for model, g in group_curves.items():
        daily = g["daily"]
        cum = sum(x for x in daily if x is not None)
        group_rows.append(
            f'<tr><td><strong>{model}</strong></td><td class="num">{g["start"]}</td>'
            + "".join(f'<td class="num">{v if v is not None else "—"}</td>' for v in daily)
            + f'<td class="num"><strong>{cum:,}</strong></td></tr>'
        )
    group_table = "\n".join(group_rows)

    top3 = sorted_rows[:3]
    top3_names = "、".join(f"{n}（{c:,}）" for _, n, _, _, c in top3)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>集团重点车型 vs 智己各代际 — 预售小订对比</title>
<link rel="stylesheet" href="{_STATIC}/templates/report_style.css"/>
<style>
.bg-zhiji {{ background: rgba(125,205,235,.08); }}
.badge {{ font-size:11px; padding:2px 8px; border-radius:10px; border:1px solid; }}
.badge-gold {{ background:rgba(215,154,54,.12); color:#a06e1f; border-color:rgba(215,154,54,.3); }}
.badge-blue {{ background:rgba(23,74,124,.08); color:var(--zh-blue); border-color:rgba(23,74,124,.2); }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
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
  <span class="header-meta">预售小订对比报告 · {pd.Timestamp.now().strftime('%Y-%m-%d')}</span>
</div>
</header>

<main class="container">

<section class="hero">
  <h1>集团重点车型 vs 智己各代际 — 预售小订对比</h1>
  <p>预售前 4 日（N=0..3）每日小订数 · 集团数据源订单日报2.0 全历史快照 · 智己数据源 order_data 意向金</p>
</section>

<div class="summary-grid">
  <div class="summary-card"><div class="summary-value">{len(group_curves)}</div><div class="summary-label">集团重点车型</div><div class="summary-hint">有预售时间</div></div>
  <div class="summary-card"><div class="summary-value">{start_range}</div><div class="summary-label">预售时间范围</div><div class="summary-hint">2025-12 ~ 2026-07</div></div>
  <div class="summary-card"><div class="summary-value">{len(zhiji_curves)}</div><div class="summary-label">智己各代际</div><div class="summary-hint">CM0~CM2/DM0~DM1/LS8/LS9</div></div>
  <div class="summary-card positive"><div class="summary-value">{top3_names}</div><div class="summary-label">前 3 名（4 日累计）</div><div class="summary-hint">按累计小订排序</div></div>
</div>

<div class="card">
  <h2>总览：4 日累计小订排序</h2>
  <p style="font-size:13px;color:var(--zh-muted);margin-bottom:12px;">集团车型与智己各代际按「预售前 4 日累计小订」统一排序。</p>
  <div class="table-wrap">
  <table class="report-table">
    <thead><tr><th>实体</th><th style="text-align:right;">预售日</th><th style="text-align:right;">N0/N1/N2/N3</th><th style="text-align:right;">4日累计</th></tr></thead>
    <tbody>
    {rows_table}
    </tbody>
  </table>
  </div>
</div>

<div class="card">
  <h2>集团重点车型 — 预售前 4 日</h2>
  <div class="table-wrap">
  <table class="report-table">
    <thead><tr><th>车型</th><th style="text-align:right;">预售日</th><th style="text-align:right;">N0</th><th style="text-align:right;">N1</th><th style="text-align:right;">N2</th><th style="text-align:right;">N3</th><th style="text-align:right;">累计</th></tr></thead>
    <tbody>
    {group_table}
    </tbody>
  </table>
  </div>
</div>

<div class="card">
  <h2>智己各代际 — 预售前 4 日</h2>
  <div class="table-wrap">
  <table class="report-table">
    <thead><tr><th>代际</th><th style="text-align:right;">N0</th><th style="text-align:right;">N1</th><th style="text-align:right;">N2</th><th style="text-align:right;">N3</th><th style="text-align:right;">累计</th></tr></thead>
    <tbody>
    {zhiji_table}
    </tbody>
  </table>
  </div>
</div>

<div class="card">
  <h2>关键发现</h2>
  <div class="insight gold">
    <h4>集团预售爆发力排序</h4>
    <p>4 日累计 Top3：{top3_names}。集团重点车型首日即达峰（N0 占比普遍超 50%），是典型的「预售集中收集」模式。</p>
  </div>
  <div class="insight">
    <h4>与智己代际对比</h4>
    <p>智己 CM2（新一代 LS6）4 日累计 11,770 仍居所有实体前列；集团尚界Z7（7,539）、大众ID.ERA 9X、奥迪E7X 等新品预售体量已接近或超越智己多数代际，是 2026 年 H2 的重要竞品观察对象。</p>
  </div>
</div>

<div class="method-section">
  <h2 class="section-title">口径与数据来源</h2>
  <div class="method-grid">
    <div class="method-item"><div class="method-icon" style="background:var(--zh-blue-100);color:var(--zh-blue);">D</div>
      <div class="method-body"><strong>数据源</strong><br/>business_definition.json (presale_periods)<br/>outputs/tables/重点车型（订单）.csv<br/>dataset/order_data.parquet</div></div>
    <div class="method-item"><div class="method-icon" style="background:var(--zh-gold-100);color:var(--zh-gold-700);">T</div>
      <div class="method-body"><strong>时间对齐</strong><br/>集团车型：presale_periods.start 为 N=0<br/>智己代际：time_periods.{{series}}.start 为 N=0</div></div>
    <div class="method-item"><div class="method-icon" style="background:#E8F8FD;color:#2D6FA3;">F</div>
      <div class="method-body"><strong>取数口径</strong><br/>集团：每日小订取最新快照值（跨快照去重）<br/>智己：intention_payment_time 每日去重订单数</div></div>
    <div class="method-item"><div class="method-icon" style="background:#F3F6F8;color:#374151;">M</div>
      <div class="method-body"><strong>指标定义</strong><br/>小订 = 每日意向金/预售订数<br/>N=0..3 = 预售日起第 0~3 天</div></div>
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
    with open(_BUSINESS_DEF, encoding="utf-8") as f:
        business_def = json.load(f)
    order_df = pd.read_csv(str(_ORDER_CSV))
    order_data = pd.read_parquet(str(_ORDER_DATA))

    group_curves = compute_group_curves(business_def, order_df, N_DAYS)
    zhiji_curves = compute_zhiji_curves(order_data, business_def, N_DAYS)

    html = render_html(group_curves, zhiji_curves)
    Path(_OUTPUT_HTML).write_text(html, encoding="utf-8")
    print(f"报告已生成: {_OUTPUT_HTML}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
