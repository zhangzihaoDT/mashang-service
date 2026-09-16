#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
门店经营状况观察（全门店）

输出每家门店的：门店类型 / 近 N 日下发线索 / CM3 留存小订 / 小订÷线索 比值。

口径:
  - 门店类型: 优先取「主理在岗统计」(dataset/门店日报_主理_当月.csv) 的 门店类型
    （车城店/商超店/独立慢闪店/城市空间/短期体验中心）；缺失时回落 store_info
    的 store_format（Dealer Code 前缀派生），再缺失记「未知」
  - 近 N 日下发线索: dataset/门店下发线索数.csv（增量库）窗口求和
  - CM3 留存小订: order_data.parquet，series_group=CM3 且意向金时间 ∈ [CM3预售开放, 截止) 且未退意向金
  - 小订/线索 = CM3 留存小订 ÷ 近 N 日下发线索
  - 覆盖全门店 = 线索库 ∪ CM3 订单 ∪ 主理在岗统计 门店并集

用法:
    python utility_scripts/store_operation_observation.py                      # 终端 top20
    python utility_scripts/store_operation_observation.py --format csv         # 落盘 CSV
    python utility_scripts/store_operation_observation.py --format csv --output outputs/tables/
    python utility_scripts/store_operation_observation.py --as-of 2026-09-16 --window-days 7
    python utility_scripts/store_operation_observation.py --limit 50           # 终端展示行数
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(_WS_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from utils.result_contract import build_success_contract, save_contract_json  # noqa: E402
from shared.loaders import store_info_loader as sl  # noqa: E402

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
LEADS_CSV = REPO_ROOT / "dataset" / "门店下发线索数.csv"
ZHULI_ZAIGANG_CSV = REPO_ROOT / "dataset" / "门店日报_主理_当月.csv"

COLUMNS = ["门店", "门店类型", "近7日下发线索", "CM3小订", "小订/线索"]
UNKNOWN_TYPE = "未知"


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description="门店经营状况观察（全门店）")
    p.add_argument("--as-of", dest="as_of", help="观测截止日 YYYY-MM-DD（默认订单/线索数据最大日）")
    p.add_argument("--window-days", type=int, default=7, help="下发线索窗口天数（默认 7）")
    p.add_argument("--presale-gen", default="CM3", help="预售代际（默认 CM3）")
    p.add_argument("--limit", type=int, default=20, help="终端展示行数（默认 20）")
    p.add_argument("--format", default="terminal", choices=["terminal", "csv", "json"])
    p.add_argument("--output", help="输出目录（csv/json 落盘）")
    return p.parse_args(argv)


def load_type_map() -> dict[str, str]:
    """门店名 → 门店类型。（主理在岗统计优先，缺失回落 store_info.store_format）"""
    m: dict[str, str] = {}
    if ZHULI_ZAIGANG_CSV.exists():
        z = pd.read_csv(ZHULI_ZAIGANG_CSV, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        if "门店类型" not in z.columns and "门店类型 " in z.columns:
            z = z.rename(columns={"门店类型 ": "门店类型"})
        if "门店名称" in z.columns and "门店类型" in z.columns:
            for name, kind in z.drop_duplicates("门店名称")[["门店名称", "门店类型"]].itertuples(index=False):
                if str(name).strip():
                    m[str(name).strip()] = str(kind).strip() or UNKNOWN_TYPE
    return m


def load_leads(as_of: pd.Timestamp | None, window_days: int) -> tuple[pd.Series, pd.Timestamp | None]:
    if not LEADS_CSV.exists():
        return pd.Series(dtype="int64"), None
    df = pd.read_csv(LEADS_CSV, encoding="utf-8-sig")
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    df["下发线索数"] = pd.to_numeric(df["下发线索数"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["日期"])
    if df.empty:
        return pd.Series(dtype="int64"), None
    asof = pd.Timestamp(as_of).normalize() if as_of else pd.Timestamp(df["日期"].max()).normalize()
    start = asof - pd.Timedelta(days=window_days - 1)
    w = df[(df["日期"] >= start) & (df["日期"] <= asof)]
    return w.groupby("门店")["下发线索数"].sum(), asof


def load_cm3(as_of: pd.Timestamp | None, presale_gen: str) -> tuple[pd.Series, pd.Timestamp | None, pd.Timestamp | None]:
    """CM3 留存小订（累计至 as_of）。返回 (by_store, as_of, presale_open)。"""
    if not ORDER_PARQUET.exists():
        return pd.Series(dtype="int64"), as_of, None
    from utils.monitors.series_group import apply_series_group_logic
    from utils.monitors.phase import load_business_definition, open_hour, open_minute

    bd = load_business_definition(BUSINESS_DEF)
    df = pd.read_parquet(ORDER_PARQUET, columns=[
        "order_number", "store_name", "series", "product_name",
        "intention_payment_time", "intention_refund_time", "lock_time",
    ])
    for c in ("intention_payment_time", "intention_refund_time", "lock_time"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df = apply_series_group_logic(df, bd)
    if as_of is None:
        asof = pd.Timestamp(df["lock_time"].max()).normalize()
    else:
        asof = pd.Timestamp(as_of).normalize()
    end = asof + pd.Timedelta(days=1)
    tp = bd.get("time_periods", {}).get(presale_gen, {})
    if not tp.get("start"):
        return pd.Series(dtype="int64"), asof, None
    open_ts = pd.Timestamp(tp["start"]) + pd.Timedelta(
        hours=open_hour(bd, presale_gen), minutes=open_minute(bd, presale_gen))
    sel = df[(df["series_group_logic"] == presale_gen)
             & (df["intention_payment_time"] >= open_ts)
             & (df["intention_payment_time"] < end)
             & (df["intention_refund_time"].isna() | (df["intention_refund_time"] >= end))]
    return sel.groupby("store_name")["order_number"].nunique(), asof, open_ts


def build_table(args) -> tuple[pd.DataFrame, dict]:
    leads, leads_asof = load_leads(args.as_of, args.window_days)
    cm3, asof, presale_open = load_cm3(pd.Timestamp(args.as_of).normalize() if args.as_of else None, args.presale_gen)
    if asof is None:
        asof = leads_asof
    type_map = load_type_map()

    names = sorted(set(leads.index) | set(cm3.index) | set(type_map.keys()))
    rows = []
    for n in names:
        L = int(leads.get(n, 0))
        C = int(cm3.get(n, 0))
        kind = type_map.get(n) or (sl.resolve_dealer_info(n) or {}).get("store_format") or UNKNOWN_TYPE
        rows.append({
            "门店": n,
            "门店类型": kind,
            "近7日下发线索": L,
            "CM3小订": C,
            "小订/线索": f"{C / L * 100:.1f}%" if L else "—",
            "_ratio": (C / L) if L else -1.0,
        })
    df = pd.DataFrame(rows).sort_values(["_ratio", "近7日下发线索"], ascending=[False, False]).reset_index(drop=True)
    meta = {"as_of": asof, "leads_asof": leads_asof, "presale_open": presale_open,
            "window_days": args.window_days, "presale_gen": args.presale_gen}
    return df, meta


def render_terminal(df: pd.DataFrame, meta: dict, limit: int, out_path: Path | None) -> str:
    lines = ["[Summary]",
             f"  门店经营状况观察（{len(df)} 家；线索窗口近 {meta['window_days']} 日，截至 {meta['as_of'].date()}）",
             "",
             "[Scope]",
             f"  数据源: {LEADS_CSV}（线索）; {ORDER_PARQUET}（{meta['presale_gen']} 小订）; {ZHULI_ZAIGANG_CSV}（门店类型）",
             f"  口径: 近N日下发线索=窗口求和; CM3小订=预售开放({meta['presale_open']})起未退意向金累计; 小订/线索=CM3小订÷近N日线索",
             "",
             "[Result]"]
    lines.append("\t".join(COLUMNS))
    for _, r in df.head(limit).iterrows():
        lines.append("\t".join([r["门店"], r["门店类型"], str(r["近7日下发线索"]), str(r["CM3小订"]), r["小订/线索"]]))
    lines.append(f"  （共 {len(df)} 家，仅显示前 {min(limit, len(df))} 家）")
    if out_path:
        lines.append(f"\n[Output]\n  CSV: {out_path}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    df, meta = build_table(args)

    out_dir = Path(args.output) if args.output else _WS_ROOT / "outputs" / "tables"
    csv_path = None
    if args.format == "csv" or args.output:
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / "store_operation_observation.csv"
        df[COLUMNS].to_csv(csv_path, index=False, encoding="utf-8-sig")

    scope = {
        "data_source": f"{LEADS_CSV}; {ORDER_PARQUET}",
        "filters": {"window_days": args.window_days, "as_of": str(meta["as_of"].date()), "presale_gen": meta["presale_gen"]},
        "metric_definition": ("门店类型=主理在岗统计门店类型(缺省回落 store_format); "
                              "近N日下发线索=SUM(下发线索数); CM3小订=COUNTD(order_number) series_group=CM3 未退; "
                              "小订/线索=CM3小订÷近N日下发线索"),
    }
    result = {
        "summary": f"门店经营状况观察：{len(df)} 家门店（截至 {meta['as_of'].date()}）",
        "metrics": {"store_count": len(df),
                    "stores_with_leads": int((df['近7日下发线索'] > 0).sum()),
                    "stores_with_cm3": int((df['CM3小订'] > 0).sum())},
        "tables": [{"name": "store_operation_observation", "columns": COLUMNS,
                    "rows": df[COLUMNS].to_dict("records")}],
    }
    artifacts = {"csv": str(csv_path)} if csv_path else {}
    contract = build_success_contract(
        script="utility_scripts/store_operation_observation.py",
        command="python " + " ".join(sys.argv),
        scope=scope, result=result, artifacts=artifacts,
    )

    if args.format == "json":
        if args.output:
            save_contract_json(contract, out_dir / "store_operation_observation.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(render_terminal(df, meta, args.limit, csv_path if args.output or args.format == "csv" else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
