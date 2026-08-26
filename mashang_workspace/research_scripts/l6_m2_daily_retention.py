#!/usr/bin/env python3
"""
L6 M2 按支付日拆分留存小订表（小订 | 留存 | 限定 | 非限定）

口径（与 l6_m2_presale_report.py 的 release DM2 一致）:
  - 小订  = 预售开放日（08-18 20:00）起，按支付日（intention_payment_time）逐日新支付单数
  - 留存  = 报告口径：支付 ≥ 开放时刻 且 < as_of+1，且至今从未退意向金（intention_refund_time IS NULL）
  - 限定  = JimmyChoo 高定限量版（product_name 含 JimmyChoo / Jimmy Choo）的留存
  - 非限定 = 其余产品的留存

用法:
  python research_scripts/l6_m2_daily_retention.py                          # 终端输出，as_of=今天
  python research_scripts/l6_m2_daily_retention.py --as-of 2026-08-26
  python research_scripts/l6_m2_daily_retention.py --format json --output outputs/tables/
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

START = pd.Timestamp("2026-08-18")
OPEN_HOUR = 20
DEFAULT_AS_OF = pd.Timestamp("2026-08-26")


def _is_limited(pname) -> bool:
    p = str(pname).lower() if pname is not None else ""
    return "jimmychoo" in p or "jimmy choo" in p


def compute_daily(df: pd.DataFrame, as_of: pd.Timestamp) -> list[dict]:
    """逐日 小订/留存/限定/非限定。"""
    open_t = START + pd.Timedelta(hours=OPEN_HOUR)
    for c in ["intention_payment_time", "intention_refund_time"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    pool = df[(df["series_group_logic"] == "DM2")
              & (df["intention_payment_time"] >= open_t)
              & (df["intention_payment_time"] < (as_of + pd.Timedelta(days=1)))
              & (df["intention_refund_time"].isna())].copy()
    pool["edition"] = pool["product_name"].apply(_is_limited).map({True: "限定", False: "非限定"})

    paid = df[(df["series_group_logic"] == "DM2") & (df["intention_payment_time"] >= open_t)
              & (df["intention_payment_time"] < (as_of + pd.Timedelta(days=1)))]

    rows = []
    d = START.normalize()
    last_day = as_of.normalize()
    while d <= last_day:
        lo = max(open_t, d)
        hi = d + pd.Timedelta(days=1)
        day_pay = paid[(paid["intention_payment_time"] >= lo) & (paid["intention_payment_time"] < hi)]
        day_ret = pool[(pool["intention_payment_time"] >= lo) & (pool["intention_payment_time"] < hi)]
        n_pay = int(day_pay["order_number"].nunique())
        n_ret = int(day_ret["order_number"].nunique())
        n_lim = int(day_ret[day_ret["edition"] == "限定"]["order_number"].nunique())
        n_non = int(day_ret[day_ret["edition"] == "非限定"]["order_number"].nunique())
        rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "xiaoding": n_pay,
            "retained": n_ret,
            "limited": n_lim,
            "non_limited": n_non,
        })
        d += pd.Timedelta(days=1)
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="L6 M2 按支付日拆分留存小订表（小订/留存/限定/非限定）")
    p.add_argument("--as-of", type=str, default=str(DEFAULT_AS_OF.date()), help="统计基准日 YYYY-MM-DD（留存判定=截至该日从未退）")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    p.add_argument("--output", type=str, help="JSON 输出目录")
    args = p.parse_args()

    as_of = pd.Timestamp(args.as_of)
    df = load_order(apply_group=True)
    rows = compute_daily(df, as_of)
    total = {
        "xiaoding": sum(r["xiaoding"] for r in rows),
        "retained": sum(r["retained"] for r in rows),
        "limited": sum(r["limited"] for r in rows),
        "non_limited": sum(r["non_limited"] for r in rows),
    }

    scope = {
        "data_source": "dataset/order_data.parquet（series_group_logic.DM2）",
        "time_window": {"start": f"{START.date()} {OPEN_HOUR}:00", "end": str(as_of.date()), "as_of": str(as_of.date())},
        "filters": {"series": "DM2", "refund": "从未退意向金"},
        "metric_definition": "小订=支付日新支付；留存=报告口径(20:00起且从未退)；限定=JimmyChoo高定限量版留存",
    }
    contract = {
        "status": "success",
        "script": "research_scripts/l6_m2_daily_retention.py",
        "scope": scope,
        "result": {"summary": f"L6 M2 预售逐日留存（截至 {as_of.date()}）",
                   "metrics": {k: int(v) for k, v in total.items()},
                   "daily": rows},
        "artifacts": {},
        "followup_context": {"metric": "presale_retention_daily", "available_dimensions": ["edition"]},
        "warnings": [],
        "errors": [],
    }

    if args.format == "json":
        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"L6_M2_daily_retention_{as_of.date()}.json"
            out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"已输出: {out}")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(f"{'支付日':<12}{'小订':>6}{'留存':>7}{'限定':>7}{'非限定':>8}")
        print("-" * 40)
        for r in rows:
            print(f"{r['date']:<12}{r['xiaoding']:>6}{r['retained']:>7}{r['limited']:>7}{r['non_limited']:>8}")
        print("-" * 40)
        print(f"{'合计':<12}{total['xiaoding']:>6}{total['retained']:>7}{total['limited']:>7}{total['non_limited']:>8}")
        print()
        print(f"口径：小订=支付日新支付；留存=报告口径（{START.date()} 20:00 起且截至 {as_of.date()} 从未退意向金）；"
              f"限定=JimmyChoo 高定限量版。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
