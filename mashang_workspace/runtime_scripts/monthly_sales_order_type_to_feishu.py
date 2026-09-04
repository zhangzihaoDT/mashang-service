#!/usr/bin/env python
"""
月度销量飞书同步 — 锁单量/开票量 × (车系 × 订单类型: 用户车/试驾车/其他)。

从 order_data.parquet 计算指定月份的锁单量(lock_time)与开票量(invoice_upload_time),
按 order_number 去重, 拆分为 订单类型 与 车系 交叉维度, 发送飞书交互卡片。

用法:
    python runtime_scripts/monthly_sales_order_type_to_feishu.py --month 2026-08
    python runtime_scripts/monthly_sales_order_type_to_feishu.py --month 2026-08 --dry-run
    python runtime_scripts/monthly_sales_order_type_to_feishu.py --month 2026-08 --format json --output outputs/tables/
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

import os
import pandas as pd
from utils.result_contract import build_success_contract, save_contract_json, print_contract_summary
from capabilities.notify.notify_service import notify

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
ORDER_GROUPS = ["用户车", "试驾车", "其他"]
SERIES_ORDER = ["LS6", "L6", "LS8", "LS9", "LS7", "L7"]


def bucket_order_type(ot):
    ot = "" if pd.isna(ot) else str(ot)
    if ot == "用户车":
        return "用户车"
    if ot == "试驾车":
        return "试驾车"
    return "其他"


def compute_monthly_sales(month: str):
    """计算指定月份(YYYY-MM)锁单量/开票量, 返回 dict。"""
    t0 = pd.Timestamp(f"{month}-01")
    t1 = t0 + pd.offsets.MonthBegin(1)

    df = pd.read_parquet(ORDER_PARQUET, columns=["order_number", "order_type", "series", "lock_time", "invoice_upload_time"])
    for c in ["lock_time", "invoice_upload_time"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    df["order_group"] = df["order_type"].map(bucket_order_type)
    df["series_group"] = df["series"].replace({"LS9Hyper": "LS9"})

    lock = df[(df["lock_time"] >= t0) & (df["lock_time"] < t1)]
    invoice = df[(df["invoice_upload_time"] >= t0) & (df["invoice_upload_time"] < t1)]

    data_end_lock = df["lock_time"].max()
    data_end_invoice = df["invoice_upload_time"].max()

    def by_group(sub):
        return sub.groupby("order_group")["order_number"].nunique().reindex(ORDER_GROUPS, fill_value=0)

    def cross(sub):
        pivot = (
            sub.groupby(["series_group", "order_group"])["order_number"]
            .nunique()
            .unstack(fill_value=0)
            .reindex(index=SERIES_ORDER, columns=ORDER_GROUPS, fill_value=0)
        )
        pivot = pivot[pivot.sum(axis=1) > 0]
        return pivot

    lk_by_group = by_group(lock)
    inv_by_group = by_group(invoice)
    lk_cross = cross(lock)
    inv_cross = cross(invoice)

    return {
        "month": month,
        "lock_total": int(lk_by_group.sum()),
        "invoice_total": int(inv_by_group.sum()),
        "lock_by_group": {k: int(v) for k, v in lk_by_group.items()},
        "invoice_by_group": {k: int(v) for k, v in inv_by_group.items()},
        "lock_by_series": {s: {g: int(v) for g, v in row.items()} for s, row in lk_cross.iterrows()},
        "invoice_by_series": {s: {g: int(v) for g, v in row.items()} for s, row in inv_cross.iterrows()},
        "data_end_lock": data_end_lock,
        "data_end_invoice": data_end_invoice,
    }


def _fmt_series_table(cross, title):
    """生成车系×订单类型交叉表 div 的 lark_md 内容 (每车系一行)。"""
    lines = [f"**{title}**", "用户车 / 试驾车 / 其他 / 合计"]
    for s in SERIES_ORDER:
        if s not in cross:
            continue
        g = cross[s]
        row_total = sum(g.values())
        lines.append(
            f"**{s}** {g['用户车']:,} / {g['试驾车']:,} / {g['其他']:,} / {row_total:,}"
        )
    return "\n".join(lines)


def build_feishu_card(m: dict) -> dict:
    """构建飞书交互卡片 — 方案 A: 多元素分层 (div + hr + note)。"""
    lk = m["lock_by_group"]
    inv = m["invoice_by_group"]

    kpi_md = f"锁单量 **{m['lock_total']:,}** / 开票量 **{m['invoice_total']:,}**"

    order_type_md = "\n".join(
        [
            "**订单类型拆解**",
            f"锁单/用户车 **{lk['用户车']:,}** / 试驾车 **{lk['试驾车']:,}** / 其他 **{lk['其他']:,}**",
            f"开票/用户车 **{inv['用户车']:,}** / 试驾车 **{inv['试驾车']:,}** / 其他 **{inv['其他']:,}**",
        ]
    )

    lock_table_md = _fmt_series_table(m["lock_by_series"], f"{m['month']} 锁单量 x 车系")
    invoice_table_md = _fmt_series_table(m["invoice_by_series"], f"{m['month']} 开票量 x 车系")

    data_end = max(m["data_end_lock"], m["data_end_invoice"])
    note_lines = [
        "口径：锁单按 lock_time、开票按 invoice_upload_time 落入当月；order_number 去重；其他 = 集团员工/大客户/员工/经销商员工/空值/仅批售等",
        "数据源：dataset/order_data.parquet",
    ]
    if data_end is not None and str(data_end)[:7] == m["month"]:
        note_lines.append(f"数据截至 {str(data_end)[:10]}，当月完整度需结合更新时点判断")

    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": kpi_md}},
        {"tag": "div", "text": {"tag": "lark_md", "content": order_type_md}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": lock_table_md}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": invoice_table_md}},
        {"tag": "note", "elements": [{"tag": "plain_text", "content": "；".join(note_lines)}]},
        {"tag": "note", "elements": [{"tag": "plain_text", "content": f"统计时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}]},
    ]

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📊 月度销量（{m['month']}）"},
                "template": "blue",
            },
            "elements": elements,
        },
    }


def send_to_feishu(webhook_url: str, card: dict) -> bool:
    """发送飞书交互卡片 — 传输收敛至 capabilities.notify（重试/频率限制/错误语义由能力统一处理）。"""
    result = notify(raw_payload=card, webhook_url=webhook_url, provider_name="feishu_webhook")
    if result.ok:
        print("✅ 飞书消息发送成功")
    else:
        print(f"❌ 飞书消息发送失败: {result.error}")
    return result.ok


def build_contract(m: dict, command: str, artifacts: dict | None = None) -> dict:
    scope = {
        "data_source": "dataset/order_data.parquet",
        "time_window": {"start_date": f"{m['month']}-01", "end_date": f"{m['month']}-月末"},
        "filters": {},
        "metric_definition": "lock_count = COUNTD(order_number WHERE lock_time IS NOT NULL); invoice_count = COUNTD(order_number WHERE invoice_upload_time IS NOT NULL), 按 order_type 分组(用户车/试驾车/其他) 与 车系 交叉",
    }
    result = {
        "summary": f"{m['month']} 锁单量 {m['lock_total']:,} / 开票量 {m['invoice_total']:,}",
        "metrics": {
            "lock_total": m["lock_total"],
            "invoice_total": m["invoice_total"],
            "lock_user_car": m["lock_by_group"]["用户车"],
            "lock_test_drive": m["lock_by_group"]["试驾车"],
            "lock_other": m["lock_by_group"]["其他"],
            "invoice_user_car": m["invoice_by_group"]["用户车"],
            "invoice_test_drive": m["invoice_by_group"]["试驾车"],
            "invoice_other": m["invoice_by_group"]["其他"],
        },
        "dimensions": [
            {"name": "order_type", "items": [{"value": k, "metrics": {"lock_count": v}} for k, v in m["lock_by_group"].items()]},
            {"name": "series", "items": [{"value": s, "metrics": m["lock_by_series"][s]} for s in m["lock_by_series"]]},
        ],
        "tables": [
            {"name": "lock_by_series", "rows": [{"series": s, **g} for s, g in m["lock_by_series"].items()]},
            {"name": "invoice_by_series", "rows": [{"series": s, **g} for s, g in m["invoice_by_series"].items()]},
        ],
    }
    followup = {
        "metric": "monthly_sales",
        "time_window": m["month"],
        "available_dimensions": ["order_type", "series"],
        "top_entities": [
            {"field": "series", "value": s, "metrics": {"lock_count": sum(g.values())}} for s, g in m["lock_by_series"].items()
        ],
    }
    return build_success_contract(
        script="runtime_scripts/monthly_sales_order_type_to_feishu.py",
        command=command,
        scope=scope,
        result=result,
        artifacts=artifacts or {},
        followup_context=followup,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="月度销量(锁单/开票) × 订单类型 × 车系 飞书同步")
    parser.add_argument("--month", type=str, required=True, help="月份 (YYYY-MM, 如 2026-08)")
    parser.add_argument("--dry-run", action="store_true", help="只打印卡片 JSON，不发送飞书")
    parser.add_argument("--webhook", type=str, default=None, nargs="?", const="env",
                        help="飞书 webhook URL（默认从 FS_WEBHOOK_URL 读取）")
    parser.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    parser.add_argument("--output", type=str, default=None, help="输出目录")
    args = parser.parse_args()

    try:
        m = compute_monthly_sales(args.month)
    except Exception as e:
        print(f"❌ 计算失败: {e}")
        return 1

    if not args.dry_run:
        print(f"锁单量: {m['lock_total']:,}  开票量: {m['invoice_total']:,}")
        for g in ORDER_GROUPS:
            print(f"  {g}: 锁单 {m['lock_by_group'][g]:,} / 开票 {m['invoice_by_group'][g]:,}")
        print()

    card = build_feishu_card(m)

    artifacts = {}
    if args.format == "json":
        contract = build_contract(m, " ".join(sys.argv), artifacts)
        print_contract_summary(contract)
        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"monthly_sales_{args.month}.json"
            save_contract_json(contract, path)
            artifacts["json"] = str(path)
        return 0

    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return 0

    webhook = args.webhook if args.webhook not in (None, "env") else os.getenv("FS_WEBHOOK_URL")
    if not webhook:
        print("⚠️ 未设置 FS_WEBHOOK_URL，跳过发送（使用 --dry-run 查看卡片）")
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return 0

    ok = send_to_feishu(webhook, card)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
