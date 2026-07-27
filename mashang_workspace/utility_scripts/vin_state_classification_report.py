#!/usr/bin/env python
"""
VIN 生命周期状态分类报告 — 将 delivery_inventory 与 order_data 串联，
按三层体系输出：physical_stage / order_relation / vin_lifecycle_status。

用法:
    python utility_scripts/vin_state_classification_report.py
    python utility_scripts/vin_state_classification_report.py --format json
    python utility_scripts/vin_state_classification_report.py --output outputs/reports/
"""

import sys
import argparse
import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
WS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(WS_ROOT))

DELIVERY_INVENTORY = Path("/Users/zihao_/Documents/coding/dataset/original/delivery_inventory.parquet")
ORDER_DATA = REPO_ROOT / "dataset" / "order_data.parquet"
DEFAULT_OUTPUT = WS_ROOT / "outputs" / "reports"

STATE_ORDER = [
    "已锁单待排产",
    "已排产待下线_未匹配", "已排产待下线_已锁单",
    "已下线待质检_未匹配", "已下线待质检_已锁单",
    "已质检待入库_未匹配", "已质检待入库_已锁单",
    "工厂库存_未匹配", "工厂库存_已锁单待发运",
    "在途_未匹配", "在途_已锁单",
    "交付中心库存_未匹配", "交付中心库存_已锁单待交付",
    "已离开交付中心_未匹配", "已离开交付中心_已锁单",
    "已交付",
]

SPECIAL_STATES = ["订单已关联但锁单时间缺失", "退款待重新匹配", "数据异常或状态未知"]

SERIES_MAP = {
    "LSJEL": "LS8", "LSJEH": "LS9", "LSJWL": "LS7",
    "LSJWR": "LS6", "LSJWT": "L6", "LSJE3": "L7",
}


def physical_stage(row):
    """仅依赖事件时间字段，返回车辆物理位置。"""
    h = lambda x: pd.notna(x)
    if h(row["out_delivery_center_time"]):
        return "已离开交付中心"
    if h(row["real_in_dc_time"]):
        return "交付中心库存"
    if h(row["actual_waybill_out_time"]):
        return "在途"
    if h(row["first_in_inv_time"]):
        return "工厂库存"
    if h(row["real_qc_offline_time"]):
        return "已质检待入库"
    if h(row["real_as_offline_time"]):
        return "已下线待质检"
    if h(row["schedule_effective_time"]):
        return "已排产待下线"
    return "无进度"


def order_relation(row):
    """仅依赖订单关联状态。"""
    if pd.notna(row["actual_refund_time"]):
        return "退款"
    if pd.notna(row["lock_time"]):
        return "已锁单"
    if row.get("vin_linked", False):
        return "订单已关联但锁单时间缺失"
    return "未关联"


def vin_lifecycle_status(row):
    """合并物理位置 + 订单关系，输出 15+3 状态。"""
    lt = row["lock_time"]
    refund = row["actual_refund_time"]
    delivery = row["delivery_date"]
    out_dc = row["out_delivery_center_time"]

    if pd.notna(refund):
        return "退款待重新匹配"

    h = lambda x: pd.notna(x)

    # 终端状态
    if h(out_dc) and h(delivery):
        return "已交付"
    if h(out_dc):
        return "已离开交付中心_未匹配" if not h(lt) else "已离开交付中心_已锁单"

    # 物理位置
    if h(row["real_in_dc_time"]):
        pos = "交付中心库存"
    elif h(row["actual_waybill_out_time"]):
        pos = "在途"
    elif h(row["first_in_inv_time"]):
        pos = "工厂库存"
    elif h(row["real_qc_offline_time"]):
        pos = "已质检待入库"
    elif h(row["real_as_offline_time"]):
        pos = "已下线待质检"
    elif h(row["schedule_effective_time"]):
        pos = "已排产待下线"
    elif h(lt):
        return "已锁单待排产"
    else:
        return "数据异常或状态未知"

    if h(lt):
        if pos == "工厂库存":
            return "工厂库存_已锁单待发运"
        elif pos == "交付中心库存":
            return "交付中心库存_已锁单待交付"
        else:
            return "{0}_已锁单".format(pos)
    else:
        return "{0}_未匹配".format(pos)


def build_report(df) -> dict:
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_vin": len(df),
    }
    # 物理位置分布
    stage_dist = df["stage"].value_counts()
    report["physical_stage"] = {}
    for k, v in stage_dist.items():
        report["physical_stage"][k] = {"count": int(v), "pct": round(v / len(df) * 100, 1)}

    # 订单关系分布
    rel_dist = df["relation"].value_counts()
    report["order_relation"] = {}
    for k, v in rel_dist.items():
        report["order_relation"][k] = {"count": int(v), "pct": round(v / len(df) * 100, 1)}

    # 生命周期状态分布
    ls_dist = df["lifecycle"].value_counts()
    report["lifecycle_states"] = {}
    for s in STATE_ORDER + SPECIAL_STATES:
        v = int(ls_dist.get(s, 0))
        if v > 0:
            report["lifecycle_states"][s] = {"count": v, "pct": round(v / len(df) * 100, 1)}

    # 车系 × 生命周期交叉
    report["series_cross"] = {}
    for s_name in ["L6", "L7", "LS6", "LS7", "LS8", "LS9", "其他"]:
        sub = df[df["series"] == s_name]
        if len(sub) == 0:
            continue
        ss = {}
        for s in STATE_ORDER + SPECIAL_STATES:
            v = int((sub["lifecycle"] == s).sum())
            if v > 0:
                ss[s] = v
        report["series_cross"][s_name] = {"total": len(sub), "states": ss}

    # 物理位置 × 订单关系 交叉（库存计算依据）
    cross = df.groupby(["stage", "relation"]).size().unstack(fill_value=0)
    report["stage_relation_cross"] = {}
    for stage_name in cross.index:
        report["stage_relation_cross"][stage_name] = {
            str(k): int(v) for k, v in cross.loc[stage_name].items()
        }

    # 按生产年份
    df["prod_year"] = df["real_as_offline_time"].dt.year
    report["by_production_year"] = {}
    for s in STATE_ORDER + SPECIAL_STATES:
        v = ls_dist.get(s, 0)
        if v < 100:
            continue
        by_year = df[df["lifecycle"] == s].groupby("prod_year").size()
        report["by_production_year"][s] = {
            str(int(y)): int(c) for y, c in sorted(by_year.items())
        }

    return report


def format_markdown(report: dict, df_len: int) -> str:
    lines = []
    lines.append("# VIN 生命周期状态分类报告")
    lines.append("")
    lines.append("**生成时间**: {0}".format(report["generated_at"]))
    lines.append("**数据源**: `delivery_inventory.parquet` + `order_data.parquet` (vin 左连接)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. 物理位置分布（库存计算依据）")
    lines.append("")
    lines.append("仅依赖车辆事件时间字段，不受订单状态影响。")
    lines.append("")
    lines.append("| 物理位置 | VIN 数 | 占比 |")
    lines.append("|----------|-------:|----:|")
    pos_order = ["已排产待下线", "已下线待质检", "已质检待入库", "工厂库存", "在途", "交付中心库存", "已离开交付中心", "无进度"]
    for p in pos_order:
        info = report["physical_stage"].get(p)
        if info:
            lines.append("| {0} | {1:,} | {2:.1f}% |".format(p, info["count"], info["pct"]))
    lines.append("")
    lines.append("## 2. 订单关系分布")
    lines.append("")
    lines.append("| 订单关系 | VIN 数 | 占比 |")
    lines.append("|----------|-------:|----:|")
    for r in ["已锁单", "订单已关联但锁单时间缺失", "未关联", "退款"]:
        info = report["order_relation"].get(r)
        if info:
            lines.append("| {0} | {1:,} | {2:.1f}% |".format(r, info["count"], info["pct"]))
    lines.append("")
    lines.append("## 3. 物理位置 × 订单关系 交叉")
    lines.append("")
    lines.append("库存统计应基于此表：锁定物理位置后，查看订单匹配状态。")
    lines.append("")
    relations = ["已锁单", "订单已关联但锁单时间缺失", "未关联", "退款"]
    visible_rels = [r for r in relations if any(
        r in sc for sc in report["stage_relation_cross"].values())]
    lines.append("| 物理位置 | " + " | ".join(visible_rels) + " | 合计 |")
    lines.append("|:---------|" + "|".join("---:" for _ in visible_rels) + "|----:|")
    for p in pos_order:
        sc = report["stage_relation_cross"].get(p)
        if not sc:
            continue
        vals = [str(sc.get(r, 0)) for r in visible_rels]
        total = sum(sc.get(r, 0) for r in visible_rels)
        lines.append("| {0} | {1} | {2:,} |".format(p, " | ".join(vals), total))
    lines.append("")
    lines.append("## 4. 生命周期状态（16 类常规 + 3 类异常）")
    lines.append("")
    lines.append("| 状态 | VIN 数 | 占比 |")
    lines.append("|------|-------:|----:|")
    for s in STATE_ORDER:
        info = report["lifecycle_states"].get(s)
        if info:
            lines.append("| {0} | {1:,} | {2:.1f}% |".format(s, info["count"], info["pct"]))
    lines.append("")
    lines.append("### 异常/特殊状态")
    lines.append("")
    for s in SPECIAL_STATES:
        info = report["lifecycle_states"].get(s)
        if info:
            lines.append("- **{0}**: {1:,} ({2:.1f}%)".format(s, info["count"], info["pct"]))
        else:
            lines.append("- **{0}**: 0".format(s))
    lines.append("")
    lines.append("## 5. 车系 × 生命周期交叉")
    lines.append("")
    all_series = ["L6", "L7", "LS6", "LS7", "LS8", "LS9", "其他"]
    visible = [s for s in STATE_ORDER + SPECIAL_STATES if s in report["lifecycle_states"]]
    lines.append("| 车系 | " + " | ".join(s[:12] for s in visible) + " | 合计 |")
    lines.append("|:-----|" + "|".join("---:" for _ in visible) + "|----:|")
    for s_name in all_series:
        sc = report["series_cross"].get(s_name)
        if not sc:
            continue
        vals = [str(sc["states"].get(s, 0)) for s in visible]
        lines.append("| {0} | {1} | {2:,} |".format(s_name, " | ".join(vals), sc["total"]))
    lines.append("")
    lines.append("## 6. 按生产年份分布（状态数 > 100）")
    lines.append("")
    for s, years in report["by_production_year"].items():
        parts = ["{0}: {1}".format(y, c) for y, c in years.items()]
        lines.append("- **{0}**: {1}".format(s, " → ".join(parts)))
    lines.append("")
    lines.append("---")
    lines.append("")
    active = sum(1 for s in STATE_ORDER + SPECIAL_STATES if s in report["lifecycle_states"])
    lines.append("*共计 {0:,} VIN，{1} 个非空生命周期状态。*".format(df_len, active))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="VIN 生命周期状态分类报告")
    parser.add_argument("--format", choices=["md", "json"], default="md", help="输出格式")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="输出目录")
    args = parser.parse_args(argv)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("📖 读取 delivery_inventory ...")
    inv = pd.read_parquet(DELIVERY_INVENTORY)
    print("📖 读取 order_data ...")
    odf = pd.read_parquet(ORDER_DATA)
    odf_vin = odf[["vin", "lock_time", "delivery_date", "actual_refund_time"]].drop_duplicates(subset="vin")

    print("🔗 合并 ...")
    df = inv.merge(odf_vin, on="vin", how="left")

    print("🏷️  三层分类 ...")
    df["vin_linked"] = df["vin"].isin(odf_vin["vin"])
    df["stage"] = df.apply(physical_stage, axis=1)
    df["relation"] = df.apply(order_relation, axis=1)
    df["lifecycle"] = df.apply(vin_lifecycle_status, axis=1)
    df["series"] = df["vin"].str[:5].map(SERIES_MAP).fillna("其他")

    report = build_report(df)

    if args.format == "json":
        out_path = out_dir / "vin_state_classification_report.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    else:
        md = format_markdown(report, len(df))
        out_path = out_dir / "vin_state_classification_report.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)

    print("✅ 报告已保存: {0}".format(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
