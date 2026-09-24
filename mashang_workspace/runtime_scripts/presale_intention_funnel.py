#!/usr/bin/env python
"""预售小订转化漏斗 — 泛化处理链路（任意代际）。

固定链路（口径全部来自 shared/schema/business_definition.json）：
  1) 代际归属：series_group_logic（按 product_name 判定），而非 series 字段
  2) 预售窗口：time_periods.{gen}.start + monitor.open_hour/minute（预售开放时刻）
               ~ time_periods.{gen}.end + 1 天（上市日结束，口径到当日 24:00）
  3) 小订池：intention_payment_time ∈ [开放时刻, 上市日结束)，按 order_number 去重；
              默认剔除测试单（总部主理店 + 假身份号），可选 --include-test-orders
  4) 漏斗：退订 = intention_refund_time 非空；留存 = 未退意向金；
           转大定 = deposit_payment_time 非空；锁单 = lock_time 非空；
           大定退款 = deposit_refund_time 非空；纯留存 = 留存且未锁单
  5) point-in-time：以 --as-of 当日 24:00 为截止，晚于截止的退订/转化不计入

用法:
  python runtime_scripts/presale_intention_funnel.py                       # 当前预售代际
  python runtime_scripts/presale_intention_funnel.py --series CM3
  python runtime_scripts/presale_intention_funnel.py --series CM2 CM3 DM2 --as-of 2026-09-24
  python runtime_scripts/presale_intention_funnel.py --series CM3 --format json
  python runtime_scripts/presale_intention_funnel.py --list
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(_WS_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd

from utils.monitors.order_filter import flag_test_orders
from utils.monitors.phase import (
    detect_active,
    load_business_definition,
    model_series_of,
    open_hour,
    open_minute,
    series_label,
)
from utils.monitors.series_group import apply_series_group_logic
from utils.paths import DATASET_DIR
from utils.result_contract import (
    build_success_contract,
    contract_to_terminal,
    save_contract_json,
)

ORDER_PARQUET = DATASET_DIR / "order_data.parquet"
TIME_COLUMNS = [
    "intention_payment_time",
    "intention_refund_time",
    "deposit_payment_time",
    "deposit_refund_time",
    "lock_time",
]


def parse_args():
    p = argparse.ArgumentParser(description="预售小订转化漏斗（泛化，任意代际）")
    p.add_argument("--series", nargs="+", help="代际 key（如 CM3 DM2 LS8）；默认当前预售/最新代际")
    p.add_argument("--as-of", type=str, default=None, help="统计截止日 (YYYY-MM-DD)，默认今天")
    p.add_argument("--include-test-orders", action="store_true", help="不剔除总部测试单")
    p.add_argument("--output", type=str, help="输出目录 (默认 outputs/tables/)")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json", "csv"])
    p.add_argument("--list", action="store_true", help="列出所有可分析代际及其预售窗口")
    return p.parse_args()


def resolve_default_generations(bdef: dict, today: pd.Timestamp) -> list[str]:
    active = detect_active(bdef, today, phases=("presale",))
    if active:
        return [active[0]["generation"]]
    periods = [
        (gen, tp.get("start"))
        for gen, tp in (bdef.get("time_periods") or {}).items()
        if (tp or {}).get("start")
    ]
    periods.sort(key=lambda item: item[1], reverse=True)
    return [periods[0][0]] if periods else []


def resolve_window(bdef: dict, generation: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    tp = (bdef.get("time_periods") or {}).get(generation) or {}
    start, end = tp.get("start"), tp.get("end")
    if not start or not end:
        raise ValueError(f"business_definition.time_periods.{generation} 缺少 start/end")
    open_ts = pd.Timestamp(start) + pd.Timedelta(
        hours=open_hour(bdef, generation), minutes=open_minute(bdef, generation)
    )
    close_ts = pd.Timestamp(end) + pd.Timedelta(days=1)
    return cast(pd.Timestamp, open_ts), cast(pd.Timestamp, close_ts)


def load_orders(bdef: dict) -> pd.DataFrame:
    df = pd.read_parquet(ORDER_PARQUET)
    for col in TIME_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return apply_series_group_logic(df, bdef)


def compute_funnel(
    df: pd.DataFrame,
    bdef: dict,
    generation: str,
    as_of: pd.Timestamp,
    include_test_orders: bool,
) -> dict:
    open_ts, close_ts = resolve_window(bdef, generation)
    cutoff = as_of.normalize() + pd.Timedelta(days=1)

    slice_df = cast(pd.DataFrame, df.loc[df["series_group_logic"].eq(generation)]).copy()
    test_mask = cast(pd.Series, flag_test_orders(slice_df, bdef))
    test_orders = int(test_mask.sum())
    if not include_test_orders:
        slice_df = slice_df.loc[~test_mask]

    pay = cast(pd.Series, slice_df["intention_payment_time"])
    cohort = cast(pd.DataFrame, slice_df.loc[pay.notna() & (pay >= open_ts) & (pay < close_ts)])
    cohort = cohort.drop_duplicates(subset=["order_number"])

    refund_ts = cast(pd.Series, cohort["intention_refund_time"])
    deposit_ts = cast(pd.Series, cohort["deposit_payment_time"])
    deposit_refund_ts = cast(pd.Series, cohort["deposit_refund_time"])
    lock_ts = cast(pd.Series, cohort["lock_time"])

    def flag(series: pd.Series) -> pd.Series:
        return (series.notna() & (series < cutoff)).fillna(False)

    refunded_mask = cast(pd.Series, flag(refund_ts))
    deposit_mask = cast(pd.Series, flag(deposit_ts))
    lock_mask = cast(pd.Series, flag(lock_ts))

    refunded = int(refunded_mask.sum())
    deposit = int(deposit_mask.sum())
    deposit_refunded = int(flag(deposit_refund_ts).sum())
    locked = int(lock_mask.sum())

    total = int(cast(pd.Series, cohort["order_number"]).nunique())

    # 互斥进度漏斗（优先级：锁单 > 转大定 > 退订 > 纯留存），四项之和 = 小订池
    locked_only = locked
    deposit_not_locked = int((deposit_mask & ~lock_mask).sum())
    refunded_not_progressed = int((refunded_mask & ~deposit_mask & ~lock_mask).sum())
    pending = int((~refunded_mask & ~deposit_mask & ~lock_mask).sum())

    def rate(num: int, den: int) -> float:
        return round(num / den, 4) if den else 0.0

    row = {
        "generation": generation,
        "label": series_label(bdef, generation),
        "model_series": model_series_of(bdef, generation),
        "presale_open": open_ts.strftime("%Y-%m-%d %H:%M"),
        "presale_close": close_ts.strftime("%Y-%m-%d"),
        "as_of_cutoff": cutoff.strftime("%Y-%m-%d"),
        "cohort_total": total,
        "locked_only": locked_only,
        "deposit_not_locked": deposit_not_locked,
        "refunded_not_progressed": refunded_not_progressed,
        "pending": pending,
        "retained_not_refunded": total - refunded,
        "refunded_total": refunded,
        "deposit_total": deposit,
        "lock_total": locked,
        "deposit_refunded_total": deposit_refunded,
        "locked_rate": rate(locked_only, total),
        "deposit_not_locked_rate": rate(deposit_not_locked, total),
        "refunded_not_progressed_rate": rate(refunded_not_progressed, total),
        "pending_rate": rate(pending, total),
        "lock_total_rate": rate(locked, total),
        "deposit_total_rate": rate(deposit, total),
        "refunded_total_rate": rate(refunded, total),
        "test_orders_excluded": 0 if include_test_orders else test_orders,
        "presale_ongoing": bool(as_of.normalize() < close_ts),
    }
    assert locked_only + deposit_not_locked + refunded_not_progressed + pending == total
    return row


def render_terminal(rows: list[dict]) -> str:
    lines = ["[Summary]"]
    for row in rows:
        lines.append(
            f"  {row['generation']}（{row['label']}）小订池 {row['cohort_total']:,}｜"
            f"锁单 {row['lock_total']:,}｜转大定 {row['deposit_total']:,}｜"
            f"退订 {row['refunded_total']:,}｜留存(未退意向金) {row['retained_not_refunded']:,}"
        )
    lines.append("")
    lines.append("[Scope]")
    lines.append(f"  数据源: {ORDER_PARQUET}")
    lines.append("  代际归属: series_group_logic（business_definition）")
    lines.append("  漏斗口径: 锁单=lock_time；大定=deposit_payment_time；退订=intention_refund_time；留存=未退意向金（point-in-time 至 as_of 当日 24:00）")
    lines.append("")
    for row in rows:
        lines.append(f"[Result] {row['generation']}（{row['label']}）")
        lines.append(f"  预售窗口: {row['presale_open']} ~ {row['presale_close']}")
        lines.append(f"  统计截止: {row['as_of_cutoff']}")
        lines.append("")
        g = row["cohort_total"]

        def pct(n: int) -> str:
            return f"{n / g * 100:5.1f}%" if g else "  n/a"

        lines.append("  互斥进度漏斗（优先级：锁单 > 转大定 > 退订 > 纯留存）")
        lines.append("  阶段                    数量        占小订池")
        lines.append(f"  小订池              {row['cohort_total']:>9,}     100.0%")
        lines.append(f"  已锁单              {row['locked_only']:>9,}    {pct(row['locked_only'])}")
        lines.append(f"  已转大定（未锁单）    {row['deposit_not_locked']:>9,}    {pct(row['deposit_not_locked'])}")
        lines.append(f"  已退订（未转化）      {row['refunded_not_progressed']:>9,}    {pct(row['refunded_not_progressed'])}")
        lines.append(f"  纯留存（未退未转化）  {row['pending']:>9,}    {pct(row['pending'])}")
        lines.append("")
        lines.append("  参考（含重叠，非互斥）")
        lines.append(f"  已退订（意向金）      {row['refunded_total']:>9,}    {pct(row['refunded_total'])}")
        lines.append(f"  已转大定（含锁单）    {row['deposit_total']:>9,}    {pct(row['deposit_total'])}")
        lines.append(f"  已锁单（含退订重叠）  {row['lock_total']:>9,}    {pct(row['lock_total'])}")
        lines.append(f"  留存（未退意向金）    {row['retained_not_refunded']:>9,}    {pct(row['retained_not_refunded'])}")
        if row["deposit_refunded_total"]:
            lines.append(f"  大定退款              {row['deposit_refunded_total']:>9,}    {pct(row['deposit_refunded_total'])}")
        notes = []
        if row["presale_ongoing"]:
            notes.append("预售未结束（右删失，转化仍在进行）")
        if row["test_orders_excluded"]:
            notes.append(f"已剔除测试单 {row['test_orders_excluded']} 笔")
        if notes:
            lines.append(f"  备注: {'；'.join(notes)}")
        lines.append("")
    return "\n".join(lines)


def main():
    args = parse_args()
    today = cast(pd.Timestamp, pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp(datetime.now().date()))
    bdef = load_business_definition()
    cmd = "python " + " ".join(sys.argv)

    if args.list:
        rows = []
        for gen, tp in (bdef.get("time_periods") or {}).items():
            tp = tp or {}
            if not tp.get("start"):
                continue
            rows.append(
                f"  {gen:<10} {series_label(bdef, gen):<14} "
                f"{tp.get('start')} + {open_hour(bdef, gen):02d}:{open_minute(bdef, gen):02d} "
                f"~ {tp.get('end')}"
            )
        print("[Available Generations]")
        print("\n".join(sorted(rows)))
        return

    generations = args.series or resolve_default_generations(bdef, today)
    if not generations:
        print("错误: 无法确定代际，请显式指定 --series", file=sys.stderr)
        sys.exit(1)

    try:
        df = load_orders(bdef)
    except FileNotFoundError:
        print(f"错误: 数据文件不存在 {ORDER_PARQUET}", file=sys.stderr)
        sys.exit(1)

    rows = []
    for gen in generations:
        if gen not in (bdef.get("series_group_logic") or {}):
            print(f"错误: series_group_logic 中不存在代际 {gen}", file=sys.stderr)
            sys.exit(1)
        try:
            rows.append(compute_funnel(df, bdef, gen, today, args.include_test_orders))
        except ValueError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            sys.exit(1)

    out_dir = Path(args.output) if args.output else (REPO_ROOT / "outputs" / "tables")
    scope = {
        "data_source": str(ORDER_PARQUET),
        "time_window": {
            "as_of": today.strftime("%Y-%m-%d"),
            "presale_windows": {
                row["generation"]: {"open": row["presale_open"], "close": row["presale_close"]}
                for row in rows
            },
        },
        "filters": {
            "generation": generations if len(generations) > 1 else generations[0],
            "include_test_orders": args.include_test_orders,
        },
        "metric_definition": "presale_intention_funnel: cohort=intention_payment_time in presale window; refunded=intention_refund_time; retained=cohort-refunded; deposit=deposit_payment_time; locked=lock_time; point-in-time at as_of end-of-day",
    }
    primary = rows[0]
    result = {
        "summary": "; ".join(
            f"{r['generation']} 小订池 {r['cohort_total']:,} → 锁单 {r['lock_total']:,}，"
            f"转大定 {r['deposit_total']:,}，退订 {r['refunded_total']:,}，"
            f"留存(未退意向金) {r['retained_not_refunded']:,}"
            for r in rows
        ),
        "metrics": {
            f"{primary['generation']}_cohort_total": primary["cohort_total"],
            f"{primary['generation']}_locked_only": primary["locked_only"],
            f"{primary['generation']}_deposit_not_locked": primary["deposit_not_locked"],
            f"{primary['generation']}_refunded_not_progressed": primary["refunded_not_progressed"],
            f"{primary['generation']}_pending": primary["pending"],
            f"{primary['generation']}_lock_total": primary["lock_total"],
            f"{primary['generation']}_deposit_total": primary["deposit_total"],
            f"{primary['generation']}_refunded_total": primary["refunded_total"],
            f"{primary['generation']}_retained_not_refunded": primary["retained_not_refunded"],
        },
        "tables": [{"name": "presale_intention_funnel", "rows": rows}],
        "dimensions": [
            {
                "name": "generation",
                "items": [{"value": r["generation"], "metrics": {k: v for k, v in r.items() if k != "generation"}} for r in rows],
            }
        ],
    }
    ctx = {
        "metric": "presale_intention_funnel",
        "available_dimensions": ["generation", "product_name", "parent_region_name", "store_name"],
        "top_entities": [{"field": "series", "value": r["generation"], "metrics": {"cohort_total": r["cohort_total"]}} for r in rows],
    }
    contract = build_success_contract(
        script="runtime_scripts/presale_intention_funnel.py",
        command=cmd,
        scope=scope,
        result=result,
        followup_context=ctx,
    )

    if args.format == "json":
        if args.output:
            out_dir.mkdir(parents=True, exist_ok=True)
            save_contract_json(contract, out_dir / "presale_intention_funnel.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    elif args.format == "csv":
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "presale_intention_funnel.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        contract["artifacts"]["csv"] = str(path)
        print(contract_to_terminal(contract))
    else:
        print(render_terminal(rows))


if __name__ == "__main__":
    main()
