#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新车上市深度研究 — 等生命周期（D1..DN）跨代际对比引擎。

定位
----
把一个新车代际与其历史对标代际放在**各自上市后相同天数窗口**内做同口径比较，
逐层回答：卖得怎么样 → 差异为什么出现 → 差异发生在哪里 → 意味着什么。

与 `launch_cumulative_lock_compare.py` 的关系
--------------------------------------------
后者是固定框架的「上市累计对比 Basic 报告」（默认 30 天曲线 + 固定模块）。
本脚本不扩展它，而是独立的可复用研究入口：窗口由 `--gen/--as-of` 推导，
对标代际由 `--benchmarks` 显式指定，输出为「研究数据包（JSON）+ 数据表 + HTML 叙事报告」。

核心口径（全部来自 shared/schema/business_definition.json 与既有算子）
--------------------------------------------------------------------
- 代际归属：series_group_logic（product_name 判定），不按字符串猜代际
- 上市日 T0：time_periods.{gen}.end（业务定义，不从数据推断）
- 窗口：last_date = as_of（T-1，最后完整观察日）；N = (last_date - T0).days + 1
        第 d 天 = T0 + (d-1)，窗口 = [T0, T0+N) 左闭右开
- 零售锁单：lock_time 非空 COUNTD(order_number)，order_type ∈ {用户车, 空}，
            剔除 NON_RETAIL 与 flag_test_orders（总部主理店 + 假身份号）
- 预售池：intention_payment_time < T0（严格早于上市日），point-in-time 用事件时间截断
- 前向池（D_N 时点待转化）：小订已付且未退、未锁、未退大定，按事件时间重建

用法
----
  python workspace/research_scripts/launch_deep_dive.py \
      --gen LS8Neo --benchmarks CM3 LS8 --as-of 2026-11-08 \
      --format html

  python workspace/research_scripts/launch_deep_dive.py \\
      --gen LS8Neo --benchmarks CM3 LS8 --as-of 2026-11-08 --format json

  --format terminal  终端摘要 / json  Result Contract / html 完整叙事报告
  --output DIR       产物根目录（默认 workspace/outputs）
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = REPO_ROOT / "workspace"
for _p in (str(REPO_ROOT), str(_WS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.monitors.order_filter import flag_test_orders  # noqa: E402
from utils.monitors.phase import load_business_definition  # noqa: E402
from utils.monitors.series_group import apply_series_group_logic  # noqa: E402
from utils.paths import DATASET_DIR  # noqa: E402
from utils.regions import norm_region  # noqa: E402
from business_scripts.user_profile import (  # noqa: E402
    CITY_TO_PROVINCE, city_to_tier_label, norm_city,
)
from shared.loaders import store_info_loader as store_loader  # noqa: E402

BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
ORDER_PARQUET = DATASET_DIR / "order_data.parquet"
CONFIG_PARQUET = DATASET_DIR / "config_attribute.parquet"
ASSIGN_CSV = DATASET_DIR / "assign_data.csv"
TEST_DRIVE_CSV = DATASET_DIR / "test_drive_data.csv"

NON_RETAIL = {"试驾车", "大客户", "员工", "集团员工", "经销商员工", "享道",
              "仅批售", "项目", "展车", "海外"}
TIME_COLUMNS = [
    "lock_time", "intention_payment_time", "intention_refund_time",
    "deposit_payment_time", "deposit_refund_time", "apply_refund_time",
    "approve_refund_time", "actual_refund_time", "final_payment_time",
    "delivery_date", "order_create_date", "first_test_drive_time",
    "first_assign_time", "first_touch_time",
]
# 语义可比的配置属性（三车型共有）；其余为产品独有，不强制对应
CORE_ATTRS = ["外饰", "内饰", "轮毂", "方向盘", "激光雷达"]
ZONE_ORDER = ["上海区", "东区", "华中区", "北区", "西区", "华南特区", "虚拟大区", "未知"]


# ─────────────────────────── 基础工具 ───────────────────────────

# ── 上市观察口径（对齐 vehicle_sales_monitor / presale 监控） ──
# 剔除：① 测试单（总部主理店 + 非 18 位身份证）；② 总部主理店整店订单（内测/自营，
#       身份号为空时 flag_test_orders 抓不到）；③ 试驾车/员工/大客户/批售等非零售。
# 锁单口径：只保留 order_type == 用户车（"用户单零售"）。
# 小订池口径：小订期 order_type 常未回填，允许空值——否则预售池会被清空——其余同上。

def _non_user_mask(df: pd.DataFrame) -> pd.Series:
    ot = df["order_type"].fillna("").astype("string")
    return ot.isin(NON_RETAIL) | (ot.ne("") & ot.ne("用户车"))


def _hq_mask(df: pd.DataFrame) -> pd.Series:
    return df["store_name"].astype("string").eq("总部主理店")


def lock_mask(df: pd.DataFrame, bd: dict) -> pd.Series:
    """锁单口径：用户单零售（严格 用户车），剔除测试单 / 内测店 / 非零售类型。"""
    ot = df["order_type"].fillna("").astype("string")
    return (ot.eq("用户车") & ~flag_test_orders(df, bd)
            & ~_hq_mask(df) & ~_non_user_mask(df))


def pool_mask(df: pd.DataFrame, bd: dict) -> pd.Series:
    """小订池口径：允许 order_type 未回填（空），其余同锁单口径。"""
    ot = df["order_type"].fillna("").astype("string")
    return (ot.isin(["", "用户车"]) & ~flag_test_orders(df, bd)
            & ~_hq_mask(df) & ~_non_user_mask(df))


def retail_mask(df: pd.DataFrame, bd: dict) -> pd.Series:  # 兼容旧调用名
    return lock_mask(df, bd)


def exclusion_report(df: pd.DataFrame, bd: dict, win: dict) -> dict:
    """各代际的剔除量（审计用）：测试单 / 内测店 / 非零售类型 / 空类型。"""
    ot = df["order_type"].fillna("").astype("string")
    test = flag_test_orders(df, bd)
    hq = _hq_mask(df)
    out = {}
    for g, w in win["windows"].items():
        t0, hi = w["launch"], w["window_end"]
        in_win = (df["series_group_logic"].eq(g) & df["lock_time"].notna()
                  & (df["lock_time"] >= t0) & (df["lock_time"] < hi))
        pool = (df["series_group_logic"].eq(g) & df["intention_payment_time"].notna()
                & (df["intention_payment_time"] < t0 + pd.Timedelta(days=1)))
        out[g] = {
            "lock_test_orders": int(df.loc[in_win & test, "order_number"].nunique()),
            "lock_hq_orders": int(df.loc[in_win & hq & ~test, "order_number"].nunique()),
            "lock_non_retail": int(df.loc[in_win & ~hq & ~test & _non_user_mask(df),
                                   "order_number"].nunique()),
            "lock_blank_type": int(df.loc[in_win & ~hq & ~test & ot.eq(""),
                                    "order_number"].nunique()),
            "pool_test_orders": int(df.loc[pool & test, "order_number"].nunique()),
            "pool_hq_orders": int(df.loc[pool & hq & ~test, "order_number"].nunique()),
            "pool_non_retail": int(df.loc[pool & ~hq & ~test & _non_user_mask(df),
                                    "order_number"].nunique()),
            "pool_blank_type": int(df.loc[pool & ~hq & ~test & ot.eq(""),
                                    "order_number"].nunique()),
        }
    return out


def resolve_gen(bd: dict, token: str) -> str:
    """把用户输入的代际 token（LS8NEO / ls8neo / 显示名）解析成 series_group_logic 键。

    只认业务配置：先精确匹配 key，再忽略大小写匹配 key，最后匹配 model_series_mapping
    的族名或 monitor.series_labels 显示名。不做前缀/子串猜测。
    """
    token = str(token).strip()
    keys = list((bd.get("series_group_logic") or {}).keys())
    if token in keys:
        return token
    low = {k.lower(): k for k in keys}
    if token.lower() in low:
        return low[token.lower()]
    labels = (bd.get("monitor") or {}).get("series_labels") or {}
    for k, v in labels.items():
        if token == v:
            return k
    raise SystemExit(
        f"无法解析代际 '{token}'：不在 series_group_logic 键 {keys} 中，"
        f"也不是已知显示名 {list(labels.values())}"
    )


def launch_day(bd: dict, gen: str) -> pd.Timestamp:
    tp = (bd.get("time_periods") or {}).get(gen) or {}
    if not tp.get("end"):
        raise SystemExit(f"business_definition.time_periods.{gen}.end 缺失，无法确定上市日")
    return pd.Timestamp(tp["end"]).normalize()


def presale_start_day(bd: dict, gen: str) -> pd.Timestamp | None:
    tp = (bd.get("time_periods") or {}).get(gen) or {}
    return pd.Timestamp(tp["start"]).normalize() if tp.get("start") else None


def _fmt_int(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{int(round(float(v))):,}"


def _pct(x: float | None, digits: int = 1) -> float | None:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    return round(float(x) * 100, digits)


def _vc(series: pd.Series, digits: int = 4) -> dict:
    """value_counts → dict，按 (-计数, 键) 排序，保证跨进程可复现（不依赖 set/hash 顺序）。"""
    vc = series.value_counts()
    items = sorted(vc.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))
    return {str(k): (int(v) if digits is None else round(float(v), digits)) for k, v in items}


def _norm_zone(name) -> str:
    """大区两级架构归一到一级大区：东区-江苏 → 东区。"""
    r = norm_region(name)
    if r in ("未知", "虚拟大区", "上海区", "华南特区"):
        return r
    return r.split("-")[0]


def load_orders(bd: dict) -> pd.DataFrame:
    cols = ["order_number", "product_name", "series", "parent_region_name",
            "store_name", "store_city", "license_city", "order_type",
            "order_gender", "owner_gender", "buyer_age", "owner_age",
            "buyer_identity_no", "owner_identity_no"] + TIME_COLUMNS
    df = pd.read_parquet(ORDER_PARQUET, columns=cols)
    for c in TIME_COLUMNS:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df = apply_series_group_logic(df, bd)
    return df


# ─────────────────────────── 时间窗口 ───────────────────────────

def build_windows(bd: dict, gens: list[str], as_of: pd.Timestamp) -> dict:
    """统一生命周期窗口：主代际 N 天，所有对标代际只取自身前 N 天。"""
    main = gens[0]
    t0 = launch_day(bd, main)
    intended = int((as_of.normalize() - t0).days) + 1
    if intended <= 0:
        raise SystemExit(f"as-of {as_of.date()} 早于 {main} 上市日 {t0.date()}，窗口无效")

    # 等窗口上限：任一参照代际的上市日若晚于主代际，其自身可观察天数可能不足 N 天。
    # 此时按「所有代际都能覆盖的最大等长天数」收窗，绝不把缺失日期补零。
    avail = {}
    for g in gens:
        la = launch_day(bd, g)
        avail[g] = max(int((as_of.normalize() - la).days) + 1, 0)
    n_days = min([intended] + [v for v in avail.values() if v > 0])
    if n_days <= 0:
        raise SystemExit("至少一个代际在 as-of 之前无可用窗口，无法等窗口比较")
    capped = n_days < intended

    out = {}
    for g in gens:
        la = launch_day(bd, g)
        out[g] = {
            "gen": g,
            "launch": la,
            "n_days": n_days,
            "n_days_intended": intended,
            "available_days": avail[g],
            "window_end": la + pd.Timedelta(days=n_days),  # 左闭右开
            "presale_start": presale_start_day(bd, g),
            "weekdays": [d.strftime("%a") for d in pd.date_range(la, periods=n_days)],
        }
    return {"main": main, "n_days": n_days, "n_days_intended": intended,
            "window_capped": capped, "as_of": as_of.normalize(),
            "last_date": as_of.normalize(), "gens": gens, "windows": out}


# ─────────────────────────── 模块 1/2/3：曲线、差额、动能 ───────────────────────────

def compute_curves(df: pd.DataFrame, win: dict) -> dict:
    """每日新增 / 累计锁单（D1..DN），以及相对两个对标的累计差额与边际差额。"""
    n = win["n_days"]
    curves: dict[str, dict] = {}
    for g, w in win["windows"].items():
        lo, hi = w["launch"], w["window_end"]
        sub = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
                 & (df["lock_time"] >= lo) & (df["lock_time"] < hi)]
        daily = (sub.groupby(sub["lock_time"].dt.normalize())["order_number"]
                 .nunique().reindex(pd.date_range(lo, hi - pd.Timedelta(days=1)),
                                    fill_value=0).astype(int))
        curves[g] = {
            "gen": g,
            "launch": lo.date().isoformat(),
            "dates": [d.date().isoformat() for d in daily.index],
            "weekdays": w["weekdays"],
            "daily": [int(v) for v in daily.values],
            "cum": [int(v) for v in daily.cumsum().values],
        }

    main = win["main"]
    m = curves[main]
    gaps = {}
    for g in win["gens"]:
        if g == main:
            continue
        b = curves[g]
        cum_gap, marg = [], []
        for d in range(n):
            gd = m["cum"][d] - b["cum"][d]
            cum_gap.append(int(gd))
            marg.append(int(gd - cum_gap[d - 1]) if d else int(gd))
        gaps[g] = {"gen": g, "cum_gap": cum_gap, "marginal": marg}
    return {"curves": curves, "gaps": gaps, "n_days": n, "main": main,
            "gens": win["gens"],
            "benchmarks": [g for g in win["gens"] if g != main]}


def compute_dynamics(curves: dict) -> dict:
    """新增动能：D1 爆发、D2..DN 稳态、衰减率、稳定性、逐日环比。"""
    out = {}
    for g, c in curves["curves"].items():
        daily = c["daily"]
        n = len(daily)
        d1 = daily[0] if daily else 0
        tail = daily[1:] or [0]
        tail_avg = sum(tail) / len(tail)
        tail_cv = (pd.Series(tail).std(ddof=0) / tail_avg) if tail_avg else None
        out[g] = {
            "gen": g,
            "d1": int(d1),
            "d1_share_of_cum": round(d1 / c["cum"][-1], 4) if c["cum"][-1] else None,
            "tail_days": n - 1,
            "tail_avg": round(tail_avg, 1),
            "tail_min": int(min(tail)),
            "tail_max": int(max(tail)),
            "d2_over_d1": round(tail[0] / d1, 4) if d1 else None,
            "tail_cv": round(float(tail_cv), 3) if tail_cv is not None else None,
            "slope_tail": round((tail[-1] - tail[0]) / (len(tail) - 1), 1) if len(tail) > 1 else None,
            "cum_total": int(c["cum"][-1]),
            "cum_avg_per_day": round(c["cum"][-1] / n, 1) if n else None,
            "weekday_profile": dict(zip(c["weekdays"], c["daily"])),
        }
    main = curves["main"]
    for g in curves["benchmarks"]:
        out[g]["vs_main_tail_ratio"] = (round(out[main]["tail_avg"] / out[g]["tail_avg"], 3)
                                        if out[g]["tail_avg"] else None)
        out[g]["vs_main_d1_ratio"] = (round(out[main]["d1"] / out[g]["d1"], 3)
                                      if out[g]["d1"] else None)
    return out


def compute_context_curves(df: pd.DataFrame, win: dict, context_days: int = 30) -> dict:
    """D1..D_context 参考曲线（**仅用于展示释放形状，不参与任何差异计算**）。

    历史代际在本研究的正式口径中只允许用前 N 天；本函数按 --context-days 额外
    取 D1..D_context（受数据截止限制自动截断），供报告 Q1 的参考延长线使用。
    该数据不进入 deltas / gaps / 分解，也不产生任何跨代际结论。
    """
    out: dict[str, dict] = {}
    if context_days <= 0:
        return {"context_days": 0, "curves": out}
    last = win["last_date"]
    for g, w in win["windows"].items():
        lo = w["launch"]
        hi = min(lo + pd.Timedelta(days=context_days), last + pd.Timedelta(days=1))
        avail = max(int((hi - lo).days), 0)
        if avail <= 0:
            out[g] = {"gen": g, "launch": lo.date().isoformat(),
                      "available_days": 0, "dates": [], "daily": [], "cum": []}
            continue
        sub = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
                 & (df["lock_time"] >= lo) & (df["lock_time"] < hi)]
        daily = (sub.groupby(sub["lock_time"].dt.normalize())["order_number"]
                 .nunique().reindex(pd.date_range(lo, periods=avail),
                                    fill_value=0).astype(int))
        cum = daily.cumsum().astype(int)
        out[g] = {
            "gen": g,
            "launch": lo.date().isoformat(),
            "available_days": avail,
            "dates": [d.date().isoformat() for d in daily.index],
            "daily": [int(v) for v in daily.values],
            "cum": [int(v) for v in cum.values],
        }
    return {"context_days": context_days, "curves": out}


def compute_launch_night(df: pd.DataFrame, win: dict) -> dict:
    """D1 上市夜对齐口径：各代际均取上市日 20:00–24:00（排除开盘时刻差异）。

    业务定义中 launch_open_minute_by_series 给出各代际首笔锁单分钟（20:0x–20:5x），
    LS8Neo 上市日首笔锁单在 19:44（早于 20:00），因此额外给出「当日全时段」对照。
    """
    out = {}
    for g, w in win["windows"].items():
        lo = w["launch"] + pd.Timedelta(hours=20)
        hi = w["launch"] + pd.Timedelta(days=1)
        sub = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
                 & (df["lock_time"] >= lo) & (df["lock_time"] < hi)]
        day = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
                 & (df["lock_time"] >= w["launch"]) & (df["lock_time"] < hi)]
        first = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
                   & (df["lock_time"] >= w["launch"])]["lock_time"]
        out[g] = {
            "gen": g,
            "night_2000_2400": int(sub["order_number"].nunique()),
            "day_total": int(day["order_number"].nunique()),
            "first_lock": first.min().strftime("%Y-%m-%d %H:%M") if len(first) else None,
            "hourly": {int(k): int(v) for k, v in
                       day.groupby(day["lock_time"].dt.hour)["order_number"].nunique().items()},
        }
    return out


# ─────────────────────────── 模块 4/5/9/10：预售池、来源分解、订单质量、前向池 ───────────────────────────

def compute_presale_pool(df: pd.DataFrame, win: dict) -> dict:
    """预售需求池 → 上市后 D_N 转化结果（统一截止到上市后第 N 天）。

    池 = intention_payment_time ∈ [T0 - 预售天数, T0) 的小订（严格早于上市日）；
    上市当日（T0 至 T0+24h）支付的小订单列为「上市当日新增小订」，不与预售池混算。
    """
    out = {}
    for g, w in win["windows"].items():
        t0, cutoff = w["launch"], w["window_end"]
        pre_start = w["presale_start"] or t0
        s = df[df["series_group_logic"].eq(g)]

        ip = s["intention_payment_time"]
        pre = s[ip.notna() & (ip < t0)]
        launch = s[ip.notna() & (ip >= t0) & (ip < t0 + pd.Timedelta(days=1))]
        post = s[ip.notna() & (ip >= t0 + pd.Timedelta(days=1)) & (ip < cutoff)]
        nopay = s[ip.isna()]

        def _cnt(x, ts_col, strict=True):
            ts = x[ts_col]
            return int((ts.notna() & ((ts < cutoff) if strict else (ts <= cutoff))).sum())

        def _locked(x):
            ts = x["lock_time"]
            return int((ts.notna() & (ts < cutoff)).sum())

        pre_locked = _locked(pre)
        pre_refunded = _cnt(pre, "intention_refund_time")
        pre_retained = len(pre) - pre_refunded
        launch_refunded = _cnt(launch, "intention_refund_time")

        out[g] = {
            "gen": g,
            "presale_start": pre_start.date().isoformat(),
            "launch": t0.date().isoformat(),
            "presale_days": int((t0 - pre_start).days),
            "pool_total": int(len(pre)),
            "pool_refunded": pre_refunded,
            "pool_retained": int(pre_retained),
            "pool_locked": pre_locked,
            "pool_pending": int(pre_retained - pre_locked),
            "pool_deposit_not_locked": int((
                pre["deposit_payment_time"].notna()
                & (pre["deposit_payment_time"] < cutoff)
                & ~(pre["lock_time"].notna() & (pre["lock_time"] < cutoff))
                & ~(pre["intention_refund_time"].notna()
                    & (pre["intention_refund_time"] < cutoff))
                & ~(pre["deposit_refund_time"].notna()
                    & (pre["deposit_refund_time"] < cutoff))).sum()),
            "pool_lock_rate": round(pre_locked / len(pre), 4) if len(pre) else None,
            "pool_refund_rate": round(pre_refunded / len(pre), 4) if len(pre) else None,
            "pool_retain_rate": round(pre_retained / len(pre), 4) if len(pre) else None,
            "launch_intent_total": int(len(launch)),
            "post_launch_intent_total": int(len(post)),
            "launch_intent_locked": _locked(launch),
            "launch_intent_refunded": launch_refunded,
            "nopay_orders": int(len(nopay)),
            "nopay_locked": _locked(nopay),
            "presale_daily": {d.date().isoformat(): int(v) for d, v in
                              pre.groupby(pre["intention_payment_time"].dt.normalize())
                              .size().items()} if len(pre) else {},
        }
        days = max(int((t0 - pre_start).days), 1)
        daily = out[g]["presale_daily"]
        first_day = daily.get(pre_start.date().isoformat(), 0)
        pre_open = int((pre["intention_payment_time"] < pre_start).sum())
        rest = int(len(pre) - pre_open - first_day)
        rest_days = max(days - 1, 1)
        total_obs = days + int(win["n_days"])
        out[g].update({
            "pool_per_presale_day": round(len(pre) / days, 1),
            "net_retained_per_presale_day": round(pre_retained / days, 1),
            "presale_day1": int(first_day),
            "presale_pre_open": pre_open,
            "pool_rest": rest,
            "rest_days": rest_days,
            "rest_daily_avg": round(rest / rest_days, 1),
            "presale_day1_share": round(first_day / len(pre), 4) if len(pre) else None,
            "launch_intent_per_day": round(len(launch) / int(win["n_days"]), 1),
            "total_intent_per_obs_day": round((len(pre) + len(launch)) / total_obs, 1),
            "net_retained_per_obs_day": round(
                (pre_retained + len(launch) + len(post) - launch_refunded) / total_obs, 1),
            "obs_days": total_obs,
        })
        # 小订池口径（业务定义：上市日 24:00 后停止收小订）→ 池 = 预售 + 上市日
        stock = s[ip.notna() & (ip < t0 + pd.Timedelta(days=1))]
        st_locked = int((stock["lock_time"].notna() & (stock["lock_time"] < cutoff)).sum())
        st_refund = int((stock["intention_refund_time"].notna()
                         & (stock["intention_refund_time"] < cutoff)).sum())
        refund_daily = (stock[stock["intention_refund_time"].notna()
                              & (stock["intention_refund_time"] < cutoff)]
                        .groupby(stock["intention_refund_time"].dt.normalize()).size()
                        .reindex(pd.date_range(t0, cutoff - pd.Timedelta(days=1)),
                                 fill_value=0).astype(int))
        out[g].update({
            "stock_total": int(len(stock)),
            "stock_presale": int(len(stock) - (ip.notna()
                                               & (ip >= t0)
                                               & (ip < t0 + pd.Timedelta(days=1))).sum()),
            "stock_launch_day": int((ip.notna() & (ip >= t0)
                                     & (ip < t0 + pd.Timedelta(days=1))).sum()),
            "stock_locked": st_locked,
            "stock_refunded": st_refund,
            "stock_remaining": int(len(stock) - st_locked - st_refund),
            "stock_locked_rate": round(st_locked / len(stock), 4) if len(stock) else None,
            "stock_refund_rate": round(st_refund / len(stock), 4) if len(stock) else None,
            "stock_remaining_rate": (round((len(stock) - st_locked - st_refund) / len(stock), 4)
                                     if len(stock) else None),
            "refund_daily": [int(v) for v in refund_daily.values],
        })

    # 池累积分解：首日爆发 / 首日后日均 / 预售期长度（反事实：按对标预售天数累积）
    main = win["main"]
    for b in [g for g in win["gens"] if g != main]:
        pm, pb = out[main], out[b]
        cf = pm["presale_day1"] + max(pb["presale_days"] - 1, 1) * pm["rest_daily_avg"]
        pm.setdefault("buildup_vs", {})[b] = {
            "bench": b,
            "pool_diff": pm["pool_total"] - pb["pool_total"],
            "day1_diff": pm["presale_day1"] - pb["presale_day1"],
            "days_diff": pm["presale_days"] - pb["presale_days"],
            "rest_rate_diff": round(pm["rest_daily_avg"] - pb["rest_daily_avg"], 1),
            "duration_effect": round((pm["presale_days"] - pb["presale_days"])
                                     * pb["rest_daily_avg"], 1),
            "rate_effect": round(pm["rest_days"]
                                 * (pm["rest_daily_avg"] - pb["rest_daily_avg"]), 1),
            "pool_if_bench_duration": int(round(cf)),
            "duration_share_of_gap": (round(((pm["presale_days"] - pb["presale_days"])
                                             * pb["rest_daily_avg"]) / (pm["pool_total"]
                                                                        - pb["pool_total"]), 4)
                                      if pm["pool_total"] != pb["pool_total"] else None),
            "day1_share_of_gap": (round((pm["presale_day1"] - pb["presale_day1"])
                                        / (pm["pool_total"] - pb["pool_total"]), 4)
                                  if pm["pool_total"] != pb["pool_total"] else None),
        }
    return out


def compute_origin_split(df: pd.DataFrame, win: dict) -> dict:
    """窗口内零售锁单按来源精确三分：预售小订转锁 / 上市当日新增小订转锁 / 直接锁单。

    小订在上市日 24:00 停收（业务定义），因此：
      预售        = intention_payment_time < T0
      上市当日新增 = T0 <= intention_payment_time < T0 + 1 天
      直接锁单    = 无 intention_payment_time（跳过小订）
    另有极少数小订晚于上市日 24:00（数据残余，各代际 2–4 单），单列为 post_launch，
    不计入上述三类，避免把口径外样本混进主口径。
    """
    out = {}
    for g, w in win["windows"].items():
        t0, hi = w["launch"], w["window_end"]
        day_end = t0 + pd.Timedelta(days=1)
        s = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
               & (df["lock_time"] >= t0) & (df["lock_time"] < hi)]
        if not len(s):
            out[g] = {"gen": g, "total": 0}
            continue
        ip = s["intention_payment_time"]
        pre = s[ip.notna() & (ip < t0)]
        launch_day = s[ip.notna() & (ip >= t0) & (ip < day_end)]
        post = s[ip.notna() & (ip >= day_end)]
        nopay = s[ip.isna()]
        total = int(s["order_number"].nunique())
        by_day = {}
        for d, grp in s.groupby(s["lock_time"].dt.normalize()):
            gip = grp["intention_payment_time"]
            by_day[d.date().isoformat()] = {
                "pre": int((gip.notna() & (gip < t0)).sum()),
                "launch_day": int((gip.notna() & (gip >= t0) & (gip < day_end)).sum()),
                "post_launch": int((gip.notna() & (gip >= day_end)).sum()),
                "none": int(gip.isna().sum()),
            }
        out[g] = {
            "gen": g, "total": total,
            "pre": int(len(pre)), "launch_day": int(len(launch_day)),
            "post_launch": int(len(post)), "none": int(len(nopay)),
            "pre_share": round(len(pre) / total, 4) if total else None,
            "launch_day_share": round(len(launch_day) / total, 4) if total else None,
            "post_launch_share": round(len(post) / total, 4) if total else None,
            "none_share": round(len(nopay) / total, 4) if total else None,
            "by_day": by_day,
        }
    return out


def compute_quality(df: pd.DataFrame, win: dict) -> dict:
    """订单质量（point-in-time 重建至 D_N 24:00，不使用当前快照状态直出）。

    只用 ≤ cutoff 的事件时间戳；晚于 cutoff 的退订/退款不计入该时点状态。
    """
    out = {}
    for g, w in win["windows"].items():
        t0, cutoff = w["launch"], w["window_end"]
        s = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
               & (df["lock_time"] >= t0) & (df["lock_time"] < cutoff)]
        total = int(s["order_number"].nunique())
        if not total:
            out[g] = {"gen": g, "locked_total": 0}
            continue

        def le(col):
            ts = s[col]
            return int((ts.notna() & (ts < cutoff)).sum())

        dep = int((s["deposit_payment_time"].notna()
                   & (s["deposit_payment_time"] < cutoff)).sum())
        dep_ref = le("deposit_refund_time")
        intent_ref = le("intention_refund_time")
        apply_ref = le("apply_refund_time")
        approve_ref = le("approve_refund_time")
        actual_ref = le("actual_refund_time")
        final_pay = le("final_payment_time")
        delivered = le("delivery_date")
        out[g] = {
            "gen": g, "locked_total": total,
            "deposit_paid": dep,
            "deposit_rate": round(dep / total, 4),
            "deposit_refunded": dep_ref,
            "deposit_refund_rate": round(dep_ref / total, 4),
            "net_locked": total - dep_ref,
            "intention_refund_on_locked": intent_ref,
            "apply_refund": apply_ref,
            "approve_refund": approve_ref,
            "actual_refund": actual_ref,
            "final_paid": final_pay,
            "final_pay_rate": round(final_pay / total, 4),
            "delivered": delivered,
            "delivery_rate": round(delivered / total, 4),
            "refund_pipeline_gap": apply_ref - actual_ref,
        }
    return out


def compute_forward(df: pd.DataFrame, win: dict, presale: dict, curves: dict) -> dict:
    """D_N 时点的前向转化池：未退小订未锁单的存量 + 已转大定未锁 + 近期直锁节奏。"""
    out = {}
    for g, w in win["windows"].items():
        t0, cutoff = w["launch"], w["window_end"]
        s = df[df["series_group_logic"].eq(g)]
        ip = s["intention_payment_time"]
        paid = s[ip.notna() & (ip < cutoff)]
        refunded = paid["intention_refund_time"].notna() & (paid["intention_refund_time"] < cutoff)
        locked = paid["lock_time"].notna() & (paid["lock_time"] < cutoff)
        deposit = paid["deposit_payment_time"].notna() & (paid["deposit_payment_time"] < cutoff)
        dep_ref = paid["deposit_refund_time"].notna() & (paid["deposit_refund_time"] < cutoff)
        alive = paid[~refunded & ~dep_ref]
        pending = alive[~(alive["lock_time"].notna() & (alive["lock_time"] < cutoff))]
        dep_not_lock = pending[pending["deposit_payment_time"].notna()
                               & (pending["deposit_payment_time"] < cutoff)]
        cold = pending[~(pending["deposit_payment_time"].notna()
                         & (pending["deposit_payment_time"] < cutoff))]

        daily = curves["curves"][g]["daily"]
        tail = daily[1:] or [0]
        out[g] = {
            "gen": g,
            "paid_presale_and_after": int(len(paid)),
            "refunded": int(refunded.sum()),
            "locked": int(locked.sum()),
            "deposit_paid": int(deposit.sum()),
            "pending_total": int(len(pending)),
            "pending_deposit_not_locked": int(len(dep_not_lock)),
            "pending_intent_only": int(len(cold)),
            "pending_share_of_paid": round(len(pending) / len(paid), 4) if len(paid) else None,
            "recent_daily_avg": round(sum(tail) / len(tail), 1) if tail else None,
            "days_of_runway_at_recent_pace": (round(len(pending) / (sum(tail) / len(tail)), 1)
                                             if tail and sum(tail) else None),
        }
    return out


def compute_pool_consumption(df: pd.DataFrame, win: dict, presale: dict,
                             dynamics: dict) -> dict:
    """小订池消耗：上市日 24:00 封盘后，池子只剩「转锁」与「退订」两种流出。

    业务定义：小订（意向金）在上市日 24:00 停止收取，之后池子为固定存量 P。
      P = 已经锁单 + 已经退订 + 剩余待转化
    动能 = 剩余池还能转化出多少锁单，取决于「锁单速度 / 退订速度」的比值。

    说明：`intention_refund_time` 在数据中是日期粒度（全部落在 00:00），
    因此只能按日归集，不能解读为某一时刻的系统批量操作。
    """
    out = {}
    for g, w in win["windows"].items():
        t0, cutoff = w["launch"], w["window_end"]
        n = int(win["n_days"])
        p = presale[g]
        stock = p.get("stock_total") or 0
        locked = p.get("stock_locked") or 0
        refunded = p.get("stock_refunded") or 0
        remaining = p.get("stock_remaining") or 0

        refund_daily = p.get("refund_daily") or []
        s_ = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
                & (df["lock_time"] >= t0) & (df["lock_time"] < cutoff)]
        by_day = (s_.groupby(s_["lock_time"].dt.normalize())["order_number"].nunique()
                  .reindex(pd.date_range(t0, cutoff - pd.Timedelta(days=1)), fill_value=0)
                  .astype(int))
        lock_series = [int(v) for v in by_day.values]
        d1_locked = lock_series[0] if lock_series else 0
        tail_days = max(n - 1, 1)
        lock_tail = (sum(lock_series[1:]) / tail_days) if n > 1 else None
        refund_tail_total = sum(refund_daily[1:]) if len(refund_daily) > 1 else 0
        refund_tail = (refund_tail_total / tail_days) if n > 1 else None

        ratio_stock = round(locked / refunded, 2) if refunded else None
        ratio_tail = (round(lock_tail / refund_tail, 2)
                      if lock_tail and refund_tail else None)
        convert_share = (round(locked / (locked + refunded), 4)
                         if (locked + refunded) else None)
        est_low = round(remaining * (p.get("stock_locked_rate") or 0))
        est_high = round(remaining * (convert_share or 0))

        out[g] = {
            "gen": g,
            "stock_total": int(stock),
            "stock_presale": int(p.get("stock_presale") or 0),
            "stock_launch_day": int(p.get("stock_launch_day") or 0),
            "locked": int(locked),
            "refunded": int(refunded),
            "remaining": int(remaining),
            "remaining_rate": p.get("stock_remaining_rate"),
            "locked_rate": p.get("stock_locked_rate"),
            "refund_rate": p.get("stock_refund_rate"),
            "lock_d1": int(d1_locked),
            "lock_tail_daily": round(lock_tail, 1) if lock_tail is not None else None,
            "refund_tail_daily": round(refund_tail, 1) if refund_tail is not None else None,
            "lock_refund_ratio_stock": ratio_stock,
            "lock_refund_ratio_tail": ratio_tail,
            "convert_share_of_consumed": convert_share,
            "lock_daily": lock_series,
            "refund_daily": refund_daily,
            "remaining_est_low": int(est_low),
            "remaining_est_high": int(est_high),
        }
    return out


# ─────────────────────────── 模块 6：区域 / 城市结构 ───────────────────────────

def _decompose(rows: list[dict], key: str, main: str, bench: str,
               t_main: int, t_bench: int) -> list[dict]:
    """精确分解：gap_x = (T_main − T_b)·s_b,x  +  T_main·(s_main,x − s_b,x)。

    前项 = 规模效应（整体体量差异按对标结构摊到该单元），后项 = 结构效应
    （该单元占比差异带来的额外增减，Σ结构效应 = 0）。
    """
    out = []
    for r in rows:
        sm, sb = r[f"{main}_share"], r[f"{bench}_share"]
        out.append({
            key: r[key], "main": r[main], "bench": r[bench],
            "main_share": sm, "bench_share": sb,
            "share_diff_pp": round((sm - sb) * 100, 1),
            "abs_diff": r[main] - r[bench],
            "scale_effect": round((t_main - t_bench) * sb, 1),
            "mix_effect": round(t_main * (sm - sb), 1),
        })
    out.sort(key=lambda d: (-abs(d["mix_effect"]), str(d[key])))
    return out


def compute_geo(df: pd.DataFrame, win: dict) -> dict:
    """区域结构分析：以**省份**为主口径（边界稳定），城市/线级为辅。

    不使用大区作为主口径：2026-04（一区/二区/三区）→ 2026-09 → 2026-11 期间大区架构
    经历过重划，且同一省组（如鲁豫、湘鄂皖）在不同代际窗口中挂在不同大区下，
    直接比较大区占比会把组织架构变更误读为区域表现差异。大区仅作方向性参考列示。
    """
    main = win["main"]
    frames = {}
    for g, w in win["windows"].items():
        t0, hi = w["launch"], w["window_end"]
        frames[g] = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
                       & (df["lock_time"] >= t0) & (df["lock_time"] < hi)]

    def _counts(col_fn, g):
        s = frames[g]
        vals = col_fn(s)
        return s.groupby(vals)["order_number"].nunique()

    city_fn = lambda s: s["license_city"].map(norm_city)
    prov_fn = lambda s: s["license_city"].map(norm_city).map(CITY_TO_PROVINCE).fillna("未知")
    tier_fn = lambda s: s["license_city"].map(norm_city).apply(city_to_tier_label)
    zone_fn = lambda s: s["parent_region_name"].map(_norm_zone)

    dims = {}
    for name, fn in (("province", prov_fn), ("city", city_fn),
                     ("tier", tier_fn), ("zone", zone_fn)):
        counts = {g: _counts(fn, g) for g in win["gens"]}
        totals = {g: int(v.sum()) for g, v in counts.items()}
        keys = sorted(set().union(*[set(c.index) for c in counts.values()]),
                      key=lambda k: (-int(counts[main].get(k, 0)), str(k)))
        rows = []
        for k in keys:
            row = {name: k}
            for g in win["gens"]:
                c = int(counts[g].get(k, 0))
                row[g] = c
                row[f"{g}_share"] = round(c / totals[g], 4) if totals[g] else 0.0
            rows.append(row)
        per_bench = {b: _decompose(rows, name, main, b, totals[main], totals[b])
                     for b in win["gens"] if b != main}
        dims[name] = {"rows": rows, "totals": totals, "gaps": per_bench,
                      "n_main": int((counts[main] > 0).sum()),
                      "n_bench": {b: int((counts[b] > 0).sum())
                                  for b in win["gens"] if b != main}}

    # 省份 Top12（按**主车型自身体量**降序）：Q6 表与 Q6-验证表共用同一清单。
    # 用主车体量而不是差额排序——按差额排会把「主车体量大但差额小/为正」的省份挤出榜单。
    dims["province"]["top_main"] = [
        r["province"] for r in sorted(dims["province"]["rows"],
                                      key=lambda d: (-int(d[main]), str(d["province"])))
    ][:12]

    # 城市差额贡献汇总（用于识别差额集中在哪些城市）
    for b in win["gens"]:
        if b == main:
            continue
        cities = sorted(dims["city"]["gaps"][b],
                        key=lambda d: (-abs(d["abs_diff"]), str(d["city"])))
        dims["city"]["gaps"][b] = {"rows": cities,
                                   "neg_contrib": int(sum(d["abs_diff"] for d in cities
                                                          if d["abs_diff"] < 0)),
                                   "pos_contrib": int(sum(d["abs_diff"] for d in cities
                                                          if d["abs_diff"] > 0))}
    return {"main": main, **dims}


def compute_channel_by_province(df: pd.DataFrame, win: dict) -> dict:
    """省份「渠道 × 需求」分解：门店数效应 vs 单店产出效应。

    口径：以**门店所在省份**（store_city → 省份）聚合，保证各省门店数之和 = 全国门店数
    （已核验无重复计数；跨省上牌仅 1.2–1.6%，不影响结论）。与 Q6 的「上牌省份」需求口径
    不同，两者不可混用。

    Δlocks(省) = (S主 − S对)·p对 + S主·(p主 − p对)
                 前项 = 渠道覆盖效应；后项 = 单店需求效应
    """
    main = win["main"]
    frames = {}
    for g, w in win["windows"].items():
        t0, hi = w["launch"], w["window_end"]
        s = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
               & (df["lock_time"] >= t0) & (df["lock_time"] < hi)].copy()
        prov = s["store_city"].map(norm_city).map(CITY_TO_PROVINCE).fillna("未知")
        agg = s.groupby(prov).agg(locks=("order_number", "nunique"),
                                  stores=("store_name", "nunique"))
        agg["locks_per_store"] = agg["locks"] / agg["stores"].replace(0, pd.NA)
        frames[g] = agg

    def _val(g, p, col):
        a = frames[g]
        if p not in a.index:
            return 0.0
        v = a.loc[p, col]
        return float(v) if pd.notna(v) else 0.0

    provinces = sorted(set().union(*[set(a.index) for a in frames.values()]))
    rows = []
    for p in provinces:
        rows.append({
            "province": p,
            **{f"{g}_locks": int(_val(g, p, "locks")) for g in win["gens"]},
            **{f"{g}_stores": int(_val(g, p, "stores")) for g in win["gens"]},
            **{f"{g}_lps": round(_val(g, p, "locks_per_store"), 2) for g in win["gens"]},
        })

    gaps = {}
    for b in [g for g in win["gens"] if g != main]:
        detail = []
        for r in rows:
            sm, sb = r[f"{main}_stores"], r[f"{b}_stores"]
            pm, pb = r[f"{main}_lps"], r[f"{b}_lps"]
            detail.append({
                "province": r["province"],
                "main_locks": r[f"{main}_locks"], "bench_locks": r[f"{b}_locks"],
                "main_stores": sm, "bench_stores": sb,
                "main_lps": pm, "bench_lps": pb,
                "abs_diff": r[f"{main}_locks"] - r[f"{b}_locks"],
                "store_diff": sm - sb,
                "network_effect": round((sm - sb) * pb, 1),
                "productivity_effect": round(sm * (pm - pb), 1),
            })
        detail.sort(key=lambda d: (-abs(d["abs_diff"]), str(d["province"])))
        gaps[b] = {
            "bench": b,
            "rows": detail[:12],
            "total_diff": sum(d["abs_diff"] for d in detail),
            "total_network_effect": round(sum(d["network_effect"] for d in detail), 1),
            "total_productivity_effect": round(sum(d["productivity_effect"] for d in detail), 1),
        }
    return {"main": main, "rows": rows, "gaps": gaps,
            "unit": "门店所在省份"}


# ─────────────────────────── 模块 6b：锁单来源差额分解 ───────────────────────────

def compute_source_decomp(ctx: dict) -> dict:
    """锁单差额的来源分解：预售小订转锁 / 上市当日新增小订转锁 / 直接锁单，
    并对预售部分进一步拆「池规模」与「转化率」。"""
    main = ctx["main"]
    pre, org, tot = ctx["presale"], ctx["origin"], ctx["curves"]["curves"]
    out = {}
    for b in ctx["benchmarks"]:
        m, k = org[main], org[b]
        gap = m["total"] - k["total"]
        out[b] = {
            "bench": b,
            "gap_total": gap,
            "pre_diff": m["pre"] - k["pre"],
            "launch_day_diff": m["launch_day"] - k["launch_day"],
            "none_diff": m["none"] - k["none"],
            "pre_share_of_gap": (round((m["pre"] - k["pre"]) / gap, 4) if gap else None),
            "launch_day_share_of_gap": (round((m["launch_day"] - k["launch_day"]) / gap, 4)
                                        if gap else None),
            "none_share_of_gap": (round((m["none"] - k["none"]) / gap, 4) if gap else None),
        }
        pm, pb = pre[main], pre[b]
        if pm["pool_total"] and pb["pool_total"]:
            p1, p0 = pm["pool_total"], pb["pool_total"]
            r1 = pm["pool_locked"] / p1
            r0 = pb["pool_locked"] / p0
            scale = (p1 - p0) * r0
            rate = p1 * (r1 - r0)
            out[b].update({
                "pool_main": p1, "pool_bench": p0,
                "pool_diff": p1 - p0,
                "pool_rel": round(p1 / p0 - 1, 4),
                "rate_main": round(r1, 4), "rate_bench": round(r0, 4),
                "presale_scale_effect": round(scale, 1),
                "presale_rate_effect": round(rate, 1),
                "presale_scale_share": (round(scale / (scale + rate), 4)
                                        if (scale + rate) else None),
            })
    return out


def compute_province_model_mix(df: pd.DataFrame, win: dict, top_n: int = 18) -> dict:
    """主代际上市窗口内，各省锁单按「主代际 / 各对标代际 / 其他」的构成。

    口径：单一日历窗口（主代际 D1–D_N），因此 CM3、LS8 等老代际的份额是
    「窗口内仍在售的存量」，不是各自上市初期的水平。
    """
    main = win["main"]
    w = win["windows"][main]
    t0, hi = w["launch"], w["window_end"]
    s = df[df["lock_time"].notna() & (df["lock_time"] >= t0) & (df["lock_time"] < hi)].copy()
    if s.empty:
        return {}
    s["_prov"] = s["license_city"].map(norm_city).map(CITY_TO_PROVINCE).fillna("未知")
    gens = [g for g in win["gens"]]
    s["_grp"] = s["series_group_logic"].where(s["series_group_logic"].isin(gens), "其他")
    ct = pd.crosstab(s["_prov"], s["_grp"])
    for c in gens + ["其他"]:
        if c not in ct.columns:
            ct[c] = 0
    ct = ct[gens + ["其他"]]
    ct["_total"] = ct.sum(axis=1)
    grand_total = int(ct["_total"].sum())
    national = {k: {"n": int(ct[k].sum()),
                    "share": round(int(ct[k].sum()) / grand_total, 4)}
                for k in gens + ["其他"]} if grand_total else {}
    # 先按体量取前 N（避免小样本省份 100% 噪声），再按主代际占比降序展示
    ct = ct.sort_values("_total", ascending=False).head(top_n).copy()
    ct["_share"] = ct[main] / ct["_total"].replace(0, pd.NA)
    ct = ct.sort_values(["_share", "_total"], ascending=False)
    rows = []
    for prov, r in ct.iterrows():
        total = int(r["_total"])
        if total <= 0:
            continue
        rows.append({
            "province": str(prov), "total": total,
            "parts": {k: {"n": int(r[k]), "share": round(int(r[k]) / total, 4)}
                      for k in gens + ["其他"]},
            "main_share": round(int(r[main]) / total, 4),
        })
    return {"window": [t0.date().isoformat(), (hi - pd.Timedelta(days=1)).date().isoformat()],
            "gens": gens, "other_label": "其他",
            "grand_total": grand_total,
            "rows": rows,
            "n_provinces": int(len(rows)),
            "national": national}


def compute_version_gap(df: pd.DataFrame, win: dict, top_n: int = 12,
                        provinces: list | None = None) -> dict:
    """验证：省份差额是不是「版本供给缺口」造成的（按电量段对齐）。

    对齐轴只能用**电量段**（93/76/103kWh），因为两代际版型命名与配置档位不同：
      LS8Neo 93 Max+ ↔ CM3 Pro Max(93)；LS8Neo 103 Max+ ↔ CM3 Ultra(103)；
      CM3 Max(76) 在 LS8Neo 没有对应版本 —— 这是供给缺口，不是需求差。
    """
    main = win["main"]
    benches = [g for g in win["gens"] if g != main]
    if not benches:
        return {}
    bench = benches[0]
    frames = {}
    for g, w in win["windows"].items():
        t0, hi = w["launch"], w["window_end"]
        s = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
               & (df["lock_time"] >= t0) & (df["lock_time"] < hi)].copy()
        s["_prov"] = s["license_city"].map(norm_city).map(CITY_TO_PROVINCE)
        s["_batt"] = s["product_name"].map(lambda x: _battery_of(x, g))
        frames[g] = s

    segs = ["93kWh", "76kWh", "103kWh"]

    def _row(label, mask_a, mask_b):
        a = frames[main][mask_a]
        b = frames[bench][mask_b]
        seg = {}
        for x in segs:
            seg[x] = int((a["_batt"] == x).sum()) - int((b["_batt"] == x).sum())
        total = int(len(a)) - int(len(b))
        return {
            "label": label,
            "main_total": int(len(a)), "bench_total": int(len(b)),
            "total": total, "by_segment": seg,
            "bench_has": {x: int((b["_batt"] == x).sum()) for x in segs},
            "main_has": {x: int((a["_batt"] == x).sum()) for x in segs},
            "missing_segments": [x for x in segs if int((a["_batt"] == x).sum()) == 0],
        }

    national = _row("全国", pd.Series(True, index=frames[main].index),
                    pd.Series(True, index=frames[bench].index))
    prov_gap = (frames[main].groupby("_prov").size()
                .sub(frames[bench].groupby("_prov").size(), fill_value=0))
    if provinces is None:
        provinces = [str(x) for x in prov_gap.sort_values().head(top_n).index]
    rows_out = [_row(str(p_), frames[main]["_prov"].eq(p_), frames[bench]["_prov"].eq(p_))
                for p_ in provinces]
    return {"bench": bench, "main": main, "segments": segs,
            "national": national, "provinces": rows_out,
            "segments_note": "按电量段对齐；76kWh 为对标独有段"}


CONFIG_EXT_ATTRS = ["外饰", "内饰"]
CONFIG_OPT_ATTRS = ["方向盘", "座椅", "激光雷达",
                    "21.5英寸二排观影屏", "智控地暖系统", "全线控转向系统"]


def compute_config_distribution(df: pd.DataFrame, win: dict) -> dict:
    """主代际锁单的配置分布（外饰 / 内饰 / 轮毂 / 选装），取值全部用 config_attribute 原值。

    选装组按属性展开：每个属性的「非默认取值」单独成行（默认 = 该属性内占比最高的取值），
    不合并、不自造品类名。
    """
    main = win["main"]
    w = win["windows"][main]
    t0, hi = w["launch"], w["window_end"]
    s = df[df["series_group_logic"].eq(main) & df["lock_time"].notna()
           & (df["lock_time"] >= t0) & (df["lock_time"] < hi)]
    ids = set(s["order_number"])
    n = len(ids)
    try:
        cfg = pd.read_parquet(CONFIG_PARQUET)
    except Exception:  # pragma: no cover
        return {"gen": main, "n": n, "groups": {}, "defaults": {}}
    sub = cfg[cfg["Order Number"].isin(ids)]

    def _values(attr: str) -> list[dict]:
        a = sub[sub["Attribute"] == attr].drop_duplicates("Order Number")
        if not len(a):
            return []
        vc = a["value"].astype(str).value_counts()
        tot = int(len(a))
        return [{"value": str(k), "count": int(v), "share": round(v / tot, 4),
                 "coverage": round(tot / n, 4)} for k, v in vc.items()]

    groups = {"外饰": _values("外饰"), "内饰": _values("内饰"),
              "轮毂": _values("轮毂"), "选装": []}
    defaults = {}
    for attr in CONFIG_OPT_ATTRS:
        vals = _values(attr)
        if not vals:
            continue
        defaults[attr] = vals[0]["value"]
        for v in vals[1:]:
            groups["选装"].append({"attr": attr, **v})
    groups["选装"].sort(key=lambda x: -x["share"])
    return {"gen": main, "n": n, "groups": groups, "defaults": defaults}


def compute_same_battery_profile(df: pd.DataFrame, win: dict,
                                 segment: str = "93kWh") -> dict:
    """同电量段 vs 全系：同一套指标算两遍，便于直接对比「差距是否缩小」。

    指标与 Q8-1 客群表完全一致（性别 / 年龄中位 / 城市线级 / 省份），
    在同一函数内计算，保证「同档」与「全系」两列口径同源。
    """
    main = win["main"]
    benches = [g for g in win["gens"] if g != main]
    if not benches:
        return {}
    bench = benches[0]

    def _profile(s: pd.DataFrame) -> dict:
        n = int(len(s))
        if not n:
            return {"n": 0}
        city = s["license_city"].map(norm_city)
        tier = city.apply(city_to_tier_label)
        prov = city.map(CITY_TO_PROVINCE)
        age = pd.to_numeric(s["owner_age"], errors="coerce").dropna()
        bage = pd.to_numeric(s["buyer_age"], errors="coerce").dropna()
        if len(age):
            cohorts = pd.cut(age, bins=AGE_BINS, labels=AGE_LABELS, right=False)
            cohort = {str(k): round(v / len(age), 4)
                      for k, v in cohorts.value_counts().sort_index().items()}
            age_median = float(age.median())
        else:
            cohort, age_median = {}, None
        lead = s["first_assign_time"].where(s["first_assign_time"].notna(),
                                            s["first_touch_time"])
        lead_days = (s["lock_time"] - lead).dt.total_seconds() / 86400
        return {
            "n": n,
            "female": round(float(s["order_gender"].eq("女").mean()), 4),
            "age_median": age_median,
            "age_mean": round(float(age.mean()), 1) if len(age) else None,
            "buyer_age_median": float(bage.median()) if len(bage) else None,
            "age_cohort": cohort,
            "tier": {k: round(v / n, 4) for k, v in _vc(tier).items()},
            "province": {k: round(v / n, 4) for k, v in _vc(prov).items()},
            "province_top": [{"province": k, "share": round(v / n, 4)}
                             for k, v in list(_vc(prov).items())[:6]],
            "test_drive_rate": round(float(s["first_test_drive_time"].notna().mean()), 4),
            "d1_lock_share": round(float((s["lock_time"].dt.normalize()
                                          == s["lock_time"].dt.normalize().min()).mean()), 4),
            "lead_to_lock_days_median": (round(float(lead_days.median()), 1)
                                         if lead_days.notna().any() else None),
        }

    out = {"segment": segment, "main": main, "bench": bench, "full": {}, "seg": {}}
    for g, w in win["windows"].items():
        t0, hi = w["launch"], w["window_end"]
        s = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
               & (df["lock_time"] >= t0) & (df["lock_time"] < hi)].copy()
        out["full"][g] = _profile(s)
        seg = s[s["product_name"].map(lambda x: _battery_of(x, g)).eq(segment)]
        out["seg"][g] = _profile(seg)
        if out["seg"][g].get("n"):
            out["seg"][g]["share_of_gen"] = round(out["seg"][g]["n"]
                                                  / max(out["full"][g]["n"], 1), 4)

    def _tvd(store, key):
        a, b = store[main].get(key) or {}, store[bench].get(key) or {}
        keys = set(a) | set(b)
        return round(0.5 * sum(abs(a.get(k, 0) - b.get(k, 0)) for k in keys), 4)

    out["tvd_full"] = {k: _tvd(out["full"], k) for k in ("tier", "age_cohort")}
    out["tvd_seg"] = {k: _tvd(out["seg"], k) for k in ("tier", "age_cohort")}
    return out


PK_CSV_FALLBACK = Path("/Users/zihao_/Documents/coding/dataset/original/"
                       "业务数据记录_竞争PK（正反向排名）.csv")


def _pk_csv_path() -> Path:
    """竞争 PK 数据路径：优先 shared/schema/data_path.md 登记，回退到固定路径。"""
    try:
        from research_scripts.pk_weekly_compare import _read_data_paths
        cands = _read_data_paths(REPO_ROOT / "shared" / "schema" / "data_path.md")
        if "正反向对比" in cands and Path(cands["正反向对比"]).exists():
            return Path(cands["正反向对比"])
    except Exception:  # pragma: no cover
        pass
    return PK_CSV_FALLBACK


def resolve_pk_series(bd: dict, gen: str) -> str | None:
    """代际 → PK 数据里的 series（LS8Neo → LS8；CM3 → LS6）。"""
    mapping = (bd.get("monitor") or {}).get("pk_series_by_generation") or {}
    if gen in mapping:
        return mapping[gen]
    for series, gens in ((bd.get("model_series_mapping") or {})).items():
        if gen in gens:
            return series
    return None


def _week_start(text) -> pd.Timestamp | None:
    import re as _re
    m = _re.match(r"(\d{4})-(\d{2})-(\d{2})", str(text))
    return pd.Timestamp(f"{m.group(1)}-{m.group(2)}-{m.group(3)}") if m else None


def compute_competition_pk(bd: dict, win: dict) -> dict:
    """竞争 PK：上市周的竞品结构、竞争位置（正/反向排名）、上市后周度热度。

    口径：PK正向排名 = 竞品对本品的冲击强度（越小冲击越强）；
         PK反向排名 = 本品对竞品的影响（越小越强）；PK次数 = 该竞品与本品 PK 的次数。
    局限：数据到 series 级（LS8 含 LS8 + LS8Neo），无法拆到单车型；每周仅列 9 个竞品。
    """
    path = _pk_csv_path()
    if not Path(path).exists():
        return {}
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["_pk"] = pd.to_numeric(df["PK次数"].astype(str).str.replace(",", ""),
                              errors="coerce").fillna(0).astype(int)
    df["_w0"] = df["Week"].map(_week_start)
    df = df.dropna(subset=["_w0"])

    gens = {}
    for g, w in win["windows"].items():
        series = resolve_pk_series(bd, g)
        if not series:
            continue
        sub = df[df["series"] == series]
        if sub.empty:
            continue
        launch = w["launch"]
        lw = launch - pd.Timedelta(days=launch.weekday())
        weeks = (sub.groupby("_w0")["_pk"].sum().sort_index())
        row = {
            "series": series,
            "launch": launch.date().isoformat(),
            "launch_week": lw.date().isoformat(),
            "has_launch_week": bool(lw in weeks.index),
            "week_total": int(weeks.get(lw, 0)),
            "aligned": [{"w": int((d - lw).days // 7 + 1), "date": d.date().isoformat(),
                         "total": int(v)} for d, v in weeks.items()
                        if (d - lw).days % 7 == 0 and -4 <= (d - lw).days // 7 <= 12],
            "weeks_available": int(len(weeks)),
            "range": [weeks.index.min().date().isoformat(), weeks.index.max().date().isoformat()],
            "competitors": [],
        }
        if lw in weeks.index:
            lwrows = sub[sub["_w0"] == lw].sort_values("_pk", ascending=False)
            row["competitors"] = [{
                "name": str(r["车系"]), "brand": str(r["品牌"]),
                "pk": int(r["_pk"]),
                "fwd_rank": int(r["PK正向排名"]), "rev_rank": int(r["PK反向排名"]),
                "share": round(int(r["_pk"]) / max(int(lwrows["_pk"].sum()), 1), 4),
            } for _, r in lwrows.iterrows()]
            # 上期（上市前一周）对照：同竞品的 PK 次数与反向排名
            prev_w = lw - pd.Timedelta(days=7)
            prow = sub[sub["_w0"] == prev_w]
            pmap = {str(r["车系"]): {"pk": int(r["_pk"]),
                                     "rev_rank": int(r["PK反向排名"]),
                                     "fwd_rank": int(r["PK正向排名"])}
                    for _, r in prow.iterrows()}
            for c in row["competitors"]:
                pv = pmap.get(c["name"])
                c["prev_pk"] = pv["pk"] if pv else None
                c["prev_rev_rank"] = pv["rev_rank"] if pv else None
                if pv:
                    c["rev_rank_change"] = pv["rev_rank"] - c["rev_rank"]  # 正 = 排名上升
                else:
                    c["rev_rank_change"] = None
            row["prev_week"] = prev_w.date().isoformat()
            row["prev_total"] = int(weeks.get(prev_w, 0))
            row["prev_pk_map"] = pmap
        gens[g] = row

    return {"source": str(path), "gens": gens,
            "series_notes": "数据到 series 级；LS8 series 同时覆盖 LS8 与 LS8Neo"}


def _slice_stats(s: pd.DataFrame, cfg: pd.DataFrame | None, gen: str) -> dict:
    """一个订单子集的「用户画像 + 版型/配置选择」，用于细分对比。"""
    n = int(len(s))
    if not n:
        return {"n": 0}
    city = s["license_city"].map(norm_city)
    tier = city.apply(city_to_tier_label)
    prov = city.map(CITY_TO_PROVINCE)
    age = pd.to_numeric(s["owner_age"], errors="coerce").dropna()
    batt = s["product_name"].map(lambda x: _battery_of(x, gen)).value_counts(normalize=True)
    ids = set(s["order_number"])
    out = {
        "n": n,
        "female": round(float(s["order_gender"].eq("女").mean()), 4),
        "age_median": float(age.median()) if len(age) else None,
        "age_mean": round(float(age.mean()), 1) if len(age) else None,
        "tier": {k: round(v / n, 4) for k, v in _vc(tier).items()},
        "province": {k: round(v / n, 4) for k, v in _vc(prov).items()},
        "test_drive_rate": round(float(s["first_test_drive_time"].notna().mean()), 4),
        "battery": {str(k): round(v, 4) for k, v in batt.items()},
        "config": {},
    }
    if cfg is None or not len(cfg):
        return out
    sub = cfg[cfg["Order Number"].isin(ids)]
    for attr, want in (("外饰", None), ("内饰", None),
                       ("方向盘", "全幅柔感瞬热运动方向盘"),
                       ("激光雷达", "Thor芯片+520线激光雷达+探射灯"),
                       ("21.5英寸二排观影屏", "是"),
                       ("座椅", "奢享大六座")):
        a = sub[sub["Attribute"] == attr].drop_duplicates("Order Number")
        if not len(a):
            continue
        vals = a["value"].astype(str)
        if want is None:
            out["config"][attr] = {k: round(v, 4) for k, v in
                                   _vc_color_or_tone(attr, vals).items()}
        else:
            if not vals.eq(want).any():   # 该代际没有这个取值（命名不同/无该选装）→ 不输出
                continue
            out["config"][f"{attr}={want}"] = round(float(vals.eq(want).mean()), 4)
    return out


def _vc_color_or_tone(attr: str, vals: pd.Series) -> dict:
    """外饰按色系、内饰按色调归组；其余按原值。"""
    if attr == "外饰":
        return vals.map(_color_family).value_counts(normalize=True).to_dict()
    if attr == "内饰":
        return vals.map(_interior_tone2).value_counts(normalize=True).to_dict()
    return vals.value_counts(normalize=True).to_dict()


def compute_slice_compares(df: pd.DataFrame, win: dict) -> dict:
    """Q8-3 Part 2 的两组细分对比：
       2A 同档：主车 93kWh vs 对标 93kWh
       2B 同车不同座椅：主车 六座 vs 五座（含版型选择）
    """
    try:
        cfg = pd.read_parquet(CONFIG_PARQUET)
    except Exception:  # pragma: no cover
        cfg = None
    main = win["main"]
    benches = [g for g in win["gens"] if g != main]
    if not benches:
        return {}
    bench = benches[0]

    def _win_slice(g):
        w = win["windows"][g]
        return df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
                  & (df["lock_time"] >= w["launch"]) & (df["lock_time"] < w["window_end"])]

    out: dict = {}

    # 2A 同档 93kWh
    seg = {}
    for g in (main, bench):
        s = _win_slice(g)
        s = s[s["product_name"].map(lambda x: _battery_of(x, g)).eq("93kWh")]
        seg[g] = _slice_stats(s, cfg, g)
    out["same_battery"] = {"segment": "93kWh", "main": main, "bench": bench, "stats": seg}

    # 2B 主车 六座 vs 五座
    s = _win_slice(main).copy()
    seat = None
    if cfg is not None:
        ids = set(s["order_number"])
        smap = (cfg[(cfg["Attribute"] == "座椅") & (cfg["Order Number"].isin(ids))]
                .drop_duplicates("Order Number").set_index("Order Number")["value"])
        seat = s["order_number"].map(smap)
    if seat is not None:
        batt = s["product_name"].map(lambda x: _battery_of(x, main))
        n_seat = int(seat.notna().sum())
        # 四种配置组合（座椅 × 电量）：实际联合分布 + 「座椅占比 × 电量占比」的乘积估算
        seg_share = {b: (float((batt == b).mean()) if len(batt) else 0.0)
                     for b in ("93kWh", "103kWh")}
        combos = []
        for seat_val, seat_key in (("旗舰大五座", "five"), ("奢享大六座", "six")):
            m = seat.eq(seat_val)
            n_s = int(m.sum())
            for b in ("93kWh", "103kWh"):
                n_sb = int((m & batt.eq(b)).sum())
                combos.append({
                    "seat": seat_val, "battery": b, "n": n_sb,
                    "share": round(n_sb / n_seat, 4) if n_seat else None,
                    "est_share": round((n_s / n_seat) * seg_share[b], 4) if n_seat else None,
                })
        out["seat"] = {
            "gen": main,
            "six": _slice_stats(s[seat.eq("奢享大六座")], cfg, main),
            "five": _slice_stats(s[seat.eq("旗舰大五座")], cfg, main),
            "coverage": round(float(seat.notna().mean()), 4),
            "combos": combos,
            "seat_n": n_seat,
        }

        # 2C 跨代际六座对比：主车六座来自「座椅」字段；对标六座写在 product_name（版型）里。
        # 逐个对标基因找含「六座」版型的那一代，取样本最多者。
        cand = []
        for b in benches:
            wb = win["windows"][b]
            s_b = df[df["series_group_logic"].eq(b) & df["lock_time"].notna()
                     & (df["lock_time"] >= wb["launch"])
                     & (df["lock_time"] < wb["window_end"])]
            six_b = s_b[s_b["product_name"].astype(str).str.contains("六座")]
            cand.append((len(six_b), b, s_b, six_b))
        cand.sort(key=lambda x: -x[0])
        n_six_b, b_gen, s_b, six_b = cand[0] if cand else (0, None, None, None)
        if n_six_b:
            out["seat_cross"] = {
                "main": main, "bench": b_gen,
                "main_six": out["seat"]["six"],
                "main_total": int(len(s)),
                "bench_six": _slice_stats(six_b, cfg, b_gen),
                "bench_total": int(len(s_b)),
                "main_six_share": round(len(s[seat.eq("奢享大六座")]) / max(len(s), 1), 4),
                "bench_six_share": round(len(six_b) / max(len(s_b), 1), 4),
                "bench_rule": "product_name 含「六座」",
            }
            # 2C 稳健性：剔除上海（六座占比在两代际差异最大的省份）
            def _prov(x):
                return x["license_city"].map(norm_city).map(CITY_TO_PROVINCE)

            s_ne = s[_prov(s).ne("上海")]
            six_b_ne = six_b[_prov(six_b).ne("上海")]
            if len(six_b_ne) and len(s_ne):
                out["seat_cross_ex_sh"] = {
                    "main": main, "bench": b_gen,
                    "main_six": _slice_stats(s_ne[seat[_prov(s).ne("上海")]
                                             .eq("奢享大六座")], cfg, main),
                    "main_total": int(len(s_ne)),
                    "bench_six": _slice_stats(six_b_ne, cfg, b_gen),
                    "bench_total": int(len(s_b[_prov(s_b).ne("上海")])),
                    "main_six_share": round(
                        float(seat[_prov(s).ne("上海")].eq("奢享大六座").mean()), 4),
                    "bench_six_share": round(
                        len(six_b_ne) / max(len(s_b[_prov(s_b).ne("上海")]), 1), 4),
                    "bench_rule": "product_name 含「六座」",
                    "excluded": "上海",
                }
    return out


# ─────────────────────────── 模块 7：门店网络 ───────────────────────────

def compute_network(df: pd.DataFrame, win: dict) -> dict:
    """网络覆盖 × 单店产能。按目标代际过滤订单，不把其他车系有单门店算作有效门店。"""
    out = {}
    enriched_cache: dict[str, pd.DataFrame] = {}
    for g, w in win["windows"].items():
        t0, hi = w["launch"], w["window_end"]
        win_all = df[df["lock_time"].notna() & (df["lock_time"] >= t0) & (df["lock_time"] < hi)]
        s = win_all[win_all["series_group_logic"].eq(g)]
        stores_all = win_all["store_name"].dropna().nunique()
        stores_gen = s["store_name"].dropna().nunique()
        n_locks = int(s["order_number"].nunique())

        # 门店维表补充：经销商主体 / 门店形态 / 城市（当前主数据映射，非 PIT）
        try:
            enr = store_loader.enrich_store_df(s)
            bloc_n = int(enr["bloc_name"].dropna().nunique())
            fmt = _vc(enr.drop_duplicates("store_name")["store_format"], digits=None)
        except Exception:  # pragma: no cover - 主数据缺失时降级
            bloc_n, fmt = None, {}
        by_store = s.groupby("store_name")["order_number"].nunique().sort_values(ascending=False)
        top10 = int(by_store.head(10).sum())
        out[g] = {
            "gen": g,
            "locks": n_locks,
            "active_stores_all_series": int(stores_all),
            "stores_with_gen": int(stores_gen),
            "gen_store_penetration": round(stores_gen / stores_all, 4) if stores_all else None,
            "locks_per_store": round(n_locks / stores_gen, 2) if stores_gen else None,
            "cities_with_gen": int(s["store_city"].dropna().nunique()),
            "bloc_count": bloc_n,
            "store_format_mix": {str(k): int(v) for k, v in fmt.items()},
            "top10_store_share": round(top10 / n_locks, 4) if n_locks else None,
            "top10_stores": [{"store": str(k), "locks": int(v)} for k, v in by_store.head(10).items()],
            "median_store_locks": float(by_store.median()) if len(by_store) else None,
            "single_lock_store_share": (round((by_store == 1).mean(), 4)
                                        if len(by_store) else None),
        }
    # 精确分解：gap = (S_main − S_b)·P_b  +  S_main·(P_main − P_b)
    main = win["main"]
    for b in [g for g in win["gens"] if g != main]:
        sm, sb = out[main]["stores_with_gen"], out[b]["stores_with_gen"]
        pm, pb = (out[main]["locks_per_store"] or 0), (out[b]["locks_per_store"] or 0)
        scale = (sm - sb) * pb
        prod = sm * (pm - pb)
        out[b]["vs_main_decomp"] = {
            "bench": b, "gap_locks": out[main]["locks"] - out[b]["locks"],
            "store_diff": sm - sb,
            "locks_per_store_main": pm, "locks_per_store_bench": pb,
            "network_effect": round(scale, 1),
            "productivity_effect": round(prod, 1),
            "network_share": (round(scale / (scale + prod), 4) if (scale + prod) else None),
        }
    return out


# ─────────────────────────── 模块 8：产品 / 配置 / 用户结构 ───────────────────────────

def _version_of(name: str) -> str:
    return str(name).replace(" ", "")


# 版本 → 电量（业务确认，2026-11-09）：LS6 全新一代 Pro Max / Max / Ultra = 93 / 76 / 103 kWh。
# 说明：shared/schema/business_definition.json 的 battery_capacity_logic 是按名称模式猜的旧规则
# （会把 Pro Max 判成 103），product_version_series 里也尚无 CM3 条目；本映射为本次研究的
# 业务口径，建议后续正式登记到 product_version_series 后再删掉这份本地常量。
VERSION_BATTERY_BY_GEN = {
    "CM3": [("PROMAX", "93kWh"), ("ULTRA", "103kWh"), ("MAX", "76kWh")],
}


def _battery_of(name: str, gen: str | None = None) -> str:
    """电量段：优先按「代际 + 版型」的业务映射，未命中再退回名称里的电量数字。"""
    key = _version_of(name).upper()
    for token, kwh in VERSION_BATTERY_BY_GEN.get(gen or "", []):
        if token in key:
            return kwh
    for kwh in ("103", "93", "100", "76", "66", "52"):
        if kwh in key:
            return f"{kwh}kWh"
    return "未标注"


def _color_family(v: str) -> str:
    v = str(v)
    for kw, label in (("黑", "黑色系"), ("白", "白色系"), ("灰", "灰色系"),
                      ("银", "银色系"), ("绿", "绿色系"), ("茶", "茶棕系"),
                      ("棕", "茶棕系"), ("蓝", "蓝色系"), ("红", "红色系"),
                      ("金", "金色系"), ("紫", "紫色系"), ("橘", "橙色系")):
        if kw in v:
            return label
    return "其他"


def _interior_tone(v: str) -> str:
    v = str(v)
    if "黑" in v:
        return "深色（黑）"
    if any(k in v for k in ("灰", "米", "白")):
        return "浅色（灰/米/白）"
    if any(k in v for k in ("棕", "橘", "茶", "咖")):
        return "暖色（棕/橘）"
    return "其他"


def _wheel_size(v: str) -> str:
    v = str(v)
    for size in ("22", "21", "20", "19"):
        if v.startswith(size) or f"{size}英寸" in v:
            return f"{size}英寸"
    return "其他"


def _hhi(shares: list[float]) -> float | None:
    """赫芬达尔指数（Σshare²）；单版型 = 1.0。"""
    if not shares:
        return None
    return round(float(sum(x * x for x in shares)), 4)


def _concentration(s: pd.DataFrame, n: int) -> dict:
    """版型 / 电量集中度。注意：集中度受「可售版型数量」机械约束，属供给端效应。"""
    out = {}
    for key, col in (("versions", "ver"), ("battery", "_batt")):
        vc = s[col].value_counts()
        shares = [v / n for v in vc.values]
        out[key] = {
            "n_options": int(len(vc)),
            "top1": str(vc.index[0]) if len(vc) else None,
            "top1_share": round(shares[0], 4) if shares else None,
            "hhi": _hhi(shares),
        }
    return out


def _tier_x_version(s: pd.DataFrame, n: int) -> dict:
    """线级 × 版型矩阵：行内占比 + 绝对单量，用于判断配置偏好是否分层。"""
    s = s.copy()
    s["_tier"] = s["license_city"].map(norm_city).apply(city_to_tier_label)
    ct = pd.crosstab(s["_tier"], s["ver"])
    if ct.empty:
        return {"tiers": [], "versions": [], "share": {}, "count": {}}
    tiers = [t for t in ("一线", "新一线", "二线", "三线及以下") if t in ct.index]
    tiers += [t for t in ct.index if t not in tiers]
    versions = [v for v, _ in sorted(ct.sum(axis=0).items(), key=lambda kv: (-int(kv[1]), str(kv[0])))]
    share = {t: {v: round(float(ct.loc[t, v]) / float(ct.loc[t].sum()), 4) for v in versions}
             for t in tiers}
    count = {t: {v: int(ct.loc[t, v]) for v in versions} for t in tiers}
    return {"tiers": tiers, "versions": versions, "share": share, "count": count}


INTERIOR_DARK_KW = ("黑", "深灰", "深棕")
INTERIOR_LIGHT_KW = ("米", "白", "浅")
INTERIOR_WARM_KW = ("棕", "橘", "咖", "褐")


def _interior_tone2(v: str) -> str:
    """内饰色调：深色（黑/深灰）/ 浅色（米/白/浅/灰）/ 暖色（棕/橘/咖）。

    命名是复合色（如「大象灰黑」「大象深灰」），先判深色关键词再判浅色，
    避免把「灰黑」误归为浅色。规则写在报告脚注里，可追溯。
    """
    v = str(v)
    if any(k in v for k in INTERIOR_DARK_KW):
        return "深色"
    if any(k in v for k in INTERIOR_WARM_KW):
        return "暖色"
    if any(k in v for k in INTERIOR_LIGHT_KW) or "灰" in v:
        return "浅色"
    return "其他"


# 选装口径：直接保留 config_attribute 的字段名与取值名，不做二次归并、不自造品类名。
# 只有「属性名 + 取值名完全相同」才算同口径可比；命名不同的在下游显式标注。
OPTION_ATTRS = [
    "方向盘",
    "座椅",
    "激光雷达",
    "超远距高精度激光雷达",
    "超远距高精度双激光雷达",
    "21.5英寸二排观影屏",
    "21.5英寸4K二排观影屏",
    "后排娱乐屏（仅5座可选）",
    "智控地暖系统",
    "IM 智控地暖系统",
    "全线控转向系统",
]


def compute_behavior(df: pd.DataFrame, win: dict) -> dict:
    """购买行为：上市日锁单占比、即时锁单、试驾参与率、小订→锁单时长。"""
    out = {}
    for g, w in win["windows"].items():
        t0, cutoff = w["launch"], w["window_end"]
        s = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
               & (df["lock_time"] >= t0) & (df["lock_time"] < cutoff)].copy()
        n = int(s["order_number"].nunique())
        if not n:
            out[g] = {"gen": g, "n": 0}
            continue
        ip = s["intention_payment_time"]
        same_day = s[ip.notna() & (ip.dt.normalize() == s["lock_time"].dt.normalize())]
        no_int = s[ip.isna()]
        inst = int(len(same_day) + len(no_int))
        td = s["first_test_drive_time"]
        hours = (s["lock_time"] - ip).dt.total_seconds() / 3600

        # 线索 → 锁单间隔（线索时间优先取 first_assign_time，缺失回退 first_touch_time）
        lead = s["first_assign_time"].where(s["first_assign_time"].notna(),
                                            s["first_touch_time"])
        lead_days = (s["lock_time"] - lead).dt.total_seconds() / 86400
        lead_ok = lead_days.notna() & (lead_days >= 0)
        pre_mask = lead_ok & (lead < t0)
        post_mask = lead_ok & (lead >= t0)
        same_day_lead = lead_ok & (lead.dt.normalize() == s["lock_time"].dt.normalize())

        out[g] = {
            "gen": g, "n": n,
            "lead_coverage": round(float(lead_ok.mean()), 4),
            "lead_to_lock_days_median": (round(float(lead_days[lead_ok].median()), 1)
                                         if lead_ok.any() else None),
            "lead_to_lock_days_median_presale": (round(float(lead_days[pre_mask].median()), 1)
                                                 if pre_mask.any() else None),
            "lead_to_lock_days_median_postlaunch": (round(float(lead_days[post_mask].median()), 2)
                                                    if post_mask.any() else None),
            "lead_to_lock_le7_share": (round(float((lead_days[lead_ok] <= 7).mean()), 4)
                                       if lead_ok.any() else None),
            "same_day_lead_lock_share": (round(float(same_day_lead[lead_ok].mean()), 4)
                                         if lead_ok.any() else None),
            "lead_presale_n": int(pre_mask.sum()),
            "lead_postlaunch_n": int(post_mask.sum()),
            "lock_d1_share": round(float((s["lock_time"].dt.normalize() == t0).mean()), 4),
            "instant_locks": inst,
            "instant_share": round(inst / n, 4),
            "same_day_locks": int(len(same_day)),
            "no_intent_locks": int(len(no_int)),
            "test_drive_rate": round(float(td.notna().mean()), 4),
            "test_drive_before_lock_rate": round(float(
                ((td.notna()) & (td <= s["lock_time"])).mean()), 4),
            "intent_to_lock_hours_median": (round(float(hours.median()), 1)
                                             if hours.notna().any() else None),
        }
    return out


AGE_BINS = [0, 30, 35, 40, 45, 50, 200]
AGE_LABELS = ["30岁以下", "30-34", "35-39", "40-44", "45-49", "50岁及以上"]


def _age_cohort(age: pd.Series) -> dict:
    """车主年龄分档占比（分母为年龄非空订单）。"""
    a = pd.to_numeric(age, errors="coerce").dropna()
    if not len(a):
        return {}
    b = pd.cut(a, bins=AGE_BINS, labels=AGE_LABELS, right=False)
    vc = b.value_counts().sort_index()
    return {str(k): round(int(v) / len(a), 4) for k, v in vc.items()}


def compute_product(df: pd.DataFrame, win: dict) -> dict:
    """版本 / 电池 / 语义可比配置结构（仅窗口内零售锁单）。"""
    try:
        cfg = pd.read_parquet(CONFIG_PARQUET)
    except Exception:  # pragma: no cover
        cfg = None
    out = {}
    for g, w in win["windows"].items():
        t0, hi = w["launch"], w["window_end"]
        s = df[df["series_group_logic"].eq(g) & df["lock_time"].notna()
               & (df["lock_time"] >= t0) & (df["lock_time"] < hi)].copy()
        n = int(s["order_number"].nunique())
        if not n:
            out[g] = {"gen": g, "n": 0}
            continue
        s["ver"] = s["product_name"].map(_version_of)
        ver = s.groupby("ver")["order_number"].nunique().sort_values(ascending=False)
        battery = s["product_name"].map(lambda x: _battery_of(x, g))
        s["_batt"] = battery
        batt_source = ("version_map" if g in VERSION_BATTERY_BY_GEN
                       and (battery != "未标注").any() else "name_pattern")
        prof = {
            "gen": g, "n": n,
            "versions": [{"version": k, "locks": int(v), "share": round(v / n, 4)}
                         for k, v in sorted(ver.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))],
            "battery": {k: round(v / n, 4) for k, v in _vc(battery).items()},
            "gender": {k: round(v / n, 4) for k, v in
                       _vc(s["order_gender"].fillna("未知")).items()},
            "tier": {k: round(v / n, 4) for k, v in
                     _vc(s["license_city"].map(norm_city).apply(city_to_tier_label)).items()},
            "province_top": [{"province": k, "share": round(v / n, 4)}
                             for k, v in list(_vc(s["license_city"].map(norm_city)
                                                  .map(CITY_TO_PROVINCE)
                                                  .fillna("未知")).items())[:8]],
            "age_cohort": _age_cohort(s["owner_age"]),
            "owner_age_mean": (round(float(pd.to_numeric(s["owner_age"], errors="coerce")
                                          .mean()), 1)
                               if pd.to_numeric(s["owner_age"], errors="coerce").notna().any()
                               else None),
            "owner_age_median": (float(s["owner_age"].median())
                                 if s["owner_age"].notna().any() else None),
            "buyer_age_median": (float(s["buyer_age"].median())
                                 if s["buyer_age"].notna().any() else None),
            "age_missing_rate": round(float(s["owner_age"].isna().mean()), 4),
            "config_coverage": None,
            "attrs": {},
            "concentration": _concentration(s, n),
            "tier_x_version": _tier_x_version(s, n),
            "interior_tone": {}, "option_values": {}, "battery_source": batt_source,
        }
        if cfg is not None:
            sub = cfg[cfg["Order Number"].isin(set(s["order_number"]))]
            prof["config_coverage"] = round(sub["Order Number"].nunique() / n, 4)
            interior = sub[sub["Attribute"] == "内饰"].drop_duplicates("Order Number")
            if len(interior):
                prof["interior_tone"] = {k: round(v / len(interior), 4) for k, v in
                                         _vc(interior["value"].map(_interior_tone2)).items()}
            # 选装：按 config_attribute 原始「属性 → 取值」保留，不自造品类名
            for attr in OPTION_ATTRS:
                a = sub[sub["Attribute"] == attr].drop_duplicates("Order Number")
                if not len(a):
                    continue
                vals = a["value"].astype(str)
                vc = vals.value_counts()
                prof["option_values"][attr] = {
                    "n": int(len(a)),
                    "covered_rate": round(len(a) / n, 4),
                    "values": [{"value": str(k), "share": round(v / len(a), 4),
                                "count": int(v)} for k, v in vc.items()],
                }
            for attr in CORE_ATTRS:
                a = sub[sub["Attribute"] == attr]
                if a.empty:
                    continue
                vals = a.drop_duplicates("Order Number")["value"].astype(str)
                prof["attrs"][attr] = {
                    "n": int(vals.nunique() and len(vals)),
                    "top": [{"value": k, "share": round(v / len(vals), 4)}
                            for k, v in list(_vc(vals).items())[:4]],
                    "normalized": {
                        "color_family": ({k: round(v / len(vals), 4) for k, v in
                                          _vc(vals.map(_color_family)).items()}
                                         if attr == "外饰" else None),
                        "interior_tone": None,
                        "wheel_size": ({k: round(v / len(vals), 4) for k, v in
                                        _vc(vals.map(_wheel_size)).items()}
                                       if attr == "轮毂" else None),
                    },
                    "n_distinct": int(a["value"].nunique()),
                }
        out[g] = prof
    return out


# ─────────────────────────── 数据质量审计 ───────────────────────────

def validate_pool_identities(presale: dict, pool: dict, gens: list[str]) -> dict:
    """跨口径恒等式校验：预售池待转化 ≠ 封盘池剩余，二者必须能对上。

    stock_total      = pool_total + launch_intent_total
    remaining(封盘)   = pool_pending(预售待转化) + 上市当日新增未转化部分
    """
    out = {}
    for g in gens:
        p_, q_ = presale.get(g) or {}, pool.get(g) or {}
        stock = q_.get("stock_total") or 0
        pool_total = p_.get("pool_total") or 0
        launch_intent = p_.get("launch_intent_total") or 0
        locked = q_.get("locked") or 0
        refunded = q_.get("refunded") or 0
        remaining = q_.get("remaining") or 0
        pool_pending = p_.get("pool_pending") or 0
        launch_remaining = (launch_intent
                            - (locked - (p_.get("pool_locked") or 0))
                            - (refunded - (p_.get("pool_refunded") or 0)))
        checks = {
            "stock_eq_pool_plus_launch": stock == pool_total + launch_intent,
            "remaining_eq_locked_refunded": remaining == stock - locked - refunded,
            "remaining_eq_parts": remaining == pool_pending + launch_remaining,
        }
        out[g] = {
            "ok": all(checks.values()),
            "checks": checks,
            "stock_total": stock, "pool_total": pool_total,
            "launch_intent_total": launch_intent,
            "remaining_stock": remaining,
            "remaining_presale_part": pool_pending,
            "remaining_launch_part": launch_remaining,
            "note": ("封盘池剩余 = 预售池待转化 + 上市当日新增未转化；"
                     "两者不是同一指标，报告标签必须区分"),
        }
    return out


def compute_data_audit(df: pd.DataFrame, win: dict, bd: dict) -> dict:
    """P0 审计：覆盖、唯一性、测试单、快照口径风险。"""
    audit = {
        "order_rows": int(len(df)),
        "order_number_dup": int(df["order_number"].duplicated().sum()),
        "order_number_dup_within_gen": {},
        "max_lock_time": (df["lock_time"].max().strftime("%Y-%m-%d %H:%M")
                          if df["lock_time"].notna().any() else None),
        "max_order_create": (df["order_create_date"].max().strftime("%Y-%m-%d")
                             if df["order_create_date"].notna().any() else None),
        "as_of": win["last_date"].date().isoformat(),
        "data_covers_as_of": bool(df["lock_time"].notna().any()
                                 and df["lock_time"].max().normalize() >= win["last_date"]),
        "gen": {},
        "aux": {},
    }
    for g, w in win["windows"].items():
        s = df[df["series_group_logic"].eq(g)]
        win_s = s[s["lock_time"].notna() & (s["lock_time"] >= w["launch"])
                  & (s["lock_time"] < w["window_end"])]
        audit["gen"][g] = {
            "orders_total": int(len(s)),
            "orders_in_window": int(win_s["order_number"].nunique()),
            "dup_in_window": int(win_s["order_number"].duplicated().sum()),
            "test_orders_flagged": int(flag_test_orders(s, bd).sum()),
            "order_type_in_window": {str(k): int(v) for k, v in
                                     win_s["order_type"].fillna("未标注").value_counts().items()},
            "max_lock_normalized_date": (win_s["lock_time"].max().normalize().date().isoformat()
                                         if len(win_s) else None),
            "days_covered": int(win_s["lock_time"].dt.normalize().nunique()),
            "n_days": w["n_days"],
        }
    # 辅助数据集最新完整日期（仅作同期市场/渠道信号，不含单车型维度）
    for key, path in (("assign", ASSIGN_CSV), ("test_drive", TEST_DRIVE_CSV)):
        try:
            head = pd.read_csv(path, encoding="utf-8-sig", nrows=2)
            date_col = head.columns[0]
            d = pd.read_csv(path, encoding="utf-8-sig", usecols=[date_col])
            parsed = pd.to_datetime(d[date_col].astype(str).str.replace("年", "-")
                                    .str.replace("月", "-").str.replace("日", ""),
                                    errors="coerce")
            audit["aux"][key] = {"path": str(path.relative_to(REPO_ROOT)),
                                 "max_date": parsed.max().date().isoformat() if parsed.notna().any() else None,
                                 "rows": int(len(d)),
                                 "date_column": str(date_col)}
        except Exception as e:  # pragma: no cover
            audit["aux"][key] = {"path": str(path.relative_to(REPO_ROOT)), "error": str(e)}
    audit["aux"]["store_master"] = {
        "path": str(store_loader.get_store_info_csv_path()),
        "rows": int(len(si)) if (si := store_loader.load_store_info()) is not None else 0,
        "note": "当前主数据快照；门店→经销商/形态映射非 PIT，仅用于结构解读",
    }
    return audit


# ─────────────────────────── 主计算入口 ───────────────────────────

def build_context(gen: str, benchmarks: list[str], as_of: pd.Timestamp,
                  context_days: int = 30) -> tuple[dict, pd.DataFrame]:
    bd = load_business_definition(BUSINESS_DEF)
    main = resolve_gen(bd, gen)
    benches = [resolve_gen(bd, b) for b in benchmarks]
    gens = [main] + [b for b in benches if b != main]

    df_all = load_orders(bd)
    df = df_all[lock_mask(df_all, bd)].copy()          # 锁单/结构口径：用户单零售
    df_pool = df_all[pool_mask(df_all, bd)].copy()     # 小订池口径：允许类型未回填
    win = build_windows(bd, gens, as_of)

    curves = compute_curves(df, win)
    presale = compute_presale_pool(df_pool, win)
    dynamics = compute_dynamics(curves)
    pool_consumption = compute_pool_consumption(df, win, presale, dynamics)
    geo = compute_geo(df, win)
    prov12 = geo["province"].get("top_main") or []
    ctx = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "main": main,
        "benchmarks": [g for g in gens if g != main],
        "as_of": win["last_date"].date().isoformat(),
        "n_days": win["n_days"],
        "n_days_intended": win.get("n_days_intended", win["n_days"]),
        "window_capped": bool(win.get("window_capped")),
        "windows": {g: {"launch": w["launch"].date().isoformat(),
                        "window_end_exclusive": w["window_end"].date().isoformat(),
                        "presale_start": (w["presale_start"].date().isoformat()
                                          if w["presale_start"] is not None else None),
                        "weekdays": w["weekdays"]}
                    for g, w in win["windows"].items()},
        "audit": {**compute_data_audit(df, win, bd),
                  "pool_identities": validate_pool_identities(presale, pool_consumption, gens)},
        "exclusions": exclusion_report(df_all, bd, win),
        "rows_raw": int(len(df_all)),
        "rows_retail": int(len(df)),
        "curves": curves,
        "dynamics": dynamics,
        "launch_night": compute_launch_night(df, win),
        "presale": presale,
        "origin": compute_origin_split(df, win),
        "quality": compute_quality(df, win),
        "forward": compute_forward(df, win, presale, curves),
        "geo": geo,
        "network": compute_network(df, win),
        "product": compute_product(df, win),
        "behavior": compute_behavior(df, win),
        "context": compute_context_curves(df, win, context_days),
        "channel": compute_channel_by_province(df, win),
        "version_gap": compute_version_gap(df, win, provinces=prov12),
        "province_mix": compute_province_model_mix(df, win),
        "same_battery": compute_same_battery_profile(df, win, "93kWh"),
        "config_dist": compute_config_distribution(df, win),
        "slice_compares": compute_slice_compares(df, win),
        "pk": compute_competition_pk(bd, win),
    }
    ctx["deltas"] = _compute_deltas(ctx)
    ctx["source_decomp"] = compute_source_decomp(ctx)
    ctx["pool"] = pool_consumption
    ctx["narrative"] = compute_narrative(ctx)
    ctx["audit"]["pool_identities"] = validate_pool_identities(
        ctx["presale"], ctx["pool"], ctx["curves"]["gens"])
    return ctx, df


def compute_narrative(ctx: dict) -> dict:
    """根据数据形态生成章节规划（由渲染器消费，而不是固定四幕十问的呈现顺序）。

    规划粒度：第二幕（Q4 预售 / Q5 来源）与第三幕（Q6 区域 / Q7 网络 / Q8 产品客群）的顺序，
    以及因数据缺失而跳过的区块。规则全部可复算、可解释。
    """
    gens = ctx["curves"]["gens"]
    main = ctx["main"]
    d = ctx["deltas"]
    rels = [abs(v.get("cum_rel") or 0) for v in d.values()]
    rules = []

    # 主线：总量关系决定叙事入口
    if rels and max(rels) <= 0.05:
        thread = {
            "label": "总量持平，差异在节奏与结构",
            "why": f"与所有对标的累计差都在 ±{max(rels) * 100:.1f}% 内，"
                   f"单看总量读不出差别",
        }
    elif all((v.get("cum_diff") or 0) < 0 for v in d.values()) and max(rels) > 0.15:
        thread = {
            "label": "全面落后，差距在上市初期即已形成",
            "why": f"对所有对标均为负，最大相对差 {max(rels) * 100:.1f}%",
        }
    else:
        thread = {
            "label": "差异小于总量波动，需按对标分别读",
            "why": f"相对差区间 {min(rels) * 100:.1f}%–{max(rels) * 100:.1f}%",
        }
    rules.append({"rule": "主线判定", "result": thread["label"], "evidence": thread["why"]})

    # 第二幕：直锁占比差异大 → 先讲来源结构（链路差异），否则先讲预售池
    org = ctx["origin"]
    dl = {g: (org[g].get("none") or 0) / max(org[g].get("total") or 1, 1) for g in gens}
    spread = (max(dl.values()) - min(dl.values())) * 100
    if spread >= 10:
        act2 = ["q5", "q4"]
        rules.append({
            "rule": "第二幕顺序：来源结构优先",
            "result": "Q5 → Q4",
            "evidence": f"直锁占比跨代际相差 {spread:.1f}pp（"
                        + "、".join(f"{g} {dl[g] * 100:.1f}%" for g in gens)
                        + "），下单链路差异会污染预售池的读法",
        })
    else:
        act2 = ["q4", "q5"]
        rules.append({"rule": "第二幕顺序：预售池优先", "result": "Q4 → Q5",
                      "evidence": f"直锁占比跨代际仅差 {spread:.1f}pp，预售池可直接比较"})

    # 第三幕：门店数与单店产出反向且幅度都大 → 网络先讲
    net = ctx["network"]
    store_rel = {b: (net[main]["stores_with_gen"] - net[b]["stores_with_gen"])
                 / max(net[b]["stores_with_gen"], 1) for b in ctx["benchmarks"]}
    per_rel = {b: (net[main]["locks_per_store"] - net[b]["locks_per_store"])
               / max(net[b]["locks_per_store"], 1e-9) for b in ctx["benchmarks"]}
    trigger = [b for b in ctx["benchmarks"]
               if store_rel[b] * per_rel[b] < 0 and abs(store_rel[b]) > 0.08
               and abs(per_rel[b]) > 0.08]
    opposite = bool(trigger)
    if opposite:
        act3 = ["q7", "q6", "q8"]
        rules.append({
            "rule": "第三幕顺序：网络优先",
            "result": "Q7 → Q6 → Q8",
            "evidence": "门店数与单店产出方向相反且幅度均 >8%（"
                        + "；".join(f"vs {b} 门店 {store_rel[b] * 100:+.1f}%、单店 {per_rel[b] * 100:+.1f}%"
                                   for b in trigger) + "）",
        })
    else:
        act3 = ["q6", "q7", "q8"]
        rules.append({"rule": "第三幕顺序：区域优先", "result": "Q6 → Q7 → Q8",
                      "evidence": "门店数与单店产出未出现反向放大，区域差异先行"})

    # 跳过项：数据不可比时显式声明
    skips = []
    sb = ctx.get("same_battery") or {}
    seg = sb.get("seg") or {}
    benign, bben = sb.get("bench") or "", None
    a, b2 = seg.get(main) or {}, seg.get(benign) or {}
    if not a.get("n") or not b2.get("n"):
        lack = []
        if not a.get("n"):
            lack.append(f"{main} 无 {sb.get('segment')} 档")
        if not b2.get("n"):
            lack.append(f"{benign} 无 {sb.get('segment')} 档")
        skips.append({"block": "Q8-1 补充（同档客群）", "reason": "；".join(lack) + "，不可比"})
    seat = (ctx.get("slice_compares") or {}).get("seat") or {}
    if not (seat.get("six", {}).get("n") and seat.get("five", {}).get("n")):
        skips.append({"block": "2B（六座 vs 五座）", "reason": "config_attribute 无「座椅」有效取值"})
    cx = (ctx.get("slice_compares") or {}).get("seat_cross") or {}
    if not (cx.get("main_six", {}).get("n") and cx.get("bench_six", {}).get("n")):
        skips.append({"block": "2C（跨代际六座）", "reason": "任一侧六座样本为空"})

    return {"thread": thread, "act2": act2, "act3": act3, "rules": rules, "skips": skips}


def _compute_deltas(ctx: dict) -> dict:
    """绝对/相对差异总表：以 D_N 累计与 D1 爆发两个口径对每个对标取差。"""
    main = ctx["main"]
    c = ctx["curves"]["curves"]
    out = {}
    for b in ctx["benchmarks"]:
        m_cum, b_cum = c[main]["cum"][-1], c[b]["cum"][-1]
        m_d1, b_d1 = c[main]["daily"][0], c[b]["daily"][0]
        out[b] = {
            "bench": b,
            "cum_main": m_cum, "cum_bench": b_cum,
            "cum_diff": m_cum - b_cum,
            "cum_rel": round(m_cum / b_cum - 1, 4) if b_cum else None,
            "cum_ratio": round(m_cum / b_cum, 3) if b_cum else None,
            "d1_main": m_d1, "d1_bench": b_d1,
            "d1_diff": m_d1 - b_d1,
            "d1_rel": round(m_d1 / b_d1 - 1, 4) if b_d1 else None,
            "d1_share_of_gap": (round((m_d1 - b_d1) / (m_cum - b_cum), 4)
                                if (m_cum - b_cum) else None),
        }
    return out


# ─────────────────────────── 终端 / JSON 输出 ───────────────────────────

def gap_narrative(d: dict, n: int) -> str:
    """把「D1 占总差额 X%」改写成可读的差额结构叙述。

    例：D1 领先 915 单，D2–D5 净回吐 873 单，最终领先 42 单。
    极小差额时占比没有意义，叙述式表达更稳。
    """
    d1 = int(round(d.get("d1_diff") or 0))
    cum = int(round(d.get("cum_diff") or 0))
    tail = cum - d1

    def _lead(v: int) -> str:
        return f"领先 {abs(v):,} 单" if v > 0 else (f"落后 {abs(v):,} 单" if v < 0 else "持平")

    if d1 == 0:
        head = "D1 持平"
    else:
        head = f"D1 {_lead(d1)}"
    if tail == 0:
        mid = f"D2–D{n} 持平"
    elif d1 and tail * d1 < 0:
        mid = f"D2–D{n} 净回吐 {abs(tail):,} 单"
    else:
        mid = f"D2–D{n} 再{'领先' if tail > 0 else '落后'} {abs(tail):,} 单"
    return f"{head}，{mid}，最终{_lead(cum)}"


def render_terminal(ctx: dict) -> str:
    main, n = ctx["main"], ctx["n_days"]
    c = ctx["curves"]["curves"]
    lines = ["[Summary]"]
    disp = " / ".join(f"{g}：{_fmt_int(c[g]['cum'][-1])}" for g in ctx["curves"]["gens"])
    lines.append(f"  {main} 上市 D1–D{n} 零售锁单累计 —— {disp}")
    for b, d in ctx["deltas"].items():
        lines.append(f"  对 {b}：{d['cum_diff']:+,} 单（相对基准 {d['cum_rel'] * 100:+.1f}%）；"
                     f"{gap_narrative(d, n)}")
    lines.append("")
    lines.append("[Scope]")
    for g in ctx["curves"]["gens"]:
        w = ctx["windows"][g]
        ps = ctx["presale"][g]
        lines.append(f"  {g}: 上市 {w['launch']} · 窗口 D1–D{n}（{w['launch']} ~ "
                     f"{c[g]['dates'][-1]}，{w['weekdays'][0]}~{w['weekdays'][-1]}）· "
                     f"预售 {ps['presale_days']} 天 · 预售池 {_fmt_int(ps['pool_total'])}")
    lines.append(f"  数据截至 {ctx['as_of']}（T-1）· 口径：上市观察口径"
                 f"（用户车零售单，剔除测试单/内测店/试驾车等非零售）")
    lines.append("")
    lines.append("[Result]")
    lines.append("  每日新增 / 累计：")
    for g in ctx["curves"]["gens"]:
        lines.append(f"    {g}: daily={c[g]['daily']} cum={c[g]['cum']}")
    lines.append("  预售池 → D_N 转化：")
    for g in ctx["curves"]["gens"]:
        p = ctx["presale"][g]
        lines.append(f"    {g}: 池 {p['pool_total']:,} · 锁单 {p['pool_locked']:,} "
                     f"({_fmt_int(p['pool_lock_rate'] * 100)}%) · 退订 {p['pool_refunded']:,} "
                     f"({p['pool_refund_rate'] * 100:.1f}%) · 待转化 {p['pool_pending']:,}")
    return "\n".join(lines)


def save_tables(ctx: dict, out_dir: Path) -> dict:
    """三车型同期对比数据表（CSV）+ 关键指标 JSON。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    curves = ctx["curves"]["curves"]

    rows = []
    for i in range(ctx["n_days"]):
        row = {"day": f"D{i + 1}"}
        for g in ctx["curves"]["gens"]:
            row[f"{g}_date"] = curves[g]["dates"][i]
            row[f"{g}_weekday"] = curves[g]["weekdays"][i]
            row[f"{g}_daily"] = curves[g]["daily"][i]
            row[f"{g}_cum"] = curves[g]["cum"][i]
        for b in ctx["benchmarks"]:
            gd = ctx["curves"]["gaps"][b]
            row[f"gap_cum_{b}"] = gd["cum_gap"][i]
            row[f"gap_marginal_{b}"] = gd["marginal"][i]
        rows.append(row)
    p = out_dir / "table_01_daily_cumulative.csv"
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")
    paths["daily_cumulative"] = str(p)

    rows = []
    for g in ctx["curves"]["gens"]:
        d = ctx["dynamics"][g]
        ps = ctx["presale"][g]
        o = ctx["origin"][g]
        q = ctx["quality"].get(g, {})
        net = ctx["network"][g]
        rows.append({
            "gen": g, "launch": ctx["windows"][g]["launch"], "n_days": ctx["n_days"],
            "cum_locks": d["cum_total"], "d1_locks": d["d1"],
            "d1_share_pct": round(d["d1_share_of_cum"] * 100, 1) if d["d1_share_of_cum"] else None,
            "tail_avg_daily": d["tail_avg"], "d2_over_d1": d["d2_over_d1"],
            "tail_cv": d["tail_cv"],
            "presale_days": ps["presale_days"], "presale_pool": ps["pool_total"],
            "presale_locked": ps["pool_locked"],
            "presale_lock_rate_pct": round(ps["pool_lock_rate"] * 100, 1) if ps["pool_lock_rate"] else None,
            "presale_refund_rate_pct": round(ps["pool_refund_rate"] * 100, 1) if ps["pool_refund_rate"] else None,
            "origin_presale_locks": o.get("pre"), "origin_launch_locks": o.get("launch"),
            "origin_direct_locks": o.get("none"),
            "pending_pool": ctx["forward"][g]["pending_total"],
            "deposit_refund_rate_pct": round(q.get("deposit_refund_rate", 0) * 100, 2),
            "active_stores": net["stores_with_gen"], "locks_per_store": net["locks_per_store"],
            "store_penetration_pct": round(net["gen_store_penetration"] * 100, 1)
            if net["gen_store_penetration"] else None,
        })
    p = out_dir / "table_02_same_period_summary.csv"
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")
    paths["same_period_summary"] = str(p)

    rows = []
    for dim in ("province", "tier", "zone"):
        for b in ctx["benchmarks"]:
            for z in ctx["geo"][dim]["gaps"][b]:
                rows.append({"dim": dim, "benchmark": b, "unit": z[dim],
                             "main": z["main"], "bench": z["bench"],
                             "main_share": round(z["main_share"] * 100, 1),
                             "bench_share": round(z["bench_share"] * 100, 1),
                             "share_diff_pp": z["share_diff_pp"],
                             "abs_diff": z["abs_diff"], "scale_effect": z["scale_effect"],
                             "mix_effect": z["mix_effect"]})
    p = out_dir / "table_03_region_decomposition.csv"
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")
    paths["region_decomposition"] = str(p)

    rows = []
    for b in ctx["benchmarks"]:
        for cty in ctx["geo"]["city"]["gaps"][b]["rows"][:15]:
            rows.append({"benchmark": b, "city": cty["city"], "main": cty["main"],
                         "bench": cty["bench"], "abs_diff": cty["abs_diff"],
                         "mix_effect": cty["mix_effect"]})
    p = out_dir / "table_04_city_gap.csv"
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")
    paths["city_gap"] = str(p)

    rows = []
    for g in ctx["curves"]["gens"]:
        p_ = ctx["presale"][g]
        o = ctx["origin"][g]
        f = ctx["forward"][g]
        rows.append({
            "gen": g, "presale_start": p_["presale_start"], "launch": p_["launch"],
            "presale_days": p_["presale_days"], "pool_total": p_["pool_total"],
            "pool_refunded": p_["pool_refunded"], "pool_retained": p_["pool_retained"],
            "pool_locked": p_["pool_locked"], "pool_pending": p_["pool_pending"],
            "pool_lock_rate": round(p_["pool_lock_rate"] * 100, 1) if p_["pool_lock_rate"] else None,
            "pool_refund_rate": round(p_["pool_refund_rate"] * 100, 1) if p_["pool_refund_rate"] else None,
            "launch_intent_total": p_["launch_intent_total"],
            "post_launch_intent_total": p_["post_launch_intent_total"],
            "launch_intent_locked": p_["launch_intent_locked"],
            "nopay_orders": p_["nopay_orders"], "nopay_locked": p_["nopay_locked"],
            "pending_total": f["pending_total"],
            "pending_deposit_not_locked": f["pending_deposit_not_locked"],
            "pending_intent_only": f["pending_intent_only"],
            "locks_from_presale": o.get("pre"), "locks_from_launch_intent": o.get("launch"),
            "locks_direct": o.get("none"),
        })
    p = out_dir / "table_05_presale_funnel.csv"
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")
    paths["presale_funnel"] = str(p)

    rows = []
    for g in ctx["curves"]["gens"]:
        n = ctx["network"][g]
        rows.append({
            "gen": g, "locks": n["locks"],
            "active_stores_all_series": n["active_stores_all_series"],
            "stores_with_gen": n["stores_with_gen"],
            "gen_store_penetration": round(n["gen_store_penetration"] * 100, 1)
            if n["gen_store_penetration"] else None,
            "locks_per_store": n["locks_per_store"],
            "median_store_locks": n["median_store_locks"],
            "single_lock_store_share": round(n["single_lock_store_share"] * 100, 1)
            if n["single_lock_store_share"] is not None else None,
            "cities_with_gen": n["cities_with_gen"], "bloc_count": n["bloc_count"],
            "top10_store_share": round(n["top10_store_share"] * 100, 1)
            if n["top10_store_share"] else None,
            "top_formats": json.dumps(n["store_format_mix"], ensure_ascii=False),
        })
    p = out_dir / "table_06_store_network.csv"
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")
    paths["store_network"] = str(p)

    rows = []
    for g in ctx["curves"]["gens"]:
        pr = ctx["product"][g]
        if not pr.get("n"):
            continue
        for v in pr["versions"][:6]:
            rows.append({"gen": g, "dim": "version", "key": v["version"],
                         "locks": v["locks"], "share": round(v["share"] * 100, 1)})
        for k, v in pr["battery"].items():
            rows.append({"gen": g, "dim": "battery", "key": k,
                         "locks": round(v * pr["n"]), "share": round(v * 100, 1)})
        for attr, a in pr["attrs"].items():
            for item in a["top"]:
                rows.append({"gen": g, "dim": f"attr:{attr}", "key": item["value"],
                             "locks": round(item["share"] * a["n"]),
                             "share": round(item["share"] * 100, 1)})
            for norm_key in ("color_family", "interior_tone", "wheel_size"):
                norm = a["normalized"].get(norm_key)
                if norm:
                    for k, v in norm.items():
                        rows.append({"gen": g, "dim": f"{norm_key}", "key": k,
                                     "locks": round(v * a["n"]), "share": round(v * 100, 1)})
    p = out_dir / "table_07_product_mix.csv"
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")
    paths["product_mix"] = str(p)

    # 08 小订池消耗（封盘池 / 锁单速度 / 退订速度 / 比值）
    rows = []
    pool = ctx.get("pool", {})
    for g in ctx["curves"]["gens"]:
        v = pool.get(g, {})
        rows.append({
            "gen": g,
            "stock_total": v.get("stock_total"),
            "stock_presale": v.get("stock_presale"),
            "stock_launch_day": v.get("stock_launch_day"),
            "locked": v.get("locked"),
            "refunded": v.get("refunded"),
            "remaining": v.get("remaining"),
            "locked_rate_pct": (round(v["locked_rate"] * 100, 1)
                                if v.get("locked_rate") is not None else None),
            "refund_rate_pct": (round(v["refund_rate"] * 100, 1)
                                if v.get("refund_rate") is not None else None),
            "remaining_rate_pct": (round(v["remaining_rate"] * 100, 1)
                                   if v.get("remaining_rate") is not None else None),
            "lock_d1": v.get("lock_d1"),
            "lock_tail_daily": v.get("lock_tail_daily"),
            "refund_tail_daily": v.get("refund_tail_daily"),
            "lock_refund_ratio_stock": v.get("lock_refund_ratio_stock"),
            "lock_refund_ratio_tail": v.get("lock_refund_ratio_tail"),
            "lock_daily": "/".join(str(x) for x in (v.get("lock_daily") or [])),
            "refund_daily": "/".join(str(x) for x in (v.get("refund_daily") or [])),
        })
    p = out_dir / "table_08_pool_consumption.csv"
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")
    paths["pool_consumption"] = str(p)

    # 09 省份渠道 × 需求分解
    rows = []
    for b in ctx["benchmarks"]:
        gd = ctx["channel"]["gaps"][b]
        for r in gd["rows"]:
            rows.append({"benchmark": b, **r})
    p = out_dir / "table_09_province_channel.csv"
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")
    paths["province_channel"] = str(p)

    # 10 线级 × 版型矩阵
    rows = []
    for g in ctx["curves"]["gens"]:
        tv = ctx["product"][g].get("tier_x_version") or {}
        for t in tv.get("tiers", []):
            for v in tv.get("versions", []):
                rows.append({"gen": g, "tier": t, "version": v,
                             "locks": tv["count"][t][v],
                             "share_in_tier_pct": round(tv["share"][t][v] * 100, 1)})
    p = out_dir / "table_10_tier_version_matrix.csv"
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")
    paths["tier_version_matrix"] = str(p)

    p = out_dir / "metrics.json"
    p.write_text(json.dumps(ctx, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    paths["metrics_json"] = str(p)
    return paths


def build_contract(ctx: dict, artifacts: dict) -> dict:
    return {
        "status": "success",
        "script": "workspace/research_scripts/launch_deep_dive.py",
        "scope": {
            "data_source": "dataset/order_data.parquet + dataset/config_attribute.parquet "
                           "+ 门店主数据（store_info）",
            "time_window": {
                "as_of": ctx["as_of"],
                "n_days": ctx["n_days"],
                "windows": ctx["windows"],
            },
            "filters": {
                "generation_logic": "shared/schema/business_definition.json series_group_logic",
                "retail": "order_type ∈ {用户车, 空} 且排除 NON_RETAIL",
                "test_orders": "flag_test_orders（总部主理店 + 非18位身份证）",
                "dedup": "order_number 去重",
            },
            "metric_definition": "零售锁单 = lock_time 非空的 COUNTD(order_number)；"
                                 "窗口 = [上市日, 上市日+N)，N 由 as-of 推导",
        },
        "result": {
            "summary": _summary_text(ctx),
            "metrics": {
                "n_days": ctx["n_days"],
                "cum_locks": {g: ctx["curves"]["curves"][g]["cum"][-1]
                              for g in ctx["curves"]["gens"]},
                "deltas": ctx["deltas"],
                "presale_pool": {g: ctx["presale"][g]["pool_total"] for g in ctx["curves"]["gens"]},
                "presale_lock_rate": {g: ctx["presale"][g]["pool_lock_rate"]
                                      for g in ctx["curves"]["gens"]},
                "pending_pool": {g: ctx["forward"][g]["pending_total"]
                                 for g in ctx["curves"]["gens"]},
                "pool_stock": {g: ctx["pool"][g]["stock_total"] for g in ctx["curves"]["gens"]},
                "pool_remaining": {g: ctx["pool"][g]["remaining"] for g in ctx["curves"]["gens"]},
                "lock_refund_ratio": {g: ctx["pool"][g]["lock_refund_ratio_stock"]
                                      for g in ctx["curves"]["gens"]},
                "instant_locks": {g: ctx["behavior"][g]["instant_locks"]
                                  for g in ctx["curves"]["gens"]},
                "context_days": ctx["context"]["context_days"],
            },
            "tables": [
                {"name": "daily_cumulative", "path": artifacts.get("daily_cumulative")},
                {"name": "same_period_summary", "path": artifacts.get("same_period_summary")},
                {"name": "region_decomposition", "path": artifacts.get("region_decomposition")},
                {"name": "presale_funnel", "path": artifacts.get("presale_funnel")},
                {"name": "store_network", "path": artifacts.get("store_network")},
                {"name": "product_mix", "path": artifacts.get("product_mix")},
                {"name": "pool_consumption", "path": artifacts.get("pool_consumption")},
                {"name": "province_channel", "path": artifacts.get("province_channel")},
                {"name": "tier_version_matrix", "path": artifacts.get("tier_version_matrix")},
            ],
        },
        "artifacts": artifacts,
        "followup_context": {
            "metric": "cumulative_retail_lock",
            "main_gen": ctx["main"],
            "benchmarks": ctx["benchmarks"],
            "window": f"D1-D{ctx['n_days']}",
            "available_dimensions": ["region", "city", "store", "product_version",
                                     "battery", "exterior_color", "interior", "wheel",
                                     "gender", "age", "presale_origin"],
        },
        "warnings": _warnings(ctx),
        "errors": [],
    }


def _summary_text(ctx: dict) -> str:
    m = ctx["main"]
    c = ctx["curves"]["curves"]
    parts = [f"{m} 上市 D1–D{ctx['n_days']} 零售锁单 {_fmt_int(c[m]['cum'][-1])} 单"]
    for b, d in ctx["deltas"].items():
        parts.append(f"{b} {_fmt_int(d['cum_bench'])} 单（{d['cum_rel'] * 100:+.1f}%）")
    return "；".join(parts)


def _warnings(ctx: dict) -> list[str]:
    w = []
    audit = ctx["audit"]
    if ctx.get("window_capped"):
        w.append(f"主代际理论窗口 {ctx['n_days_intended']} 天，但部分参照代际可观察天数不足，"
                 f"已按共同可覆盖的 {ctx['n_days']} 天收窗（不补零、不用缺失当零值）")
    if not audit["data_covers_as_of"]:
        w.append(f"order_data 最新锁单日早于 as-of {ctx['as_of']}，窗口末段可能未覆盖")
    for g, a in audit["gen"].items():
        if a["days_covered"] < a["n_days"]:
            w.append(f"{g} 窗口内只有 {a['days_covered']}/{a['n_days']} 天有锁单记录（零值非缺失，已按 0 计）")
        last_ok = ctx["windows"][g]["window_end_exclusive"]
        last_day = (pd.Timestamp(last_ok) - pd.Timedelta(days=1)).date().isoformat()
        if a.get("max_lock_normalized_date") and a["max_lock_normalized_date"] < last_day:
            w.append(f"{g} 锁单数据仅覆盖到 {a['max_lock_normalized_date']}（窗口最后一日应为 "
                     f"{last_day}），缺口日不补零、按缺失处理；该代际同期累计可能被低估")
    if audit["order_number_dup"]:
        w.append(f"order_number 存在 {audit['order_number_dup']} 条重复")
    w.append("历史车型「无小订记录直锁」占比与其下单流程有关，跨代际不可直接解释为直接需求强弱")
    w.append("门店主数据为当前快照，门店→经销商/形态映射非 PIT")
    w.append(f"试驾/下发线索数据无 {ctx['main']} 单车型维度，仅作同期渠道信号，不计算客户级转化")
    if ctx["context"]["context_days"]:
        w.append(f"D{ctx['n_days']+1}–D{ctx['context']['context_days']} 参考曲线仅用于展示对标释放形状，"
                 "不参与任何差异计算与结论")
    return w


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="新车上市深度研究（等生命周期跨代际对比）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gen", required=True, help="目标代际键（如 LS8Neo）")
    ap.add_argument("--benchmarks", nargs="+", required=True, help="对标代际键（如 CM3 LS8）")
    ap.add_argument("--as-of", default=datetime.now().strftime("%Y-%m-%d"),
                    help="数据观察截止日 T-1（最后完整观察日）")
    ap.add_argument("--format", default="terminal",
                    choices=["terminal", "json", "html", "all"])
    ap.add_argument("--output", default=str(_WS / "outputs"), help="产物根目录")
    ap.add_argument("--context-days", type=int, default=30,
                    help="Q1 参考延长线的天数（默认 30；仅用于展示释放形状，不参与差异计算；0=关闭）")
    ap.add_argument("--export-charts", action="store_true",
                    help="额外导出 7 张图表 PNG 到 outputs/charts/（需 kaleido）")
    args = ap.parse_args(argv)

    as_of = pd.Timestamp(args.as_of).normalize()
    out_root = Path(args.output).resolve()
    ctx, _df = build_context(args.gen, args.benchmarks, as_of, args.context_days)

    tag = f"{ctx['main']}_D{ctx['n_days']}"
    table_dir = out_root / "tables" / "launch_deep_dive" / tag
    paths = save_tables(ctx, table_dir)

    if args.format in ("html", "all"):
        from research_scripts.launch_deep_dive_report import render_report  # 局部导入避免循环
        report = render_report(ctx, out_root)
        paths["report_html"] = str(report)
        from research_scripts.launch_deep_dive_report import (
            export_charts, render_method_doc,
        )
        paths["method_doc"] = str(render_method_doc(ctx, out_root))
    if args.export_charts:
        from research_scripts.launch_deep_dive_report import export_charts
        pngs = export_charts(ctx, out_root, prefix=f"{ctx['main']}_D{ctx['n_days']}")
        paths["charts_png"] = [str(p) for p in pngs]

    contract = build_contract(ctx, paths)
    if args.format in ("json", "all"):
        p = table_dir / "result_contract.json"
        p.write_text(json.dumps(contract, ensure_ascii=False, indent=2, default=str),
                     encoding="utf-8")
        print(json.dumps(contract, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_terminal(ctx))
        if paths.get("report_html"):
            print(f"\n[Output]\n  HTML: {paths['report_html']}")
        print(f"  数据表 / metrics: {table_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
