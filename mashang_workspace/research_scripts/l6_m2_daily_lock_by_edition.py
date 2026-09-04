#!/usr/bin/env python3
"""
L6 M2 (DM2) 上市以来每日锁单数（限定 / 非限定）

口径（限定/非限定与 l6_m2_daily_retention.py 一致）:
  - DM2   = series_group_logic == DM2（一代 L6 家族 + M2 + Jimmy Choo）
  - 锁单   = lock_time 非空（COUNTD order_number）
  - 限定   = JimmyChoo 高定限量版（product_name 含 JimmyChoo / Jimmy Choo）
  - 非限定 = 其余产品
  - 上市日 = business_definition.json time_periods.DM2.end（默认 2026-08-28），
            可用 --start-date 覆盖；结束 = --end-date（默认取数据最新锁单日）

用法:
  python research_scripts/l6_m2_daily_lock_by_edition.py
  python research_scripts/l6_m2_daily_lock_by_edition.py --start-date 2026-08-28 --end-date 2026-09-01
  python research_scripts/l6_m2_daily_lock_by_edition.py --format json --output outputs/tables/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS = REPO_ROOT / "mashang_workspace"
for p in (str(REPO_ROOT), str(_WS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from research_scripts.l6_m2_presale_report import load_order  # noqa: E402
from utils.business import get_launch_date  # noqa: E402


def _is_limited(pname) -> bool:
    p = str(pname).lower() if pname is not None else ""
    return "jimmychoo" in p or "jimmy choo" in p


def compute_daily(df: pd.DataFrame, start_date: pd.Timestamp,
                  end_date: pd.Timestamp) -> list[dict]:
    """逐日 锁单/限定/非限定。"""
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    pool = df[df["series_group_logic"] == "DM2"].copy()
    pool = pool[pool["lock_time"].notna()].copy()
    pool["edition"] = pool["product_name"].apply(_is_limited).map({True: "限定", False: "非限定"})

    rows = []
    d = start_date.normalize()
    last_day = end_date.normalize()
    while d <= last_day:
        hi = d + pd.Timedelta(days=1)
        day = pool[(pool["lock_time"] >= d) & (pool["lock_time"] < hi)]
        n_lock = int(day["order_number"].nunique())
        n_lim = int(day[day["edition"] == "限定"]["order_number"].nunique())
        n_non = int(day[day["edition"] == "非限定"]["order_number"].nunique())
        rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "lock_count": n_lock,
            "limited": n_lim,
            "non_limited": n_non,
            "limited_share": round(n_lim / n_lock, 4) if n_lock else None,
        })
        d += pd.Timedelta(days=1)
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="L6 M2 (DM2) 上市以来每日锁单数（限定/非限定）")
    default_start = get_launch_date("DM2") or "2026-08-28"
    p.add_argument("--start-date", type=str, default=default_start,
                   help=f"上市日起（默认取 business_definition.DM2.end = {default_start}）")
    p.add_argument("--end-date", type=str, default=None, help="结束日（默认取数据最新锁单日）")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    p.add_argument("--output", type=str, help="JSON 输出目录")
    args = p.parse_args()

    df = load_order(apply_group=True)
    start_date = pd.Timestamp(args.start_date)
    max_lock = pd.to_datetime(df.loc[df["series_group_logic"] == "DM2", "lock_time"],
                              errors="coerce").max()
    end_date = pd.Timestamp(args.end_date) if args.end_date else max_lock.normalize()
    if pd.isna(end_date):
        end_date = start_date

    rows = compute_daily(df, start_date, end_date)
    total = {
        "lock_count": sum(r["lock_count"] for r in rows),
        "limited": sum(r["limited"] for r in rows),
        "non_limited": sum(r["non_limited"] for r in rows),
    }

    scope = {
        "data_source": "dataset/order_data.parquet（series_group_logic.DM2）",
        "time_window": {"start": str(start_date.date()), "end": str(end_date.date())},
        "filters": {"series": "DM2", "lock": "lock_time 非空"},
        "metric_definition": "锁单数=COUNTD(order_number WHERE lock_time NOT NULL)；"
                             "限定=JimmyChoo 高定限量版；非限定=其余 DM2 产品",
    }
    contract = {
        "status": "success",
        "script": "research_scripts/l6_m2_daily_lock_by_edition.py",
        "scope": scope,
        "result": {"summary": f"L6 M2 (DM2) 上市以来逐日锁单（{start_date.date()} ~ {end_date.date()}）",
                   "metrics": {k: int(v) for k, v in total.items()},
                   "daily": rows},
        "artifacts": {},
        "followup_context": {"metric": "lock_count_daily", "top_entities": [
            {"field": "edition", "value": "限定",
             "metrics": {"lock_count": int(total["limited"])}},
            {"field": "edition", "value": "非限定",
             "metrics": {"lock_count": int(total["non_limited"])}},
        ], "available_dimensions": ["edition"]},
        "warnings": [],
        "errors": [],
    }

    if args.format == "json":
        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"L6_M2_daily_lock_{start_date.date()}_{end_date.date()}.json"
            out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"已输出: {out}")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(f"{'日期':<12}{'锁单':>6}{'限定':>6}{'非限定':>8}{'限定占比':>8}")
        print("-" * 40)
        for r in rows:
            share = f"{r['limited_share']:.1%}" if r["limited_share"] is not None else "-"
            print(f"{r['date']:<12}{r['lock_count']:>6}{r['limited']:>6}{r['non_limited']:>8}{share:>8}")
        print("-" * 40)
        print(f"{'合计':<12}{total['lock_count']:>6}{total['limited']:>6}{total['non_limited']:>8}"
              f"{(total['limited']/total['lock_count'] if total['lock_count'] else 0):>7.1%}")
        print()
        print(f"口径：锁单=lock_time 非空；限定=JimmyChoo 高定限量版；非限定=其余 DM2 产品。上市日=DM2.end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
