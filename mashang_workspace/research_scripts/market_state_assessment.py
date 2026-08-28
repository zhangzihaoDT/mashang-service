#!/usr/bin/env python3
"""Market State Assessment：基于任意 as-of 的市场状态评估（V0.3 Runtime）。

对每个 价格段×车身 新能源市场，评估：
  - regime（NEV 渗透率 <50% = substitution / ≥50% = shock）
  - 12M 市场规模与增长
  - 替代空间（Regime 1 结构性机会）
  - 冲击者在场（最近 12 个月 SHOCK_CONFIRMED/CANDIDATE，Regime 2 机会）
  - 真空 / 红海（候选冲击者数）
输出机会市场清单（Regime 1 结构性 + Regime 2 冲击）。

用法：
  python mashang_workspace/research_scripts/market_state_assessment.py --as-of 2026-07
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[2]
_RESEARCH_DIR = ROOT / "mashang_workspace" / "research_scripts"
_OUTPUT = ROOT / "mashang_workspace" / "outputs"
_WS = ROOT / "mashang_workspace"
_TEMPLATE_DIR = _WS / "templates"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(_RESEARCH_DIR))

from shared.loaders.tp_and_mix_ways_loader import load_tp_and_mix_ways_table  # noqa: E402
import tp_and_mix_ways_market_volume as mv  # noqa: E402
import shock_detector_rolling as rolling  # noqa: E402

REGIME_THRESHOLD = 50
MIN_MARKET_SALES = 30_000  # 进入评估的最低 12M 市场规模


def assess(price: pd.DataFrame, model: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """市场级状态评估。"""
    p = price.copy()
    p["price_bucket"] = p["tp_bucket_5w"].map(mv.clean_text)
    p = p[p.price_bucket != "其他"]
    p12 = p[(p.date_month > as_of - pd.DateOffset(months=12)) & (p.date_month <= as_of)]
    p_prev = p[(p.date_month > as_of - pd.DateOffset(months=24)) & (p.date_month <= as_of - pd.DateOffset(months=12))]

    # 市场层 12M 规模 / NEV 渗透率 / 增长
    rows = []
    for (pb, bt), g in p12.groupby(["price_bucket", "body_type"]):
        tot = float(g.sales.sum())
        nev = float(g[g.fuel_type_group == "新能源"].sales.sum())
        prev_tot = float(p_prev[(p_prev.price_bucket == pb) & (p_prev.body_type == bt)].sales.sum())
        growth = (tot / prev_tot - 1) * 100 if prev_tot else None
        nev_pen = nev / tot * 100 if tot else 0
        if tot < MIN_MARKET_SALES:
            continue
        rows.append({"market": f"{pb} {bt}", "price_bucket": pb, "body_type": bt,
                     "total_sales_12m": tot, "nev_sales_12m": nev,
                     "nev_penetration": nev_pen, "market_growth_pct": growth,
                     "regime": "shock" if nev_pen >= REGIME_THRESHOLD else "substitution",
                     "substitution_space": (1 - nev_pen / 100) if nev_pen < REGIME_THRESHOLD else None})
    mkt = pd.DataFrame(rows)

    # 冲击者在场（最近 12 个月）
    scan = rolling.scan(model, price, as_of)
    cand = scan[scan.shock_state != "SHOCK_NONE"]
    cand["market"] = cand["target_market"].str.replace(" 新能源", "", regex=False)
    per_market = cand.groupby("market").agg(
        shock_count=("model", "count"),
        confirmed_count=("shock_state", lambda s: (s == "SHOCK_CONFIRMED").sum()),
        top_shocker=("tail_monthly_sales", "max"),
    ).reset_index()

    mkt = mkt.merge(per_market, on="market", how="left")
    mkt["shock_count"] = mkt["shock_count"].fillna(0).astype(int)
    mkt["confirmed_count"] = mkt["confirmed_count"].fillna(0).astype(int)
    mkt["vacuum_crowded"] = mkt["shock_count"].apply(lambda n: "vacuum" if n == 0 else ("crowded" if n == 1 else "红海"))
    # 机会类别
    def _opp(r):
        if r.regime == "substitution" and r.nev_penetration < 40:
            return "REGIME1 替代空间充足"
        if r.regime == "shock" and r.confirmed_count >= 1:
            return "REGIME2 冲击已确认"
        if r.regime == "shock" and r.shock_count >= 1:
            return "REGIME2 冲击进行中"
        if r.regime == "substitution":
            return "REGIME1 替代中段"
        return "观察"
    mkt["opportunity"] = mkt.apply(_opp, axis=1)
    return mkt.sort_values(["opportunity", "total_sales_12m"], ascending=[True, False])


def _fmt_num(v, nd=0):
    return "-" if v is None or pd.isna(v) else f"{v:,.{nd}f}"


def _fmt_pct(v, nd=1):
    return "-" if v is None or pd.isna(v) else f"{v:.{nd}f}%"


def _growth_cls(v):
    if v is None or pd.isna(v):
        return ""
    return "delta-positive" if v >= 0 else "delta-negative"


def _env_zh(v):
    return {"vacuum": "真空", "crowded": "竞争", "红海": "红海"}.get(v, v)


def render_html(df: pd.DataFrame, scan: pd.DataFrame, as_of: pd.Timestamp, out_path: Path) -> None:
    """用 Jinja2 + report_style.css 渲染月度市场观察 HTML。

    信息架构（V0.3 双视角）：
      Regime 1 看市场（结构性替代机会） / Regime 2 看产品（Shock Detector）
    """
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
    tpl = env.get_template("market_state_report.html")

    r1 = df[df.regime == "substitution"].sort_values(["substitution_space", "total_sales_12m"], ascending=[False, False])
    mature = df[df.regime == "shock"].sort_values("total_sales_12m", ascending=False)  # Mature Context 按 12M 规模降序

    def _mkt_rows(d, with_space):
        rows = []
        for r in d.itertuples():
            rows.append({
                "market": r.market, "nev_penetration": _fmt_pct(r.nev_penetration),
                "substitution_space": _fmt_num(r.substitution_space, 2) if with_space else None,
                "sales": _fmt_num(r.total_sales_12m),
                "growth": _fmt_pct(r.market_growth_pct), "growth_cls": _growth_cls(r.market_growth_pct),
                "shock": r.shock_count, "confirmed": r.confirmed_count,
                "env": _env_zh(r.vacuum_crowded),
                "env_cls": "badge-green" if r.vacuum_crowded == "vacuum" else ("badge-gold" if r.vacuum_crowded == "红海" else "badge-blue"),
                "state": r.opportunity, "top": r.opportunity in ("REGIME1 替代空间充足", "REGIME2 冲击已确认"),
            })
        return rows

    # Regime 2 产品视角：Shock Detector 完整信号（仅成熟市场候选，与环境表严格对应，不截断）
    state_order = {"SHOCK_CONFIRMED": 0, "SHOCK_CANDIDATE": 1}
    all_shock = scan[scan.shock_state != "SHOCK_NONE"].copy()
    all_shock["_order"] = all_shock["shock_state"].map(state_order)
    all_shock = all_shock.sort_values(["_order", "tail_monthly_sales"], ascending=[True, False])

    def _shocker_rows(sub):
        out = []
        for s in sub.itertuples():
            out.append({"model": f"{s.brand}{s.model}", "market": s.target_market, "state": s.shock_state,
                        "tail": _fmt_num(s.tail_monthly_sales), "top10": bool(s.top10_status),
                        "sustained": s.sustained_months, "ramp": _fmt_num(s.ramp, 2),
                        "vacuum": _env_zh(s.vacuum_crowded), "vacuum_raw": s.vacuum_crowded})
        return out

    regime1_shockers = _shocker_rows(all_shock[all_shock.market_regime == "substitution"])
    regime2_shockers = _shocker_rows(all_shock[all_shock.market_regime == "shock"])

    # 本月结论（从数据提炼）
    r1_up = r1[(r1.market_growth_pct.notna()) & (r1.market_growth_pct > 0) & (r1.total_sales_12m > 500000)]
    r1_best = r1_up.sort_values("substitution_space", ascending=False).head(1)
    r2_conf = mature[mature.confirmed_count >= 1]
    r2_conf_names = "、".join(r.market for r in r2_conf.itertuples()) if len(r2_conf) else "-"
    vac_grow = mature[mature.shock_count == 0].sort_values("market_growth_pct", ascending=False).head(1)
    conclusions = []
    if len(r1_best):
        b = r1_best.iloc[0]
        conclusions.append({"title": "未成熟市场 · 结构性替代机会", "text": f"{b.market} 是替代空间最大（{b.substitution_space:.2f}）且仍在增长（{b.market_growth_pct:+.0f}%）的大市场（{b.total_sales_12m:,.0f} 辆）——Regime 1 最优先的结构性标的。"})
    if len(r2_conf):
        names = "、".join(f"{r.market}(确认 {r.confirmed_count})" for r in r2_conf.itertuples())
        conclusions.append({"title": "成熟市场 · 产品冲击已现", "text": f"{len(r2_conf)} 个成熟市场出现 SHOCK_CONFIRMED 车型：{names}——Regime 2 看产品，冲击者正在形成。"})
    if len(vac_grow):
        v = vac_grow.iloc[0]
        if v.market_growth_pct and v.market_growth_pct > 10:
            conclusions.append({"title": "观察 · 下一个'安静的房间'", "text": f"{v.market}（NEV {v.nev_penetration:.0f}%）增长 {v.market_growth_pct:+.0f}% 却无冲击者进入——若出现强产品可能直接接管。"})

    confirm_all = int((scan.shock_state == "SHOCK_CONFIRMED").sum())
    confirm_shock = int((scan[scan.market_regime == "shock"].shock_state == "SHOCK_CONFIRMED").sum())
    confirm_sub = confirm_all - confirm_shock
    sub_confirm_names = "、".join(f"{r.brand}{r.model}" for r in scan[(scan.market_regime == "substitution") & (scan.shock_state == "SHOCK_CONFIRMED")].itertuples()) or "-"
    kpis = [
        {"value": f"{len(r2_conf)} 个", "label": "成熟市场出现 Confirmed Shock", "hint": f"市场：{r2_conf_names}"},
        {"value": f"{confirm_all} 款", "label": "车型达 SHOCK_CONFIRMED", "hint": f"成熟市场 {confirm_shock} 款（见 Regime 2）+ 未成熟 {confirm_sub} 款（{sub_confirm_names}，见 Regime 1）"},
        {"value": f"{int((df.opportunity == 'REGIME1 替代空间充足').sum())} 个", "label": "未成熟市场替代空间充足", "hint": "Regime 1"},
        {"value": f"{int((df.regime == 'shock').sum())} / {len(df)}", "label": "成熟 / 评估市场", "hint": "NEV≥50% / 总市场"},
    ]

    html = tpl.render(
        static_prefix="../..",
        title="月度市场观察", meta=f"as-of {as_of.strftime('%Y-%m')}",
        hero_title="月度市场机会与产品冲击观察",
        hero_subtitle=f"Market Opportunity Runtime V0.3 · 未成熟市场看结构，成熟市场看产品（as-of {as_of.strftime('%Y-%m')}）",
        kpis=kpis,
        conclusions=conclusions,
        regime1_markets=_mkt_rows(r1.head(14), with_space=True),
        regime1_shockers=regime1_shockers,
        regime2_markets=_mkt_rows(mature, with_space=False),  # 全部 shock 市场，与 Regime 2 表严格对应
        regime2_shockers=regime2_shockers,
        scope={
            "data_source": "dataset/TP&MIX-ways（model_monthly / price_segment_monthly，乘用车上险量）",
            "time_window": f"as-of {as_of.strftime('%Y-%m')} 前 12 个月（崛起识别窗口 12 个月，信号末段 3 个月）",
            "regime_rule": "NEV 渗透率 ≥50% → 冲击驱动 Regime 2（成熟市场 · 看产品）；<50% → 替代驱动 Regime 1（未成熟市场 · 看市场）",
            "threshold": "SHOCK_CONFIRMED=末段月均≥1万且进TOP10且持续≥3月；CANDIDATE=≥2000且(进TOP10或ramp≥2)",
            "method": "market_state_assessment.py · shock_detector_rolling.py · classifier: market_opportunity_v03_research",
        },
    )
    out_path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="市场状态评估（V0.3 Runtime，as-of 任意月）")
    parser.add_argument("--as-of", required=True, help="评估基准月 YYYY-MM")
    parser.add_argument("--output-dir", default=str(_OUTPUT), help="输出根目录")
    parser.add_argument("--format", choices=["text", "json", "html"], default="text", help="输出格式")
    args = parser.parse_args()

    output_root = Path(args.output_dir)
    table_dir = output_root / "tables"
    report_dir = output_root / "reports"
    table_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    model, price = rolling.load()
    as_of = pd.Timestamp(args.as_of + "-01")
    df = assess(price, model, as_of)
    tag = as_of.strftime("%Y-%m")
    csv_path = table_dir / f"market_state_assessment_{tag}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    if args.format == "html":
        scan = rolling.scan(model, price, as_of)
        html_path = report_dir / f"market_state_observation_{tag}.html"
        render_html(df, scan, as_of, html_path)
        print(json.dumps({"status": "success", "as_of": str(as_of)[:7], "markets": len(df),
                          "html": str(html_path), "csv": str(csv_path)}, ensure_ascii=False))
        return

    if args.format == "json":
        print(json.dumps({"status": "success", "as_of": str(as_of)[:7],
                          "script": "research_scripts/market_state_assessment.py",
                          "scope": {"data_source": "dataset/TP&MIX-ways", "window_months": 12,
                                    "regime_threshold": f"NEV {REGIME_THRESHOLD}%"},
                          "result": {"markets": len(df),
                                     "regime_dist": df.regime.value_counts().to_dict(),
                                     "opportunity_markets": df[df.opportunity.str.startswith("REGIME")].to_dict(orient="records")},
                          "artifacts": {"csv": str(csv_path)}}, ensure_ascii=False, indent=2))
    else:
        print(f"=== 市场状态评估（as-of {as_of.strftime('%Y-%m')}，12M 窗口，最低规模 {MIN_MARKET_SALES:,}）===")
        print(f"regime 分布: {df.regime.value_counts().to_dict()}")
        show = df[df.opportunity.str.startswith("REGIME")]
        cols = ["market", "regime", "nev_penetration", "total_sales_12m", "market_growth_pct",
                "substitution_space", "shock_count", "confirmed_count", "vacuum_crowded", "opportunity"]
        print(show[cols].to_string(index=False))
        print(f"\ncsv={csv_path}")


if __name__ == "__main__":
    main()
