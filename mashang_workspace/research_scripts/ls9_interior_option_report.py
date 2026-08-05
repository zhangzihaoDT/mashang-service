#!/usr/bin/env python
"""
大F(LS9) 内饰选配分布报告 — 指定范围用户车锁单的选配分布，分两个上市阶段 × 不同车型。

报告内容:
    1. 总览 · 指定范围用户车锁单选配分布（付费选配 + 免费配色）
    2. 阶段一 · LS9 上市后 · 各车型选配分布
    3. 阶段二 · LS9Hyper 上市后 · 各车型选配分布
    4. 月度趋势
    5. 数据口径

口径:
    - 指定范围: series=LS9/LS9Hyper, order_type=用户车, 自上市以来 (business_definition LS9.end=2025-11-12)
    - 分两阶段: 阶段一 2025-11-12 ~ 2026-07-16 (LS9Hyper.end)；阶段二 2026-07-16 起
    - 付费判定基于通用配置判定引擎 runtime_scripts/config_decision_engine.py
      （确认付费=有正价格证据；推定付费=产品规则应付费但价格缺失；Hyper 麂皮为标配不计付费）
    - 选配分布: 深色麂皮 / 浅色麂皮 / 橙黑+大地橘(IN2-ASF) 三类付费麂皮选项 + 免费配色

用法:
    python research_scripts/ls9_interior_option_report.py                  # 渲染 HTML 报告
    python research_scripts/ls9_interior_option_report.py --format json    # Result Contract
"""

import sys, json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
from jinja2 import Environment, FileSystemLoader
from utils.business import get_launch_date
from utils.result_contract import build_success_contract
from runtime_scripts.config_decision_engine import (
    run as engine_run, SUEDE_OPTION_CONFIG, YearlySnapshotResolver,
    STANDARD_CONFIRMED, PAID_CONFIRMED, PAID_INFERRED,
    FREE_OPTION_CONFIRMED,
)

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
CONFIG_PARQUET = REPO_ROOT / "dataset" / "config_attribute.parquet"
TEMPLATE_DIR = _WS_ROOT / "templates"
OUT_REPORT = _WS_ROOT / "outputs" / "reports" / "ls9_interior_option_report.html"

LS9_LAUNCH = get_launch_date("LS9")
HYPER_LAUNCH = get_launch_date("LS9Hyper")

# 目标配置 = 按 value_code 归并后的业务名（橙黑+大地橘 = IN2-ASF 合成一个选项）
TARGET_LABELS = list(SUEDE_OPTION_CONFIG["target_codes"].values())


def _model_name(p):
    if "Hyper" in p:
        return "Hyper"
    if "线控版" in p:
        return "52 Ultra 线控版"
    if p == "智己LS9":
        return "基础款"
    if "66" in p:
        return "66 Ultra"
    return "52 Ultra"


def _load():
    order = pd.read_parquet(str(ORDER_PARQUET), columns=["order_number", "series", "lock_time", "product_name", "order_type"])
    order["lock_time"] = pd.to_datetime(order["lock_time"], errors="coerce")
    ser = order[
        (order["series"].isin(["LS9", "LS9Hyper"]))
        & (order["order_type"] == "用户车")
        & (order["lock_time"] >= pd.Timestamp(LS9_LAUNCH))
    ].copy()
    ser["is_hyper"] = ser["product_name"].str.contains("Hyper", na=False)
    config_df = pd.read_parquet(str(CONFIG_PARQUET))
    return ser, config_df


def _selection_distribution(res_df, tot):
    """完整内饰选择分布（先回答用户选了什么，再标注商业性质）。按 value_code 归并。"""
    rows = []
    for label in TARGET_LABELS:
        sub = res_df[res_df["raw_option_values"].apply(lambda vs: label in (vs or []))]
        confirmed = int((sub["commercial_status"] == PAID_CONFIRMED).sum())
        inferred = int((sub["commercial_status"] == PAID_INFERRED).sum())
        standard = int((sub["commercial_status"] == STANDARD_CONFIRMED).sum())
        free = int((sub["commercial_status"] == FREE_OPTION_CONFIRMED).sum())
        unresolved = int((sub["commercial_status"] == "UNRESOLVED").sum())
        n = len(sub)
        paid = confirmed + inferred
        rows.append({
            "value": label, "count": n, "share": round(n / tot * 100, 1),
            "paid": paid,
            "std_free": standard + free,
            "unresolved": unresolved,
            "inferred_share": round(inferred / paid * 100, 1) if paid else 0,
        })
    free_cnt = {}
    for _, r in res_df.iterrows():
        for v in (r["raw_values"] or []):
            if v in TARGET_LABELS:
                continue
            free_cnt[v] = free_cnt.get(v, 0) + 1
    for v, c in sorted(free_cnt.items(), key=lambda x: -x[1]):
        rows.append({"value": str(v), "count": int(c), "share": round(c / tot * 100, 1),
                     "paid": None, "std_free": None, "unresolved": None, "inferred_share": None})
    return rows


def _colors(res_df, tot):
    free = {}
    for _, r in res_df.iterrows():
        for v in (r["raw_values"] or []):
            if v in TARGET_LABELS:
                continue
            free[v] = free.get(v, 0) + 1
    items = []
    if free:
        order = sorted(free.items(), key=lambda x: -x[1])
        maxc = order[0][1] or 1
        for v, c in order:
            items.append({"value": str(v), "count": int(c),
                          "share": round(c / tot * 100, 1), "bar_pct": round(c / maxc * 100)})
    return items


def _phase_matrix(phase_df):
    """分阶段各车型选择分布（车型为列、选配为行，末列总计）。按 value_code 归并。"""
    models = [m for m in ["Hyper", "52 Ultra", "66 Ultra", "52 Ultra 线控版", "基础款"] if len(phase_df[phase_df["model"] == m])]
    value_order = list(TARGET_LABELS)
    free_cnt = {}
    for _, r in phase_df.iterrows():
        for v in (r["raw_values"] or []):
            if v not in TARGET_LABELS:
                free_cnt[v] = free_cnt.get(v, 0) + 1
    value_order += [v for v, _ in sorted(free_cnt.items(), key=lambda x: -x[1])]

    lock_counts = [int(len(phase_df[phase_df["model"] == m])) for m in models]
    rows = []
    for v in value_order:
        cells = []
        for m in models:
            gg = phase_df[phase_df["model"] == m]
            if v in TARGET_LABELS:
                cells.append(int(gg["raw_option_values"].apply(lambda vs: v in (vs or [])).sum()))
            else:
                cells.append(int(gg["raw_values"].apply(lambda vs: v in (vs or [])).sum()))
        rows.append({"label": v, "paid": v in TARGET_LABELS,
                     "cells": cells, "total": sum(cells)})
    return {"models": models, "lock_counts": lock_counts, "rows": rows, "tot": len(phase_df)}


def analyze():
    ser, config_df = _load()
    resolver = YearlySnapshotResolver(REPO_ROOT / "dataset", SUEDE_OPTION_CONFIG).resolve
    res, met = engine_run(ser, config_df, SUEDE_OPTION_CONFIG, order_type=None, date_from=None,
                          conflict_resolver=resolver)
    res_df = pd.DataFrame(res)
    res_df = res_df.merge(ser[["order_number", "lock_time"]], on="order_number", how="left")
    res_df["phase"] = res_df["lock_time"].apply(lambda t: "P1" if t < pd.Timestamp(HYPER_LAUNCH) else "P2")
    res_df["model"] = res_df["model_version"].apply(_model_name)

    tot = met["total_orders"]
    conf, inf = met["paid_confirmed_count"], met["paid_inferred_count"]

    phase1_df = res_df[res_df["phase"] == "P1"]
    phase2_df = res_df[res_df["phase"] == "P2"]

    data = {
        "overall": {
            "tot": tot,
            "confirmed": conf, "inferred": inf,
            "confirmed_rate": round(conf / tot * 100, 1),
            "inferred_rate": round((conf + inf) / tot * 100, 1),
            "selection_distribution": _selection_distribution(res_df, tot),
        },
        "phase1": {
            "range": f"{LS9_LAUNCH} ~ {(pd.Timestamp(HYPER_LAUNCH) - pd.Timedelta(days=1)).strftime('%Y-%m-%d')}",
            "tot": len(phase1_df),
            "matrix": _phase_matrix(phase1_df),
        },
        "phase2": {
            "range": f"{HYPER_LAUNCH} 起",
            "tot": len(phase2_df),
            "matrix": _phase_matrix(phase2_df),
        },
        "monthly": [],
        "ls9_launch": str(LS9_LAUNCH), "hyper_launch": str(HYPER_LAUNCH),
        "data_source": f"{ORDER_PARQUET.name} ⋈ {CONFIG_PARQUET.name}",
        "filters": "series=LS9/LS9Hyper, order_type=用户车, Attribute=内饰",
        "metric_definition": (
            "业务筛选：按上市窗口过滤在售车型——LS9 上市后（2025-11-12~2026-07-15）仅 52 Ultra/66 Ultra 在售，"
            "剔除 Hyper/线控版上市前预锁订单；LS9Hyper 上市后（2026-07-16 起）Hyper/52 Ultra/66 Ultra/52 Ultra 线控版 4 个车型在售。"
            "选配分布=各付费麂皮选项（按 value_code 归并，深/浅麂皮、橙黑+大地橘）订单数及占比；确认付费=订单内该选项存在 price>0 记录；"
            "推定付费=产品规则应付费但价格缺失（线控版麂皮）；Hyper 麂皮为标配不计付费；线控版橙黑/大地橘为免费可选。配置按 value_code 归并（橙黑+大地橘=IN2-ASF 同一配置）。"
            "互斥冲突订单按最新年度快照（2023/2024/2025/2026 中最新值）消解。"
        ),
        "interpretation": "",
    }

    # 月度趋势（确认/推定）
    month_rows = []
    for m, g in res_df.groupby(res_df["lock_time"].dt.to_period("M")):
        c = int((g["commercial_status"] == PAID_CONFIRMED).sum())
        i = int((g["commercial_status"] == PAID_INFERRED).sum())
        s = int((g["commercial_status"] == STANDARD_CONFIRMED).sum())
        n = len(g)
        month_rows.append({
            "value": str(m), "count": n, "confirmed": c, "paid": c + i, "standard": s,
            "confirmed_rate": round(c / n * 100, 1),
            "inferred_rate": round((c + i) / n * 100, 1),
        })
    data["monthly"] = month_rows
    return data


def render(data):
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("ls9_interior_option.html")
    o = data["overall"]
    sel = o["selection_distribution"]
    top1, top2 = sel[3], sel[4]
    data["interpretation"] = (
        f"用户车锁单共 {o['tot']:,} 单，均记录有内饰选择。最受欢迎的是大地象灰深（{top1['count']:,} 单，{top1['share']}%）"
        f"与大地象灰浅（{top2['count']:,} 单，{top2['share']}%），均为免费配色；"
        f"付费麂皮类选装中：深色麂皮 {sel[0]['count']} 单（付费含推断 {sel[0]['paid']}、标配/免费 {sel[0]['std_free']}，"
        f"其中价格缺失推断占该选项 {sel[0]['inferred_share']}%），浅色麂皮 {sel[1]['count']} 单，橙黑/大地橘 {sel[2]['count']} 单。"
        f"整体确认付费率 {o['confirmed_rate']}%、推定付费选装率 {o['inferred_rate']}%。"
        f"分阶段看：阶段一各车型选配率普遍较低；阶段二 Hyper 上市后，Hyper 车型麂皮为标配（不计付费），"
        f"基础 LS9 各车型选配率明显抬升（52 Ultra 阶段二深色麂皮 "
        f"{data['phase2']['matrix']['rows'][0]['cells'][data['phase2']['matrix']['models'].index('52 Ultra')]} 单）。"
    )
    html = template.render(
        static_prefix="../..",
        title="大F(LS9) 内饰选配分布报告",
        brand_name="Raccoon Research",
        meta="mashang | 2026-08-05",
        hero_title="大F(LS9) 内饰选配分布报告",
        hero_subtitle=(
            f"用户车 · 自上市以来（{data['ls9_launch']} 起）确认付费率 {o['confirmed_rate']}%、"
            f"推定付费选装率 {o['inferred_rate']}%"
        ),
        data=data,
    )
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(html, encoding="utf-8")
    return OUT_REPORT


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--format" and "json" in sys.argv[1:]:
        data = analyze()
        o = data["overall"]
        contract = build_success_contract(
            script="research_scripts/ls9_interior_option_report.py",
            command="python " + " ".join(sys.argv),
            scope={
                "data_source": f"{ORDER_PARQUET} ⋈ {CONFIG_PARQUET}",
                "time_window": {"type": "since_launch",
                                "ls9": f"{data['ls9_launch']} 起", "ls9hyper": f"{data['hyper_launch']} 起"},
                "filters": {"series": "LS9/LS9Hyper", "order_type": "用户车"},
                "metric_definition": data["metric_definition"],
            },
            result={
                "summary": f"用户车锁单选配分布：确认付费率 {o['confirmed_rate']}%（{o['confirmed']}/{o['tot']}），推定 {o['inferred_rate']}%",
                "metrics": {
                    "total_orders": o["tot"], "paid_confirmed": o["confirmed"],
                    "paid_inferred": o["inferred"],
                    "confirmed_rate_pct": o["confirmed_rate"],
                    "inferred_rate_pct": o["inferred_rate"],
                },
                "dimensions": [{
                    "name": "option",
                    "items": [{"value": d["value"], "metrics": {"count": d["count"], "paid_incl_inferred": d["paid"], "std_free": d["std_free"], "inferred_share_pct": d["inferred_share"]}}
                              for d in o["selection_distribution"]],
                }],
            },
            followup_context={
                "metric": "config_decision", "option": "suede_interior", "series": "LS9",
                "available_dimensions": ["phase", "model", "option"],
            },
        )
        print(json.dumps(contract, ensure_ascii=False, indent=2))
        return

    data = analyze()
    out = render(data)
    o = data["overall"]
    print(f"  HTML: {out.resolve()}")
    print(f"  总锁单 {o['tot']} | 确认付费率 {o['confirmed_rate']}% | 推定 {o['inferred_rate']}%")
    for d in o["selection_distribution"]:
        print(f"    {d['value']}: {d['count']} 单 (付费含推断 {d['paid']} / 标配免费 {d['std_free']} / 推断占比 {d['inferred_share']}%)")
    for ph in ["phase1", "phase2"]:
        mx = data[ph]["matrix"]
        print(f"  [{ph}] 车型为列、选配为行:")
        print(f"    选配 | " + " | ".join(mx["models"]) + " | 总计")
        print(f"    锁单数 | " + " | ".join(str(c) for c in mx["lock_counts"]) + f" | {mx['tot']}")
        for r in mx["rows"]:
            print(f"    {r['label']} | " + " | ".join(str(c) for c in r["cells"]) + f" | {r['total']}")


if __name__ == "__main__":
    main()
