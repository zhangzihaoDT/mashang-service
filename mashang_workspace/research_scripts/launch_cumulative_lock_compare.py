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

模块 4：锁单用户画像对比（各代际上市同期窗口内零售锁单的性别 / 年龄代际 / 城市线级 /
  省份结构；口径字段参考 l6_m2_presale_report 用户画像模块与 business_scripts/user_profile.py）。

模块 5：车主年龄分层 & 复购对比（owner_age 分年龄段 vs 历届；复购复用 shared/operators/
  repurchase.py 算子 mode=fulfilled_repurchase（canonical）：owner_identity_no 在窗口前已完成
  兑现购车（交付或开票早于上市日）→ 复购，排除"历史已锁未兑现"悬置误判；
   宽松对照 mode=prior_locker 对齐 lock_attribution_analysis "Repeat Lockers (Had Prior Locks)"）。

模块 6：上市后下发线索窗口增幅对比（最新两代际 DM1/DM2，assign_data「下发线索数」整体口径，
  上市后 N 天窗口 vs 上市前等长基线，N=1/3/7；含上市后 D1..D7 每日相对前 7 日均值节奏）。

模块 7：最新代际上市以来锁单配置分布（复用 research_scripts/lock_config_distribution.py，
  gen = 报告最新代际 series_group_logic；数据源 = config_attribute.parquet 增量更新后；
  核心 5 属性 + 是/否型选装项拥有率）。

口径：
  - 锁单 = lock_time 非空 COUNTD(order_number)
  - 零售 = order_type ∈ {用户车, NaN}（DM2 新车型 order_type 未填充，保留 NaN；其余代际排除非零售单）
  - 剔除测试单 = flag_test_orders（总部主理店 + 假身份号，与 utils/monitors/launch.py 上市监控同口径）
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
import plotly.graph_objects as go
from plotly.subplots import make_subplots

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = REPO_ROOT / "mashang_workspace"
for p in (str(REPO_ROOT), str(_WS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from utils.monitors.launch import _norm_product_name  # noqa: E402
from utils.monitors.order_filter import flag_test_orders  # noqa: E402
from utils.monitors.phase import load_business_definition  # noqa: E402
from utils.monitors.series_group import apply_series_group_logic  # noqa: E402
from research_scripts.lock_config_distribution import (  # noqa: E402
    compute_lock_config_distribution,
    is_core_attribute,
)
from research_scripts.store_network_compare import compute_store_network  # noqa: E402
from business_scripts.user_profile import (  # noqa: E402
    CITY_TO_PROVINCE,
    age_cohort_distribution,
    city_to_tier_label,
    norm_city,
)
from business_scripts.presale_intention_funnel import (  # noqa: E402
    compute_funnel as compute_presale_funnel,
)
from utils.paths import ensure_shared_on_path  # noqa: E402
from utils.plotly_theme import apply_zh_theme, get_series_color  # noqa: E402
from utils.regions import REGION_MAP_OLD_TO_NEW, norm_region  # noqa: E402

ensure_shared_on_path()  # 让 operators.*（shared/operators）优先于其他 operators 可导入
from operators.repurchase import split_repurchase  # noqa: E402

_BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
_ORDER_DATA = REPO_ROOT / "dataset" / "order_data.parquet"
_ASSIGN_DATA = REPO_ROOT / "dataset" / "assign_data.csv"
_TEST_DRIVE_DATA = REPO_ROOT / "dataset" / "test_drive_data.csv"
_DEFAULT_REPORT = _WS / "outputs" / "reports"
_DEFAULT_TABLE = _WS / "outputs" / "tables"

DEFAULT_GENS = ["DM0", "DM1", "DM2"]
CHART_WINDOW_DAYS = 30  # 模块 1 折线固定窗口：上市后天数 1..30；未满 30 天的代际只画到已有天数
# 模块 8 试驾数据（test_drive_data.csv）按车系拆分，有效试驾数列
_TESTDRIVE_SERIES_COL = {"L6": "L6有效试驾数", "LS6": "LS6有效试驾数", "LS9": "LS9有效试驾数"}
_TEST_DRIVE_PRE_DAYS = 14  # 模块 8 上市前观察天数（含预售爬坡）
NON_RETAIL = {"试驾车", "大客户", "员工", "集团员工", "经销商员工", "享道", "仅批售", "项目", "展车", "海外"}
# 预售小订 → 上市 N 日锁单分解（对齐 business_scripts/presale_intention_funnel.py 通用漏斗）
_BREAKDOWN_COLORS = {
    "留存小订": "#174A7C",       # 本品蓝
    "预售退订": "#D95F59",       # 负向
    "预售转化锁单": "#D79A36",   # 重点金
    "直接锁单": "#9AA3AD",       # 中性灰
}


def _retail_mask(order_type: pd.Series) -> pd.Series:
    ot = order_type.fillna("").astype("string")
    return ot.isin(["", "用户车"]) & ~ot.isin(NON_RETAIL)


def _fmt_int(v) -> str:
    if pd.isna(v):
        return "—"
    return f"{int(round(float(v))):,}"


def load_data() -> pd.DataFrame:
    bd = load_business_definition(_BUSINESS_DEF)
    df = pd.read_parquet(_ORDER_DATA)
    for c in ["lock_time", "intention_payment_time", "delivery_date"]:
        if c in df.columns and not pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = pd.to_datetime(df[c], errors="coerce")
    df = apply_series_group_logic(df, bd)
    return df


def resolve_end_day(bd: dict, gen: str) -> pd.Timestamp:
    tp = (bd.get("time_periods", {}) or {}).get(gen, {}) or {}
    return pd.Timestamp(tp["end"]).normalize()


def _chart_curves(retail: pd.DataFrame, ends: dict, last_date: pd.Timestamp,
                  window_days: int) -> dict:
    """模块 1 折线窗口：固定 window_days 天 X 轴，各代际只绘制其上市至今已发生的天数。

    第 t 天 = 各代际自身上市日 + (t-1)；某代际上市不足 window_days 天时不补齐、不画完整，
    曲线在第 available_days 天处截至（last_date = as-of 前一日，即最后完整观察日）。
    """
    out: dict[str, dict] = {}
    for g, end in ends.items():
        avail = int((last_date - end).days) + 1
        avail = max(0, min(avail, window_days))
        if avail <= 0:
            out[g] = {"end": end.date().isoformat(), "available_days": 0,
                      "day_offset": [], "dates": [], "daily": [], "cum": []}
            continue
        window_end = end + pd.Timedelta(days=avail)
        sub = retail[retail["series_group_logic"].eq(g) &
                     retail["lock_time"].notna() &
                     (retail["lock_time"] >= end) &
                     (retail["lock_time"] < window_end)].copy()
        sub["d"] = sub["lock_time"].dt.normalize()
        daily = sub.groupby("d")["order_number"].nunique()
        full = pd.date_range(end, periods=avail)
        daily = daily.reindex(full, fill_value=0)
        cum = daily.cumsum().astype(int)
        out[g] = {
            "end": end.date().isoformat(),
            "available_days": avail,
            "day_offset": list(range(1, avail + 1)),
            "dates": [d.date().isoformat() for d in full],
            "daily": [int(v) for v in daily],
            "cum": [int(v) for v in cum],
        }
    return out


def _retail_bridge(df: pd.DataFrame, bd: dict, gens: list[str],
                   ends: dict, n_days: int) -> dict:
    """口径桥接：最新代际在模块 1 同窗口内，零售口径 vs 上市监控卡片口径。

    本报告模块 1 采用零售口径（order_type ∈ 用户车/NaN，排除试驾车/员工/大客户等非零售单）；
    上市监控卡片仅剔除测试单、不区分 order_type。本函数给出同一时间窗下两者差额与已排除类型，
    便于报告读者与卡片数字对齐（避免误判为口径冲突）。
    """
    g = gens[-1]
    end = ends[g]
    hi = end + pd.Timedelta(days=n_days)  # 右开区间 = 第 n_days 天末
    seg = df[
        df["series_group_logic"].eq(g)
        & df["lock_time"].notna()
        & (df["lock_time"] >= end)
        & (df["lock_time"] < hi)
        & ~flag_test_orders(df, bd)
    ]
    is_retail = _retail_mask(seg["order_type"])
    excluded = seg.loc[~is_retail]
    counts = excluded["order_type"].fillna("(未标注)").value_counts()
    return {
        "gen": g,
        "start": end.date().isoformat(),
        "last_date": (hi - pd.Timedelta(days=1)).date().isoformat(),
        "retail": int(seg.loc[is_retail, "order_number"].nunique()),
        "all_types": int(seg["order_number"].nunique()),
        "excluded": int(excluded["order_number"].nunique()),
        "excluded_types": {str(k): int(v) for k, v in counts.items()},
    }


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

    # 锁单口径与上市监控一致：剔除测试单（总部主理店 + 假身份号，flag_test_orders）
    # 并在其基础上保留零售口径（order_type ∈ 用户车/NaN，排除试驾车/员工/大客户等非零售单）。
    retail = df[_retail_mask(df["order_type"]) & ~flag_test_orders(df, bd)].copy()
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
        "chart_window": CHART_WINDOW_DAYS,
        "as_of": as_of.date().isoformat(),
        "last_date": last_date.date().isoformat(),
        "max_end": max_end.date().isoformat(),
        "curves": curves,
        "chart": _chart_curves(retail, ends, last_date, CHART_WINDOW_DAYS),
        "presale": _presale_conversion(df, bd, gens, ends, n_days),
        "daily_product": _daily_product_breakdown(retail, bd, gens, ends, n_days),
        "region": _region_compare(retail, gens, ends, n_days),
        "network": compute_store_network(retail, gens, ends, n_days),
        "user_profile": _user_profile_compare(retail, gens, ends, n_days),
        "age_repurchase": _age_repurchase_compare(retail, gens, ends, n_days),
        "lead_window": _lead_window_compare(ends, last_date),
        "lock_config": _lock_config_distribution(as_of.normalize(), gens[-1]),
        "test_drive": _test_drive_compare(bd, gens, ends, last_date),
        "retail_bridge": _retail_bridge(df, bd, gens, ends, n_days),
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


def _lock_user_profile(df: pd.DataFrame, gen: str, end: pd.Timestamp, n_days: int,
                       lock_year: int) -> dict:
    """某代际上市同期窗口内零售锁单的用户画像（订单级去重）。

    口径字段参考 l6_m2_presale_report 用户画像模块与 business_scripts/user_profile.py：
      - 样本 = 窗口内零售锁单 COUNTD(order_number)
      - 性别 = order_gender（含 owner_gender 对照，缺失少）
      - 年龄 = buyer_age 中位/均值 + owner_age 对照；缺失率单列
      - 城市线级 / 省份 = license_city 归一 → tier / CITY_TO_PROVINCE
      - 年龄代际 = owner_age → birth year = lock_year - owner_age → COHORTS
    """
    lo, hi = end, end + pd.Timedelta(days=n_days)
    sub = df[df["series_group_logic"].eq(gen) &
              df["lock_time"].notna() &
              (df["lock_time"] >= lo) & (df["lock_time"] < hi)].copy()
    sub = sub.drop_duplicates(subset=["order_number"])
    n = len(sub)
    if n == 0:
        return {"gen": gen, "n": 0}
    og = sub["order_gender"].fillna("默认未知").astype(str).value_counts().to_dict()
    owg = sub["owner_gender"].fillna("默认未知").astype(str).value_counts().to_dict()
    ba = pd.to_numeric(sub["buyer_age"], errors="coerce")
    oa = pd.to_numeric(sub["owner_age"], errors="coerce")
    cohorts, age_known = age_cohort_distribution(oa, lock_year=lock_year)
    city = sub["license_city"].apply(norm_city)
    tier = city.apply(city_to_tier_label).value_counts().to_dict()
    prov = city.map(CITY_TO_PROVINCE).fillna("未知").value_counts()
    return {
        "gen": gen,
        "n": n,
        "gender": og,
        "owner_gender": owg,
        "age_buyer": {
            "median": float(ba.median()) if ba.notna().any() else None,
            "mean": round(float(ba.mean()), 1) if ba.notna().any() else None,
            "missing_pct": round(float(ba.isna().mean() * 100), 1),
        },
        "age_owner": {
            "median": float(oa.median()) if oa.notna().any() else None,
            "mean": round(float(oa.mean()), 1) if oa.notna().any() else None,
            "missing_pct": round(float(oa.isna().mean() * 100), 1),
        },
        "cohorts": cohorts,
        "cohorts_known": age_known,
        "tier": tier,
        "province": [{"province": p, "count": int(v)} for p, v in prov.items()],
    }


def _user_profile_compare(df: pd.DataFrame, gens: list[str], ends: dict,
                          n_days: int) -> dict | None:
    """各代际上市同期窗口零售锁单用户画像（含对比结论要点）。"""
    if len(gens) < 2:
        return None
    profiles = {g: _lock_user_profile(df, g, ends[g], n_days, ends[g].year) for g in gens}
    latest = gens[-1]
    target = profiles[latest]
    if target["n"] == 0:
        return {"gens": gens, "n_days": n_days, "profiles": profiles, "insights": []}
    others = [profiles[g] for g in gens[:-1] if profiles[g]["n"]]

    def _share(p: dict, dim: str, key: str) -> float:
        return (p[dim].get(key, 0) / p["n"]) if p["n"] else 0.0

    # 判断要点
    insights = []
    female_target = _share(target, "owner_gender", "女")
    if others:
        female_others = [_share(p, "owner_gender", "女") for p in others]
        direction = "高于" if female_target >= max(female_others) else \
            ("介于" if min(female_others) < female_target < max(female_others) else "低于")
        insights.append(f"{latest} 女性占比（owner_gender）{female_target * 100:.0f}%，{direction}其余代际"
                        f"（{min(female_others) * 100:.0f}%~{max(female_others) * 100:.0f}%）。")
    mean_target = target["age_owner"].get("mean")
    if mean_target is not None and others:
        means = [p["age_owner"].get("mean") for p in others]
        means = [m for m in means if m is not None]
        if means:
            direction = "更年轻" if mean_target <= min(means) else ("更年长" if mean_target >= max(means) else "与历届相近")
            insights.append(f"{latest} 车主年龄均值（owner_age）{mean_target:.1f} 岁，{direction}"
                            f"（其余代际 {min(means):.1f}~{max(means):.1f} 岁）。")
    new1_t1 = _share(target, "tier", "新一线") + _share(target, "tier", "一线")
    top_prov = target["province"][:3]
    insights.append(
        f"{latest} 城市新一线+一线合计占比 {new1_t1 * 100:.0f}%；省份集中于 "
        + " / ".join(f"{p['province']} {p['count'] / target['n'] * 100:.0f}%" for p in top_prov)
        + f"。画像样本 = {latest} 上市同期 {n_days} 天零售锁单（{target['n']} 单，去重订单）。")
    return {"gens": gens, "n_days": n_days, "profiles": profiles, "insights": insights}


# 年龄分桶（owner_age，车主年龄）：左闭右开。
AGE_BAND_EDGES = [18, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75]
AGE_BAND_LABELS = (
    "18-25岁", "25-30岁", "30-35岁", "35-40岁", "40-45岁", "45-50岁",
    "50-55岁", "55-60岁", "60-65岁", "65-70岁", "70-75岁", "75岁以上",
)


def _age_band_rows(age: pd.Series, n: int) -> list[dict]:
    """把车主年龄序列按 AGE_BAND_LABELS 分桶，返回 [{band, count, share_known, share}]。"""
    valid = age.notna()
    counts = pd.cut(age[valid], bins=AGE_BAND_EDGES + [float("inf")],
                    labels=AGE_BAND_LABELS, right=False).value_counts()
    n_known = int(valid.sum())
    rows = []
    for label in AGE_BAND_LABELS:
        c = int(counts.get(label, 0))
        rows.append({
            "band": label, "count": c,
            "share_known": (c / n_known) if n_known else 0.0,
            "share": (c / n) if n else 0.0,
        })
    return rows


def _repurchase_split(df: pd.DataFrame, gen: str, end: pd.Timestamp, n_days: int) -> dict:
    """某代际上市同期窗口内零售锁单的复购 / 首购拆分。

    委托 shared/operators/repurchase.py 算子（mode=fulfilled_repurchase，canonical）：
    - 窗口内锁单订单按 owner_identity_no（18 位有效）判其窗口前购车史
    - prior_fulfilled（历史已兑现购车，交付/开票早于窗口开始）→ 复购 repeat
    - prior_unfulfilled（已锁未兑现/悬置历史）→ suspended，不计复购（避免误判）
    - no_prior_history → first；身份缺失/无效 → unknown
    PIT：兑现事件须早于窗口开始，不穿越。对齐 lock_attribution_analysis.py 宽松语义的收紧版。
    """
    lo = end
    hi = end + pd.Timedelta(days=n_days)
    r = split_repurchase(
        df, lo, hi, mode="fulfilled_repurchase", series=gen,
    )
    if "error" in r:
        return {"n": r.get("n", 0), "repeat": 0, "suspended": 0, "first": 0,
                "unknown": 0, "known_pct": 0.0}
    s = r["summary"]
    return {"n": s["n"], "repeat": s["repeat"], "suspended": s["suspended"],
            "first": s["first"], "unknown": s["unknown"], "known_pct": s["known_pct"]}


def _age_repurchase_compare(df: pd.DataFrame, gens: list[str], ends: dict,
                            n_days: int) -> dict | None:
    """年龄分层（owner_age 分桶）+ 复购拆分（owner_identity_no 历史锁单）对比：最新两代际。"""
    if len(gens) < 2:
        return None
    gen_a, gen_b = gens[-2], gens[-1]
    out = {"gens": [gen_a, gen_b], "n_days": n_days, "rows": [], "repurchase": {}, "insights": []}
    per_gen: dict[str, dict] = {}
    for g in (gen_a, gen_b):
        end = ends[g]
        lo, hi = end, end + pd.Timedelta(days=n_days)
        sub = df[df["series_group_logic"].eq(g) &
                  df["lock_time"].notna() &
                  (df["lock_time"] >= lo) & (df["lock_time"] < hi)].copy()
        sub = sub.drop_duplicates(subset=["order_number"])
        n = len(sub)
        age = pd.to_numeric(sub["owner_age"], errors="coerce")
        per_gen[g] = {"n": n, "rows": _age_band_rows(age, n),
                      "age_missing_pct": round(float(age.isna().mean() * 100), 1) if n else 0.0,
                      "repurchase": _repurchase_split(df, g, end, n_days)}
    rows = []
    for i, label in enumerate(AGE_BAND_LABELS):
        ra = next(r for r in per_gen[gen_a]["rows"] if r["band"] == label)
        rb = next(r for r in per_gen[gen_b]["rows"] if r["band"] == label)
        rows.append({
            "band": label,
            "a": ra["count"], "a_share_known": ra["share_known"],
            "b": rb["count"], "b_share_known": rb["share_known"],
            "diff_pp": round((rb["share_known"] - ra["share_known"]) * 100, 1),
        })
    out["rows"] = rows
    out["repurchase"] = {"a": per_gen[gen_a]["repurchase"], "b": per_gen[gen_b]["repurchase"]}
    out["n_a"] = per_gen[gen_a]["n"]
    out["n_b"] = per_gen[gen_b]["n"]

    # 判断要点
    rep_a, rep_b = per_gen[gen_a]["repurchase"], per_gen[gen_b]["repurchase"]
    if rep_a["known_pct"] and rep_b["known_pct"]:
        def _repeat_share(rp: dict) -> float:
            known = rp["repeat"] + rp["first"] + rp["suspended"]
            return (rp["repeat"] / known) if known else 0.0

        ra_share, rb_share = _repeat_share(rep_a), _repeat_share(rep_b)
        out["insights"].append(
            f"{gen_b} 窗口锁单中老车主复购（owner_identity_no 在窗口前已完成交付/开票）占比 "
            f"{rb_share * 100:.0f}%（{rep_b['repeat']}/{rep_b['repeat'] + rep_b['first'] + rep_b['suspended']} 单，可判定 {rep_b['known_pct']:.0f}%），"
            f"{gen_a} 为 {ra_share * 100:.0f}%（{rep_a['repeat']}/{rep_a['repeat'] + rep_a['first'] + rep_a['suspended']} 单）。")
        if rep_a["suspended"] or rep_b["suspended"]:
            out["insights"].append(
                f"注：另检出「历史已锁但未兑现（无交付/开票）」的悬置单 {gen_a} {rep_a['suspended']} 单 / "
                f"{gen_b} {rep_b['suspended']} 单，未计入复购（避免误判）。")
    # 主力年龄带迁移
    def _peak(g: str):
        r = max(per_gen[g]["rows"], key=lambda x: x["count"])
        return r["band"]
    out["insights"].append(
        f"年龄段分布按 owner_age 分桶；{gen_a} 主力带 {_peak(gen_a)}，{gen_b} 主力带 {_peak(gen_b)}。")
    return out


_CHANNEL_COLS = [
    "下发线索数 (门店)",
    "下发线索数（APP小程序)",
    "下发线索数（平台)",
    "下发线索数（直播）",
    "下发线索数（快慢闪)",
]
_CHANNEL_LABELS = {
    "下发线索数 (门店)": "门店",
    "下发线索数（APP小程序)": "APP小程序",
    "下发线索数（平台)": "平台",
    "下发线索数（直播）": "直播",
    "下发线索数（快慢闪)": "快慢闪",
}


def _load_assign_daily() -> pd.DataFrame:
    """assign_data 日频：返回 d / 下发线索数 / 下发门店数 / 各渠道线索（整体口径）。"""
    df = pd.read_csv(_ASSIGN_DATA, encoding="utf-8-sig")
    dt = pd.to_datetime(df["Assign Time 年/月/日"], format="%Y年%m月%d日", errors="coerce")
    cols = ["d", "下发线索数", "下发门店数"] + [c for c in _CHANNEL_COLS if c in df.columns]
    out = df.assign(d=dt)[cols].dropna(subset=["d"])
    return out.sort_values("d")


def _lock_config_distribution(as_of: pd.Timestamp | None = None,
                              gen: str | None = None) -> dict | None:
    """模块 7：最新代际上市以来锁单配置分布（gen = 报告最新代际 series_group_logic）。

    复用 research_scripts/lock_config_distribution.py 的
    compute_lock_config_distribution(gen=...)（独立脚本，--format json 输出 Result Contract）。
    窗口与报告对齐：该代际上市日 end 起至 as_of（数据最新完整日）。
    """
    try:
        if gen is None:
            return compute_lock_config_distribution(as_of=as_of)
        return compute_lock_config_distribution(as_of=as_of, gen=gen)
    except Exception:
        return None


def _lead_window_compare(ends: dict, complete_day: pd.Timestamp | None = None) -> dict | None:
    """模块 6：最新两代际上市后下发线索窗口增幅对比。

    口径：assign_data「下发线索数」整体口径。
      - 上市后窗口 = 上市日 end 起 N 天（[end, end+N)），N = 1/3/5/7
      - 基线 = 上市前 7 天（[end-7, end)）日均，N 日基线 = 日均 × N
      - 每日节奏：上市后 D1..D7 当日线索，及相对上市前 7 日均值的倍数
      - 完整性：仅当 N 天全部落在完整观察日（complete_day，默认数据最新日）内才给结论；
        未完成窗口（如 CM3 上市仅 5 天时的 N=7）标记 pending，缺失日不补 0。
    """
    if len(ends) < 2:
        return None
    keys = list(ends)
    gen_a, gen_b = keys[-2], keys[-1]
    df = _load_assign_daily()
    if df.empty:
        return None
    ddf = df.set_index("d")
    s = ddf["下发线索数"]
    complete_day = pd.Timestamp(complete_day).normalize() if complete_day is not None \
        else pd.Timestamp(s.index.max()).normalize()
    target_days = 7

    def _sum(lo: pd.Timestamp, n: int) -> float:
        return float(s.loc[lo:lo + pd.Timedelta(days=n) - pd.Timedelta(microseconds=1)].sum())

    def _daily(lo: pd.Timestamp, observed: int) -> dict:
        out = {}
        for t in range(1, target_days + 1):
            d = lo + pd.Timedelta(days=t - 1)
            out[str(t)] = float(s.get(d, 0.0)) if (t <= observed and d <= complete_day) else None
        return out

    per = {}
    channels_out = {}
    for g, key in ((gen_a, "a"), (gen_b, "b")):
        end = pd.Timestamp(ends[g]).normalize()
        observed = int((complete_day - end).days) + 1 if complete_day >= end else 0
        base7 = _sum(end - pd.Timedelta(days=7), 7)
        base_daily_avg = base7 / 7
        daily = _daily(end, observed)
        windows = {}
        for n in (1, 3, 5, 7):
            if n <= observed:
                wsum = _sum(end, n)
                bsum = base7 * n / 7
                windows[n] = {
                    "win": int(round(wsum)),
                    "base": int(round(bsum)),
                    "delta": int(round(wsum - bsum)),
                    "delta_pct": round((wsum - bsum) / bsum, 4) if bsum else None,
                }
            else:
                windows[n] = {"pending": True, "required_days": n, "observed_days": observed}
        per[key] = {
            "gen": g, "end": end.date().isoformat(),
            "base7_total": int(round(base7)),
            "base7_daily_avg": int(round(base_daily_avg)),
            "observed_days": observed,
            "daily": daily,
            "windows": windows,
        }
        # 各渠道窗口增幅（上市前 7 天为基线）
        ch_rows = []
        for c in _CHANNEL_COLS:
            if c not in df.columns:
                continue
            cc = ddf[c]
            base7c = float(cc.loc[end - pd.Timedelta(days=7):end - pd.Timedelta(microseconds=1)].sum())
            row = {"channel": _CHANNEL_LABELS[c], "windows": {}}
            for n in (1, 3, 5, 7):
                if n <= observed:
                    win = float(cc.loc[end:end + pd.Timedelta(days=n) - pd.Timedelta(microseconds=1)].sum())
                    bsum = base7c * n / 7
                    row["windows"][n] = {
                        "win": int(round(win)),
                        "base": int(round(bsum)),
                        "delta": int(round(win - bsum)),
                        "delta_pct": round((win - bsum) / bsum, 4) if bsum else None,
                    }
                else:
                    row["windows"][n] = {"pending": True}
            ch_rows.append(row)
        channels_out[key] = ch_rows

    # 判断要点（整体）
    insights = []
    for n in (1, 3, 5, 7):
        wa, wb = per["a"]["windows"][n], per["b"]["windows"][n]
        if "pending" in wa or "pending" in wb:
            pend_key = "b" if "pending" in wb else "a"
            gname = per[pend_key]["gen"]
            insights.append(
                f"上市后 {n} 天窗口：{gname} 数据未足 {n} 个完整日"
                f"（已观察 {per[pend_key]['observed_days']} 天），暂不给结论，待补数据。")
            continue
        a_s, b_s = wa["delta_pct"], wb["delta_pct"]
        if a_s is not None and b_s is not None:
            insights.append(
                f"上市后 {n} 天窗口增幅：{gen_a} {a_s:+.1%} / {gen_b} {b_s:+.1%}（"
                f"窗口累计 {wa['win']:,} vs 基线 {wa['base']:,}；"
                f"{wb['win']:,} vs {wb['base']:,}）。")
    # 渠道要点（最新代际 = b，取已完成的窗口）
    if channels_out["b"]:
        for n in (1, 3, 5, 7):
            cands = [r for r in channels_out["b"]
                     if "pending" not in r["windows"][n] and r["windows"][n]["delta_pct"] is not None]
            if not cands:
                continue
            r = max(cands, key=lambda x: x["windows"][n]["delta_pct"])
            w = r["windows"][n]
            insights.append(
                f"{gen_b} 上市后 {n} 天窗口渠道增幅最高 = {r['channel']}"
                f"（{w['delta_pct']:+.1%}，窗口 {w['win']:,} vs 基线 {w['base']:,}）。")
    return {"gens": [gen_a, gen_b], "per": per, "channels": channels_out,
            "insights": insights, "metric": "下发线索数", "baseline": "上市前 7 日均值",
            "target_days": target_days, "complete_day": complete_day.date().isoformat(),
            "window_days": [1, 3, 5, 7]}


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


def _diff_barcell(diff_pp: float | None, max_abs: float) -> str:
    """占比差（pp）行内数据条：宽度 ∝ |差| / 最大 |差|，正向绿、负向红。

    样式复用 templates/report_style.css 的 .barcell（与模块 7 一致），
    直接在表格「占比差」单元格内可视化。
    """
    if diff_pp is None:
        return "<div class='barcell'><div class='txt'>—</div></div>"
    ratio = min(abs(diff_pp) / max_abs, 1.0) if max_abs else 0.0
    cls = "positive" if diff_pp > 0 else ("negative" if diff_pp < 0 else "")
    bar = f"<div class='bar {cls}' style='width:{ratio * 100:.1f}%;'></div>" if cls else ""
    txt = "0.0" if diff_pp == 0 else f"{diff_pp:+.1f}"
    return f"<div class='barcell'>{bar}<div class='txt'>{txt} pp</div></div>"


def _region_table(c: dict) -> str:
    rc = c.get("region")
    if not rc:
        return ""
    max_abs = max((abs(r["diff_pp"]) for r in rc["regions"]), default=0.0) or 1.0
    rows_html = []
    for r in rc["regions"]:
        rows_html.append(
            f"<tr><td>{r['region']}</td>"
            f"<td class='num'><strong>{r['b']:,}</strong></td><td class='num'>{r['b_share'] * 100:.1f}%</td>"
            f"<td class='num'>{r['a']:,}</td><td class='num'>{r['a_share'] * 100:.1f}%</td>"
            f"<td style='min-width:180px;'>{_diff_barcell(r['diff_pp'], max_abs)}</td></tr>"
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
      <p class="section-note">上市同期 = 各代际自上市日起第 1..{rc['n_days']} 天（与折线同窗口，N = {c['n_days']}）；大区 = parent_region_name，旧架构（一区/二区/三区）已归一到新架构（东区/西区/北区/华中），详见口径说明。占比差 = {b} 占比 − {a} 占比（pp）；数据条宽度 ∝ |占比差|，绿 = {b} 更高、红 = {a} 更高。</p>
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


def _user_profile_table(c: dict) -> str:
    pc = c.get("user_profile")
    if not pc or pc.get("profiles") is None:
        return ""
    gens = [g for g in pc["gens"] if pc["profiles"][g]["n"] > 0]
    latest = gens[-1]
    thead_cells = "".join(f"<th>{g}</th>" for g in gens)
    body = []

    def _row(label: str, cells: list[str]) -> None:
        body.append(f"<tr><td>{label}</td>"
                    + "".join(f"<td class='num'>{v}</td>" for v in cells) + "</tr>")

    def _cell(fn, g: str, latest: bool = False) -> str:
        v = fn(pc["profiles"][g])
        s = "—" if v is None else (f"{v * 100:.0f}%" if isinstance(v, float) else str(v))
        return f"<strong>{s}</strong>" if latest and s != "—" else s

    _row("锁单样本（去重订单）", [
        _cell(lambda p: int(p["n"]), g, g == latest) for g in gens])
    _row("女性占比（owner_gender）", [
        _cell(lambda p: (p["owner_gender"].get("女", 0) / p["n"]) if p["n"] else None, g, g == latest)
        for g in gens])
    _row("车主年龄均值（owner_age）", [
        _cell(lambda p: None if p["age_owner"].get("mean") is None
              else f"{p['age_owner']['mean']:.1f}", g, g == latest)
        for g in gens])
    _row("00后 / 95后 占已知年龄", [
        _cell(lambda p: None if not p["cohorts_known"]
              else (sum(r["count"] for r in p["cohorts"]
                        if r["cohort"] in ("00后", "95后")) / p["cohorts_known"]),
              g, g == latest) for g in gens])
    _row("新一线城市占比", [
        _cell(lambda p: (p["tier"].get("新一线", 0) / p["n"]) if p["n"] else None, g, g == latest)
        for g in gens])
    _row("一线城市占比", [
        _cell(lambda p: (p["tier"].get("一线", 0) / p["n"]) if p["n"] else None, g, g == latest)
        for g in gens])
    _row("三线及以下占比", [
        _cell(lambda p: (p["tier"].get("三线及以下", 0) / p["n"]) if p["n"] else None, g, g == latest)
        for g in gens])

    insights_html = ""
    if pc.get("insights"):
        insights_html = '<div class="section-note" style="margin-top:14px;"><strong>判断</strong><ul style="margin:6px 0 0 18px;padding:0;">' + "".join(
            f"<li>{s}</li>" for s in pc["insights"]) + "</ul></div>"

    return f"""
    <div class="card">
      <h2>模块 4 · 锁单用户画像对比（{ ' / '.join(gens) }，上市同期 {pc['n_days']} 天窗口）</h2>
      <p class="section-note">口径：各代际上市同期第 1..{pc['n_days']} 天窗口内零售锁单（order_type ∈ 用户车/NaN，排除非零售），按 order_number 去重；性别仅取 owner_gender 口径（女性占比 = owner_gender 女 ÷ 锁单样本），年龄仅取 owner_age 口径（仅列均值，不含中位数），城市线级与省份 = license_city 归一（norm_city → city_to_tier_label / CITY_TO_PROVINCE）；年龄代际 = owner_age → birth = 上市年 − age → COHORTS（00后/95后…）。字段口径与 business_scripts/user_profile.py、l6_m2_presale_report 用户画像模块一致。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>指标</th>{thead_cells}</tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
      </div>
      {insights_html}
    </div>"""


def _age_repurchase_table(c: dict) -> str:
    ar = c.get("age_repurchase")
    if not ar or not ar.get("rows"):
        return ""
    a, b = ar["gens"][0], ar["gens"][1]
    max_abs = max((abs(r["diff_pp"]) for r in ar["rows"]), default=0.0) or 1.0
    rows_html = []
    for r in ar["rows"]:
        rows_html.append(
            f"<tr><td>{r['band']}</td>"
            f"<td class='num'>{r['a']}</td><td class='num'>{r['a_share_known'] * 100:.0f}%</td>"
            f"<td class='num'><strong>{r['b']}</strong></td><td class='num'><strong>{r['b_share_known'] * 100:.0f}%</strong></td>"
            f"<td style='min-width:180px;'>{_diff_barcell(r['diff_pp'], max_abs)}</td></tr>"
        )

    # 复购表
    rep_a, rep_b = ar["repurchase"]["a"], ar["repurchase"]["b"]

    def _rep_cells(rp: dict) -> dict:
        known = rp["repeat"] + rp["first"] + rp["suspended"]
        share = (rp["repeat"] / known) if known else 0.0
        susp_share = (rp["suspended"] / known) if known else 0.0
        return {"repeat": rp["repeat"], "first": rp["first"],
                "suspended": rp["suspended"], "unknown": rp["unknown"],
                "share": share, "susp_share": susp_share}

    ca, cb = _rep_cells(rep_a), _rep_cells(rep_b)

    def _pct(x):
        return f"{x * 100:.0f}%"

    rep_rows = [
        f"<tr><td>老车主复购（历史已兑现购车）</td><td class='num'>{ca['repeat']}</td><td class='num'>{_pct(ca['share'])}</td>"
        f"<td class='num'><strong>{cb['repeat']}</strong></td><td class='num'><strong>{_pct(cb['share'])}</strong></td></tr>",
        f"<tr><td>悬置历史（已锁未交付/开票）</td><td class='num'>{ca['suspended']}</td><td class='num'>{_pct(ca['susp_share'])}</td>"
        f"<td class='num'>{cb['suspended']}</td><td class='num'>{_pct(cb['susp_share'])}</td></tr>",
        f"<tr><td>首次购车（无历史锁单）</td><td class='num'>{ca['first']}</td><td class='num'>—</td>"
        f"<td class='num'>{cb['first']}</td><td class='num'>—</td></tr>",
        f"<tr><td>身份无法判定</td><td class='num'>{ca['unknown']}</td><td class='num'>—</td>"
        f"<td class='num'>{cb['unknown']}</td><td class='num'>—</td></tr>",
    ]

    insights_html = ""
    if ar.get("insights"):
        insights_html = '<div class="section-note" style="margin-top:14px;"><strong>判断</strong><ul style="margin:6px 0 0 18px;padding:0;">' + "".join(
            f"<li>{s}</li>" for s in ar["insights"]) + "</ul></div>"

    return f"""
    <div class="card">
      <h2>模块 5 · 车主年龄分层 &amp; 复购对比：{b} vs {a}（上市同期 {ar['n_days']} 天窗口）</h2>
      <p class="section-note">年龄分层按 owner_age（车主年龄，各代际窗口缺失约 5–9%）分桶，占比为各带占「已知年龄」比例；占比差 = {b} 占已知 − {a} 占已知（pp）；数据条宽度 ∝ |占比差|，绿 = {b} 更高、红 = {a} 更高。复购（老车主）复用 shared/operators/repurchase.py 算子（mode=fulfilled_repurchase，canonical）：窗口内锁单的 owner_identity_no（18 位有效，缺失/无效记无法判定）须在窗口开始前已完成过**兑现购车**——历史零售锁单的交付或开票时间早于上市日；仅历史锁单、从未交付/开票的「悬置单」不计复购，另列悬置历史，避免误判（PIT 不穿越；宽松对照 mode=prior_locker 对齐 lock_attribution_analysis.py "Repeat Lockers (Had Prior Locks)"）。复购占比按可判定业务单（复购+悬置+首购）计。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>年龄段</th><th>{a} 单数</th><th>{a} 占已知</th><th>{b} 单数</th><th>{b} 占已知</th><th>占比差（{b}−{a}）</th></tr></thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
      </div>
      <h3 style="margin-top:20px;">复购 / 首购拆分（owner_identity_no）</h3>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>类别</th><th>{a} 单数</th><th>{a} 占比</th><th>{b} 单数</th><th>{b} 占比</th></tr></thead>
        <tbody>{''.join(rep_rows)}</tbody>
      </table>
      </div>
      {insights_html}
    </div>"""


def _lead_daily_figure(lc: dict) -> str:
    """每日下发线索：上=绝对值（分组柱 + 前 7 日均值虚线），下=相对前 7 日均值倍数（基准 1.0）。

    未完成日（如 CM3 上市仅 5 天时的 D6/D7）留空不补 0，并标注「待补」。
    """
    a, b = lc["per"]["a"], lc["per"]["b"]
    ga, gb = a["gen"], b["gen"]
    td = lc.get("target_days", 7)
    xs = [f"D{t}" for t in range(1, td + 1)]
    ya = [a["daily"].get(str(t)) for t in range(1, td + 1)]
    yb = [b["daily"].get(str(t)) for t in range(1, td + 1)]
    avg_a, avg_b = a["base7_daily_avg"], b["base7_daily_avg"]
    ia = [(v / avg_a if (v is not None and avg_a) else None) for v in ya]
    ib = [(v / avg_b if (v is not None and avg_b) else None) for v in yb]
    ca, cb = get_series_color("sage"), get_series_color("own")

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.18, row_heights=[0.56, 0.44],
        subplot_titles=["每日下发线索（绝对值 · 虚线 = 上市前 7 日均值）",
                        "相对上市前 7 日均值（基准 = 1.0）"],
    )
    fig.add_trace(go.Bar(x=xs, y=ya, name=ga, marker_color=ca,
                         text=[f"{int(v):,}" if v is not None else "" for v in ya],
                         textposition="outside", cliponaxis=False,
                         hovertemplate=f"<b>{ga}</b> · %{{x}}<br>%{{y:,}} 条<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Bar(x=xs, y=yb, name=gb, marker_color=cb,
                         text=[f"{int(v):,}" if v is not None else "" for v in yb],
                         textposition="outside", cliponaxis=False,
                         hovertemplate=f"<b>{gb}</b> · %{{x}}<br>%{{y:,}} 条<extra></extra>"), row=1, col=1)
    fig.add_hline(y=avg_a, line_dash="dot", line_color=ca, row=1, col=1,
                  annotation_text=f"{ga} 基线 {avg_a:,}", annotation_position="top right",
                  annotation_font_color=ca)
    fig.add_hline(y=avg_b, line_dash="dot", line_color=cb, row=1, col=1,
                  annotation_text=f"{gb} 基线 {avg_b:,}", annotation_position="top right",
                  annotation_font_color=cb)
    for g, y, color in ((ga, ia, ca), (gb, ib, cb)):
        fig.add_trace(go.Scatter(x=xs, y=y, name=g, mode="lines+markers",
                                 line={"color": color}, marker={"size": 7}, connectgaps=False,
                                 showlegend=False,
                                 hovertemplate=f"<b>{g}</b> · %{{x}}<br>%{{y:.2f}}× 前7日均<extra></extra>"),
                      row=2, col=1)
    fig.add_hline(y=1.0, line_dash="dash", line_color="#9AA3AD", row=2, col=1,
                  annotation_text="基准 100%", annotation_position="top left",
                  annotation_font_color="#6B7C8A")
    # 未完成日标注（最新代际 b）
    y_top = max([v for v in (ya + yb) if v is not None] or [1])
    for t in range(1, td + 1):
        if b["daily"].get(str(t)) is None:
            fig.add_annotation(x=f"D{t}", y=y_top * 1.06, row=1, col=1, text="待补",
                               showarrow=False, font={"size": 10, "color": "#9AA3AD"})
    fig.update_layout(
        template="none", height=560, barmode="group",
        margin={"l": 10, "r": 90, "t": 60, "b": 30},
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", font={"color": "#374151", "size": 12},
        legend={"orientation": "h", "y": -0.10, "x": 0}, bargap=0.25, bargroupgap=0.08,
    )
    fig.update_yaxes(title_text="线索数（条）", automargin=True, gridcolor="#EEF2F6", linecolor="#C7CDD4", row=1, col=1)
    fig.update_yaxes(tickformat=".0%", rangemode="tozero", automargin=True,
                     gridcolor="#EEF2F6", linecolor="#C7CDD4", row=2, col=1)
    fig.update_xaxes(gridcolor="#FFFFFF", linecolor="#C7CDD4")
    return fig.to_json()


def _hex_lerp(c1, c2, t):
    return tuple(round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _heat_cell_style(v: float | None, vmax: float) -> str:
    """表格式热力图：按数值返回 inline 背景色 + 文字色（发散色阶，0 为白）。"""
    if v is None or not vmax:
        return ""
    t = max(-1.0, min(1.0, v / vmax))
    white = (255, 255, 255)
    if t >= 0:
        rgb = _hex_lerp(white, (23, 74, 124), t)     # own 蓝 = 增幅高
    else:
        rgb = _hex_lerp(white, (185, 74, 68), -t)    # 负向红 = 低于基线
    fg = "#FFFFFF" if abs(t) >= 0.55 else "#1F2D3D"
    return f"background:rgb({rgb[0]},{rgb[1]},{rgb[2]});color:{fg};"


def _lead_channel_abs_compare_figure(lc: dict) -> str | None:
    """渠道窗口绝对值对比：CM2 / CM3 各自「上市后 vs 自身基线」，按 N 分面。

    行 = 代际（CM2 / CM3），列 = N 窗口；每格灰条 = 基线(上市前 7 日均值×N)、
    蓝条 = 上市后窗口、条末标净增。同一列共享 x 轴（shared_xaxes="columns"），
    便于 CM2 与 CM3 在同一 N 下直接比较规模与净增。
    """
    a, b = lc["per"]["a"], lc["per"]["b"]
    ga, gb = lc["gens"]
    NDS = lc.get("window_days", [1, 3, 5, 7])
    chans = list(_CHANNEL_LABELS.values()) + ["全部渠道合计"]
    yorder = list(reversed(chans))  # 门店在上
    base_c = get_series_color("ash")
    gen_colors = {ga: get_series_color("steel"), gb: get_series_color("own")}

    def vals(side_key, per, cname, nd):
        if cname == "全部渠道合计":
            w = per["windows"][nd]
        else:
            r = next((x for x in lc["channels"][side_key] if x["channel"] == cname), None)
            w = r["windows"].get(nd) if r else None
        if not w or "pending" in w:
            return None
        return w

    rows = 2
    cols = len(NDS)
    col_max = [0.0] * cols
    fig = make_subplots(rows=rows, cols=cols, shared_xaxes=False, shared_yaxes=False,
                        horizontal_spacing=0.06, vertical_spacing=0.16,
                        subplot_titles=[f"{g} · 上市后 {nd} 天" for g in (ga, gb) for nd in NDS])
    for ri, (g, side_key, per) in enumerate(((ga, "a", a), (gb, "b", b)), start=1):
        color = gen_colors[g]
        for ci, nd in enumerate(NDS, start=1):
            base_x, win_x, delta_s, yy = [], [], [], []
            for cname in yorder:
                w = vals(side_key, per, cname, nd)
                yy.append(cname)
                if w is None:
                    base_x.append(None)
                    win_x.append(None)
                    delta_s.append("")
                else:
                    base_x.append(w["base"])
                    win_x.append(w["win"])
                    delta_s.append(f"{w['delta']:+,}")
            nums = [v for v in (base_x + win_x) if v is not None]
            if nums:
                col_max[ci - 1] = max(col_max[ci - 1], max(nums))
            fig.add_trace(go.Bar(y=yy, x=base_x, orientation="h", name="基线(7日均值×N)",
                                 marker_color=base_c, showlegend=(ri == 1 and ci == 1),
                                 hovertemplate="基线 %{x:,}<extra></extra>"), row=ri, col=ci)
            fig.add_trace(go.Bar(y=yy, x=win_x, orientation="h", name=f"{g} 上市后",
                                 marker_color=color, showlegend=(ci == 1),
                                 text=delta_s, textposition="outside", cliponaxis=False,
                                 textfont={"size": 10, "color": color},
                                 hovertemplate=f"{g} 上市后 %{{x:,}}<extra></extra>"), row=ri, col=ci)
    fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.1,
                      height=330 * rows,
                      margin={"l": 8, "r": 70, "t": 50, "b": 40},
                      paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                      font={"color": "#374151", "size": 12},
                      legend={"orientation": "h", "y": -0.06, "x": 0})
    # 同列统一横轴范围（含条末净增文字留白），便于 CM2 / CM3 同一 N 直接比较
    for ci in range(1, cols + 1):
        hi = (col_max[ci - 1] or 1.0) * 1.18
        fig.update_xaxes(range=[0, hi], row=1, col=ci)
        fig.update_xaxes(range=[0, hi], row=2, col=ci)
    fig.update_xaxes(gridcolor="#EEF2F6", linecolor="#C7CDD4", zeroline=False, automargin=True)
    fig.update_xaxes(showticklabels=False, row=1)  # 上排隐藏刻度，避免与下排重复
    fig.update_yaxes(gridcolor="#FFFFFF", linecolor="#C7CDD4", automargin=True)
    return fig.to_json()


def _lead_window_table(c: dict) -> str:
    lc = c.get("lead_window")
    if not lc or not lc.get("per"):
        return ""
    a, b = lc["per"]["a"], lc["per"]["b"]
    ga, gb = lc["gens"]
    NDS = lc.get("window_days", [1, 3, 5, 7])

    def _pct_cell(w, bold: bool = False) -> str:
        if "pending" in w:
            return ("<td class='num' style='color:#9AA3AD;'>—<span style='font-size:0.85em;'>（待补）</span></td>")
        v = w["delta_pct"]
        cls = " pos" if v > 0 else (" neg" if v < 0 else "")
        s = f"{w['delta']:+,}（{v * 100:+.1f}%）"
        return f"<td class='num{cls}'><strong>{s}</strong></td>" if bold else f"<td class='num{cls}'>{s}</td>"

    def _num_cell(w, key: str) -> str:
        if "pending" in w:
            return "<td class='num' style='color:#9AA3AD;'>—</td>"
        return f"<td class='num'>{w[key]:,}</td>"

    # 表 1：窗口增幅
    rows1 = []
    for n in NDS:
        wa, wb = a["windows"][n], b["windows"][n]
        rows1.append(
            f"<tr><td>上市后 {n} 天窗口</td>"
            f"{_num_cell(wa, 'win')}{_num_cell(wa, 'base')}{_pct_cell(wa)}"
            f"{_num_cell(wb, 'win')}{_num_cell(wb, 'base')}{_pct_cell(wb, bold=True)}</tr>"
        )
    # 表 2 → 图：每日下发线索（上绝对值 + 基线，下相对倍数）
    fig = _lead_daily_figure(lc)
    chart_html = (
        '<div class="chart-box" id="chart-lead-daily" style="height:560px;"></div>'
        if fig else ""
    )
    script_html = (
        f'<script>Plotly.newPlot("chart-lead-daily", {fig});</script>'
        if fig else ""
    )
    abs_fig = _lead_channel_abs_compare_figure(lc)
    abs_chart_html = (
        '<div class="chart-box" id="chart-lead-channel-abs" style="height:680px;"></div>'
        if abs_fig else ""
    )
    if abs_fig:
        script_html += f'\n<script>Plotly.newPlot("chart-lead-channel-abs", {abs_fig});</script>'

    # 增幅热力基准（|%|；上限截断至 100，避免 CM3 首窗极值把 CM2 差异压扁）
    _vals = []
    for side in ("a", "b"):
        for r in lc["channels"][side]:
            for n in NDS:
                w = r["windows"].get(n)
                if w and "pending" not in w and w.get("delta_pct") is not None:
                    _vals.append(abs(w["delta_pct"] * 100))
        for n in NDS:
            w = lc["per"][side]["windows"][n]
            if "pending" not in w and w.get("delta_pct") is not None:
                _vals.append(abs(w["delta_pct"] * 100))
    vmax = max(40.0, min(max(_vals) if _vals else 40.0, 100.0))

    # 表 3：渠道窗口增幅（表格式热力图：按值着色 + CM3 加粗 + ↑/↓）
    def _ch_cell(row, n, bold: bool = False) -> str:
        w = row["windows"].get(n) if row else None
        if not w or "pending" in w or w.get("delta_pct") is None:
            return "<td class='num' style='color:#9AA3AD;'>—</td>"
        pv = w["delta_pct"] * 100
        style = _heat_cell_style(pv, vmax)
        arrow = " ↑" if pv > 0 else (" ↓" if pv < 0 else "")
        s = f"{pv:+.1f}%{arrow}"
        if bold:
            s = f"<strong>{s}</strong>"
        return f"<td class='num' style='{style}'>{s}</td>"

    rows3 = []
    for cname in _CHANNEL_LABELS.values():
        ra = next((r for r in lc["channels"]["a"] if r["channel"] == cname), None)
        rb = next((r for r in lc["channels"]["b"] if r["channel"] == cname), None)
        rows3.append(
            f"<tr><td><strong>{cname}</strong></td>"
            + "".join(_ch_cell(ra, n) for n in NDS)
            + "".join(_ch_cell(rb, n, bold=True) for n in NDS) + "</tr>")
    # 合计行（整体，复用整体窗口窗口）
    rows3.append(
        f"<tr><td><strong>全部渠道合计</strong></td>"
        + "".join(_ch_cell(a, n) for n in NDS)
        + "".join(_ch_cell(b, n, bold=True) for n in NDS) + "</tr>"
    )
    thead3 = (f"<th>渠道</th><th colspan='{len(NDS)}'>{ga}</th>"
              f"<th colspan='{len(NDS)}'>{gb}（重点）</th>")
    subhead3 = "<th></th>" + "".join(f"<th>N{n}</th>" for n in NDS) * 2

    # 表 4：渠道窗口绝对值（{gb} = 重点，上市后窗口 / 基线 / 净增）
    def _abs3(row, n) -> str:
        w = row["windows"].get(n) if row else None
        if not w or "pending" in w:
            return "<td colspan='3' class='num' style='color:#9AA3AD;'>—（待补）</td>"
        return (f"<td class='num'>{w['win']:,}</td>"
                f"<td class='num'>{w['base']:,}</td>"
                f"<td class='num'>{w['delta']:+,}</td>")

    def _tot3(p, n) -> str:
        w = p["windows"][n]
        if "pending" in w:
            return "<td colspan='3' class='num' style='color:#9AA3AD;'>—（待补）</td>"
        return (f"<td class='num'><strong>{w['win']:,}</strong></td><td class='num'>{w['base']:,}</td>"
                f"<td class='num'>{w['delta']:+,}</td>")

    rows4 = []
    for g, side_key, per in ((ga, "a", a), (gb, "b", b)):
        rows4.append(
            f"<tr class='section-row'><td colspan='{1 + 3 * len(NDS)}'>"
            f"<strong>{g}</strong>（上市日 {per['end']}）</td></tr>")
        for cname in _CHANNEL_LABELS.values():
            r = next((x for x in lc["channels"][side_key] if x["channel"] == cname), None)
            rows4.append(f"<tr><td>{cname}</td>" + "".join(_abs3(r, n) for n in NDS) + "</tr>")
        rows4.append(f"<tr><td><strong>全部渠道合计</strong></td>"
                     + "".join(_tot3(per, n) for n in NDS) + "</tr>")
    thead4 = "<th>渠道</th>"
    thead4 += "".join(f"<th colspan='3'>上市后 {n} 天窗口</th>" for n in NDS)
    subhead4 = "<th></th>" + ("<th>上市后</th><th>基线(7日均值×N)</th><th>净增</th>" * len(NDS))

    insights_html = ""
    if lc.get("insights"):
        insights_html = '<div class="section-note" style="margin-top:14px;"><strong>判断</strong><ul style="margin:6px 0 0 18px;padding:0;">' + "".join(
            f"<li>{s}</li>" for s in lc["insights"]) + "</ul></div>"
    return f"""

    <div class="card">
      <h2>模块 6 · 上市后下发线索窗口增幅对比：{gb} vs {ga}</h2>
      <p class="section-note">数据源 = dataset/assign_data.csv「下发线索数」（整体口径）；完整观察日截至 <strong>{lc.get('complete_day', '—')}</strong>。上市后窗口 = 上市日 end 起 N 天（N = {'/'.join(str(n) for n in NDS)}）；基线 = 上市前 7 天日均 × N；窗口增幅 = (上市后窗口 − 基线) ÷ 基线。<strong>仅当 N 天全部为完整日才给结论</strong>：{gb} 上市已 {b['observed_days']} 天，未满 7 天的窗口标「待补」，不补 0。每日线索见下图（上：绝对值 + 上市前 7 日均值虚线；下：相对前 7 日均值倍数，基准 1.0）。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>窗口</th><th>{ga} 上市后</th><th>{ga} 基线</th><th>{ga} 增幅</th><th>{gb} 上市后</th><th>{gb} 基线</th><th>{gb} 增幅</th></tr></thead>
        <tbody>{''.join(rows1)}</tbody>
      </table>
      </div>
      <h3 style="margin-top:20px;">上市后每日下发线索（上：绝对值 + 前 7 日均值；下：相对前 7 日均值倍数）</h3>
      {chart_html}
      <h3 style="margin-top:20px;">渠道窗口增幅（上市后 N 天 vs 上市前 7 日均值 × N）</h3>
      <p class="section-note">表格式热力图：单元格底色按增幅着色（<span style="background:rgb(23,74,124);color:#fff;padding:0 4px;border-radius:3px;">蓝 = 增幅高</span> ／ <span style="background:rgb(185,74,68);color:#fff;padding:0 4px;border-radius:3px;">红 = 低于基线</span>，白色 = 与基线持平）；↑/↓ 表示方向，<strong>{gb}</strong> 列为加粗重点。为兼顾 CM2 与 CM3 可读性，色阶饱和上限截断至 ±{vmax:.0f}%（CM3 首窗 +242% 显示为饱和）。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr>{thead3}</tr><tr>{subhead3}</tr></thead>
        <tbody>{''.join(rows3)}</tbody>
      </table>
      </div>
      <h3 style="margin-top:20px;">渠道窗口绝对值对比（{ga} / {gb}：各自上市后窗口 vs 自身基线）</h3>
      <p class="section-note">行 = 代际（{ga} / {gb}），列 = 上市后 N 天；每格灰条 = 该代际<strong>上市前 7 日均值×N</strong>（基线），蓝条 = 该代际<strong>上市后窗口</strong>，条末标净增（上市后 − 基线）。<strong>同一列共享横轴</strong>，便于同一 N 下 {ga} 与 {gb} 直接比较规模与净增；两代基线各自独立（= 各自上市前 7 日均值），可区分「上市后规模差异」与「基线差异」。明细见下表。</p>
      {abs_chart_html}
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr>{thead4}</tr><tr>{subhead4}</tr></thead>
        <tbody>{''.join(rows4)}</tbody>
      </table>
      </div>
      {insights_html}
    </div>
    {script_html}"""


def _gen_to_testdrive_series(bd: dict, gen: str) -> str | None:
    """把代际映射到 test_drive_data.csv 的车系列（L6/LS6/LS9）；无对应列返回 None。"""
    for series, gens in (bd.get("model_series_mapping", {}) or {}).items():
        if gen in gens and series in _TESTDRIVE_SERIES_COL:
            return series
    if gen in _TESTDRIVE_SERIES_COL:
        return gen
    for series in _TESTDRIVE_SERIES_COL:  # 前缀兜底，如 LS9Hyper → LS9
        if gen.startswith(series):
            return series
    return None


def _load_test_drive_daily() -> pd.DataFrame | None:
    """读取试驾数据（Tableau core_metric_observation/7），日频，按车系列列。

    注意：有效试驾数列在 CSV 中带千分位逗号（如 "1,020"），需先去除再加数值化。
    """
    if not _TEST_DRIVE_DATA.exists():
        return None
    df = pd.read_csv(_TEST_DRIVE_DATA, encoding="utf-8-sig")
    out = {"d": pd.to_datetime(df["create_date 年/月/日"], format="%Y年%m月%d日", errors="coerce")}
    for series, col in _TESTDRIVE_SERIES_COL.items():
        if col in df.columns:
            out[series] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
    return pd.DataFrame(out).dropna(subset=["d"]).sort_values("d")


def _test_drive_compare(bd: dict, gens: list[str], ends: dict,
                        last_date: pd.Timestamp) -> dict | None:
    """模块 8：试驾数据（按车系）对齐上市前后天数，对比各代际上市周期试驾表现。

    - 试驾数据按车系（L6/LS6/LS9）拆分，无法按代际拆分；每个代际映射到其车系列，
      读该系列日频「有效试驾数」，按各代际自己的上市日对齐「上市前后天数」。
    - 窗口 = 上市前 _TEST_DRIVE_PRE_DAYS 天 ~ 上市后截至数据最新完整日（各代际同窗口）。
    - 上市前 7 日均值 = 上市日前第 1..7 天（不含上市日）的均值。
    """
    daily = _load_test_drive_daily()
    if daily is None:
        return None
    series_map = {g: _gen_to_testdrive_series(bd, g) for g in gens}
    usable = [g for g in gens if series_map[g]]
    if not usable:
        return None
    last_date = pd.Timestamp(last_date).normalize()
    max_end = max(pd.Timestamp(ends[g]).normalize() for g in usable)
    end_off = max(0, int((last_date - max_end).days))
    start_off = -_TEST_DRIVE_PRE_DAYS
    s_by_series = {s: daily.set_index("d")[s] for s in {series_map[g] for g in usable}}
    offsets = list(range(start_off, end_off + 1))

    def _val(series: str, end: pd.Timestamp, off: int):
        v = s_by_series[series].get(end + pd.Timedelta(days=off))
        return None if (v is None or pd.isna(v)) else int(round(float(v)))

    rows, per = [], {}
    for g in usable:
        end = pd.Timestamp(ends[g]).normalize()
        series = series_map[g]
        vals = {off: _val(series, end, off) for off in offsets}
        pre7 = [vals[o] for o in range(-7, 0) if vals.get(o) is not None]
        post = [vals[o] for o in range(1, end_off + 1) if vals.get(o) is not None]
        per[g] = {
            "gen": g, "series": series, "end": end.date().isoformat(),
            "values": vals,
            "pre7_avg": round(sum(pre7) / len(pre7), 1) if pre7 else None,
            "launch": vals.get(0),
            "post_avg": round(sum(post) / len(post), 1) if post else None,
            "post_sum": int(sum(post)) if post else None,
            "post_days": len(post),
        }
    for off in offsets:
        rows.append({"offset": off,
                     "values": {g: per[g]["values"].get(off) for g in usable},
                     "dates": {g: (pd.Timestamp(per[g]["end"]) + pd.Timedelta(days=off)).date().isoformat()
                               for g in usable}})

    insights = []
    if len(usable) >= 2:
        gb, ga = usable[-1], usable[-2]
        pb, pa = per[gb], per[ga]
        if pb["pre7_avg"] and pa["pre7_avg"]:
            chg = (pb["pre7_avg"] - pa["pre7_avg"]) / pa["pre7_avg"]
            insights.append(
                f"上市前 7 日试驾日均：{gb}（{pb['series']}）{pb['pre7_avg']:,.0f} vs "
                f"{ga}（{pa['series']}）{pa['pre7_avg']:,.0f}（{chg:+.0%}）。")
        if pb["post_avg"] and pa["post_avg"]:
            chg = (pb["post_avg"] - pa["post_avg"]) / pa["post_avg"]
            insights.append(
                f"上市后 {pb['post_days']} 日试驾日均：{gb} {pb['post_avg']:,.0f} vs "
                f"{ga} {pa['post_avg']:,.0f}（{chg:+.0%}）。")
    return {"gens": usable, "series_map": series_map, "start_off": start_off,
            "end_off": end_off, "rows": rows, "per": per, "insights": insights,
            "metric": "有效试驾数", "pre_days": _TEST_DRIVE_PRE_DAYS,
            "last_date": last_date.date().isoformat(),
            "data_source": "dataset/test_drive_data.csv（Tableau core_metric_observation/7）"}


def _test_drive_table(c: dict) -> str:
    td = c.get("test_drive")
    if not td or not td.get("rows"):
        return ""
    usable = td["gens"]
    end_off = td["end_off"]

    def _off_label(o: int) -> str:
        if o == 0:
            return "★ 上市日"
        return f"上市前 {abs(o)} 天" if o < 0 else f"上市后 {o} 天"

    head = "<tr><th>上市前后天</th>"
    for g in usable:
        head += f"<th>{g} 日期</th><th>{g} 有效试驾</th>"
    head += "</tr>"

    body = []
    for r in td["rows"]:
        o = r["offset"]
        cls = " style='background:var(--zh-gold-100);'" if o == 0 else ""
        cells = f"<td>{_off_label(o)}</td>"
        for g in usable:
            v = r["values"].get(g)
            vs = "—" if v is None else f"{v:,}"
            if g == usable[-1] and v is not None:
                vs = f"<strong>{vs}</strong>"
            cells += f"<td class='num' style='color:#6B7280;'>{r['dates'][g]}</td><td class='num'>{vs}</td>"
        body.append(f"<tr{cls}>{cells}</tr>")

    def _fmt(v, dec: int = 0) -> str:
        return "—" if v is None else f"{v:,.{dec}f}"

    sum_rows = []
    for label, key in (("上市前 7 日试驾日均", "pre7_avg"),
                       ("上市日", "launch"),
                       (f"上市后 {end_off} 日日均", "post_avg"),
                       (f"上市后 {end_off} 日合计", "post_sum")):
        cells = f"<td>{label}</td>"
        for g in usable:
            cells += f"<td class='num'>{_fmt(td['per'][g].get(key))}</td>"
        sum_rows.append(f"<tr>{cells}</tr>")
    sum_head = "<tr><th>周期指标</th>" + "".join(f"<th>{g}</th>" for g in usable) + "</tr>"

    insights_html = ""
    if td.get("insights"):
        insights_html = ('<div class="section-note" style="margin-top:14px;"><strong>判断</strong>'
                         '<ul style="margin:6px 0 0 18px;padding:0;">'
                         + "".join(f"<li>{s}</li>" for s in td["insights"]) + "</ul></div>")

    gmap = " / ".join(f"{g}→{td['series_map'][g]}" for g in usable)
    return f"""
    <div class="card">
      <h2>模块 8 · 上市周期试驾数据对比：{''.join(usable)}（对齐上市前后天数）</h2>
      <p class="section-note">数据源 = {td['data_source']}（日频，按<strong>车系</strong>拆分，无法按代际拆分）；代际→车系映射 = {gmap}。各代际读其车系列的「有效试驾数」，按各自上市日对齐「上市前后天数」，窗口 = 上市前 {td['pre_days']} 天 ~ 上市后 {end_off} 天（★ 上市日），上市后数据统计截至 {td['last_date']}。上市前 7 日试驾日均 = 上市日前第 1..7 天均值（不含上市日）。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead>{head}</thead>
        <tbody>{''.join(body)}</tbody>
      </table>
      </div>
      <h3 style="margin-top:20px;">周期汇总</h3>
      <div class="table-wrap">
      <table class="report-table">
        <thead>{sum_head}</thead>
        <tbody>{''.join(sum_rows)}</tbody>
      </table>
      </div>
      {insights_html}
    </div>"""


def _lock_config_table(c: dict) -> str:
    lc = c.get("lock_config")
    if not lc or not lc.get("attrs"):
        return ""
    n = lc["n"]
    core_rows = []
    for a in lc["attrs"]:
        tag = " · 核心" if is_core_attribute(a["attribute"]) else ""
        items = "".join(
            f"<tr><td>{it['value']}</td><td class='num'>{it['count']:,}</td>"
            f"<td class='num'>{it['share'] * 100:.1f}%</td>"
            f"<td><div class='barcell'><div class='bar' style='width:{it['share'] * 100:.0f}%'></div>"
            f"<div class='txt'>{it['share'] * 100:.1f}%</div></div></td></tr>"
            for it in a["items"])
        core_rows.append(
            f"<h3 style='margin-top:20px;'>{a['attribute']}{tag} "
            f"（关联 {a['orders_with_value']}/{n} 单）</h3>"
            f"<div class='table-wrap'><table class='report-table'>"
            f"<thead><tr><th>选配项</th><th>数量</th><th>占锁单</th><th style='min-width:180px;'>占比</th></tr></thead>"
            f"<tbody>{items}</tbody></table></div>")

    opt_rows = ""
    if lc.get("option_attrs"):
        opt_rows = "".join(
            f"<tr><td>{a['attribute']}</td><td class='num'>{a['yes_count']:,}</td>"
            f"<td class='num'>{n:,}</td><td class='num'><strong>{a['yes_count'] / n * 100:.1f}%</strong></td>"
            f"<td><div class='barcell'><div class='bar' style='width:{a['yes_count'] / n * 100:.0f}%'></div>"
            f"<div class='txt'>{a['yes_count'] / n * 100:.1f}%</div></div></td></tr>"
            for a in lc["option_attrs"])

    return f"""
    <div class="card">
      <h2>模块 7 · {lc['gen']} 上市以来锁单配置分布（{lc['launch']} ~ {lc['hi']}，零售 {n} 单）</h2>
      <p class="section-note">本模块复用 research_scripts/lock_config_distribution.py（独立脚本，--format json 输出 Result Contract）。数据源 = dataset/config_attribute.parquet（order_config_to_parquet.py 增量更新后含最新代际）。锁单窗口 = {lc['gen']} 上市日 {lc['launch']} 起至 {lc['hi']}（零售口径 order_type ∈ 用户车/NaN，并剔除测试单：总部主理店 + 假身份号，与模块 1 一致）；配置归属 = 锁单订单 (Order Number) 匹配的 Attribute/value；核心 5 配置 = 内饰 / 外饰 / 轮毂 / 方向盘 / 激光雷达（含「超远距高精度激光雷达」等同槽位别名）。{n} 单全部可关联配置，核心 5 配置完整 {lc['core_complete']} 单（{lc['core_complete'] / n * 100:.0f}%）。</p>
      {''.join(core_rows)}
      {f'<h3 style="margin-top:20px;">是/否型选装项拥有率（是 = 已选）</h3><div class="table-wrap"><table class="report-table"><thead><tr><th>选装项</th><th>已选</th><th>锁单总数</th><th>拥有率</th><th style="min-width:180px;"></th></tr></thead><tbody>{opt_rows}</tbody></table></div>' if opt_rows else ''}
    </div>"""


def _presale_conversion(df: pd.DataFrame, bd: dict, gens: list[str],
                        ends: dict, n_days: int) -> list[dict]:
    """预售小订 → 上市 N 日锁单分解（口径对齐 business_scripts/presale_intention_funnel.py 通用漏斗）。

    逐代际，统一 N 日窗口（截止 = 上市日 + N - 1，与本报告折线同窗口，保证各代际可比）：
       预售小订池 cohort_total（预售 cohort 起点 ~ 上市日结束支付意向金，order_number 去重、剔测试单）
        ├─ 预售退订 refunded_total（截止前意向金已退）
        └─ 留存小订 retained_count = 小订池 − 预售退订
      上市 N 日锁单总数 total_lock（该代际 lock_time ∈ [上市日, 上市日+N)，剔测试单）
        ├─ 预售转化锁单 presale_conv（小订池中于截止前锁单；= 通用漏斗 locked_only）
        └─ 直接锁单 direct_lock = N 日锁单总数 − 预售转化锁单
    预售退订率 = 预售退订 ÷ 小订池；预售转化率 = 预售转化锁单 ÷ 留存小订；
    直接锁单占比 = 直接锁单 ÷ N 日锁单总数。
    """
    rows: list[dict] = []
    for g in gens:
        launch = pd.Timestamp(ends[g]).normalize()
        as_of = launch + pd.Timedelta(days=n_days - 1)
        try:
            f = compute_presale_funnel(df, bd, g, as_of, include_test_orders=False)
        except Exception as exc:  # noqa: BLE001
            rows.append({"gen": g, "error": str(exc)})
            continue
        cohort = int(f["cohort_total"])
        refunded = int(f["refunded_total"])
        retained = int(f["retained_not_refunded"])
        presale_conv = int(f["locked_only"])

        sub = df[df["series_group_logic"].eq(g)
                 & _retail_mask(df["order_type"])
                 & ~flag_test_orders(df, bd)].copy()
        lock = pd.to_datetime(sub["lock_time"], errors="coerce")
        win = lock.notna() & (lock >= launch) & (lock < launch + pd.Timedelta(days=n_days))
        total_lock = int(sub.loc[win, "order_number"].nunique())
        direct = max(total_lock - presale_conv, 0)

        def rate(num: int, den: int) -> float | None:
            return (num / den) if den else None

        rows.append({
            "gen": g,
            "label": f.get("label", g),
            "launch": launch.date().isoformat(),
            "as_of": as_of.date().isoformat(),
            "n_days": n_days,
            "cohort_total": cohort,
            "refunded_total": refunded,
            "retained_count": retained,
            "total_lock": total_lock,
            "presale_conv": presale_conv,
            "direct_lock": direct,
            "refund_rate": rate(refunded, cohort),
            "presale_conversion_rate": rate(presale_conv, retained),
            "direct_share": rate(direct, total_lock),
            "presale_conv_share": rate(presale_conv, total_lock),
            "test_orders_excluded": int(f.get("test_orders_excluded") or 0),
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


def _presale_breakdown_figure(rows: list[dict], n_days: int) -> str:
    """预售小订 → 上市 N 日锁单 双层堆叠分解图（每代际两条：预售小订池 / 上市 N 日锁单）。"""
    valid = [r for r in rows if "error" not in r and r.get("cohort_total")]
    if not valid:
        return ""
    order = list(reversed(valid))  # 最新代际在上
    ys, retained_x, refunded_x, conv_x, direct_x = [], [], [], [], []
    for r in order:
        ys.append(f"{r['gen']}·预售小订池")
        retained_x.append(r["retained_count"])
        refunded_x.append(r["refunded_total"])
        conv_x.append(0)
        direct_x.append(0)
        ys.append(f"{r['gen']}·{n_days}日锁单")
        retained_x.append(0)
        refunded_x.append(0)
        conv_x.append(r["presale_conv"])
        direct_x.append(r["direct_lock"])

    x_max = max([r["cohort_total"] for r in valid] + [r["total_lock"] for r in valid]) or 1
    txt_threshold = x_max * 0.04

    def _bar(name: str, x: list[int], color: str) -> go.Bar:
        return go.Bar(
            name=name, y=ys, x=x, orientation="h",
            marker={"color": color},
            text=[f"{v:,}" if v >= txt_threshold else "" for v in x],
            textposition="inside", insidetextanchor="middle",
            textfont={"color": "#FFFFFF", "size": 11},
            hovertemplate=f"<b>%{{y}}</b><br>{name}：%{{x:,}} 单<extra></extra>",
        )

    fig = go.Figure(data=[
        _bar("留存小订", retained_x, _BREAKDOWN_COLORS["留存小订"]),
        _bar("预售退订", refunded_x, _BREAKDOWN_COLORS["预售退订"]),
        _bar("预售转化锁单", conv_x, _BREAKDOWN_COLORS["预售转化锁单"]),
        _bar("直接锁单", direct_x, _BREAKDOWN_COLORS["直接锁单"]),
    ])

    def _pct(v) -> str:
        return "—" if v is None else f"{v * 100:.1f}%"

    annotations = []
    for r in order:
        annotations.append(dict(
            x=x_max * 1.03, y=f"{r['gen']}·预售小订池", xref="x", yref="y", showarrow=False,
            xanchor="left", align="left", font={"size": 11, "color": "#5F6B7A"},
            text=f"退订率 {_pct(r['refund_rate'])}｜留存 {r['retained_count']:,}",
        ))
        annotations.append(dict(
            x=x_max * 1.03, y=f"{r['gen']}·{n_days}日锁单", xref="x", yref="y", showarrow=False,
            xanchor="left", align="left", font={"size": 11, "color": "#5F6B7A"},
            text=f"预售转化率 {_pct(r['presale_conversion_rate'])}｜直接锁单占比 {_pct(r['direct_share'])}",
        ))
    fig.update_layout(
        template="none",
        barmode="stack",
        height=150 + 56 * len(ys),
        margin={"l": 10, "r": 10, "t": 50, "b": 30},
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        font={"color": "#374151", "size": 12},
        title={"text": f"预售小订 → 上市 {n_days} 日锁单分解（每代际：小订池 / 锁单）", "x": 0.01, "xanchor": "left"},
        legend={"orientation": "h", "y": -0.16, "x": 0},
        xaxis={"title": "订单数（单）", "rangemode": "tozero", "range": [0, x_max * 1.45],
               "gridcolor": "#EEF2F6", "linecolor": "#C7CDD4", "zeroline": False},
        yaxis={"autorange": "reversed", "automargin": True, "tickfont": {"size": 12},
               "gridcolor": "#FFFFFF", "linecolor": "#FFFFFF"},
        annotations=annotations,
    )
    return fig.to_json()


def _key_points_table(c: dict) -> str:
    rows = c["presale"]
    n_days = c["n_days"]
    body = []

    def _pct(v) -> str:
        return "—" if v is None else f"{v * 100:.1f}%"

    for r in rows:
        if "error" in r:
            body.append(
                f"<tr><td><strong>{r['gen']}</strong></td>"
                f"<td colspan='10' class='cell-note'>无法计算：{r['error']}</td></tr>"
            )
            continue
        body.append(
            f"<tr><td><strong>{r['gen']}</strong></td>"
            f"<td class='num'>{r['launch'] or '—'}</td>"
            f"<td class='num'>{r['cohort_total']:,}</td>"
            f"<td class='num'>{r['refunded_total']:,}</td>"
            f"<td class='num'>{r['retained_count']:,}</td>"
            f"<td class='num'><strong>{r['total_lock']:,}</strong></td>"
            f"<td class='num'>{r['presale_conv']:,}</td>"
            f"<td class='num'>{r['direct_lock']:,}</td>"
            f"<td class='num'>{_pct(r['refund_rate'])}</td>"
            f"<td class='num'>{_pct(r['presale_conversion_rate'])}</td>"
            f"<td class='num'>{_pct(r['direct_share'])}</td></tr>"
        )
    fig = _presale_breakdown_figure(rows, n_days)
    chart_html = (
        '<div class="chart-box" id="chart-presale-breakdown" style="height:520px;"></div>'
        if fig else ""
    )
    script_html = (
        f'<script>Plotly.newPlot("chart-presale-breakdown", {fig});</script>'
        if fig else ""
    )
    return f"""
    <div class="card">
      <h2>预售小订 → 上市 {n_days} 日锁单分解（口径对齐通用漏斗）</h2>
      <p class="section-note">指标定义对齐 business_scripts/presale_intention_funnel.py（通用漏斗，已剔测试单），各代际统一 <strong>{n_days} 日窗口</strong>（截止 = 上市日 + {n_days - 1}，与折线同窗口，保证可比）：预售小订池 = 预售 cohort 起点 ~ 上市日结束支付意向金（order_number 去重）；预售退订 = 截止前意向金已退；留存小订 = 小订池 − 预售退订；上市 {n_days} 日锁单总数 = 该代际 [上市日, 上市日+{n_days}) 内 lock_time 非空订单（零售口径，剔测试单，去重）；预售转化锁单 = 小订池中截止前锁单；直接锁单 = 锁单总数 − 预售转化锁单。预售退订率 = 预售退订 ÷ 小订池；<strong>预售转化率 = 预售转化锁单 ÷ 留存小订</strong>；直接锁单占比 = 直接锁单 ÷ {n_days} 日锁单总数。</p>
      {chart_html}
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>代际</th><th>上市日</th><th>预售小订池</th><th>预售退订</th><th>留存小订</th><th>上市 {n_days} 日锁单总数</th><th>预售转化锁单</th><th>直接锁单</th><th>预售退订率</th><th>预售转化率</th><th>直接锁单占比</th></tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
      </div>
    </div>
    {script_html}"""


def render_html(c: dict) -> str:
    gens = c["gens"]
    n = c["n_days"]
    cur = c["curves"]
    chart = c["chart"]
    chart_n = c["chart_window"]
    latest = {g: cur[g]["cum"][n - 1] for g in gens}
    top_gen = max(latest, key=latest.get)
    second = sorted(latest.values(), reverse=True)[1] if len(latest) > 1 else 1
    ratio = latest[top_gen] / max(second, 1)

    # 口径桥接注记：零售口径 vs 上市监控卡片口径（仅未排除类型时显示）
    rb = c.get("retail_bridge") or {}
    bridge_note = ""
    if rb.get("excluded"):
        types = "、".join(rb.get("excluded_types", {}).keys()) or "非零售单"
        bridge_note = (
            f" 口径提示：本模块为<strong>零售口径</strong>，{rb['gen']} 同期（{rb['start']} ~ {rb['last_date']}）"
            f"已排除 {rb['excluded']} 台{types}；若按<strong>上市监控卡片口径</strong>（全部 order_type、仅剔测试单），"
            f"同期为 <strong>{rb['all_types']:,}</strong> 单（其中零售 {rb['retail']:,}）。"
        )

    x_range = [0.5, chart_n + 2.0]
    x_ticks = list(range(1, chart_n + 1))

    def _color(g: str) -> str:
        if g == gens[-1]:
            return get_series_color("own")
        # 由近及远分配异色（跳过与本品蓝接近的 steel）：最近的上代际取 sage，更早取 mauve
        i = list(reversed(gens[:-1])).index(g)
        return get_series_color(["sage", "mauve", "clay", "sky_muted"][i % 4])

    end_labels = [
        {"x": chart[g]["day_offset"][-1], "y": chart[g]["cum"][-1],
         "text": f"{chart[g]['cum'][-1]:,}", "showarrow": False,
         "xanchor": "left", "yanchor": "middle", "xshift": 7,
         "font": {"color": _color(g), "size": 12}}
        for g in gens if chart[g]["cum"]
    ]

    fig_json = json.dumps({
        "data": [{
            "x": chart[g]["day_offset"],
            "y": chart[g]["cum"],
            "customdata": chart[g]["dates"],
            "mode": "lines+markers",
            "name": f"{g}（{chart[g]['available_days']} 天）",
            "line": {"width": (3.0 if g == gens[-1] else 2.5),
                     "color": _color(g),
                     "dash": None if g == gens[-1] else ("dot" if g == gens[0] else "dash")},
            "marker": {"size": 5 if g == gens[-1] else 4},
            "hovertemplate": f"<b>{g}</b> · 上市后第 %{{x}} 天（%{{customdata}}）<br>累计锁单 %{{y:,}} 单<extra></extra>",
        } for g in gens],
        "layout": {
            "title": {"text": f"上市后累计锁单对比（{''.join(gens)}，{chart_n} 天窗口）", "x": 0.01, "xanchor": "left"},
            "xaxis": {"title": "上市后天数（第 1 天 = 各代际上市日）",
                      "range": x_range, "tickmode": "array", "tickvals": x_ticks},
            "yaxis": {"title": "累计零售锁单（单）", "rangemode": "tozero"},
            "annotations": end_labels,
            "legend": {"orientation": "h", "y": -0.25, "x": 0},
            "margin": {"l": 60, "r": 70, "t": 55, "b": 70},
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
    <p>折线窗口 {chart_n} 天（第 1 天 = 各代际上市日）；{gens[-1]} 上市 {chart[gens[-1]]['available_days']} 天暂画至该天数，其余代际满 {chart_n} 天；累计至 {c['last_date']}。</p>
  </section>

  <div class="summary-grid">
    <div class="summary-card"><div class="summary-value">{_fmt_int(latest[gens[-1]])}</div>
      <div class="summary-label">{gens[-1]} 同窗口（{n} 天）累计</div><div class="summary-hint">第 {n} 天</div></div>
    <div class="summary-card"><div class="summary-value">{_fmt_int(latest[gens[1]])}</div>
      <div class="summary-label">{gens[1]} 同窗口（{n} 天）累计</div><div class="summary-hint">第 {n} 天</div></div>
    <div class="summary-card"><div class="summary-value">{_fmt_int(latest[gens[0]])}</div>
      <div class="summary-label">{gens[0]} 同窗口（{n} 天）累计</div><div class="summary-hint">第 {n} 天</div></div>
    <div class="summary-card"><div class="summary-value">{top_gen}</div>
      <div class="summary-label">同窗口最高</div><div class="summary-hint">领先约 {ratio:.1f} 倍</div></div>
  </div>

  <section class="card">
    <h2>模块 1 · 上市后每日累计锁单对比折线图</h2>
    <div class="chart-box" id="chart-launch-cum" style="height:520px;"></div>
    <div class="section-note">
      各代际自其上市日（{' / '.join(f"{g} {chart[g]['end']}" for g in gens)}）起，按上市后天数对齐绘制第 1..{chart_n} 天；
      累计 = 截至当日 23:59 零售锁单 COUNTD(order_number)（order_type ∈ 用户车/NaN，且剔除测试单：总部主理店 + 假身份号）。{gens[-1]} 上市仅 {chart[gens[-1]]['available_days']} 天，曲线暂绘制至该天数（不补齐）；其余代际满 {chart_n} 天。{gens[-1]} 为实线，{gens[1]} 虚线、{gens[0]} 点线以示区分。{bridge_note}
    </div>
  </section>

  {_key_points_table(c)}

  {_daily_product_table(c)}

  {_region_table(c)}

  {_store_network_table(c)}

  {_user_profile_table(c)}

  {_age_repurchase_table(c)}

  {_lead_window_table(c)}

  {_lock_config_table(c)}

  {_test_drive_table(c)}

  <div class="method-section">
    <h2 class="section-title">口径与数据来源</h2>
    <div class="method-grid">
      <div class="method-item"><div class="method-icon" style="background:var(--zh-blue-100);color:var(--zh-blue);">D</div>
        <div class="method-body"><strong>数据源</strong><br/>dataset/order_data.parquet<br/>dataset/assign_data.csv（有效门店 / 下发线索，模块 6）<br/>shared/schema/business_definition.json<br/>shared/loaders/store_info_loader.py（经销商 Bloc 关联）<br/>research_scripts/store_network_compare.py（网络对比组件）<br/>business_scripts/user_profile.py（画像字段口径）<br/>shared/operators/repurchase.py（复购算子）<br/>research_scripts/lock_config_distribution.py（模块 7 · 配置分布）<br/>dataset/config_attribute.parquet（模块 7 · 配置）<br/>dataset/test_drive_data.csv（模块 8 · 试驾，Tableau core_metric_observation/7）</div></div>
      <div class="method-item"><div class="method-icon" style="background:var(--zh-gold-100);color:var(--zh-gold-700);">T</div>
        <div class="method-body"><strong>时间窗口</strong><br/>各代际上市日（time_periods.end）起<br/>共同 {c['n_days']} 天，累计至 {c['last_date']}</div></div>
      <div class="method-item"><div class="method-icon" style="background:#E8F8FD;color:#2D6FA3;">F</div>
        <div class="method-body"><strong>筛选口径</strong><br/>零售 = order_type ∈ {{用户车, NaN}}<br/>排除试驾车/员工/大客户/批售等非零售单<br/>剔除测试单（总部主理店 + 假身份号，flag_test_orders，与上市监控同口径）<br/>注意：上市监控卡片不区分 order_type（仅剔测试单），故卡片数 ≈ 本报告零售数 + 非零售单；见模块 1 口径提示</div></div>
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
                                "n_days": c["n_days"],
                                "chart_window": c["chart_window"]},
                "filters": {"gens": gens,
                            "order_type": "用户车/NaN（零售口径）",
                            "metric_definition": "累计锁单 = 自上市日起 COUNTD(order_number) 截至当日；天数以最新代际上市日为第1天"},
            },
            "result": {
                "summary": f"{' / '.join(gens)} 上市后 {c['n_days']} 天累计锁单对比",
                "metrics": {g: {"cum": c["curves"][g]["cum"][-1],
                                "daily_last": c["curves"][g]["daily"][-1]} for g in gens},
                "curve": c["curves"],
                "chart": c["chart"],
                "presale_conversion": c["presale"],
                "daily_product_lock": c["daily_product"],
                "region_compare": c["region"],
                "store_network_compare": c["network"],
                "user_profile_compare": c["user_profile"],
                "age_repurchase_compare": c["age_repurchase"],
                "lead_window_compare": c["lead_window"],
                "lock_config_distribution": c["lock_config"],
                "test_drive_compare": c["test_drive"],
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
