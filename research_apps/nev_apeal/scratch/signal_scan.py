"""Signal Scan — candidate-pool expansion across unused variable axes.

One-time screening: weighted APEAL mean per group + axis gap, on axes not yet
researched in topic_tournament.md.  This is screening only; no mechanism claim.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analysis._common import labels, load, valid_groups, weighted_mean, WEIGHT

REPORT = Path(__file__).resolve().parents[1] / "reports" / "signal_board.md"
MIN_N = 50  # minimum group n to count toward the axis gap


def fixed_bins(series: pd.Series, boundaries: list[float], names: list[str]) -> pd.Series:
    return pd.Series(pd.cut(series, bins=[-np.inf, *boundaries, np.inf], labels=names), index=series.index)


def scan_categorical(df: pd.DataFrame, meta, name: str, *, drop_labels: set[str] | None = None) -> list[dict]:
    clean = valid_groups(df, meta, name)
    rows = []
    lab = labels(meta, name)
    for value in sorted(clean.dropna().unique()):
        label = lab.get(value, str(value))
        if drop_labels and label in drop_labels:
            continue
        sub = df[clean == value]
        rows.append({
            "group": name,
            "segment": label,
            "n": int(len(sub)),
            "apeal": round(float(weighted_mean(sub["APEAL_Index"], sub[WEIGHT].fillna(1.0))), 1),
        })
    return rows


def scan_binned(df: pd.DataFrame, name: str, binned: pd.Series) -> list[dict]:
    rows = []
    for interval in sorted(binned.dropna().unique(), key=lambda x: str(x)):
        sub = df[binned == interval]
        rows.append({
            "group": name,
            "segment": str(interval),
            "n": int(len(sub)),
            "apeal": round(float(weighted_mean(sub["APEAL_Index"], sub[WEIGHT].fillna(1.0))), 1),
        })
    return rows


def axis_gap(rows: list[dict]) -> float | None:
    valid = [r for r in rows if r["n"] >= MIN_N]
    if len(valid) < 2:
        return None
    return round(max(r["apeal"] for r in valid) - min(r["apeal"] for r in valid), 1)


def main() -> None:
    df, meta = load()

    categorical_axes = [
        ("Region_DP", "地理·大区", None),
        ("CITY_TIER_DP", "地理·城市层级", None),
        ("ORIGIN3_DP", "OEM 来源结构", None),
        ("PREMMAKE_DP", "OEM 豪华/大众", None),
        ("SUB_ORIGIN_DP", "OEM 原产地", None),
        ("NEV_01", "充电生活·慢充频率", None),
        ("NEV_08", "充电生活·快充频率", None),
        ("NEV_05_R1", "充电生活·家充可用性", None),
        ("NEV_07", "充电生活·车位共享", None),
        ("NEV_11A", "使用场景·通勤", None),
        ("NEV_11B", "使用场景·商务", None),
        ("NEV_11C", "使用场景·个人/家庭", None),
        ("NEV_11D", "使用场景·户外", None),
        ("NEV_11E", "使用场景·越野", None),
        ("NEV_11F", "使用场景·拖拽", None),
        ("NEV_11G", "使用场景·驾驶乐趣", None),
        ("CN_EDUCATION", "家庭·教育", None),
        ("CN_OCCUPATION", "家庭·职业", None),
        ("CN_MARITAL_STATUS", "家庭·婚况", None),
        ("AGE_BUCKETS", "人口·年龄分桶", None),
        ("GENDER", "人口·性别", None),
    ]

    binned_axes = [
        ("NEV_12", "使用强度·累积里程", fixed_bins(df["NEV_12"], [1000, 5000, 10000, 20000, 50000],
                                                    ["<1k", "1k-5k", "5k-10k", "10k-20k", "20k-50k", "50k+"])),
        ("NEV_13a", "使用强度·日均驾驶时长", fixed_bins(df["NEV_13a"], [1, 2, 4], ["<1h", "1-2h", "2-4h", "4h+"])),
        ("CN_NUMBER_HOUSEHOLD", "家庭·人口规模", fixed_bins(df["CN_NUMBER_HOUSEHOLD"], [1, 2, 3], ["1", "2", "3", "4+"])),
        ("YPV_05", "家庭·车辆数", fixed_bins(df["YPV_05"], [1, 2], ["1", "2", "3+"])),
    ]

    board = []
    for name, label, drop in categorical_axes:
        rows = scan_categorical(df, meta, name, drop_labels=drop)
        board.append({"axis": name, "label": label, "gap": axis_gap(rows), "rows": rows})
    for name, label, binned in binned_axes:
        rows = scan_binned(df, name, binned)
        board.append({"axis": name, "label": label, "gap": axis_gap(rows), "rows": rows})

    board.sort(key=lambda b: (b["gap"] is None, -b["gap"] if b["gap"] else -1))

    lines = [
        "# Signal Board — 候选池扩展扫描",
        "",
        f"**日期**：2026-08-19 ｜ 数据 `data/source.sav`(9,937×370) ｜ 权重 `APEAL_WT` ｜ 指标 `APEAL_Index`",
        "",
        "**性质**：一次性筛选（screening）。横截面加权均值差（gap = 加权 APEAL max − min，组 n≥50）。",
        "**不是机制结论**：未做 confounder 控制；被选中轴仍需走完整验证（PRICE/BRAND/能源 + item 下钻）。",
        "",
        "| 轴 | 分组变量 | gap | 最高分组 | 最低分组 | 最高→最低 | 覆盖n |",
        "|---|---|---:|---|---|---|---:|",
    ]
    for b in board:
        if b["gap"] is None:
            lines.append(f"| {b['label']} | {b['axis']} | — | — | — | — | 组数不足 |")
            continue
        rows = [r for r in b["rows"] if r["n"] >= MIN_N]
        hi = max(rows, key=lambda r: r["apeal"])
        lo = min(rows, key=lambda r: r["apeal"])
        total_n = sum(r["n"] for r in b["rows"])
        lines.append(
            f"| {b['label']} | {b['axis']} | {b['gap']} | {hi['segment']} {hi['apeal']} | {lo['segment']} {lo['apeal']} | {hi['segment']}→{lo['segment']} | {total_n} |"
        )

    lines += ["", "## 各轴明细", ""]
    for b in board:
        lines.append(f"### {b['label']}（{b['axis']}）")
        lines.append("")
        lines.append("| 分组 | n | 加权APEAL |")
        lines.append("|---|---:|---:|")
        for r in b["rows"]:
            lines.append(f"| {r['segment']} | {r['n']} | {r['apeal']} |")
        lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"signal board written -> {REPORT}")
    print("=" * 88)
    print(f"{'轴':<22}{'gap':>6}   最高 → 最低")
    for b in board:
        if b["gap"] is None:
            continue
        rows = [r for r in b["rows"] if r["n"] >= MIN_N]
        hi = max(rows, key=lambda r: r["apeal"])
        lo = min(rows, key=lambda r: r["apeal"])
        print(f"{b['label']:<22}{b['gap']:>6.1f}   {hi['segment']}({hi['apeal']}) → {lo['segment']}({lo['apeal']})")


if __name__ == "__main__":
    main()
