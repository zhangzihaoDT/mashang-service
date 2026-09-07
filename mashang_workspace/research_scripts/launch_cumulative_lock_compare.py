#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上市后累计锁单对比（DM0 / DM1 / DM2） — HTML 报告脚本

模块 1：对比 DM0/DM1/DM2 上市后每天的累计锁单数折线图。
  - 天数基准：以最新代际上市日（time_periods.DM2.end）为第 1 天，
    第 t 天对应日期 = DM2.end + (t-1)，t = 1..N。
  - N = 上市日至今（today / as-of 前一日）天数；累计 = 自各代际上市日起至第 t 天的零售锁单。
  - 三系曲线 X 轴对齐"上市后天数"，各自按实取本代上市日起同窗口累计。
  - 关键时点表 = 预售期留存小订 × 上市周期转化（成交金→锁单漏斗，逐代际对比）。

模块 3：有效门店 × 经销商网络对比（复用 research_scripts/store_network_compare.py 的
  compute_store_network 计算结果；独立脚本可单独 --format json 输出 Result Contract）。

口径：
  - 锁单 = lock_time 非空 COUNTD(order_number)
  - 零售 = order_type ∈ {用户车, NaN}（DM2 新车型 order_type 未填充，保留 NaN；其余代际排除非零售单）
  - 代际归属 = shared/schema/business_definition.json series_group_logic
  - 对齐参考：analyze_order_launch.py build_same_period_lock_totals / _compute_same_period_n

用法：
  python research_scripts/launch_cumulative_lock_compare.py --html
  python research_scripts/launch_cumulative_lock_compare.py --as-of 2026-09-06
  python research_scripts/launch_cumulative_lock_compare.py --format json --output outputs/tables/
  python research_scripts/launch_cumulative_lock_compare.py --gens DM1 DM2
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = REPO_ROOT / "mashang_workspace"
for p in (str(REPO_ROOT), str(_WS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from research_scripts.l6_m2_launch_lock_metrics_to_feishu import (  # noqa: E402
    _norm_product_name,
    _parse_logic,
    _rule_condition,
    apply_series_group_logic,
    load_business_definition,
)
from research_scripts.store_network_compare import compute_store_network  # noqa: E402
from utils.plotly_theme import apply_zh_theme, get_series_color  # noqa: E402
from utils.regions import REGION_MAP_OLD_TO_NEW, norm_region  # noqa: E402

_BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
_ORDER_DATA = REPO_ROOT / "dataset" / "order_data.parquet"
_ASSIGN_DATA = REPO_ROOT / "dataset" / "assign_data.csv"
_DEFAULT_REPORT = _WS / "outputs" / "reports"
_DEFAULT_TABLE = _WS / "outputs" / "tables"

DEFAULT_GENS = ["DM0", "DM1", "DM2"]
NON_RETAIL = {"试驾车", "大客户", "员工", "集团员工", "经销商员工", "享道", "仅批售", "项目", "展车", "海外"}


def _retail_mask(order_type: pd.Series) -> pd.Series:
    ot = order_type.fillna("").astype("string")
    return ot.isin(["", "用户车"]) & ~ot.isin(NON_RETAIL)


def _fmt_int(v) -> str:
    if pd.isna(v):
        return "—"
    return f"{int(round(float(v))):,}"


def load_data() -> pd.DataFrame:
    bd = load_business_definition(_BUSINESS_DEF)
    asts = {g: _parse_logic(_rule_condition(c)) for g, c in bd["series_group_logic"].items()}
    df = pd.read_parquet(_ORDER_DATA)
    for c in ["lock_time", "intention_payment_time", "delivery_date"]:
        if c in df.columns and not pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = pd.to_datetime(df[c], errors="coerce")
    df = apply_series_group_logic(df, bd, asts)
    return df


def resolve_end_day(bd: dict, gen: str) -> pd.Timestamp:
    tp = (bd.get("time_periods", {}) or {}).get(gen, {}) or {}
    return pd.Timestamp(tp["end"]).normalize()


def compute_curves(df: pd.DataFrame, bd: dict, gens: list[str],
                   as_of: pd.Timestamp) -> dict:
    """逐代际上市后每日累计锁单曲线（对齐上市后天数 1..N）。"""
    ends = {g: resolve_end_day(bd, g) for g in gens}
    max_end = max(ends.values())

    # 今天（as-of 数据覆盖上限）；"today-1"：最后观察日 = as-of 前一日（不含当天不完整数据）
    max_lock = pd.to_datetime(df["lock_time"], errors="coerce").max()
    if pd.notna(max_lock):
        as_of = min(as_of, pd.Timestamp(max_lock).normalize())
    last_date = as_of.normalize() - pd.Timedelta(days=1)
    n_days = max(1, int((last_date - max_end).days) + 1)  # 含首尾：第1天=end，最后一天=today-1

    retail = df[_retail_mask(df["order_type"])].copy()
    curves: dict[str, dict] = {}

    for g in gens:
        end = ends[g]
        window_end = end + pd.Timedelta(days=n_days)
        sub = retail[retail["series_group_logic"].eq(g) &
                      retail["lock_time"].notna() &
                      (retail["lock_time"] >= end) &
                      (retail["lock_time"] < window_end)].copy()
        sub["d"] = sub["lock_time"].dt.normalize()
        daily = sub.groupby("d")["order_number"].nunique()
        full = pd.date_range(end, window_end - pd.Timedelta(days=1))
        daily = daily.reindex(full, fill_value=0)
        cum = daily.cumsum().astype(int)

        curves[g] = {
            "end": end.date().isoformat(),
            "day_offset": [i + 1 for i in range(n_days)],
            "dates": [d.date().isoformat() for d in full],
            "daily": [int(v) for v in daily],
            "cum": [int(v) for v in cum],
        }

    return {
        "gens": gens,
        "n_days": n_days,
        "as_of": as_of.date().isoformat(),
        "last_date": last_date.date().isoformat(),
        "max_end": max_end.date().isoformat(),
        "curves": curves,
        "presale": _presale_conversion(retail, bd, gens, ends, n_days),
        "daily_product": _daily_product_breakdown(retail, bd, gens, ends, n_days),
        "region": _region_compare(retail, gens, ends, n_days),
        "network": compute_store_network(retail, gens, ends, n_days),
    }


def _daily_product_breakdown(df: pd.DataFrame, bd: dict, gens: list[str],
                             ends: dict, n_days: int) -> dict:
    """最新代际上市后每日锁单数 × product_name 拆分（当日去重，非累计）。
    product_name 先做空格归一化（连续空白→单空格），合并同一产品的排版变体。"""
    target = gens[-1]
    end = ends[target]
    window_end = end + pd.Timedelta(days=n_days)
    sub = df[df["series_group_logic"].eq(target) &
              df["lock_time"].notna() &
              (df["lock_time"] >= end) &
              (df["lock_time"] < window_end)].copy()
    sub["d"] = sub["lock_time"].dt.normalize()
    sub["product_name"] = sub["product_name"].map(_norm_product_name)

    full = pd.date_range(end, window_end - pd.Timedelta(days=1))
    pivot = sub.pivot_table(index="d", columns="product_name",
                            values="order_number", aggfunc="nunique", fill_value=0)
    pivot = pivot.reindex(full, fill_value=0).astype(int)

    products = sorted(pivot.columns, key=lambda c: (-int(pivot[c].sum()), str(c)))
    dates = [d.date().isoformat() for d in full]
    rows = [{
        "day": i + 1,
        "date": dates[i],
        "products": [int(pivot.loc[full[i], c]) if c in pivot.columns else 0 for c in products],
        "daily_total": int(pivot.iloc[i].sum()),
    } for i in range(n_days)]
    day_total_cum = [sum(r["daily_total"] for r in rows[: i + 1]) for i in range(n_days)]
    return {
        "gen": target,
        "end": end.date().isoformat(),
        "products": products,
        "rows": rows,
        "day_total_cum": day_total_cum,
    }


def _load_assign_daily_stores() -> pd.DataFrame:
    """assign_data 日频下发门店数（整体口径）。返回 d / 下发门店数。”"""
    df = pd.read_csv(_ASSIGN_DATA, encoding="utf-8-sig")
    dt = pd.to_datetime(df["Assign Time 年/月/日"], format="%Y年%m月%d日", errors="coerce")
    out = df.assign(d=dt)[["d", "下发门店数"]].dropna(subset=["d"])
    return out.sort_values("d")


def _avg_daily_stores(assign: pd.DataFrame, start: pd.Timestamp, n_days: int) -> dict | None:
    """某代际上市同期窗口（自上市日起 n_days 天）内日均下发门店数（assign 整体口径）。"""
    w = assign[(assign["d"] >= start) & (assign["d"] < start + pd.Timedelta(days=n_days))]
    if w.empty:
        return None
    avg = float(w["下发门店数"].mean())
    mx = int(w["下发门店数"].max())
    return {"avg": int(round(avg)), "max": mx, "days": int(w["d"].nunique())}


def _region_compare(df: pd.DataFrame, gens: list[str], ends: dict, n_days: int) -> dict | None:
    """最新两代际上市同周期零售锁单 ÷ 大区（旧架构大区名归一到新架构），附各代际上市同期窗口有效门店数。"""
    if len(gens) < 2:
        return None
    gen_a, gen_b = gens[-2], gens[-1]
    counts: dict[str, dict] = {"a": {}, "b": {}}
    assign = _load_assign_daily_stores()
    stores: dict[str, dict] = {"a": {}, "b": {}}
    for key, g in (("a", gen_a), ("b", gen_b)):
        end = ends[g]
        window_end = end + pd.Timedelta(days=n_days)
        sub = df[df["series_group_logic"].eq(g) &
                  df["lock_time"].notna() &
                  (df["lock_time"] >= end) &
                  (df["lock_time"] < window_end)]
        region = sub["parent_region_name"].map(norm_region)
        counts[key] = dict(sub.groupby(region)["order_number"].nunique())
        stores[key] = _avg_daily_stores(assign, end, n_days)

    regions = sorted(set(counts["a"]) | set(counts["b"]),
                     key=lambda r: (-counts["b"].get(r, 0), r))
    total_a = sum(counts["a"].values())
    total_b = sum(counts["b"].values())
    rows = []
    for r in regions:
        ca, cb = counts["a"].get(r, 0), counts["b"].get(r, 0)
        rows.append({
            "region": r,
            "a": int(ca), "a_share": ca / total_a if total_a else 0,
            "b": int(cb), "b_share": cb / total_b if total_b else 0,
            "diff_pp": round((cb / total_b - ca / total_a) * 100, 1)
                       if total_a and total_b else 0,
        })
    return {
        "gen_a": gen_a, "gen_b": gen_b, "n_days": n_days,
        "regions": rows, "total_a": int(total_a), "total_b": int(total_b),
        "store_metric": "assign_daily_stores",
        "valid_days_a": stores["a"]["days"] if stores["a"] else 0,
        "valid_days_b": stores["b"]["days"] if stores["b"] else 0,
        "total_stores_a": stores["a"]["avg"] if stores["a"] else None,
        "total_stores_b": stores["b"]["avg"] if stores["b"] else None,
        "max_stores_a": stores["a"]["max"] if stores["a"] else None,
        "max_stores_b": stores["b"]["max"] if stores["b"] else None,
    }


def _daily_product_table(c: dict) -> str:
    dp = c["daily_product"]
    products = dp["products"]
    n = len(dp["rows"])
    thead = (
        "<tr><th rowspan='2'>天数</th><th rowspan='2'>日期</th>"
        + "".join(f"<th colspan='1'>{p}</th>" for p in products)
        + "<th rowspan='2'>当日合计</th><th rowspan='2'>累计</th></tr><tr>"
        + "<th></th>" * len(products)
        + "</tr>"
    )
    rows_html = []
    for r in dp["rows"]:
        cells = f"<td class='num'>{r['day']}</td><td class='num'>{r['date']}</td>"
        cells += "".join(f"<td class='num'>{v}</td>" for v in r["products"])
        cells += f"<td class='num'><strong>{r['daily_total']}</strong></td>"
        cells += f"<td class='num'>{dp['day_total_cum'][r['day'] - 1]}</td>"
        rows_html.append(f"<tr>{cells}</tr>")
    col_totals = [sum(r["products"][i] for r in dp["rows"]) for i in range(len(products))]
    total_row = "<td></td><td><strong>上市同期累计</strong></td>"
    total_row += "".join(f"<td class='num'><strong>{v}</strong></td>" for v in col_totals)
    total_row += f"<td class='num'><strong>{dp['day_total_cum'][-1]}</strong></td><td></td>"
    rows_html.append(f"<tr>{total_row}</tr>")
    return f"""
    <div class="card">
      <h2>{dp['gen']} 上市以来每日锁单 × 车型（product_name）</h2>
      <p class="section-note">上市同期第 1..{n} 天（{dp['end']} 起，N = {c['n_days']}）；当日锁单 = lock_time 落在该日 23:59 前的零售（order_type ∈ 用户车/NaN）去重订单数；累计 = 上市日起至当日累计。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead>{thead}</thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
      </div>
    </div>"""


def _region_table(c: dict) -> str:
    rc = c.get("region")
    if not rc:
        return ""
    rows_html = []
    for r in rc["regions"]:
        diff = r["diff_pp"]
        sign = f"+{diff:.1f}" if diff > 0 else f"{diff:.1f}"
        cls = " class='pos'" if diff > 0 else (" class='neg'" if diff < 0 else "")
        rows_html.append(
            f"<tr><td>{r['region']}</td>"
            f"<td class='num'><strong>{r['b']:,}</strong></td><td class='num'>{r['b_share'] * 100:.1f}%</td>"
            f"<td class='num'>{r['a']:,}</td><td class='num'>{r['a_share'] * 100:.1f}%</td>"
            f"<td class='num'{cls}>{sign} pp</td></tr>"
        )
    rows_html.append(
        f"<tr><td><strong>合计</strong></td>"
        f"<td class='num'><strong>{rc['total_b']:,}</strong></td><td class='num'>100%</td>"
        f"<td class='num'><strong>{rc['total_a']:,}</strong></td><td class='num'>100%</td>"
        f"<td class='num'>—</td></tr>"
    )
    a, b = rc["gen_a"], rc["gen_b"]
    store_note = ""
    if rc.get("total_stores_a") is not None and rc.get("total_stores_b") is not None:
        note_avg = (f"有效门店数（各代际上市同期 {rc['n_days']} 天窗口日均，assign_data 下发门店口径）："
                    f"{b} = <strong>{rc['total_stores_b']:,} 家</strong> / {a} = <strong>{rc['total_stores_a']:,} 家</strong>"
                    f"（窗口单日 max：{b} {rc['max_stores_b']} / {a} {rc['max_stores_a']}）")
        store_note = f"""<tr><td colspan='5' class='cell-note'>{note_avg}</td></tr>"""
    return f"""
    <div class="card">
      <h2>分大区对比：{b} vs {a}（上市同期累计锁单 + 有效门店）</h2>
      <p class="section-note">上市同期 = 各代际自上市日起第 1..{rc['n_days']} 天（与折线同窗口，N = {c['n_days']}）；大区 = parent_region_name，旧架构（一区/二区/三区）已归一到新架构（东区/西区/北区/华中），详见口径说明。占比差 = {b} 占比 − {a} 占比（pp）。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>大区</th><th>{b} 锁单</th><th>{b} 占比</th><th>{a} 锁单</th><th>{a} 占比</th><th>占比差（{b}−{a}）</th></tr></thead>
        <tbody>{''.join(rows_html)}{store_note}</tbody>
      </table>
      </div>
    </div>"""


def _store_network_table(c: dict) -> str:
    sc = c.get("network")
    if not sc:
        return ""
    a, b = sc["gen_a"], sc["gen_b"]
    rows_html = []
    for r in sc["rows"]:
        d_stores = r["b_stores"] - r["a_stores"]
        d_blocs = r["b_blocs"] - r["a_blocs"]
        store_cls = " class='pos'" if d_stores > 0 else (" class='neg'" if d_stores < 0 else "")
        bloc_cls = " class='pos'" if d_blocs > 0 else (" class='neg'" if d_blocs < 0 else "")
        rows_html.append(
            f"<tr><td><strong>{r['region']}</strong></td>"
            f"<td class='num'>{r['a_stores']}</td><td class='num'>{r['a_blocs']}</td>"
            f"<td class='num'><strong>{r['b_stores']}</strong></td><td class='num'><strong>{r['b_blocs']}</strong></td>"
            f"<td class='num'{store_cls}>{d_stores:+d}</td><td class='num'{bloc_cls}>{d_blocs:+d}</td></tr>"
        )
    d_s = sc["total_b_stores"] - sc["total_a_stores"]
    d_b = sc["total_b_blocs"] - sc["total_a_blocs"]
    rows_html.append(
        f"<tr><td><strong>合计</strong></td>"
        f"<td class='num'>{sc['total_a_stores']}</td><td class='num'>{sc['total_a_blocs']}</td>"
        f"<td class='num'><strong>{sc['total_b_stores']}</strong></td><td class='num'><strong>{sc['total_b_blocs']}</strong></td>"
        f"<td class='num'{' class=\"pos\"' if d_s > 0 else ''}>{d_s:+d}</td>"
        f"<td class='num'{' class=\"pos\"' if d_b > 0 else ''}>{d_b:+d}</td></tr>"
    )
    return f"""
    <div class="card">
      <h2>有效门店 × 经销商网络对比：{b} vs {a}</h2>
      <p class="section-note">本模块复用 research_scripts/store_network_compare.py（独立脚本，支持 --format json 输出 Result Contract）。有效门店口径 = 该代际上市同期第 1..{sc['n_days']} 天窗口内真实发生锁单的订单侧门店（order_data.store_name），不依赖门店状态（停业/暂停/在建）猜测；经销商（Bloc）= 有效门店经 store_info_loader 关联到的经销商集团；大区 = 订单侧 parent_region_name，旧架构已归一为新架构（utils/regions.py）。变化 = {b} − {a}。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>大区</th><th>{a} 门店</th><th>{a} 经销商</th><th>{b} 门店</th><th>{b} 经销商</th><th>门店变化</th><th>经销商变化</th></tr></thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
      </div>
    </div>"""


def _presale_conversion(df: pd.DataFrame, bd: dict, gens: list[str],
                        ends: dict, n_days: int) -> list[dict]:
    """预售期留存小订 → 上市同期锁单转化（对齐 retained_intention_conversion operator）。"""
    rows = []
    for g in gens:
        tp = (bd.get("time_periods", {}) or {}).get(g, {}) or {}
        start = pd.Timestamp(tp["start"]).normalize()
        end = pd.Timestamp(tp["end"]).normalize()
        presale_end_excl = end + pd.Timedelta(days=1)

        sub = df[df["series_group_logic"].eq(g)].copy()
        pay = pd.to_datetime(sub["intention_payment_time"], errors="coerce")
        exit_cols = [c for c in ["intention_refund_time", "deposit_payment_time",
                                  "deposit_refund_time", "lock_time"] if c in sub.columns]
        exit_time = sub[exit_cols].min(axis=1, skipna=True)
        m_pay = pay.notna() & (pay >= start) & (pay < presale_end_excl)
        m_retained = m_pay & (exit_time.isna() | (exit_time >= presale_end_excl))
        retained_ids = sub.loc[m_retained, "order_number"].dropna().astype("string")
        retained_cnt = int(retained_ids.nunique())

        lock = pd.to_datetime(sub["lock_time"], errors="coerce")
        m_lock = lock.notna() & (lock >= end) & (lock < end + pd.Timedelta(days=n_days))
        lock_ids = sub.loc[m_lock, "order_number"].dropna().astype("string")
        total_lock = int(lock_ids.nunique())
        retained_lock = int(lock_ids.isin(retained_ids).sum())

        rows.append({
            "gen": g,
            "presale_period": f"{start.date().isoformat()} ~ {end.date().isoformat()}",
            "presale_days": int((end - start).days) + 1,
            "retained_count": retained_cnt,
            "total_lock": total_lock,
            "retained_lock": retained_lock,
            "share": (retained_lock / total_lock) if total_lock else None,
            "rate": (retained_lock / retained_cnt) if retained_cnt else None,
        })
    return rows


def terminal(c: dict) -> None:
    print(f"上市后累计锁单对比 · 第1天={c['max_end']}（以 {c['gens'][-1]} 上市日对齐）"
          f" · 窗口 {c['n_days']} 天 · 累计至 {c['last_date']}")
    hdr = f"{'上市后天数':<8}{'日期':<12}" + "".join(f"{g+'累计':>10}" for g in c['gens'])
    print(hdr)
    for i in range(0, c["n_days"]):
        row = f"{c['curves'][c['gens'][0]]['day_offset'][i]:<8}{c['curves'][c['gens'][-1]]['dates'][i]:<12}"
        for g in c["gens"]:
            row += f"{c['curves'][g]['cum'][i]:>10,}"
        print(row)


def _key_points_table(c: dict) -> str:
    body = []
    for r in c["presale"]:
        share = r["share"] or 0
        rate = r["rate"] or 0
        body.append(
            f"<tr><td><strong>{r['gen']}</strong></td>"
            f"<td>{r['presale_period']}</td>"
            f"<td class='num'>{r['presale_days']}</td>"
            f"<td class='num'>{r['retained_count']:,}</td>"
            f"<td class='num'>{r['total_lock']:,}</td>"
            f"<td class='num'>{r['retained_lock']:,}</td>"
            f"<td class='num'>{share:.0%}</td>"
            f"<td class='num'>{rate:.0%}</td></tr>"
        )
    return f"""
    <div class="card">
      <h2>预售期留存小订 × 上市周期转化（上市后第 1..{c['n_days']} 天）</h2>
      <p class="section-note">预售期 = time_periods.start ~ end；留存小订 = 预售期内支付意向金且预售期末未退（exit_time 空或 ≥ end+1 天）；上市同期 = 各代际上市日起第 1..N 天（N = {c['n_days']}，同折线窗口）；留存小订转化占比 = 转化数 ÷ 上市同期累计锁单；转化率 = 转化数 ÷ 留存小订数。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>系列分组</th><th>预售期</th><th>预售周期（日）</th><th>留存小订数</th><th>上市同期累计锁单数</th><th>上市同期累计留存小订转化数</th><th>留存小订转化占比</th><th>转化率</th></tr></thead>
        <tbody>{{}}</tbody>
      </table>
      </div>
    </div>""".format("\n".join(body))


def render_html(c: dict) -> str:
    gens = c["gens"]
    n = c["n_days"]
    cur = c["curves"]
    latest = {g: cur[g]["cum"][n - 1] for g in gens}
    top_gen = max(latest, key=latest.get)
    second = sorted(latest.values(), reverse=True)[1] if len(latest) > 1 else 1
    ratio = latest[top_gen] / max(second, 1)

    x_range = [0.5, n + 0.5]
    x_ticks = list(range(1, n + 1))
    if n > 30:
        step = (n // 10) or 1
        x_ticks = list(range(1, n + 1, step))
    y_max = max(cur[g]["cum"][-1] for g in gens)

    fig_json = json.dumps({
        "data": [{
            "x": cur[g]["day_offset"],
            "y": cur[g]["cum"],
            "customdata": cur[g]["dates"],
            "mode": "lines+markers",
            "name": g,
            "line": {"width": (3.0 if g == gens[-1] else 2.5),
                     "color": (get_series_color("own") if g == gens[-1]
                               else get_series_color("competitor", gens.index(g))),
                     "dash": None if g == gens[-1] else ("dot" if g == gens[0] else "dash")},
            "marker": {"size": 4},
            "hovertemplate": f"<b>{g}</b> · 上市后第 %{{x}} 天（%{{customdata}}）<br>累计锁单 %{{y:,}} 单<extra></extra>",
        } for g in gens],
        "layout": {
            "title": {"text": f"上市后累计锁单对比（{''.join(gens)}）", "x": 0.01, "xanchor": "left"},
            "xaxis": {"title": "上市后天数（第 1 天 = 各代际上市日）",
                      "range": x_range, "tickmode": "array", "tickvals": x_ticks},
            "yaxis": {"title": "累计零售锁单（单）", "rangemode": "tozero"},
            "legend": {"orientation": "h", "y": -0.25, "x": 0},
            "margin": {"l": 60, "r": 30, "t": 55, "b": 70},
            "height": 480,
        },
    }, ensure_ascii=False)

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>上市后累计锁单对比 · {''.join(gens)} · {c['as_of']}</title>
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
    <span class="header-meta">上市后累计锁单对比 · as-of {c['as_of']}</span>
  </div>
</header>

<main class="container">
  <section class="hero">
    <h1>上市后累计锁单对比：{ ' / '.join(gens) }</h1>
    <p>{n} 天窗口（{c['max_end']} = {gens[-1]} 上市日，第 1 天）至 {c['last_date']}；三系 t 轴对齐上市后天数。</p>
  </section>

  <div class="summary-grid">
    <div class="summary-card"><div class="summary-value">{_fmt_int(latest[gens[-1]])}</div>
      <div class="summary-label">{gens[-1]} 上市 {n} 天累计</div><div class="summary-hint">第 {n} 天</div></div>
    <div class="summary-card"><div class="summary-value">{_fmt_int(latest[gens[1]])}</div>
      <div class="summary-label">{gens[1]} 同窗口累计</div><div class="summary-hint">第 {n} 天</div></div>
    <div class="summary-card"><div class="summary-value">{_fmt_int(latest[gens[0]])}</div>
      <div class="summary-label">{gens[0]} 同窗口累计</div><div class="summary-hint">第 {n} 天</div></div>
    <div class="summary-card"><div class="summary-value">{top_gen}</div>
      <div class="summary-label">同窗口最高</div><div class="summary-hint">领先约 {ratio:.1f} 倍</div></div>
  </div>

  <section class="card">
    <h2>模块 1 · 上市后每日累计锁单对比折线图</h2>
    <div class="chart-box" id="chart-launch-cum" style="height:520px;"></div>
    <div class="section-note">
      各代际自其上市日（DM0 {c['curves'][gens[0]]['end']} / DM1 {c['curves'][gens[1]]['end']} / DM2 {c['curves'][gens[2]]['end']}）起，
      按 DM2 上市后天数对齐第 1..{n} 天；累计 = 截至当日 23:59 零售锁单 COUNTD(order_number)。DM2 为菱形实线，DM0 点线供形态参考。
    </div>
  </section>

  {_key_points_table(c)}

  {_daily_product_table(c)}

  {_region_table(c)}

  {_store_network_table(c)}

  <div class="method-section">
    <h2 class="section-title">口径与数据来源</h2>
    <div class="method-grid">
      <div class="method-item"><div class="method-icon" style="background:var(--zh-blue-100);color:var(--zh-blue);">D</div>
        <div class="method-body"><strong>数据源</strong><br/>dataset/order_data.parquet<br/>dataset/assign_data.csv（有效门店）<br/>shared/schema/business_definition.json<br/>shared/loaders/store_info_loader.py（经销商 Bloc 关联）<br/>research_scripts/store_network_compare.py（网络对比组件）</div></div>
      <div class="method-item"><div class="method-icon" style="background:var(--zh-gold-100);color:var(--zh-gold-700);">T</div>
        <div class="method-body"><strong>时间窗口</strong><br/>各代际上市日（time_periods.end）起<br/>共同 {c['n_days']} 天，累计至 {c['last_date']}</div></div>
      <div class="method-item"><div class="method-icon" style="background:#E8F8FD;color:#2D6FA3;">F</div>
        <div class="method-body"><strong>筛选口径</strong><br/>零售 = order_type ∈ {{用户车, NaN}}<br/>排除试驾车/员工/大客户/批售等</div></div>
      <div class="method-item"><div class="method-icon" style="background:#F3F6F8;color:#374151;">M</div>
        <div class="method-body"><strong>指标定义</strong><br/>锁单 = lock_time 非空 COUNTD(order_number)<br/>累计 = 上市日起至第 t 天末</div></div>
    </div>
  </div>
</main>

<footer>
  <img class="brand-sig" src="../../assets/brand/zihao_signature_transparent.png" alt="Raccoon Research"/>
  <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>

<script>
Plotly.newPlot('chart-launch-cum', {fig_json});
</script>
</body>
</html>"""
    return html


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="上市后累计锁单对比（DM0/DM1/DM2）HTML 报告")
    p.add_argument("--gens", type=str, nargs="*", default=DEFAULT_GENS,
                   help=f"代际（默认 {' '.join(DEFAULT_GENS)}），需按上市先后传入")
    p.add_argument("--as-of", type=str, default=None, help="统计基准日 YYYY-MM-DD（默认今天）")
    p.add_argument("--format", choices=["terminal", "json", "html"], default="terminal")
    p.add_argument("--output", type=str, default=None, help="HTML/JSON 输出目录")
    p.add_argument("--html", action="store_true", help="生成 HTML 报告（等价 --format html）")
    args = p.parse_args(argv)

    if not _ORDER_DATA.exists():
        print(f"❌ 文件不存在: {_ORDER_DATA}")
        return 1

    fmt = "html" if args.html else args.format
    gens = args.gens or DEFAULT_GENS
    df = load_data()
    bd = load_business_definition(_BUSINESS_DEF)
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp(datetime.now().date())
    c = compute_curves(df, bd, gens, as_of)

    if fmt == "terminal":
        terminal(c)
        return 0

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = _DEFAULT_TABLE if fmt == "json" else _DEFAULT_REPORT

    if fmt == "json":
        contract = {
            "status": "success",
            "script": "research_scripts/launch_cumulative_lock_compare.py",
            "scope": {
                "data_source": "dataset/order_data.parquet + shared/schema/business_definition.json",
                "time_window": {"start": c["max_end"], "end": c["last_date"],
                                "n_days": c["n_days"]},
                "filters": {"gens": gens,
                            "order_type": "用户车/NaN（零售口径）",
                            "metric_definition": "累计锁单 = 自上市日起 COUNTD(order_number) 截至当日；天数以最新代际上市日为第1天"},
            },
            "result": {
                "summary": f"{' / '.join(gens)} 上市后 {c['n_days']} 天累计锁单对比",
                "metrics": {g: {"cum": c["curves"][g]["cum"][-1],
                                "daily_last": c["curves"][g]["daily"][-1]} for g in gens},
                "curve": c["curves"],
                "presale_conversion": c["presale"],
                "daily_product_lock": c["daily_product"],
                "region_compare": c["region"],
                "store_network_compare": c["network"],
            },
            "artifacts": {},
            "followup_context": {"metric": "lock_count_cumulative", "gens": gens,
                                 "available_dimensions": ["day", "series"]},
            "warnings": [],
            "errors": [],
        }
        out = out_dir / f"launch_cum_lock_compare_{'_'.join(gens)}.json"
        out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已输出: {out}")
        return 0

    out = out_dir / f"launch_cum_lock_compare_{c['as_of'].replace('-', '')}.html"
    out.write_text(render_html(c), encoding="utf-8")
    print(f"✅ HTML 报告已生成: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())