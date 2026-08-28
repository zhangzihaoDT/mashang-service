#!/usr/bin/env python3
"""Price-band migration: Premiumization vs Price-band migration 判别。

实现 StudySpec: mashang_workspace/configs/studies/specs/price_band_migration.yaml

对每个 车身×能源，把连续价格带放一起看，三期 freeze period 横截面对比，
用 Price Gravity = Σ(价格带中值×销量)/总销量 判别整体成交重心方向，区分：
  - 价格段内部 Premiumization（带内升级：同带消费者向上选择更贵产品）
  - 高价需求下沉（消费降级中的承接者：更高价格带需求下沉到本带）

判定组合（高价需求下沉）：
  本带扩容 + 本带 TOP3 价格升 + 整体价格重心降 + 上一档萎缩

输出：
  outputs/tables/price_band_growth_{window}.csv
  outputs/tables/price_gravity_{window}.csv
  outputs/tables/top3_price_position_{window}.csv
  outputs/tables/migration_verdict_{window}.csv
  outputs/reports/price_band_migration_{window}.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
_RESEARCH_DIR = ROOT / "mashang_workspace" / "research_scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(_RESEARCH_DIR))

from shared.loaders.tp_and_mix_ways_loader import load_tp_and_mix_ways_table  # noqa: E402
import tp_and_mix_ways_market_volume as mv  # noqa: E402

OUTPUT_DIR = ROOT / "mashang_workspace" / "outputs"

FREEZE_PERIODS = [
    {"freeze": "2023-03", "obs_start": "2022-04-01", "obs_end": "2023-03-31"},
    {"freeze": "2024-03", "obs_start": "2023-04-01", "obs_end": "2024-03-31"},
    {"freeze": "2025-03", "obs_start": "2024-04-01", "obs_end": "2025-03-31"},
]

BANDS = ["5万以下", "5-10万", "10-15万", "15-20万", "20-25万", "25-30万",
         "30-35万", "35-40万", "40-45万", "45-50万", "50-55万", "55-60万", "60万以上"]
BAND_INDEX = {b: i for i, b in enumerate(BANDS)}

# 显著性阈值（spec thresholds）
GRAVITY_SIGNIFICANT_PP = 0.5     # 价格重心显著变化（万元）
SHARE_SIGNIFICANT_PP = 1.0       # 份额显著变化（百分点）
BAND_GROWTH_SIGNIFICANT_PCT = 10.0  # 价格带显著增长（%）


def band_midpoint(band: str) -> float | None:
    """价格带中值（万元）。"""
    if band == "5万以下":
        return 2.5
    if band == "60万以上":
        return 65.0
    m = re.match(r"(\d+)-(\d+)万", band)
    return (float(m.group(1)) + float(m.group(2))) / 2 if m else None


def load_data():
    price = load_tp_and_mix_ways_table("price_segment_monthly").copy()
    model = load_tp_and_mix_ways_table("model_monthly").copy()
    for f in (price, model):
        f["date_month"] = pd.to_datetime(f["date_month"])
    price["price_bucket"] = price["tp_bucket_5w"].map(mv.clean_text)
    model["price_bucket"] = model["weighted_tp"].map(mv.map_tp_to_5w).replace({"价格缺失/无效": "其他"})
    model["price_bucket"] = model["price_bucket"].astype(str)
    return price, model


def unit_band_sales(price: pd.DataFrame, obs_start: str, obs_end: str) -> pd.DataFrame:
    """(车身×能源, 价格带) 观测窗口 12M 销量。"""
    p = price[price.date_month.between(obs_start, obs_end)].copy()
    p = p[p.price_bucket.isin(BANDS)]
    return p.groupby(["body_type", "fuel_type_group", "price_bucket"], as_index=False)["sales"].sum()


def compute_band_tables(price: pd.DataFrame, model: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """三期 freeze 的价格带销量/份额/增长 + Price Gravity + TOP3 位置。"""
    band_rows = []
    gravity_rows = []
    pos_rows = []
    prev = None  # 上一 freeze 的 band sales（用于增长/份额/重力变化）

    for period in FREEZE_PERIODS:
        band = unit_band_sales(price, period["obs_start"], period["obs_end"])
        # Price Gravity
        gravity = []
        for (unit, unit_d), g in band.groupby(["body_type", "fuel_type_group"]):
            total = float(g.sales.sum())
            grav = float(sum(band_midpoint(r.price_bucket) * r.sales for r in g.itertuples()) / total) if total else pd.NA
            gravity.append({"body_type": unit, "fuel_type_group": unit_d, "freeze": period["freeze"],
                            "price_gravity": grav, "total_sales": total})
        gdf = pd.DataFrame(gravity)
        gravity_rows.append(gdf)

        # 增长/份额（跨 freeze）
        if prev is not None:
            band = band.merge(prev.rename(columns={"sales": "prev_sales"}),
                              on=["body_type", "fuel_type_group", "price_bucket"], how="left")
            band["growth_pct"] = (band.sales / band.prev_sales - 1) * 100
            band["growth_pct"] = band["growth_pct"].where(band.prev_sales.notna())
            band = band.drop(columns="prev_sales")
        else:
            band["growth_pct"] = pd.NA
        # 份额与份额变化
        band["share_pct"] = band.groupby(["body_type", "fuel_type_group"])["sales"].transform(lambda s: s / s.sum() * 100)
        band["freeze"] = period["freeze"]
        band_rows.append(band)

        # TOP3 价格位置（本档）
        m = model[model.date_month.between(period["obs_start"], period["obs_end"])].copy()
        m = m[m.price_bucket.isin(BANDS) & (m.sales > 0)]
        pos_rows.append(_top3_position(m, period["freeze"]))
        prev = band

    band_df = pd.concat(band_rows, ignore_index=True)
    # 份额变化：跨 freeze
    band_df["share_delta_pp"] = band_df.groupby(["body_type", "fuel_type_group", "price_bucket"])["share_pct"].diff()
    gravity_df = pd.concat(gravity_rows, ignore_index=True)
    gravity_df["gravity_delta"] = gravity_df.groupby(["body_type", "fuel_type_group"])["price_gravity"].diff()
    pos_df = pd.concat(pos_rows, ignore_index=True)
    pos_df["position_delta"] = pos_df.groupby(["body_type", "fuel_type_group", "price_bucket"])["top3_price_position"].diff()
    return band_df, gravity_df, pos_df


def _top3_position(model: pd.DataFrame, freeze: str) -> pd.DataFrame:
    """本档 TOP3 车型加权均价相对价格带的位置（0=下沿，0.5=中位，1=上沿）。"""
    rows = []
    for (bt, ft, pb), g in model.groupby(["body_type", "fuel_type_group", "price_bucket"]):
        d = g.groupby("model", as_index=False)["sales"].sum().sort_values("sales", ascending=False).head(3)
        top3_models = set(d["model"])
        sub = g[g.model.isin(top3_models)]
        tot = float(sub.sales.sum())
        if not tot:
            continue
        tp3_price = float((sub["weighted_tp"] * sub["sales"]).sum()) / tot
        lo, hi = _band_bounds(pb)
        position = (tp3_price - lo) / (hi - lo) if hi > lo else pd.NA
        rows.append({"body_type": bt, "fuel_type_group": ft, "price_bucket": pb, "freeze": freeze,
                     "top3_price": tp3_price, "top3_price_position": position})
    return pd.DataFrame(rows)


def _band_bounds(band: str) -> tuple[float, float]:
    if band == "5万以下":
        return 0.0, 5.0
    if band == "60万以上":
        return 60.0, 70.0
    m = re.match(r"(\d+)-(\d+)万", band)
    return (float(m.group(1)), float(m.group(2))) if m else (0.0, 5.0)


def migration_verdict(band_df: pd.DataFrame, gravity_df: pd.DataFrame, pos_df: pd.DataFrame) -> pd.DataFrame:
    """对每个 车身×能源 判别：消费升级 / 高价需求下沉 / 低段承接+内部高端化 / 无法判别。

    取三期首尾对比（2023-03 → 2025-03 的观测窗口变化）。
    """
    rows = []
    for (bt, ft), unit in band_df.groupby(["body_type", "fuel_type_group"]):
        first, last = "2023-03", "2025-03"
        b_first = unit[unit.freeze == first].set_index("price_bucket")
        b_last = unit[unit.freeze == last].set_index("price_bucket")
        g = gravity_df[(gravity_df.body_type == bt) & (gravity_df.fuel_type_group == ft)]
        gravity_delta = float(g[g.freeze == last].price_gravity.iloc[0] - g[g.freeze == first].price_gravity.iloc[0]) if len(g[g.freeze == last]) and len(g[g.freeze == first]) else pd.NA
        # 扩容带 = 份额上升最多且 12M 销量达到该单位总量 5% 以上的带
        share_delta = (b_last.share_pct - b_first.share_pct).dropna()
        share_delta = share_delta[b_last.loc[share_delta.index, "sales"] >= b_last.sales.sum() * 0.05]
        if share_delta.empty:
            rows.append(_verdict_row(bt, ft, "无法判别", gravity_delta))
            continue
        top_band = share_delta.idxmax()
        band_top3_up = False
        pos_sub = pos_df[(pos_df.body_type == bt) & (pos_df.fuel_type_group == ft) & (pos_df.price_bucket == top_band)]
        if len(pos_sub) and len(pos_sub[pos_sub.freeze == first]) and len(pos_sub[pos_sub.freeze == last]):
            p_first = float(pos_sub[pos_sub.freeze == first].top3_price_position.iloc[0])
            p_last = float(pos_sub[pos_sub.freeze == last].top3_price_position.iloc[0])
            band_top3_up = (p_last - p_first) > 0.05
        # 上一档萎缩
        idx = BAND_INDEX[top_band]
        upper_band = BANDS[idx + 1] if idx + 1 < len(BANDS) else None
        upper_growth = pd.NA
        if upper_band and upper_band in b_first.index and upper_band in b_last.index and b_first.loc[upper_band, "sales"]:
            upper_growth = (b_last.loc[upper_band, "sales"] / b_first.loc[upper_band, "sales"] - 1) * 100
        gravity_down = (not pd.isna(gravity_delta)) and gravity_delta < -GRAVITY_SIGNIFICANT_PP
        gravity_up = (not pd.isna(gravity_delta)) and gravity_delta > GRAVITY_SIGNIFICANT_PP
        upper_shrink = (not pd.isna(upper_growth)) and upper_growth < -BAND_GROWTH_SIGNIFICANT_PCT

        if band_top3_up and gravity_up:
            verdict = "消费升级"
        elif band_top3_up and gravity_down and upper_shrink:
            verdict = "高价需求下沉"
        elif band_top3_up and gravity_down and not upper_shrink:
            verdict = "低段承接+内部高端化"
        elif not band_top3_up and gravity_down:
            verdict = "高价需求下沉"
        else:
            verdict = "无法判别"
        rows.append(_verdict_row(bt, ft, verdict, gravity_delta, top_band, share_delta.loc[top_band], band_top3_up, upper_growth))
    return pd.DataFrame(rows)


def _verdict_row(bt, ft, verdict, gravity_delta, top_band=None, share_delta=None, band_top3_up=None, upper_growth=None):
    return {"body_type": bt, "fuel_type_group": ft, "verdict": verdict,
            "gravity_delta_wan": gravity_delta, "top_band": top_band,
            "top_band_share_delta_pp": share_delta, "top_band_top3_up": band_top3_up,
            "upper_band_growth_pct": upper_growth}


def write_report(band_df, gravity_df, pos_df, verdict, path: Path) -> None:
    lines = [
        "# 产品升级 or 消费降级：价格带迁移判别",
        "",
        "对每个 车身×能源，把连续价格带放一起看，三期 freeze period（2023-03/2024-03/2025-03）横截面对比。",
        "Price Gravity = Σ(价格带中值×销量)/总销量（万元）。",
        "",
        "## 判别结论（每 车身×能源）",
        "",
        "|车身|能源|判别|价格重心变化(万元)|扩容带|扩容带份额变化(pp)|扩容带TOP3上移|上一档增长|",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in verdict.itertuples():
        lines.append(
            f"|{r.body_type}|{r.fuel_type_group}|{r.verdict}|{_fmt(r.gravity_delta_wan)}|{r.top_band or '-'}|"
            f"{_fmt(r.top_band_share_delta_pp)}|{'是' if r.top_band_top3_up is True else '否'}|{_fmt(r.upper_band_growth_pct,'%')}|"
        )
    lines += ["", "## Price Gravity（价格重心，万元）", "",
              "|车身|能源|freeze|价格重心|重心变化(万元)|", "|---|---|---|---:|---:|"]
    for r in gravity_df.itertuples():
        lines.append(f"|{r.body_type}|{r.fuel_type_group}|{r.freeze}|{_fmt(r.price_gravity, ndigits=2)}|{_fmt(r.gravity_delta)}|")
    lines += ["", "## 各价格带销量与份额（跨 freeze）", "",
              "|车身|能源|freeze|价格带|12M销量|增长%|份额%|份额变化(pp)|", "|---|---|---|---|---:|---:|---:|---:|"]
    for r in band_df.sort_values(["body_type", "fuel_type_group", "freeze", "price_bucket"]).itertuples():
        lines.append(
            f"|{r.body_type}|{r.fuel_type_group}|{r.freeze}|{r.price_bucket}|{r.sales:,.0f}|{_fmt(r.growth_pct,'%')}|{_fmt(r.share_pct, ndigits=1)}|{_fmt(r.share_delta_pp, ndigits=1)}|"
        )
    lines += ["", "## 口径与限制", "",
              "- 数据源：`dataset/TP&MIX-ways`，乘用车上险量。",
              "- Price Gravity 价格带中值：5万以下=2.5万，5-10万=7.5万，…，60万以上=65万。",
              "- 判别取三期首尾（2023-03→2025-03 观测窗口）对比；扩容带 = 份额上升且销量≥该单位总量5%。",
              "- TOP3 位置 = 本带 TOP3 车型加权均价在价格带内的位置（0=下沿，1=上沿）。",
              "- 样本为三期 12M 横截面，判别组合为启发式，阈值见 thresholds；信号冲突归为无法判别。"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt(v, suffix="", ndigits=1, na="-"):
    return na if v is None or pd.isna(v) else f"{v:,.{ndigits}f}{suffix}"


def main() -> None:
    parser = argparse.ArgumentParser(description="价格带迁移判别：产品升级 or 消费降级")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="输出根目录")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()

    output_root = Path(args.output_dir)
    table_dir = output_root / "tables"
    report_dir = output_root / "reports"
    table_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    price, model = load_data()
    band_df, gravity_df, pos_df = compute_band_tables(price, model)
    verdict = migration_verdict(band_df, gravity_df, pos_df)

    tag = "2022-04_2026-03"
    band_df.to_csv(table_dir / f"price_band_growth_{tag}.csv", index=False, encoding="utf-8-sig")
    gravity_df.to_csv(table_dir / f"price_gravity_{tag}.csv", index=False, encoding="utf-8-sig")
    pos_df.to_csv(table_dir / f"top3_price_position_{tag}.csv", index=False, encoding="utf-8-sig")
    verdict.to_csv(table_dir / f"migration_verdict_{tag}.csv", index=False, encoding="utf-8-sig")
    report_path = report_dir / f"price_band_migration_{tag}.md"
    write_report(band_df, gravity_df, pos_df, verdict, report_path)

    if args.format == "json":
        print(json.dumps({
            "status": "success",
            "script": "research_scripts/price_band_migration.py",
            "scope": {"freeze_periods": [p["freeze"] for p in FREEZE_PERIODS],
                      "analysis_unit": "body_type × fuel_type_group"},
            "result": verdict.to_dict(orient="records"),
            "artifacts": {"report": str(report_path)},
        }, ensure_ascii=False, indent=2))
    else:
        print("=== 价格带迁移判别（产品升级 or 消费降级）===")
        print(verdict[["body_type", "fuel_type_group", "verdict", "gravity_delta_wan", "top_band", "top_band_top3_up", "upper_band_growth_pct"]].to_string(index=False))
        print(f"\nreport={report_path}")


if __name__ == "__main__":
    main()
