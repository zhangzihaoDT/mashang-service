#!/usr/bin/env python
"""通用预售小订监控 CLI（发送飞书）。

代际口径全部来自 shared/schema/business_definition.json + monitor 配置，
脚本不再硬编码 DM2/CM3。

用法:
    python research_scripts/presale_metrics_to_feishu.py --series CM3
    python research_scripts/presale_metrics_to_feishu.py --series CM3 --dry-run
    python research_scripts/presale_metrics_to_feishu.py --series CM3 --as-of 2026-09-10
    python research_scripts/presale_metrics_to_feishu.py            # 默认当前 presale 代际
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(_WS_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from capabilities.notify.notify_service import notify  # noqa: E402
from utils.monitors.phase import detect_active, load_business_definition  # noqa: E402
from utils.monitors.presale import build_card, compute  # noqa: E402
from utils.monitors.series_group import apply_series_group_logic  # noqa: E402

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
DATETIME_COLS = [
    "intention_payment_time",
    "intention_refund_time",
    "deposit_payment_time",
    "deposit_refund_time",
    "lock_time",
    "approve_refund_time",
]


def load_order() -> pd.DataFrame:
    df = pd.read_parquet(ORDER_PARQUET)
    for c in DATETIME_COLS:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="通用预售小订监控（飞书）")
    parser.add_argument("--series", default=None, help="代际（series_group_logic 键），默认当前 presale 代际")
    parser.add_argument("--dry-run", action="store_true", help="只打印卡片，不发送飞书")
    parser.add_argument("--as-of", default=None, help="统计基准日 YYYY-MM-DD（默认今天）")
    args = parser.parse_args()

    if not ORDER_PARQUET.exists():
        print(f"❌ 文件不存在: {ORDER_PARQUET}")
        return 1

    bdef = load_business_definition()
    today = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp(datetime.now().date())

    series = args.series
    if not series:
        active = detect_active(bdef, today, phases=("presale",))
        if not active:
            print(f"⚠️ {today.date()} 无 presale 代际")
            return 0
        series = active[0]["generation"]

    print(f"📖 Loading: {ORDER_PARQUET}（series={series}）")
    df = apply_series_group_logic(load_order(), bdef)
    metrics = compute(df, bdef, today, series)
    card = build_card(metrics, show_notes=args.dry_run)

    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return 0

    result = notify(raw_payload=card, provider_name="feishu_webhook")
    if result.ok:
        print("✅ 飞书消息发送成功")
        return 0
    print(f"❌ 飞书消息发送失败: {result.error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
