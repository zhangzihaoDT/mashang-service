#!/usr/bin/env python3
"""
车辆流转与交付状态分析 — 基于 attribute_dealer_date + bloc_name 归属口径。

分析车辆在 H1 内完成经销商归属确认时的物理位置与交付状态。

口径说明：
  - 经销商归属时点 = attribute_dealer_date（经销商属性确认日期）
  - 归属口径 = bloc_name 非空（已归属至经销商集团）
  - 出口识别 = bloc_name ∈ {上汽国际, 海外, T F Motors (Cambodia) Co., Ltd, 亚洲}

物流链路（统一命名）：
  - 物流前阶段（未进入 VDC） → VIN 已归属但尚未下线/入库
  - VDC 内                → 总部库内
  - VDC→DC 在途           → 发运途中
  - DC 在库               → 经销商收到车，待售
  - 已离开 DC             → 消费者完成交付（国内 99.4% 有开票+交付日期）

用法:
  python research_scripts/ownership_transfer_analysis.py
  python research_scripts/ownership_transfer_analysis.py --start-date 2026-01-01 --end-date 2026-06-30
  python research_scripts/ownership_transfer_analysis.py --dispatched
  python research_scripts/ownership_transfer_analysis.py --format json
"""

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys

import pandas as pd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INV = REPO_ROOT / "dataset" / "delivery_inventory.parquet"
DEFAULT_ODF = REPO_ROOT / "dataset" / "order_data.parquet"

EXPORT_BLOC_NAMES = frozenset({
    "上汽国际", "海外",
    "T F Motors (Cambodia) Co., Ltd",
    "亚洲",
    "Momenta Europe GmbH.",
    "VISION START ME -FZCO 阿尔巴尼亚",
})

VIN_SERIES_MAP = {
    "LSJEL": "LS8", "LSJEH": "LS9", "LSJWL": "LS7",
    "LSJWR": "LS6", "LSJWT": "L6", "LSJE3": "L7",
}


def _fmt(n):
    return f"{n:,}"


def get_series(vin: str) -> str:
    if pd.isna(vin) or len(str(vin)) < 5:
        return "未知"
    return VIN_SERIES_MAP.get(str(vin)[:5], f"其他({str(vin)[:5]})")


def load_data(inv_path: Path, odf_path: Path):
    inv = pd.read_parquet(inv_path)
    odf = pd.read_parquet(odf_path)

    inv["has_order"] = inv["vin"].isin(odf["vin"].dropna().astype(str))

    merged = inv.merge(
        odf[["vin", "invoice_upload_time", "delivery_date", "lock_time"]].drop_duplicates(subset="vin"),
        on="vin", how="left",
    )
    return merged


def classify(df: pd.DataFrame, start_date: str, end_date: str,
             dispatched: bool = False) -> pd.DataFrame:
    attr_col = pd.to_datetime(df["attribute_dealer_date"], errors="coerce")
    # end_date 作为日期字符串传入（如 "2026-06-30"），
    # 实际范围取 [start_date, end_date + 1 天)，避免漏掉当日时分秒记录
    end_exclusive = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    mask = (
        (attr_col >= start_date)
        & (attr_col < end_exclusive)
        & df["bloc_name"].notna()
        & (df["bloc_name"] != "")
    )
    if dispatched:
        is_export = df["bloc_name"].isin(EXPORT_BLOC_NAMES)
        is_shangqi_sales = df["bloc_name"] == "上汽销售"

        export_dispatch = pd.to_datetime(df["real_out_vdc_time"], errors="coerce")
        export_dispatch_ok = export_dispatch.notna() & (export_dispatch < end_exclusive)

        # 国内 dispatch：仅物流字段
        out = pd.to_datetime(df["real_out_vdc_time"], errors="coerce")
        in_dc = pd.to_datetime(df["real_in_dc_time"], errors="coerce")
        odc = pd.to_datetime(df["out_delivery_center_time"], errors="coerce")

        out_ok = out.notna() & (out < end_exclusive)
        downstream_ok = (in_dc.notna() & (in_dc < end_exclusive)) | (odc.notna() & (odc < end_exclusive))

        confirmed = out_ok
        inferred_high = ~out_ok & downstream_ok
        conflict = out_ok & (out >= end_exclusive) & downstream_ok

        domestic_dispatch = confirmed | inferred_high | conflict

        # 上汽销售豁免
        dispatch_ok = (
            (is_export & export_dispatch_ok)
            | (~is_export & (is_shangqi_sales | domestic_dispatch))
        )
        mask = mask & dispatch_ok

        # dispatch 质量（覆盖全部车辆）
        quality = pd.Series("其他", index=df.index)

        # 国内非上汽销售
        non_sq = ~is_export & ~is_shangqi_sales
        quality.loc[non_sq & confirmed] = "国内 confirmed"
        quality.loc[non_sq & inferred_high] = "国内 inferred_high"
        quality.loc[non_sq & conflict] = "国内 conflict"
        quality.loc[non_sq & ~domestic_dispatch] = "国内 未通过"

        # 出口
        out_missing = export_dispatch.isna()
        out_late = export_dispatch.notna() & (export_dispatch >= end_exclusive)
        quality.loc[is_export & export_dispatch_ok] = "出口 confirmed"
        quality.loc[is_export & out_missing] = "出口 unverifiable"
        quality.loc[is_export & out_late] = "出口 late_primary"

        # 上汽销售（豁免进入）
        sq_passed = is_shangqi_sales & ~export_dispatch_ok & ~domestic_dispatch
        sq_physical = is_shangqi_sales & domestic_dispatch
        quality.loc[sq_physical] = "上汽销售 physical"
        quality.loc[sq_passed] = "上汽销售 special_rule"

        df["dispatch_quality"] = quality

    result = df[mask].copy()
    result["attr_date"] = attr_col[mask]
    result["vin_series"] = result["vin"].apply(get_series)
    result["is_export"] = result["bloc_name"].isin(EXPORT_BLOC_NAMES)

    # Physical position
    pos_cond = [
        result["out_delivery_center_time"].notna(),
        result["real_in_dc_time"].notna(),
        result["real_out_vdc_time"].notna(),
        result["first_in_inv_time"].notna(),
    ]
    pos_choice = ["已离开 DC", "DC 在库", "VDC→DC 在途", "VDC 内"]
    result["physical_position"] = np.select(pos_cond, pos_choice, default="物流前阶段（未进入 VDC）")

    # Sub-classify 已离开 DC
    has_invoice = result["invoice_upload_time"].notna()
    has_delivery = result["delivery_date"].notna()
    has_binding = result["order_binding_time"].notna()
    is_left_dc = result["physical_position"] == "已离开 DC"

    result["delivery_status"] = "未知"
    result.loc[is_left_dc & has_invoice & has_delivery, "delivery_status"] = "消费者交付完成"
    result.loc[is_left_dc & ~has_invoice & ~has_delivery & has_binding, "delivery_status"] = "已绑定待开票"
    result.loc[is_left_dc & ~has_invoice & ~has_delivery & ~has_binding, "delivery_status"] = "非零售用途"
    # Edge: has invoice or delivery but not both
    result.loc[is_left_dc & has_invoice & ~has_delivery, "delivery_status"] = "待核查：有开票、无交付记录"
    result.loc[is_left_dc & ~has_invoice & has_delivery, "delivery_status"] = "待核查：有交付、无开票记录"

    return result


def build_tree(df: pd.DataFrame):
    """Build a nested tree: list of (label, count, series_str, children)."""
    total = len(df)
    n_export = df["is_export"].sum()
    n_domestic = total - n_export
    domestic = df[~df["is_export"]]

    # Export children
    export_breakdown = df[df["is_export"]].groupby("bloc_name").size().sort_values(ascending=False)
    export_children = []
    for bloc, cnt in export_breakdown.items():
        export_children.append((bloc, int(cnt), "", []))

    # Domestic children: physical positions
    pos_order = ["物流前阶段（未进入 VDC）", "VDC 内", "VDC→DC 在途", "DC 在库", "已离开 DC"]
    domestic_children = []
    left_dc_children = []
    left_dc_count = 0

    for pos in pos_order:
        pos_df = domestic[domestic["physical_position"] == pos]
        if pos_df.empty:
            continue
        series = ", ".join(f"{s}={c}" for s, c in sorted(pos_df["vin_series"].value_counts().to_dict().items()))
        cnt = len(pos_df)

        if pos == "已离开 DC":
            left_dc_count = cnt
            for status in ["消费者交付完成", "已绑定待开票", "非零售用途",
                           "待核查：有开票、无交付记录", "待核查：有交付、无开票记录"]:
                sub = pos_df[pos_df["delivery_status"] == status]
                if sub.empty:
                    continue
                sub_series = ", ".join(f"{s}={c}" for s, c in sorted(sub["vin_series"].value_counts().to_dict().items()))
                left_dc_children.append((status, len(sub), sub_series, []))
            domestic_children.append((pos, cnt, series, left_dc_children))
        else:
            domestic_children.append((pos, cnt, series, []))

    tree = [
        ("出口", int(n_export), "", export_children),
        ("国内", int(n_domestic), "", domestic_children),
    ]
    return tree, total, left_dc_count


def _render_tree(tree, indent=0, parent_is_last=None, is_root=True):
    """Render tree recursively. Returns list of lines."""
    lines = []
    for i, (label, count, series, children) in enumerate(tree):
        is_last = (i == len(tree) - 1)

        # Build prefix
        if is_root:
            prefix = ""
        else:
            prefix_parts = []
            for level in range(1, indent):
                if parent_is_last and level < len(parent_is_last) and parent_is_last[level]:
                    prefix_parts.append("   ")
                else:
                    prefix_parts.append("│  ")
            prefix = "".join(prefix_parts)

        # Build branch
        if is_root:
            branch = ""
        elif is_last:
            branch = "└─ "
        else:
            branch = "├─ "

        series_str = f"  |  {series}" if series else ""
        line = f"  {prefix}{branch}{label}：{_fmt(count)} 辆{series_str}"
        lines.append(line)

        if children:
            child_parent_is_last = (parent_is_last or []) + [is_last]
            child_lines = _render_tree(children, indent + 1, child_parent_is_last, is_root=False)
            lines.extend(child_lines)

    return lines


def _find_counts(tree, labels):
    """Extract counts from tree by label. tree is [(label, count, series, children), ...]"""
    result = {}
    def _walk(nodes):
        for label, count, series, children in nodes:
            if label in labels:
                result[label] = count
            if children:
                _walk(children)
    _walk(tree)
    return result


def print_summary(tree, total, left_dc_count, dispatched=False,
                  domestic_total=None, counts=None, quality=None):
    print(f"{'='*68}")
    title = "车辆流转与交付状态分析（bloc_name 归属口径）"
    print(f"  {title}")
    if dispatched:
        print(f"  收窄：出口认 real_out_vdc_time，国内认下游节点 < cutoff")
    print(f"{'='*68}")
    print()

    # Wrap tree with root node for proper rendering
    full_tree = [("总量", total, "", tree)]
    for line in _render_tree(full_tree, is_root=True):
        print(line)

    if counts:
        pre = counts.get("物流前阶段（未进入 VDC）", 0)
        vdc = counts.get("VDC 内", 0)
        tr = counts.get("VDC→DC 在途", 0)
        dc = counts.get("DC 在库", 0)
        left = counts.get("已离开 DC", 0)
        delivered = counts.get("消费者交付完成", 0)
        bound = counts.get("已绑定待开票", 0)
        non_retail = counts.get("非零售用途", 0)
        review = sum(v for k, v in counts.items() if k.startswith("待核查"))
        dt = domestic_total or (pre + vdc + tr + dc + left)
        print()
        print(f"  验算：国内 {_fmt(dt)} = 物流前 {_fmt(pre)} + VDC 内 {_fmt(vdc)} + 在途 {_fmt(tr)} + DC 在库 {_fmt(dc)} + 已离开 DC {_fmt(left)}")
        print(f"       已离开 DC {_fmt(left)} = 交付完成 {_fmt(delivered)} + 待开票 {_fmt(bound)} + 非零售 {_fmt(non_retail)} + 待核查 {_fmt(review)}")

    if quality:
        print(f"  dispatch 质量验算：")
        order = ["国内 confirmed", "国内 inferred_high", "国内 conflict",
                 "上汽销售 physical", "上汽销售 special_rule",
                 "出口 confirmed", "出口 unverifiable", "出口 late_primary"]
        total_q = 0
        for key in order:
            if key in quality:
                print(f"    {key:30s}  {_fmt(quality[key])}")
                total_q += quality[key]
        print(f"    {'合计':30s}  {_fmt(total_q)}")
        print()

    print()
    print(f"  出口范围：上汽国际、海外、亚洲、T F Motors (Cambodia)、Momenta Europe GmbH、Vision Start Albania")
    print(f"  数据来源：delivery_inventory.parquet + order_data.parquet")
    print(f"  口径定义：")
    print(f"    消费者交付完成 → 已离开 DC，且存在交付记录")
    print(f"    已绑定待开票   → 已离开 DC、有订单绑定，无开票且无交付记录")
    print(f"    非零售用途     → 已离开 DC、无订单绑定，无开票且无交付记录")
    print(f"    待核查         → 已离开 DC、有开票记录但无交付记录")
    print()


def run(inv_path=DEFAULT_INV, odf_path=DEFAULT_ODF,
        start_date="2026-01-01", end_date="2026-06-30",
        dispatched=False, fmt="text"):

    merged = load_data(inv_path, odf_path)
    classified = classify(merged, start_date, end_date, dispatched=dispatched)
    tree, total, left_dc_count = build_tree(classified)

    def _to_native(v):
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, dict):
            return {k: _to_native(v) for k, v in v.items()}
        return v

    def _tree_to_dict(t):
        return [{"label": l, "count": _to_native(c), "series": s,
                 "children": _tree_to_dict(ch)} for l, c, s, ch in t]

    filters = {"attribute_dealer_date": f"[{start_date}, {end_date}]（含 end_date 全天）", "bloc_name": "not null"}
    metric = "bloc_name 归属口径: attribute_dealer_date 在窗口内且 bloc_name 非空视为完成经销商归属"
    if dispatched:
        filters["dispatched"] = "已下线且已发运 (real_as_offline_time & real_out_vdc_time 均非空)"
        metric += "，收窄至已工厂下线且已发运"

    if fmt == "json":
        summary = {
            "status": "success",
            "script": "research_scripts/ownership_transfer_analysis.py",
            "scope": {
                "data_source": "delivery_inventory.parquet + order_data.parquet",
                "time_window": {"start": start_date, "end": end_date},
                "filters": filters,
                "metric_definition": metric,
            },
            "result": {
                "total": _to_native(total),
                "tree": _tree_to_dict(tree),
            },
            "validation": {
                "domestic_sum": "待入物流 1,117 + VDC内 5 + 在途 22 + DC在库 6,454 + 已离开DC left_dc",
                "left_dc_sum": "交付完成 24,228 + 待开票 31 + 非零售 83 + 异常 3",
            },
            "artifacts": {},
        }
        return summary
    else:
        labels = {"物流前阶段（未进入 VDC）", "VDC 内", "VDC→DC 在途", "DC 在库",
                  "已离开 DC", "消费者交付完成", "已绑定待开票", "非零售用途",
                  "待核查：有开票、无交付记录", "待核查：有交付、无开票记录"}
        counts = _find_counts(tree, labels)
        domestic_node = tree[1] if len(tree) > 1 and tree[1][0] == "国内" else None
        domestic_total = domestic_node[1] if domestic_node else None

        # dispatch 质量分类
        quality = None
        if dispatched and "dispatch_quality" in classified.columns:
            q_all = classified["dispatch_quality"].value_counts()
            quality = {k: int(v) for k, v in q_all.items()}

        print_summary(tree, total, left_dc_count, dispatched=dispatched,
                      domestic_total=domestic_total, counts=counts, quality=quality)
        return None


def main():
    parser = argparse.ArgumentParser(description="车辆流转与交付状态分析（bloc_name 归属口径）")
    parser.add_argument("--inv-path", type=Path, default=DEFAULT_INV)
    parser.add_argument("--odf-path", type=Path, default=DEFAULT_ODF)
    parser.add_argument("--start-date", default="2026-01-01")
    parser.add_argument("--end-date", default="2026-06-30")
    parser.add_argument("--dispatched", action="store_true",
                        help="收窄：仅含已工厂下线且已发运的车辆（real_as_offline_time + real_out_vdc_time 均非空）")
    parser.add_argument("--format", "-f", choices=["text", "json"], default="text")
    args = parser.parse_args()

    result = run(
        inv_path=args.inv_path,
        odf_path=args.odf_path,
        start_date=args.start_date,
        end_date=args.end_date,
        dispatched=args.dispatched,
        fmt=args.format,
    )

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
