#!/usr/bin/env python3
"""
description: "门店锁单停滞预警 — 按在营门店分桶：无锁单天数 3/10/30/>30 天"
用法:
    python mashang_workspace/utility_scripts/skills_store_lock_alert.py
    python mashang_workspace/utility_scripts/skills_store_lock_alert.py --as-of 2026-07-21
    python mashang_workspace/utility_scripts/skills_store_lock_alert.py --format json
    python mashang_workspace/utility_scripts/skills_store_lock_alert.py --top-n 15
    python mashang_workspace/utility_scripts/skills_store_lock_alert.py --exclude-stores "上海张江展厅"
"""

# 默认排除的非销售门店（培训展厅、总部等，不参与预警）
DEFAULT_EXCLUDE_STORES = [
    "上海张江展厅",
]

import sys, argparse, json, re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))
from utils.paths import resolve_data_path

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
STORE_INFO_CSV_PATH = resolve_data_path("门店信息")

BUCKET_LABELS = [
    ("0~3d_active", "0~3 天（活跃）"),
    ("3~10d_warn", "3~10 天（关注）"),
    ("10~30d_alert", "10~30 天（预警）"),
    ("30d+_cold", ">30 天（沉睡）"),
    ("never_locked", "从未锁单"),
]


def parse_args():
    p = argparse.ArgumentParser(description="门店锁单停滞预警")
    p.add_argument("--as-of", type=str, help="基准日期 (YYYY-MM-DD，默认昨天)")
    p.add_argument("--window-days", type=int, default=30, help="在营门店判定窗口（默认 30 天）")
    p.add_argument("--top-n", type=int, default=10, help="沉睡门店 TopN 输出（默认 10）")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    p.add_argument("--exclude-stores", type=str, default="",
                   help="额外排除门店（逗号分隔，默认排除培训展厅等非销售门店）")
    return p.parse_args()


def main():
    args = parse_args()

    if args.as_of:
        base = pd.Timestamp(args.as_of)
    else:
        base = pd.Timestamp(datetime.now().date()) - timedelta(days=1)

    window_start = base - timedelta(days=args.window_days - 1)

    df = pd.read_parquet(str(ORDER_PARQUET))
    df["order_create_date"] = pd.to_datetime(df["order_create_date"], errors="coerce")
    df["store_create_date"] = pd.to_datetime(df["store_create_date"], errors="coerce")
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")

    active_mask = (
        (df["order_create_date"] >= window_start)
        & (df["order_create_date"] <= base)
        & (df["store_create_date"] <= base)
    )
    active_stores = df[active_mask]["store_name"].unique()

    exclude = set(s.strip() for s in DEFAULT_EXCLUDE_STORES)
    if args.exclude_stores:
        exclude |= set(s.strip() for s in args.exclude_stores.split(","))
    excluded_found = [s for s in active_stores if s in exclude]
    active_stores = [s for s in active_stores if s not in exclude]
    n_active = len(active_stores)

    last_lock = (
        df[df["store_name"].isin(active_stores)]
        .groupby("store_name")["lock_time"]
        .max()
    )

    store_list = []
    for store in active_stores:
        l = last_lock.get(store)
        if pd.notna(l):
            days = (base - l).days
        else:
            days = None
        store_list.append({"store_name": store, "days_since_last_lock": days})

    sdf = pd.DataFrame(store_list)

    def bucket(d):
        if d is None:
            return "never_locked"
        if d <= 3:
            return "0~3d_active"
        if d <= 10:
            return "3~10d_warn"
        if d <= 30:
            return "10~30d_alert"
        return "30d+_cold"

    sdf["bucket"] = sdf["days_since_last_lock"].apply(bucket)
    bucket_counts = sdf["bucket"].value_counts()

    summary_rows = []
    for key, label in BUCKET_LABELS:
        cnt = int(bucket_counts.get(key, 0))
        summary_rows.append({
            "bucket_key": key,
            "bucket_label": label,
            "store_count": cnt,
            "share_pct": round(cnt / n_active * 100, 1) if n_active else 0,
        })

    cold = sdf[sdf["bucket"] == "30d+_cold"].sort_values("days_since_last_lock", ascending=False)
    alert = sdf[sdf["bucket"].isin(["10~30d_alert", "3~10d_warn"])].sort_values("days_since_last_lock", ascending=False)

    cold_stores = []
    for _, r in cold.head(args.top_n).iterrows():
        cold_stores.append({
            "store_name": r["store_name"],
            "days_since_last_lock": int(r["days_since_last_lock"]),
        })

    alert_stores = []
    for _, r in alert.head(args.top_n).iterrows():
        alert_stores.append({
            "store_name": r["store_name"],
            "days_since_last_lock": int(r["days_since_last_lock"]),
            "bucket": dict(BUCKET_LABELS).get(
                [k for k, _ in BUCKET_LABELS if k == r["bucket"]][0], r["bucket"]
            ),
        })

    # ── Bloc Name 聚合 ──
    bloc_info = {}
    if STORE_INFO_CSV_PATH.exists():
        info = pd.read_csv(str(STORE_INFO_CSV_PATH))
        def _clean(name):
            n = re.sub(r'[（(].*[）)]', '', str(name)).strip()
            return re.sub(r'\s+', '', n)
        info["_clean"] = info["Dealer Name Fc"].apply(_clean)
        for _, r in info.iterrows():
            cn = r["_clean"]
            bloc_info.setdefault(cn, []).append((r["Bloc Name"], r["Dealer_type"], r.get("Region Name", "")))

    def _lookup_bloc(store_name):
        if not bloc_info:
            return None
        sn = _clean(store_name)
        for cn, rows in bloc_info.items():
            if store_name in cn or sn in cn:
                return rows[0][0]
        cn2 = re.sub(r'车城店.*|分销店.*|换铺.*|迁址.*|换址.*', '', sn).strip()
        if cn2 != sn:
            for cn, rows in bloc_info.items():
                if cn2 in cn:
                    return rows[0][0]
        # try reverse: remove 体验/用户中心 suffix
        return None

    sdf["bloc_name"] = sdf["store_name"].apply(_lookup_bloc)

    # ── Bloc 级聚合：不只是看最近锁单，而是看门店活性分布 ──
    def _bloc_stats(group):
        stores = len(group)
        active_3d = ((group["days_since_last_lock"].notna()) & (group["days_since_last_lock"] <= 3)).sum()
        active_10d = ((group["days_since_last_lock"].notna()) & (group["days_since_last_lock"] <= 10)).sum()
        warn = ((group["days_since_last_lock"].notna()) & (group["days_since_last_lock"] > 3) & (group["days_since_last_lock"] <= 10)).sum()
        alert = ((group["days_since_last_lock"].notna()) & (group["days_since_last_lock"] > 10) & (group["days_since_last_lock"] <= 30)).sum()
        cold = ((group["days_since_last_lock"].notna()) & (group["days_since_last_lock"] > 30)).sum()
        never = group["days_since_last_lock"].isna().sum()
        min_d = group["days_since_last_lock"].min()
        max_d = group["days_since_last_lock"].max()
        return pd.Series({
            "store_count": stores,
            "active_3d": int(active_3d), "active_10d": int(active_10d),
            "warn_count": int(warn), "alert_count": int(alert), "cold_count": int(cold), "never_locked_count": int(never),
            "min_days": min_d, "max_days": max_d,
            "active_ratio": round(active_3d / stores * 100, 1),
        })

    bloc_detail = sdf[sdf["bloc_name"].notna()].groupby("bloc_name").apply(_bloc_stats).reset_index()

    # 主体健康分层：基于"最差门店"而非"最好门店"
    def _bloc_health(r):
        if r["max_days"] and r["max_days"] > 30:
            return "30d+_cold"
        if r["alert_count"] > r["store_count"] * 0.5 or (r["max_days"] and r["max_days"] > 10):
            return "10~30d_alert"
        if r["warn_count"] > r["store_count"] * 0.5:
            return "3~10d_warn"
        return "0~3d_active"

    bloc_detail["bloc_bucket"] = bloc_detail.apply(_bloc_health, axis=1)
    bloc_bucket_counts = bloc_detail["bloc_bucket"].value_counts()

    # 集中度标识：锁单集中在少数门店的主体
    def _concentration(r):
        if r["store_count"] <= 1 or r["active_3d"] == 0:
            return "无活跃"
        if r["active_3d"] == r["store_count"]:
            return "全店活跃"
        if r["active_3d"] >= r["store_count"] * 0.5:
            return "部分集中"
        return "高度集中(活跃店<50%)"

    bloc_detail["concentration"] = bloc_detail.apply(_concentration, axis=1)

    bloc_summary_rows = []
    for key, label in BUCKET_LABELS:
        cnt = int(bloc_bucket_counts.get(key, 0))
        bloc_summary_rows.append({
            "bucket_key": key,
            "bucket_label": label,
            "bloc_count": cnt,
            "share_pct": round(cnt / len(bloc_detail) * 100, 1) if len(bloc_detail) else 0,
        })

    bloc_cold = bloc_detail[bloc_detail["bloc_bucket"] == "30d+_cold"].sort_values("max_days", ascending=False)
    bloc_alert = bloc_detail[bloc_detail["bloc_bucket"] == "10~30d_alert"].sort_values("max_days", ascending=False)

    def _bloc_to_dict(r, detail=False):
        d = {
            "bloc_name": r["bloc_name"],
            "store_count": int(r["store_count"]),
            "active_3d": int(r["active_3d"]),
            "max_days_since_last_lock": int(r["max_days"]),
            "concentration": r["concentration"],
        }
        if detail:
            d.update({
                "warn_count": int(r["warn_count"]), "alert_count": int(r["alert_count"]),
                "cold_count": int(r["cold_count"]), "min_days": int(r["min_days"]),
            })
        return d

    bloc_cold_list = [_bloc_to_dict(r) for _, r in bloc_cold.head(args.top_n).iterrows()]
    bloc_alert_list = [_bloc_to_dict(r, detail=True) for _, r in bloc_alert.head(args.top_n).iterrows()]
    # 集中度高但主体活跃的（"少数门店扛量"）
    bloc_concentrated = bloc_detail[
        (bloc_detail["active_3d"] > 0) & (bloc_detail["concentration"] == "高度集中(活跃店<50%)")
    ].sort_values("store_count", ascending=False)

    locked = sdf[sdf["days_since_last_lock"].notna()]
    result = {
        "summary": {
            "as_of_date": base.strftime("%Y-%m-%d"),
            "active_store_count": n_active,
            "window_days": args.window_days,
            "stores_with_lock": int(len(locked)),
            "stores_never_locked": int(n_active - len(locked)),
            "median_days_no_lock": int(locked["days_since_last_lock"].median()) if len(locked) else None,
            "max_days_no_lock": int(locked["days_since_last_lock"].max()) if len(locked) else None,
        },
        "bucket_summary": summary_rows,
        "cold_stores": cold_stores,
        "alert_stores": alert_stores,
        "excluded_stores": excluded_found,
        "bloc_summary": {
            "matched_bloc_count": len(bloc_detail),
            "bloc_buckets": bloc_summary_rows,
            "bloc_cold": bloc_cold_list,
            "bloc_alert": bloc_alert_list,
            "bloc_concentrated": [
                {"bloc_name": r["bloc_name"], "store_count": int(r["store_count"]),
                 "active_3d": int(r["active_3d"]), "max_days": int(r["max_days"])}
                for _, r in bloc_concentrated.head(args.top_n).iterrows()
            ],
        },
    }

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if excluded_found:
        print(f"[排除门店]  {' '.join(excluded_found)}（不参与预警）")
    s = result["summary"]
    print(f"[Summary]  基准日期: {s['as_of_date']}  在营门店(扣除排除): {s['active_store_count']} 家")
    print(f"           中位数无锁单: {s['median_days_no_lock']} 天  最长: {s['max_days_no_lock']} 天")
    print()
    print(f"  {'分层':>20}  {'门店数':>6}  {'占比':>8}")
    print(f"  {'-'*20}  {'-'*6}  {'-'*8}")
    for rw in summary_rows:
        print(f"  {rw['bucket_label']:>20}  {rw['store_count']:>6}  {rw['share_pct']:>7.1f}%")
    print()

    if cold_stores:
        print(f"  [沉睡门店 Top {len(cold_stores)}]")
        for cs in cold_stores:
            print(f"    {cs['store_name']:<30}  {cs['days_since_last_lock']} 天无锁单")
    if alert_stores:
        print(f"  [预警门店 Top {len(alert_stores)}]")
        for cs in alert_stores:
            print(f"    {cs['store_name']:<30}  {cs['days_since_last_lock']} 天无锁单  ({cs['bucket']})")

    # ── Bloc Name 终端输出 ──
    bloc = result["bloc_summary"]
    print()
    print(f"[经销商主体]  已匹配 {bloc['matched_bloc_count']} 家")
    print(f"  {'分层':>20}  {'主体数':>6}  {'占比':>8}")
    print(f"  {'-'*20}  {'-'*6}  {'-'*8}")
    for rw in bloc["bloc_buckets"]:
        print(f"  {rw['bucket_label']:>20}  {rw['bloc_count']:>6}  {rw['share_pct']:>7.1f}%")
    if bloc.get("bloc_cold"):
        print(f"  [全部门店停滞 Top {len(bloc['bloc_cold'])}]")
        for b in bloc["bloc_cold"]:
            print(f"    {b['bloc_name']:<24}  {b['store_count']} 家店  3d活跃{b['active_3d']}家  最长{b['max_days_since_last_lock']}天无锁单")
    if bloc.get("bloc_alert"):
        print(f"  [部分门店停滞 Top {len(bloc['bloc_alert'])}]")
        for b in bloc["bloc_alert"]:
            print(f"    {b['bloc_name']:<24}  {b['store_count']}家店  3d活跃{b['active_3d']}家  预警{b['alert_count']}+关注{b['warn_count']}  最长{b['max_days_since_last_lock']}天")
    if bloc.get("bloc_concentrated"):
        print(f"  [集中度风险（少数门店扛量）Top {len(bloc['bloc_concentrated'])}]")
        for b in bloc["bloc_concentrated"]:
            print(f"    {b['bloc_name']:<24}  {b['store_count']}家店  仅{b['active_3d']}家活跃  最久未锁单{b['max_days']}天")


if __name__ == "__main__":
    main()
