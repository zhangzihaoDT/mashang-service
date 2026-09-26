#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
门店 → 经销商主体画像

输入门店（简称或全名），返回：
  1) 经销商主体（Bloc）、大区、该主体在营门店数与城市分布
  2) 近期主理数量（无独立主理时标注并回落关联车城店）
  3) 近 N 日锁单（该店 + 该主体合计 + 主体内排名/占比/水平 + 车系分布）
  4) CM3 预售开始后的留存小订（该店 + 该主体合计 + 主体内占比）

口径:
  - 数据源: store_info.csv（门店主数据，经 store_info_loader 读取）
  - 经销商主体 = Bloc Name（集团/投资人）；一个 Bloc 可跨多个税号（法人主体）
  - 门店数 = 按 Dealer Name Fc 去重（同门店名可有多个职能 Dealer Code）
  - 在营 = Store Create Status Desc ∈ --status（默认『开业』；可传『开业,暂停』放宽）
  - 城市分布 = 该主体在营门店按 City Name 去重计数
  - 近期主理 = 主理名册（dataset/主理信息表.csv，由 dataset/updater/store_daily_zhuli_to_csv.py
    更新）中该店在职主理数；无独立主理的门店（如 popup 城市展厅）回落同主体同城市车城店
  - 锁单/留存小订 = order_data.parquet；锁单窗口 = 截至 --as-of（默认订单最大锁单日）的近
    --window-days 日；留存小订 = series_group=CM3 且意向金时间 ∈ [预售开放, 截止) 且未退意向金；
    无独立订单口径的门店回落关联车城店
  - 主体内排名的**分母统一 = 该主体全部在营门店数**（store_info 状态∈--status，无数据记 0）；
    名词 = 1 + 数值高于本店的门店数（并列取同名次）

用法:
    python runtime_scripts/store_dealer_profile.py 遵义吾悦广场城市展厅 重庆万州万达城市展厅
    python runtime_scripts/store_dealer_profile.py --store 遵义吾悦广场城市展厅
    python runtime_scripts/store_dealer_profile.py --store 遵义吾悦广场城市展厅 --status 开业,暂停
    python runtime_scripts/store_dealer_profile.py --store 遵义吾悦广场城市展厅 --as-of 2026-09-16 --window-days 7
    python runtime_scripts/store_dealer_profile.py --store 遵义吾悦广场城市展厅 --format json
    python runtime_scripts/store_dealer_profile.py --store 遵义吾悦广场城市展厅 --format csv --output outputs/tables/
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(_WS_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.loaders import store_info_loader as sl  # noqa: E402
from utils.result_contract import (  # noqa: E402
    build_success_contract,
    save_contract_json,
)

COLUMNS = ["门店", "经销商主体 (Bloc)", "大区", "该主体门店数(在营)", "城市分布"]
ZHULI_COLUMNS = ["门店", "近期主理数量", "主理归属说明"]
DEFAULT_IN_OPERATION = "开业"
UNMATCHED = "未匹配"
NO_OWN_ZHULI = "无独立主理"

# 主理数据（Tableau 导出；dataset/updater/store_daily_zhuli_to_csv.py）
#   主理信息表 = 主理名册（权威主理数量）；门店日报_主理_当月 = 主理在岗统计（门店类型）
ZHULI_ROSTER_CSV = REPO_ROOT / "dataset" / "主理信息表.csv"
ZHULI_ZAIGANG_CSV = REPO_ROOT / "dataset" / "门店日报_主理_当月.csv"

# 订单数据（近 N 日锁单 / CM3 预售留存小订）
ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
LOCK_COLUMNS = ["门店", "近7日锁单", "车系分布", "该主体近7日锁单", "锁单主体内排名", "锁单主体内占比", "水平"]
PRESALE_COLUMNS = ["门店", "统计门店", "CM3留存小订", "该主体CM3留存小订", "CM3主体内占比", "小订/线索"]

# 每日下发线索（by门店；增量库；dataset/updater/store_daily_leads_to_csv.py）
LEADS_CSV = REPO_ROOT / "dataset" / "store_daily_leads.csv"
LEADS_COLUMNS = ["门店", "近7日下发线索", "该主体近7日下发线索", "线索主体内排名", "线索主体内占比"]


def _norm(s: Any) -> str:
    import re
    return re.sub(r"[\s（）()]+", "", str(s or ""))


def _longest_common_substring(a: str, b: str) -> int:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def load_zhuli():
    """加载主理名册（主理信息表），并补上门店类型。返回 DataFrame 或 None。

    门店类型取自「主理在岗统计」(门店日报_主理_当月.csv)，用于回落关联车城店。
    """
    if not ZHULI_ROSTER_CSV.exists():
        return None
    roster = pd.read_csv(ZHULI_ROSTER_CSV, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    kind = {}
    if ZHULI_ZAIGANG_CSV.exists():
        z = pd.read_csv(ZHULI_ZAIGANG_CSV, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        if "门店类型" not in z.columns and "门店类型 " in z.columns:
            z = z.rename(columns={"门店类型 ": "门店类型"})
        kind = (z.drop_duplicates("门店名称").set_index("门店名称")["门店类型"].to_dict()
                if "门店类型" in z.columns else {})
    roster["门店类型"] = roster["门店"].map(lambda s: kind.get(s, ""))
    return roster


def _zhuli_count(df) -> int:
    return int(df["主理"].nunique())


def resolve_zhuli(store_name: str, info: dict | None, zhuli) -> dict:
    """解析门店的近期主理：独立主理 / 无独立主理（回落关联车城店）。

    返回 {own: bool, count: int|None, store_kind: str, parent_store: str|None,
          parent_count: int|None}
    """
    empty = {"own": False, "count": None, "store_kind": "", "parent_store": None, "parent_count": None}
    if zhuli is None or zhuli.empty:
        return dict(empty)
    if "在职状态" in zhuli.columns:
        zhuli = zhuli[zhuli["在职状态"] == "在职"]

    name = _norm(store_name)
    z = zhuli.assign(_n=zhuli["门店"].map(_norm))
    # 1) 直接命中（简称/全名互为子串）
    hit = z[z["_n"].map(lambda s: bool(s) and (s in name or name in s))]
    if not hit.empty:
        matched = hit.iloc[0]["门店"]
        sub = z[z["门店"] == matched]
        return {
            "own": True,
            "count": _zhuli_count(sub),
            "store_kind": str(sub.iloc[0].get("门店类型", "") or ""),
            "parent_store": None,
            "parent_count": None,
        }

    # 2) 无独立主理 → 回落同主体同城市的「车城店」
    if not info:
        return dict(empty)
    bloc = info.get("bloc_name") or ""
    city = (info.get("city_name") or "").replace("市", "")
    cand = z[z["经销商主体"] == bloc]
    if city:
        same = cand[cand["城市"].str.replace("市", "", regex=False) == city]
        cand = same if not same.empty else cand
    cand = cand[cand["门店类型"] == "车城店"]
    if cand.empty:
        return dict(empty)
    target = info.get("dealer_name_fc") or store_name
    scored = cand.assign(_s=cand["门店"].map(lambda s: _longest_common_substring(target, s)))
    parent = scored.sort_values("_s", ascending=False).iloc[0]
    pname = parent["门店"]
    psub = z[z["门店"] == pname]
    return {
        "own": False,
        "count": None,
        "store_kind": "",
        "parent_store": str(pname),
        "parent_count": _zhuli_count(psub),
    }


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description="门店 → 经销商主体画像")
    p.add_argument("stores", nargs="*", help="门店简称或全名（可多个）")
    p.add_argument("--store", dest="store_opts", action="append", default=[],
                   help="门店（可重复传参）")
    p.add_argument("--status", default=DEFAULT_IN_OPERATION,
                   help="在营门店状态，逗号分隔（默认『开业』；可传『开业,暂停』）")
    p.add_argument("--as-of", dest="as_of", help="锁单/预售观测截止日 YYYY-MM-DD（默认订单数据最大锁单日）")
    p.add_argument("--window-days", type=int, default=7, help="近期锁单窗口天数（默认 7）")
    p.add_argument("--format", default="terminal", choices=["terminal", "json", "csv"])
    p.add_argument("--output", help="输出目录（csv/json 落盘）")
    return p.parse_args(argv)


# ── 订单：近 N 日锁单 / CM3 预售留存小订 ──────────────────────

def load_order_metrics(as_of: str | None = None, window_days: int = 7,
                       presale_gen: str = "CM3") -> dict | None:
    """读取 order_data，计算近 window_days 日锁单与 presale_gen 预售留存小订（按门店）。

    返回 {as_of, window_days, presale_gen, presale_open,
          lock_by_store, cm3_by_store, bloc_of, order_store_names}
    """
    if not ORDER_PARQUET.exists():
        return None
    from utils.monitors.series_group import apply_series_group_logic
    from utils.monitors.phase import load_business_definition, open_hour, open_minute

    bd = load_business_definition(BUSINESS_DEF)
    df = pd.read_parquet(ORDER_PARQUET, columns=[
        "order_number", "store_name", "series", "product_name",
        "lock_time", "intention_payment_time", "intention_refund_time",
    ])
    for c in ("lock_time", "intention_payment_time", "intention_refund_time"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df = apply_series_group_logic(df, bd)

    if as_of is None:
        as_of_ts = pd.Timestamp(df["lock_time"].max()).normalize()
    else:
        as_of_ts = pd.Timestamp(as_of).normalize()
    start = as_of_ts - pd.Timedelta(days=window_days - 1)
    end = as_of_ts + pd.Timedelta(days=1)

    w = df[(df["lock_time"] >= start) & (df["lock_time"] < end)]
    lock_by_store = w.groupby("store_name")["order_number"].nunique()
    lock_series = w.groupby(["store_name", "series"])["order_number"].nunique()

    tp = bd.get("time_periods", {}).get(presale_gen, {})
    presale_open = None
    cm3_by_store = pd.Series(dtype="int64")
    if tp.get("start"):
        presale_open = pd.Timestamp(tp["start"]) + pd.Timedelta(
            hours=open_hour(bd, presale_gen), minutes=open_minute(bd, presale_gen))
        sel = df[(df["series_group_logic"] == presale_gen)
                 & (df["intention_payment_time"] >= presale_open)
                 & (df["intention_payment_time"] < end)
                 & (df["intention_refund_time"].isna() | (df["intention_refund_time"] >= end))]
        cm3_by_store = sel.groupby("store_name")["order_number"].nunique()

    order_store_names = sorted({str(x) for x in list(lock_by_store.index) + list(cm3_by_store.index)})
    bloc_of = {n: ((sl.resolve_dealer_info(n) or {}).get("bloc_name") or "") for n in order_store_names}
    return {
        "as_of": as_of_ts,
        "window_days": window_days,
        "presale_gen": presale_gen,
        "presale_open": presale_open,
        "lock_by_store": lock_by_store,
        "lock_series": {(str(s), str(se)): int(c) for (s, se), c in lock_series.items()},
        "cm3_by_store": cm3_by_store,
        "bloc_of": bloc_of,
        "order_store_names": order_store_names,
    }


def match_order_store(store_name: str, info: dict | None, order_store_names: list[str],
                      parent_store: str | None = None) -> tuple[str | None, bool]:
    """把门店匹配到订单侧 store_name；匹配不到时回落关联车城店。

    返回 (order_store_name, is_fallback)。
    """
    cands = [store_name, (info or {}).get("dealer_name_fc") or ""]
    for c in cands:
        cn = _norm(c)
        if not cn:
            continue
        best, best_len = None, 0
        for n in order_store_names:
            nn = _norm(n)
            if cn in nn or nn in cn:
                if len(nn) > best_len:
                    best, best_len = n, len(nn)
        if best:
            return best, False
    if parent_store:
        pn = _norm(parent_store)
        for n in order_store_names:
            if pn and (pn in _norm(n) or _norm(n) in pn):
                return n, True
    return None, False


def load_leads_metrics(as_of=None, window_days: int = 7) -> dict | None:
    """读取每日下发线索（by门店）增量库，聚合近 window_days 日每店下发线索数。

    返回 {as_of, window_days, leads_by_store, bloc_of, store_names}
    """
    if not LEADS_CSV.exists():
        return None
    df = pd.read_csv(LEADS_CSV, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    df["下发线索数"] = pd.to_numeric(df["下发线索数"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["日期"])
    if df.empty:
        return None
    as_of_ts = pd.Timestamp(as_of).normalize() if as_of else pd.Timestamp(df["日期"].max()).normalize()
    start = as_of_ts - pd.Timedelta(days=window_days - 1)
    w = df[(df["日期"] >= start) & (df["日期"] <= as_of_ts)]
    by_store = w.groupby("门店")["下发线索数"].sum()
    store_names = sorted({str(x) for x in by_store.index})
    bloc_of = {n: ((sl.resolve_dealer_info(n) or {}).get("bloc_name") or "") for n in store_names}
    return {
        "as_of": as_of_ts,
        "window_days": window_days,
        "leads_by_store": by_store,
        "bloc_of": bloc_of,
        "store_names": store_names,
    }


def _leads_cells(store: str, info: dict | None, z: dict, lm: dict | None,
                 n_stores: int | None = None) -> dict:
    """计算某门店的近 N 日下发线索数（含主体内排名/占比，无独立口径时回落车城店）。"""
    res = {"近7日下发线索": None, "该主体近7日下发线索": None,
           "线索主体内排名": "—", "线索主体内占比": "—", "leads_store": None,
           "leads_fallback": False, "leads_note": "无下发线索数据"}
    if not lm or not info:
        return res
    lstore, fb = match_order_store(store, info, lm["store_names"], z.get("parent_store"))
    if not lstore:
        return res
    res["leads_store"] = lstore
    res["leads_fallback"] = fb
    res["leads_note"] = f"回落关联车城店：{lstore}" if fb else f"独立门店：{lstore}"
    bloc = info.get("bloc_name") or ""
    by_store, bloc_of = lm["leads_by_store"], lm["bloc_of"]
    target = int(by_store.get(lstore, 0))
    bloc_tot = {s: int(c) for s, c in by_store.items() if bloc_of.get(s) == bloc}
    total = sum(bloc_tot.values())
    rank, n = _bloc_rank(bloc_tot, lstore, target, n_stores)
    res.update({
        "近7日下发线索": target,
        "该主体近7日下发线索": total,
        "线索主体内排名": f"第{rank}/{n}",
        "线索主体内占比": _pct(target, total),
    })
    return res


def _bloc_rank(values: dict[str, int], target: str, target_count: int,
               n_stores: int | None = None) -> tuple[int, int]:
    """返回 (排名, 分母)。

    分母统一为「该主体全部在营门店数」(n_stores)；排名 = 1 + 数值高于本店的门店数
    （窗口内无数据的门店按 0 计，不额外占位）。
    """
    rank = 1 + sum(1 for v in values.values() if v > target_count)
    n = int(n_stores) if n_stores else max(len(values), rank)
    return rank, n


def _level(rank: int, n: int) -> str:
    if n <= 1:
        return "—"
    p = 1 - (rank - 1) / (n - 1)
    if p >= 0.75:
        return "头部"
    if p >= 0.25:
        return "中位"
    return "尾部"


def _pct(a: int, b: int) -> str:
    return f"{a / b * 100:.1f}%" if b else "—"


def resolve_statuses(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def build_dealer_network(statuses: list[str]):
    """返回 (in_op_df, 主体 → 城市分布/门店数 的聚合 dict)。

    在营口径 = 状态 ∈ statuses；门店数按 Dealer Name Fc 去重。
    """
    df = sl.load_store_info()
    if df is None or df.empty:
        return df, {}
    cols = {c.lower(): c for c in df.columns}
    status_col = cols.get("store create status desc", "Store Create Status Desc")
    name_col = cols.get("dealer name fc", "Dealer Name Fc")
    bloc_col = cols.get("bloc name", "Bloc Name")
    city_col = cols.get("city name", "City Name")

    in_op = df[df[status_col].isin(statuses)].copy()
    # 去重到门店名级（同门店名多个职能 code 只算一次）
    stores = in_op.drop_duplicates(subset=[bloc_col, name_col])

    net: dict[str, dict] = {}
    for bloc, g in stores.groupby(bloc_col):
        city_counts = g.groupby(city_col)[name_col].nunique().sort_values(ascending=False)
        net[str(bloc)] = {
            "store_count": int(g[name_col].nunique()),
            "city_distribution": {
                str(city): int(cnt) for city, cnt in city_counts.items()
            },
        }
    return in_op, net


def format_city_distribution(city_counts: dict[str, int]) -> str:
    if not city_counts:
        return "—"
    return "、".join(f"{city} {cnt}" for city, cnt in city_counts.items())


def _zhuli_cells(z: dict) -> tuple[str, str]:
    """把 resolve_zhuli 结果转成 (近期主理数量, 主理归属说明)。"""
    if z.get("own"):
        kind = z.get("store_kind") or ""
        note = f"独立主理（{kind}）" if kind else "独立主理"
        return str(z.get("count")), note
    if z.get("parent_store"):
        return NO_OWN_ZHULI, f"关联车城店：{z['parent_store']}（主理 {z.get('parent_count')} 人）"
    return NO_OWN_ZHULI, "未找到关联车城店"


def _order_cells(store: str, info: dict | None, z: dict, om: dict | None,
                 n_stores: int | None = None) -> dict:
    """计算某门店的近 N 日锁单与 CM3 预售留存小订（含主体内排名/占比/水平）。"""
    res = {
        "近7日锁单": None, "该主体近7日锁单": None, "锁单主体内排名": "—",
        "锁单主体内占比": "—", "水平": "—", "车系分布": "—", "订单口径说明": "无订单数据",
        "CM3留存小订": None, "该主体CM3留存小订": None, "CM3主体内占比": "—",
        "order_store": None, "order_fallback": False, "lock_series_detail": [],
    }
    if not om or not info:
        return res
    ostore, fb = match_order_store(store, info, om["order_store_names"], z.get("parent_store"))
    if not ostore:
        return res
    res["order_store"] = ostore
    res["order_fallback"] = fb
    res["订单口径说明"] = f"回落关联车城店：{ostore}" if fb else f"独立门店：{ostore}"

    bloc = info.get("bloc_name") or ""
    lock, cm3, bloc_of = om["lock_by_store"], om["cm3_by_store"], om["bloc_of"]
    lock_target = int(lock.get(ostore, 0))
    bloc_lock = {s: int(c) for s, c in lock.items() if bloc_of.get(s) == bloc}
    bloc_lock_total = sum(bloc_lock.values())
    rank, n = _bloc_rank(bloc_lock, ostore, lock_target, n_stores)
    series_detail = sorted(
        [(se, int(c)) for (st, se), c in om["lock_series"].items() if st == ostore],
        key=lambda kv: kv[1], reverse=True,
    )
    res.update({
        "近7日锁单": lock_target,
        "车系分布": "、".join(f"{se} {c}" for se, c in series_detail) or "—",
        "lock_series_detail": [{"车系": se, "近7日锁单": c} for se, c in series_detail],
        "该主体近7日锁单": bloc_lock_total,
        "锁单主体内排名": f"第{rank}/{n}",
        "锁单主体内占比": _pct(lock_target, bloc_lock_total),
        "水平": _level(rank, n),
    })

    cm3_target = int(cm3.get(ostore, 0))
    bloc_cm3 = {s: int(c) for s, c in cm3.items() if bloc_of.get(s) == bloc}
    bloc_cm3_total = sum(bloc_cm3.values())
    res.update({
        "CM3留存小订": cm3_target,
        "该主体CM3留存小订": bloc_cm3_total,
        "CM3主体内占比": _pct(cm3_target, bloc_cm3_total),
    })
    return res


def build_rows(stores: list[str], net: dict[str, dict], zhuli=None, om: dict | None = None,
               lm: dict | None = None) -> list[dict]:
    rows: list[dict] = []
    zhuli_missing = zhuli is None or zhuli.empty
    for store in stores:
        info = sl.resolve_dealer_info(store)
        if zhuli_missing:
            z = {"own": False, "count": None, "store_kind": "", "parent_store": None, "parent_count": None}
            qty, note = "数据缺失", "未找到主理数据集（请运行 dataset/updater/store_daily_zhuli_to_csv.py）"
        else:
            z = resolve_zhuli(store, info, zhuli)
            qty, note = _zhuli_cells(z)
        bloc = (info or {}).get("bloc_name", "") or ""
        entry = net.get(bloc) or {}
        n_stores = int(entry.get("store_count", 0)) or None
        o = _order_cells(store, info, z, om, n_stores)
        l = _leads_cells(store, info, z, lm, n_stores)
        # 统计门店（CM3 实际取数的门店；popup 回落车城店）+ 小订/线索比值
        ostore = o.get("order_store")
        if ostore:
            o["统计门店"] = f"{ostore}（回落）" if o.get("order_fallback") else str(ostore)
        else:
            o["统计门店"] = "—"
        cm3_v, leads_v = o.get("CM3留存小订"), l.get("近7日下发线索")
        o["小订/线索"] = f"{cm3_v / leads_v * 100:.1f}%" if (leads_v and cm3_v is not None) else "—"
        if info is None:
            rows.append({
                "门店": store,
                "经销商主体 (Bloc)": UNMATCHED,
                "大区": "",
                "该主体门店数(在营)": None,
                "城市分布": "",
                "dealer_code": None,
                "store_format": None,
                "matched": False,
                "近期主理数量": qty,
                "主理归属说明": note,
                "zhuli_own": z.get("own", False),
                "zhuli_parent_store": z.get("parent_store"),
                **o, **l,
            })
            continue
        city_dist = entry.get("city_distribution", {})
        rows.append({
            "门店": store,
            "经销商主体 (Bloc)": bloc,
            "大区": info.get("region_name", "") or "",
            "该主体门店数(在营)": int(entry.get("store_count", 0)),
            "城市分布": format_city_distribution(city_dist),
            "dealer_code": info.get("dealer_code", ""),
            "store_format": info.get("store_format", ""),
            "matched": True,
            "近期主理数量": qty,
            "主理归属说明": note,
            "zhuli_own": z.get("own", False),
            "zhuli_parent_store": z.get("parent_store"),
            **o, **l,
        })
    return rows


def render_terminal(rows: list[dict], statuses: list[str], zhuli_loaded: bool,
                    om: dict | None, lm: dict | None) -> str:
    lines = []
    lines.append("[Summary]")
    lines.append(f"  门店 → 经销商主体画像（在营口径: {'/'.join(statuses)}）")
    lines.append("")
    lines.append("[Scope]")
    lines.append(f"  数据源: {sl.get_store_info_csv_path()}")
    lines.append(f"          {ZHULI_ROSTER_CSV}（主理名册，{'有' if zhuli_loaded else '缺失'}）")
    lines.append(f"          {ORDER_PARQUET}（订单，{'有' if om else '缺失'}）")
    lines.append(f"          {LEADS_CSV}（下发线索，{'有' if lm else '缺失'}）")
    lines.append("  口径: 经销商主体=Bloc Name; 门店数按 Dealer Name Fc 去重; 在营状态=" + "/".join(statuses))
    if om:
        lines.append(f"  订单窗口: 近 {om['window_days']} 日（截至 {om['as_of'].date()}）; "
                     f"{om['presale_gen']} 预售开放 {str(om['presale_open'])[:16]}（留存小订，未退口径）")
    if lm:
        lines.append(f"  线索窗口: 近 {lm['window_days']} 日（截至 {lm['as_of'].date()}）")
    lines.append("")
    lines.append("[Result]")
    lines.append("\t".join(COLUMNS))
    for r in rows:
        lines.append("\t".join([
            str(r["门店"]),
            str(r["经销商主体 (Bloc)"]),
            str(r["大区"]),
            "" if r["该主体门店数(在营)"] is None else str(r["该主体门店数(在营)"]),
            str(r["城市分布"]),
        ]))
    lines.append("")
    lines.append("[主理]")
    lines.append("\t".join(ZHULI_COLUMNS))
    for r in rows:
        lines.append("\t".join([str(r["门店"]), str(r["近期主理数量"]), str(r["主理归属说明"])]))
    lines.append("")
    lines.append("[下发线索]")
    lines.append("\t".join(LEADS_COLUMNS))
    for r in rows:
        lines.append("\t".join([
            str(r["门店"]),
            "" if r["近7日下发线索"] is None else str(r["近7日下发线索"]),
            "" if r["该主体近7日下发线索"] is None else str(r["该主体近7日下发线索"]),
            str(r["线索主体内排名"]),
            str(r["线索主体内占比"]),
        ]))
    lines.append("  说明: " + "；".join(f"{r['门店']}→{r['leads_note']}" for r in rows)
                 + "（排名分母=该主体全部在营门店数）")
    lines.append("")
    lines.append("[锁单]")
    lines.append("\t".join(LOCK_COLUMNS))
    for r in rows:
        lines.append("\t".join([
            str(r["门店"]),
            "" if r["近7日锁单"] is None else str(r["近7日锁单"]),
            str(r["车系分布"]),
            "" if r["该主体近7日锁单"] is None else str(r["该主体近7日锁单"]),
            str(r["锁单主体内排名"]),
            str(r["锁单主体内占比"]),
            str(r["水平"]),
        ]))
    lines.append("  说明: " + "；".join(f"{r['门店']}→{r['订单口径说明']}" for r in rows)
                 + "（排名分母=该主体全部在营门店数）")
    lines.append("")
    lines.append(f"[{om['presale_gen']} 预售留存小订]" if om else "[预售留存小订]")
    lines.append("\t".join(PRESALE_COLUMNS))
    for r in rows:
        lines.append("\t".join([
            str(r["门店"]),
            str(r["统计门店"]),
            "" if r["CM3留存小订"] is None else str(r["CM3留存小订"]),
            "" if r["该主体CM3留存小订"] is None else str(r["该主体CM3留存小订"]),
            str(r["CM3主体内占比"]),
            str(r["小订/线索"]),
        ]))
    lines.append("  说明: 小订/线索 = CM3留存小订 ÷ 近7日下发线索（统计门店口径）")
    return "\n".join(lines)


def write_csv(rows: list[dict], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = (COLUMNS + ZHULI_COLUMNS[1:] + LEADS_COLUMNS[1:] + LOCK_COLUMNS[1:]
            + PRESALE_COLUMNS[1:])
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([
                r["门店"],
                r["经销商主体 (Bloc)"],
                r["大区"],
                "" if r["该主体门店数(在营)"] is None else r["该主体门店数(在营)"],
                r["城市分布"],
                r["近期主理数量"],
                r["主理归属说明"],
                "" if r["近7日下发线索"] is None else r["近7日下发线索"],
                "" if r["该主体近7日下发线索"] is None else r["该主体近7日下发线索"],
                r["线索主体内排名"],
                r["线索主体内占比"],
                "" if r["近7日锁单"] is None else r["近7日锁单"],
                r["车系分布"],
                "" if r["该主体近7日锁单"] is None else r["该主体近7日锁单"],
                r["锁单主体内排名"],
                r["锁单主体内占比"],
                r["水平"],
                r["统计门店"],
                "" if r["CM3留存小订"] is None else r["CM3留存小订"],
                "" if r["该主体CM3留存小订"] is None else r["该主体CM3留存小订"],
                r["CM3主体内占比"],
                r["小订/线索"],
            ])
    return out_path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stores = list(args.stores) + list(args.store_opts)
    if not stores:
        print("❌ 请至少指定一个门店（位置参数或 --store）")
        return 2
    statuses = resolve_statuses(args.status)

    _, net = build_dealer_network(statuses)
    zhuli = load_zhuli()
    om = load_order_metrics(as_of=args.as_of, window_days=args.window_days)
    lm = load_leads_metrics(as_of=args.as_of, window_days=args.window_days)
    rows = build_rows(stores, net, zhuli, om, lm)

    table_rows = [{c: r[c] for c in COLUMNS} for r in rows]
    zhuli_rows = [{c: r[c] for c in ZHULI_COLUMNS} for r in rows]
    leads_rows = [{c: r[c] for c in LEADS_COLUMNS} for r in rows]
    lock_rows = [{c: r[c] for c in LOCK_COLUMNS} for r in rows]
    presale_rows = [{c: r[c] for c in PRESALE_COLUMNS} for r in rows]
    metrics = {
        "store_count": len(rows),
        "matched_count": sum(1 for r in rows if r["matched"]),
        "own_zhuli_count": sum(1 for r in rows if r.get("zhuli_own")),
        "order_fallback_count": sum(1 for r in rows if r.get("order_fallback")),
        "leads_fallback_count": sum(1 for r in rows if r.get("leads_fallback")),
    }
    scope = {
        "data_source": str(sl.get_store_info_csv_path()),
        "zhuli_source": str(ZHULI_ROSTER_CSV),
        "order_source": str(ORDER_PARQUET),
        "leads_source": str(LEADS_CSV),
        "filters": {"stores": stores, "in_operation_status": statuses,
                    "window_days": args.window_days,
                    "as_of": str(om["as_of"].date()) if om else None,
                    "leads_as_of": str(lm["as_of"].date()) if lm else None,
                    "presale_gen": om["presale_gen"] if om else None},
        "metric_definition": ("门店 → Bloc Name; 该主体门店数=COUNTD(Dealer Name Fc), status∈在营口径; "
                              "城市分布=COUNTD by City Name; 近期主理=COUNTD(主理) by 门店, 无独立主理时回落同主体同城市车城店; "
                              "近N日下发线索=SUM(下发线索数) by 门店(增量库); "
                              "近N日锁单=COUNTD(order_number) by store_name(窗口); "
                              "排名分母统一=该主体全部在营门店数(无数据记0), 名词=1+数值更高门店数; "
                              "CM3留存小订=COUNTD(order_number) where series_group=CM3 且意向金时间∈[预售开放,截止) 且未退; "
                              "小订/线索=CM3留存小订 ÷ 近N日下发线索（统计门店口径）"),
    }
    result = {
        "summary": f"门店 → 经销商主体画像（{len(rows)} 家查询，在营口径 {'/'.join(statuses)}）",
        "metrics": metrics,
        "dimensions": [{"name": "门店", "items": [
            {"value": r["门店"], "metrics": {
                "bloc_name": r["经销商主体 (Bloc)"],
                "region_name": r["大区"],
                "dealer_store_count_in_operation": r["该主体门店数(在营)"],
                "city_distribution": r["城市分布"],
                "recent_zhuli_count": r["近期主理数量"],
                "zhuli_note": r["主理归属说明"],
                "recent_assigned_leads": r["近7日下发线索"],
                "bloc_recent_assigned_leads": r["该主体近7日下发线索"],
                "leads_note": r["leads_note"],
                "recent_lock_count": r["近7日锁单"],
                "bloc_recent_lock_count": r["该主体近7日锁单"],
                "bloc_rank": r["锁单主体内排名"],
                "bloc_lock_share": r["锁单主体内占比"],
                "level": r["水平"],
                "cm3_retained_intention": r["CM3留存小订"],
                "bloc_cm3_retained_intention": r["该主体CM3留存小订"],
                "presale_stat_store": r["统计门店"],
                "intention_to_leads_ratio": r["小订/线索"],
                "order_note": r["订单口径说明"],
            }} for r in rows
        ]}],
        "tables": [
            {"name": "store_dealer_profile", "columns": COLUMNS, "rows": table_rows},
            {"name": "store_zhuli_profile", "columns": ZHULI_COLUMNS, "rows": zhuli_rows},
            {"name": "store_leads_profile", "columns": LEADS_COLUMNS, "rows": leads_rows},
            {"name": "store_lock_profile", "columns": LOCK_COLUMNS, "rows": lock_rows},
            {"name": "store_presale_profile", "columns": PRESALE_COLUMNS, "rows": presale_rows},
        ],
    }
    followup_context = {
        "metric": "store_dealer_profile",
        "stores": [r["门店"] for r in rows],
        "blocs": [r["经销商主体 (Bloc)"] for r in rows if r["matched"]],
        "in_operation_status": statuses,
        "window_days": args.window_days,
        "as_of": str(om["as_of"].date()) if om else None,
        "presale_gen": om["presale_gen"] if om else None,
        "available_dimensions": ["bloc_name", "region_name", "city_name", "store_format",
                                 "dealer_code", "zhuli", "leads", "lock", "presale"],
    }

    artifacts: dict = {}
    out_dir = Path(args.output) if args.output else _WS_ROOT / "outputs" / "tables"
    if args.format in ("csv", "json") or args.output:
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.format == "csv":
            artifacts["csv"] = str(write_csv(rows, out_dir / "store_dealer_profile.csv"))

    contract = build_success_contract(
        script="runtime_scripts/store_dealer_profile.py",
        command="python " + " ".join(sys.argv),
        scope=scope,
        result=result,
        artifacts=artifacts,
        followup_context=followup_context,
    )

    if args.format == "json":
        if args.output:
            save_contract_json(contract, out_dir / "store_dealer_profile.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(render_terminal(rows, statuses, zhuli is not None, om, lm))
        if artifacts.get("csv"):
            print(f"\n[Output]\n  CSV: {artifacts['csv']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
