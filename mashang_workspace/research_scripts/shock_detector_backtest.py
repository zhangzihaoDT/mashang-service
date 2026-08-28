#!/usr/bin/env python3
"""Shock Detector 滚动回溯验证。

对多个历史 as-of 月份运行滚动扫描（只用 as-of 之前的数据），
验证识别的 SHOCK_CANDIDATE / SHOCK_CONFIRMED 在 as-of 之后 12M 是否真的成为爆款（12M 销量≥5万）。

as-of 选择保证后续 12M 数据完整（数据至 2026-07）：
  2023-06 / 2023-12 / 2024-06 / 2024-12 / 2025-06

输出：
  outputs/tables/shock_detector_backtest_{tag}.csv
  outputs/reports/shock_detector_backtest_{tag}.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
_RESEARCH_DIR = ROOT / "mashang_workspace" / "research_scripts"
_OUTPUT = ROOT / "mashang_workspace" / "outputs"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(_RESEARCH_DIR))

from shared.loaders.tp_and_mix_ways_loader import load_tp_and_mix_ways_table  # noqa: E402
import shock_detector_rolling as rolling  # noqa: E402
import tp_and_mix_ways_market_volume as mv  # noqa: E402

BREAKOUT_12M = 50000
AS_OF_DATES = ["2023-06", "2023-12", "2024-06", "2024-12", "2025-06"]


def validate(df: pd.DataFrame, model: pd.DataFrame) -> pd.DataFrame:
    """对每行（新品×目标市场）计算 as_of 后 12M 销量与爆款。"""
    rows = []
    for r in df.itertuples():
        parts = r.target_market.split(" ", 2)
        pb, bt, ft = parts[0], parts[1], parts[2]
        as_of = pd.Timestamp(r.as_of + "-01")
        end = as_of + pd.DateOffset(months=13)
        val = model[(model.date_month > as_of) & (model.date_month < end)
                    & (model.brand == r.brand) & (model.model == r.model)
                    & (model.price_bucket == pb) & (model.body_type == bt) & (model.fuel_type_group == ft)]
        val_12m = float(val.sales.sum())
        rows.append({"as_of": r.as_of, "brand": r.brand, "model": r.model, "target_market": r.target_market,
                     "shock_state": r.shock_state, "tail_monthly_sales": r.tail_monthly_sales,
                     "val_12m": val_12m, "is_breakout": val_12m >= BREAKOUT_12M})
    return pd.DataFrame(rows)


def _fmt(v, suffix="", ndigits=1, na="-"):
    return na if v is None or pd.isna(v) else f"{v:,.{ndigits}f}{suffix}"


def write_report(df: pd.DataFrame, path: Path) -> None:
    lines = [
        "# Shock Detector 滚动回溯验证",
        "",
        f"对历史 as-of 运行滚动扫描（只用 as-of 之前数据），验证识别状态在 as-of 后 12M 是否成为爆款（12M 销量≥{BREAKOUT_12M}）。",
        "",
        "## 命中率（按状态 × as-of）",
        "",
        "|as-of|分级|n|爆款|命中率|",
        "|---|---|---:|---:|---:|",
    ]
    for asof, g in df.groupby("as_of"):
        for tier, m in [("SHOCK_CONFIRMED", g.shock_state == "SHOCK_CONFIRMED"),
                        ("SHOCK_CANDIDATE", g.shock_state == "SHOCK_CANDIDATE"),
                        ("全部新品(基线)", pd.Series(True, index=g.index))]:
            sub = g[m]
            hit = int(sub.is_breakout.sum())
            rate = hit / len(sub) * 100 if len(sub) else None
            lines.append(f"|{asof}|{tier}|{len(sub)}|{hit}|{_fmt(rate, '%') if rate is not None else '-'}")
    lines += ["", "## 合计命中率", "",
              "|分级|n|爆款|命中率|", "|---|---|---:|---:|"]
    for tier, m in [("SHOCK_CONFIRMED", df.shock_state == "SHOCK_CONFIRMED"),
                    ("SHOCK_CANDIDATE", df.shock_state == "SHOCK_CANDIDATE"),
                    ("候选合计(CANDIDATE+CONFIRMED)", df.shock_state != "SHOCK_NONE"),
                    ("全部新品(基线)", pd.Series(True, index=df.index))]:
        sub = df[m]
        hit = int(sub.is_breakout.sum())
        rate = hit / len(sub) * 100 if len(sub) else None
        lines.append(f"|{tier}|{len(sub)}|{hit}|{_fmt(rate, '%') if rate is not None else '-'}")
    lines += ["", "## 候选明细（含验证结果）", "",
              "|as-of|车型|目标市场|状态|末段月均|验证12M|爆款|",
              "|---|---|---|---|---:|---:|---|"]
    cand = df[df.shock_state != "SHOCK_NONE"].sort_values(["as_of", "shock_state", "val_12m"], ascending=[True, True, False])
    for r in cand.itertuples():
        lines.append(f"|{r.as_of}|{r.brand}{r.model}|{r.target_market}|{r.shock_state}|{r.tail_monthly_sales:,.0f}|{r.val_12m:,.0f}|{'✓' if r.is_breakout else ''}|")
    lines += ["", "## 口径与限制", "",
              "- 滚动扫描只用 as-of 之前 6 个月数据（point-in-time），验证用 as-of 后 12M。",
              "- as-of 选点保证后续 12M 完整（数据至 2026-07）。",
              "- 分级阈值（末段月均≥2000/10000、持续≥3月）沿用 classifier spec，属 research 状态。"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Shock Detector 滚动回溯验证")
    parser.add_argument("--output-dir", default=str(_OUTPUT), help="输出根目录")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()

    output_root = Path(args.output_dir)
    table_dir = output_root / "tables"
    report_dir = output_root / "reports"
    table_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    model, price = rolling.load()
    frames = []
    for asof in AS_OF_DATES:
        scan = rolling.scan(model, price, pd.Timestamp(asof + "-01"))
        scan["as_of"] = asof
        frames.append(scan)
    all_scan = pd.concat(frames, ignore_index=True)
    df = validate(all_scan, model)

    tag = "2023-06_2025-06"
    df.to_csv(table_dir / f"shock_detector_backtest_{tag}.csv", index=False, encoding="utf-8-sig")
    report_path = report_dir / f"shock_detector_backtest_{tag}.md"
    write_report(df, report_path)

    if args.format == "json":
        print(json.dumps({"status": "success", "script": "research_scripts/shock_detector_backtest.py",
                          "result": df.groupby(["as_of", "shock_state"]).apply(
                              lambda d: {"n": len(d), "breakout": int(d.is_breakout.sum()),
                                         "rate": f"{d.is_breakout.mean()*100:.1f}%"}).to_dict(),
                          "artifacts": {"report": str(report_path)}}, ensure_ascii=False, indent=2))
    else:
        print("=== Shock Detector 滚动回溯（历史 as-of → 后续12M爆款）===")
        for asof, g in df.groupby("as_of"):
            for tier in ["SHOCK_CONFIRMED", "SHOCK_CANDIDATE"]:
                sub = g[g.shock_state == tier]
                if len(sub):
                    hit = int(sub.is_breakout.sum())
                    print(f"  {asof} {tier}: n={len(sub)} 爆款={hit} 命中率={hit/len(sub)*100:.1f}%")
        print("\n=== 合计 ===")
        for tier, m in [("SHOCK_CONFIRMED", df.shock_state == "SHOCK_CONFIRMED"),
                        ("SHOCK_CANDIDATE", df.shock_state == "SHOCK_CANDIDATE"),
                        ("候选合计", df.shock_state != "SHOCK_NONE"),
                        ("全部新品(基线)", pd.Series(True, index=df.index))]:
            sub = df[m]
            hit = int(sub.is_breakout.sum())
            rate = hit / len(sub) * 100 if len(sub) else 0
            print(f"  {tier}: n={len(sub)} 爆款={hit} 命中率={rate:.1f}%")
        print(f"\nreport={report_path}")


if __name__ == "__main__":
    main()
