#!/usr/bin/env python3
"""Mature Market Shock Study：成熟市场里什么样的新产品冲击能带来真正扩容。

实现 StudySpec: mashang_workspace/configs/studies/specs/mature_market_shock.yaml

用成功冲击者（SU7 / 问界M7 / 海鸥 / 秦 / 10-15万SUV成功新品）对照同期失败新品，
从爬坡速度、进入 TOP10 速度、性价比攻击、目标市场状态四维提炼冲击者早期特征。

核心判据：区分"把市场做大"（目标市场扩容）与"市场内部分流"（无扩容）。

输出：
  outputs/tables/shock_cases_{window}.csv
  outputs/tables/shock_ramp_{window}.csv
  outputs/tables/shock_target_market_{window}.csv
  outputs/reports/mature_market_shock_{window}.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
_RESEARCH_DIR = ROOT / "mashang_workspace" / "research_scripts"
_OUTPUT = ROOT / "mashang_workspace" / "outputs"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(_RESEARCH_DIR))

from shared.loaders.tp_and_mix_ways_loader import load_tp_and_mix_ways_table  # noqa: E402
import tp_and_mix_ways_market_volume as mv  # noqa: E402

RAMP_BREAKOUT = 2000      # 冲击起点：目标市场月销量首次突破该值
BREAKOUT_12M = 50000      # 爆款判定：起点后 12M 销量 ≥ 该值
TOP10_RANK = 10

# 案例用 (brand, model) 元组：数据里 model 列命名不统一（如 小米→"小米SU7"，深蓝→"S05"）
SUCCESS_CASES = [("小米", "小米SU7"), ("AITO", "问界M7"), ("比亚迪", "海鸥"), ("比亚迪", "秦"), ("比亚迪", "宋"),
                 ("比亚迪", "海狮05"), ("吉利", "银河E5"), ("吉利", "银河L7"), ("零跑", "零跑C10"), ("深蓝", "S05")]
FAIL_CASES = [("哈弗", "哈弗枭龙"), ("哈弗", "哈弗枭龙MAX"), ("蓝电", "蓝电E3"), ("吉利", "几何M6"),
              ("启辰", "VX6"), ("荣威", "D5X"), ("哪吒", "哪吒X"), ("MG", "MG ES5"), ("奇瑞", "风云T6"), ("奇瑞", "舒享家")]

SHOCK_EPOCH = "2023-01-01"  # 冲击起点限定在此之后（区分 2023+ 新品/冲量 vs 2020 上市老车型）


def load_data():
    model = load_tp_and_mix_ways_table("model_monthly").copy()
    model["date_month"] = pd.to_datetime(model["date_month"])
    model["price_bucket"] = model["weighted_tp"].map(mv.map_tp_to_5w).replace({"价格缺失/无效": "其他"})
    model["price_bucket"] = model["price_bucket"].astype(str)
    return model


def find_target_market(model: pd.DataFrame, brand: str, model_name: str) -> tuple[str, str, str] | None:
    """案例销量最大的 (价格带, 车身, 能源) 组合作为目标市场。"""
    sub = model[(model.brand == brand) & (model.model == model_name)]
    if not len(sub):
        return None
    g = sub.groupby(["price_bucket", "body_type", "fuel_type_group"])["sales"].sum()
    g = g[g.index.get_level_values(0) != "其他"]
    return g.idxmax() if len(g) else None


def analyze_case(model: pd.DataFrame, brand: str, model_name: str, outcome: str) -> dict | None:
    """提取单案例冲击特征。"""
    target = find_target_market(model, brand, model_name)
    if target is None:
        return None
    pb, bt, ft = target
    sub = model[(model.brand == brand) & (model.model == model_name)
                & (model.price_bucket == pb) & (model.body_type == bt) & (model.fuel_type_group == ft)].copy()
    sub = sub.sort_values("date_month")
    if sub.empty:
        return None

    first_active = sub.date_month.min()
    # 冲击起点：限定在 SHOCK_EPOCH 之后，取月销量首次突破阈值；若无达标则取该段月销最大月
    sub_epoch = sub[sub.date_month >= SHOCK_EPOCH]
    if sub_epoch.empty:
        sub_epoch = sub
    pos = sub_epoch[sub_epoch.sales >= RAMP_BREAKOUT]
    if len(pos):
        breakout = pos.date_month.min()
    else:
        breakout = sub_epoch.loc[sub_epoch.sales.idxmax(), "date_month"] if len(sub_epoch) else first_active
    b_idx = sub[sub.date_month >= breakout].index[0]

    # 起点后前 3 月爬坡
    m3 = sub[sub.date_month >= breakout].head(3)
    ramp_3m_ratio = float(m3.sales.max() / m3.sales.iloc[0]) if len(m3) and m3.sales.iloc[0] > 0 else None

    # 起点后 12M 销量（目标市场）
    end12 = breakout + pd.DateOffset(months=12)
    s12 = float(sub[(sub.date_month >= breakout) & (sub.date_month < end12)].sales.sum())
    # 起点前 12M 销量（自身基量，判断分流 vs 增量）
    pre12 = float(sub[(sub.date_month >= breakout - pd.DateOffset(months=12)) & (sub.date_month < breakout)].sales.sum())

    # 进入目标市场新能源月销量 TOP10 的月数（相对起点）
    months_to_top10 = None
    month_rank = model[model.date_month >= breakout].groupby("date_month").apply(
        lambda d: _rank_in_market(d, pb, bt, ft, brand, model_name), include_groups=False
    )
    if isinstance(month_rank, pd.Series) and len(month_rank):
        hit = month_rank[month_rank <= TOP10_RANK]
        if len(hit):
            months_to_top10 = (hit.index[0] - first_active).days / 30.4

    # 性价比攻击：起点月新品价格 vs 起点前 12M 在位 TOP3 均价
    entry_price = float(sub[sub.date_month == breakout].weighted_tp.iloc[0]) if len(sub[sub.date_month == breakout]) else None
    inc = _incumbent_top3_price(model, pb, bt, ft, breakout, brand, model_name)
    price_ratio = (entry_price / inc) if (entry_price and inc) else None

    # 目标市场状态（起点月所在观测窗口）
    mkt = model[(model.price_bucket == pb) & (model.body_type == bt) & (model.fuel_type_group == ft)]
    # NEV 渗透率用 price 口径近似：用新能源销量 / 全部能源（本 model 表仅有新能源，改用 price 表）
    ces = _read_ces(pb, bt, breakout)

    # 目标市场扩容：起点后 12M vs 起点前 12M（该市场新能源总量）
    mkt_pre = float(mkt[(mkt.date_month >= breakout - pd.DateOffset(months=12)) & (mkt.date_month < breakout)].sales.sum())
    mkt_post = float(mkt[(mkt.date_month >= breakout) & (mkt.date_month < end12)].sales.sum())
    mkt_growth = (mkt_post / mkt_pre - 1) * 100 if mkt_pre else None
    # 自身对扩容的贡献：s12 / (mkt_post - mkt_pre)
    expansion_contrib = (s12 / (mkt_post - mkt_pre) * 100) if (mkt_post - mkt_pre) > 0 else None

    # 在位 TOP3 集中度（起点前 12M）
    inc_share = _incumbent_top3_share(model, pb, bt, ft, breakout, brand, model_name)

    return {
        "brand": brand, "model": model_name, "outcome": outcome,
        "target_market": f"{pb} {bt} {ft}",
        "first_active_month": str(first_active)[:7], "breakout_month": str(breakout)[:7],
        "ramp_3m_ratio": ramp_3m_ratio, "months_to_top10": months_to_top10,
        "s12_sales": s12, "pre12_sales": pre12,
        "entry_price": entry_price, "incumbent_top3_price": inc, "price_ratio_vs_incumbent": price_ratio,
        "ces_score": ces, "incumbent_top3_share": inc_share,
        "market_12m_growth": mkt_growth, "expansion_contribution_pct": expansion_contrib,
        "is_breakout": s12 >= BREAKOUT_12M,
    }


def _rank_in_market(d, pb, bt, ft, brand, model_name):
    """案例车型在该市场当月的销量排名（1-based）。"""
    dd = d[(d.price_bucket == pb) & (d.body_type == bt) & (d.fuel_type_group == ft)]
    if dd.empty:
        return None
    rank = dd.groupby(["brand", "model"])["sales"].sum().sort_values(ascending=False)
    if (brand, model_name) not in rank.index:
        return None
    return int(rank.index.get_loc((brand, model_name))) + 1


def _incumbent_top3_price(model, pb, bt, ft, breakout, brand, model_name):
    """起点前 12M 在位 TOP3 车型加权均价（排除案例自身）。"""
    mkt = model[(model.price_bucket == pb) & (model.body_type == bt) & (model.fuel_type_group == ft)]
    mkt = mkt[(mkt.date_month >= breakout - pd.DateOffset(months=12)) & (mkt.date_month < breakout)]
    mkt = mkt[~((mkt.brand == brand) & (mkt.model == model_name))]
    if mkt.empty:
        return None
    top3 = mkt.groupby(["brand", "model"])["sales"].sum().sort_values(ascending=False).head(3)
    sub = mkt[mkt.set_index(["brand", "model"]).index.isin(top3.index)]
    tot = float(sub.sales.sum())
    return float((sub.weighted_tp * sub.sales).sum()) / tot if tot else None


def _incumbent_top3_share(model, pb, bt, ft, breakout, brand, model_name):
    mkt = model[(model.price_bucket == pb) & (model.body_type == bt) & (model.fuel_type_group == ft)]
    mkt = mkt[(mkt.date_month >= breakout - pd.DateOffset(months=12)) & (mkt.date_month < breakout)]
    if mkt.empty:
        return None
    tot = float(mkt.sales.sum())
    top3 = mkt.groupby(["brand", "model"])["sales"].sum().sort_values(ascending=False).head(3)
    return float(top3.sum()) / tot * 100 if tot else None


def _read_ces(pb, bt, breakout):
    """读取目标市场在起点所在观测窗口的 CES（market_state_v0_2_{freeze}.csv）。"""
    year = breakout.year
    if pd.Timestamp(breakout) < pd.Timestamp("2023-04-01"):
        freeze = "202303"
    elif pd.Timestamp(breakout) < pd.Timestamp("2024-04-01"):
        freeze = "202403"
    else:
        freeze = "202503"
    path = _OUTPUT / "tables" / f"market_state_v0_2_{freeze}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    row = df[(df.price_bucket == pb) & (df.body_type == bt)]
    return float(row.CES_score.iloc[0]) if len(row) else None


def write_report(rows: pd.DataFrame, path: Path) -> None:
    lines = [
        "# 成熟市场冲击研究：什么冲击能带来真正扩容",
        "",
        "案例对照：成功冲击者（SU7/问界M7/海鸥/秦/10-15万SUV成功新品）vs 同期失败新品。",
        f"冲击起点 = 目标市场月销量首次突破 {RAMP_BREAKOUT} 的月；爆款 = 起点后 12M 销量 ≥ {BREAKOUT_12M}。",
        "",
        "## 案例明细",
        "",
        "|车型|结果|目标市场|起点|爬坡(3M/首月)|进TOP10月|12M销量|自身前12M|价格比(新品/在位TOP3)|CES|在位TOP3集中度|市场12M增长|扩容贡献%|",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows.sort_values(["outcome", "s12_sales"], ascending=[True, False]).itertuples():
        lines.append(
            f"|{r.brand}{r.model}|{r.outcome}|{r.target_market}|{r.breakout_month}|{_fmt(r.ramp_3m_ratio)}|{_fmt(r.months_to_top10)}|"
            f"{r.s12_sales:,.0f}|{r.pre12_sales:,.0f}|{_fmt(r.price_ratio_vs_incumbent)}|{_fmt(r.ces_score)}|{_fmt(r.incumbent_top3_share,'%')}|"
            f"{_fmt(r.market_12m_growth,'%')}|{_fmt(r.expansion_contribution_pct,'%')}|"
        )
    lines += ["", "## 组间对比（成功 vs 失败，中位数）", "",
              "|特征|成功冲击者|失败新品|", "|---|---|---|"]
    metrics = [("ramp_3m_ratio", "爬坡(3M/首月)"), ("months_to_top10", "进入TOP10月数"),
               ("s12_sales", "12M销量"), ("price_ratio_vs_incumbent", "价格比(新品/在位)"),
               ("market_12m_growth", "目标市场12M增长%"), ("expansion_contribution_pct", "扩容贡献%")]
    for col, label in metrics:
        s = rows[rows.outcome == "成功冲击者"][col].median()
        f = rows[rows.outcome == "失败新品"][col].median()
        lines.append(f"|{label}|{_fmt(s)}|{_fmt(f)}|")
    lines += ["", "## 口径与限制", "",
              "- 数据源：`dataset/TP&MIX-ways` model_monthly，乘用车上险量。",
              "- 目标市场 = 案例销量最大的 价格带×车身×能源；问界M7 老款(2022)与换代冲量共享 model 名，冲击起点取月销突破阈值。",
              "- 扩容贡献% = 案例 12M 销量 / 目标市场增量（>100% 表示市场被撑大；负增量时该值缺失）。",
              "- 案例为第一批样本（成功 10 / 失败 10），描述性对比，不构成 Shock Detector 生产规则。"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt(v, suffix="", ndigits=1, na="-"):
    return na if v is None or pd.isna(v) else f"{v:,.{ndigits}f}{suffix}"


def main() -> None:
    parser = argparse.ArgumentParser(description="成熟市场冲击研究：成功 vs 失败新品特征对比")
    parser.add_argument("--output-dir", default=str(_OUTPUT), help="输出根目录")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()

    output_root = Path(args.output_dir)
    table_dir = output_root / "tables"
    report_dir = output_root / "reports"
    table_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    model = load_data()
    rows = []
    for brand, mn in SUCCESS_CASES:
        r = analyze_case(model, brand, mn, "成功冲击者")
        if r:
            rows.append(r)
    for brand, mn in FAIL_CASES:
        r = analyze_case(model, brand, mn, "失败新品")
        if r:
            rows.append(r)
    df = pd.DataFrame(rows)

    tag = "2022-04_2026-03"
    df.to_csv(table_dir / f"shock_cases_{tag}.csv", index=False, encoding="utf-8-sig")
    df.to_csv(table_dir / f"shock_ramp_{tag}.csv", index=False, encoding="utf-8-sig")
    df.to_csv(table_dir / f"shock_target_market_{tag}.csv", index=False, encoding="utf-8-sig")
    report_path = report_dir / f"mature_market_shock_{tag}.md"
    write_report(df, report_path)

    if args.format == "json":
        print(json.dumps({"status": "success", "script": "research_scripts/mature_market_shock.py",
                          "result": df.to_dict(orient="records"), "artifacts": {"report": str(report_path)}},
                         ensure_ascii=False, indent=2))
    else:
        print("=== 成熟市场冲击研究：成功 vs 失败新品 ===")
        print(df[["brand", "model", "outcome", "target_market", "breakout_month", "ramp_3m_ratio",
                  "months_to_top10", "s12_sales", "price_ratio_vs_incumbent", "market_12m_growth", "expansion_contribution_pct"]].to_string(index=False))
        print(f"\nreport={report_path}")


if __name__ == "__main__":
    main()
