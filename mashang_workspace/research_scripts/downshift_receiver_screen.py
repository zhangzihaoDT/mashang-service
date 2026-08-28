#!/usr/bin/env python3
"""Downshift Receiver（下沉承接市场）初步验证。

概念定义见 docs/market_state_v0_2_design.md §8.6（V0.3 假说，非最终规则）。

用三期数据识别 Downshift Receiver 候选价格带，并检验这些市场未来 12 个月是否真的继续扩容：
  - freeze 2024-03：obs 2023-04~2024-03（vs 前一期 2022-04~2023-03）→ 信号；验证 2024-04~2025-03
  - freeze 2025-03：obs 2024-04~2025-03（vs 前一期 2023-04~2024-03）→ 信号；验证 2025-04~2026-03

必要条件（须同时满足）：
  1) 本带份额明显上升（share_delta_pp ≥ +1.0）
  2) 整体 Price Gravity 下移（gravity_delta < 0）
  3) 上一级价格带承压（上一档销量下降）
增强信号：
  E1) CES 高（读取 market_state_v0_2_{freeze}.csv，须先运行 historical_opportunity_validation.py）
  E2) 本带 TOP3 位置靠上沿（top3_price_position ≥ 0.5）

输出：
  outputs/tables/downshift_receiver_screen_{tag}.csv
  outputs/reports/downshift_receiver_validation_{tag}.md
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
import price_band_migration as pbm  # noqa: E402  (复用价格带迁移的辅助函数)

SHARE_SIGNIFICANT_PP = 1.0
EXPANSION_MIN = 10.0
TOP3_POSITION_HIGH = 0.5

PERIODS = [
    {"freeze": "2024-03", "prev_obs": ("2022-04-01", "2023-03-31"), "obs": ("2023-04-01", "2024-03-31"),
     "val": ("2024-04-01", "2025-03-31")},
    {"freeze": "2025-03", "prev_obs": ("2023-04-01", "2024-03-31"), "obs": ("2024-04-01", "2025-03-31"),
     "val": ("2025-04-01", "2026-03-31")},
]


def _unit_gravity(price: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """单位（车身×能源）整体 Price Gravity（万元）。"""
    p = price[price.date_month.between(start, end)].copy()
    p = p[p.price_bucket.isin(pbm.BANDS)]
    rows = []
    for (bt, ft), g in p.groupby(["body_type", "fuel_type_group"]):
        total = float(g.sales.sum())
        grav = float(sum(pbm.band_midpoint(r.price_bucket) * r.sales for r in g.itertuples()) / total) if total else None
        rows.append({"body_type": bt, "fuel_type_group": ft, "price_gravity": grav})
    return pd.DataFrame(rows)


def _read_ces(freeze: str) -> pd.DataFrame:
    path = _OUTPUT / "tables" / f"market_state_v0_2_{freeze.replace('-', '')}.csv"
    if not path.exists():
        return pd.DataFrame(columns=["price_bucket", "body_type", "CES_score"])
    df = pd.read_csv(path)
    return df[["price_bucket", "body_type", "CES_score"]].rename(columns={"price_bucket": "band", "body_type": "unit"})


def screen_period(period: dict, price: pd.DataFrame, model: pd.DataFrame) -> pd.DataFrame:
    """单 freeze：计算信号、判定 Downshift Receiver、验证后续 12M 扩容。"""
    prev_band = pbm.unit_band_sales(price, *period["prev_obs"])
    obs_band = pbm.unit_band_sales(price, *period["obs"])
    val_band = pbm.unit_band_sales(price, *period["val"])

    g_prev = _unit_gravity(price, *period["prev_obs"]).set_index(["body_type", "fuel_type_group"])
    g_obs = _unit_gravity(price, *period["obs"]).set_index(["body_type", "fuel_type_group"])

    obs = obs_band.merge(prev_band.rename(columns={"sales": "prev_sales"}),
                         on=["body_type", "fuel_type_group", "price_bucket"], how="left")
    obs["share_pct"] = obs.groupby(["body_type", "fuel_type_group"])["sales"].transform(lambda s: s / s.sum() * 100)
    obs["prev_share_pct"] = obs.groupby(["body_type", "fuel_type_group"])["prev_sales"].transform(lambda s: s / s.sum() * 100)
    obs["share_delta_pp"] = obs["share_pct"] - obs["prev_share_pct"]
    obs["growth_pct"] = (obs.sales / obs.prev_sales - 1) * 100

    # 验证窗口新能源扩容
    val = val_band.rename(columns={"sales": "val_sales"})
    obs = obs.merge(val[["body_type", "fuel_type_group", "price_bucket", "val_sales"]],
                    on=["body_type", "fuel_type_group", "price_bucket"], how="left")
    obs["val_growth_pct"] = (obs.val_sales / obs.sales - 1) * 100
    obs["expanded"] = obs["val_growth_pct"] >= EXPANSION_MIN

    # 单位重力变化
    gravity = []
    for (bt, ft), _ in obs.groupby(["body_type", "fuel_type_group"]):
        gp = g_prev.loc[(bt, ft), "price_gravity"] if (bt, ft) in g_prev.index else None
        go = g_obs.loc[(bt, ft), "price_gravity"] if (bt, ft) in g_obs.index else None
        gravity.append({"body_type": bt, "fuel_type_group": ft, "gravity_delta": (go - gp) if (gp is not None and go is not None) else None})
    obs = obs.merge(pd.DataFrame(gravity), on=["body_type", "fuel_type_group"], how="left")

    # 上一档销量变化（承压）
    band_index = {b: i for i, b in enumerate(pbm.BANDS)}
    rows = []
    for r in obs.itertuples():
        idx = band_index.get(r.price_bucket)
        upper = pbm.BANDS[idx + 1] if idx is not None and idx + 1 < len(pbm.BANDS) else None
        upper_growth = pd.NA
        if upper:
            up_prev = prev_band[(prev_band.body_type == r.body_type) & (prev_band.fuel_type_group == r.fuel_type_group) & (prev_band.price_bucket == upper)]
            up_obs = obs_band[(obs_band.body_type == r.body_type) & (obs_band.fuel_type_group == r.fuel_type_group) & (obs_band.price_bucket == upper)]
            if len(up_prev) and len(up_obs) and float(up_prev.sales.iloc[0]):
                upper_growth = (float(up_obs.sales.iloc[0]) / float(up_prev.sales.iloc[0]) - 1) * 100
        rows.append({"price_bucket": r.price_bucket, "body_type": r.body_type, "fuel_type_group": r.fuel_type_group,
                     "upper_band_growth_pct": upper_growth})
    obs = obs.merge(pd.DataFrame(rows), on=["price_bucket", "body_type", "fuel_type_group"], how="left")

    # E2 本带 TOP3 位置
    obs_model = model[model.date_month.between(*period["obs"])].copy()
    obs_model = obs_model[obs_model.price_bucket.isin(pbm.BANDS) & (obs_model.sales > 0)]
    pos = pbm._top3_position(obs_model, period["freeze"])
    obs = obs.merge(pos[["body_type", "fuel_type_group", "price_bucket", "top3_price_position"]],
                    on=["body_type", "fuel_type_group", "price_bucket"], how="left")

    # E1 CES（读取已有计算结果）
    ces = _read_ces(period["freeze"])
    obs = obs.merge(ces, left_on=["price_bucket", "body_type"], right_on=["band", "unit"], how="left", suffixes=("", "_ces"))
    obs = obs.drop(columns=["band", "unit"], errors="ignore")

    # 判定
    def _tier(r):
        share_up = (not pd.isna(r.share_delta_pp)) and r.share_delta_pp >= SHARE_SIGNIFICANT_PP
        gravity_down = (not pd.isna(r.gravity_delta)) and r.gravity_delta < 0
        upper_press = (not pd.isna(r.upper_band_growth_pct)) and r.upper_band_growth_pct < 0
        if not (share_up and gravity_down and upper_press):
            return "非Receiver"
        e1 = (not pd.isna(r.CES_score)) and r.CES_score >= 0.20
        e2 = (not pd.isna(r.top3_price_position)) and r.top3_price_position >= TOP3_POSITION_HIGH
        if e1 and e2:
            return "Strong Receiver"
        if e1 or e2:
            return "Receiver"
        return "Weak Receiver"

    obs["receiver_tier"] = obs.apply(_tier, axis=1)
    obs["freeze"] = period["freeze"]
    return obs[["freeze", "body_type", "fuel_type_group", "price_bucket", "share_delta_pp", "gravity_delta",
                "upper_band_growth_pct", "CES_score", "top3_price_position", "receiver_tier",
                "sales", "val_sales", "val_growth_pct", "expanded"]]


def write_report(screen: pd.DataFrame, path: Path) -> None:
    lines = [
        "# Downshift Receiver（下沉承接市场）初步验证",
        "",
        "概念定义见 market_state_v0_2_design.md §8.6（V0.3 假说，非最终规则）。",
        "必要条件：本带份额升(≥+1pp) + 单位 Price Gravity 下移 + 上一档承压；增强：E1 CES 高、E2 本带 TOP3 靠上沿(≥0.5)。",
        f"验证：后续 12M 新能源销量增速 ≥ +{EXPANSION_MIN:.0f}% 视为扩容。",
        "",
        "## 识别结果与未来 12M 扩容",
        "",
        "|freeze|车身|能源|价格带|份额Δ(pp)|重力Δ(万)|上一档增%|CES|TOP3位置|判别|后续12M增%|扩容|",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---|",
    ]
    for r in screen.sort_values(["freeze", "receiver_tier", "body_type"]).itertuples():
        lines.append(
            f"|{r.freeze}|{r.body_type}|{r.fuel_type_group}|{r.price_bucket}|{pbm._fmt(r.share_delta_pp, ndigits=1)}|"
            f"{pbm._fmt(r.gravity_delta, ndigits=2)}|{pbm._fmt(r.upper_band_growth_pct,'%')}|{pbm._fmt(r.CES_score, ndigits=2)}|"
            f"{pbm._fmt(r.top3_price_position, ndigits=2)}|{r.receiver_tier}|{pbm._fmt(r.val_growth_pct,'%')}|{'是' if r.expanded else '否'}|"
        )
    # 命中率汇总
    lines += ["", "## 判别命中率（识别带 vs 未识别带）", "",
              "|freeze|判别|n|其中扩容|命中率|", "|---|---|---:|---:|---:|"]
    for freeze, g in screen.groupby("freeze"):
        for tier, mask in [("Receiver(含Strong)", g.receiver_tier.isin(["Strong Receiver", "Receiver", "Weak Receiver"])),
                           ("非Receiver", ~g.receiver_tier.isin(["Strong Receiver", "Receiver", "Weak Receiver"]))]:
            sub = g[mask]
            hit = int(sub.expanded.sum())
            rate = hit / len(sub) * 100 if len(sub) else None
            lines.append(f"|{freeze}|{tier}|{len(sub)}|{hit}|{pbm._fmt(rate,'%')}|")
    # 两期合并
    rec_mask = screen.receiver_tier.isin(["Strong Receiver", "Receiver", "Weak Receiver"])
    hit_all = int(screen[rec_mask].expanded.sum())
    n_all = int(rec_mask.sum())
    hit_non = int(screen[~rec_mask].expanded.sum())
    n_non = int((~rec_mask).sum())
    lines += [f"|**合计**|Receiver|{n_all}|{hit_all}|{pbm._fmt(hit_all/n_all*100 if n_all else None,'%')}|",
              f"|**合计**|非Receiver|{n_non}|{hit_non}|{pbm._fmt(hit_non/n_non*100 if n_non else None,'%')}|"]
    lines += ["", "## 口径与限制", "",
              "- 信号来自两期连续观测窗口对比（obs vs 前一 obs），可用的 freeze 为 2024-03 与 2025-03。",
              "- E1 CES 读取 market_state_v0_2_{freeze}.csv（须先运行 historical_opportunity_validation.py）；E2 本带 TOP3 位置来自 model 数据。",
              "- 判定为启发式（阈值 share≥+1pp、TOP3 位≥0.5、CES≥0.20），属 V0.3 假说验证，非 production rule。"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Downshift Receiver 初步验证：识别下沉承接价格带并检验后续扩容")
    parser.add_argument("--output-dir", default=str(_OUTPUT), help="输出根目录")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()

    output_root = Path(args.output_dir)
    table_dir = output_root / "tables"
    report_dir = output_root / "reports"
    table_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    price, model = pbm.load_data()
    screens = [screen_period(p, price, model) for p in PERIODS]
    screen = pd.concat(screens, ignore_index=True)

    tag = "2024-03_2025-03"
    screen.to_csv(table_dir / f"downshift_receiver_screen_{tag}.csv", index=False, encoding="utf-8-sig")
    report_path = report_dir / f"downshift_receiver_validation_{tag}.md"
    write_report(screen, report_path)

    rec = screen[screen.receiver_tier.isin(["Strong Receiver", "Receiver", "Weak Receiver"])]
    non = screen[~screen.receiver_tier.isin(["Strong Receiver", "Receiver", "Weak Receiver"])]
    hit_rec = int(rec.expanded.sum())
    hit_non = int(non.expanded.sum())

    if args.format == "json":
        print(json.dumps({
            "status": "success",
            "script": "research_scripts/downshift_receiver_screen.py",
            "scope": {"freeze_periods": [p["freeze"] for p in PERIODS], "concept": "Downshift Receiver（V0.3 假说）"},
            "result": {"receiver_identified": len(rec), "receiver_hit": hit_rec,
                       "receiver_hit_rate": hit_rec / len(rec) if len(rec) else None,
                       "non_receiver_hit_rate": hit_non / len(non) if len(non) else None,
                       "identified": rec[["freeze", "body_type", "price_bucket", "receiver_tier", "val_growth_pct", "expanded"]].to_dict(orient="records")},
            "artifacts": {"report": str(report_path)},
        }, ensure_ascii=False, indent=2))
    else:
        print("=== Downshift Receiver 识别（含未来12M扩容）===")
        print(rec[["freeze", "body_type", "fuel_type_group", "price_bucket", "receiver_tier", "val_growth_pct", "expanded"]].to_string(index=False))
        print(f"\n识别数={len(rec)} 其中扩容={hit_rec}（命中率 {hit_rec/len(rec)*100 if len(rec) else 0:.0f}%）")
        print(f"未识别带扩容率={hit_non/len(non)*100 if len(non) else 0:.0f}%（n={len(non)}）")
        print(f"report={report_path}")


if __name__ == "__main__":
    main()
