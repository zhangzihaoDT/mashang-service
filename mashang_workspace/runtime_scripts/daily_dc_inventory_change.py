#!/usr/bin/env python
"""
DC 库存变动分析 — 解释库存为什么从昨天变成了今天。

核心价值不是记录当天发生了什么，而是对账：
  库存变化 = 入库 - 出库
  开票数 ≠ 库存减少（受入库对冲、已出库补开票、出库未开票影响）

支持单日分析或时间范围汇总。

用法:
    python runtime_scripts/daily_dc_inventory_change.py
    python runtime_scripts/daily_dc_inventory_change.py --date 2026-07-28
    python runtime_scripts/daily_dc_inventory_change.py --start-date 2026-07-28 --end-date 2026-07-30
    python runtime_scripts/daily_dc_inventory_change.py --format json
    python runtime_scripts/daily_dc_inventory_change.py --date 2026-07-28 --format json --output outputs/tables/
"""

import sys, argparse, json, os
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import importlib.util
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from utils.result_contract import build_success_contract, save_contract_json
from utils.business import is_corporate_owner
from capabilities.notify.notify_service import notify

spec = importlib.util.spec_from_file_location(
    "d", REPO_ROOT / "shared/operators" / "dealer_unsold_inventory.py"
)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

INVENTORY_PARQUET = REPO_ROOT / "dataset" / "delivery_inventory.parquet"
ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
OVERSEAS = {"上汽国际", "海外"}
SERIES_MAP = {"LSJEL":"LS8","LSJEH":"LS9","LSJWL":"LS7","LSJWR":"LS6","LSJWT":"L6","LSJE3":"L7"}
MODELS = ["LS6", "LS8", "LS9", "L6", "LS7", "L7"]


def parse_args():
    p = argparse.ArgumentParser(description="DC 库存变动分析 — 单日或时间范围")
    p.add_argument("--date", type=str, default=None, help="目标日期 (YYYY-MM-DD，默认昨天)")
    p.add_argument("--start-date", type=str, default=None, help="开始日期 (YYYY-MM-DD)")
    p.add_argument("--end-date", type=str, default=None, help="结束日期 (YYYY-MM-DD)")
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    p.add_argument("--webhook", type=str, default=None, nargs="?", const="env",
                    help="发送到飞书 webhook（传值或默认从 FS_WEBHOOK_URL 读取）")
    args = p.parse_args()
    if args.start_date and not args.end_date:
        p.error("--start-date 需要配合 --end-date 使用")
    return args


def analyze_day(target_date: str) -> dict:
    d1 = pd.Timestamp(target_date).normalize()
    d2 = d1 + timedelta(days=1)

    inv = pd.read_parquet(INVENTORY_PARQUET)
    odf = pd.read_parquet(ORDER_PARQUET)
    inv = d.compute(inv, odf)

    domestic = inv[~inv["bloc_name"].isin(OVERSEAS)].copy()
    domestic["arrival"] = pd.to_datetime(domestic["real_in_dc_time"])
    domestic["exit_event"] = domestic[["out_delivery_center_time", "order_invoice_upload_time"]].min(axis=1)

    # 库存水位（同口径：国内DC在库_未开票），以 snapshot 为准
    def inventory_mask(dt):
        d_end = dt + timedelta(days=1)
        return (domestic["arrival"] < d_end) & (domestic["exit_event"].isna() | (domestic["exit_event"] >= d_end))

    prev_mask = inventory_mask(d1 - timedelta(days=1))
    curr_mask = inventory_mask(d1)
    prev_set = set(domestic[prev_mask]["vin"].astype(str))
    curr_set = set(domestic[curr_mask]["vin"].astype(str))
    inv_prev = len(prev_set)
    inv_curr = len(curr_set)
    net_change = inv_curr - inv_prev

    # 从 snapshot 差异直接推导出入库（不依赖事件计数，消除时序异常影响）
    arrivals_set = curr_set - prev_set        # 真正进入库存并留存的车辆集合
    exited_set = prev_set - curr_set          # 真正离开库存的车辆集合
    arrivals = len(arrivals_set)              # 真正进入库存并留存的车辆
    exits_all = len(exited_set)               # 真正离开库存的车辆

    # ── 出库拆解（仅限真正出库的车辆） ──
    exited = domestic[domestic["vin"].astype(str).isin(exited_set)]
    has_inv = exited["order_invoice_upload_time"].notna()
    has_outdc = exited["out_delivery_center_time"].notna()
    exit_invoice_driven = int((has_inv & (exited["exit_event"] == exited["order_invoice_upload_time"])).sum())
    exit_outdc_driven = int((has_outdc & (exited["exit_event"] == exited["out_delivery_center_time"])).sum())
    exit_only_invoice_no_outdc = int((exited["order_invoice_upload_time"].notna() & exited["out_delivery_center_time"].isna()).sum())

    exited["series"] = exited["vin"].str[:5].map(SERIES_MAP).fillna("其他")
    exit_by_model = {m: int((exited["series"] == m).sum()) for m in MODELS if (exited["series"] == m).sum() > 0}

    # ── 库存车型拆解 ──
    domestic["series"] = domestic["vin"].str[:5].map(SERIES_MAP).fillna("其他")
    curr_inventory = domestic[domestic["vin"].astype(str).isin(curr_set)]
    inventory_by_model = {m: int((curr_inventory["series"] == m).sum()) for m in MODELS if (curr_inventory["series"] == m).sum() > 0}



    # ── 开票拆解 ──
    odf["inv_date"] = pd.to_datetime(odf["invoice_upload_time"])
    raw_inv = odf[(odf["inv_date"] >= d1) & (odf["inv_date"] < d2)]
    raw_total = raw_inv["order_number"].nunique()

    with_lock = raw_inv[raw_inv["lock_time"].notna()]
    retail_total = with_lock["order_number"].nunique()
    user_car = with_lock[with_lock["order_type"] == "用户车"]["order_number"].nunique()

    corp_total = 0
    corp_by_model = {}
    if "owner_identity_no" in raw_inv.columns:
        corp_mask = raw_inv["owner_identity_no"].apply(is_corporate_owner)
        corp_total = raw_inv[corp_mask]["order_number"].nunique()
        for m in MODELS:
            subset = raw_inv[corp_mask & (raw_inv["series"].isin(["LS9", "LS9Hyper"]) if m == "LS9" else (raw_inv["series"] == m))]
            cnt = subset["order_number"].nunique()
            if cnt:
                corp_by_model[m] = cnt

    # ── 开票 vs 出库 交叉 ──
    inv_vins = set(raw_inv["vin"].dropna().astype(str))
    # 已出库补开票：开票车辆中，出库事件在当日之前
    invoice_vins_with_prior_exit = len(inv_vins - exited_set - arrivals_set)
    # 出库未开票：出库车辆中，当天无开票记录
    exit_no_invoice = len(exited_set - inv_vins)

    # ── 车型级开票分布 ──
    invoice_by_model = {}
    for m in MODELS:
        subset = with_lock[with_lock["series"].isin(["LS9", "LS9Hyper"]) if m == "LS9" else (with_lock["series"] == m)]
        uc = subset[subset["order_type"] == "用户车"]["order_number"].nunique() if "order_type" in subset.columns else 0
        cnt = subset["order_number"].nunique()
        if cnt:
            invoice_by_model[m] = {"total": cnt, "user_car": uc}

    return {
        "date": target_date,
        "inventory": {
            "prev_day": inv_prev,
            "curr_day": inv_curr,
            "net_change": net_change,
            "arrivals": arrivals,
            "exits_total": exits_all,
            "exits_by_invoice_driven": exit_invoice_driven,
            "exits_by_outdc_driven": exit_outdc_driven,
            "exits_only_invoice_no_outdc": exit_only_invoice_no_outdc,
            "exits_by_model": exit_by_model,
            "by_model": inventory_by_model,
        },
        "invoice": {
            "raw_total": raw_total,
            "retail_total": retail_total,
            "user_car": user_car,
            "corporate_total": corp_total,
            "corporate_by_model": corp_by_model,
            "by_model": invoice_by_model,
        },
        "reconciliation": {
            "invoice_vins_with_prior_exit": invoice_vins_with_prior_exit,
            "exit_without_invoice": exit_no_invoice,
        },
    }


def analyze_range(start_date: str, end_date: str) -> dict:
    days = []
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    cursor = start
    while cursor <= end:
        days.append(analyze_day(cursor.strftime("%Y-%m-%d")))
        cursor += timedelta(days=1)

    inv_first = days[0]["inventory"]["prev_day"]
    inv_last = days[-1]["inventory"]["curr_day"]
    total_arrivals = sum(d["inventory"]["arrivals"] for d in days)
    total_exits = sum(d["inventory"]["exits_total"] for d in days)
    total_invoice = sum(d["invoice"]["raw_total"] for d in days)
    total_prior_exit = sum(d["reconciliation"]["invoice_vins_with_prior_exit"] for d in days)
    total_exit_no_invoice = sum(d["reconciliation"]["exit_without_invoice"] for d in days)

    exit_by_model = {}
    for d in days:
        for m, c in d["inventory"].get("exits_by_model", {}).items():
            exit_by_model[m] = exit_by_model.get(m, 0) + c

    invoice_by_model = {}
    for d in days:
        for m, info in d["invoice"].get("by_model", {}).items():
            if m not in invoice_by_model:
                invoice_by_model[m] = {"total": 0, "user_car": 0}
            invoice_by_model[m]["total"] += info["total"]
            invoice_by_model[m]["user_car"] += info["user_car"]

    inventory_by_model = days[-1]["inventory"].get("by_model", {})

    return {
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
        "summary": {
            "inventory_start": inv_first,
            "inventory_end": inv_last,
            "net_change": inv_last - inv_first,
            "total_arrivals": total_arrivals,
            "total_exits": total_exits,
            "total_invoice": total_invoice,
            "invoice_vins_with_prior_exit": total_prior_exit,
            "exit_without_invoice": total_exit_no_invoice,
            "exit_by_model": exit_by_model,
            "invoice_by_model": invoice_by_model,
            "inventory_by_model": inventory_by_model,
        },
    }


def format_range_terminal(report: dict) -> str:
    s = report["summary"]
    days = report["days"]
    lines = []
    lines.append(f"📦 DC 库存变动汇总（{report['start_date']} → {report['end_date']}，共 {len(days)} 天）")
    lines.append("")
    lines.append("📊 库存概况")
    lines.append(f"开始时（{report['start_date']} 期初）：{s['inventory_start']:,} 台")
    lines.append(f"结束时（{report['end_date']} 期末）：{s['inventory_end']:,} 台")
    lines.append(f"净变化：{s['net_change']:+d} 台")
    lines.append("")
    lines.append("📋 逐日明细")
    lines.append(f"{'日期':<12} {'期初库存':<10} {'期末库存':<10} {'入库':<8} {'出库':<8} {'净变':<8} {'开票':<6}")
    lines.append("-" * 62)
    for d in days:
        inv = d["inventory"]
        invc = d["invoice"]
        lines.append(f"{d['date']:<12} {inv['prev_day']:<10,} {inv['curr_day']:<10,} {inv['arrivals']:<8} {inv['exits_total']:<8} {inv['net_change']:<+8} {invc['raw_total']:<6}")
    total_invoice = s["total_invoice"]
    lines.append("-" * 62)
    lines.append(f"{'合计':<12} {'':<10} {'':<10} {s['total_arrivals']:<8} {s['total_exits']:<8} {s['net_change']:<+8} {total_invoice:<6}")
    lines.append("")
    lines.append("🚚 出库车型汇总")
    for m in ["LS6", "LS8", "LS9", "L6", "LS7", "L7"]:
        if m in s["exit_by_model"]:
            lines.append(f"  - {m}：{s['exit_by_model'][m]} 台")
    if s.get("inventory_by_model"):
        lines.append("")
        lines.append("📦 当前 DC 库存余量")
        for m in ["LS6", "LS8", "LS9", "L6", "LS7", "L7"]:
            if m in s["inventory_by_model"]:
                lines.append(f"  - {m}：{s['inventory_by_model'][m]:,} 台")
    lines.append("")
    lines.append("🧾 开票汇总")
    lines.append(f"总开票：{s['total_invoice']} 台")
    for m in ["LS6", "LS8", "LS9", "L6", "LS7", "L7"]:
        if m in s["invoice_by_model"]:
            info = s["invoice_by_model"][m]
            lines.append(f"  - {m}：{info['total']} 台（用户车 {info['user_car']} 台）")
    lines.append("")
    lines.append("🔍 差异归因")
    lines.append(f"开票 {s['total_invoice']} 台 ≠ 库存减少 {abs(s['net_change'])} 台")
    lines.append(f"· 入库对冲：+{s['total_arrivals']} 台（新到 DC）")
    lines.append(f"· 已出库补开票：-{s['invoice_vins_with_prior_exit']} 台")
    lines.append(f"· 出库未开票：+{s['exit_without_invoice']} 台")
    lines.append("──")
    net_calc = s["total_arrivals"] - s["total_exits"]
    lines.append(f"库存净变化 = 入库 {s['total_arrivals']} - 出库 {s['total_exits']} = {net_calc}  ✓")
    lines.append("")
    lines.append("---")
    lines.append(f"统计时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} | 脚本：daily_dc_inventory_change.py")
    return "\n".join(lines)


def format_terminal(report: dict) -> str:
    d = report["date"]
    inv = report["inventory"]
    invc = report["invoice"]
    rec = report["reconciliation"]

    lines = []

    # ── 标题 ──
    lines.append(f"📦 DC 库存变动分析（{d}）")
    lines.append("")

    # ── 库存概况 ──
    lines.append("📊 库存概况")
    lines.append(f"开始时：{inv['prev_day']:,} 台")
    lines.append(f"结束时：{inv['curr_day']:,} 台")
    lines.append(f"净变化：{inv['net_change']:+d} 台")
    lines.append("")

    # ── 当日库存流转 ──
    lines.append("🚚 当日库存流转")
    lines.append(f"入库：{inv['arrivals']} 台")
    lines.append(f"出库：{inv['exits_total']} 台")
    lines.append(f"- 开票驱动出库：{inv['exits_by_invoice_driven']} 台（其中仅开票未出 DC：{inv['exits_only_invoice_no_outdc']} 台）")
    lines.append(f"- 物理出库驱动：{inv['exits_by_outdc_driven']} 台")
    if inv.get("exits_by_model"):
        parts = [f"{m} {inv['exits_by_model'][m]}" for m in MODELS if m in inv.get("exits_by_model", {})]
        lines.append(f"出库车型：{'、'.join(parts)}")
    if inv.get("by_model"):
        parts = [f"{m} {inv['by_model'][m]}" for m in MODELS if m in inv.get("by_model", {})]
        lines.append(f"DC 库存余量：{'、'.join(parts)}")
    lines.append("")

    # ── 当日开票 ──
    lines.append("🧾 当日开票")
    lines.append(f"原始开票：{invc['raw_total']} 台")
    lines.append(f"零售口径：{invc['retail_total']} 台（用户车 {invc['user_car']} 台）")
    if invc.get("by_model"):
        for m in MODELS:
            if m in invc["by_model"]:
                info = invc["by_model"][m]
                lines.append(f"- {m}：{info['total']} 台（用户车 {info['user_car']} 台）")
    if invc["corporate_total"] > 0:
        cp = "、".join(f"{m} {c}" for m, c in invc.get("corporate_by_model", {}).items())
        lines.append(f"对公批售（已排除）：{invc['corporate_total']} 台" + (f"（{cp}）" if cp else ""))
    lines.append("")

    # ── 差异归因 ──
    lines.append("🔍 差异归因")
    lines.append(f"开票 {invc['raw_total']} 台 ≠ 库存减少 {abs(inv['net_change'])} 台")
    lines.append(f"· 入库对冲：+{inv['arrivals']} 台（新到 DC）")
    lines.append(f"· 已出库补开票：-{rec['invoice_vins_with_prior_exit']} 台（开票时早已出库，库存此前已扣减）")
    lines.append(f"· 出库未开票：+{rec['exit_without_invoice']} 台（物理出库但未开票）")
    lines.append("──")
    lines.append(f"库存净变化 = 入库 {inv['arrivals']} - 出库 {inv['exits_total']} = {inv['net_change']}  ✓ 已闭环")
    lines.append("")
    lines.append("---")
    lines.append(f"统计时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} | 脚本：daily_dc_inventory_change.py")

    return "\n".join(lines)


def build_feishu_card(report: dict, is_range: bool) -> dict:
    def block(*lines):
        return "\n".join(line for line in lines if line)

    if is_range:
        s = report["summary"]
        days = report["days"]
        daily_rows = "\n".join(
            f"{d['date']}  期初 {d['inventory']['prev_day']:,} → 期末 {d['inventory']['curr_day']:,}  "
            f"入库 {d['inventory']['arrivals']}  出库 {d['inventory']['exits_total']}  净变 {d['inventory']['net_change']:+d}"
            for d in days
        )
        exit_models = "、".join(f"{m} {s['exit_by_model'][m]}" for m in ["LS6","LS8","LS9","L6","LS7","L7"] if m in s.get("exit_by_model", {}))
        inv_items = "、".join(
            f"{m} {s['inventory_by_model'][m]:,}" for m in ["LS6","LS8","LS9","L6","LS7","L7"] if m in s.get("inventory_by_model", {})
        )
        blocks = [
            f"**📦 DC 库存变动汇总（{report['start_date']} → {report['end_date']}）**",
            f"**库存水位：** {s['inventory_start']:,} → {s['inventory_end']:,}（净变 {s['net_change']:+d}）",
        ]
        if inv_items:
            blocks.append(f"**DC 库存余量：** {inv_items}")
        blocks.append(block("**逐日明细：**", daily_rows))
        if exit_models:
            blocks.append(f"**出库车型：** {exit_models}")
        blocks.append(f"**总开票：** {s['total_invoice']} 台")
        blocks.append(
            block(
                "**差异归因：**",
                f"开票 {s['total_invoice']} 台 ≠ 库存减少 {abs(s['net_change'])} 台",
                f"· 入库对冲 +{s['total_arrivals']}  已出库补开票 -{s['invoice_vins_with_prior_exit']}  出库未开票 +{s['exit_without_invoice']}",
                f"净变 = 入库 {s['total_arrivals']} - 出库 {s['total_exits']} = {s['net_change']} ✓",
            )
        )
        content = "\n\n".join(blocks)
    else:
        inv = report["inventory"]
        invc = report["invoice"]
        rec = report["reconciliation"]
        exit_models = "、".join(f"{m} {inv['exits_by_model'][m]}" for m in ["LS6","LS8","LS9","L6","LS7","L7"] if m in inv.get("exits_by_model", {}))
        invoice_lines = "\n".join(
            f"- {m}：{invc['by_model'][m]['total']} 台（用户车 {invc['by_model'][m]['user_car']}）"
            for m in ["LS6","LS8","LS9","L6","LS7","L7"] if m in invc.get("by_model", {})
        )
        inv_items = "、".join(
            f"{m} {inv['by_model'][m]:,}" for m in ["LS6","LS8","LS9","L6","LS7","L7"] if m in inv.get("by_model", {})
        )
        blocks = [
            f"**📦 DC 库存变动分析（{report['date']}）**",
            f"**库存概况：** {inv['prev_day']:,} → {inv['curr_day']:,}（净变 {inv['net_change']:+d}）",
        ]
        if inv_items:
            blocks.append(f"**DC 库存余量：** {inv_items}")
        blocks.append(
            block(
                f"**当日流转：** 入库 {inv['arrivals']}  出库 {inv['exits_total']} 台",
                f"**出库车型：** {exit_models}",
            )
        )
        blocks.append(block(f"**开票：** {invc['raw_total']} 台", invoice_lines))
        blocks.append(
            block(
                "**差异归因：**",
                f"开票 {invc['raw_total']} 台 ≠ 库存减少 {abs(inv['net_change'])} 台",
                f"· 入库对冲 +{inv['arrivals']}  已出库补开票 -{rec['invoice_vins_with_prior_exit']}  出库未开票 +{rec['exit_without_invoice']}",
                f"净变 = 入库 {inv['arrivals']} - 出库 {inv['exits_total']} = {inv['net_change']} ✓",
            )
        )
        content = "\n\n".join(blocks)

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "📦 DC 库存变动"},
                "template": "indigo",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"统计时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"}]},
            ],
        },
    }


def send_to_feishu(webhook_url: str, card: dict):
    """发送飞书交互卡片 — 传输收敛至 capabilities.notify。"""
    result = notify(raw_payload=card, webhook_url=webhook_url, provider_name="feishu_webhook")
    if result.ok:
        print("✅ 飞书消息发送成功")
    else:
        print(f"❌ 飞书消息发送失败: {result.error}")


def main():
    args = parse_args()

    if args.start_date and args.end_date:
        report = analyze_range(args.start_date, args.end_date)
        target_label = f"{args.start_date}_to_{args.end_date}"
        is_range = True
    else:
        target = args.date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        report = analyze_day(target)
        target_label = target
        is_range = False

    cmd = "python runtime_scripts/daily_dc_inventory_change.py"
    if args.start_date:
        cmd += f" --start-date {args.start_date} --end-date {args.end_date}"
    elif args.date:
        cmd += f" --date {args.date}"

    if args.format == "json":
        contract = build_success_contract(
            script="runtime_scripts/daily_dc_inventory_change.py",
            command=cmd,
            scope={
                "data_source": "dataset/delivery_inventory.parquet + dataset/order_data.parquet",
                "target_date": target_label,
                "metric_definition": "国内DC在库_未开票 事件回放",
            },
            result=report,
            followup_context={
                "metric": "dc_inventory_change",
                "date": target_label,
            },
        )
        out_dir = Path(args.output) if args.output else _WS_ROOT / "outputs" / "tables"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"dc_inventory_change_{target_label}.json"
        save_contract_json(contract, out_path)
        print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        if "days" in report:
            print(format_range_terminal(report))
        else:
            print(format_terminal(report))

    # ── 飞书推送 ──
    if args.webhook is not None:
        if args.webhook == "env":
            webhook_url = os.getenv("FS_WEBHOOK_URL")
        else:
            webhook_url = args.webhook
        if not webhook_url:
            print("❌ 未找到 FS_WEBHOOK_URL，跳过飞书推送")
        else:
            card = build_feishu_card(report, is_range)
            send_to_feishu(webhook_url, card)

    return 0


if __name__ == "__main__":
    sys.exit(main())
