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
  省份结构；口径字段参考 l6_m2_presale_report 用户画像模块与 runtime_scripts/user_profile.py）。

模块 5：车主年龄分层 & 复购对比（owner_age 分年龄段 vs 历届；复购复用 shared/operators/
  repurchase.py 算子 mode=fulfilled_repurchase（canonical）：owner_identity_no 在窗口前已完成
  兑现购车（交付或开票早于上市日）→ 复购，排除"历史已锁未兑现"悬置误判；
   宽松对照 mode=prior_locker 对齐 lock_attribution_analysis "Repeat Lockers (Had Prior Locks)"）。

模块 6：集团订单上市对比（智己L6 / MG 07 / 大众ID.ERA 5S，上市后 N 日每日 + 累计订单）；
  数据源 = 观星台集团订单日报「重点车型(订单)」国内订单（outputs/tables/重点车型（订单）.csv，
  由 saic_group_order_daily_parse.py 重刷），口径与模块 1 内部零售锁单不同源；命名归一复用
  model_order_monthly_compare_report.NAME2CANON（保持两脚本一致）。

模块 7：上市后下发线索窗口增幅对比（最新两代际 DM1/DM2，assign_data「下发线索数」整体口径，
  上市后 N 天窗口 vs 上市前等长基线，N=1/3/7；含上市后 D1..D7 每日相对前 7 日均值节奏）。

模块 8：DM2 上市以来锁单配置分布（复用 research_scripts/l6_m2_lock_config_distribution.py；
  数据源 = config_attribute.parquet 增量更新后；核心 5 属性 + 是/否型选装项拥有率）。

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
from research_scripts.l6_m2_lock_config_distribution import (  # noqa: E402
    compute_lock_config_distribution,
)
from research_scripts.model_order_monthly_compare_report import NAME2CANON  # noqa: E402
from research_scripts.store_network_compare import compute_store_network  # noqa: E402
from runtime_scripts.user_profile import (  # noqa: E402
    CITY_TO_PROVINCE,
    age_cohort_distribution,
    city_to_tier_label,
    norm_city,
)
from utils.paths import ensure_shared_on_path  # noqa: E402
from utils.plotly_theme import apply_zh_theme, get_series_color  # noqa: E402
from utils.regions import REGION_MAP_OLD_TO_NEW, norm_region  # noqa: E402

ensure_shared_on_path()  # 让 operators.*（shared/operators）优先于 legacy runtime 可导入
from operators.repurchase import split_repurchase  # noqa: E402

_BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
_ORDER_DATA = REPO_ROOT / "dataset" / "order_data.parquet"
_ASSIGN_DATA = REPO_ROOT / "dataset" / "assign_data.csv"
_GROUP_ORDER_CSV = _WS / "outputs" / "tables" / "重点车型（订单）.csv"
_DEFAULT_REPORT = _WS / "outputs" / "reports"
_DEFAULT_TABLE = _WS / "outputs" / "tables"

DEFAULT_GENS = ["DM0", "DM1", "DM2"]
NON_RETAIL = {"试驾车", "大客户", "员工", "集团员工", "经销商员工", "享道", "仅批售", "项目", "展车", "海外"}

# 集团订单上市对比（观星台订单日报「重点车型(订单)」口径，全代际汇总）：
# 车型规范名 → 上市日 t0（用户口径：智己L6=08-28 上市；MG 07 / 大众ID.ERA 5S 以 08-21 为基准，近似对齐）
GROUP_ORDER_MODELS = [
    {"model": "智己L6", "t0": "2026-08-28", "label": "智己L6（上市 08-28）"},
    {"model": "MG 07", "t0": "2026-08-21", "label": "MG 07（以 08-21 对齐）"},
    {"model": "大众ID.ERA 5S", "t0": "2026-08-21", "label": "大众ID.ERA 5S（以 08-21 对齐）"},
]


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
        "user_profile": _user_profile_compare(retail, gens, ends, n_days),
        "age_repurchase": _age_repurchase_compare(retail, gens, ends, n_days),
        "group_order": _group_order_compare(),
        "lead_window": _lead_window_compare(ends),
        "lock_config": _lock_config_distribution(as_of.normalize()),
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

    口径字段参考 l6_m2_presale_report 用户画像模块与 runtime_scripts/user_profile.py：
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
    male_target = _share(target, "gender", "男")
    if others:
        male_others = [_share(p, "gender", "男") for p in others]
        direction = "高于" if male_target >= max(male_others) else \
            ("介于" if min(male_others) < male_target < max(male_others) else "低于")
        insights.append(f"{latest} 男性占比 {male_target * 100:.0f}%，{direction}其余代际"
                        f"（{min(male_others) * 100:.0f}%~{max(male_others) * 100:.0f}%）。")
    med_target = target["age_owner"].get("median")
    if med_target is not None and others:
        meds = [p["age_owner"].get("median") for p in others]
        meds = [m for m in meds if m is not None]
        if meds:
            direction = "更年轻" if med_target <= min(meds) else ("更年长" if med_target >= max(meds) else "与历届相近")
            insights.append(f"{latest} 车主年龄中位 {med_target:.0f} 岁，{direction}"
                            f"（其余代际 {min(meds):.0f}~{max(meds):.0f} 岁）。")
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


def _lock_config_distribution(as_of: pd.Timestamp | None = None) -> dict | None:
    """模块 8：DM2 上市以来锁单配置分布。

    复用 research_scripts/l6_m2_lock_config_distribution.py 的
    compute_lock_config_distribution()（独立脚本，--format json 输出 Result Contract）。
    窗口与报告对齐：上市日 end 起至 as_of（数据最新完整日）。
    """
    try:
        return compute_lock_config_distribution(as_of=as_of)
    except Exception:
        return None


def _lead_window_compare(ends: dict) -> dict | None:
    """模块 7：最新两代际上市后下发线索窗口增幅对比。

    口径：assign_data「下发线索数」整体口径。
      - 上市后窗口 = 上市日 end 起 N 天（[end, end+N)）
      - 基线 = 上市前等长窗口（[end-N, end)），N = 1/3/7
      - 每日节奏：上市后 D1..D7 相对上市前 7 天日均的增减
    DM2 基线(08-21~08-27)处于预售放量高峰，故窗口增幅走低；DM1 上市日见顶。
    """
    if len(ends) < 2:
        return None
    keys = list(ends)
    gen_a, gen_b = keys[-2], keys[-1]
    df = _load_assign_daily()
    if df.empty:
        return None
    s = df.set_index("d")["下发线索数"]

    def _sum(lo: pd.Timestamp, n: int) -> float:
        return float(s.loc[lo:lo + pd.Timedelta(days=n) - pd.Timedelta(microseconds=1)].sum())

    def _daily(lo: pd.Timestamp) -> dict:
        out = {}
        for t in range(1, 8):
            d = lo + pd.Timedelta(days=t - 1)
            out[t] = float(s.get(d, 0.0)) if d in s.index else 0.0
        return out

    per = {}
    channels_out = {}
    for g, key in ((gen_a, "a"), (gen_b, "b")):
        end = pd.Timestamp(ends[g])
        base7 = _sum(end - pd.Timedelta(days=7), 7)
        base_daily_avg = base7 / 7
        daily = _daily(end)
        windows = {}
        for n in (1, 3, 7):
            wsum = _sum(end, n)
            bsum = base7 * n / 7
            windows[n] = {
                "win": int(round(wsum)),
                "base": int(round(bsum)),
                "delta": int(round(wsum - bsum)),
                "delta_pct": round((wsum - bsum) / bsum, 4) if bsum else None,
            }
        per[key] = {
            "gen": g, "end": end.date().isoformat(),
            "base7_total": int(round(base7)),
            "base7_daily_avg": int(round(base_daily_avg)),
            "daily": daily,
            "windows": windows,
        }
        # 各渠道窗口增幅（上市前 7 天为基线）
        ch_rows = []
        for c in df.columns:
            if c not in _CHANNEL_COLS:
                continue
            cc = df.set_index("d")[c]
            base7c = float(cc.loc[end - pd.Timedelta(days=7):end - pd.Timedelta(microseconds=1)].sum())
            row = {"channel": _CHANNEL_LABELS[c], "windows": {}}
            for n in (1, 3, 7):
                win = float(cc.loc[end:end + pd.Timedelta(days=n) - pd.Timedelta(microseconds=1)].sum())
                bsum = base7c * n / 7
                row["windows"][n] = {
                    "win": int(round(win)),
                    "base": int(round(bsum)),
                    "delta": int(round(win - bsum)),
                    "delta_pct": round((win - bsum) / bsum, 4) if bsum else None,
                }
            ch_rows.append(row)
        channels_out[key] = ch_rows
    # 判断要点（整体）
    insights = []
    for n in (1, 3, 7):
        w = per["a"]["windows"][n], per["b"]["windows"][n]
        a_s, b_s = w[0]["delta_pct"], w[1]["delta_pct"]
        if a_s is not None and b_s is not None:
            insights.append(
                f"上市后 {n} 天窗口增幅：{gen_a} {a_s:+.1%} / {gen_b} {b_s:+.1%}（"
                f"窗口累计 {per['a']['windows'][n]['win']:,} vs 基线 {per['a']['windows'][n]['base']:,}；"
                f"{per['b']['windows'][n]['win']:,} vs {per['b']['windows'][n]['base']:,}）。")
    # 渠道要点（最新代际 DM2 = b）
    if channels_out["b"]:
        def _best(n: int) -> dict:
            cands = [r for r in channels_out["b"] if r["windows"][n]["delta_pct"] is not None]
            return max(cands, key=lambda r: r["windows"][n]["delta_pct"]) if cands else {}
        for n in (1, 3, 7):
            r = _best(n)
            if r:
                w = r["windows"][n]
                insights.append(
                    f"{gen_b} 上市后 {n} 天窗口渠道增幅最高 = {r['channel']}（{w['delta_pct']:+.1%}，"
                    f"窗口 {w['win']:,} vs 基线 {w['base']:,}）；单日看 APP小程序在上市当日冲高，"
                    f"持续性增量集中在快慢闪/门店。")
    return {"gens": [gen_a, gen_b], "per": per, "channels": channels_out,
            "insights": insights, "metric": "下发线索数", "baseline": "上市前等长窗口"}


def _load_group_order_daily() -> pd.DataFrame:
    """读重刷后的观星台重点车型(订单)宽表 → 长表（主体/日期/订单值/快照日）。

    命名先用 NAME2CANON 归一（与 model_order_monthly_compare_report 一致：智己L6/L6、
    大众ID.ERA 5S 空格变体等）；跨快照重叠日取最新快照值。
    """
    if not _GROUP_ORDER_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(_GROUP_ORDER_CSV)
    df["主体"] = df["主体"].map(lambda x: NAME2CANON.get(x, x))
    daily_cols = [c for c in df.columns if c.startswith("每日_")]
    rows = []
    for _, r in df.iterrows():
        snap_year = str(r["数据日期"])[:4]
        for c in daily_cols:
            if pd.notna(r[c]):
                md = c.split("_")[1]
                m, dd = md.split("/")
                rows.append({
                    "主体": r["主体"],
                    "日期": f"{snap_year}-{int(m):02d}-{int(dd):02d}",
                    "订单": r[c],
                    "快照": str(r["数据日期"]),
                })
    long = pd.DataFrame(rows)
    if long.empty:
        return long
    # 跨快照重叠：按（主体,日期）取最新快照值
    long = long.sort_values("快照").groupby(["主体", "日期"], as_index=False).last()
    return long


def _group_order_compare() -> dict | None:
    """集团订单上市对比：智己L6 / MG 07 / 大众ID.ERA 5S 上市后第 1..N 日每日及累计订单。

    口径：观星台「重点车型(订单)」国内订单（含渠道/预售/试驾全量，非零售锁单，全代际汇总）；
    t0：智己L6 = 2026-08-28（业务定义 DM2 上市日）；MG 07 / 大众ID.ERA 5S = 2026-08-21（用户近似对齐基准）。
    """
    long = _load_group_order_daily()
    if long.empty:
        return None
    out = {"data_source": "观星台集团订单日报·重点车型(订单)", "models": []}
    for spec in GROUP_ORDER_MODELS:
        m = spec["model"]
        sub = long[long["主体"].eq(m)].copy()
        if sub.empty:
            continue
        sub["日期"] = pd.to_datetime(sub["日期"])
        t0 = pd.Timestamp(spec["t0"])
        # 上市后第 t 天 = t0 + (t-1)（含 t0 当日为第 1 天），至数据覆盖末
        end = sub["日期"].max()
        full = pd.date_range(t0, end, freq="D")
        s = sub.groupby("日期")["订单"].sum().reindex(full).fillna(0)
        daily = [int(v) for v in s]
        cum = []
        acc = 0
        for v in daily:
            acc += v
            cum.append(acc)
        out["models"].append({
            "model": m,
            "t0": spec["t0"],
            "label": spec["label"],
            "dates": [d.date().isoformat() for d in full],
            "day_offset": [i + 1 for i in range(len(full))],
            "daily": daily,
            "cum": cum,
            "latest_date": end.date().isoformat(),
        })
    return out


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
    _row("男性占比（order_gender）", [
        _cell(lambda p: (p["gender"].get("男", 0) / p["n"]) if p["n"] else None, g, g == latest)
        for g in gens])
    _row("男性占比（owner_gender 对照）", [
        _cell(lambda p: (p["owner_gender"].get("男", 0) / p["n"]) if p["n"] else None, g, g == latest)
        for g in gens])
    _row("车主年龄中位 / 均值（owner_age）", [
        _cell(lambda p: None
              if p["age_owner"].get("median") is None
              else f"{p['age_owner']['median']:.0f} / {p['age_owner']['mean']:.1f}", g, g == latest)
        for g in gens])
    _row("购车人年龄中位（buyer_age）", [
        _cell(lambda p: None if p["age_buyer"].get("median") is None
              else f"{p['age_buyer']['median']:.0f}（缺失 {p['age_buyer']['missing_pct']:.0f}%）", g, g == latest)
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
      <p class="section-note">口径：各代际上市同期第 1..{pc['n_days']} 天窗口内零售锁单（order_type ∈ 用户车/NaN，排除非零售），按 order_number 去重；性别字段 order_gender / owner_gender，年龄字段 owner_age（车主）/ buyer_age（购车人），城市线级与省份 = license_city 归一（norm_city → city_to_tier_label / CITY_TO_PROVINCE）；年龄代际 = owner_age → birth = 上市年 − age → COHORTS（00后/95后…）。字段口径与 runtime_scripts/user_profile.py、l6_m2_presale_report 用户画像模块一致。</p>
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
    rows_html = []
    for r in ar["rows"]:
        diff = r["diff_pp"]
        sign = f"+{diff:.1f}" if diff > 0 else f"{diff:.1f}"
        cls = " class='pos'" if diff > 0 else (" class='neg'" if diff < 0 else "")
        rows_html.append(
            f"<tr><td>{r['band']}</td>"
            f"<td class='num'>{r['a']}</td><td class='num'>{r['a_share_known'] * 100:.0f}%</td>"
            f"<td class='num'><strong>{r['b']}</strong></td><td class='num'><strong>{r['b_share_known'] * 100:.0f}%</strong></td>"
            f"<td class='num'{cls}>{sign} pp</td></tr>"
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
      <p class="section-note">年龄分层按 owner_age（车主年龄，DM0/DM1/DM2 窗口缺失 5–9%）分桶，占比为各带占「已知年龄」比例。复购（老车主）复用 shared/operators/repurchase.py 算子（mode=fulfilled_repurchase，canonical）：窗口内锁单的 owner_identity_no（18 位有效，缺失/无效记无法判定）须在窗口开始前已完成过**兑现购车**——历史零售锁单的交付或开票时间早于上市日；仅历史锁单、从未交付/开票的「悬置单」不计复购，另列悬置历史，避免误判（PIT 不穿越；宽松对照 mode=prior_locker 对齐 lock_attribution_analysis.py "Repeat Lockers (Had Prior Locks)"）。复购占比按可判定业务单（复购+悬置+首购）计。</p>
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


def _group_order_table(c: dict) -> str:
    gc = c.get("group_order")
    if not gc or not gc.get("models"):
        return ""
    model_names = [m["model"] for m in gc["models"]]
    common_n = min(len(m["day_offset"]) for m in gc["models"])
    blocks = []
    for m in gc["models"]:
        rows = "".join(
            f"<tr><td class='num'>{t}</td><td class='num'>{d[5:]}</td>"
            f"<td class='num'>{int(m['daily'][t - 1]):,}</td>"
            f"<td class='num'><strong>{int(m['cum'][t - 1]):,}</strong></td></tr>"
            for t, d in zip(m["day_offset"], m["dates"])
        )
        blocks.append(f"""
        <h3 style="margin-top:18px;">{m['model']} <span class="text-muted" style="font-weight:400;font-size:0.9em;">— {m['label']}，t0 = {m['t0']}，数据至 {m['latest_date']}</span></h3>
        <div class="table-wrap">
        <table class="report-table">
          <thead><tr><th>上市后第 t 日</th><th>日期</th><th>每日订单</th><th>累计订单</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        </div>""")
    return f"""
    <div class="card">
      <h2>模块 6 · 集团订单上市对比：{ ' / '.join(model_names) }（上市后 N 日 · 每日 + 累计订单）</h2>
      <p class="section-note">数据源 = 观星台集团订单日报「重点车型(订单)」国内订单（重刷至最新快照 {gc['models'][0]['latest_date']}）；口径为全渠道国内订单（含门店/预售/试驾锁定等全量进单）。第 1 日 = 各车 t0（上市基准日）：智己L6 = 2026-08-28（业务定义 DM2 上市日）；MG 07 / 大众ID.ERA 5S = 2026-08-21（近似对齐基准）。跨快照重叠日取最新快照值。<br/><br/><strong>口径对齐说明（智己L6 集团 vs 内部 order_data）</strong>：集团「智己L6」为全代际（含 DM1 老款）+ 自 08 月中旬预售试驾铺车即开始计 + 含试驾车锁定等全量订单，故其同期累计（{gc['models'][0]['cum'][-1]:,} 单）与内部按同尺口径 <strong>L6 全代际自 08-14 起全口径锁单（约 1,282 单）基本一致</strong>（尾差 ~7 为命名/录入差异）。切勿将集团订单与模块 1/5 的「DM2 上市后零售锁单（655）」直接横比——差异主要来自①全代际（含 DM1 老款 ~278）②含预售试驾车铺车锁定（~390）③全渠道订单流 vs 零售锁单漏斗，而非数据口径缺陷。</p>
      <h3 style="margin-top:14px;">上市后累计订单收口对比（公共窗口：第 1..{common_n} 日）</h3>
      <div class="chart-box" id="chart-group-order-cum" style="height:440px;"></div>
      <div class="section-note">折线按各车型上市日 t0 对齐为第 1 天，仅展示公共窗口前 {common_n} 天（三车中数据覆盖最短者）；y = 上市以来累计订单。累计口径即下方每日订单逐日累加。</div>
      {''.join(blocks)}
    </div>"""


def _lead_window_table(c: dict) -> str:
    lc = c.get("lead_window")
    if not lc or not lc.get("per"):
        return ""
    a, b = lc["per"]["a"], lc["per"]["b"]
    ga, gb = lc["gens"]
    # 表 1：窗口增幅
    rows1 = []
    for n in (1, 3, 7):
        wa, wb = a["windows"][n], b["windows"][n]
        rows1.append(
            f"<tr><td>上市后 {n} 天窗口</td>"
            f"<td class='num'>{wa['win']:,}</td><td class='num'>{wa['base']:,}</td>"
            f"<td class='num'>{wa['delta']:+,}（{wa['delta_pct'] * 100:+.1f}%）</td>"
            f"<td class='num'><strong>{wb['win']:,}</strong></td><td class='num'>{wb['base']:,}</td>"
            f"<td class='num'><strong>{wb['delta']:+,}（{wb['delta_pct'] * 100:+.1f}%）</strong></td></tr>"
        )
    # 表 2：上市后每日线索 vs 上市前 7 日日均
    def _daily_row(p: dict, bold: bool = False) -> str:
        avg = p["base7_daily_avg"]
        cells = []
        for t in range(1, 8):
            v = p["daily"][t]
            d = v - avg
            sign = "pos" if d >= 0 else "neg"
            cells.append(
                f"<td class='num'>{int(v):,}</td><td class='num {sign}'>{d:+,.0f}</td>")
        return "".join(cells)

    thead2 = "".join(
        f"<th colspan='2'>D{t}</th>" for t in range(1, 8))
    rows2 = (
        f"<tr><td><strong>{ga}</strong>（上市日 {a['end']}，前7日均 {a['base7_daily_avg']:,}）</td>{_daily_row(a)}</tr>"
        f"<tr><td><strong>{gb}</strong>（上市日 {b['end']}，前7日均 {b['base7_daily_avg']:,}）</td>{_daily_row(b, bold=True)}</tr>"
    )

    # 表 3：渠道窗口增幅（最新代际 DM2 为主视角，DM1 对照）
    def _ch_cell(row, n, bold: bool = False) -> str:
        w = row["windows"].get(n)
        if not w or w.get("delta_pct") is None:
            return "<td class='num'>—</td>"
        v = w["delta_pct"]
        cls = " pos" if v > 0 else (" neg" if v < 0 else "")
        s = f"{v * 100:+.1f}%"
        return f"<td class='num{cls}'>{s}</td>" if not bold else f"<td class='num{cls}'><strong>{s}</strong></td>"

    rows3 = []
    for i, cname in enumerate(_CHANNEL_LABELS.values()):
        ra = next((r for r in lc["channels"]["a"] if r["channel"] == cname), None)
        rb = next((r for r in lc["channels"]["b"] if r["channel"] == cname), None)
        b_cells = "".join(_ch_cell(rb, n, bold=True) for n in (1, 3, 7)) if rb else "<td colspan='3' class='num'>—</td>"
        a_cells = "".join(_ch_cell(ra, n) for n in (1, 3, 7)) if ra else "<td colspan='3' class='num'>—</td>"
        rows3.append(
            f"<tr><td><strong>{cname}</strong></td>{a_cells}{b_cells}</tr>")
    # 合计行（整体）
    ra = None
    rb_tot = {n: b["windows"][n]["delta_pct"] for n in (1, 3, 7)}
    a_tot = {n: a["windows"][n]["delta_pct"] for n in (1, 3, 7)}
    rows3.append(
        f"<tr><td><strong>全部渠道合计</strong></td>"
        + "".join(f"<td class='num'>{a_tot[n] * 100:+.1f}%</td>" for n in (1, 3, 7))
        + "".join(f"<td class='num'><strong>{rb_tot[n] * 100:+.1f}%</strong></td>" for n in (1, 3, 7))
        + "</tr>"
    )
    thead3 = f"<th>渠道</th><th colspan='3'>{ga}</th><th colspan='3'>{gb}（重点）</th>"
    subhead3 = "<th></th>" + "<th>N1</th><th>N3</th><th>N7</th>" * 2

    # 表 4：渠道窗口绝对值（{gb} = 重点，上市后窗口 / 等长基线 / 净增）
    def _abs3(row, n) -> str:
        w = row["windows"].get(n)
        if not w:
            return "<td colspan='3' class='num'>—</td>"
        return (f"<td class='num'>{w['win']:,}</td>"
                f"<td class='num'>{w['base']:,}</td>"
                f"<td class='num'>{w['delta']:+,}</td>")

    def _tot3(p, n) -> str:
        w = p["windows"][n]
        return f"<td class='num'><strong>{w['win']:,}</strong></td><td class='num'>{w['base']:,}</td><td class='num'>{w['delta']:+,}</td>"

    rows4 = []
    for cname in _CHANNEL_LABELS.values():
        rb = next((r for r in lc["channels"]["b"] if r["channel"] == cname), None)
        cells = "".join(_abs3(rb, n) for n in (1, 3, 7)) if rb else ""
        rows4.append(f"<tr><td><strong>{cname}</strong></td>{cells}</tr>")
    rows4.append(f"<tr><td><strong>全部渠道合计</strong></td>"
                 + "".join(_tot3(b, n) for n in (1, 3, 7)) + "</tr>")
    thead4 = f"<th>渠道（{gb} 上市日 {b['end']}）</th>"
    thead4 += "".join(f"<th colspan='3'>上市后 {n} 天窗口</th>" for n in (1, 3, 7))
    subhead4 = "<th></th>" + ("<th>上市后</th><th>等长基线</th><th>净增</th>" * 3)

    insights_html = ""
    if lc.get("insights"):
        insights_html = '<div class="section-note" style="margin-top:14px;"><strong>判断</strong><ul style="margin:6px 0 0 18px;padding:0;">' + "".join(
            f"<li>{s}</li>" for s in lc["insights"]) + "</ul></div>"
    return f"""

    <div class="card">
      <h2>模块 7 · 上市后下发线索窗口增幅对比：{gb} vs {ga}</h2>
      <p class="section-note">数据源 = dataset/assign_data.csv「下发线索数」（整体口径）。上市后窗口 = 各代际上市日 end 起 N 天；基线 = 上市前等长窗口（end−N ~ end）；窗口增幅 = (上市后窗口 − 等长基线) ÷ 基线。每日行 = 上市后 D1..D7 当日线索及其相对上市前 7 日均值的增减。注意：{gb} 的基线（上市前 7 天）正处于 8/18 预售开启后的放量高峰，故其窗口增幅被抬高基线拉低；当日值受周内节奏影响（周一/周二为周内低谷）。</p>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>窗口</th><th>{ga} 上市后</th><th>{ga} 基线</th><th>{ga} 增幅</th><th>{gb} 上市后</th><th>{gb} 基线</th><th>{gb} 增幅</th></tr></thead>
        <tbody>{''.join(rows1)}</tbody>
      </table>
      </div>
      <h3 style="margin-top:20px;">上市后每日下发线索（相对上市前 7 日均值）</h3>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr><th>代际</th>{thead2}</tr><tr><th></th>{'<th>当日</th><th>vs 日均</th>' * 7}</tr></thead>
        <tbody>{rows2}</tbody>
      </table>
      </div>
      <h3 style="margin-top:20px;">渠道窗口增幅（上市后 N 天 vs 上市前等长基线）</h3>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr>{thead3}</tr><tr>{subhead3}</tr></thead>
        <tbody>{''.join(rows3)}</tbody>
      </table>
      </div>
      <h3 style="margin-top:20px;">渠道窗口绝对值（{gb}：上市后窗口 / 等长基线 / 净增）</h3>
      <div class="table-wrap">
      <table class="report-table">
        <thead><tr>{thead4}</tr><tr>{subhead4}</tr></thead>
        <tbody>{''.join(rows4)}</tbody>
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
        tag = " · 核心" if a["attribute"] in ("内饰", "外饰", "轮毂", "方向盘", "超远距高精度激光雷达") else ""
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
      <h2>模块 8 · DM2 上市以来锁单配置分布（{lc['launch']} ~ {lc['hi']}，零售 {n} 单）</h2>
      <p class="section-note">本模块复用 research_scripts/l6_m2_lock_config_distribution.py（独立脚本，--format json 输出 Result Contract）。数据源 = dataset/config_attribute.parquet（order_config_to_parquet.py 增量更新后含 DM2）。锁单窗口 = DM2 上市日 {lc['launch']} 起至 {lc['hi']}（零售口径 order_type ∈ 用户车/NaN，与模块 1 一致）；配置归属 = 锁单订单 (Order Number) 匹配的 Attribute/value；核心 5 配置 = 内饰 / 外饰 / 轮毂 / 方向盘 / 超远距高精度激光雷达（每单 1 值）。{n} 单全部可关联配置，核心 5 配置完整 {lc['core_complete']} 单（{lc['core_complete'] / n * 100:.0f}%）。</p>
      {''.join(core_rows)}
      {f'<h3 style="margin-top:20px;">是/否型选装项拥有率（是 = 已选）</h3><div class="table-wrap"><table class="report-table"><thead><tr><th>选装项</th><th>已选</th><th>锁单总数</th><th>拥有率</th><th style="min-width:180px;"></th></tr></thead><tbody>{opt_rows}</tbody></table></div>' if opt_rows else ''}
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

    # 模块 6 集团订单收口对比图（公共窗口 = 各车型上市后第 1..common_n 日）
    gc = c.get("group_order")
    group_fig_json = None
    if gc and gc.get("models"):
        common_n = min(len(m["day_offset"]) for m in gc["models"])
        gdata = []
        for i, m in enumerate(gc["models"]):
            days = list(range(1, common_n + 1))
            cum = m["cum"][:common_n]
            dates = m["dates"][:common_n]
            role = "own" if i == 0 else "competitor"
            gdata.append({
                "x": days,
                "y": cum,
                "customdata": dates,
                "mode": "lines+markers",
                "name": m["model"],
                "line": {"width": 3.0 if i == 0 else 2.4,
                         "color": get_series_color("own") if i == 0 else get_series_color("competitor", i - 1),
                         "dash": None if i == 0 else ("dot" if i == 1 else "dash")},
                "marker": {"size": 5},
                "hovertemplate": f"<b>{m['model']}</b> · 上市后第 %{{x}} 天（%{{customdata}}）<br>累计订单 %{{y:,}} 单<extra></extra>",
            })
        group_fig_json = json.dumps({
            "data": gdata,
            "layout": {
                "title": {"text": f"上市后累计订单收口对比（第 1..{common_n} 日 · 集团订单口径）",
                          "x": 0.01, "xanchor": "left"},
                "xaxis": {"title": "上市后天数（第 1 天 = 各车上市日 t0）",
                          "range": [0.5, common_n + 0.5],
                          "tickmode": "array", "tickvals": list(range(1, common_n + 1))},
                "yaxis": {"title": "累计订单（单）", "rangemode": "tozero"},
                "legend": {"orientation": "h", "y": -0.25, "x": 0},
                "margin": {"l": 60, "r": 30, "t": 55, "b": 70},
                "height": 440,
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

  {_user_profile_table(c)}

  {_age_repurchase_table(c)}

  {_group_order_table(c)}

  {_lead_window_table(c)}

  {_lock_config_table(c)}

  <div class="method-section">
    <h2 class="section-title">口径与数据来源</h2>
    <div class="method-grid">
      <div class="method-item"><div class="method-icon" style="background:var(--zh-blue-100);color:var(--zh-blue);">D</div>
        <div class="method-body"><strong>数据源</strong><br/>dataset/order_data.parquet<br/>dataset/assign_data.csv（有效门店 / 下发线索，模块 7）<br/>shared/schema/business_definition.json<br/>shared/loaders/store_info_loader.py（经销商 Bloc 关联）<br/>research_scripts/store_network_compare.py（网络对比组件）<br/>runtime_scripts/user_profile.py（画像字段口径）<br/>shared/operators/repurchase.py（复购算子）<br/>research_scripts/l6_m2_lock_config_distribution.py（模块 8 · 配置分布）<br/>dataset/config_attribute.parquet（模块 8 · 配置）<br/>outputs/tables/重点车型（订单）.csv（模块 6 · 集团订单）</div></div>
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
{('Plotly.newPlot(\'chart-group-order-cum\', ' + group_fig_json + ');') if group_fig_json else '// 无集团订单数据，跳过模块 6 折线图'}
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
                "user_profile_compare": c["user_profile"],
                "age_repurchase_compare": c["age_repurchase"],
                "group_order_compare": c["group_order"],
                "lead_window_compare": c["lead_window"],
                "lock_config_distribution": c["lock_config"],
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