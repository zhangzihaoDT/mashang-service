#!/usr/bin/env python3
"""
车辆 Dispatch 分析 — 国内=订单绑定, 出口=出厂发运。

口径：
  国内 Dispatch = order_binding_time 在窗口内
  出口 Dispatch = actual_waybill_out_time 在窗口内（出厂发运）
  业务 Dispatch = 国内 Dispatch ∪ 出口 Dispatch
  同时输出出口离港出关量（out_dc）和出厂→离港中位周期
  剔除：试驾车（order_type = '试驾车'）
  可选排除：--exclude-test-drive 剔除试驾车

用法:
  python research_scripts/ownership_transfer_analysis.py
  python research_scripts/ownership_transfer_analysis.py --start-date 2026-01-01 --end-date 2026-06-30
  python research_scripts/ownership_transfer_analysis.py --exclude-test-drive
  python research_scripts/ownership_transfer_analysis.py --format json
"""

import argparse
import json
from pathlib import Path
import sys

import pandas as pd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

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

ALL_SERIES = ["LS6", "LS9", "L6", "LS8", "LS7", "L7"]


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
        odf[["vin", "invoice_upload_time", "delivery_date", "lock_time", "order_type"]].drop_duplicates(subset="vin"),
        on="vin", how="left",
    )
    return merged


def classify_dispatch(df: pd.DataFrame, start_date: str, end_date: str,
                       exclude_test_drive: bool = True) -> dict:
    end_excl = pd.Timestamp(end_date)
    out_dc = pd.to_datetime(df["out_delivery_center_time"], errors="coerce")
    waybill = pd.to_datetime(df["actual_waybill_out_time"], errors="coerce")
    binding = pd.to_datetime(df["order_binding_time"], errors="coerce")
    in_dc = pd.to_datetime(df["real_in_dc_time"], errors="coerce")
    attr = pd.to_datetime(df["attribute_dealer_date"], errors="coerce")
    invoice = pd.to_datetime(df["invoice_upload_time"], errors="coerce")
    delivery = pd.to_datetime(df["delivery_date"], errors="coerce")

    def in_h1(ts):
        return (ts >= start_date) & (ts < end_excl)

    is_export = df["bloc_name"].isin(EXPORT_BLOC_NAMES)

    # 国内 Dispatch
    dom_dispatch = ~is_export & in_h1(invoice)

    # 出口 Dispatch
    exp_dispatch = is_export & in_h1(waybill)

    business = dom_dispatch | exp_dispatch

    # 剔除试驾车
    if exclude_test_drive and "order_type" in df.columns:
        not_test = df["order_type"] != "试驾车"
        business = business & not_test
        dom_dispatch = dom_dispatch & not_test
        exp_dispatch = exp_dispatch & not_test

    result = df[business].copy()
    result["is_export"] = is_export[business]
    result["dispatch_track"] = np.where(result["is_export"], "出口 Dispatch", "国内 Dispatch")
    result["dispatch_event"] = "其他"
    result.loc[~result["is_export"], "dispatch_event"] = "开票"
    result.loc[result["is_export"], "dispatch_event"] = "出厂发运"

    result["vin_series"] = result["vin"].apply(get_series)

    invoice_ts = pd.to_datetime(result["invoice_upload_time"], errors="coerce")
    waybill_ts = pd.to_datetime(result["actual_waybill_out_time"], errors="coerce")
    result["event_time"] = np.where(~result["is_export"], invoice_ts, waybill_ts)
    result["event_month"] = pd.to_datetime(result["event_time"]).dt.month

    as_of = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    for col in ["first_in_inv_time", "real_out_vdc_time", "real_in_dc_time", "out_delivery_center_time"]:
        result[col + "_ts"] = pd.to_datetime(result[col], errors="coerce")
    pos_cond = [
        result["out_delivery_center_time_ts"].notna() & (result["out_delivery_center_time_ts"] <= as_of),
        result["real_in_dc_time_ts"].notna() & (result["real_in_dc_time_ts"] <= as_of),
        result["real_out_vdc_time_ts"].notna() & (result["real_out_vdc_time_ts"] <= as_of),
        result["first_in_inv_time_ts"].notna() & (result["first_in_inv_time_ts"] <= as_of),
    ]
    pos_choice = ["已离开 DC", "DC 在库", "VDC→DC 在途", "VDC 内"]
    result["physical_position"] = np.select(pos_cond, pos_choice, default="物流前阶段（未进入 VDC）")

    # 出口仅归属未离港
    exp_attr_only = is_export & in_h1(attr) & ~exp_dispatch
    if exclude_test_drive:
        exp_attr_only = exp_attr_only & not_test

    # 出口物流跟踪统计
    if exclude_test_drive and "order_type" in df.columns:
        nt_full = df["order_type"] != "试驾车"
    else:
        nt_full = True
    exp_base = is_export & nt_full
    exp_wb_h1 = exp_base & in_h1(waybill)
    exp_out_h1 = exp_base & in_h1(out_dc)
    exp_both_h1 = exp_wb_h1 & exp_out_h1
    exp_wb_only_h1 = exp_wb_h1 & ~exp_out_h1
    exp_out_only_h1 = exp_out_h1 & ~exp_wb_h1
    median_gap = None
    if exp_both_h1.sum() > 0:
        gap = (out_dc[exp_both_h1] - waybill[exp_both_h1]).dt.total_seconds() / 86400
        median_gap = int(gap.median())

    # 出口仅归属未离港（attr only）
    exp_attr_only = is_export & in_h1(attr) & ~exp_dispatch
    if exclude_test_drive:
        exp_attr_only = exp_attr_only & not_test

    # 双口径补充：real_out_vdc_time（不剔除试驾车）
    out_vdc_h1 = (pd.to_datetime(df["real_out_vdc_time"], errors="coerce") >= start_date) & \
                 (pd.to_datetime(df["real_out_vdc_time"], errors="coerce") < end_excl)

    return {
        "main": result,
        "exp_attr_only": int(exp_attr_only.sum()),
        "out_vdc_h1": int(out_vdc_h1.sum()),
        "exp_logistics": {
            "both_h1": int(exp_both_h1.sum()),
            "wb_only_h1": int(exp_wb_only_h1.sum()),
            "out_dc_only_h1": int(exp_out_only_h1.sum()),
            "out_dc_total": int(exp_out_h1.sum()),
            "waybill_to_out_dc_median_days": median_gap,
            "both_sample": int(exp_both_h1.sum()),
        },
        "stats": {
            "dom_total": int(dom_dispatch.sum()),
            "exp_total": int(exp_dispatch.sum()),
            "total": int(business.sum()),
        },
    }


def print_summary(classified: dict, start_date: str, end_date: str):
    df = classified["main"]
    stats = classified["stats"]

    total = stats["total"]
    n_dom = stats["dom_total"]
    n_exp = stats["exp_total"]
    n_exp_attr = classified["exp_attr_only"]
    log = classified.get("exp_logistics", {})

    # ── 校验 ──
    dom_vins = set(df[~df["is_export"]].index)
    exp_vins = set(df[df["is_export"]].index)
    assert dom_vins.isdisjoint(exp_vins), "国内与出口 VIN 有重叠"
    assert len(dom_vins | exp_vins) == total, f"VIN 并集 != 合计: {len(dom_vins | exp_vins)} != {total}"

    print(f"{'='*68}")
    print(f"  车辆 Dispatch 分析")
    print(f"  时间范围：[{start_date}, {end_date})")
    print(f"{'='*68}")
    print()
    print(f"  业务 Dispatch：{_fmt(total)} 辆")
    print(f"  ├─ 国内 Dispatch：{_fmt(n_dom)} 辆")
    print(f"  │  └─ 口径：开票发生在 H1")
    print(f"  └─ 出口 Dispatch：{_fmt(n_exp)} 辆")
    print(f"     └─ 口径：出厂发运（waybill）发生在 H1")
    print()
    print(f"  出口物流跟踪（不计入 Dispatch）")
    print()
    both_h1 = log.get('both_h1', 0)
    wb_only_h1 = log.get('wb_only_h1', 0)
    out_dc_total = log.get('out_dc_total', 0)
    out_dc_only_h1 = log.get('out_dc_only_h1', 0)
    print(f"  H1 出厂发运 {_fmt(n_exp)} 辆中：")
    print(f"    ├─ H1 内完成离港    {_fmt(both_h1)}")
    print(f"    └─ H1 末未离港      {_fmt(wb_only_h1)}")
    print()
    print(f"  H1 离港 {_fmt(out_dc_total)} 辆来源：")
    print(f"    ├─ 来自 H1 出厂     {_fmt(both_h1)}")
    print(f"    └─ 来自 H1 前出厂   {_fmt(out_dc_only_h1)}")
    print()
    if n_exp_attr > 0:
        print(f"  出口仅归属未发运（不计入）         {_fmt(n_exp_attr)}")
    print(f"  （以上已剔除试驾车）")
    out_vdc = classified.get("out_vdc_h1", 0)
    print()
    print(f"  Real Out VDC Time（参考口径）")
    print(f"  H1 内离开 VDC: {_fmt(out_vdc)} 辆")
    median_gap = log.get("waybill_to_out_dc_median_days")
    if median_gap is not None:
        print(f"  出厂→离港中位周期                 {median_gap} 天")
    print()
    gap_text = f"约 {median_gap} 天后" if median_gap is not None else "约 75 天后"
    print(f"  注：出口 Dispatch 采用出厂发运（actual_waybill_out_time）作为统计节点，")
    print(f"      离港通常 {gap_text} 发生，")
    print(f"      因此 H1 出厂车辆有相当一部分将在 H2 完成离港。")
    print()

    print("  按车系：")
    for s in ALL_SERIES:
        dom_s = df[(df["vin_series"] == s) & ~df["is_export"]]
        exp_s = df[(df["vin_series"] == s) & df["is_export"]]
        parts = [f"    {s:>6s}"]
        parts.append(f"  国内 {_fmt(len(dom_s)):>10s}")
        parts.append(f"  出口 {_fmt(len(exp_s)):>10s}")
        parts.append(f"  合计 {_fmt(len(dom_s)+len(exp_s)):>8s}")
        print("".join(parts))

    print()
    monthly = df.groupby(["event_month", "dispatch_track"]).size().unstack(fill_value=0)
    print("  月度趋势：")
    header = f"    {'月份':>4s}"
    for c in ["国内 Dispatch", "出口 Dispatch"]:
        if c in monthly.columns:
            header += f"  {c:>14s}"
    header += f"  {'合计':>8s}"
    print(header)
    for month in sorted(monthly.index):
        parts = [f"    {month:>4d}月"]
        row_total = 0
        for c in ["国内 Dispatch", "出口 Dispatch"]:
            if c in monthly.columns:
                v = monthly.loc[month, c]
                parts.append(f"  {_fmt(v):>14s}")
                row_total += v
        parts.append(f"  {_fmt(row_total):>8s}")
        print("".join(parts))
    print()

    print(f"  数据来源：delivery_inventory.parquet + order_data.parquet")
    print(f"  口径：")
    print(f"    国内 Dispatch = invoice_upload_time 在窗口内（开票）")
    print(f"    出口 Dispatch = actual_waybill_out_time 在窗口内（出厂发运）")
    print(f"    剔除：试驾车（order_type = '试驾车'）")
    print()


def _build_result_contract(classified: dict, start_date: str, end_date: str) -> dict:
    df = classified["main"]
    stats = classified["stats"]

    series_list = []
    for s in ALL_SERIES:
        sub = df[df["vin_series"] == s]
        entry = {
            "series": s,
            "total": len(sub),
            "domestic": int((~sub["is_export"]).sum()),
            "export": int(sub["is_export"].sum()),
        }
        series_list.append(entry)

    monthly_list = []
    for m, grp in df.groupby("event_month"):
        entry = {
            "month": int(m),
            "total": len(grp),
            "domestic": int((~grp["is_export"]).sum()),
            "export": int(grp["is_export"].sum()),
        }
        monthly_list.append(entry)
    monthly_list.sort(key=lambda x: x["month"])

    def _to_native(v):
        if isinstance(v, (np.integer,)): return int(v)
        if isinstance(v, (np.floating,)): return float(v)
        if isinstance(v, dict): return {k: _to_native(v) for k, v in v.items()}
        return v

    return {
        "status": "success",
        "script": "research_scripts/ownership_transfer_analysis.py",
        "scope": {
            "data_source": "delivery_inventory.parquet + order_data.parquet",
            "time_window": {"start": start_date, "end": end_date},
            "metric_definition": "国内=开票; 出口=出厂发运; 剔除试驾车",
        },
        "result": _to_native({
            "total": stats["total"],
            "domestic_dispatch": stats["dom_total"],
            "export_dispatch": stats["exp_total"],
            "export_logistics": classified.get("exp_logistics", {}),
            "export_attr_only_no_dispatch": classified["exp_attr_only"],
            "real_out_vdc_time_h1": classified.get("out_vdc_h1", 0),
            "by_series": series_list,
            "monthly": monthly_list,
        }),
        "artifacts": {},
    }


def run(inv_path=DEFAULT_INV, odf_path=DEFAULT_ODF,
        start_date="2026-01-01", end_date="2026-06-30",
        series=None, exclude_test_drive=True, fmt="text"):

    merged = load_data(inv_path, odf_path)
    classified = classify_dispatch(merged, start_date, end_date,
                                    exclude_test_drive=exclude_test_drive)

    if series:
        series_set = {s.strip() for s in series.split(",")}
        mask = classified["main"]["vin_series"].isin(series_set)
        classified["main"] = classified["main"][mask]

    if fmt == "json":
        return _build_result_contract(classified, start_date, end_date)
    else:
        print_summary(classified, start_date, end_date)
        return None


def main():
    parser = argparse.ArgumentParser(description="车辆 Dispatch 分析（国内=订单绑定, 出口=离港出关∪出厂发运）")
    parser.add_argument("--inv-path", type=Path, default=DEFAULT_INV)
    parser.add_argument("--odf-path", type=Path, default=DEFAULT_ODF)
    parser.add_argument("--start-date", default="2026-01-01")
    parser.add_argument("--end-date", default="2026-06-30")
    parser.add_argument("--series", help="车系过滤（逗号分隔，如 LS6,LS9）")
    parser.add_argument("--no-exclude-test-drive", action="store_true", help="不剔除试驾车（默认剔除）")
    parser.add_argument("--format", "-f", choices=["text", "json"], default="text")
    args = parser.parse_args()

    result = run(
        inv_path=args.inv_path,
        odf_path=args.odf_path,
        start_date=args.start_date,
        end_date=args.end_date,
        series=args.series,
        exclude_test_drive=not args.no_exclude_test_drive,
        fmt=args.format,
    )

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
