#!/usr/bin/env python3
"""Shock Detector 早期规则雏形：观测窗口末段扫描新品冲击者，验证命中率。

概念见 docs/market_state_v0_2_design.md §8.7（Shock Detector / Breakout Entry）。

早期信号（观测窗口末段可观察）：
  - 末段月均销量 ≥ RAMP_BREAKOUT（2000）
  - 爬坡 = 末段月均 / 首段月均 ≥ 阈值
  - 末段进入该市场 TOP10

验证（验证窗口 12M）：
  - 新品成为爆款（12M 销量 ≥ BREAKOUT_12M = 5万）
  - 命中率 vs 全部新品成为爆款的 baseline

三期 freeze：2023-03 / 2024-03 / 2025-03，均 point-in-time（观测信号只来自观测窗口）。

输出：
  outputs/tables/shock_detector_scan_{tag}.csv
  outputs/reports/shock_detector_scan_{tag}.md
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
import tp_and_mix_ways_market_volume as mv  # noqa: E402

RAMP_BREAKOUT = 2000
BREAKOUT_12M = 50000
TOP10_RANK = 10
RAMP_MIN = 2.0
RAMP_STRONG = 3.0
TAIL_MONTHS = 3  # 末段观察月数

PERIODS = [
    {"freeze": "2023-03", "obs_start": "2022-04-01", "obs_end": "2023-03-31", "val_start": "2023-04-01", "val_end": "2024-03-31"},
    {"freeze": "2024-03", "obs_start": "2023-04-01", "obs_end": "2024-03-31", "val_start": "2024-04-01", "val_end": "2025-03-31"},
    {"freeze": "2025-03", "obs_start": "2024-04-01", "obs_end": "2025-03-31", "val_start": "2025-04-01", "val_end": "2026-03-31"},
]


def load_model():
    model = load_tp_and_mix_ways_table("model_monthly").copy()
    model["date_month"] = pd.to_datetime(model["date_month"])
    model["price_bucket"] = model["weighted_tp"].map(mv.map_tp_to_5w).replace({"价格缺失/无效": "其他"})
    model["price_bucket"] = model["price_bucket"].astype(str)
    return model


def monthly_top10(model: pd.DataFrame, start: str, end: str):
    """观测窗口内每月每市场 TOP10 车型集（仅新能源）。"""
    obs = model[model.date_month.between(start, end)]
    obs = obs[obs.price_bucket != "其他"]
    top10 = {}
    for month, d in obs.groupby("date_month"):
        for (pb, bt, ft), g in d.groupby(["price_bucket", "body_type", "fuel_type_group"]):
            if ft != "新能源":
                continue
            rank = g.groupby(["brand", "model"])["sales"].sum().sort_values(ascending=False).head(TOP10_RANK)
            top10[(pb, bt, month, "新能源")] = set(rank.index)
    return top10


def scan_period(period: dict, model: pd.DataFrame, top10: dict) -> pd.DataFrame:
    """单期：识别 obs 窗口内新上市车型的早期冲击信号，验证窗口结果。"""
    obs = model[model.date_month.between(period["obs_start"], period["obs_end"])].copy()
    obs = obs[obs.price_bucket != "其他"]
    obs_start_ts = pd.Timestamp(period["obs_start"])
    obs_end_ts = pd.Timestamp(period["obs_end"])
    tail_ts = obs_end_ts - pd.DateOffset(months=TAIL_MONTHS - 1)

    rows = []
    # 每个 (market, brand, model) 组合：判断是否新品（首次活跃在 obs 窗口内）
    first_map = model.groupby(["price_bucket", "body_type", "fuel_type_group", "brand", "model"])["date_month"].min()
    for (pb, bt, ft, brand, mdl), first in first_map.items():
        if first < obs_start_ts or first > obs_end_ts:
            continue
        d = obs[(obs.price_bucket == pb) & (obs.body_type == bt) & (obs.fuel_type_group == ft)
                & (obs.brand == brand) & (obs.model == mdl)]
        if d.empty:
            continue
        d = d.sort_values("date_month")
        # 首段 3 月与末段 3 月
        first3 = d.head(3)
        tail = d[d.date_month >= tail_ts]
        first3_avg = float(first3.sales.mean()) if len(first3) else 0
        tail_avg = float(tail.sales.mean()) if len(tail) else 0
        ramp = (tail_avg / first3_avg) if first3_avg > 0 else None
        # 末段进入 TOP10
        top10_hit = any((pb, bt, m, ft) in top10 and (brand, mdl) in top10[(pb, bt, m, ft)]
                        for m in d[d.date_month >= tail_ts].date_month)
        # 验证窗口
        val = model[(model.date_month >= period["val_start"]) & (model.date_month <= period["val_end"])
                    & (model.price_bucket == pb) & (model.body_type == bt) & (model.fuel_type_group == ft)
                    & (model.brand == brand) & (model.model == mdl)]
        val_12m = float(val.sales.sum())
        is_breakout = val_12m >= BREAKOUT_12M

        # 分级
        if tail_avg >= RAMP_BREAKOUT and ramp is not None and ramp >= RAMP_STRONG and top10_hit:
            tier = "Strong"
        elif tail_avg >= RAMP_BREAKOUT and ((ramp is not None and ramp >= RAMP_MIN) or top10_hit):
            tier = "Candidate"
        else:
            tier = "None"
        rows.append({
            "freeze": period["freeze"], "price_bucket": pb, "body_type": bt, "fuel_type_group": ft,
            "brand": brand, "model": mdl,
            "first_active": str(first)[:7], "first3_avg": first3_avg, "tail3_avg": tail_avg,
            "ramp": ramp, "top10_hit": top10_hit, "tier": tier,
            "val_12m": val_12m, "is_breakout": is_breakout,
        })
    return pd.DataFrame(rows)


def market_state_increment(all_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """2×2 增量检验：Shock（候选/否）× CES（高/低）→ 后续爆款率。

    回答：Market State（CES）在 Shock Detector 之上有没有增量信息。
    仅用新能源市场新品（市场级 CES 来自 market_state_v0_2_{freeze}.csv）。
    """
    frames = []
    for freeze in sorted(all_df["freeze"].unique()):
        tag = freeze.replace("-", "")
        path = _OUTPUT / "tables" / f"market_state_v0_2_{tag}.csv"
        if not path.exists():
            continue
        ces = pd.read_csv(path)[["price_bucket", "body_type", "CES_score"]]
        sub = all_df[(all_df.freeze == freeze) & (all_df.fuel_type_group == "新能源")].copy()
        sub = sub.merge(ces, on=["price_bucket", "body_type"], how="left")
        frames.append(sub)
    if not frames:
        return pd.DataFrame(), pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True).dropna(subset=["CES_score"])
    merged["shock"] = merged["tier"].isin(["Strong", "Candidate"])
    merged["ces_high"] = merged["CES_score"] >= 0.20

    rows = []
    for shock in [False, True]:
        for ces_hi in [False, True]:
            d = merged[(merged["shock"] == shock) & (merged["ces_high"] == ces_hi)]
            n = len(d)
            hit = int(d["is_breakout"].sum())
            rate = hit / n * 100 if n else None
            rows.append({"Shock": "候选" if shock else "否", "CES": "高(≥0.2)" if ces_hi else "低(<0.2)",
                         "n": n, "爆款数": hit, "爆款率": rate})
    grid = pd.DataFrame(rows)
    return grid, merged


def write_report(all_df: pd.DataFrame, path: Path) -> None:
    lines = [
        "# Shock Detector 早期规则雏形：观测窗口末段扫描新品冲击者",
        "",
        f"早期信号（观测窗口末段 {TAIL_MONTHS} 个月）：末段月均≥{RAMP_BREAKOUT}、爬坡≥{RAMP_MIN}/{RAMP_STRONG}、进入 TOP{TOP10_RANK}。",
        f"验证：验证窗口 12M 销量 ≥ {BREAKOUT_12M} 视为爆款。",
        "",
        "## 命中率（识别冲击者 vs 全部新品 baseline）",
        "",
        "|freeze|分级|n|其中爆款|命中率|",
        "|---|---|---:|---:|---:|",
    ]
    for freeze, g in all_df.groupby("freeze"):
        for tier, m in [("Strong", g.tier == "Strong"), ("Candidate", g.tier == "Candidate"),
                        ("全部新品(基线)", pd.Series(True, index=g.index))]:
            sub = g[m]
            hit = int(sub.is_breakout.sum())
            rate = hit / len(sub) * 100 if len(sub) else None
            lines.append(f"|{freeze}|{tier}|{len(sub)}|{hit}|{mv._fmt(rate, '%') if hasattr(mv,'_fmt') else ''}")
    # 合计
    for tier, m in [("Strong", all_df.tier == "Strong"), ("Candidate", all_df.tier == "Candidate"),
                    ("Strong+Candidate", all_df.tier.isin(["Strong", "Candidate"])),
                    ("全部新品(基线)", pd.Series(True, index=all_df.index))]:
        sub = all_df[m]
        hit = int(sub.is_breakout.sum())
        rate = hit / len(sub) * 100 if len(sub) else None
        lines.append(f"|**合计**|{tier}|{len(sub)}|{hit}|{rate:.1f}%|")
    lines += ["", "## 识别出的候选冲击者（含验证结果）", "",
              "|freeze|市场|车型|首月|末段月均|爬坡|进TOP10|分级|验证12M|爆款|",
              "|---|---|---|---:|---:|---:|---|---:|---|"]
    cand = all_df[all_df.tier.isin(["Strong", "Candidate"])].sort_values(["freeze", "tier", "val_12m"], ascending=[True, True, False])
    for r in cand.itertuples():
        lines.append(f"|{r.freeze}|{r.price_bucket}{r.body_type}|{r.brand}{r.model}|{r.first_active}|{r.tail3_avg:,.0f}|"
                     f"{'-' if r.ramp is None else f'{r.ramp:.1f}'}|{'是' if r.top10_hit else '否'}|{r.tier}|{r.val_12m:,.0f}|{'✓' if r.is_breakout else ''}|")
    lines += ["", "## Market State（CES）增量检验：2×2 爆款率", "",
              "回答：在 Shock Detector 之上，Market State（CES 高低）有没有增量信息？",
              "",
              "| |CES 低(<0.2)|CES 高(≥0.2)|",
              "|---|---|---|", ]
    grid, _ = market_state_increment(all_df)
    if not grid.empty:
        def _cell(shock, ces):
            row = grid[(grid.Shock == shock) & (grid.CES == ces)]
            return f"{row['爆款率'].iloc[0]:.1f}% (n={row['n'].iloc[0]}, 爆款{row['爆款数'].iloc[0]})" if len(row) and not pd.isna(row['爆款率'].iloc[0]) else "-"
        lines.append(f"|**Shock 否**|{_cell('否','低(<0.2)')}|{_cell('否','高(≥0.2)')}|")
        lines.append(f"|**Shock 候选**|{_cell('候选','低(<0.2)')}|{_cell('候选','高(≥0.2)')}|")
    lines += ["", "## 口径与限制", "",
              "- 新品 = 该 价格带×车身×能源 市场内首次活跃落在观测窗口的车型。",
              "- 信号只用观测窗口末段 3 个月（point-in-time），验证窗口 12M 只看结果。",
              "- 2×2 增量检验仅覆盖有市场级 CES 的新能源市场（规模≥10万），Shock 候选含 Strong+Candidate。",
              "- 分级为启发式阈值，属 Shock Detector 雏形，非 production rule。"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Shock Detector 早期规则雏形：观测窗口末段扫描新品冲击者")
    parser.add_argument("--output-dir", default=str(_OUTPUT), help="输出根目录")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()

    output_root = Path(args.output_dir)
    table_dir = output_root / "tables"
    report_dir = output_root / "reports"
    table_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    model = load_model()
    frames = []
    for period in PERIODS:
        top10 = monthly_top10(model, period["obs_start"], period["obs_end"])
        frames.append(scan_period(period, model, top10))
    all_df = pd.concat(frames, ignore_index=True)

    tag = "2022-04_2026-03"
    all_df.to_csv(table_dir / f"shock_detector_scan_{tag}.csv", index=False, encoding="utf-8-sig")
    report_path = report_dir / f"shock_detector_scan_{tag}.md"
    write_report(all_df, report_path)

    if args.format == "json":
        cand = all_df[all_df.tier.isin(["Strong", "Candidate"])]
        grid, _ = market_state_increment(all_df)
        print(json.dumps({"status": "success", "script": "research_scripts/shock_detector_scan.py",
                          "result": {"strong": int((all_df.tier == "Strong").sum()),
                                     "candidate": int((all_df.tier == "Candidate").sum()),
                                     "breakout_baseline": f"{all_df.is_breakout.mean()*100:.1f}%",
                                     "cand_hit_rate": f"{cand.is_breakout.mean()*100:.1f}%" if len(cand) else None,
                                     "market_state_increment_2x2": grid.to_dict(orient="records")},
                          "artifacts": {"report": str(report_path)}}, ensure_ascii=False, indent=2))
    else:
        print("=== Shock Detector 扫描（观测窗口末段 → 验证窗口爆款）===")
        for tier in ["Strong", "Candidate", "全部新品(基线)"]:
            if tier == "全部新品(基线)":
                sub = all_df
            else:
                sub = all_df[all_df.tier == tier]
            hit = int(sub.is_breakout.sum())
            rate = hit / len(sub) * 100 if len(sub) else 0
            print(f"  {tier}: n={len(sub)} 爆款={hit} 命中率={rate:.1f}%")
        print("\n=== Market State（CES）增量检验 2×2 ===")
        grid, merged = market_state_increment(all_df)
        if not grid.empty:
            print(grid.to_string(index=False))
        print(f"\nreport={report_path}")


if __name__ == "__main__":
    main()
