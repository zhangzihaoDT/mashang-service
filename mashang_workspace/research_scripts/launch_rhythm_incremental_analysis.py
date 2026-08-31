#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上市节奏（预售-上市-权益结束）对车系销量的增量贡献研究脚本

研究问题：评估历史上各代际（CM0/DM0/CM1/DM1/CM2/LS9/LS8）「预售小订 → 上市集中转大定 → 权益窗口兑现」
的集中爆发式销售运营，对该车系累计销量带来多少增量，贡献重要性如何。

方法（双轨）：
  证据线 A - 阶段占比法（重要性）：按 lock_time 拆解到 预售期/上市爆发/权益期/常态期，
            上市节奏窗口 [start, finish] 内锁单量 ÷ 总量窗口内锁单 = 节奏窗口贡献率。
  证据线 B - 基线差值法（增量）：增量 = 节奏窗口实际锁单 − 基线日均 × 窗口天数。
            基线1 = 上一代际成熟期（finish→+180d）日均锁单；基线2 = 品牌上市前 180 天自然日均锁单。
  证据线 C - 预售池转化追踪（机制）：预售小订池 → 上市转大定/锁单 → 最终交付的转化率与绝对量。

口径：
  - 代际归属：shared/schema/business_definition.json series_group_logic
  - 预售期 [start, end)；上市爆发 [end, end+7d)；权益期 [end+7d, finish]；常态期 (finish, end+12M]
  - 零售口径：order_type ∈ {用户车, NaN}（排除试驾车/员工/大客户/批售等一切非零售单）
  - 上市节奏窗口 = [start, finish]；总量窗口 = [start, min(end+12M, as_of)]

用法：
  python mashang_workspace/research_scripts/launch_rhythm_incremental_analysis.py
  python mashang_workspace/research_scripts/launch_rhythm_incremental_analysis.py --format json --output outputs/tables/
  python mashang_workspace/research_scripts/launch_rhythm_incremental_analysis.py --html
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
    load_business_definition,
    apply_series_group_logic,
    _parse_logic,
    _rule_condition,
)
from utils.result_contract import (  # noqa: E402
    build_success_contract,
    save_contract_json,
)

_BUSINESS_DEF = REPO_ROOT / "shared" / "schema" / "business_definition.json"
_ORDER_DATA = REPO_ROOT / "dataset" / "order_data.parquet"
_DEFAULT_OUTPUT = _WS / "outputs" / "tables"
_DEFAULT_REPORT = _WS / "outputs" / "reports" / "launch_rhythm_incremental_analysis.html"

GENERATIONS = ["CM0", "DM0", "CM1", "DM1", "CM2", "LS9", "LS8"]
COMPARE_GEN = "DM2"
FAMILY = {
    "CM0": "LS6", "CM1": "LS6", "CM2": "LS6", "CM3": "LS6",
    "DM0": "L6", "DM1": "L6", "DM2": "L6",
    "LS9": "LS9", "LS8": "LS8", "LS9Hyper": "LS9",
}
FAMILY_ORDER = {"LS6": ["CM0", "CM1", "CM2"], "L6": ["DM0", "DM1", "DM2"]}
NON_RETAIL = {"试驾车", "大客户", "员工", "集团员工", "经销商员工", "享道", "仅批售", "项目", "展车", "海外"}
LAUNCH_BURST_DAYS = 7
MONTH_DAYS = 365  # 12M
HALF_MONTH_DAYS = 182  # 6M
MATURE_WINDOW_DAYS = 180
BRAND_BASELINE_DAYS = 180


def _fmt_int(v: float | int) -> str:
    return f"{int(round(v)):,}"


def _fmt_pct(v: float | None, nd: int = 1) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v * 100:.{nd}f}%"


def _retail_mask(order_type: pd.Series) -> pd.Series:
    ot = order_type.fillna("").astype("string")
    return ot.isin(["", "用户车"])


def _phase_bounds(p: dict, as_of: pd.Timestamp, horizon_days: int) -> dict:
    start = pd.Timestamp(p["start"]).normalize()
    end = pd.Timestamp(p["end"]).normalize()
    finish = pd.Timestamp(p.get("finish") or p["end"]).normalize()
    total_end = min(end + pd.Timedelta(days=horizon_days), as_of.normalize())
    return {
        "start": start,
        "end": end,
        "finish": finish,
        "burst_end": end + pd.Timedelta(days=LAUNCH_BURST_DAYS),
        "total_end": total_end,
        "full_window_obs": bool(as_of.normalize() >= end + pd.Timedelta(days=horizon_days)),
    }


def _window_locks(locks: pd.DataFrame, lo: pd.Timestamp, hi: pd.Timestamp) -> int:
    if pd.isna(lo) or pd.isna(hi) or hi <= lo:
        return 0
    return int(locks[(locks["lock_time"] >= lo) & (locks["lock_time"] < hi)]["order_number"].nunique())


def _window_daily_avg(df: pd.DataFrame, lo: pd.Timestamp, hi: pd.Timestamp, field: str) -> float:
    if pd.isna(lo) or pd.isna(hi) or hi <= lo:
        return 0.0
    sub = df[(df[field].notna()) & (df[field] >= lo) & (df[field] < hi)]
    if sub.empty:
        return 0.0
    days = (hi - lo).days
    return float(sub["order_number"].nunique()) / max(days, 1)


def _prev_generation(gen: str) -> str | None:
    fam = FAMILY_ORDER.get(FAMILY[gen], [])
    if gen not in fam:
        return None
    idx = fam.index(gen)
    return fam[idx - 1] if idx > 0 else None


def _brand_baseline(all_locks: pd.DataFrame, gen_bounds: dict, periods: dict, retail_df: pd.DataFrame) -> float:
    lo = gen_bounds["end"] - pd.Timedelta(days=BRAND_BASELINE_DAYS)
    hi = gen_bounds["end"]
    if hi <= lo:
        return 0.0
    activity_days: set = set()
    for g, p in periods.items():
        if not p.get("start") or not p.get("end"):
            continue
        s = pd.Timestamp(p["start"]).normalize()
        f = pd.Timestamp(p.get("finish") or p["end"]).normalize()
        d = s
        while d <= f:
            activity_days.add(d.date())
            d += pd.Timedelta(days=1)
    sub = retail_df[
        (retail_df["lock_time"].notna())
        & (retail_df["lock_time"] >= lo)
        & (retail_df["lock_time"] < hi)
        & ~(retail_df["lock_time"].dt.date.isin(activity_days))
    ]
    if sub.empty:
        return 0.0
    days = (hi - lo).days
    return float(sub["order_number"].nunique()) / max(days, 1)


def compute_generation(
    df: pd.DataFrame,
    retail_df: pd.DataFrame,
    locks: pd.DataFrame,
    gen: str,
    periods: dict,
    as_of: pd.Timestamp,
    horizon_days: int,
    prev_baseline: float,
    brand_baseline: float,
) -> dict:
    p = periods[gen]
    b = _phase_bounds(p, as_of, horizon_days)
    start, end, finish, burst_end, total_end = b["start"], b["end"], b["finish"], b["burst_end"], b["total_end"]
    full_window_obs = (as_of.normalize() >= end + pd.Timedelta(days=horizon_days))

    sub = df[df["series_group_logic"] == gen]
    retail = retail_df[retail_df["series_group_logic"] == gen]
    locks_g = locks[locks["series_group_logic"] == gen]

    presale_lock = _window_locks(locks_g, start, end)
    launch_burst = _window_locks(locks_g, end, burst_end)
    benefit = _window_locks(locks_g, burst_end, finish)
    steady = _window_locks(locks_g, finish, total_end)
    rhythm_lock = presale_lock + launch_burst + benefit
    total_lock = rhythm_lock + steady

    presale_pool = int(
        retail[
            (retail["intention_payment_time"].notna())
            & (retail["intention_payment_time"] >= start)
            & (retail["intention_payment_time"] < end)
        ]["order_number"].nunique()
    )

    rhythm_days = (finish - start).days if finish > start else 0

    inc_prev = rhythm_lock - prev_baseline * rhythm_days if prev_baseline > 0 else None
    inc_brand = rhythm_lock - brand_baseline * rhythm_days if brand_baseline > 0 else None
    inc_median = None
    share_median = None
    cands = [v for v in [inc_prev, inc_brand] if v is not None]
    if cands:
        cands_sorted = sorted(cands)
        inc_median = float(cands_sorted[len(cands_sorted) // 2])
        if inc_median == inc_brand:
            share_median = (inc_brand / total_lock) if total_lock else None
        elif inc_median == inc_prev:
            share_median = (inc_prev / total_lock) if total_lock else None
        else:
            share_median = ((inc_prev + inc_brand) / 2 / total_lock) if total_lock else None

    share_rhythm = rhythm_lock / total_lock if total_lock else None
    share_prev = (inc_prev / total_lock) if (inc_prev is not None and total_lock) else None
    share_brand = (inc_brand / total_lock) if (inc_brand is not None and total_lock) else None

    pool = retail[
        (retail["intention_payment_time"].notna())
        & (retail["intention_payment_time"] >= start)
        & (retail["intention_payment_time"] < end)
    ].copy()
    pool_locked = pool[pool["lock_time"].notna()]
    pool_delivered = pool[pool["delivery_date"].notna()]
    conv_rate = len(pool_locked) / len(pool) if len(pool) else None

    direct_lock = int(
        locks_g[
            (locks_g["lock_time"] >= start)
            & (locks_g["lock_time"] < total_end)
            & (locks_g["intention_payment_time"].isna() | (locks_g["intention_payment_time"] < start))
        ]["order_number"].nunique()
    )

    return {
        "generation": gen,
        "family": FAMILY[gen],
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "finish": finish.date().isoformat(),
        "rhythm_days": rhythm_days,
        "total_end": total_end.date().isoformat(),
        "full_window_obs": full_window_obs,
        "presale_lock": presale_lock,
        "launch_burst": launch_burst,
        "benefit": benefit,
        "steady": steady,
        "rhythm_lock": rhythm_lock,
        "total_lock": total_lock,
        "presale_pool": presale_pool,
        "share_rhythm": share_rhythm,
        "prev_baseline_daily": prev_baseline,
        "brand_baseline_daily": brand_baseline,
        "increment_prev": inc_prev,
        "increment_brand": inc_brand,
        "increment_median": inc_median,
        "share_median": share_median,
        "share_prev": share_prev,
        "share_brand": share_brand,
        "pool_locked": len(pool_locked),
        "pool_delivered": len(pool_delivered),
        "conv_rate": conv_rate,
        "direct_lock": direct_lock,
    }


def build_summary(rows: list[dict]) -> str:
    if not rows:
        return "无数据"
    valid_share = [r["share_rhythm"] for r in rows if r["share_rhythm"] is not None]
    med = sorted(valid_share)[len(valid_share) // 2] if valid_share else None
    med_inc = None
    incs = [r["increment_median"] for r in rows if r["increment_median"] is not None]
    if incs:
        med_inc = sorted(incs)[len(incs) // 2]
    part = _fmt_pct(med) if med is not None else "—"
    inc_part = _fmt_int(med_inc) if med_inc is not None else "—"
    return (
        f"{len(rows)} 个代际上市节奏窗口（预售→上市→权益结束）锁单占总量中位 {part}；"
        f"基线差值法估算中位增量 {inc_part} 单"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="上市节奏增量贡献研究：阶段占比 + 基线差值 + 预售池转化")
    parser.add_argument("--as-of", type=str, default=None, help="统计基准日 YYYY-MM-DD（默认今天）")
    parser.add_argument("--format", choices=["terminal", "json"], default="terminal")
    parser.add_argument("--output", type=str, default=str(_DEFAULT_OUTPUT), help="CSV/JSON 输出目录")
    parser.add_argument("--html", action="store_true", help="生成品牌化 HTML 研究报告")
    parser.add_argument("--report-output", type=str, default=str(_DEFAULT_REPORT), help="HTML 报告输出路径")
    args = parser.parse_args(argv)

    if not _ORDER_DATA.exists():
        print(f"❌ 文件不存在: {_ORDER_DATA}")
        return 1

    business_def = load_business_definition(_BUSINESS_DEF)
    asts = {g: _parse_logic(_rule_condition(c)) for g, c in business_def["series_group_logic"].items()}
    periods = business_def.get("time_periods", {}) or {}

    print(f"📖 Loading: {_ORDER_DATA}")
    df = pd.read_parquet(_ORDER_DATA)
    for c in ["lock_time", "intention_payment_time", "intention_refund_time", "deposit_payment_time", "delivery_date"]:
        if not pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = pd.to_datetime(df[c], errors="coerce")
    df = apply_series_group_logic(df, business_def, asts)

    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp(datetime.now().date())
    as_of = min(as_of, pd.Timestamp(df["lock_time"].max()).normalize() + pd.Timedelta(days=1))

    retail_df = df[_retail_mask(df["order_type"])].copy()
    locks = df[df["lock_time"].notna()].copy()
    all_locks = locks[_retail_mask(locks["order_type"])].copy()

    horizons = {"12M": MONTH_DAYS, "6M": HALF_MONTH_DAYS}
    out_rows: dict[str, list[dict]] = {}
    warnings: list[str] = []

    for hname, hdays in horizons.items():
        rows = []
        for g in GENERATIONS:
            if g not in periods or not periods[g].get("start") or not periods[g].get("end"):
                warnings.append(f"{g} 缺少 start/end，跳过")
                continue
            b = _phase_bounds(periods[g], as_of, hdays)
            prev = _prev_generation(g)
            prev_baseline = 0.0
            if prev and prev in periods and periods[prev].get("finish"):
                pf = pd.Timestamp(periods[prev]["finish"]).normalize()
                prev_baseline = _window_daily_avg(
                    all_locks, pf, pf + pd.Timedelta(days=MATURE_WINDOW_DAYS), "lock_time"
                )
            brand_baseline = _brand_baseline(all_locks, b, periods, all_locks)
            rows.append(
                compute_generation(df, retail_df, all_locks, g, periods, as_of, hdays, prev_baseline, brand_baseline)
            )
            if not b["full_window_obs"] and g not in (COMPARE_GEN,):
                warnings.append(f"{g} 在 {hname} 窗口未完全观测（as_of {as_of.date()}），总量为至今累计")
        out_rows[hname] = rows

    rows_12 = out_rows["12M"]
    summary = build_summary(rows_12)

    gen_dm2 = None
    if COMPARE_GEN in periods and periods[COMPARE_GEN].get("end"):
        b = _phase_bounds(periods[COMPARE_GEN], as_of, MONTH_DAYS)
        start = b["start"]
        end = b["end"]
        finish = b["finish"]
        sub = all_locks[all_locks["series_group_logic"] == COMPARE_GEN]
        obs_end = min(finish, as_of.normalize() + pd.Timedelta(days=1))
        dm2_lock = _window_locks(sub, end, obs_end)
        dm2_kept = int(
            sub[
                (sub["lock_time"] >= end)
                & (sub["lock_time"] < obs_end)
                & sub["approve_refund_time"].isna()
            ]["order_number"].nunique()
        ) if "approve_refund_time" in sub.columns else dm2_lock
        gen_dm2 = {
            "generation": COMPARE_GEN,
            "end": end.date().isoformat(),
            "finish": finish.date().isoformat(),
            "lock_cum": dm2_lock,
            "kept_cum": dm2_kept,
            "launch_days": (as_of.normalize() - end).days,
        }

    result = {
        "summary": summary,
        "metrics": {
            "generations": len(GENERATIONS),
            "rhythm_share_median_12m": build_summary(rows_12).split("；")[0],
        },
        "dimensions": [
            {
                "name": "generation_12m",
                "items": [
                    {
                        "value": r["generation"],
                        "metrics": {
                            "rhythm_lock": r["rhythm_lock"],
                            "total_lock": r["total_lock"],
                            "share_rhythm": round(r["share_rhythm"], 4) if r["share_rhythm"] is not None else None,
                            "increment_median": r["increment_median"],
                        },
                    }
                    for r in rows_12
                ],
            }
        ],
    }

    scope = {
        "data_source": "dataset/order_data.parquet + shared/schema/business_definition.json",
        "time_window": {"start_date": min(periods[g]["start"] for g in GENERATIONS if periods[g].get("start")), "end_date": as_of.date().isoformat()},
        "filters": {"order_type": "用户车/NaN（零售口径）", "series_group_logic": GENERATIONS},
        "metric_definition": "上市节奏窗口=[start,finish]锁单/总量窗口=[start,end+12M]锁单；增量=窗口实际−基线日均×窗口天数",
    }

    artifacts: dict = {}
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    for hname, rows in out_rows.items():
        fname = out_dir / f"launch_rhythm_{hname.lower()}.csv"
        pd.DataFrame(rows).to_csv(fname, index=False, encoding="utf-8-sig")
        artifacts[hname] = str(fname)
    if gen_dm2:
        pd.DataFrame([gen_dm2]).to_csv(out_dir / "launch_rhythm_dm2_current.csv", index=False, encoding="utf-8-sig")
        artifacts["dm2_current"] = str(out_dir / "launch_rhythm_dm2_current.csv")

    if args.format == "json":
        contract = build_success_contract(
            script="mashang_workspace/research_scripts/launch_rhythm_incremental_analysis.py",
            command="launch_rhythm_incremental_analysis.py " + " ".join(argv or []),
            scope=scope,
            result=result,
            artifacts=artifacts,
            followup_context={
                "metric": "lock_count",
                "available_dimensions": ["generation", "family", "phase"],
                "top_entities": [{"field": "generation", "value": r["generation"], "metrics": {"share_rhythm": r["share_rhythm"]}} for r in rows_12],
            },
            warnings=warnings,
        )
        save_contract_json(contract, out_dir / "launch_rhythm_contract.json")
        print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print("=" * 100)
        print(f"上市节奏增量贡献研究 · as-of {as_of.date()} · 总量窗口 end+12M")
        print("=" * 100)
        for hname, rows in out_rows.items():
            print(f"\n--- 证据线 A+B：阶段占比 + 基线差值（{hname} 窗口）---")
            hdr = f"{'代际':<5}{'车系':<5}{'节奏窗口':<11}{'总量':>8}{'预售锁':>7}{'上市爆':>7}{'权益期':>7}{'常态期':>7}{'窗口占比':>9}{'增量(中)':>10}{'增量占比':>9}"
            print(hdr)
            for r in rows:
                print(
                    f"{r['generation']:<5}{r['family']:<5}{r['rhythm_days']}d       "
                    f"{_fmt_int(r['total_lock']):>8}{r['presale_lock']:>7}{r['launch_burst']:>7}{r['benefit']:>7}{r['steady']:>7}"
                    f"{_fmt_pct(r['share_rhythm']):>9}"
                    f"{_fmt_int(r['increment_median']) if r['increment_median'] is not None else '—':>10}"
                    f"{_fmt_pct(r['share_median']):>9}"
                )
        print("\n--- 证据线 C：预售池转化 ---")
        for r in rows_12:
            print(
                f"{r['generation']:<5} 预售小订池 {_fmt_int(r['presale_pool']):>7} → 锁单 {_fmt_int(r['pool_locked']):>6} "
                f"({_fmt_pct(r['conv_rate'])})  → 交付 {_fmt_int(r['pool_delivered']):>6} ｜ 窗口内直接锁单 {_fmt_int(r['direct_lock']):>6}"
            )
        if gen_dm2:
            print(
                f"\n--- {COMPARE_GEN} 当前对照（上市 {gen_dm2['launch_days']} 天）---"
                f"\n  上市至今累计锁单 {_fmt_int(gen_dm2['lock_cum'])}，留存 {_fmt_int(gen_dm2['kept_cum'])}"
            )
        if warnings:
            print("\n[Warnings]")
            for w in warnings:
                print(f"  ⚠ {w}")
        print("\n[Output]")
        for k, v in artifacts.items():
            print(f"  {k.upper()}: {v}")

    if args.html:
        from research_scripts.launch_rhythm_incremental_html import render_html_report
        render_html_report(
            rows_12=rows_12,
            rows_6=out_rows["6M"],
            gen_dm2=gen_dm2,
            as_of=as_of,
            output=Path(args.report_output),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
