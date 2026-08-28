#!/usr/bin/env python3
"""Shock Detector 滚动扫描（每月运行）。

实现 V0.3 classifier spec：configs/studies/classifiers/market_opportunity_v03_research.yaml
对最近 3-6 个月的新车型，输出 SHOCK_NONE / SHOCK_CANDIDATE / SHOCK_CONFIRMED，
附：末段月均销量、TOP10 状态、持续月份、ramp、market regime、CES、vacuum/crowded。

用法：
  python mashang_workspace/research_scripts/shock_detector_rolling.py
  python mashang_workspace/research_scripts/shock_detector_rolling.py --as-of 2026-06
  python mashang_workspace/research_scripts/shock_detector_rolling.py --format json
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

CANDIDATE_TAIL_SALES = 2000
CONFIRMED_TAIL_SALES = 10000
CONFIRMED_SUSTAINED_MONTHS = 3
CES_HIGH = 0.20
WINDOW_MONTHS = 12   # 崛起识别窗口：捕捉上市后 6-12 个月仍在放量的车型（如理想 i6 上市11个月后月销2万+）
TAIL_MONTHS = 3
REGIME_THRESHOLD = 50


def load():
    model = load_tp_and_mix_ways_table("model_monthly").copy()
    price = load_tp_and_mix_ways_table("price_segment_monthly").copy()
    for f in (model, price):
        f["date_month"] = pd.to_datetime(f["date_month"])
    model["price_bucket"] = model["weighted_tp"].map(mv.map_tp_to_5w).replace({"价格缺失/无效": "其他"}).astype(str)
    price["price_bucket"] = price["tp_bucket_5w"].map(mv.clean_text)
    return model, price


def read_ces(pb: str, bt: str, as_of: pd.Timestamp) -> float | None:
    """读取 as-of 对应 freeze 的市场 CES（market_state_v0_2_{freeze}.csv）。"""
    if as_of < pd.Timestamp("2023-04-01"):
        freeze = "202303"
    elif as_of < pd.Timestamp("2024-04-01"):
        freeze = "202403"
    else:
        freeze = "202503"
    path = _OUTPUT / "tables" / f"market_state_v0_2_{freeze}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    row = df[(df.price_bucket == pb) & (df.body_type == bt)]
    return float(row.CES_score.iloc[0]) if len(row) else None


def scan(model: pd.DataFrame, price: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    obs_start = as_of - pd.DateOffset(months=WINDOW_MONTHS)
    tail_start = as_of - pd.DateOffset(months=TAIL_MONTHS - 1)
    obs = model[(model.date_month >= obs_start) & (model.date_month <= as_of)].copy()
    obs = obs[obs.price_bucket != "其他"]

    # 每月每市场 TOP10
    top10 = {}
    for month, d in obs.groupby("date_month"):
        for (pb, bt, ft), g in d.groupby(["price_bucket", "body_type", "fuel_type_group"]):
            if ft != "新能源":
                continue
            rank = g.groupby(["brand", "model"])["sales"].sum().sort_values(ascending=False).head(10)
            top10[(pb, bt, month, "新能源")] = set(rank.index)

    # 新车型：目标市场首次活跃在观测窗口内
    first_map = model[model.price_bucket != "其他"].groupby(["price_bucket", "body_type", "fuel_type_group", "brand", "model"])["date_month"].min()
    rows = []
    for (pb, bt, ft, brand, mdl), first in first_map.items():
        if first < obs_start or first > as_of:
            continue
        d = obs[(obs.price_bucket == pb) & (obs.body_type == bt) & (obs.fuel_type_group == ft)
                & (obs.brand == brand) & (obs.model == mdl)].sort_values("date_month")
        if d.empty:
            continue
        tail = d[d.date_month >= tail_start]
        tail_avg = float(tail.sales.mean()) if len(tail) else 0.0
        first3 = d.head(3)
        first3_avg = float(first3.sales.mean()) if len(first3) else 0.0
        ramp = (tail_avg / first3_avg) if first3_avg > 0 else None
        top10_status = any((pb, bt, m, ft) in top10 and (brand, mdl) in top10[(pb, bt, m, ft)]
                           for m in tail.date_month)
        # 持续月份：截至 as_of 连续月销≥2000
        sustained = 0
        for m in sorted(d.date_month.unique(), reverse=True):
            if float(d[d.date_month == m].sales.sum()) >= CANDIDATE_TAIL_SALES:
                sustained += 1
            else:
                break

        # market regime（该市场 NEV 渗透率，as-of 前 12M）
        p12 = price[(price.date_month >= as_of - pd.DateOffset(months=12)) & (price.date_month <= as_of)]
        mkt = p12[(p12.price_bucket == pb) & (p12.body_type == bt)]
        tot = float(mkt.sales.sum())
        nev = float(mkt[mkt.fuel_type_group == "新能源"].sales.sum())
        nev_pen = nev / tot * 100 if tot else None
        regime = "shock" if (nev_pen is not None and nev_pen >= REGIME_THRESHOLD) else "substitution"

        # vacuum/crowded：该市场末段是否还有其他候选冲击者
        other_candidates = 0
        for (opb, obt, oft, obrand, omdl), ofirst in first_map.items():
            if (opb, obt, oft) != (pb, bt, ft) or (obrand, omdl) == (brand, mdl):
                continue
            if ofirst > as_of or ofirst < obs_start:
                continue
            od = obs[(obs.price_bucket == opb) & (obs.body_type == obt) & (obs.fuel_type_group == oft)
                     & (obs.brand == obrand) & (obs.model == omdl)]
            otail = od[od.date_month >= tail_start]
            if float(otail.sales.mean()) >= CANDIDATE_TAIL_SALES:
                other_candidates += 1
        vacuum = "vacuum" if other_candidates == 0 else "crowded"

        # CES
        ces = read_ces(pb, bt, as_of)

        # 分级
        if tail_avg >= CONFIRMED_TAIL_SALES and top10_status and sustained >= CONFIRMED_SUSTAINED_MONTHS:
            state = "SHOCK_CONFIRMED"
        elif tail_avg >= CANDIDATE_TAIL_SALES and (top10_status or (ramp is not None and ramp >= 2)):
            state = "SHOCK_CANDIDATE"
        else:
            state = "SHOCK_NONE"
        rows.append({
            "brand": brand, "model": mdl, "target_market": f"{pb} {bt} {ft}",
            "first_active": str(first)[:7],
            "tail_monthly_sales": tail_avg, "top10_status": top10_status,
            "sustained_months": sustained, "ramp": ramp,
            "nev_penetration": nev_pen, "market_regime": regime,
            "ces": ces, "vacuum_crowded": vacuum,
            "shock_state": state,
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Shock Detector 滚动扫描（每月运行）")
    parser.add_argument("--as-of", default=None, help="滚动基准月 YYYY-MM（默认数据最新月）")
    parser.add_argument("--output-dir", default=str(_OUTPUT), help="输出根目录")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()

    output_root = Path(args.output_dir)
    table_dir = output_root / "tables"
    report_dir = output_root / "reports"
    table_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    model, price = load()
    if args.as_of:
        as_of = pd.Timestamp(args.as_of + "-01")
    else:
        as_of = model.date_month.max().replace(day=1)

    df = scan(model, price, as_of)
    tag = as_of.strftime("%Y-%m")
    csv_path = table_dir / f"shock_detector_rolling_{tag}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    if args.format == "json":
        cand = df[df.shock_state != "SHOCK_NONE"]
        states = df.shock_state.value_counts().to_dict()
        print(json.dumps({
            "status": "success",
            "script": "research_scripts/shock_detector_rolling.py",
            "command": f"python mashang_workspace/research_scripts/shock_detector_rolling.py --as-of {as_of.strftime('%Y-%m')} --format json",
            "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
            "scope": {
                "data_source": "dataset/TP&MIX-ways (model_monthly / price_segment_monthly)",
                "time_window": {"type": "rolling", "end_date": str(as_of.date()),
                                "observation_months": WINDOW_MONTHS, "tail_months": TAIL_MONTHS},
                "filters": {"as_of": as_of.strftime("%Y-%m"), "fuel_type": "新能源"},
                "metric_definition": "SHOCK_CONFIRMED=尾段月均≥10000且进TOP10且持续≥3月；SHOCK_CANDIDATE=尾段月均≥2000且(进TOP10或ramp≥2)；classifier: configs/studies/classifiers/market_opportunity_v03_research.yaml",
            },
            "result": {
                "summary": f"as-of {as_of.strftime('%Y-%m')}：扫描 {WINDOW_MONTHS} 个月新车型 {len(df)} 个，SHOCK_CONFIRMED {states.get('SHOCK_CONFIRMED', 0)}、SHOCK_CANDIDATE {states.get('SHOCK_CANDIDATE', 0)}、SHOCK_NONE {states.get('SHOCK_NONE', 0)}。",
                "metrics": states,
                "dimensions": [
                    {"name": "market_regime", "items": df.groupby("market_regime").size().reset_index(name="n").to_dict(orient="records")},
                    {"name": "vacuum_crowded", "items": df.groupby("vacuum_crowded").size().reset_index(name="n").to_dict(orient="records")},
                ],
                "tables": [
                    {
                        "name": "shock_candidates",
                        "columns": ["brand", "model", "target_market", "tail_monthly_sales", "top10_status",
                                    "sustained_months", "ramp", "market_regime", "ces", "vacuum_crowded", "shock_state"],
                        "rows": cand.sort_values(["shock_state", "tail_monthly_sales"], ascending=[True, False]).to_dict(orient="records"),
                    }
                ],
            },
            "artifacts": {"csv": str(csv_path), "json": None, "html": None, "png": None},
        }, ensure_ascii=False, indent=2))
    else:
        print(f"=== Shock Detector 滚动扫描（as-of {as_of.strftime('%Y-%m')}，观测窗口近 {WINDOW_MONTHS} 个月）===")
        print(f"状态分布: {df.shock_state.value_counts().to_dict()}")
        print()
        show = df[df.shock_state != "SHOCK_NONE"].sort_values(["shock_state", "tail_monthly_sales"], ascending=[True, False])
        cols = ["brand", "model", "target_market", "tail_monthly_sales", "top10_status", "sustained_months",
                "ramp", "market_regime", "ces", "vacuum_crowded", "shock_state"]
        print(show[cols].to_string(index=False))
        print(f"\ncsv={csv_path}")


if __name__ == "__main__":
    main()
