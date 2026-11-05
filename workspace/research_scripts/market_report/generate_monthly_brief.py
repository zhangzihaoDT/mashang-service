#!/usr/bin/env python3
"""
Generate TP&MIX-ways Monthly Brief Report.

Reads all 6 TP&MIX-ways parquet tables, computes metrics
per the analysis framework, outputs a structured Markdown report
with JSON data file.

Usage:
    python research_scripts/market_report/generate_monthly_brief.py --month 2026-06
    python research_scripts/market_report/generate_monthly_brief.py --month 2026-06 --format html
    python research_scripts/market_report/generate_monthly_brief.py --month 2026-06 --output outputs/reports/
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

_THIS_DIR = Path(__file__).resolve().parent
_WORKSPACE_ROOT = _THIS_DIR.parents[1]

if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from utils.paths import WORKSPACE_ROOT, PROJECT_ROOT, ensure_shared_on_path
ensure_shared_on_path()

from shared.loaders.tp_and_mix_ways_loader import load_tp_and_mix_ways_table


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wtp(df: pd.DataFrame) -> float:
    """销量加权平均价格重心。"""
    total = df["sales"].sum()
    if total == 0:
        return 0.0
    return float((df["sales"] * df["weighted_tp"]).sum() / total)


def _pct(val: float, total: float) -> float:
    if total == 0:
        return 0.0
    return val / total * 100


def _fmt(val: Any, decimals: int = 0) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "-"
    if isinstance(val, float):
        return f"{val:,.{decimals}f}"
    return str(val)


def _chg(current: float, previous: float) -> tuple[float | None, str]:
    if previous == 0 or pd.isna(previous) or pd.isna(current):
        return None, "-"
    delta = (current / previous - 1) * 100
    arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
    return delta, arrow


def _pct_chg_str(current: float, previous: float, label: str = "") -> str:
    delta, arrow = _chg(current, previous)
    if delta is None:
        return f"{_fmt(current)}"
    return f"{_fmt(current)}  {arrow}{abs(delta):.1f}%"


def _pt_chg_str(current: float, previous: float, label: str = "") -> str:
    """百分点变化。"""
    if pd.isna(previous) or pd.isna(current):
        return _fmt(current, 1)
    diff = current - previous
    arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
    return f"{current:.1f}%  {arrow}{abs(diff):.1f}pct"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

class ReportData:
    def __init__(self, report_month: str):
        self.month = report_month
        self.month_start = f"{report_month}-01"
        dt = datetime.strptime(report_month, "%Y-%m")

        # Previous month
        if dt.month == 1:
            prev = dt.replace(year=dt.year - 1, month=12)
        else:
            prev = dt.replace(month=dt.month - 1)
        self.prev_month_start = f"{prev.year:04d}-{prev.month:02d}-01"

        # Same month last year
        ly = dt.year - 1
        self.ly_month_start = f"{ly:04d}-{dt.month:02d}-01"

        # Load tables
        self.dfs: dict[str, pd.DataFrame] = {}
        for tbl in [
            "market_energy_monthly", "brand_monthly", "model_monthly",
            "geo_monthly", "price_segment_monthly", "product_segment_monthly",
        ]:
            df = load_tp_and_mix_ways_table(tbl)
            if df is not None and not df.empty:
                df["date_month"] = pd.to_datetime(df["date_month"])
                self.dfs[tbl] = df

    def _filter(self, table: str, month: str) -> pd.DataFrame:
        df = self.dfs.get(table)
        if df is None or df.empty:
            return pd.DataFrame()
        return df[df["date_month"] == pd.Timestamp(month)].copy()

    def current(self, table: str) -> pd.DataFrame:
        return self._filter(table, self.month_start)

    def prev(self, table: str) -> pd.DataFrame:
        return self._filter(table, self.prev_month_start)

    def ly(self, table: str) -> pd.DataFrame:
        return self._filter(table, self.ly_month_start)

    def historical(self, table: str) -> pd.DataFrame:
        df = self.dfs.get(table)
        if df is None or df.empty:
            return pd.DataFrame()
        mask = df["date_month"] < pd.Timestamp(self.month_start)
        return df[mask].copy()


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def build_executive_summary(rd: ReportData) -> dict:
    cur = rd.current("market_energy_monthly")
    prev = rd.prev("market_energy_monthly")
    ly = rd.ly("market_energy_monthly")

    if cur.empty:
        return {"summary": "无当月数据", "insights": []}

    total_sales = cur["sales"].sum()
    prev_sales = prev["sales"].sum() if not prev.empty else 0
    ly_sales = ly["sales"].sum() if not ly.empty else 0

    nev = cur[cur["fuel_type_group"] == "新能源"]
    nev_sales = nev["sales"].sum()
    nev_pen = _pct(nev_sales, total_sales)

    prev_nev = prev[prev["fuel_type_group"] == "新能源"]["sales"].sum() if not prev.empty else 0
    prev_total = prev["sales"].sum() if not prev.empty else 0
    prev_nev_pen = _pct(prev_nev, prev_total) if prev_total else 0

    ly_nev = ly[ly["fuel_type_group"] == "新能源"]["sales"].sum() if not ly.empty else 0
    ly_total = ly["sales"].sum() if not ly.empty else 0
    ly_nev_pen = _pct(ly_nev, ly_total) if ly_total else 0

    tp = _wtp(cur)
    prev_tp = _wtp(prev) if not prev.empty else 0

    # MoM / YoY
    mom_sales, mom_arrow = _chg(total_sales, prev_sales)
    yoy_sales, yoy_arrow = _chg(total_sales, ly_sales)

    # Top 5 Insights (compute from broader data)
    insights = _compute_top_insights(rd)

    return {
        "total_sales": int(total_sales),
        "yoy_sales_pct": round(yoy_sales, 1) if yoy_sales is not None else None,
        "yoy_arrow": yoy_arrow,
        "mom_sales_pct": round(mom_sales, 1) if mom_sales is not None else None,
        "mom_arrow": mom_arrow,
        "nev_penetration": round(nev_pen, 1),
        "nev_pen_mom": round(nev_pen - prev_nev_pen, 1),
        "nev_pen_yoy": round(nev_pen - ly_nev_pen, 1),
        "weighted_tp": round(tp),
        "weighted_tp_mom": round(tp - prev_tp),
        "prev_total_sales": int(prev_sales),
        "ly_total_sales": int(ly_sales),
        "insights": insights,
    }


def _compute_top_insights(rd: ReportData) -> list[str]:
    """Compute top 5 notable changes for the month."""
    insights = []
    cur = rd.current("market_energy_monthly")
    prev = rd.prev("market_energy_monthly")
    hist = rd.historical("market_energy_monthly")

    if cur.empty:
        return ["无当月数据"]

    total_sales = cur["sales"].sum()
    prev_total = prev["sales"].sum() if not prev.empty else 0
    nev = cur[cur["fuel_type_group"] == "新能源"]
    nev_sales = nev["sales"].sum()

    # Energy structure
    fuel_cur = cur.groupby("fuel_type")["sales"].sum()
    if not prev.empty:
        fuel_prev = prev.groupby("fuel_type")["sales"].sum()
        for ft in ["插电式混合动力", "纯电动", "增程型电动", "汽油"]:
            if ft in fuel_cur and ft in fuel_prev:
                chg, _ = _chg(fuel_cur[ft], fuel_prev[ft])
                if chg is not None and abs(chg) > 5:
                    direction = "增长" if chg > 0 else "下降"
                    insights.append(f"{ft}{direction} {abs(chg):.0f}%")

    # Brand share changes
    cur_brands = rd.current("brand_monthly")
    prev_brands = rd.prev("brand_monthly")
    if not cur_brands.empty and not prev_brands.empty:
        cb = cur_brands.groupby("brand", observed=True)["sales"].sum()
        pb = prev_brands.groupby("brand", observed=True)["sales"].sum()
        cb_share = cb / cb.sum() * 100
        pb_share = pb / pb.sum() * 100
        all_bs = list(set(cb_share.index) | set(pb_share.index))
        share_chgs = []
        for b in all_bs:
            cs = float(cb_share.get(b, 0))
            ps = float(pb_share.get(b, 0))
            diff = cs - ps
            if diff > 0.3:
                share_chgs.append((b, diff))
        share_chgs.sort(key=lambda x: -x[1])
        for b, diff in share_chgs[:2]:
            insights.append(f"{b}份额+{diff:.1f}pct")

    # Price band growth
    cur_price = rd.current("price_segment_monthly")
    prev_price = rd.prev("price_segment_monthly")
    if not cur_price.empty and not prev_price.empty:
        price_cur = cur_price.groupby("tp_bucket_5w")["sales"].sum()
        price_prev = prev_price.groupby("tp_bucket_5w")["sales"].sum()
        for band in price_cur.index:
            if band in price_prev.index and band in ["20-25万", "25-30万"]:
                chg, _ = _chg(price_cur[band], price_prev[band])
                if chg is not None and chg > 10:
                    insights.append(f"{band}价格带+{chg:.0f}%")

    # Tier city NEV growth
    cur_geo = rd.current("geo_monthly")
    prev_geo = rd.prev("geo_monthly")
    if not cur_geo.empty and not prev_geo.empty:
        for tier in ["三线", "四五线", "新一线"]:
            c = cur_geo[cur_geo["city_tier_group"] == tier]
            p = prev_geo[prev_geo["city_tier_group"] == tier]
            if not c.empty and not p.empty:
                c_sales = c["sales"].sum()
                p_sales = p["sales"].sum()
                c_nev = c[c["fuel_type_group"] == "新能源"]["sales"].sum()
                p_nev = p[p["fuel_type_group"] == "新能源"]["sales"].sum()
                c_pen = _pct(c_nev, c_sales)
                p_pen = _pct(p_nev, p_sales)
                if c_pen - p_pen > 2:
                    insights.append(f"{tier}城市新能源+{c_pen - p_pen:.1f}pct")
                    break

    # Product structure
    cur_prod = rd.current("product_segment_monthly")
    prev_prod = rd.prev("product_segment_monthly")
    if not cur_prod.empty and not prev_prod.empty:
        body_cur = cur_prod.groupby("body_type")["sales"].sum()
        body_prev = prev_prod.groupby("body_type")["sales"].sum()
        for bt in ["SUV", "轿车"]:
            if bt in body_cur and bt in body_prev:
                chg, _ = _chg(body_cur[bt], body_prev[bt])
                if chg is not None and abs(chg) > 3:
                    direction = "扩大" if chg > 0 else "缩小"
                    insights.append(f"{bt}份额{direction}")

    if not insights:
        insights.append("市场整体平稳，无明显结构性变化")
    return insights[:5]


def build_overall_market(rd: ReportData) -> dict:
    cur = rd.current("market_energy_monthly")
    prev = rd.prev("market_energy_monthly")
    ly = rd.ly("market_energy_monthly")
    hist = rd.historical("market_energy_monthly")

    if cur.empty:
        return {"error": "no data"}

    total_sales = cur["sales"].sum()
    prev_total = prev["sales"].sum() if not prev.empty else 0
    ly_total = ly["sales"].sum() if not ly.empty else 0
    tp = _wtp(cur)
    prev_tp = _wtp(prev) if not prev.empty else 0

    # Energy breakdown
    energy_rows = []
    for _, r in cur.iterrows():
        prev_row = prev[prev["fuel_type"] == r["fuel_type"]]
        prev_sale = prev_row["sales"].sum() if not prev.empty else 0
        mom, _ = _chg(r["sales"], prev_sale)
        share = _pct(r["sales"], total_sales)
        energy_rows.append({
            "group": r["fuel_type_group"],
            "type": r["fuel_type"],
            "sales": int(r["sales"]),
            "share_pct": round(share, 1),
            "mom_pct": round(mom, 1) if mom is not None else None,
            "weighted_tp": round(r["weighted_tp"]),
        })

    # NEV penetration
    nev = cur[cur["fuel_type_group"] == "新能源"]
    nev_sales = nev["sales"].sum()
    nev_pen = _pct(nev_sales, total_sales)
    prev_nev = prev[prev["fuel_type_group"] == "新能源"]["sales"].sum() if not prev.empty else 0
    prev_nev_pen = _pct(prev_nev, prev_total) if prev_total else 0
    ly_nev = ly[ly["fuel_type_group"] == "新能源"]["sales"].sum() if not ly.empty else 0
    ly_nev_pen = _pct(ly_nev, ly_total) if ly_total else 0

    # NEV structure (BEV / PHEV / REEV within new energy)
    bev = cur[cur["fuel_type"] == "纯电动"]["sales"].sum()
    phev = cur[cur["fuel_type"] == "插电式混合动力"]["sales"].sum()
    reev = cur[cur["fuel_type"] == "增程型电动"]["sales"].sum()
    nev_total = nev_sales

    return {
        "total_sales": int(total_sales),
        "mom_pct": round((total_sales / prev_total - 1) * 100, 1) if prev_total else None,
        "yoy_pct": round((total_sales / ly_total - 1) * 100, 1) if ly_total else None,
        "weighted_tp": round(tp),
        "tp_mom": round(tp - prev_tp),
        "nev_penetration": round(nev_pen, 1),
        "nev_pen_mom": round(nev_pen - prev_nev_pen, 1),
        "nev_pen_yoy": round(nev_pen - ly_nev_pen, 1),
        "energy_breakdown": energy_rows,
        "nev_structure": {
            "bev_share": round(_pct(bev, nev_total), 1),
            "phev_share": round(_pct(phev, nev_total), 1),
            "reev_share": round(_pct(reev, nev_total), 1),
        },
    }


def build_brand_landscape(rd: ReportData) -> dict:
    cur = rd.current("brand_monthly")
    prev = rd.prev("brand_monthly")
    ly = rd.ly("brand_monthly")

    if cur.empty:
        return {"error": "no data"}

    total_sales = cur["sales"].sum()
    prev_total = prev["sales"].sum() if not prev.empty else 0

    # Top brands
    cur_agg = cur.groupby("brand", observed=True).agg(
        sales=("sales", "sum"), weighted_tp=("weighted_tp", "mean")
    ).reset_index()
    top_brands = cur_agg.nlargest(20, "sales")[["brand", "sales", "weighted_tp"]].copy()
    top_brands["share_pct"] = (_pct(top_brands["sales"], total_sales)).round(1)
    top_brands["sales"] = top_brands["sales"].astype(int)
    top_brands["weighted_tp"] = top_brands["weighted_tp"].round(0).astype(int)

    if not prev.empty:
        prev_agg = prev.groupby("brand", observed=True)["sales"].sum()
        top_brands["prev_sales"] = top_brands["brand"].map(prev_agg).fillna(0).astype(int)
        mom = top_brands["sales"] / top_brands["prev_sales"].replace(0, pd.NA) - 1
        top_brands["mom_pct"] = (mom * 100).round(1)
    else:
        top_brands["mom_pct"] = None

    top20 = top_brands.to_dict(orient="records")

    # Share change
    share_chg = []
    if not prev.empty:
        cu = cur.groupby("brand", observed=True)["sales"].sum()
        pv = prev.groupby("brand", observed=True)["sales"].sum()
        cur_pct = cu / total_sales * 100
        prev_pct = pv / prev_total * 100
        all_b = list(set(cur_pct.index) | set(prev_pct.index))
        share_chg = []
        for b in all_b:
            cp = float(cur_pct.get(b, 0)) if hasattr(cur_pct, 'get') else 0.0
            pp = float(prev_pct.get(b, 0)) if hasattr(prev_pct, 'get') else 0.0
            diff = round(cp - pp, 1)
            if abs(diff) >= 0.1:
                share_chg.append({"brand": b, "share_chg": diff})
    share_chg_sorted = sorted(share_chg, key=lambda x: abs(x["share_chg"]), reverse=True)

    # Group analysis
    group_data = []
    for group_field in ["brand_luxury_group", "ownership_type"]:
        if group_field in cur.columns:
            g_cur = cur.groupby(group_field)["sales"].sum()
            g_cur_pct = (g_cur / total_sales * 100).round(1)
            if not prev.empty:
                g_prev = prev.groupby(group_field)["sales"].sum()
                g_prev_pct = (g_prev / max(prev_total, 1) * 100).round(1)
            else:
                g_prev_pct = pd.Series(dtype=float)
            rows_g = []
            for label in sorted(g_cur.index, key=lambda x: g_cur[x], reverse=True):
                chg = round(g_cur_pct[label] - g_prev_pct.get(label, 0), 1) if label in g_prev_pct.index else None
                rows_g.append({
                    "group": label,
                    "sales": int(g_cur[label]),
                    "share_pct": g_cur_pct[label],
                    "share_chg": chg,
                })
            group_data.append({"field": group_field, "rows": rows_g})

    return {
        "total_sales": int(total_sales),
        "top20": top20,
        "share_changes": share_chg_sorted[:10],
        "group_analysis": group_data,
    }


def build_model_ranking(rd: ReportData) -> dict:
    cur = rd.current("model_monthly")
    prev = rd.prev("model_monthly")

    if cur.empty:
        return {"error": "no data"}

    total_sales = cur["sales"].sum()

    top50 = cur.nlargest(50, "sales")[
        ["brand", "model", "sub_model", "fuel_type", "sales", "weighted_tp"]
    ].copy()
    top50["sales"] = top50["sales"].astype(int)
    top50["weighted_tp"] = top50["weighted_tp"].round(0).astype(int)
    top50["share_pct"] = (_pct(top50["sales"], total_sales)).round(1)

    if not prev.empty:
        prev_top50 = prev.nlargest(50, "sales")[["brand", "model", "sub_model", "sales"]].copy()
        prev_models = set(prev_top50.apply(lambda r: f"{r['brand']}|{r['model']}|{r['sub_model']}", axis=1))
        cur_models = set(top50.apply(lambda r: f"{r['brand']}|{r['model']}|{r['sub_model']}", axis=1))
        new_entries = cur_models - prev_models
    else:
        prev_top50 = pd.DataFrame()
        new_entries = set()

    new_entry_list = []
    for _, r in top50.iterrows():
        key = f"{r['brand']}|{r['model']}|{r['sub_model']}"
        if key in new_entries:
            new_entry_list.append({
                "brand": r["brand"],
                "model": r["model"],
                "sub_model": r["sub_model"],
                "sales": int(r["sales"]),
            })

    # Fuel type breakdown
    nev = cur[cur["fuel_type_group"] == "新能源"]
    bev_top = nev[nev["fuel_type"] == "纯电动"].nlargest(10, "sales")[
        ["brand", "model", "sales"]
    ]
    phev_top = nev[nev["fuel_type"] == "插电式混合动力"].nlargest(10, "sales")[
        ["brand", "model", "sales"]
    ]
    reev_top = nev[nev["fuel_type"] == "增程型电动"].nlargest(10, "sales")[
        ["brand", "model", "sales"]
    ]

    return {
        "top50": top50.to_dict(orient="records"),
        "new_entries_top20": new_entry_list[:10],
        "bev_top10": bev_top.to_dict(orient="records"),
        "phev_top10": phev_top.to_dict(orient="records"),
        "reev_top10": reev_top.to_dict(orient="records"),
    }


def build_product_structure(rd: ReportData) -> dict:
    cur = rd.current("product_segment_monthly")
    prev = rd.prev("product_segment_monthly")

    if cur.empty:
        return {"error": "no data"}

    total_sales = cur["sales"].sum()
    prev_total = prev["sales"].sum() if not prev.empty else 0

    # Body type
    body = cur.groupby("body_type")["sales"].sum().reset_index()
    body["share_pct"] = (_pct(body["sales"], total_sales)).round(1)
    body["sales"] = body["sales"].astype(int)
    if not prev.empty:
        prev_body = prev.groupby("body_type")["sales"].sum()
        body["prev_sales"] = body["body_type"].map(prev_body).fillna(0).astype(int)
        body["mom_pct"] = ((body["sales"] / body["prev_sales"].replace(0, pd.NA) - 1) * 100).round(1)
    else:
        body["mom_pct"] = None

    # Level
    level = cur.groupby("vehicle_level_group")["sales"].sum().reset_index()
    level["share_pct"] = (_pct(level["sales"], total_sales)).round(1)
    level["sales"] = level["sales"].astype(int)
    if not prev.empty:
        prev_level = prev.groupby("vehicle_level_group")["sales"].sum()
        level["prev_sales"] = level["vehicle_level_group"].map(prev_level).fillna(0).astype(int)
        level["mom_pct"] = ((level["sales"] / level["prev_sales"].replace(0, pd.NA) - 1) * 100).round(1)

    # Drive type
    drive = cur.groupby("drive_type_group")["sales"].sum().reset_index()
    drive["share_pct"] = (_pct(drive["sales"], total_sales)).round(1)
    drive["sales"] = drive["sales"].astype(int)

    # Size trends
    size_metrics = {}
    for metric in ["weighted_length_mm", "weighted_width_mm", "weighted_height_mm", "weighted_wheelbase_mm"]:
        if metric in cur.columns:
            val = round(float((cur["sales"] * cur[metric]).sum() / total_sales), 1)
            prev_val = None
            if not prev.empty:
                pv = prev["sales"].sum()
                if pv > 0:
                    prev_val = round(float((prev["sales"] * prev[metric]).sum() / pv), 1)
            size_metrics[metric] = {"current": val, "prev": prev_val, "chg": round(val - prev_val, 1) if prev_val else None}

    return {
        "body_type": body.to_dict(orient="records"),
        "vehicle_level": level.to_dict(orient="records"),
        "drive_type": drive.to_dict(orient="records"),
        "size_metrics": size_metrics,
    }


def build_price_analysis(rd: ReportData) -> dict:
    cur = rd.current("price_segment_monthly")
    prev = rd.prev("price_segment_monthly")

    if cur.empty:
        return {"error": "no data"}

    total_sales = cur["sales"].sum()

    bands = cur.groupby("tp_bucket_5w").agg(
        sales=("sales", "sum"),
        weighted_tp=("weighted_tp", "mean"),
    ).reset_index()
    bands["share_pct"] = (_pct(bands["sales"], total_sales)).round(1)
    bands["sales"] = bands["sales"].astype(int)
    if not prev.empty:
        prev_bands = prev.groupby("tp_bucket_5w")["sales"].sum()
        bands["prev_sales"] = bands["tp_bucket_5w"].map(prev_bands).fillna(0).astype(int)
        bands["mom_pct"] = ((bands["sales"] / bands["prev_sales"].replace(0, pd.NA) - 1) * 100).round(1)
    else:
        bands["mom_pct"] = None
    bands = bands.sort_values("sales", ascending=False)

    # NEV price band structure
    nev = cur[cur["fuel_type_group"] == "新能源"]
    nev_bands = nev.groupby(["tp_bucket_5w", "body_type"])["sales"].sum().reset_index()
    nev_bands["sales"] = nev_bands["sales"].astype(int)
    nev_bands = nev_bands.sort_values("sales", ascending=False)

    return {
        "price_bands": bands.to_dict(orient="records"),
        "nev_price_bands": nev_bands.to_dict(orient="records"),
    }


def build_geographic(rd: ReportData) -> dict:
    cur = rd.current("geo_monthly")
    prev = rd.prev("geo_monthly")

    if cur.empty:
        return {"error": "no data"}

    total_sales = cur["sales"].sum()

    # Province top20
    prov = cur.groupby("province")["sales"].sum().reset_index()
    prov["share_pct"] = (_pct(prov["sales"], total_sales)).round(1)
    prov["sales"] = prov["sales"].astype(int)
    prov = prov.sort_values("sales", ascending=False).head(20)

    # City top20
    city = cur.groupby("city")["sales"].sum().reset_index()
    city["share_pct"] = (_pct(city["sales"], total_sales)).round(1)
    city["sales"] = city["sales"].astype(int)
    city = city.sort_values("sales", ascending=False).head(20)

    # City tier
    tiers = cur.groupby("city_tier_group").agg(
        sales=("sales", "sum"),
    ).reset_index()
    tiers["share_pct"] = (_pct(tiers["sales"], total_sales)).round(1)
    tiers["sales"] = tiers["sales"].astype(int)
    if not prev.empty:
        prev_tier = prev.groupby("city_tier_group")["sales"].sum()
        tiers["prev_sales"] = tiers["city_tier_group"].map(prev_tier).fillna(0).astype(int)
        tiers["mom_pct"] = ((tiers["sales"] / tiers["prev_sales"].replace(0, pd.NA) - 1) * 100).round(1)
    else:
        tiers["mom_pct"] = None

    # NEV penetration by tier
    nev_pen_tier = []
    for tier in cur["city_tier_group"].unique():
        t_cur = cur[cur["city_tier_group"] == tier]
        t_nev = t_cur[t_cur["fuel_type_group"] == "新能源"]["sales"].sum()
        t_total = t_cur["sales"].sum()
        pen = round(_pct(t_nev, t_total), 1) if t_total else 0

        t_prev = prev[prev["city_tier_group"] == tier] if not prev.empty else pd.DataFrame()
        if not t_prev.empty:
            t_prev_nev = t_prev[t_prev["fuel_type_group"] == "新能源"]["sales"].sum()
            t_prev_total = t_prev["sales"].sum()
            prev_pen = round(_pct(t_prev_nev, t_prev_total), 1) if t_prev_total else 0
        else:
            prev_pen = 0

        nev_pen_tier.append({
            "tier": tier,
            "nev_penetration": pen,
            "pen_chg": round(pen - prev_pen, 1),
        })

    # Region
    region = cur.groupby("region_group")["sales"].sum().reset_index()
    region["share_pct"] = (_pct(region["sales"], total_sales)).round(1)
    region["sales"] = region["sales"].astype(int)
    region = region.sort_values("sales", ascending=False)
    if not prev.empty:
        prev_region = prev.groupby("region_group")["sales"].sum()
        region["prev_sales"] = region["region_group"].map(prev_region).fillna(0).astype(int)
        region["mom_pct"] = ((region["sales"] / region["prev_sales"].replace(0, pd.NA) - 1) * 100).round(1)

    return {
        "province_top20": prov.to_dict(orient="records"),
        "city_top20": city.to_dict(orient="records"),
        "city_tier": tiers.to_dict(orient="records"),
        "nev_penetration_by_tier": nev_pen_tier,
        "region": region.to_dict(orient="records"),
    }


def build_deep_insight(rd: ReportData) -> dict:
    """Identify winners, losers, structural changes."""
    cur_market = rd.current("market_energy_monthly")
    prev_market = rd.prev("market_energy_monthly")
    cur_brand = rd.current("brand_monthly")
    prev_brand = rd.prev("brand_monthly")
    cur_price = rd.current("price_segment_monthly")
    prev_price = rd.prev("price_segment_monthly")
    cur_prod = rd.current("product_segment_monthly")
    prev_prod = rd.prev("product_segment_monthly")

    winners = []
    losers = []
    structural_changes = []
    price_changes = []
    new_trends = []

    # Brand winner/loser
    if not cur_brand.empty and not prev_brand.empty and cur_brand["sales"].sum() > 0:
        cb = cur_brand.groupby("brand")["sales"].sum()
        pb = prev_brand.groupby("brand")["sales"].sum()
        total_c = cur_brand["sales"].sum()
        total_p = prev_brand["sales"].sum()
        cur_share = cb / total_c * 100
        prev_share = pb / total_p * 100
        merged = pd.DataFrame({"share": cur_share, "share_prev": prev_share}).fillna(0)
        merged["chg"] = merged["share"] - merged["share_prev"]
        top_winner = merged.nlargest(1, "chg").iloc[0] if len(merged) > 0 else None
        top_loser = merged.nsmallest(1, "chg").iloc[0] if len(merged) > 0 else None
        if top_winner is not None and top_winner["chg"] > 0.3:
            winners.append({"type": "品牌", "name": top_winner.name, "change": round(top_winner["chg"], 1), "unit": "pct"})
        if top_loser is not None and top_loser["chg"] < -0.3:
            losers.append({"type": "品牌", "name": top_loser.name, "change": round(abs(top_loser["chg"]), 1), "unit": "pct", "direction": "down"})

    # Price band winner
    if not cur_price.empty and not prev_price.empty:
        cp = cur_price.groupby("tp_bucket_5w")["sales"].sum()
        pp = prev_price.groupby("tp_bucket_5w")["sales"].sum()
        merged_p = pd.DataFrame({"cur": cp, "prev": pp}).fillna(0)
        merged_p["mom"] = (merged_p["cur"] / merged_p["prev"].replace(0, pd.NA) - 1) * 100
        top_band = merged_p.nlargest(1, "mom").iloc[0] if len(merged_p) > 0 else None
        if top_band is not None and top_band["mom"] > 5:
            price_changes.append(f"{top_band.name}增长{top_band['mom']:.0f}%")

    # Structural: SUV share
    if not cur_prod.empty and not prev_prod.empty:
        body_c = cur_prod.groupby("body_type")["sales"].sum()
        body_p = prev_prod.groupby("body_type")["sales"].sum()
        suv_c = body_c.get("SUV", 0)
        suv_p = body_p.get("SUV", 0)
        total_c = body_c.sum()
        total_p = body_p.sum()
        if total_c > 0 and total_p > 0:
            suv_share_c = suv_c / total_c * 100
            suv_share_p = suv_p / total_p * 100
            if suv_share_c - suv_share_p > 0.5:
                structural_changes.append(f"SUV 份额升至 {suv_share_c:.1f}%")
            elif suv_share_p - suv_share_c > 0.5:
                structural_changes.append(f"SUV 份额降至 {suv_share_c:.1f}%")

    # Luxury share
    if not cur_brand.empty and not prev_brand.empty:
        for gf in ["brand_luxury_group", "ownership_type"]:
            if gf in cur_brand.columns:
                cg = cur_brand.groupby(gf)["sales"].sum()
                pg = prev_brand.groupby(gf)["sales"].sum()
                total_c = cg.sum()
                total_p = pg.sum()
                for label in ["豪华", "自主", "合资"]:
                    if label in cg.index and label in pg.index:
                        cs = cg[label] / total_c * 100
                        ps = pg[label] / total_p * 100
                        diff = cs - ps
                        if abs(diff) > 0.3:
                            direction = "升至" if diff > 0 else "降至"
                            structural_changes.append(f"{label}品牌份额{direction}{cs:.1f}%")

    # New trends: 4WD, large SUV
    if not cur_prod.empty and not prev_prod.empty:
        drive_c = cur_prod.groupby("drive_type_group")["sales"].sum()
        drive_p = prev_prod.groupby("drive_type_group")["sales"].sum()
        total_c = drive_c.sum()
        total_p = drive_p.sum()
        for dt in ["四轮驱动", "电动四驱", "前置四驱", "后置四驱"]:
            if dt in drive_c and dt in drive_p:
                share_c = drive_c[dt] / total_c * 100
                share_p = drive_p[dt] / total_p * 100
                if share_c - share_p > 0.5:
                    new_trends.append(f"四驱({dt})占比+{share_c - share_p:.1f}pct")
                    break

    # ReEV trend
    cur_fuel = cur_market.groupby("fuel_type")["sales"].sum()
    prev_fuel = prev_market.groupby("fuel_type")["sales"].sum() if not prev_market.empty else pd.Series(dtype=float)
    for ft in ["增程型电动"]:
        if ft in cur_fuel and ft in prev_fuel:
            chg, _ = _chg(cur_fuel[ft], prev_fuel[ft])
            if chg is not None and abs(chg) > 3:
                direction = "增长" if chg > 0 else "放缓/下降"
                new_trends.append(f"增程式{direction} {abs(chg):.0f}%")

    return {
        "winners": winners[:3],
        "losers": losers[:3],
        "structural_changes": structural_changes[:3],
        "price_changes": price_changes[:3],
        "new_trends": new_trends[:3],
    }


def build_change_detection(rd: ReportData) -> dict:
    """Historical percentile-based anomaly detection."""
    cur = rd.current("market_energy_monthly")
    hist = rd.historical("market_energy_monthly")
    cur_brand = rd.current("brand_monthly")
    hist_brand = rd.historical("brand_monthly")
    cur_price = rd.current("price_segment_monthly")
    prev_price = rd.prev("price_segment_monthly")
    hist_price = rd.historical("price_segment_monthly")
    cur_prod = rd.current("product_segment_monthly")
    prev_prod = rd.prev("product_segment_monthly")
    hist_prod = rd.historical("product_segment_monthly")
    cur_geo = rd.current("geo_monthly")
    prev_geo = rd.prev("geo_monthly")
    hist_geo = rd.historical("geo_monthly")

    changes = []
    prev = rd.prev("market_energy_monthly")

    # Market total sales
    if not hist.empty and not cur.empty:
        total_c = cur["sales"].sum()
        prev_total = prev["sales"].sum() if not prev.empty else 0
        if prev_total:
            mom = total_c / prev_total - 1
            hist_mom = _calc_historical_mom(hist, "sales")
            if hist_mom:
                pctile = _percentile(hist_mom, mom)
                level = "🔴" if pctile >= 95 or pctile <= 5 else ("🟡" if pctile >= 90 or pctile <= 10 else "🟢")
                changes.append({
                    "module": "市场", "indicator": "总销量",
                    "change": f"{mom * 100:+.1f}% MoM",
                    "percentile": f"P{int(pctile)}",
                    "level": level,
                })

    # NEV penetration
    if not hist.empty and not cur.empty:
        nev_c = cur[cur["fuel_type_group"] == "新能源"]["sales"].sum()
        total_c = cur["sales"].sum()
        pen_c = nev_c / total_c * 100
        if not prev.empty:
            nev_p = prev[prev["fuel_type_group"] == "新能源"]["sales"].sum()
            total_p = prev["sales"].sum()
            pen_p = nev_p / total_p * 100 if total_p else 0
            pen_chg = pen_c - pen_p
            hist_pen = []
            for m in sorted(hist["date_month"].unique()):
                h = hist[hist["date_month"] == m]
                if not h.empty:
                    hn = h[h["fuel_type_group"] == "新能源"]["sales"].sum()
                    ht = h["sales"].sum()
                    hist_pen.append(hn / ht * 100 if ht else 0)
            if hist_pen:
                pctile = _percentile(hist_pen, pen_c)
                level = "🔴" if pctile >= 95 else ("🟡" if pctile >= 90 else "🟢")
                changes.append({
                    "module": "能源", "indicator": "新能源渗透率",
                    "change": f"{pen_c:.1f}% ({pen_chg:+.1f}pct)",
                    "percentile": f"P{int(pctile)}",
                    "level": level,
                })

    # PHEV share
    if not hist.empty and not cur.empty:
        phev_c = cur[cur["fuel_type"] == "插电式混合动力"]["sales"].sum()
        total_c = cur["sales"].sum()
        phev_share_c = phev_c / total_c * 100
        if not prev.empty:
            phev_p = prev[prev["fuel_type"] == "插电式混合动力"]["sales"].sum()
            total_p = prev["sales"].sum()
            phev_share_p = phev_p / total_p * 100 if total_p else 0
            hist_phev = []
            for m in sorted(hist["date_month"].unique()):
                h = hist[hist["date_month"] == m]
                if not h.empty:
                    hp = h[h["fuel_type"] == "插电式混合动力"]["sales"].sum()
                    ht = h["sales"].sum()
                    hist_phev.append(hp / ht * 100 if ht else 0)
            if hist_phev:
                pctile = _percentile(hist_phev, phev_share_c)
                if pctile >= 90:
                    level = "🔴" if pctile >= 95 else "🟡"
                    changes.append({
                        "module": "能源", "indicator": "PHEV 份额",
                        "change": f"{phev_share_c:.1f}% ({phev_share_c - phev_share_p:+.1f}pct)",
                        "percentile": f"P{int(pctile)}",
                        "level": level,
                    })

    # Price band anomaly
    if not hist_price.empty and not cur_price.empty:
        for band in ["20-25万", "25-30万"]:
            cb = cur_price[cur_price["tp_bucket_5w"] == band]["sales"].sum()
            pb = prev_price[prev_price["tp_bucket_5w"] == band]["sales"].sum() if not prev_price.empty else 0
            # MoM change for this band
            if cb and pb:
                mom = cb / pb - 1
                # Historical MoM for this band
                hist_band_sales = {}
                for m in sorted(hist_price["date_month"].unique()):
                    h = hist_price[hist_price["date_month"] == m]
                    hist_band_sales[m] = h[h["tp_bucket_5w"] == band]["sales"].sum()
                hist_band_mom = []
                prev_m = None
                for m in sorted(hist_band_sales.keys()):
                    if prev_m is not None and hist_band_sales[prev_m] > 0:
                        hist_band_mom.append(hist_band_sales[m] / hist_band_sales[prev_m] - 1)
                    prev_m = m
                if hist_band_mom:
                    pctile = _percentile(hist_band_mom, mom)
                    if pctile >= 90:
                        level = "🔴" if pctile >= 95 else "🟡"
                        changes.append({
                            "module": "价格", "indicator": f"{band}",
                            "change": f"{mom * 100:+.1f}%",
                            "percentile": f"P{int(pctile)}",
                            "level": level,
                        })

    # SUV/Large car share anomaly
    if not hist_prod.empty and not cur_prod.empty:
        suv_c = cur_prod[cur_prod["body_type"] == "SUV"]["sales"].sum()
        total_c = cur_prod["sales"].sum()
        suv_share_c = suv_c / total_c * 100
        prev_suv = prev_prod[prev_prod["body_type"] == "SUV"]["sales"].sum() if not prev_prod.empty else 0
        prev_total = prev_prod["sales"].sum() if not prev_prod.empty else 0
        suv_share_p = prev_suv / prev_total * 100 if prev_total else 0
        hist_suv = []
        for m in sorted(hist_prod["date_month"].unique()):
            h = hist_prod[hist_prod["date_month"] == m]
            if not h.empty:
                hs = h[h["body_type"] == "SUV"]["sales"].sum()
                ht = h["sales"].sum()
                hist_suv.append(hs / ht * 100 if ht else 0)
        if hist_suv:
            pctile = _percentile(hist_suv, suv_share_c)
            if pctile >= 90:
                level = "🔴" if pctile >= 95 else "🟡"
                changes.append({
                    "module": "产品", "indicator": "SUV 份额",
                    "change": f"{suv_share_c:.1f}% ({suv_share_c - suv_share_p:+.1f}pct)",
                    "percentile": f"P{int(pctile)}",
                    "level": level,
                })

    # Tier city NEV penetration
    if not hist_geo.empty and not cur_geo.empty:
        for tier in ["三线", "四五线"]:
            tc = cur_geo[cur_geo["city_tier_group"] == tier]
            if tc.empty:
                continue
            tc_nev = tc[tc["fuel_type_group"] == "新能源"]["sales"].sum()
            tc_total = tc["sales"].sum()
            tc_pen = tc_nev / tc_total * 100 if tc_total else 0
            tp = prev_geo[prev_geo["city_tier_group"] == tier] if not prev_geo.empty else pd.DataFrame()
            if not tp.empty:
                tp_nev = tp[tp["fuel_type_group"] == "新能源"]["sales"].sum()
                tp_total = tp["sales"].sum()
                tp_pen = tp_nev / tp_total * 100 if tp_total else 0
                hist_pen = []
                for m in sorted(hist_geo["date_month"].unique()):
                    h = hist_geo[hist_geo["date_month"] == m]
                    ht = h[h["city_tier_group"] == tier]
                    if not ht.empty:
                        hn = ht[ht["fuel_type_group"] == "新能源"]["sales"].sum()
                        htot = ht["sales"].sum()
                        hist_pen.append(hn / htot * 100 if htot else 0)
                if hist_pen:
                    pctile = _percentile(hist_pen, tc_pen)
                    if pctile >= 90:
                        level = "🔴" if pctile >= 95 else "🟡"
                        changes.append({
                            "module": "区域", "indicator": f"{tier}新能源渗透",
                            "change": f"{tc_pen:.1f}% ({tc_pen - tp_pen:+.1f}pct)",
                            "percentile": f"P{int(pctile)}",
                            "level": level,
                        })

    return {"changes": changes}


def _calc_historical_mom(hist: pd.DataFrame, metric: str) -> list[float]:
    moms = []
    months = sorted(hist["date_month"].unique())
    for i in range(1, len(months)):
        m1 = hist[hist["date_month"] == months[i - 1]][metric].sum()
        m2 = hist[hist["date_month"] == months[i]][metric].sum()
        if m1 > 0:
            moms.append(m2 / m1 - 1)
    return moms


def _percentile(values: list[float], val: float) -> float:
    if not values:
        return 50
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if val <= sorted_vals[0]:
        return 1
    if val >= sorted_vals[-1]:
        return 100
    import bisect
    idx = bisect.bisect_left(sorted_vals, val)
    return idx / n * 100


def HistMonthly(df: pd.DataFrame, month) -> float | None:
    """Helper: total sales for a given month in historical data."""
    d = df[df["date_month"] == month]
    if d.empty:
        return None
    return d["sales"].sum()


# ---------------------------------------------------------------------------
# Report renderers
# ---------------------------------------------------------------------------

def render_markdown(report: dict) -> str:
    lines = []
    es = report.get("executive_summary", {})
    month = report.get("report_month", "")
    lines.append(f"# TP&MIX-ways Monthly Brief — {month}")
    lines.append(f"")
    lines.append("---")
    lines.append("")

    # ① Executive Summary
    lines.append("## ① Executive Summary")
    lines.append("")
    lines.append(f"**市场规模**")
    lines.append(f"- 总销量: {_fmt(es.get('total_sales'))} 辆")
    if es.get("yoy_sales_pct") is not None:
        lines.append(f"- 同比: {es['yoy_arrow']}{abs(es['yoy_sales_pct']):.1f}%")
    if es.get("mom_sales_pct") is not None:
        lines.append(f"- 环比: {es['mom_arrow']}{abs(es['mom_sales_pct']):.1f}%")
    lines.append(f"")
    lines.append(f"**新能源渗透率**: {es.get('nev_penetration', '-')}% ({es.get('nev_pen_mom', 0):+.1f}pct MoM)")
    lines.append(f"**价格重心**: {_fmt(es.get('weighted_tp'))} 元 ({es.get('weighted_tp_mom', 0):+,} MoM)")
    lines.append("")
    insights = es.get("insights", [])
    if insights:
        lines.append("**Top 5 Insights**")
        for ins in insights:
            lines.append(f"- {ins}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ② Overall Market
    om = report.get("overall_market", {})
    if om and "error" not in om:
        lines.append("## ② Overall Market")
        lines.append("")
        lines.append(f"| 指标 | 本月 | 变化 |")
        lines.append(f"|------|------|------|")
        lines.append(f"| 总销量 | {_fmt(om.get('total_sales'))} | MoM {_fmt(om.get('mom_pct'), 1)}% / YoY {_fmt(om.get('yoy_pct'), 1)}% |")
        tp_mom_val = om.get('tp_mom')
        tp_mom_str = f"{tp_mom_val:+,}" if isinstance(tp_mom_val, (int, float)) else "-"
        lines.append(f"| 价格重心 | {_fmt(om.get('weighted_tp'))} 元 | {tp_mom_str} |")
        lines.append(f"| 新能源渗透率 | {om.get('nev_penetration', '-')}% | MoM {om.get('nev_pen_mom', 0):+.1f}pct / YoY {om.get('nev_pen_yoy', 0):+.1f}pct |")
        lines.append("")
        ns = om.get("nev_structure", {})
        if ns:
            lines.append(f"**新能源结构**: BEV {ns.get('bev_share', '-')}% / PHEV {ns.get('phev_share', '-')}% / REEV {ns.get('reev_share', '-')}%")
        lines.append("")
        lines.append("**能源结构明细**")
        lines.append("")
        lines.append("| 组 | 类型 | 销量 | 占比 | MoM | 价格重心 |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for row in om.get("energy_breakdown", []):
            mom_str = f"{row['mom_pct']:+.1f}%" if row.get("mom_pct") is not None else "-"
            lines.append(f"| {row['group']} | {row['type']} | {_fmt(row['sales'])} | {row['share_pct']}% | {mom_str} | {_fmt(row['weighted_tp'])} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ③ Brand Landscape
    bl = report.get("brand_landscape", {})
    if bl and "error" not in bl:
        lines.append("## ③ Brand Landscape")
        lines.append("")
        lines.append("### Top 20 品牌")
        lines.append("")
        lines.append("| # | 品牌 | 销量 | 份额 | MoM | 价格重心 |")
        lines.append("|---|------|---:|---:|---:|---:|")
        for i, b in enumerate(bl.get("top20", []), 1):
            mom_str = f"{b['mom_pct']:+.1f}%" if b.get("mom_pct") is not None else "-"
            lines.append(f"| {i} | {b['brand']} | {_fmt(b['sales'])} | {b['share_pct']}% | {mom_str} | {_fmt(b['weighted_tp'])} |")
        lines.append("")

        sc = bl.get("share_changes", [])
        if sc:
            lines.append("### 品牌份额变化 Top 10")
            lines.append("")
            lines.append("| 品牌 | 变化 |")
            lines.append("|------|-----:|")
            for s in sc:
                arrow = "↑" if s["share_chg"] > 0 else "↓"
                lines.append(f"| {s['brand']} | {arrow}{abs(s['share_chg']):.1f}pct |")
            lines.append("")

        ga = bl.get("group_analysis", [])
        for g in ga:
            label_map = {"brand_luxury_group": "豪华分组", "ownership_type": "所有权"}
            lines.append(f"### 按 {label_map.get(g['field'], g['field'])}")
            lines.append("")
            lines.append("| 分组 | 销量 | 份额 | 份额变化 |")
            lines.append("|------|---:|---:|---:|")
            for r in g["rows"]:
                chg_str = f"{r['share_chg']:+.1f}pct" if r.get("share_chg") is not None else "-"
                lines.append(f"| {r['group']} | {_fmt(r['sales'])} | {r['share_pct']}% | {chg_str} |")
            lines.append("")

        lines.append("---")
        lines.append("")

    # ④ Model Ranking
    mr = report.get("model_ranking", {})
    if mr and "error" not in mr:
        lines.append("## ④ Model Ranking")
        lines.append("")
        lines.append("### Top 50 车型（前 20 展示）")
        lines.append("")
        lines.append("| # | 品牌 | 车型 | 子车型 | 燃料 | 销量 | 份额 | 价格重心 |")
        lines.append("|---|------|------|--------|------|---:|---:|---:|")
        for i, r in enumerate(mr.get("top50", [])[:20], 1):
            lines.append(f"| {i} | {r['brand']} | {r['model']} | {r['sub_model']} | {r['fuel_type']} | {_fmt(r['sales'])} | {r['share_pct']}% | {_fmt(r['weighted_tp'])} |")
        lines.append("")

        new_entries = mr.get("new_entries_top20", [])
        if new_entries:
            lines.append("### 新进入 TOP50 车型")
            lines.append("")
            lines.append("| 品牌 | 车型 | 子车型 | 销量 |")
            lines.append("|------|------|--------|---:|")
            for r in new_entries:
                lines.append(f"| {r['brand']} | {r['model']} | {r['sub_model']} | {_fmt(r['sales'])} |")
            lines.append("")

        for label, key in [("纯电动 BEV Top 10", "bev_top10"), ("插电式混合动力 PHEV Top 10", "phev_top10"), ("增程型电动 REEV Top 10", "reev_top10")]:
            rows = mr.get(key, [])
            if rows:
                lines.append(f"### {label}")
                lines.append("")
                lines.append("| 品牌 | 车型 | 销量 |")
                lines.append("|------|------|---:|")
                for r in rows:
                    lines.append(f"| {r['brand']} | {r['model']} | {_fmt(r['sales'])} |")
                lines.append("")

        lines.append("---")
        lines.append("")

    # ⑤ Product Structure
    ps = report.get("product_structure", {})
    if ps and "error" not in ps:
        lines.append("## ⑤ Product Structure")
        lines.append("")

        for label_key in [("body_type", "车身类型"), ("vehicle_level", "车型级别"), ("drive_type", "驱动形式")]:
            rows = ps.get(label_key[0], [])
            if rows:
                lines.append(f"### {label_key[1]}")
                lines.append("")
                cols = list(rows[0].keys())
                # Filter columns
                display_cols = [c for c in cols if c not in ("prev_sales",)]
                lines.append("| " + " | ".join(display_cols) + " |")
                lines.append("| " + " | ".join(["---"] * len(display_cols)) + " |")
                for r in rows:
                    vals = []
                    for c in display_cols:
                        v = r.get(c)
                        if c == "mom_pct" and v is not None:
                            vals.append(f"{v:+.1f}%")
                        elif c == "share_pct":
                            vals.append(f"{v}%")
                        elif isinstance(v, float):
                            vals.append(f"{v:.1f}" if abs(v) < 100 else _fmt(v))
                        else:
                            vals.append(str(v))
                    lines.append("| " + " | ".join(vals) + " |")
                lines.append("")

        sm = ps.get("size_metrics", {})
        if sm:
            lines.append("### 产品尺寸趋势")
            lines.append("")
            labels = {
                "weighted_length_mm": "平均车长(mm)",
                "weighted_width_mm": "平均车宽(mm)",
                "weighted_height_mm": "平均车高(mm)",
                "weighted_wheelbase_mm": "平均轴距(mm)",
            }
            lines.append("| 指标 | 本月 | 上月 | 变化 |")
            lines.append("|------|---:|---:|---:|")
            for k, v in sm.items():
                prev_str = _fmt(v.get("prev"), 1) if v.get("prev") else "-"
                chg_str = f"{v['chg']:+.1f}" if v.get("chg") else "-"
                lines.append(f"| {labels.get(k, k)} | {_fmt(v['current'], 1)} | {prev_str} | {chg_str} |")
            lines.append("")

        lines.append("---")
        lines.append("")

    # ⑥ Price Analysis
    pa = report.get("price_analysis", {})
    if pa and "error" not in pa:
        lines.append("## ⑥ Price Analysis")
        lines.append("")
        lines.append("### 价格带销量分布")
        lines.append("")
        lines.append("| 价格带 | 销量 | 份额 | MoM |")
        lines.append("|--------|---:|---:|---:|")
        for r in pa.get("price_bands", []):
            mom_str = f"{r['mom_pct']:+.1f}%" if r.get("mom_pct") is not None else "-"
            lines.append(f"| {r['tp_bucket_5w']} | {_fmt(r['sales'])} | {r['share_pct']}% | {mom_str} |")
        lines.append("")

        lines.append("---")
        lines.append("")

    # ⑦ Geographic
    geo = report.get("geographic", {})
    if geo and "error" not in geo:
        lines.append("## ⑦ Geographic")
        lines.append("")

        lines.append("### 省份 Top 20")
        lines.append("")
        lines.append("| # | 省份 | 销量 | 份额 |")
        lines.append("|---|------|---:|---:|")
        for i, r in enumerate(geo.get("province_top20", []), 1):
            lines.append(f"| {i} | {r['province']} | {_fmt(r['sales'])} | {r['share_pct']}% |")
        lines.append("")

        lines.append("### 城市线级")
        lines.append("")
        lines.append("| 线级 | 销量 | 份额 | MoM | 新能源渗透率 |")
        lines.append("|------|---:|---:|---:|---:|")
        for r in geo.get("city_tier", []):
            mom_str = f"{r['mom_pct']:+.1f}%" if r.get("mom_pct") is not None else "-"
            pen = ""
            for pt in geo.get("nev_penetration_by_tier", []):
                if pt["tier"] == r["city_tier_group"]:
                    pen = f"{pt['nev_penetration']}% ({pt['pen_chg']:+.1f}pct)"
                    break
            lines.append(f"| {r['city_tier_group']} | {_fmt(r['sales'])} | {r['share_pct']}% | {mom_str} | {pen} |")
        lines.append("")

        lines.append("### 区域")
        lines.append("")
        lines.append("| 区域 | 销量 | 份额 | MoM |")
        lines.append("|------|---:|---:|---:|")
        for r in geo.get("region", []):
            mom_str = f"{r['mom_pct']:+.1f}%" if r.get("mom_pct") is not None else "-"
            lines.append(f"| {r['region_group']} | {_fmt(r['sales'])} | {r['share_pct']}% | {mom_str} |")
        lines.append("")

        lines.append("---")
        lines.append("")

    # ⑧ Deep Insight
    di = report.get("deep_insight", {})
    if di:
        lines.append("## ⑧ Deep Insight")
        lines.append("")
        for label, key in [("本月最大的赢家", "winners"), ("本月最大的输家", "losers")]:
            items = di.get(key, [])
            if items:
                lines.append(f"**{label}**")
                for item in items:
                    chg_val = item.get('change', 0)
                    if item.get('direction') == 'down':
                        lines.append(f"- {item['name']}（{item['type']}，↓{chg_val}{item['unit']}）")
                    else:
                        lines.append(f"- {item['name']}（{item['type']}，{chg_val:+.1f}{item['unit']}）")
                lines.append("")

        for label, key in [("本月最大的结构变化", "structural_changes"), ("本月最大的价格变化", "price_changes"), ("本月值得关注的新趋势", "new_trends")]:
            items = di.get(key, [])
            if items:
                lines.append(f"**{label}**")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

        lines.append("---")
        lines.append("")

    # ⑨ Watch List
    lines.append("## ⑨ Watch List")
    lines.append("")
    lines.append("| 指标 | 本月 | 上月 | 趋势 |")
    lines.append("|------|----:|----:|------|")
    om_data = report.get("overall_market", {})
    es_data = report.get("executive_summary", {})
    bl_data = report.get("brand_landscape", {})
    ps_data = report.get("product_structure", {})

    total_sales = es_data.get("total_sales", 0)
    prev_total = es_data.get("prev_total_sales", 0)
    _, tr = _chg(total_sales, prev_total)

    nev_pen = es_data.get("nev_penetration", 0)
    nev_pen_prev = nev_pen - es_data.get("nev_pen_mom", 0)
    _, nr = _chg(nev_pen, nev_pen_prev)
    nr = "↑" if es_data.get("nev_pen_mom", 0) > 0 else ("↓" if es_data.get("nev_pen_mom", 0) < 0 else "→")

    tp = es_data.get("weighted_tp", 0)
    tp_prev = tp - es_data.get("weighted_tp_mom", 0)
    _, tpr = _chg(tp, tp_prev)

    # SUV share
    body_rows = ps_data.get("body_type", [])
    suv_share = ""
    suv_share_prev = ""
    for r in body_rows:
        if r.get("body_type") == "SUV":
            suv_share = f"{r['share_pct']}%"
            suv_share_prev = f"{_pct(r.get('prev_sales', 0), sum(br.get('sales', 0) for br in body_rows) or 1):.1f}%" if r.get("prev_sales") else "-"
            break

    wk = report.get("watch_list", {})
    used_labels = set()
    items = [
        ("总销量", _fmt(total_sales), _fmt(prev_total), tr),
        ("新能源渗透", f"{nev_pen:.1f}%", f"{nev_pen_prev:.1f}%", nr),
        ("平均成交价", f"{_fmt(tp)}元", f"{_fmt(tp_prev)}元", tpr),
        ("SUV 份额", suv_share, suv_share_prev, wk.get("suv_trend", "→")),
    ]
    for label, cur_val, prev_val, trend in items:
        if label in used_labels:
            continue
        used_labels.add(label)
        lines.append(f"| {label} | {cur_val} | {prev_val} | {trend} |")
    lines.append("")

    lines.append("---")
    lines.append("")

    # ⑩ Change Detection
    cd = report.get("change_detection", {})
    changes = cd.get("changes", [])
    if changes:
        lines.append("## ⑩ Change Detection")
        lines.append("")
        lines.append("| 模块 | 指标 | 本月变化 | 历史分位 | 异常 |")
        lines.append("|------|------|----------|----------|------|")
        for c in changes:
            lines.append(f"| {c['module']} | {c['indicator']} | {c['change']} | {c['percentile']} | {c['level']} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*报告由 TP&MIX-ways Monthly Brief 自动生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

_CSS_CACHE: str | None = None


def _load_css() -> str:
    global _CSS_CACHE
    if _CSS_CACHE is not None:
        return _CSS_CACHE
    css_path = WORKSPACE_ROOT / "templates" / "report_style.css"
    if css_path.exists():
        _CSS_CACHE = css_path.read_text(encoding="utf-8")
    else:
        _CSS_CACHE = ""
    return _CSS_CACHE


def _es(report: dict, key: str, default: Any = "-") -> Any:
    es = report.get("executive_summary", {})
    return es.get(key, default)


def _h(val: Any) -> str:
    if val is None or (isinstance(val, float) and (pd.isna(val) or val != val)):
        return "-"
    if isinstance(val, float):
        return f"{val:,.0f}"
    return str(val)


def _hdelta(val: Any, up_str: str = "up", down_str: str = "down") -> str:
    if val is None:
        return "neutral"
    if isinstance(val, str):
        return "neutral"
    return up_str if val > 0 else down_str if val < 0 else "neutral"


def _htr(val: Any) -> str:
    if val is None or val == "-":
        return "→"
    if isinstance(val, str):
        return val
    return "↑" if val > 0 else "↓" if val < 0 else "→"


def _hfmt(val: Any, pct: bool = False) -> str:
    if val is None:
        return "-"
    if pct:
        return f"{val:.1f}%"
    if isinstance(val, float):
        return f"{val:,.0f}" if abs(val) >= 1000 else f"{val:.1f}"
    return str(val)


def _section(title: str, content: str, note: str = "") -> str:
    n = f'<p class="section-note">{note}</p>' if note else ""
    return f'<section class="report-section"><h2 class="section-title">{title}</h2>{n}{content}</section>'


def _table(headers: list[str], rows: list[list[str]], num_cols: set[int] | None = None,
           right_cols: set[int] | None = None, delta_cols: dict[int, str] | None = None) -> str:
    if not rows:
        return '<p class="section-note">暂无数据</p>'
    num_cols = num_cols or set()
    right_cols = right_cols or set()
    delta_cols = delta_cols or {}
    hd = "".join(f"<th>{h}</th>" for h in headers)
    rds = []
    for row in rows:
        cds = ""
        for ci, c in enumerate(row):
            cls = ""
            if ci in num_cols:
                cls = ' class="num"'
            elif ci in right_cols:
                cls = ' class="num"'
            if ci in delta_cols:
                cls = f' class="{delta_cols[ci]}"'
            cds += f"<td{cls}>{c}</td>"
        rds.append(f"<tr>{cds}</tr>")
    return f'<div class="table-wrap"><table class="report-table"><thead><tr>{hd}</tr></thead><tbody>{"".join(rds)}</tbody></table></div>'


def render_html(report: dict, css: str, brand_assets_prefix: str = ".") -> str:
    es = report.get("executive_summary", {})
    om = report.get("overall_market", {})
    bl = report.get("brand_landscape", {})
    mr = report.get("model_ranking", {})
    ps = report.get("product_structure", {})
    pa = report.get("price_analysis", {})
    geo = report.get("geographic", {})
    di = report.get("deep_insight", {})
    cd = report.get("change_detection", {})
    month = report.get("report_month", "")

    ts = _h(es.get("total_sales"))
    yoy = es.get("yoy_sales_pct")
    mom = es.get("mom_sales_pct")
    nev_pen = es.get("nev_penetration")
    tp = _h(es.get("weighted_tp"))
    tp_mom = es.get("weighted_tp_mom")

    kpi_cards = f"""<div class="kpi-grid">
  <div class="kpi-card"><div class="label">总销量</div><div class="value">{ts}</div><div class="change {_hdelta(mom)}">环比 {_hfmt(mom)}%</div></div>
  <div class="kpi-card"><div class="label">同比</div><div class="value">{_hfmt(yoy, True)}</div><div class="change {_hdelta(yoy)}">vs 2025-06</div></div>
  <div class="kpi-card"><div class="label">新能源渗透率</div><div class="value">{nev_pen}%</div><div class="change {_hdelta(es.get('nev_pen_mom'))}">{es.get('nev_pen_mom', 0):+.1f}pct MoM</div></div>
  <div class="kpi-card"><div class="label">价格重心</div><div class="value">¥{tp}</div><div class="change {_hdelta(tp_mom)}">{tp_mom:+,} MoM</div></div>
</div>"""

    insights = es.get("insights", [])
    ins_cards = ""
    if insights:
        ins_rows = "".join(f'<div class="summary-card"><div class="summary-value">{ins}</div><div class="summary-label">Insight</div></div>' for ins in insights)
        ins_cards = f'<div class="summary-grid">{ins_rows}</div>'

    # Overall Market
    om_sections = ""
    if om and "error" not in om:
        ns = om.get("nev_structure", {})
        ns_str = f"BEV {ns.get('bev_share', '-')}% / PHEV {ns.get('phev_share', '-')}% / REEV {ns.get('reev_share', '-')}%" if ns else ""
        om_meta = f'<div class="summary-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:16px">' \
                  f'<div class="summary-card"><div class="summary-value">{_h(om.get("total_sales"))}</div><div class="summary-label">总销量</div></div>' \
                  f'<div class="summary-card"><div class="summary-value">{_hfmt(om.get("mom_pct"), True)}</div><div class="summary-label">环比</div></div>' \
                  f'<div class="summary-card"><div class="summary-value">{_hfmt(om.get("yoy_pct"), True)}</div><div class="summary-label">同比</div></div>' \
                  f'<div class="summary-card"><div class="summary-value">{ns_str}</div><div class="summary-label">新能源结构</div></div></div>'
        er = om.get("energy_breakdown", [])
        eh = ["组", "类型", "销量", "占比", "MoM", "价格重心"]
        erows = [[r["group"], r["type"], _hfmt(r["sales"]), f'{r["share_pct"]}%',
                  f'{r.get("mom_pct", 0):+.1f}%' if r.get("mom_pct") else "-", _hfmt(r["weighted_tp"])] for r in er]
        om_sections = om_meta + _table(eh, erows, num_cols={2, 5}, right_cols={3, 4})
    else:
        om_sections = '<p class="section-note">暂无市场数据</p>'

    # Brand Landscape
    bl_sections = ""
    if bl and "error" not in bl:
        top20 = bl.get("top20", [])
        bh = ["#", "品牌", "销量", "份额", "MoM", "价格重心"]
        brows = [[str(i), r["brand"], _hfmt(r["sales"]), f'{r["share_pct"]}%',
                  f'{r.get("mom_pct", 0):+.1f}%' if r.get("mom_pct") else "-", _hfmt(r["weighted_tp"])]
                 for i, r in enumerate(top20, 1)]
        bl_sections = _table(bh, brows, num_cols={2, 5}, right_cols={3, 4})

        sc = bl.get("share_changes", [])
        if sc:
            sc_rows = [[f'<span class="{_hdelta(s["share_chg"], "delta-positive", "delta-negative")}">{s["share_chg"]:+.1f}pct</span>', s["brand"]] for s in sc[:10]]
            bl_sections += '<h3 style="font-size:14px;margin:16px 0 8px;color:var(--zh-deep-blue)">品牌份额变化 Top 10</h3>' + \
                          _table(["变化", "品牌"], [[r[1], r[0]] for r in sc_rows], delta_cols={0: "delta-positive"})

        ga = bl.get("group_analysis", [])
        for g in ga:
            label_map = {"brand_luxury_group": "豪华分组", "ownership_type": "所有权"}
            gr_rows = []
            for r in g["rows"]:
                chg_str = f'{r["share_chg"]:+.1f}pct' if r.get("share_chg") is not None else "-"
                gr_rows.append([r["group"], _hfmt(r["sales"]), f'{r["share_pct"]}%', chg_str])
            bl_sections += f'<h3 style="font-size:14px;margin:16px 0 8px;color:var(--zh-deep-blue)">按 {label_map.get(g["field"], g["field"])}</h3>' + \
                          _table(["分组", "销量", "份额", "份额变化"], gr_rows, num_cols={1})
    else:
        bl_sections = '<p class="section-note">暂无品牌数据</p>'

    # Model Ranking
    mr_sections = ""
    if mr and "error" not in mr:
        top50 = mr.get("top50", [])
        mh = ["#", "品牌", "车型", "燃料", "销量", "份额"]
        mrows = [[str(i), r["brand"], r["model"], r["fuel_type"], _hfmt(r["sales"]), f'{r["share_pct"]}%']
                 for i, r in enumerate(top50[:20], 1)]
        mr_sections = _table(mh, mrows, num_cols={4}, right_cols={5})

        for label, key in [("纯电动 BEV Top 10", "bev_top10"), ("插电式混合动力 PHEV Top 10", "phev_top10"), ("增程式 REEV Top 10", "reev_top10")]:
            rows = mr.get(key, [])
            if rows:
                r2 = [[r["brand"], r["model"], _hfmt(r["sales"])] for r in rows]
                mr_sections += f'<h3 style="font-size:14px;margin:16px 0 8px;color:var(--zh-deep-blue)">{label}</h3>' + \
                              _table(["品牌", "车型", "销量"], r2, num_cols={2})
    else:
        mr_sections = '<p class="section-note">暂无车型数据</p>'

    # Product Structure
    ps_sections = ""
    if ps and "error" not in ps:
        for label_key, title in [("body_type", "车身类型"), ("vehicle_level", "车型级别"), ("drive_type", "驱动形式")]:
            rows = ps.get(label_key, [])
            if rows:
                ph = list(rows[0].keys())
                pr = []
                for r in rows:
                    pr.append([f'{r.get("share_pct", 0)}%' if c == "share_pct"
                               else f'{r.get("mom_pct", 0):+.1f}%' if c == "mom_pct" and r.get("mom_pct") else str(r.get(c, ""))
                               for c in ph])
                ps_sections += f'<h3 style="font-size:14px;margin:14px 0 8px;color:var(--zh-deep-blue)">{title}</h3>' + \
                              _table(ph, pr, num_cols={1})

        sm = ps.get("size_metrics", {})
        if sm:
            labels = {"weighted_length_mm": "平均车长", "weighted_width_mm": "平均车宽",
                      "weighted_height_mm": "平均车高", "weighted_wheelbase_mm": "平均轴距"}
            sr = [[labels.get(k, k), f'{v["current"]:.1f}mm', f'{v["prev"]:.1f}mm' if v.get("prev") else "-",
                   f'{v["chg"]:+.1f}mm' if v.get("chg") else "-"] for k, v in sm.items()]
            ps_sections += f'<h3 style="font-size:14px;margin:14px 0 8px;color:var(--zh-deep-blue)">产品尺寸趋势</h3>' + \
                          _table(["指标", "本月", "上月", "变化"], sr)
    else:
        ps_sections = '<p class="section-note">暂无产品结构数据</p>'

    # Price Analysis
    pa_sections = ""
    if pa and "error" not in pa:
        bands = pa.get("price_bands", [])
        pah = ["价格带", "销量", "份额", "MoM"]
        par = [[r["tp_bucket_5w"], _hfmt(r["sales"]), f'{r["share_pct"]}%',
                f'{r.get("mom_pct", 0):+.1f}%' if r.get("mom_pct") else "-"] for r in bands]
        pa_sections = _table(pah, par, num_cols={1}, right_cols={2, 3})
    else:
        pa_sections = '<p class="section-note">暂无价格数据</p>'

    # Geographic
    geo_sections = ""
    if geo and "error" not in geo:
        prov = geo.get("province_top20", [])
        prh = ["#", "省份", "销量", "份额"]
        prr = [[str(i), r["province"], _hfmt(r["sales"]), f'{r["share_pct"]}%'] for i, r in enumerate(prov, 1)]
        geo_sections = _table(prh, prr, num_cols={2}, right_cols={3})

        tiers = geo.get("city_tier", [])
        nth = geo.get("nev_penetration_by_tier", [])
        pen_map = {p["tier"]: p for p in nth}
        trh = ["线级", "销量", "份额", "MoM", "新能源渗透"]
        trr = []
        for r in tiers:
            t = r["city_tier_group"]
            pen = pen_map.get(t, {})
            pen_str = f'{pen.get("nev_penetration", 0):.1f}% ({pen.get("pen_chg", 0):+.1f}pct)' if pen else "-"
            mom_str = f'{r.get("mom_pct", 0):+.1f}%' if r.get("mom_pct") else "-"
            trr.append([t, _hfmt(r["sales"]), f'{r["share_pct"]}%', mom_str, pen_str])
        geo_sections += f'<h3 style="font-size:14px;margin:16px 0 8px;color:var(--zh-deep-blue)">城市线级</h3>' + \
                       _table(trh, trr, num_cols={1}, right_cols={2, 3})

        region = geo.get("region", [])
        reh = ["区域", "销量", "份额", "MoM"]
        rer = [[r["region_group"], _hfmt(r["sales"]), f'{r["share_pct"]}%',
                f'{r.get("mom_pct", 0):+.1f}%' if r.get("mom_pct") else "-"] for r in region]
        geo_sections += f'<h3 style="font-size:14px;margin:16px 0 8px;color:var(--zh-deep-blue)">区域</h3>' + \
                       _table(reh, rer, num_cols={1}, right_cols={2, 3})
    else:
        geo_sections = '<p class="section-note">暂无地理数据</p>'

    # Deep Insight
    di_sections = ""
    if di:
        parts = []
        for label, key in [("本月最大的赢家", "winners"), ("本月最大的输家", "losers")]:
            items = di.get(key, [])
            for item in items:
                chg_val = item.get("change", 0)
                direction = item.get("direction", "")
                arrow = "↓" if direction == "down" else "↑"
                parts.append(f'<div class="summary-card"><div class="summary-value">{item["name"]}</div><div class="summary-label">{label}</div><div class="summary-hint">{arrow}{chg_val}{item.get("unit", "")}</div></div>')
        for label, key in [("结构变化", "structural_changes"), ("价格变化", "price_changes"), ("新趋势", "new_trends")]:
            items = di.get(key, [])
            for item in items:
                parts.append(f'<div class="summary-card"><div class="summary-value" style="font-size:16px">{item}</div><div class="summary-label">{label}</div></div>')
        if parts:
            di_sections = f'<div class="summary-grid">{"".join(parts)}</div>'
    else:
        di_sections = '<p class="section-note">暂无深入分析</p>'

    # Change Detection
    cd_sections = ""
    changes = cd.get("changes", [])
    if changes:
        ch = ["模块", "指标", "变化", "分位", "异常"]
        cr = []
        for c in changes:
            level_dot = "🟢" if c.get("level") == "🟢" else "🔴" if c.get("level") == "🔴" else "🟡"
            cr.append([c["module"], c["indicator"], c["change"], c["percentile"], level_dot])
        cd_sections = _table(ch, cr)
    else:
        cd_sections = '<p class="section-note">本月无明显异常变化</p>'

    # Watch List
    wl = report.get("watch_list", {})
    total_sales = _es(report, "total_sales", 0)
    prev_total = _es(report, "prev_total_sales", 0)
    _, tr = _chg(total_sales, prev_total)
    nev_pen_val = _es(report, "nev_penetration", 0)
    nev_pen_mom = _es(report, "nev_pen_mom", 0)
    tp_val = _es(report, "weighted_tp", 0)
    tp_mom_val2 = _es(report, "weighted_tp_mom", 0)
    suv_share = wl.get("suv_share")
    suv_prev = wl.get("suv_prev")
    suv_trend = wl.get("suv_trend", "→")

    wh = ["指标", "本月", "上月", "趋势"]
    wr = [
        ["总销量", _h(total_sales), _h(prev_total), tr],
        ["新能源渗透", f"{nev_pen_val:.1f}%", f"{nev_pen_val - nev_pen_mom:.1f}%", _htr(nev_pen_mom)],
        ["平均成交价", f"¥{tp_val:,}", f"¥{tp_val - tp_mom_val2:,}", _htr(tp_mom_val2)],
    ]
    if suv_share:
        wr.append(["SUV 份额", f"{suv_share:.1f}%", f"{suv_prev:.1f}%" if suv_prev else "-", suv_trend])
    wl_sections = _table(wh, wr)

    sections = [
        ("① Executive Summary", kpi_cards + ins_cards),
        ("② Overall Market", om_sections),
        ("③ Brand Landscape", bl_sections),
        ("④ Model Ranking", mr_sections),
        ("⑤ Product Structure", ps_sections),
        ("⑥ Price Analysis", pa_sections),
        ("⑦ Geographic", geo_sections),
        ("⑧ Deep Insight", di_sections),
        ("⑨ Watch List", wl_sections),
        ("⑩ Change Detection", cd_sections),
    ]

    body = "".join(_section(t, c) for t, c in sections)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TP&MIX-ways Monthly Brief — {month}</title>
<style>{css}</style>
</head>
<body>
<header>
<div class="container">
<div class="brand">
<img class="brand-avatar" src="{brand_assets_prefix}/assets/brand/raccoon_avatar_light.png" alt="">
<span class="brand-name">Raccoon Research</span>
</div>
<span class="header-meta">{month} · 乘用车上险数据</span>
</div>
</header>
<main class="container">
<section class="hero">
<h1>TP&MIX-ways Monthly Brief</h1>
<p>{month} · 基于 TP&MIX-ways 乘用车上险数据</p>
</section>
{body}
</main>
<footer>
<img class="brand-sig" src="{brand_assets_prefix}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research">
<div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
<div style="font-size:12px;color:var(--zh-muted);margin-top:8px">报告自动生成 · {now_str}</div>
</footer>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="生成乘用车市场月报")
    parser.add_argument("--month", default="2026-06", help="报告月份 YYYY-MM")
    parser.add_argument("--output", default=None, help="输出目录")
    parser.add_argument("--format", choices=["md", "json", "html", "all"], default="all")
    args = parser.parse_args()

    rd = ReportData(args.month)
    out_dir = Path(args.output) if args.output else (
        WORKSPACE_ROOT / "outputs" / "reports" / f"tp_and_mix_ways_monthly_brief_{args.month}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"📊 生成 {args.month} 乘用车市场月报 ...")
    print(f"   数据月份: {rd.month_start}")
    print(f"   对比上月: {rd.prev_month_start}")
    print(f"   对比去年: {rd.ly_month_start}")

    for tbl_name in ["market_energy_monthly", "brand_monthly", "model_monthly",
                      "geo_monthly", "price_segment_monthly", "product_segment_monthly"]:
        df = rd.dfs.get(tbl_name)
        if df is not None:
            print(f"   📦 {tbl_name}: {len(df)} 行, {df['date_month'].min().strftime('%Y-%m')} ~ {df['date_month'].max().strftime('%Y-%m')}")

    # Build all sections
    report = {
        "report_month": args.month,
        "generated_at": datetime.now().isoformat(),
        "executive_summary": build_executive_summary(rd),
        "overall_market": build_overall_market(rd),
        "brand_landscape": build_brand_landscape(rd),
        "model_ranking": build_model_ranking(rd),
        "product_structure": build_product_structure(rd),
        "price_analysis": build_price_analysis(rd),
        "geographic": build_geographic(rd),
        "deep_insight": build_deep_insight(rd),
        "change_detection": build_change_detection(rd),
    }

    report["watch_list"] = _compute_watch_list(rd, report)

    # Write JSON
    json_path = out_dir / "report_data.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"   ✅ JSON: {json_path}")

    # Write MD
    if args.format in ("md", "all"):
        md_content = render_markdown(report)
        md_path = out_dir / f"monthly_brief_{args.month}.md"
        md_path.write_text(md_content, encoding="utf-8")
        print(f"   ✅ MD:   {md_path}")

    # Write HTML
    if args.format in ("html", "all"):
        css_content = _load_css()
        html_content = render_html(report, css_content, brand_assets_prefix="../../..")
        html_path = out_dir / f"monthly_brief_{args.month}.html"
        html_path.write_text(html_content, encoding="utf-8")
        print(f"   ✅ HTML: {html_path}")

    print(f"\n📈 报告生成完成: {out_dir}")
    return 0


def _compute_watch_list(rd: ReportData, report: dict | None = None) -> dict:
    """Compute watch list trend directions."""
    cur = rd.current("market_energy_monthly")
    prev = rd.prev("market_energy_monthly")
    hist = rd.historical("market_energy_monthly")
    cur_prod = rd.current("product_segment_monthly")
    prev_prod = rd.prev("product_segment_monthly")
    cur_brand = rd.current("brand_monthly")
    prev_brand = rd.prev("brand_monthly")
    cur_geo = rd.current("geo_monthly")
    prev_geo = rd.prev("geo_monthly")

    wl = {}

    # SUV share
    if not cur_prod.empty and not prev_prod.empty:
        suv_c = cur_prod[cur_prod["body_type"] == "SUV"]["sales"].sum()
        total_c = cur_prod["sales"].sum()
        suv_p = prev_prod[prev_prod["body_type"] == "SUV"]["sales"].sum()
        total_p = prev_prod["sales"].sum()
        if total_c and total_p:
            wl["suv_share"] = suv_c / total_c * 100
            wl["suv_prev"] = suv_p / total_p * 100
            wl["suv_trend"] = "↑" if wl["suv_share"] > wl["suv_prev"] else "↓" if wl["suv_share"] < wl["suv_prev"] else "→"

    # Luxury share
    if not cur_brand.empty and not prev_brand.empty and "brand_luxury_group" in cur_brand.columns:
        pass

    return wl


if __name__ == "__main__":
    sys.exit(main())
