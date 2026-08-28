#!/usr/bin/env python3
"""Explore TP&MIX-ways price/body market volume and model concentration."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.loaders.tp_and_mix_ways_loader import load_tp_and_mix_ways_table


OUTPUT_DIR = ROOT / "mashang_workspace" / "outputs"

SEGMENT_KEYS = ["price_bucket", "body_type", "vehicle_level_group", "fuel_type_group"]
PRIMARY_KEYS = ["price_bucket", "body_type", "fuel_type_group"]
RADAR_SEGMENT_KEYS = ["price_bucket", "body_type", "vehicle_level_group", "fuel_type_group"]
OPPORTUNITY_MIN_SALES = 100_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="分析 TP&MIX-ways 近12个月价格段与车型出量结构")
    parser.add_argument("--start", default="2025-08-01", help="起始月份，YYYY-MM-DD")
    parser.add_argument("--end", default="2026-07-01", help="结束月份，YYYY-MM-DD")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="输出根目录")
    return parser.parse_args()


def month_label(value: str) -> str:
    return pd.Timestamp(value).strftime("%Y-%m")


def map_tp_to_5w(value: float) -> str:
    if pd.isna(value) or value <= 0:
        return "价格缺失/无效"
    if value < 50_000:
        return "5万以下"
    if value >= 600_000:
        return "60万以上"
    lower = int(value // 50_000) * 50_000
    upper = lower + 50_000
    return f"{lower // 10_000}-{upper // 10_000}万"


def bucket_sort_key(value: str) -> tuple[int, str]:
    if value == "5万以下":
        return (0, value)
    if value == "60万以上":
        return (99, value)
    match = re.match(r"(\d+)-", value)
    return (int(match.group(1)) if match else 98, value)


def clean_text(value: object) -> str:
    return "未知" if pd.isna(value) else str(value)


def load_window(start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    price = load_tp_and_mix_ways_table("price_segment_monthly").copy()
    model = load_tp_and_mix_ways_table("model_monthly").copy()
    for frame in (price, model):
        frame["date_month"] = pd.to_datetime(frame["date_month"])
    price = price[price.date_month.between(start_ts, end_ts)].copy()
    model = model[model.date_month.between(start_ts, end_ts)].copy()
    return price, model


def build_market(price: pd.DataFrame) -> pd.DataFrame:
    price = price.assign(price_bucket=price["tp_bucket_5w"].map(clean_text))
    grouped = price.groupby(SEGMENT_KEYS, dropna=False, as_index=False).agg(
        sales=("sales", "sum"),
        weighted_tp=("weighted_tp", "mean"),
        active_months=("date_month", "nunique"),
    )
    total = grouped.sales.sum()
    grouped["share_pct"] = grouped.sales / total * 100 if total else 0
    grouped["market_rank"] = grouped.sales.rank(method="first", ascending=False).astype(int)
    return grouped.sort_values("sales", ascending=False)


def build_model_candidates(model: pd.DataFrame) -> pd.DataFrame:
    model = model.copy()
    model["mapped_price_bucket"] = model["weighted_tp"].map(map_tp_to_5w)
    model["brand"] = model["brand"].map(clean_text)
    model["model"] = model["model"].map(clean_text)
    group_keys = ["mapped_price_bucket", "body_type", "vehicle_level_group", "fuel_type_group", "brand", "model"]
    model["tp_sales"] = model["weighted_tp"].where(model["weighted_tp"] > 0, 0) * model["sales"]
    model["active_date"] = model["date_month"].where(model["sales"] > 0)
    grouped = model.groupby(group_keys, dropna=False, as_index=False).agg(
        sales=("sales", "sum"),
        tp_sales=("tp_sales", "sum"),
        first_active_month=("active_date", "min"),
        last_active_month=("active_date", "max"),
    )
    active_months = (
        model[model["sales"] > 0]
        .groupby(group_keys, dropna=False)["date_month"]
        .nunique()
        .reset_index(name="active_months")
    )
    grouped = grouped.merge(active_months, on=group_keys, how="left")
    grouped["weighted_tp"] = grouped["tp_sales"] / grouped["sales"].where(grouped["sales"] > 0)
    grouped = grouped.drop(columns="tp_sales")
    grouped = grouped.rename(columns={"mapped_price_bucket": "price_bucket"})
    return grouped[grouped.sales > 0].copy()


def build_model_radar(model: pd.DataFrame, end: str) -> pd.DataFrame:
    """Rank model families by current scale, momentum, and segment position."""
    model = model.copy()
    model["price_bucket"] = model["weighted_tp"].map(map_tp_to_5w)
    model["brand"] = model["brand"].map(clean_text)
    model["model"] = model["model"].map(clean_text)
    family_keys = ["brand", "model"]
    segment_keys = RADAR_SEGMENT_KEYS + family_keys
    family_monthly = model.groupby(family_keys + ["date_month"], as_index=False).agg(sales=("sales", "sum"))
    end_month = pd.Timestamp(end).replace(day=1)
    recent_start = end_month - pd.DateOffset(months=2)
    prior_start = end_month - pd.DateOffset(months=5)
    recent = family_monthly[family_monthly.date_month.between(recent_start, end_month)]
    prior = family_monthly[family_monthly.date_month.between(prior_start, recent_start - pd.DateOffset(months=1))]
    radar = family_monthly.groupby(family_keys, as_index=False).agg(
        sales_12m=("sales", "sum"),
        active_months=("sales", lambda values: int((values > 0).sum())),
    )
    recent_stats = recent.groupby(family_keys, as_index=False).agg(recent_3m_sales=("sales", "sum"))
    prior_stats = prior.groupby(family_keys, as_index=False).agg(prior_3m_sales=("sales", "sum"))
    radar = radar.merge(recent_stats, on=family_keys, how="left").merge(prior_stats, on=family_keys, how="left")
    radar["recent_3m_avg"] = radar["recent_3m_sales"] / 3
    radar["prior_3m_avg"] = radar["prior_3m_sales"] / 3
    radar["growth_pct"] = (radar["recent_3m_avg"] / radar["prior_3m_avg"] - 1) * 100
    radar.loc[radar["prior_3m_avg"] <= 0, "growth_pct"] = pd.NA

    segment_family = model.groupby(segment_keys, as_index=False).agg(segment_sales=("sales", "sum"))
    primary_segment = segment_family.sort_values("segment_sales", ascending=False).drop_duplicates(family_keys)
    primary_segment = primary_segment.rename(columns={"segment_sales": "primary_segment_sales"})
    radar = radar.merge(primary_segment, on=family_keys, how="left")
    recent_segment = model[model.date_month.between(recent_start, end_month)]
    segment_totals = recent_segment.groupby(RADAR_SEGMENT_KEYS, as_index=False).agg(segment_recent_sales=("sales", "sum"))
    recent_family_segment = recent_segment.groupby(segment_keys, as_index=False).agg(model_recent_segment_sales=("sales", "sum"))
    radar = radar.merge(recent_family_segment, on=segment_keys, how="left").merge(segment_totals, on=RADAR_SEGMENT_KEYS, how="left")
    radar["recent_segment_share_pct"] = radar["model_recent_segment_sales"] / radar["segment_recent_sales"] * 100
    radar["current_rank"] = radar["recent_3m_sales"].rank(method="min", ascending=False).astype("Int64")

    price_group = radar.groupby("price_bucket")["recent_3m_avg"]
    scale_cut = price_group.transform(lambda values: values.quantile(0.8))
    median_scale = price_group.transform("median")
    radar["breakout"] = (radar["recent_3m_avg"] >= median_scale) & (radar["growth_pct"] >= 25)
    radar["dominant"] = (radar["recent_3m_avg"] >= median_scale) & (radar["recent_segment_share_pct"] >= 20)
    radar["scale_hit"] = radar["recent_3m_avg"] >= scale_cut
    radar["persistent"] = (radar["recent_3m_avg"] >= median_scale) & (radar["active_months"] >= 9)
    radar["breakout_type"] = "普通车型"
    radar.loc[radar["persistent"], "breakout_type"] = "持续型爆款"
    radar.loc[radar["dominant"], "breakout_type"] = "统治型爆款"
    radar.loc[radar["breakout"], "breakout_type"] = "增长爆款"
    radar.loc[radar["scale_hit"] & (radar["growth_pct"].fillna(0) >= 0), "breakout_type"] = "规模爆款"
    radar["current_status"] = "稳定"
    radar.loc[radar["growth_pct"] >= 15, "current_status"] = "上升"
    radar.loc[radar["growth_pct"] <= -15, "current_status"] = "下滑"
    return radar.sort_values(["recent_3m_sales", "sales_12m"], ascending=False).reset_index(drop=True)


def attach_top3(market: pd.DataFrame, models: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    rows = []
    for values, segment in market.groupby(keys, dropna=False):
        key_dict = dict(zip(keys, values if isinstance(values, tuple) else (values,)))
        candidates = models
        for key in keys:
            candidates = candidates[candidates[key] == key_dict[key]]
        all_candidates = candidates.copy()
        candidates = all_candidates.sort_values("sales", ascending=False).head(3).copy()
        stable_candidates = all_candidates[all_candidates.active_months >= 9].sort_values("sales", ascending=False).head(3).copy()
        market_sales = float(segment.sales.iloc[0])
        top3_sales = float(candidates.sales.sum())
        stable_sales = float(stable_candidates.sales.sum())
        labels = [
            f"{row.brand}{row.model}（{row.sales / market_sales * 100:.1f}%）"
            for row in candidates.itertuples()
        ]
        rows.append({
            **key_dict,
            "model_top3": "、".join(labels) if labels else "无可映射车型",
            "top1_model": f"{candidates.iloc[0].brand}{candidates.iloc[0].model}" if len(candidates) else "无可映射车型",
            "top3_sales": top3_sales,
            "top3_concentration_pct": top3_sales / market_sales * 100 if market_sales else 0,
            "top3_stable": "、".join(
                f"{row.brand}{row.model}（{row.sales / market_sales * 100:.1f}%）"
                for row in stable_candidates.itertuples()
            ) if len(stable_candidates) else "无满足9个月暴露期车型",
            "stable_top3_concentration_pct": stable_sales / market_sales * 100 if market_sales else 0,
            "stable_model_count": len(stable_candidates),
            "mapped_model_sales_pct": all_candidates.sales.sum() / market_sales * 100 if market_sales else 0,
        })
    return market.merge(pd.DataFrame(rows), on=keys, how="left")


def concentration_label(value: float) -> str:
    if value >= 50:
        return "高集中"
    if value >= 30:
        return "中度集中"
    return "低集中"


def build_price_body_summary(market: pd.DataFrame) -> pd.DataFrame:
    summary = market.groupby(["price_bucket", "body_type"], as_index=False).agg(sales=("sales", "sum"))
    total = summary.sales.sum()
    summary["share_pct"] = summary.sales / total * 100 if total else 0
    return summary.sort_values("sales", ascending=False)


def build_primary_market(market: pd.DataFrame) -> pd.DataFrame:
    return market.groupby(PRIMARY_KEYS, as_index=False).agg(sales=("sales", "sum"))


def build_price_energy_penetration(price: pd.DataFrame, model: pd.DataFrame) -> pd.DataFrame:
    """价格段新能源渗透率（精确）与纯电渗透率（车型 weighted_tp 映射）。"""
    seg = price.copy()
    seg["price_bucket"] = seg["tp_bucket_5w"].map(clean_text)
    grouped = seg.groupby("price_bucket", as_index=False).agg(total_sales=("sales", "sum"))
    nev = seg[seg["fuel_type_group"] == "新能源"].groupby("price_bucket", as_index=False).agg(nev_sales=("sales", "sum"))
    grouped = grouped.merge(nev, on="price_bucket", how="left")
    grouped["nev_penetration_pct"] = grouped.nev_sales / grouped.total_sales * 100

    m = model.copy()
    m["price_bucket"] = m["weighted_tp"].map(map_tp_to_5w).replace({"价格缺失/无效": "其他"})
    m["fuel_type"] = m["fuel_type"].map(clean_text)
    bev = m[m["fuel_type"] == "纯电动"].groupby("price_bucket", as_index=False).agg(bev_sales=("sales", "sum"))
    grouped = grouped.merge(bev, on="price_bucket", how="left")
    grouped["bev_penetration_pct"] = grouped.bev_sales / grouped.total_sales * 100
    grouped["bev_share_of_nev_pct"] = grouped.bev_sales / grouped.nev_sales * 100
    grouped = grouped[grouped.price_bucket != "其他"]
    return grouped.sort_values("price_bucket", key=lambda s: s.map(bucket_sort_key))


def build_segment_growth(price: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """主分析单元最近3个月相对前3个月的增长。"""
    frame = price.copy()
    frame["price_bucket"] = frame["tp_bucket_5w"].map(clean_text)
    monthly = frame.groupby(keys + ["date_month"], as_index=False).agg(sales=("sales", "sum"))
    end_month = monthly.date_month.max()
    recent_start = end_month - pd.DateOffset(months=2)
    prior_start = end_month - pd.DateOffset(months=5)
    recent = monthly[monthly.date_month.between(recent_start, end_month)].groupby(keys, as_index=False).agg(recent_3m_sales=("sales", "sum"))
    prior = monthly[monthly.date_month.between(prior_start, recent_start - pd.DateOffset(months=1))].groupby(keys, as_index=False).agg(prior_3m_sales=("sales", "sum"))
    growth = recent.merge(prior, on=keys, how="left")
    growth["growth_pct"] = (growth.recent_3m_sales / growth.prior_3m_sales - 1) * 100
    growth.loc[growth.prior_3m_sales <= 0, "growth_pct"] = pd.NA
    return growth


def build_market_layers(price: pd.DataFrame, model: pd.DataFrame) -> pd.DataFrame:
    """价格段×车身 市场层：NEV 渗透率与 BEV/NEV 路线（产品规划参考）。"""
    seg = price.copy()
    seg["price_bucket"] = seg["tp_bucket_5w"].map(clean_text)
    seg["body_type"] = seg["body_type"].map(clean_text)
    market = seg.groupby(["price_bucket", "body_type"], as_index=False).agg(total_sales=("sales", "sum"))
    nev = seg[seg["fuel_type_group"] == "新能源"].groupby(["price_bucket", "body_type"], as_index=False).agg(nev_sales=("sales", "sum"))
    market = market.merge(nev, on=["price_bucket", "body_type"], how="left")
    market["nev_penetration_pct"] = market.nev_sales / market.total_sales * 100

    m = model.copy()
    m["price_bucket"] = m["weighted_tp"].map(map_tp_to_5w).replace({"价格缺失/无效": "其他"})
    m["body_type"] = m["body_type"].map(clean_text)
    m["fuel_type"] = m["fuel_type"].map(clean_text)
    m["fuel_type_group"] = m["fuel_type_group"].map(clean_text)
    by_fuel = m.groupby(["price_bucket", "body_type", "fuel_type_group", "fuel_type"], as_index=False).agg(sales=("sales", "sum"))
    nev_model = by_fuel[by_fuel["fuel_type_group"] == "新能源"].groupby(["price_bucket", "body_type"], as_index=False).agg(nev_model_sales=("sales", "sum"))
    bev_model = by_fuel[by_fuel["fuel_type"] == "纯电动"].groupby(["price_bucket", "body_type"], as_index=False).agg(bev_model_sales=("sales", "sum"))
    route = nev_model.merge(bev_model, on=["price_bucket", "body_type"], how="left")
    route["bev_route_pct"] = route.bev_model_sales / route.nev_model_sales * 100
    return market.merge(route, on=["price_bucket", "body_type"], how="left")


def opportunity_profile(openness: float, nev_space: float, bev_route: float) -> str:
    if openness < 0.35:
        return "头部锁死"
    if nev_space >= 0.4 and openness >= 0.5:
        return "开放替代蓝海"
    if nev_space >= 0.4:
        return "替代空间主导"
    if bev_route >= 60:
        return "BEV友好"
    if bev_route < 40:
        return "混动/增程主导"
    return "均衡机会"


def build_opportunity_layers(primary: pd.DataFrame, growth: pd.DataFrame, market_layers: pd.DataFrame) -> pd.DataFrame:
    """三层市场机会：市场开放度 × NEV替代空间 × BEV路线（并列展示，不合成单一指数）。"""
    frame = primary.merge(growth, on=PRIMARY_KEYS, how="left")
    frame = frame.merge(market_layers, on=["price_bucket", "body_type"], how="left")
    frame = frame[frame.price_bucket != "其他"].copy()
    frame["market_openness"] = 1 - frame.top3_concentration_pct / 100
    frame["nev_substitution_space"] = 1 - frame.nev_penetration_pct / 100
    frame["open_convertible_share"] = frame.market_openness * frame.nev_substitution_space
    frame["opportunity_profile"] = frame.apply(
        lambda row: opportunity_profile(row.market_openness, row.nev_substitution_space, row.bev_route_pct), axis=1
    )
    return frame


def write_report(market: pd.DataFrame, primary: pd.DataFrame, price_body: pd.DataFrame, radar: pd.DataFrame, penetration: pd.DataFrame, opportunity: pd.DataFrame, start: str, end: str, path: Path) -> None:
    total = market.sales.sum()
    top = market.head(20).copy()
    primary = primary.sort_values("sales", ascending=False)
    top_primary = primary.iloc[0]
    top_price_body = price_body.iloc[0]
    body_lines = [
        f"- 最大价格段×车身市场：{top_price_body.price_bucket} × {top_price_body.body_type}，累计销量 {top_price_body.sales:,.0f} 辆，占市场 {top_price_body.share_pct:.1f}%。",
        f"- 最大价格段×车身×能源市场：{top_primary.price_bucket} × {top_primary.body_type} × {top_primary.fuel_type_group}，累计销量 {top_primary.sales:,.0f} 辆。",
    ]
    for row in price_body.head(8).itertuples():
        body_lines.append(f"- {row.price_bucket} × {row.body_type}：{row.sales:,.0f} 辆，占比 {row.share_pct:.1f}%。")
    market_total = penetration.total_sales.sum()
    market_nev = penetration.nev_sales.sum()
    market_bev = penetration.bev_sales.sum()
    top_nev_row = penetration.loc[penetration.nev_penetration_pct.idxmax()]
    top_bev_row = penetration.loc[penetration.bev_penetration_pct.idxmax()]
    nev_opportunity = opportunity[
        (opportunity.fuel_type_group == "新能源") & (opportunity.sales >= OPPORTUNITY_MIN_SALES)
    ].sort_values("open_convertible_share", ascending=False)
    if len(nev_opportunity):
        top_opp = nev_opportunity.iloc[0]
        opportunity_bullet = (
            f"- 三层市场机会（开放度×NEV替代空间×BEV路线）最突出的新能源市场：{top_opp.price_bucket} × {top_opp.body_type}"
            f"（开放度 {top_opp.market_openness * 100:.0f}%、NEV替代空间 {top_opp.nev_substitution_space * 100:.0f}%、BEV/NEV {top_opp.bev_route_pct:.0f}%）。"
        )
    else:
        opportunity_bullet = ""
    lines = [
        "# TP&MIX-ways 细分市场出量分析",
        "",
        f"研究窗口：{month_label(start)}—{month_label(end)}（近12个月）",
        "",
        "## 核心结论",
        "",
        f"- 价格段×车身×级别×能源细分市场合计销量：{total:,.0f} 辆。",
        *body_lines,
        f"- 最大细分单元：{top.iloc[0].price_bucket} × {top.iloc[0].body_type} × {top.iloc[0].vehicle_level_group} × {top.iloc[0].fuel_type_group}，累计销量 {top.iloc[0].sales:,.0f} 辆，占市场 {top.iloc[0].share_pct:.1f}%。",
        f"- 整体新能源渗透率 {market_nev / market_total * 100:.1f}%，纯电渗透率 {market_bev / market_total * 100:.1f}%。",
        f"- 新能源渗透率最高价格段：{top_nev_row.price_bucket}（{top_nev_row.nev_penetration_pct:.1f}%）；纯电渗透率最高价格段：{top_bev_row.price_bucket}（{top_bev_row.bev_penetration_pct:.1f}%）。",
        *([opportunity_bullet] if opportunity_bullet else []),
        "- 车型爆款不再用累计销量或9个月门槛单独定义，而是分别识别规模爆款、增长爆款、统治型爆款和持续型爆款。",
        "- TOP3 车型份额基于车型 weighted_tp 映射价格段，属于车型归属近似结果；市场规模本身使用价格段表精确汇总。",
        "",
        "## 各价格段新能源/纯电渗透率",
        "",
        "新能源渗透率来自 `price_segment_monthly` 的 `fuel_type_group`，为精确口径；纯电销量来自 `model_monthly` 中 `fuel_type=纯电动` 的车型，按 `weighted_tp` 映射价格段，为近似口径。",
        "",
        "|价格段|12个月总销量|新能源销量|新能源渗透率|纯电销量|纯电渗透率|纯电占新能源比|",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in penetration.itertuples():
        lines.append(
            f"|{row.price_bucket}|{row.total_sales:,.0f}|{row.nev_sales:,.0f}|{row.nev_penetration_pct:.1f}%|{row.bev_sales:,.0f}|{row.bev_penetration_pct:.1f}%|{row.bev_share_of_nev_pct:.1f}%|"
        )
    lines.append(
        f"|**合计**|{market_total:,.0f}|{market_nev:,.0f}|{market_nev / market_total * 100:.1f}%|{market_bev:,.0f}|{market_bev / market_total * 100:.1f}%|{market_bev / market_nev * 100:.1f}%|"
    )
    lines.extend([
        "",
        "## 车型爆款雷达（车型家族层）",
        "",
        "判定逻辑：先在各价格段内比较车型，再用近3个月月均销量衡量当前规模；近3个月相对前3个月的变化衡量增长；所属细分市场近3个月份额衡量竞争地位；有效月份衡量持续性。增长爆款要求在同价格段内近3个月月均销量不低于中位数且增速至少25%；规模爆款为同价格段内近3个月月均销量前20%且未下滑。",
        "",
        "|排名|价格段|车型|近12月销量|近3月月均|近3月增速|细分市场份额|有效月份|类型|状态|",
        "|---:|---|---|---:|---:|---:|---:|---:|---|---|",
    ])
    for rank, row in enumerate(radar.head(20).itertuples(), 1):
        growth = "-" if pd.isna(row.growth_pct) else f"{row.growth_pct:.1f}%"
        share = "-" if pd.isna(row.recent_segment_share_pct) else f"{row.recent_segment_share_pct:.1f}%"
        lines.append(f"|{rank}|{row.price_bucket}|{row.brand}{row.model}|{row.sales_12m:,.0f}|{row.recent_3m_avg:,.0f}|{growth}|{share}|{row.active_months}|{row.breakout_type}|{row.current_status}|")
    lines.extend([
        "",
        "## 各价格段爆款榜单",
        "",
        "每个价格段单独识别规模、增长、统治和持续型爆款，避免高价车型因绝对销量较低而被系统性排除。",
        "",
        "|价格段|类型|车型|近3个月月均|近3个月增速|细分市场份额|",
        "|---|---|---|---:|---:|---:|",
    ])
    for price_bucket, price_models in radar.groupby("price_bucket", sort=False):
        for label in ["规模爆款", "增长爆款", "统治型爆款", "持续型爆款"]:
            subset = price_models[price_models.breakout_type == label].head(3)
            for row in subset.itertuples():
                growth = "-" if pd.isna(row.growth_pct) else f"{row.growth_pct:.1f}%"
                share = "-" if pd.isna(row.recent_segment_share_pct) else f"{row.recent_segment_share_pct:.1f}%"
                lines.append(f"|{price_bucket}|{label}|{row.brand}{row.model}|{row.recent_3m_avg:,.0f}|{growth}|{share}|")
    lines.extend([
        "",
        "## 三层市场机会（新能源细分市场）",
        "",
        "市场机会拆成三层并列展示，不合成单一指数：市场开放度 = 1 − TOP3集中度（现有玩家是否锁死）；NEV替代空间 = 1 − NEV渗透率（还有多少燃油可被新能源替代，按价格段×车身市场口径）；BEV路线 = BEV÷NEV（新能源消费者中选择纯电的比例，同一市场内新能源与燃油行取值相同）。仅列出12个月规模≥10万辆的新能源市场，表按开放度×替代空间排序。",
        "",
        "|排名|价格段|车身|12个月规模|近3月增速|TOP3集中度|市场开放度|NEV渗透率|NEV替代空间|BEV/NEV|机会画像|",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    for rank, row in enumerate(nev_opportunity.head(15).itertuples(), 1):
        growth = "-" if pd.isna(row.growth_pct) else f"{row.growth_pct:.1f}%"
        bev_route = "-" if pd.isna(row.bev_route_pct) else f"{row.bev_route_pct:.1f}%"
        lines.append(
            f"|{rank}|{row.price_bucket}|{row.body_type}|{row.sales:,.0f}|{growth}|{row.top3_concentration_pct:.1f}%|{row.market_openness * 100:.0f}%|{row.nev_penetration_pct:.1f}%|{row.nev_substitution_space * 100:.0f}%|{bev_route}|{row.opportunity_profile}|"
        )
    contrast = opportunity.set_index(PRIMARY_KEYS)
    for key in [("10-15万", "SUV", "新能源"), ("25-30万", "SUV", "新能源")]:
        if key in contrast.index:
            row = contrast.loc[key]
            bev_route = "-" if pd.isna(row.bev_route_pct) else f"{row.bev_route_pct:.1f}%"
            lines.append(
                f"- {key[0]} 新能源 SUV：开放度 {row.market_openness * 100:.0f}%，NEV替代空间 {row.nev_substitution_space * 100:.0f}%，BEV/NEV {bev_route}，画像 {row.opportunity_profile}。"
            )
    lines.extend([
        "",
        "## 主分析单元 TOP15（价格段×车身×能源）",
        "",
        "|排名|价格段|车身|能源|12个月销量|TOP3车型分布|TOP3集中度|",
        "|---:|---|---|---:|---:|---|---:|",
    ])
    for rank, row in enumerate(primary.head(15).itertuples(), 1):
        lines.append(f"|{rank}|{row.price_bucket}|{row.body_type}|{row.fuel_type_group}|{row.sales:,.0f}|{row.model_top3}|{row.top3_concentration_pct:.1f}%|")
    lines.extend([
        "",
        "## 细分市场 TOP20",
        "",
        "|排名|价格段|车身|级别|能源|12个月销量|市场份额|TOP3车型销量分布|TOP3集中度|判断|",
        "|---:|---|---|---|---|---:|---:|---|---:|---|",
    ])
    for row in top.itertuples():
        lines.append(
            f"|{row.market_rank}|{row.price_bucket}|{row.body_type}|{row.vehicle_level_group}|{row.fuel_type_group}|{row.sales:,.0f}|{row.share_pct:.1f}%|{row.model_top3}|{row.top3_concentration_pct:.1f}%|{concentration_label(row.top3_concentration_pct)}|"
        )
    lines.extend([
        "",
        "## 口径与限制",
        "",
        "- 数据源：`dataset/TP&MIX-ways`，通过 `shared.loaders.tp_and_mix_ways_loader` 读取。",
        "- 销量为乘用车上险量，不等同于批发量或订单量。",
        "- 车型表没有直接价格段字段，使用车型 `weighted_tp` 映射到 5 万元价格带；价格重心缺失/无效的车型未强行归入价格段。",
        "- 新能源渗透率为 `price_segment_monthly` 精确口径；纯电渗透率基于车型 `weighted_tp` 映射，属于近似口径，映射总量与价格段表校验一致（各档比例≈1.0）。",
        "- 三层市场机会的 NEV替代空间与 BEV/NEV 按价格段×车身市场口径计算（BEV/NEV 由车型表映射），同一市场的不同能源细分共享市场层取值；不含价格缺失桶。",
        "- 车型家族层用于识别整体爆款；细分市场份额仍基于 weighted_tp 映射价格段，属于近似归属。",
        "- 新车型不再被9个月门槛排除，而是通过增长爆款单独识别；增速在前3个月无销量时不计算。",
        "- 车型表按品牌、车型和产品维度汇总，不对因燃料/驱动展开形成的重复行直接去重。",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_dir)
    table_dir = output_root / "tables"
    report_dir = output_root / "reports"
    table_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    price, model = load_window(args.start, args.end)
    market = build_market(price)
    candidates = build_model_candidates(model)
    result = attach_top3(market, candidates, SEGMENT_KEYS)
    result["concentration_label"] = result.top3_concentration_pct.map(concentration_label)
    price_body = build_price_body_summary(result)
    primary_market = build_primary_market(result)
    primary_models = candidates.groupby(PRIMARY_KEYS + ["brand", "model"], as_index=False).agg(
        sales=("sales", "sum"), active_months=("active_months", "max"), weighted_tp=("weighted_tp", "mean")
    )
    primary = attach_top3(primary_market, primary_models, PRIMARY_KEYS)
    radar = build_model_radar(model, args.end)
    penetration = build_price_energy_penetration(price, model)
    growth = build_segment_growth(price, PRIMARY_KEYS)
    market_layers = build_market_layers(price, model)
    opportunity = build_opportunity_layers(primary, growth, market_layers)
    result.to_csv(table_dir / "tp_and_mix_ways_market_segments_2025-08_2026-07.csv", index=False, encoding="utf-8-sig")
    price_body.to_csv(table_dir / "tp_and_mix_ways_price_body_summary_2025-08_2026-07.csv", index=False, encoding="utf-8-sig")
    primary.to_csv(table_dir / "tp_and_mix_ways_primary_segments_2025-08_2026-07.csv", index=False, encoding="utf-8-sig")
    penetration.to_csv(table_dir / "tp_and_mix_ways_price_energy_penetration_2025-08_2026-07.csv", index=False, encoding="utf-8-sig")
    opportunity.to_csv(table_dir / "tp_and_mix_ways_market_opportunity_2025-08_2026-07.csv", index=False, encoding="utf-8-sig")

    candidates.sort_values("sales", ascending=False).to_csv(
        table_dir / "tp_and_mix_ways_model_candidates_2025-08_2026-07.csv", index=False, encoding="utf-8-sig"
    )
    radar.to_csv(table_dir / "tp_and_mix_ways_model_breakout_radar_2025-08_2026-07.csv", index=False, encoding="utf-8-sig")
    write_report(result, primary, price_body, radar, penetration, opportunity, args.start, args.end, report_dir / "tp_and_mix_ways_market_volume_2025-08_2026-07.md")
    print(f"market_segments={len(result)}")
    print(f"model_candidates={len(candidates)}")
    print(f"model_radar={len(radar)}")
    print(f"penetration={len(penetration)}")
    print(f"opportunity={len(opportunity)}")
    print(f"report={report_dir / 'tp_and_mix_ways_market_volume_2025-08_2026-07.md'}")
    nev_print = opportunity[
        (opportunity.fuel_type_group == "新能源") & (opportunity.sales >= OPPORTUNITY_MIN_SALES)
    ].sort_values("open_convertible_share", ascending=False)
    print(nev_print.head(15)[PRIMARY_KEYS + ["sales", "market_openness", "nev_penetration_pct", "nev_substitution_space", "bev_route_pct", "opportunity_profile"]].to_string(index=False))


if __name__ == "__main__":
    main()
