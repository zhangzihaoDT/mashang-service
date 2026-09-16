#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用车型预售情况对比报告（terminal / json / html）。

由 l6_m2_presale_report.py 泛化而来：代际、开放时刻、对标代际、PK series 全部来自
shared/schema/business_definition.json，不再硬编码 DM2/L6。

模块:
  1 预售核心指标（KPI：累计/留存/唯一用户/开盘 24h/峰值）
  2 跨代际对标（同 N 日留存 · 峰值小时 · 开盘日留存）
  3 产品结构（纯产品，不做限量版小计）
  4 大区结构（主代际 vs 对标代际 · 同 N 日窗口）
  5 线索→预订间隔（预售前线索占比 + 即时/观望/存量 · 跨代际）
  6 预售窗口期小订和下发线索比值（完整观察日 vs 前 30 日基线 · 跨代际）
  7 正反向 PK（主代际最新周 + 对标代际周 + 上汽集团竞品趋势）
  8 预选配置（留存池按产品覆盖 + 已选分布）
  9 用户画像（性别/年龄/城市线级/省份 · 跨代际）

集团 / 观星台背景模块不在此脚本产出（独立模块，按需后加）。

口径（全文统一，release 口径）:
  留存小订 = 预售开放时刻之后支付意向金、且未退意向金的订单（试驾车不纳入零售预售分析）。
  - 累计口径：intention_payment_time ∈ [open_ts, as_of+1d) 且 intention_refund_time 为空
  - 同 N 日窗口：intention_payment_time ∈ [open_ts, open_ts+Nd) 且（未退 或 退订晚于窗口末）
  - N=0 开盘日：open_ts ~ start 当日 24:00
  代际归属 = series_group_logic；时间一律取 time_periods，不从数据最小值推断。

用法:
  python research_scripts/presale_cumulative_order_compare.py \
      --gens DM1 CM2 LS9 LS8 DM2 --as-of 2026-08-24 --n-days 7 --format html
  python research_scripts/presale_cumulative_order_compare.py --format json
  python research_scripts/presale_cumulative_order_compare.py            # 默认当前预售代际
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
for _p in (str(REPO_ROOT), str(_WS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from utils.monitors.order_filter import flag_test_orders  # noqa: E402
from utils.monitors.phase import (  # noqa: E402
    compare_keys,
    detect_active,
    load_business_definition,
    model_series_of,
    open_hour,
    open_minute,
    series_label,
)
from utils.monitors.series_group import apply_series_group_logic  # noqa: E402
from utils.regions import REGION_MAP_OLD_TO_NEW  # noqa: E402

BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
ASSIGN_CSV = REPO_ROOT / "dataset" / "assign_data.csv"
CONFIG_PARQUET = REPO_ROOT / "dataset" / "config_attribute.parquet"

# 按预售先后传入，末位 = 主代际（本次汇报对象）
DEFAULT_GENS = ["DM1", "CM2", "LS9", "LS8", "DM2"]
DEFAULT_N_DAYS = 7
DEFAULT_PK_CSV = "/Users/zihao_/Documents/coding/dataset/original/业务数据记录_竞争PK（正反向排名）.csv"
_DEFAULT_REPORT = _WS / "outputs" / "reports"
_DEFAULT_TABLE = _WS / "outputs" / "tables"

DATETIME_COLS = [
    "intention_payment_time",
    "intention_refund_time",
    "deposit_payment_time",
    "deposit_refund_time",
    "first_assign_time",
    "lock_time",
    "invoice_upload_time",
    "delivery_date",
    "order_create_date",
]

CONV_KEYS = ["store", "trial", "lock7", "lock30"]
CONV_LABELS = {"store": "门店线索占比", "trial": "当日试驾率", "lock7": "7 日锁单率", "lock30": "30 日锁单率"}
_CONV_COLS = {
    "store": "下发线索数 (门店)",
    "trial": "下发线索当日试驾数",
    "lock7": "下发线索 7 日锁单数",
    "lock30": "下发线索 30 日锁单数",
}


# ── 基础工具 ─────────────────────────────────────────────

def _fmt_int(v) -> str:
    return f"{int(v):,}"


def _fmt_pct(v, nd: int = 1) -> str:
    return f"{v * 100:.{nd}f}%"


def _cn_date(s) -> pd.Timestamp:
    return pd.to_datetime(
        str(s).replace("年", "-").replace("月", "-").replace("日", ""),
        format="%Y-%m-%d", errors="coerce",
    )


def _norm_retail_order_type(order_type: pd.Series) -> pd.Series:
    return order_type.fillna("").astype(str)


# ── 数据加载 ─────────────────────────────────────────────

def load_order(bd: dict, exclude_test: bool = True) -> pd.DataFrame:
    df = pd.read_parquet(ORDER_PARQUET)
    for c in DATETIME_COLS:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    df = apply_series_group_logic(df, bd)
    if exclude_test:
        df = df.loc[~flag_test_orders(df, bd)].copy()
    return df


def load_assign() -> pd.DataFrame:
    df = pd.read_csv(ASSIGN_CSV, encoding="utf-8-sig")
    df["_date"] = df["Assign Time 年/月/日"].apply(_cn_date)
    return df[df["_date"].notna()].copy()


def load_pk(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["PK次数"] = df["PK次数"].astype(str).str.replace(",", "", regex=False).astype(int)
    return df


# ── 预售窗口口径 ─────────────────────────────────────────

def open_ts(bd: dict, gen: str) -> pd.Timestamp:
    start = pd.Timestamp(bd["time_periods"][gen]["start"])
    return start + pd.Timedelta(hours=open_hour(bd, gen), minutes=open_minute(bd, gen))


def _retention_upto(df: pd.DataFrame, bd: dict, gen: str, as_of: pd.Timestamp) -> pd.DataFrame:
    """截至 as_of 收盘的留存小订（point-in-time 正确：as_of 之后的退订不计为流失）。"""
    ot = open_ts(bd, gen)
    cutoff = as_of + pd.Timedelta(days=1)
    return df[
        (df["series_group_logic"] == gen)
        & (df["intention_payment_time"] >= ot)
        & (df["intention_payment_time"] < cutoff)
        & (df["intention_refund_time"].isna() | (df["intention_refund_time"] >= cutoff))
    ].copy()


def _retention_window(df: pd.DataFrame, bd: dict, gen: str, n_days: int,
                      as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    ot = open_ts(bd, gen)
    wend = ot + pd.Timedelta(days=n_days)
    if as_of is not None:
        wend = min(wend, as_of + pd.Timedelta(days=1))  # PIT：窗口不得越过 as-of
    # 观测截止 = 窗口末（或 as-of 收盘）；退订发生在截止时刻之后（含边界）视为仍留存
    m = (
        (df["series_group_logic"] == gen)
        & (df["intention_payment_time"] >= ot)
        & (df["intention_payment_time"] < wend)
        & (df["intention_refund_time"].isna() | (df["intention_refund_time"] >= wend))
    )
    return df[m].copy()


def _peak_hour(day: pd.DataFrame) -> tuple[str, int, int, int]:
    if day.empty:
        return "-", 0, 0, 0
    h = day["intention_payment_time"].dt.hour.astype(int)
    hourly = h.value_counts().reindex(range(24), fill_value=0)
    peak = int(hourly.idxmax())
    nxt = int(hourly.iloc[peak + 1]) if peak < 23 else 0
    return f"{peak:02d}:00", int(hourly.iloc[peak]), nxt, int(hourly.sum())


# ── 模块 1：预售核心指标 ─────────────────────────────────

def compute_core(df: pd.DataFrame, bd: dict, as_of: pd.Timestamp, gen: str) -> dict:
    start = pd.Timestamp(bd["time_periods"][gen]["start"])
    ot = open_ts(bd, gen)
    end_t = as_of + pd.Timedelta(days=1)
    sel = df[df["series_group_logic"] == gen]

    cum = sel[(sel["intention_payment_time"] >= ot) & (sel["intention_payment_time"] < end_t)]
    ret = _retention_upto(df, bd, gen, as_of)

    start_day_end = start + pd.Timedelta(days=1)
    ld = sel[(sel["intention_payment_time"] >= ot) & (sel["intention_payment_time"] < start_day_end)]
    ld_ret = ld[ld["intention_refund_time"].isna() | (ld["intention_refund_time"] > start_day_end)]

    day24 = sel[(sel["intention_payment_time"] >= ot) & (sel["intention_payment_time"] < ot + pd.Timedelta(hours=24))]
    peak_hour, peak_count, next_hour, _ = _peak_hour(day24)

    return {
        "gen": gen,
        "open_ts": ot.isoformat(),
        "cum": int(cum["order_number"].nunique()),
        "retention": int(ret["order_number"].nunique()),
        "retention_users": int(ret["buyer_identity_no"].nunique()),
        "start_day_total": int(ld["order_number"].nunique()),
        "start_day_retained": int(ld_ret["order_number"].nunique()),
        "peak_hour": peak_hour,
        "peak_count": peak_count,
        "next_hour": next_hour,
        "day24": int(day24["order_number"].nunique()),
        "product": ret.groupby("product_name")["order_number"].nunique().sort_values(ascending=False),
        "region": ret.groupby("parent_region_name")["order_number"].nunique().sort_values(ascending=False),
    }


# ── 模块 2：跨代际对标 ───────────────────────────────────

def compute_benchmark(df: pd.DataFrame, bd: dict, gens: list[str], n_days: int,
                      as_of: pd.Timestamp) -> list[dict]:
    rows = []
    for gen in gens:
        start = pd.Timestamp(bd["time_periods"][gen]["start"])
        ot = open_ts(bd, gen)
        sel = df[df["series_group_logic"] == gen]
        ret_n = int(_retention_window(df, bd, gen, n_days, as_of)["order_number"].nunique())

        day24 = sel[(sel["intention_payment_time"] >= ot) & (sel["intention_payment_time"] < ot + pd.Timedelta(hours=24))]
        peak_h, peak_c, _, _ = _peak_hour(day24)

        start_day_end = start + pd.Timedelta(days=1)
        ld = sel[(sel["intention_payment_time"] >= ot) & (sel["intention_payment_time"] < start_day_end)]
        ld_total = int(ld["order_number"].nunique())
        ld_ret = int(
            ld[ld["intention_refund_time"].isna() | (ld["intention_refund_time"] > start_day_end)]["order_number"].nunique()
        )
        rows.append({"gen": gen, "ret_n": ret_n, "peak_h": peak_h, "peak_c": peak_c,
                     "start_day_total": ld_total, "start_day_retained": ld_ret})
    return rows


# ── 模块 3：产品结构 ─────────────────────────────────────

def compute_product(core: dict) -> list[dict]:
    total = core["retention"] or 1
    prod = core["product"]
    return [{"product": p, "count": int(c), "share": c / total} for p, c in prod.items()]


# ── 模块 4：大区结构 ─────────────────────────────────────

def _region_counts(df: pd.DataFrame, bd: dict, gen: str, n_days: int,
                   as_of: pd.Timestamp) -> dict[str, int]:
    sel = _retention_window(df, bd, gen, n_days, as_of)
    mapped: dict[str, int] = {}
    for reg, cnt in sel.groupby("parent_region_name")["order_number"].nunique().items():
        tgt = REGION_MAP_OLD_TO_NEW.get(str(reg), str(reg))
        mapped[tgt] = mapped.get(tgt, 0) + int(cnt)
    return dict(sorted(mapped.items(), key=lambda kv: kv[1], reverse=True))


def compute_region(df: pd.DataFrame, bd: dict, main_gen: str, cmp_gen: str, n_days: int,
                   as_of: pd.Timestamp) -> dict:
    return {
        "main_gen": main_gen, "cmp_gen": cmp_gen,
        "main": _region_counts(df, bd, main_gen, n_days, as_of),
        "cmp": _region_counts(df, bd, cmp_gen, n_days, as_of),
    }


# ── 模块 5：线索→预订间隔 ────────────────────────────────

def compute_lead_gap(df: pd.DataFrame, bd: dict, gens: list[str], n_days: int,
                     as_of: pd.Timestamp) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for gen in gens:
        ot = open_ts(bd, gen)
        sel = _retention_window(df, bd, gen, n_days, as_of)
        gap = (sel["intention_payment_time"] - sel["first_assign_time"]).dt.total_seconds() / 86400
        n = int(gap.notna().sum())
        out[gen] = {
            "n": int(len(sel)),
            "before": float((sel["first_assign_time"] < ot).mean()) if n else float("nan"),
            "med": round(float(gap.median()), 2) if n else float("nan"),
            "instant": float((gap < 3).mean()) if n else float("nan"),
            "wait": float(((gap >= 3) & (gap < 30)).mean()) if n else float("nan"),
            "stock": float((gap >= 30).mean()) if n else float("nan"),
        }
    return out


# ── 模块 6：下发线索 ─────────────────────────────────────

def _lead_block(df: pd.DataFrame, s: pd.Timestamp, e: pd.Timestamp) -> dict:
    w = df[(df["_date"] >= s) & (df["_date"] <= e)]
    leads = int(w["下发线索数"].sum())
    stores = int(w["下发门店数"].sum())
    return {"leads": leads, "stores": stores,
            "per_store": leads / stores if stores else None,
            "daily_avg": leads / int(w["_date"].nunique()) if not w.empty else None,
            "days": int(w["_date"].nunique())}


def _conv_rates(w: pd.DataFrame) -> dict[str, float]:
    total = w["下发线索数"].sum()
    return {k: (w[c].sum() / total if total else float("nan")) for k, c in _CONV_COLS.items()}


def _presale_window_dates(bd: dict, gen: str, as_of: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """返回预售窗口的自然日范围，末日不超过完整观察日（as-of 前一天）。"""
    start = pd.Timestamp(bd["time_periods"][gen]["start"]).normalize()
    planned_end = pd.Timestamp(bd["time_periods"][gen]["end"]).normalize() - pd.Timedelta(days=1)
    complete_day = as_of.normalize() - pd.Timedelta(days=1)
    return start, min(planned_end, complete_day)


def _presale_small_orders(df: pd.DataFrame, bd: dict, gen: str,
                          window_start: pd.Timestamp, window_end: pd.Timestamp) -> int:
    if window_end < window_start:
        return 0
    end_exclusive = window_end + pd.Timedelta(days=1)
    sel = df[
        (df["series_group_logic"] == gen)
        & (df["intention_payment_time"] >= open_ts(bd, gen))
        & (df["intention_payment_time"] < end_exclusive)
    ]
    return int(sel["order_number"].nunique())


def compute_assign(assign: pd.DataFrame, df: pd.DataFrame, bd: dict,
                   gens: list[str], as_of: pd.Timestamp,
                   main_gen: str | None = None) -> dict:
    main_gen = main_gen or gens[-1]
    main_start, main_end = _presale_window_dates(bd, main_gen, as_of)
    main_base_start = main_start - pd.Timedelta(days=30)
    main_base_end = main_start - pd.Timedelta(days=1)
    win = _lead_block(assign, main_start, main_end)
    base = _lead_block(assign, main_base_start, main_base_end)

    rows = []
    for gen in gens:
        start, end = _presale_window_dates(bd, gen, as_of)
        baseline_start = start - pd.Timedelta(days=30)
        baseline_end = start - pd.Timedelta(days=1)
        gw = assign[(assign["_date"] >= start) & (assign["_date"] <= end)]
        gb = assign[(assign["_date"] >= baseline_start) & (assign["_date"] <= baseline_end)]
        wl, bl = int(gw["下发线索数"].sum()), int(gb["下发线索数"].sum())
        window_days = int((end - start).days + 1) if end >= start else 0
        small_orders = _presale_small_orders(df, bd, gen, start, end)
        rows.append({
            "gen": gen,
            "window_start": str(start.date()),
            "window_end": str(end.date()) if end >= start else None,
            "window_days": window_days,
            "baseline_start": str(baseline_start.date()),
            "baseline_end": str(baseline_end.date()),
            "window_leads": wl,
            "baseline_leads": bl,
            "window_daily_avg": wl / window_days if window_days else None,
            "baseline_daily_avg": bl / 30 if bl else None,
            "delta": wl - bl,
            "delta_pct": (wl - bl) / bl if bl else None,
            "small_orders": small_orders,
            "small_order_daily_avg": small_orders / window_days if window_days else None,
            "all_assigned_leads": wl,
            "small_order_lead_ratio": (
                (small_orders / window_days) / (bl / 30)
                if window_days and bl else None
            ),
        })
    return {
        "window": win,
        "baseline": base,
        "cross": rows,
        "main_start": str(main_start.date()),
        "main_end": str(main_end.date()) if main_end >= main_start else None,
        "complete_observation_date": str((as_of.normalize() - pd.Timedelta(days=1)).date()),
        "baseline_days": 30,
    }


# ── 模块 7：正反向 PK ────────────────────────────────────

def _pk_series(bd: dict, gen: str) -> str | None:
    mon = bd.get("monitor") or {}
    by = mon.get("pk_series_by_generation") or {}
    return by.get(gen) or model_series_of(bd, gen)


def _week_bounds(w) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """解析 PK Week（兼容 2025-04-14~04-20 / 2026-08-17 ~ 2026-08-23 / 全角～）。"""
    import re

    parts = [p.strip() for p in re.split(r"[~～]", str(w))]
    if not parts or not parts[0]:
        return None
    try:
        s = pd.to_datetime(parts[0], errors="raise")
    except Exception:
        return None
    if len(parts) == 1 or not parts[-1]:
        return s, s
    tail = parts[-1]
    if len(tail.split("-")) == 2:
        tail = f"{s.year}-{tail}"
    try:
        e = pd.to_datetime(tail, errors="raise")
    except Exception:
        return None
    if e < s:
        e = e + pd.DateOffset(years=1)
    return s, e


def _pk_week_for_date(df: pd.DataFrame, series: str, target: pd.Timestamp,
                      fallback_latest: bool = False) -> tuple[str | None, pd.DataFrame]:
    sub = df[df["series"] == series]
    weeks = sorted(sub["Week"].unique())
    for w in weeks:
        b = _week_bounds(w)
        if b and b[0] <= target <= b[1]:
            return w, sub[sub["Week"] == w].sort_values("PK次数", ascending=False)
    if fallback_latest:
        # 回退：起始日 <= target 的最近一周（避免取到 as-of 之后的未来周）
        cands = [w for w in weeks if (_week_bounds(w) and _week_bounds(w)[0] <= target)]
        if cands:
            w = cands[-1]
            return w, sub[sub["Week"] == w].sort_values("PK次数", ascending=False)
    return None, sub.iloc[0:0]


def compute_pk(pk: pd.DataFrame | None, bd: dict, as_of: pd.Timestamp, main_gen: str, cmp_gen: str) -> dict | None:
    if pk is None:
        return None
    series = _pk_series(bd, main_gen)
    if not series or series not in set(pk["series"].unique()):
        return None
    # 最新周：以 as-of 前一日所在周定位（无则回退最新周）
    main_week, main_rows = _pk_week_for_date(pk, series, as_of - pd.Timedelta(days=1), fallback_latest=True)
    cmp_start = pd.Timestamp(bd["time_periods"][cmp_gen]["start"])
    cmp_week, cmp_rows = _pk_week_for_date(pk, series, cmp_start)

    weeks = sorted(pk[pk["series"] == series]["Week"].unique())
    recent = weeks[-5:]
    saic = pk[(pk["series"] == series) & (pk["品牌"].astype(str).str.contains("上汽集团"))]
    trend = []
    for w in recent:
        for _, r in saic[saic["Week"] == w].sort_values("PK次数", ascending=False).iterrows():
            trend.append({"week": str(w), "car": str(r["车系"]), "pk": int(r["PK次数"]),
                          "fwd": int(r["PK正向排名"]), "rev": int(r["PK反向排名"])})
    return {
        "series": series, "main_week": main_week, "cmp_week": cmp_week, "cmp_gen": cmp_gen,
        "main_rows": main_rows, "cmp_rows": cmp_rows, "trend": trend,
    }


# ── 模块 8：预选配置 ─────────────────────────────────────

def compute_config(ret: pd.DataFrame) -> dict | None:
    if not CONFIG_PARQUET.exists():
        return None
    cfg = pd.read_parquet(CONFIG_PARQUET)
    cfg["Order Number"] = cfg["Order Number"].astype(str)
    ret_ids = set(ret["order_number"].astype(str).str.strip())
    sub = cfg[cfg["Order Number"].isin(ret_ids) & cfg["value"].notna()].copy()
    if sub.empty:
        return {"covered": 0, "rows": 0, "prod_rows": [], "attr_dist": {}}
    per_order_attrs = sub.groupby("Order Number")["Attribute"].apply(set).to_dict()
    prod_rows = []
    for prod, grp in ret.groupby("product_name"):
        ids = grp["order_number"].astype(str).str.strip().tolist()
        withval = sum(1 for o in ids if o in per_order_attrs)
        prod_rows.append({"product": prod, "total": len(ids), "withval": withval})
    attr_dist: dict[str, dict] = {}
    for attr, a in sub.groupby("Attribute"):
        attr_dist[attr] = a["value"].value_counts().to_dict()
    return {"covered": int(sub["Order Number"].nunique()), "rows": int(len(sub)),
            "prod_rows": prod_rows, "attr_dist": attr_dist}


# ── 模块 9：用户画像 ─────────────────────────────────────

# 年龄分桶（左闭右开）；末段收敛为「65岁以上」，不再细分 65+。
# 注意：与 research_scripts/launch_cumulative_lock_compare.py（细分至 75+）口径不同。
# 预售留存池 owner_age 全缺，画像年龄统一用 buyer_age（购车人年龄）。
AGE_BAND_EDGES = [18, 25, 30, 35, 40, 45, 50, 55, 60, 65]
AGE_BAND_LABELS = (
    "18-25岁", "25-30岁", "30-35岁", "35-40岁", "40-45岁", "45-50岁",
    "50-55岁", "55-60岁", "60-65岁", "65岁以上",
)


def _profile(ret: pd.DataFrame) -> dict:
    from runtime_scripts.user_profile import CITY_TO_PROVINCE, city_to_tier_label, norm_city

    n = len(ret)
    if not n:
        return {"n": 0, "gender": {}, "age_bands": {}, "age_nonnull": 0, "age_mean": None,
                "age_median": None, "tier": {}, "prov": {}, "product": {}}
    g = ret["order_gender"].fillna("(未知)").astype(str)
    a = pd.to_numeric(ret["buyer_age"], errors="coerce")
    city = ret["license_city"].apply(norm_city)
    tier = city.apply(city_to_tier_label)
    prov = city.map(CITY_TO_PROVINCE).fillna("未知")
    age_bands: dict[str, int] = {}
    if a.notna().any():
        cats = pd.cut(a, bins=AGE_BAND_EDGES + [float("inf")],
                      labels=list(AGE_BAND_LABELS), right=False)
        vc = cats.value_counts()
        age_bands = {lab: int(vc.get(lab, 0)) for lab in AGE_BAND_LABELS}
    return {
        "n": n,
        "gender": g.value_counts().to_dict(),
        "age_bands": age_bands,
        "age_nonnull": int(a.notna().sum()),
        "age_mean": round(float(a.mean()), 1) if a.notna().any() else None,
        "age_median": float(a.median()) if a.notna().any() else None,
        "tier": tier.value_counts().to_dict(),
        "prov": prov.value_counts().to_dict(),
        "product": ret["product_name"].value_counts().to_dict(),
    }


def compute_profile(df: pd.DataFrame, bd: dict, gens: list[str], n_days: int,
                    as_of: pd.Timestamp) -> dict[str, dict]:
    return {
        gen: _profile(_retention_window(df, bd, gen, n_days, as_of))
        for gen in gens
    }


def _known_gender_base(p: dict) -> int:
    """已知性别样本数（剔除「未知」），用于性别占比基数。"""
    return p["gender"].get("男", 0) + p["gender"].get("女", 0)


def _main_age_band(p: dict) -> str:
    """占已知年龄比例最高的年龄段。"""
    base = p.get("age_nonnull", 0)
    bands = p.get("age_bands") or {}
    if not base or not bands:
        return "—"
    band, cnt = max(bands.items(), key=lambda kv: kv[1])
    return f"{band}（{cnt / base * 100:.0f}%）"


# ── 汇总 ─────────────────────────────────────────────────

def compute_all(df: pd.DataFrame, bd: dict, as_of: pd.Timestamp, gens: list[str],
                n_days: int, pk: pd.DataFrame | None) -> dict:
    main_gen = gens[-1]
    # 末位仍为主代际判定；展示/对比顺序统一主代际前置。
    ordered = [main_gen] + [g for g in gens if g != main_gen]
    ck = compare_keys(bd, main_gen)
    cmp_gen = ck[0] if ck else (ordered[-2] if len(ordered) > 1 else main_gen)

    core = compute_core(df, bd, as_of, main_gen)
    ret = _retention_upto(df, bd, main_gen, as_of)
    return {
        "as_of": str(as_of.date()),
        "gens": ordered,
        "main_gen": main_gen,
        "cmp_gen": cmp_gen,
        "n_days": n_days,
        "series": _pk_series(bd, main_gen),
        "label": series_label(bd, main_gen),
        "window": {
            "start": bd["time_periods"][main_gen].get("start"),
            "end": bd["time_periods"][main_gen].get("end"),
            "open": core["open_ts"],
        },
        "core": core,
        "benchmark": compute_benchmark(df, bd, ordered, n_days, as_of),
        "product": compute_product(core),
        "region": compute_region(df, bd, main_gen, cmp_gen, n_days, as_of),
        "lead_gap": compute_lead_gap(df, bd, ordered, n_days, as_of),
        "assign": compute_assign(load_assign(), df, bd, ordered, as_of, main_gen=main_gen),
        "pk": compute_pk(pk, bd, as_of, main_gen, cmp_gen),
        "config": compute_config(ret),
        "profile": compute_profile(df, bd, ordered, n_days, as_of),
    }


# ── 图表 ─────────────────────────────────────────────────

def _daily_flows(df: pd.DataFrame, bd: dict, as_of: pd.Timestamp, gen: str) -> dict:
    start = pd.Timestamp(bd["time_periods"][gen]["start"])
    ot = open_ts(bd, gen)
    end_t = as_of + pd.Timedelta(days=1)
    sel = df[(df["series_group_logic"] == gen)
             & (df["intention_payment_time"] >= ot)
             & (df["intention_payment_time"] < end_t)]
    pay = sel.groupby(sel["intention_payment_time"].dt.date)["order_number"].nunique()
    ref = sel[sel["intention_refund_time"].notna() & (sel["intention_refund_time"] < end_t)]
    ref = ref.groupby(ref["intention_refund_time"].dt.date)["order_number"].nunique()
    days = pd.date_range(start.normalize(), as_of.normalize(), freq="D").date
    new = [int(pay.get(d, 0)) for d in days]
    refund = [int(ref.get(d, 0)) for d in days]
    retained_cum, s = [], 0
    for n, r in zip(new, refund):
        s += n - r
        retained_cum.append(s)
    return {"dates": [str(d) for d in days], "new": new, "refund": refund, "retained_cum": retained_cum}


def render_flow_chart(flow: dict, out_html: Path, main_gen: str,
                      flow_compare: dict | None = None, compare_label: str = "") -> Path | None:
    try:
        import plotly.graph_objects as go
        from utils.plotly_theme import apply_zh_theme, get_series_color
    except Exception as e:  # pragma: no cover
        print(f"⚠️ plotly 主题加载失败，跳过头部图表: {e}")
        return None
    cum = sum(flow["new"])
    refunded = sum(flow["refund"])
    retained = cum - refunded
    fig = go.Figure()
    fig.add_trace(go.Bar(x=flow["dates"], y=flow["new"], name="每日新支付小订",
                         marker_color=get_series_color("own")))
    fig.add_trace(go.Bar(x=flow["dates"], y=[-v for v in flow["refund"]], name="每日退订（向下）",
                         marker_color=get_series_color("negative")))
    fig.add_trace(go.Scatter(x=flow["dates"], y=flow["retained_cum"], name="累计留存小订（右轴）",
                             yaxis="y2", line=dict(color=get_series_color("ash"), width=2)))
    if flow_compare and flow_compare.get("retained_cum"):
        x_cmp = flow["dates"][: len(flow_compare["retained_cum"])]
        fig.add_trace(go.Scatter(x=x_cmp, y=flow_compare["retained_cum"],
                                 name=compare_label or "对比代际累计留存（右轴）", yaxis="y2",
                                 line=dict(color=get_series_color("steel"), width=2, dash="dash")))
    apply_zh_theme(fig)
    title = f"预售期每日小订 × 退订（release {main_gen} 口径）：累计 {cum:,} − 退订 {refunded:,} = 留存 {retained:,}"
    if flow_compare and flow_compare.get("retained_cum"):
        title += f"；{compare_label or '对比'} = {flow_compare['retained_cum'][-1]:,}"
    fig.update_layout(
        title=dict(text=title, font=dict(size=15)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(l=50, r=60, t=80, b=40), height=380, hovermode="x unified",
        barmode="relative",
        yaxis2=dict(overlaying="y", side="right", showgrid=False, title="累计留存",
                    tickfont=dict(color=get_series_color("ash")),
                    title_font=dict(color=get_series_color("ash"))))
    fig.update_yaxes(title_text="每日小订（台）", automargin=True)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(out_html, include_plotlyjs="cdn")
    _export_png(fig, out_html.stem)
    return out_html


# ── 图表：嵌入 HTML 的 Plotly 图（inline） ───────────────

_PLOTLY_CDN = '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'


def _plotly_deps():
    try:
        import plotly.graph_objects as go
        from utils.plotly_theme import ZH, apply_zh_theme, get_series_color

        return go, ZH, apply_zh_theme, get_series_color
    except Exception:
        return None, None, None, None


_PNG_DIR: Path | None = None
_PNG_PREFIX: str = ""


def _export_png(fig, name: str) -> Path | None:
    """Export a plotly figure to PNG (outputs/charts) when PNG_DIR is set."""
    if _PNG_DIR is None or fig is None:
        return None
    try:
        _PNG_DIR.mkdir(parents=True, exist_ok=True)
        out = _PNG_DIR / f"{name}.png"
        h = getattr(fig.layout, "height", None)
        fig.write_image(out, width=1200, height=h or 460, scale=2)
        return out
    except Exception as e:  # pragma: no cover
        print(f"⚠️ PNG 导出失败: {name}: {e}")
        return None


def _chart_box(fig, name: str = "") -> str:
    if name:
        _export_png(fig, f"{_PNG_PREFIX}_{name}" if _PNG_PREFIX else name)
    return f'<div class="chart-box">{fig.to_html(full_html=False, include_plotlyjs=False)}</div>'


def _yesno(v) -> bool:
    return v is not None and not (hasattr(v, "__float__") and pd.isna(v))


def chart_benchmark(bench: list[dict], main_gen: str) -> str | None:
    go, ZH, apply_zh_theme, get_series_color = _plotly_deps()
    if go is None:
        return None
    gens = [b["gen"] for b in bench]
    ret = [b["ret_n"] for b in bench]
    start = [b["start_day_retained"] for b in bench]
    colors = [get_series_color("own") if g == main_gen else "#B6C3CE" for g in gens]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=ret, y=gens, orientation="h", name="同 N 日留存",
        marker_color=colors,
        text=[f"{v:,}" for v in ret], textposition="outside",
        hovertemplate="%{y} · 同 N 日留存 %{x:,} 单<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=start, y=gens, mode="markers", name="开盘日留存",
        marker=dict(color=get_series_color("event"), size=10,
                    line=dict(color="#ffffff", width=1)),
        text=[f"{v:,}" for v in start], textposition="middle right",
        hovertemplate="%{y} · 开盘日留存 %{x:,} 单<extra></extra>",
    ))
    apply_zh_theme(fig)
    fig.update_layout(
        height=max(270, 46 * len(gens)),
        margin=dict(l=20, r=90, t=30, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        barmode="overlay",
    )
    fig.update_xaxes(title_text="订单数（台）", rangemode="tozero")
    fig.update_yaxes(autorange="reversed")
    return _chart_box(fig, "benchmark")


def chart_product(product: list[dict], total: int) -> str | None:
    go, ZH, apply_zh_theme, get_series_color = _plotly_deps()
    if go is None:
        return None
    labels = [p["product"] for p in product[:8]]
    counts = [p["count"] for p in product[:8]]
    rest = sum(p["count"] for p in product[8:])
    if rest:
        labels.append("其他")
        counts.append(rest)
    if not labels:
        return None
    fig = go.Figure(go.Bar(
        x=counts, y=labels, orientation="h",
        marker_color=get_series_color("own"),
        text=[f"{v:,}" for v in counts], textposition="outside",
        hovertemplate="%{y} · %{x:,} 单 <extra></extra>",
    ))
    apply_zh_theme(fig)
    fig.update_layout(
        height=max(220, 42 * len(labels)),
        margin=dict(l=20, r=70, t=30, b=30),
    )
    fig.update_xaxes(title_text="留存订单数（台）", rangemode="tozero")
    fig.update_yaxes(autorange="reversed")
    return _chart_box(fig, "product")


def chart_region_dumbbell(reg: dict, main_gen: str, cmp_gen: str) -> str | None:
    go, ZH, apply_zh_theme, get_series_color = _plotly_deps()
    if go is None:
        return None
    m_reg, c_reg = reg["main"], reg["cmp"]
    m_total = sum(m_reg.values()) or 1
    c_total = sum(c_reg.values()) or 1
    all_regs = list(dict.fromkeys(list(m_reg.keys()) + list(c_reg.keys())))
    top = sorted(all_regs, key=lambda r: -(m_reg.get(r, 0) or 0))[:10]
    if not top:
        return None
    m_share = [m_reg.get(r, 0) / m_total for r in top]
    c_share = [c_reg.get(r, 0) / c_total for r in top]
    fig = go.Figure()
    for i, r in enumerate(top):
        fig.add_trace(go.Scatter(
            x=[c_share[i], m_share[i]], y=[r, r], mode="lines",
            line=dict(color="#C7D3DC", width=2), showlegend=False, hoverinfo="skip",
        ))
    fig.add_trace(go.Scatter(
        x=c_share, y=top, mode="markers", name=f"{cmp_gen} 占比",
        marker=dict(color=get_series_color("event"), size=11),
        hovertemplate="%{y} · %{x:.1%}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=m_share, y=top, mode="markers", name=f"{main_gen} 占比",
        marker=dict(color=get_series_color("own"), size=11),
        hovertemplate="%{y} · %{x:.1%}<extra></extra>",
    ))
    deltas = [f"{(m - c) * 100:+.1f}pp" for m, c in zip(m_share, c_share)]
    fig.add_trace(go.Scatter(
        x=m_share, y=top, mode="text", text=deltas,
        textposition="middle right", showlegend=False, hoverinfo="skip",
    ))
    apply_zh_theme(fig)
    fig.update_layout(
        height=max(280, 42 * len(top)),
        margin=dict(l=20, r=70, t=30, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(title_text="留存小订占比", tickformat=".0%", rangemode="tozero")
    fig.update_yaxes(autorange="reversed")
    return _chart_box(fig, "region_dumbbell")


def chart_lead_amplitude(lcg: list[dict], main_gen: str) -> str | None:
    go, ZH, apply_zh_theme, get_series_color = _plotly_deps()
    if go is None:
        return None
    gens = [r["gen"] for r in lcg]
    win = [r["window_daily_avg"] for r in lcg]
    base = [r["baseline_daily_avg"] for r in lcg]
    if all(v is None for v in win):
        return None
    fig = go.Figure()
    for i, g in enumerate(gens):
        if win[i] is None or base[i] is None:
            continue
        highlight = g == main_gen
        fig.add_trace(go.Scatter(
            x=[base[i], win[i]], y=[g, g], mode="lines",
            line=dict(color=get_series_color("own") if highlight else "#C7D3DC",
                      width=3 if highlight else 1.5),
            showlegend=False, hoverinfo="skip",
        ))
    fig.add_trace(go.Scatter(
        x=base, y=gens, mode="markers", name="前30日下发线索日均",
        marker=dict(color=get_series_color("event"), size=11, symbol="square"),
        hovertemplate="%{y} · 前30日日均 %{x:.1f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=win, y=gens, mode="markers", name="窗口日均下发线索",
        marker=dict(color=get_series_color("own"), size=12),
        hovertemplate="%{y} · 窗口日均 %{x:.1f}<extra></extra>",
    ))
    labels = []
    for r in lcg:
        if r["baseline_daily_avg"] and r["baseline_daily_avg"] > 0 and r["window_daily_avg"] is not None:
            d = r["window_daily_avg"] - r["baseline_daily_avg"]
            labels.append(f"{d:+.0f}（{d / r['baseline_daily_avg'] * 100:+.1f}%）")
        else:
            labels.append("—")
    fig.add_trace(go.Scatter(
        x=win, y=gens, mode="text", text=labels, textposition="middle right",
        showlegend=False, hoverinfo="skip",
    ))
    apply_zh_theme(fig)
    xmax = max([v for v in (win + base) if v is not None] or [0])
    fig.update_layout(
        height=max(270, 46 * len(gens)),
        margin=dict(l=20, r=120, t=30, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(title_text="日均下发线索（条/日）", rangemode="tozero", range=[0, xmax * 1.4 or 1])
    fig.update_yaxes(autorange="reversed")
    return _chart_box(fig, "lead_amplitude")


def chart_lead_ratio(lcg: list[dict], main_gen: str) -> str | None:
    go, ZH, apply_zh_theme, get_series_color = _plotly_deps()
    if go is None:
        return None
    rows = [r for r in lcg if r["small_order_lead_ratio"] is not None]
    if not rows:
        return None
    rows.sort(key=lambda r: r["small_order_lead_ratio"], reverse=True)
    gens = [r["gen"] for r in rows]
    vals = [r["small_order_lead_ratio"] * 100 for r in rows]
    colors = [get_series_color("own") if g == main_gen else "#B6C3CE" for g in gens]
    fig = go.Figure(go.Bar(
        x=vals, y=gens, orientation="h",
        marker_color=colors,
        text=[f"{v:.2f}%" for v in vals], textposition="outside",
        hovertemplate="%{y} · 小订/线索日均比值 %{x:.2f}%<extra></extra>",
    ))
    apply_zh_theme(fig)
    fig.update_layout(
        height=max(240, 42 * len(gens)),
        margin=dict(l=20, r=70, t=30, b=30),
    )
    fig.update_xaxes(title_text="小订/线索日均比值（%）", rangemode="tozero")
    fig.update_yaxes(autorange="reversed")
    return _chart_box(fig, "lead_ratio")


def _pk_barcell_table(pk: dict, rank_col: str, cmp_gen: str, main_gen: str) -> str:
    """周 × 竞品 排名条形表：列 = 前代预售周 + 本代预售周。

    单元格为 barcell（横条宽度 ∝ PK次数，跨两周统一标度；文字为该周排名），
    行按本代预售周 PK次数降序。样式复用 templates/report_style.css 的 .barcell。
    """
    cmp_map = {str(r["车系"]): r for _, r in pk["cmp_rows"].iterrows()}
    main_map = {str(r["车系"]): r for _, r in pk["main_rows"].iterrows()}
    cars = list(dict.fromkeys(list(main_map.keys()) + list(cmp_map.keys())))
    if not cars:
        return ""
    pk_max = max(int(r["PK次数"]) for r in [*cmp_map.values(), *main_map.values()])
    cars.sort(key=lambda c: -(int(main_map[c]["PK次数"]) if c in main_map else -1))

    def _cell(r) -> str:
        if r is None:
            return '<td class="num">—</td>'
        cnt = int(r["PK次数"])
        rank = int(r[rank_col])
        width = int(round(100 * cnt / pk_max)) if pk_max else 0
        return (f'<td><div class="barcell" title="PK次数: {cnt:,}">'
                f'<div class="bar" style="width:{width}%;"></div>'
                f'<div class="txt">{rank}</div></div></td>')

    def _head(gen: str, week: str) -> str:
        wk = (f'<br/><span style="font-weight:400;font-size:11px;color:#6B7C8F;">{week}</span>'
              if week else "")
        return f"{gen} 预售周{wk}"

    rows = []
    for car in cars:
        r = main_map.get(car) if car in main_map else cmp_map.get(car)
        brand = str(r["品牌"]) if r is not None else ""
        rows.append(f"<tr><td>{car}</td><td>{brand}</td>"
                    f"{_cell(cmp_map.get(car))}{_cell(main_map.get(car))}</tr>")
    th = (f"<th>竞品车系</th><th>品牌</th>"
          f"<th>{_head(cmp_gen, pk.get('cmp_week') or '')}</th>"
          f"<th>{_head(main_gen, pk.get('main_week') or '')}</th>")
    return (f'<div class="table-wrap"><table class="report-table">'
            f'<thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def chart_profile(pfx: dict, gens: list[str], main_gen: str) -> str | None:
    """用户画像 small multiples：每代际一列，行 = 性别 / 城市线级 / 省份 Top5。"""
    go, ZH, apply_zh_theme, get_series_color = _plotly_deps()
    if go is None or not gens:
        return None
    from plotly.subplots import make_subplots

    k = len(gens)
    fig = make_subplots(
        rows=2, cols=k,
        subplot_titles=[g if r == 0 else "" for r in range(2) for g in gens],
        vertical_spacing=0.07, horizontal_spacing=0.03,
        row_heights=[0.17, 0.83],
    )

    for j, gen in enumerate(gens):
        p = pfx[gen]
        if not p["n"]:
            continue
        col = j + 1
        # 性别结构（100% 堆叠；剔除「未知」后按已知性别为基数）
        g_base = _known_gender_base(p) or 1
        segs = [("男", p["gender"].get("男", 0) / g_base * 100, get_series_color("own")),
                ("女", p["gender"].get("女", 0) / g_base * 100, get_series_color("competitor", 1))]
        for label, v, color in segs:
            if v <= 0:
                continue
            fig.add_trace(go.Bar(
                x=[v], y=[label], orientation="h", showlegend=False, marker_color=color,
                text=[f"{v:.0f}%"], textposition="inside", insidetextanchor="middle",
                textfont=dict(color="#ffffff", size=11),
                hovertemplate=f"{gen} · {label} {v:.1f}%<extra></extra>"), row=1, col=col)
        # 年龄分层（占已知年龄比例，按代际着色；主代际高亮）
        a_base = p.get("age_nonnull", 0) or 1
        gcolor = get_series_color("own") if gen == main_gen else get_series_color("steel")
        for band in AGE_BAND_LABELS:
            cnt = p["age_bands"].get(band, 0)
            if cnt <= 0:
                continue
            v = cnt / a_base * 100
            fig.add_trace(go.Bar(
                x=[v], y=[band], orientation="h", showlegend=False, marker_color=gcolor,
                text=f"{v:.0f}%" if v >= 3 else "", textposition="outside",
                hovertemplate=f"{gen} · {band} {v:.1f}%<extra></extra>"), row=2, col=col)

    apply_zh_theme(fig)
    fig.update_layout(
        barmode="stack", showlegend=False,
        height=480,
        margin=dict(l=80, r=30, t=40, b=30),
    )
    fig.update_xaxes(range=[0, 105])
    for c in range(1, k + 1):
        fig.update_yaxes(autorange="reversed", row=1, col=c)
        fig.update_yaxes(autorange="reversed", row=2, col=c)
    # 行标签（paper 左缘）
    for r, label in ((1, "性别"), (2, "年龄分层")):
        ya = fig.layout[f"yaxis{(r - 1) * k + 1}"].domain
        fig.add_annotation(x=0, y=(ya[0] + ya[1]) / 2, xref="paper", yref="paper",
                           text=label, showarrow=False, xanchor="right",
                           font=dict(size=12, color=get_series_color("ash")))
    # 主代际列标题高亮
    for col, gen in enumerate(gens):
        if gen == main_gen:
            fig.layout.annotations[col].font.color = get_series_color("own")
            fig.layout.annotations[col].font.weight = "bold"  # type: ignore[attr-defined]
    return _chart_box(fig, "profile_small_multiples")


# ── HTML 渲染 ────────────────────────────────────────────

def _h_table(headers: list[str], rows: list[list[str]], num_cols: set[int] | None = None,
             bold_rows: set[int] | None = None,
             highlight_cells: set[tuple[int, int]] | None = None) -> str:
    num_cols = num_cols or set()
    bold_rows = bold_rows or set()
    highlight_cells = highlight_cells or set()
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = []
    for ri, row in enumerate(rows):
        tds = []
        for ci, cell in enumerate(row):
            cls = []
            if ci in num_cols:
                cls.append("num")
            if (ri, ci) in highlight_cells:
                cls.append("cell-max")
            attr = f' class="{" ".join(cls)}"' if cls else ""
            tds.append(f"<td{attr}>{cell}</td>")
        style = ' class="row-highlight"' if ri in bold_rows else ""
        trs.append(f"<tr{style}>{''.join(tds)}</tr>")
    return f'<div class="table-wrap"><table class="report-table"><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


def _h_kpi(value: str, label: str, hint: str = "") -> str:
    hint_html = f'<div class="summary-hint">{hint}</div>' if hint else ""
    return f'<div class="summary-card"><div class="summary-value">{value}</div><div class="summary-label">{label}</div>{hint_html}</div>'


def _h_section(title: str, inner: str, note: str = "") -> str:
    note_html = f'<p class="section-note">{note}</p>' if note else ""
    return f'<section class="report-section"><h2 class="section-title">{title}</h2>{note_html}{inner}</section>'


def _cell_conv(w: float, b_: float) -> str:
    if pd.isna(w) or pd.isna(b_):
        return "—"
    return f"{w * 100:.1f}% → {b_ * 100:.1f}%（{(w - b_) * 100:+.1f}pp）"


def render_html(c: dict, df: pd.DataFrame, bd: dict, as_of: pd.Timestamp, out_dir: Path) -> Path:
    import html as html_lib

    esc = html_lib.escape
    static = "../.."
    gens = c["gens"]
    main_gen = c["main_gen"]
    core = c["core"]

    global _PNG_DIR, _PNG_PREFIX
    _PNG_DIR = out_dir.parent / "charts"
    _PNG_PREFIX = main_gen
    S: list[str] = []
    A = S.append

    A('<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8" />')
    A('<meta name="viewport" content="width=device-width, initial-scale=1.0" />')
    A(f"<title>{esc(c['label'])} 预售情况汇报 | {c['as_of']}</title>")
    A(f'<link rel="stylesheet" href="{static}/templates/report_style.css" />')
    A(_PLOTLY_CDN)
    A('</head>\n<body class="report-page">\n<header><div class="container">')
    A('<div class="brand"><img class="brand-avatar" src="../../assets/brand/raccoon_avatar_light.png" alt="" />'
      '<span class="brand-name">Raccoon Research</span></div>')
    A(f"<span class=\"header-meta\">{esc(c['label'])} 预售情况汇报 · 截至 {c['as_of']}</span>")
    A('</div></header>\n<main class="report-container">\n')
    A(f"<div class=\"hero\"><h1>{esc(c['label'])} 预售情况汇报</h1>")
    A(f"<p>release {main_gen} 口径 · 预售窗口 {c['window']['start']} ~ {c['window']['end']}（N={c['n_days']}）"
      f"· 数据截至 {c['as_of']}<br/>口径：预售开放时刻之后支付意向金且未退的留存小订；试驾车不纳入</p></div>")

    A('<div class="summary-grid">')
    A(_h_kpi(_fmt_int(core["retention"]), "留存小订（报告口径）", "开放时刻起未退意向金"))
    A(_h_kpi(_fmt_int(core["cum"]), "累计小订", "含已退订"))
    A(_h_kpi(_fmt_int(core["retention_users"]), "留存唯一订单用户", ""))
    A(_h_kpi(_fmt_int(core["start_day_retained"]), "开盘日留存", "20:00-24:00"))
    A("</div>")

    # 头部图表
    dm2_flow = _daily_flows(df, bd, as_of, main_gen)
    cmp_gen = c["cmp_gen"]
    cmp_flow = _daily_flows(df, bd, as_of, cmp_gen)
    flow_name = f"presale_{main_gen}_每日小订退订.html"
    chart_path = render_flow_chart(dm2_flow, out_dir.parent / "charts" / flow_name, main_gen,
                                   flow_compare=cmp_flow, compare_label=f"{cmp_gen} 同窗口累计留存（右轴）")
    if chart_path:
        A(_h_section(f"预售期每日小订 × 退订（release 口径 · {cmp_gen} 同窗口对比）",
                     f'<div class="chart-box"><iframe src="../charts/{flow_name}" '
                     'style="width:100%;height:410px;border:0;" loading="lazy" '
                     'title="预售期每日小订与退订对比"></iframe></div>',
                     note=f"上方柱 = 每日新支付小订，下方柱 = 每日退订（release {main_gen} 口径）；"
                          f"Σ每日新支付 = 累计小订 {_fmt_int(core['cum'])}，Σ新支付 − Σ退订 = 留存小订 {_fmt_int(core['retention'])}；"
                          f"灰线 = {main_gen} 累计留存，蓝色虚线 = {cmp_gen} 同窗口累计留存（右轴）。"))

    # 模块 1/2：核心 + 对标
    bench = c["benchmark"]
    main_idx = next((i for i, b in enumerate(bench) if b["gen"] == main_gen), 0)
    rows_bench = [[b["gen"], _fmt_int(b["ret_n"]), b["peak_h"], _fmt_int(b["peak_c"]),
                   _fmt_int(b["start_day_total"]), _fmt_int(b["start_day_retained"])] for b in bench]
    A(_h_section("一、预售对标（跨代际 · 同 N 日窗口）",
                 (chart_benchmark(bench, main_gen) or "") + _h_table(
                     ["代际", "同 N 日留存", "首日峰值小时", "峰值小时小订", "开盘日小订", "开盘日留存"],
                     rows_bench, num_cols={1, 3, 4, 5}, bold_rows={main_idx}),
                 note=f"统一按各自预售开放时刻起算，N={c['n_days']} 日同窗口；开盘日 = 开放时刻 ~ 当日 24:00。"
                      f"截至快照日 release 口径尚无大定/锁单转化（预售期试驾车不计入零售）。"))

    # 模块 3：产品结构（纯产品）
    rows_prod = [[p["product"], _fmt_int(p["count"]), _fmt_pct(p["share"])] for p in c["product"]]
    rows_prod.append([f"<strong>合计</strong>", f"<strong>{_fmt_int(core['retention'])}</strong>", "<strong>100%</strong>"])
    A(_h_section("二、产品结构（留存小订）",
                 (chart_product(c["product"], core["retention"]) or "") + _h_table(
                     ["产品", "留存订单", "占比"], rows_prod, num_cols={1, 2})))

    # 模块 4：大区结构
    reg = c["region"]
    m_reg, c_reg = reg["main"], reg["cmp"]
    m_total = sum(m_reg.values()) or 1
    c_total = sum(c_reg.values()) or 1
    all_regs = list(dict.fromkeys(list(m_reg.keys()) + list(c_reg.keys())))
    rows_reg = []
    for r in sorted(all_regs, key=lambda x: (-m_reg.get(x, 0), -c_reg.get(x, 0))):
        c2, c1 = m_reg.get(r, 0), c_reg.get(r, 0)
        s2, s1 = c2 / m_total, c1 / c_total
        rows_reg.append([r, _fmt_int(c2), _fmt_pct(s2),
                         (_fmt_int(c1) if c1 else "—"), (_fmt_pct(s1) if c1 else "—"),
                         (f"{(s2 - s1) * 100:+.1f}" if c1 else "—")])
    rows_reg.append([f"<strong>合计</strong>", f"<strong>{_fmt_int(m_total)}</strong>", "<strong>100%</strong>",
                     f"<strong>{_fmt_int(c_total)}</strong>", "<strong>100%</strong>", "—"])
    A(_h_section(f"三、大区结构（留存小订 · {main_gen} vs {cmp_gen} 同 N 日窗口）",
                 (chart_region_dumbbell(reg, main_gen, cmp_gen) or "") + _h_table(
                     [f"大区（新架构口径）", f"{main_gen} 留存订单", f"{main_gen} 占比",
                      f"{cmp_gen} 留存订单*", f"{cmp_gen} 占比*", f"占比差（{main_gen}−{cmp_gen}，pp）"],
                     rows_reg, num_cols={1, 3}),
                 note=f"*{cmp_gen} 为其预售开放日起 N={c['n_days']} 同窗口留存小订（总量约为 {main_gen} 的 "
                      f"{c_total / m_total:.0f} 倍），看结构占比。大区命名已按省份组归一。" if c_total else ""))

    # 模块 5：线索→预订间隔
    gapx = c["lead_gap"]
    rows_gap = []
    for gen in gens:
        b_ = gapx[gen]
        med = f"{b_['med']:.2f}d" if not pd.isna(b_["med"]) else "—"
        rows_gap.append([gen, _fmt_int(b_["n"]),
                         (_fmt_pct(b_["before"], 1) if not pd.isna(b_["before"]) else "—"), med,
                         (_fmt_pct(b_["instant"], 1) if not pd.isna(b_["instant"]) else "—"),
                         (_fmt_pct(b_["wait"], 1) if not pd.isna(b_["wait"]) else "—"),
                         (_fmt_pct(b_["stock"], 1) if not pd.isna(b_["stock"]) else "—")])
    # 各指标列最大值高亮（样本列不参与）
    gap_max_cells: set[tuple[int, int]] = set()
    for key, ci in (("before", 2), ("med", 3), ("instant", 4), ("wait", 5), ("stock", 6)):
        vals = [(float(gapx[g][key]), ri) for ri, g in enumerate(gens) if not pd.isna(gapx[g][key])]
        if vals:
            gap_max_cells.add((max(vals)[1], ci))
    A(_h_section("四、线索→预订间隔（预售前线索占比 + 即时/观望/存量 · 跨代际）",
                 _h_table(
                     ["代际", "样本", "预售前线索占比", "间隔中位", "即时 0-3天", "观望 3-30天", "存量 >30天"],
                     rows_gap, num_cols={1, 2, 3, 4, 5, 6}, bold_rows={main_idx},
                     highlight_cells=gap_max_cells),
                 note="间隔 = 意向金支付 − 首次下发线索（first_assign_time）；预售前线索占比 = 线索下发早于预售开放时刻的订单占比。金色底为该列最大值。"))

    # 模块 6：预售窗口期下发线索增幅对比（逐代际）
    asg = c["assign"]
    lcg = asg["cross"]
    lcg_idx = next((i for i, r in enumerate(lcg) if r["gen"] == main_gen), 0)
    rows_lead = []
    for r in lcg:
        if r["baseline_daily_avg"] and r["baseline_daily_avg"] > 0:
            delta = r["window_daily_avg"] - r["baseline_daily_avg"]
            delta_str = f"{delta:+.1f}（{delta / r['baseline_daily_avg'] * 100:+.1f}%）"
        else:
            delta_str = "—"
        rows_lead.append([
            r["gen"], f"{r['window_start']}~{r['window_end'] or '—'}",
            (f"{r['window_daily_avg']:.1f}" if r["window_daily_avg"] is not None else "—"),
            (f"{r['baseline_daily_avg']:.1f}" if r["baseline_daily_avg"] is not None else "—"),
            delta_str,
        ])
    lcg_lead_idx = next((i for i, r in enumerate(lcg) if r["gen"] == main_gen), 0)
    A(_h_section("五、预售窗口期下发线索增幅对比",
                 (chart_lead_amplitude(lcg, main_gen) or "") + _h_table(
                     ["代际", "预售窗口", "窗口日均下发线索", "前30日下发线索日均", "窗口 vs 基线"],
                     rows_lead, num_cols={2, 3, 4}, bold_rows={lcg_lead_idx}),
                 note=f"完整观察日：{asg['complete_observation_date']}；预售窗口按各代际预售起点至完整观察日/预售结束日前一天。"
                      "下发线索为整体业务口径，不代表该车型专属线索。"))

    rows_lcg2 = [[r["gen"], f"{r['window_start']}~{r['window_end'] or '—'}",
                  _fmt_int(r["small_orders"]),
                  (f"{r['small_order_daily_avg']:.1f}" if r["small_order_daily_avg"] is not None else "—"),
                  (_fmt_pct(r["small_order_lead_ratio"], 2) if r["small_order_lead_ratio"] is not None else "—"),
                  (f"{r['window_daily_avg']:.1f}" if r["window_daily_avg"] is not None else "—")] for r in lcg]
    A(_h_section("跨代际：预售窗口期小订和下发线索比值",
                 (chart_lead_ratio(lcg, main_gen) or "") + _h_table(
                     ["代际", "预售窗口", "窗口小订", "窗口小订日均",
                      "小订/线索日均比值", "窗口下发线索日均"], rows_lcg2,
                     num_cols={2, 3, 4, 5}, bold_rows={lcg_idx}),
                 note="比值 = 预售窗口期小订日均 ÷ 前30日下发线索日均；小订数为预售开放时刻后支付意向金的去重订单数（含后续已退）。下发线索无车型字段，因此该比值是整体业务代理指标，不是车型真实转化率。"))

    # 模块 7：正反向 PK
    pk = c["pk"]
    if pk:
        _h3 = '<h3 style="margin:16px 0 6px;font-size:15px;color:#06213D;">'
        A(_h_section(f"六、正反向对比：{pk['series']} 竞品 PK 榜（{pk['main_week']}）",
                     f"{_h3}PK 正向排名 · 竞品对本品冲击（越小越强）</h3>"
                     + _pk_barcell_table(pk, "PK正向排名", cmp_gen, main_gen)
                     + f"{_h3}PK 反向排名 · 本品对竞品影响（越小越强）</h3>"
                     + _pk_barcell_table(pk, "PK反向排名", cmp_gen, main_gen),
                     note="单元格横条宽度 ∝ 该周 PK次数（两周统一标度），数字为该周排名；行按本代预售周 PK次数降序。"
                          "正向排名=竞品对本品的冲击强度；反向排名=本品对竞品的影响。"))
        cmp_cars = {str(r["车系"]): int(r["PK次数"]) for _, r in pk["cmp_rows"].head(8).iterrows()}
        main_cars = {str(r["车系"]): int(r["PK次数"]) for _, r in pk["main_rows"].head(8).iterrows()}
        if pk["cmp_week"]:
            all_cars = list(dict.fromkeys(list(cmp_cars.keys()) + list(main_cars.keys())))
            rows_cmp = [[car, (_fmt_int(cmp_cars[car]) if car in cmp_cars else "—"),
                         (_fmt_int(main_cars[car]) if car in main_cars else "—")] for car in all_cars]
            A(_h_section(f"跨代际对比：{cmp_gen} 预售周 vs {main_gen} 预售周（series={pk['series']}）",
                         _h_table(["竞品车系", f"{cmp_gen} 预售周（{pk['cmp_week']}）",
                                   f"{main_gen} 预售周（{pk['main_week']}）"], rows_cmp, num_cols={1, 2}),
                         note="PK 次数为绝对量级，跨年对比仅作结构参考。"))
        else:
            A(_h_section(f"跨代际对比：{cmp_gen} 预售周 vs {main_gen} 预售周",
                         '<p class="section-note">竞争 PK 数据未覆盖对标代际预售周，跳过跨代际 PK 对比。</p>'))
        rows_trend = [[r["week"], r["car"], _fmt_int(r["pk"]), str(r["fwd"]), str(r["rev"])] for r in pk["trend"]]
        A(_h_section(f"上汽集团竞品近 5 周 PK 趋势（series={pk['series']}）",
                     _h_table(["周", "车系", "PK次数", "PK正向排名", "PK反向排名"], rows_trend, num_cols={2})))

    # 模块 8：预选配置
    conf = c["config"]
    if conf and conf["covered"]:
        rows_cov = [[p["product"], _fmt_int(p["total"]), _fmt_int(p["withval"]),
                     _fmt_pct(p["withval"] / p["total"] if p["total"] else 0)] for p in conf["prod_rows"]]
        rows_cov.append([f"<strong>合计</strong>", f"<strong>{_fmt_int(core['retention'])}</strong>",
                         f"<strong>{_fmt_int(conf['covered'])}</strong>",
                         f"<strong>{_fmt_pct(conf['covered'] / core['retention'])}</strong>"])
        A(_h_section("七、预选配置：选配覆盖概览（按产品）",
                     _h_table(["产品", "留存订单", "有选配 value", "覆盖率"], rows_cov, num_cols={1, 2, 3}),
                     note="config_attribute.parquet 为 EAV 长表；留存池订单 value_code 若缺失则按显示名统计。"))
        rows_cfg = [[attr, v, _fmt_int(cnt), _fmt_pct(cnt / conf["covered"])]
                    for attr, vc in conf["attr_dist"].items() for v, cnt in vc.items()]
        A(_h_section("已选配置分布（按显示名）",
                     _h_table(["属性", "选项", "订单数", "占比"], rows_cfg, num_cols={2, 3}),
                     note=f"样本为留存小订池内有选配 value 的 {_fmt_int(conf['covered'])} 单。"))
    else:
        A(_h_section("七、预选配置", '<p class="section-note">配置表缺失或留存池无可用 value，暂不输出配置分析。</p>'))

    # 模块 9：用户画像
    pfx = c["profile"]
    def _pcell(gen: str, fn) -> str:
        v = fn(pfx[gen])
        return f"<strong>{v}</strong>" if gen == main_gen else str(v)

    metrics_pf = [
        ("留存小订样本", lambda p: _fmt_int(p["n"])),
        ("男性占比（order_gender，剔除未知）", lambda p: _fmt_pct(p["gender"].get("男", 0) / _known_gender_base(p)) if _known_gender_base(p) else "—"),
        ("年龄中位 / 均值（buyer_age）",
         lambda p: f"{p['age_median']:.0f} / {p['age_mean']:.1f}" if p["age_nonnull"] else "—"),
        ("年龄已知率", lambda p: _fmt_pct(p["age_nonnull"] / p["n"]) if p["n"] else "—"),
        ("主力年龄段", lambda p: _main_age_band(p)),
    ]
    rows_pfg = [[label] + [_pcell(gen, fn) for gen in gens] for label, fn in metrics_pf]
    A(_h_section("八、订单用户画像（留存小订 · release 口径 · 各代际对比）",
                 (chart_profile(pfx, gens, main_gen) or "") + _h_table(["指标"] + gens, rows_pfg),
                 note="各代际均为其预售开放时刻起同 N 日窗口内未退意向金的留存小订。性别占比剔除「默认未知」，按已知性别（男+女）为基数；年龄按 buyer_age（购车人年龄）分桶，占比为各带占「已知年龄」比例（预售留存池无 owner_age）。"))

    # 附录
    scope_rows = [
        ["订单", f"order_data.parquet · series_group_logic.{main_gen} · release 口径留存小订 {_fmt_int(core['retention'])} 单"],
        ["下发线索", "assign_data.csv · 预售窗口至完整观察日 vs 前30日基线；整体业务口径；小订/线索比为代理指标"],
        ["正反向", f"竞争PK（正反向排名）CSV · series={c['series']}" if pk else "竞争PK CSV 缺失/无该 series，跳过"],
        ["预选配置", f"config_attribute.parquet · 留存池 {_fmt_int(conf['covered']) if conf else 0} 单有 value"],
        ["用户画像", "order_data.parquet · release 口径留存小订"],
    ]
    A(_h_section("口径与数据源", _h_table(["模块", "口径"], scope_rows)))
    known = ("已知限制：预售订单口径统一为 release（留存小订）；预售期无零售大定/锁单转化；预售未结束存在右删失；"
             "正反向为竞争 PK 排名（非订单漏斗）；配置 value_code 可能缺失。")
    A(f'<p class="section-note">{esc(known)}</p>')

    A("</main>\n<footer>")
    A(f'<img class="brand-sig" src="{static}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />')
    A('<div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>')
    A("</footer>\n</body>\n</html>")

    out_path = out_dir / f"presale_cum_order_compare_{'_'.join(gens)}_{c['as_of'].replace('-', '')}.html"
    out_path.write_text("\n".join(S), encoding="utf-8")
    return out_path


# ── Markdown 渲染（--to-feishu 用；服务端 Markdown→Block） ─────

def _md_table(headers: list[str], rows: list[list]) -> str:
    esc = lambda x: str(x).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    lines = ["| " + " | ".join(esc(h) for h in headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(esc(x) for x in r) + " |")
    return "\n".join(lines)


# Markdown 章节 → 图表 PNG（文件名后缀；实际文件名 {main_gen}_{name}.png）。
MD_SECTION_IMAGES: list[tuple[str, list[str]]] = [
    ("二、跨代际对标", ["benchmark"]),
    ("三、产品结构", ["product"]),
    ("四、大区结构", ["region_dumbbell"]),
    ("六、预售窗口期下发线索增幅对比", ["lead_amplitude", "lead_ratio"]),
    ("九、订单用户画像", ["profile_small_multiples"]),
]


def _md_sections_with_images(md: str, main_gen: str, charts_dir: Path) -> list[tuple[str, list[Path]]]:
    """把 Markdown 按 `## ` 章节切分，并为每章匹配图表 PNG（存在才带）。"""
    chunks: list[list[str]] = []
    cur: list[str] = []
    for ln in md.splitlines():
        if ln.startswith("## ") and cur:
            chunks.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        chunks.append(cur)
    out: list[tuple[str, list[Path]]] = []
    for ch in chunks:
        text = "\n".join(ch).strip()
        if not text:
            continue
        title = ch[0][3:].strip() if ch[0].startswith("## ") else ""
        imgs: list[Path] = []
        for key, names in MD_SECTION_IMAGES:
            if title.startswith(key):
                for n in names:
                    p = charts_dir / f"{main_gen}_{n}.png"
                    if p.exists():
                        imgs.append(p)
        out.append((text, imgs))
    return out


def render_markdown(c: dict) -> str:
    gens = c["gens"]
    main_gen = c["main_gen"]
    cmp_gen = c["cmp_gen"]
    core = c["core"]
    L: list[str] = []
    A = L.append

    A(f"# {c['label']} 预售情况汇报")
    A("")
    A(f"> 数据快照：截至 **{c['as_of']}**；预售窗口 {c['window']['start']} ~ {c['window']['end']}"
      f"（开放时刻 {c['window']['open']}）  ")
    A(f"> 主代际：**{main_gen}**；对标代际：{' / '.join(g for g in gens if g != main_gen)}  ")
    A(f"> 口径：release 留存小订（预售开放时刻后支付意向金且未退）；同 N 日窗口 N={c['n_days']}；试驾车不纳入零售。")
    A("")

    A("## 一、预售核心指标")
    A("")
    A(_md_table(["指标", "数值"], [
        ["累计小订（含已退）", _fmt_int(core["cum"])],
        ["留存小订（报告口径）", _fmt_int(core["retention"])],
        ["留存唯一用户", _fmt_int(core["retention_users"])],
        ["开盘日小订", _fmt_int(core["start_day_total"])],
        ["开盘日留存", _fmt_int(core["start_day_retained"])],
        ["首日峰值小时", f"{_fmt_int(core['peak_count'])}（{core['peak_hour']}）"],
        ["开放 24h 累计", _fmt_int(core["day24"])],
    ]))
    A("")

    A(f"## 二、跨代际对标（同 N={c['n_days']} 日窗口）")
    A("")
    A(_md_table(["代际", "同 N 日留存", "首日峰值小时", "峰值小时小订", "开盘日小订", "开盘日留存"],
                [[b["gen"], _fmt_int(b["ret_n"]), b["peak_h"], _fmt_int(b["peak_c"]),
                  _fmt_int(b["start_day_total"]), _fmt_int(b["start_day_retained"])] for b in c["benchmark"]]))
    A("")

    A("## 三、产品结构（留存小订）")
    A("")
    A(_md_table(["产品", "留存订单", "占比"],
                [[p["product"], _fmt_int(p["count"]), _fmt_pct(p["share"])] for p in c["product"]]))
    A("")

    reg = c["region"]
    m_reg, c_reg = reg["main"], reg["cmp"]
    m_total = sum(m_reg.values()) or 1
    c_total = sum(c_reg.values()) or 1
    all_regs = list(dict.fromkeys(list(m_reg.keys()) + list(c_reg.keys())))
    rows_reg = []
    for r in sorted(all_regs, key=lambda x: (-m_reg.get(x, 0), -c_reg.get(x, 0))):
        c2, c1 = m_reg.get(r, 0), c_reg.get(r, 0)
        rows_reg.append([r, _fmt_int(c2), _fmt_pct(c2 / m_total),
                         (_fmt_int(c1) if c1 else "—"),
                         (_fmt_pct(c1 / c_total) if c1 else "—")])
    A(f"## 四、大区结构（{main_gen} vs {cmp_gen} 同 N 日窗口）")
    A("")
    A(_md_table([f"大区", f"{main_gen} 留存", f"{main_gen} 占比", f"{cmp_gen} 留存", f"{cmp_gen} 占比"], rows_reg))
    A("")

    A("## 五、线索→预订间隔（跨代际）")
    A("")
    rows_gap = []
    for gen in gens:
        b_ = c["lead_gap"][gen]
        rows_gap.append([
            gen, _fmt_int(b_["n"]),
            (_fmt_pct(b_["before"], 1) if not pd.isna(b_["before"]) else "—"),
            (f"{b_['med']:.2f}d" if not pd.isna(b_["med"]) else "—"),
            (_fmt_pct(b_["instant"], 1) if not pd.isna(b_["instant"]) else "—"),
            (_fmt_pct(b_["wait"], 1) if not pd.isna(b_["wait"]) else "—"),
            (_fmt_pct(b_["stock"], 1) if not pd.isna(b_["stock"]) else "—"),
        ])
    A(_md_table(["代际", "样本", "预售前线索占比", "间隔中位", "即时 0-3天", "观望 3-30天", "存量 >30天"], rows_gap))
    A("")

    asg = c["assign"]
    lcg = asg["cross"]
    rows_lead = []
    for r in lcg:
        if r["baseline_daily_avg"] and r["baseline_daily_avg"] > 0:
            delta = r["window_daily_avg"] - r["baseline_daily_avg"]
            delta_str = f"{delta:+.1f}（{delta / r['baseline_daily_avg'] * 100:+.1f}%）"
        else:
            delta_str = "—"
        rows_lead.append([
            r["gen"], f"{r['window_start']}~{r['window_end'] or '—'}",
            (f"{r['window_daily_avg']:.1f}" if r["window_daily_avg"] is not None else "—"),
            (f"{r['baseline_daily_avg']:.1f}" if r["baseline_daily_avg"] is not None else "—"),
            delta_str,
        ])
    A("## 六、预售窗口期下发线索增幅对比")
    A("")
    A(f"> 完整观察日：{asg['complete_observation_date']}；窗口从预售开始日至完整观察日/预售结束日前一天；下发线索为整体业务口径。")
    A("")
    A(_md_table(["代际", "预售窗口", "窗口日均下发线索", "前30日下发线索日均", "窗口 vs 基线"], rows_lead))
    A("")
    rows_ratio = [[r["gen"], f"{r['window_start']}~{r['window_end'] or '—'}",
                   _fmt_int(r["small_orders"]),
                   (f"{r['small_order_daily_avg']:.1f}" if r["small_order_daily_avg"] is not None else "—"),
                   (_fmt_pct(r["small_order_lead_ratio"], 2) if r["small_order_lead_ratio"] is not None else "—"),
                   (f"{r['window_daily_avg']:.1f}" if r["window_daily_avg"] is not None else "—")] for r in asg["cross"]]
    A(_md_table(["代际", "预售窗口", "窗口小订", "窗口小订日均",
                 "小订/线索日均比值", "窗口下发线索日均"], rows_ratio))
    A("> 比值 = 预售窗口期小订日均 ÷ 前30日下发线索日均；小订数为预售开放时刻后支付意向金的去重订单数（含后续已退）。下发线索无车型字段，该比值是整体业务代理指标，不是车型真实转化率。")
    A("")

    pk = c["pk"]
    if pk:
        A(f"## 七、正反向对比（{pk['series']} 竞品 PK）")
        A("")
        A(f"**{pk['series']} 竞品 PK 榜（{pk['main_week']}）**")
        A("")
        A(_md_table(["竞品车系", "品牌", "PK次数", "PK正向排名", "PK反向排名"],
                    [[str(r["车系"]), str(r["品牌"]), _fmt_int(int(r["PK次数"])),
                      str(int(r["PK正向排名"])), str(int(r["PK反向排名"]))]
                     for _, r in pk["main_rows"].head(10).iterrows()]))
        A("")
        if pk["cmp_week"]:
            cmp_cars = {str(r["车系"]): int(r["PK次数"]) for _, r in pk["cmp_rows"].head(8).iterrows()}
            main_cars = {str(r["车系"]): int(r["PK次数"]) for _, r in pk["main_rows"].head(8).iterrows()}
            all_cars = list(dict.fromkeys(list(cmp_cars.keys()) + list(main_cars.keys())))
            A(f"**跨代际：{cmp_gen} 预售周（{pk['cmp_week']}） vs {main_gen} 预售周（{pk['main_week']}）**")
            A("")
            A(_md_table(["竞品车系", f"{cmp_gen} PK次数", f"{main_gen} PK次数"],
                        [[car, (_fmt_int(cmp_cars[car]) if car in cmp_cars else "—"),
                          (_fmt_int(main_cars[car]) if car in main_cars else "—")] for car in all_cars]))
            A("")

    conf = c["config"]
    A("## 八、预选配置")
    A("")
    if conf and conf["covered"]:
        rows_cov = [[p["product"], _fmt_int(p["total"]), _fmt_int(p["withval"]),
                     _fmt_pct(p["withval"] / p["total"] if p["total"] else 0)] for p in conf["prod_rows"]]
        rows_cov.append(["合计", _fmt_int(core["retention"]), _fmt_int(conf["covered"]),
                         _fmt_pct(conf["covered"] / core["retention"])])
        A(_md_table(["产品", "留存订单", "有选配 value", "覆盖率"], rows_cov))
        A("")
        A(_md_table(["属性", "选项（显示名）", "订单数", "占比"],
                    [[attr, v, _fmt_int(cnt), _fmt_pct(cnt / conf["covered"])]
                     for attr, vc in conf["attr_dist"].items() for v, cnt in vc.items()]))
    else:
        A("> 配置表缺失或留存池无可用 value，暂不输出配置分析。")
    A("")

    pfx = c["profile"]
    A("## 九、订单用户画像（留存小订 · 各代际对比）")
    A("")
    A(_md_table(["指标"] + gens, [
        ["留存小订样本"] + [_fmt_int(pfx[g]["n"]) for g in gens],
        ["男性占比（剔除未知）"] + [(_fmt_pct(pfx[g]["gender"].get("男", 0) / _known_gender_base(pfx[g])) if _known_gender_base(pfx[g]) else "—") for g in gens],
        ["年龄中位 / 均值（buyer_age）"] + [(f"{pfx[g]['age_median']:.0f} / {pfx[g]['age_mean']:.1f}" if pfx[g]["age_nonnull"] else "—") for g in gens],
        ["年龄已知率"] + [(_fmt_pct(pfx[g]["age_nonnull"] / pfx[g]["n"]) if pfx[g]["n"] else "—") for g in gens],
        ["主力年龄段"] + [_main_age_band(pfx[g]) for g in gens],
    ]))
    A("")

    A("## 口径与数据源")
    A("")
    A(_md_table(["模块", "口径"], [
        ["订单", f"order_data.parquet · series_group_logic.{main_gen} · release 留存小订 {_fmt_int(core['retention'])} 单"],
        ["下发线索", "assign_data.csv · 预售窗口至完整观察日 vs 前30日基线；整体业务口径；小订/线索比为代理指标"],
        ["正反向", (f"竞争PK（正反向排名）CSV · series={c['series']}" if pk else "竞争PK CSV 缺失/无该 series，跳过")],
        ["预选配置", f"config_attribute.parquet · 留存池 {_fmt_int(conf['covered']) if conf else 0} 单有 value"],
        ["用户画像", "order_data.parquet · release 口径留存小订"],
    ]))
    A("")
    A("> 已知限制：预售订单口径统一为 release（留存小订）；预售期无零售大定/锁单转化；"
      "预售未结束存在右删失；正反向为竞争 PK 排名（非订单漏斗）；配置 value_code 可能缺失。")
    return "\n".join(L)


# ── terminal ─────────────────────────────────────────────


def terminal(c: dict) -> None:
    core = c["core"]
    print(f"[Summary] {c['label']}（{c['main_gen']}）预售情况 · 截至 {c['as_of']} · N={c['n_days']}")
    print()
    print("[Scope]")
    print(f"  数据源: order_data.parquet · series_group_logic.{c['main_gen']}")
    print(f"  时间窗口: {c['window']['start']} ~ {c['window']['end']}；开放时刻 {c['window']['open']}")
    print(f"  过滤条件: release 口径留存小订；试驾车不纳入零售")
    print(f"  对标代际: {' / '.join(c['gens'])}")
    print()
    print("[Result]")
    print(f"  累计小订: {core['cum']:,}；留存小订: {core['retention']:,}；唯一用户: {core['retention_users']:,}")
    print(f"  开盘日留存: {core['start_day_retained']:,}（小订 {core['start_day_total']:,}）")
    print(f"  首日峰值: {core['peak_count']:,}（{core['peak_hour']}）")
    print()
    print("  跨代际同 N 日留存:")
    for b in c["benchmark"]:
        mark = " ←" if b["gen"] == c["main_gen"] else ""
        print(f"    {b['gen']:>5}: {b['ret_n']:>7,}{mark}")


# ── main ─────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="通用车型预售情况对比报告（terminal/json/html）")
    p.add_argument("--gens", type=str, nargs="*", default=None,
                   help=f"代际（按预售先后传入，末位=主代际；默认 {' '.join(DEFAULT_GENS)}）")
    p.add_argument("--as-of", type=str, default=None, help="统计基准日 YYYY-MM-DD（默认今天）")
    p.add_argument("--n-days", type=int, default=DEFAULT_N_DAYS, help=f"同 N 日留存窗口（默认 {DEFAULT_N_DAYS}）")
    p.add_argument("--format", choices=["terminal", "json", "html"], default="html",
                   help="输出格式（默认 html）")
    p.add_argument("--output", type=str, default=None, help="HTML/JSON 输出目录")
    p.add_argument("--html", action="store_true", help="生成 HTML 报告（等价 --format html）")
    p.add_argument("--to-feishu", action="store_true", help="额外产出飞书云文档（默认不产出，仅 HTML）")
    p.add_argument("--feishu-folder", type=str, default=None,
                   help="飞书目标文件夹 token（默认 FEISHU_DOCX_FOLDER_TOKEN）")
    p.add_argument("--feishu-dry-run", action="store_true", help="仅预览飞书文档写入计划，不触网")
    p.add_argument("--pk-csv", type=str, default=DEFAULT_PK_CSV, help="竞争 PK 正反向排名 CSV 路径")
    p.add_argument("--include-test-orders", action="store_true", help="不剔除测试单（默认剔除）")
    args = p.parse_args(argv)

    if not ORDER_PARQUET.exists():
        print(f"❌ 文件不存在: {ORDER_PARQUET}")
        return 1

    bd = load_business_definition(BUSINESS_DEF)
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp(datetime.now().date())

    gens = args.gens
    if not gens:
        active = detect_active(bd, as_of, phases=("presale",))
        if not active:
            print(f"⚠️ {as_of.date()} 无 presale 代际，且未显式传入 --gens")
            return 0
        main = active[0]["generation"]
        ck = compare_keys(bd, main)
        gens = list(reversed(ck)) + [main] if ck else [main]
    missing = [g for g in gens if g not in (bd.get("time_periods") or {})]
    if missing:
        print(f"⚠️ 代际不在 time_periods，无法解析预售窗口: {missing}")
        return 1
    if len(gens) < 1:
        print("⚠️ --gens 为空")
        return 1

    df = load_order(bd, exclude_test=not args.include_test_orders)
    pk_path = Path(args.pk_csv)
    pk = load_pk(pk_path) if pk_path.exists() else None
    if pk is None:
        print(f"⚠️ 竞争 PK CSV 不存在，跳过模块 7: {pk_path}")

    c = compute_all(df, bd, as_of, gens, args.n_days, pk)

    fmt = "html" if args.html else args.format
    if args.to_feishu:
        fmt = "html"  # 飞书文档与 HTML 报告同时产出
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
            "script": "research_scripts/presale_cumulative_order_compare.py",
            "scope": {
                "data_source": "dataset/order_data.parquet + dataset/assign_data.csv + shared/schema/business_definition.json",
                "time_window": {"start": c["window"]["start"], "end": c["window"]["end"],
                                "open": c["window"]["open"], "as_of": c["as_of"], "n_days": c["n_days"]},
                "filters": {"gens": c["gens"], "main_gen": c["main_gen"],
                            "metric_definition": "留存小订 = 预售开放时刻后支付意向金且未退；同 N 日窗口为各自开放时刻起 N 日"},
            },
            "result": {
                "summary": f"{c['label']}（{c['main_gen']}）预售情况 · 留存小订 {_fmt_int(c['core']['retention'])} 单 · 截至 {c['as_of']}",
                "metrics": {"cum": c["core"]["cum"], "retention": c["core"]["retention"],
                            "retention_users": c["core"]["retention_users"],
                            "start_day_retained": c["core"]["start_day_retained"]},
                "benchmark": c["benchmark"],
                "product": c["product"],
                "region": c["region"],
                "lead_booking_gap": c["lead_gap"],
                "assign": c["assign"],
                "pk": {"series": c["pk"]["series"], "main_week": c["pk"]["main_week"],
                       "cmp_week": c["pk"]["cmp_week"]} if c["pk"] else None,
                "config_covered": (c["config"] or {}).get("covered"),
                "profile": c["profile"],
            },
            "artifacts": {},
            "followup_context": {"metric": "presale_retention", "gens": c["gens"], "main_gen": c["main_gen"],
                                 "available_dimensions": ["day", "product", "region", "channel"]},
            "warnings": [],
            "errors": [],
        }
        out = out_dir / f"presale_cum_order_compare_{'_'.join(c['gens'])}.json"
        out.write_text(json.dumps(contract, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"已输出: {out}")
        return 0

    # html
    out = render_html(c, df, bd, as_of, out_dir)
    print(f"✅ HTML 报告已生成: {out}")
    if args.to_feishu:
        rc = publish_feishu(c, args, out_dir.parent / "charts")
        return rc if rc else 0
    return 0


def publish_feishu(c: dict, args, charts_dir) -> int:
    """把报告写入飞书云文档：Markdown→Block，并在对应章节内嵌图表 PNG。"""
    from capabilities.feishu.auth import FeishuAPIError
    from capabilities.feishu.docx import FeishuDocxClient

    title = f"{c['label']} 预售情况汇报 {c['as_of']}"
    client = FeishuDocxClient(folder_token=args.feishu_folder, dry_run=args.feishu_dry_run)
    sections = _md_sections_with_images(render_markdown(c), c["main_gen"], Path(charts_dir))
    n_imgs = sum(len(imgs) for _, imgs in sections)

    if client.dry_run:
        print(f"🧪 飞书文档 dry-run：{title}（{len(sections)} 章 / {n_imgs} 图，未触网）")
        for text, imgs in sections:
            head = text.splitlines()[0][:40] if text else ""
            if imgs:
                print(f"    · {head} ← {', '.join(p.name for p in imgs)}")
        return 0

    try:
        document_id = client.create_document(title, folder_token=args.feishu_folder)
        n_blocks = 0
        n_uploaded = 0
        img_errors: list[str] = []
        for text, imgs in sections:
            conv = client.convert_to_blocks(text, content_type="markdown")
            client.insert_descendants(document_id, conv["blocks"], conv["first_level_block_ids"], index=-1)
            n_blocks += len(conv["blocks"])
            for p in imgs:
                try:
                    client.insert_image(document_id, p, index=-1)
                    n_uploaded += 1
                except Exception as e:  # noqa: BLE001
                    img_errors.append(f"{p.name}: {e}")
    except FeishuAPIError as e:
        print(f"❌ 飞书文档生成失败: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"❌ 飞书文档生成异常: {e}")
        return 1
    print(f"✅ 飞书云文档已生成: {client.document_url(document_id)}（blocks={n_blocks}, images={n_uploaded}）")
    for msg in img_errors:
        print(f"⚠️ 图片插入被拒（已跳过）: {msg}")
    return 0
    try:
        res = client.create_document_from_markdown(title, md)
    except FeishuAPIError as e:
        print(f"❌ 飞书文档生成失败: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"❌ 飞书文档生成异常: {e}")
        return 1
    if res.get("dry_run"):
        print(f"🧪 飞书文档 dry-run：{title}（{res.get('content_chars')} 字，未触网）")
    else:
        print(f"✅ 飞书云文档已生成: {res['url']}（blocks={res.get('blocks')}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
