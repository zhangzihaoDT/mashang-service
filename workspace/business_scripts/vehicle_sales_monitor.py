#!/usr/bin/env python
"""统一预售/上市监控 runner。

读 shared/schema/business_definition.json → 判定 active 代际 + phase（支持多代际）
→ order_data 新鲜度 gate → 调 utils/monitors.{presale,launch} compute/card → notify。

脚本本身不知道 CM3/DM2/LS6 的含义，一切口径来自 business_definition。

用法:
    python business_scripts/vehicle_sales_monitor.py --dry-run
    python business_scripts/vehicle_sales_monitor.py --as-of 2026-09-10 --dry-run
    python business_scripts/vehicle_sales_monitor.py --series CM3 --phase presale
    python business_scripts/vehicle_sales_monitor.py --series CM3 --phase presale --force-phase
    python business_scripts/vehicle_sales_monitor.py --format json --output outputs/tables/

`--force-phase`（配合 --series）忽略 active 窗口判定，按 --phase（默认 presale）
渲染指定代际——用于「代际已进入 launch 后仍发预售快照」等场景（原 presale-snapshot 语义）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter

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
from jobs.snapshot import read_snapshot_inputs  # noqa: E402
from utils.monitors import freshness  # noqa: E402
from utils.monitors import launch as launch_monitor  # noqa: E402
from utils.monitors import presale as presale_monitor  # noqa: E402
from utils.monitors.phase import (  # noqa: E402
    detect_active,
    load_business_definition,
    model_series_of,
    phase_of,
    presale_open_ended_window_days,
    series_label,
)
from utils.monitors.series_group import apply_series_group_logic  # noqa: E402
from utils.result_contract import (  # noqa: E402
    build_error_contract,
    build_partial_contract,
    build_success_contract,
    save_contract_json,
)

SCRIPT = "business_scripts/vehicle_sales_monitor.py"
ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
DATETIME_COLS = [
    "intention_payment_time",
    "intention_refund_time",
    "deposit_payment_time",
    "deposit_refund_time",
    "lock_time",
    "approve_refund_time",
    "order_create_date",
    "invoice_upload_time",
    "delivery_date",
]


def load_order(path: Path | None = None) -> pd.DataFrame:
    df = pd.read_parquet(path if path is not None else ORDER_PARQUET)
    for c in DATETIME_COLS:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def build_stale_card(fresh: dict, active: list[dict]) -> dict:
    gens = "、".join(f"{a['label']}（{a['generation']}·{a['phase']}）" for a in active) or "无"
    ref = fresh.get("refresh_ts")
    ref_str = f"{ref:%Y-%m-%d %H:%M}" if ref is not None else "未知"
    source = "调度器刷新" if fresh.get("refresh_source") == "scheduler" else "文件 mtime"
    latest = fresh.get("latest_ts")
    latest_str = f"{latest:%Y-%m-%d %H:%M}" if latest is not None else "未知"
    lines = [
        "**⚠ 监控数据尚未刷新，本次指标推送跳过**",
        "",
        f"监控对象：{gens}",
        f"数据刷新时间：{ref_str}（{source}）",
        f"最新订单时间：{latest_str}",
        f"判定：{fresh.get('reason')}",
        "",
        "请先运行 `make dataset-update` 刷新数据后重试。",
    ]
    return {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "⚠ 监控数据未刷新"}, "template": "orange"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}},
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": f"统计时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}],
                },
            ],
        },
    }


def run(args) -> int:
    started = perf_counter()
    snapshot = getattr(args, "snapshot", None)
    snapshot_scope = {}
    order_path = None
    if snapshot:
        args.format = "json"
        try:
            version, inputs = read_snapshot_inputs(snapshot, ["order_data"])
            order_path = Path(inputs["order_data"]["path"])
            snapshot_scope = {"data_source": "ticket_snapshot", "snapshot_version": version, "inputs": inputs}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return _emit(build_error_contract(SCRIPT, " ".join(sys.argv), str(exc)), args, cards=[])
    bdef = load_business_definition()
    today = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp(datetime.now().date())

    if args.force_phase:
        # 强制按指定 phase 渲染显式 series，忽略 active 窗口判定。
        # 用于「代际已进入 launch 后仍发预售快照」等场景（原 presale-snapshot 语义）。
        wanted = {s.strip() for s in (args.series or "").split(",") if s.strip()}
        if not wanted:
            raise SystemExit("--force-phase 需要显式 --series")
        wanted_p = {p.strip() for p in (args.phase or "presale").split(",") if p.strip()}
        active = [
            {
                "generation": g,
                "model_series": model_series_of(bdef, g),
                "phase": p,
                "label": series_label(bdef, g),
                "presale_close": None,
                "open_ended": False,
            }
            for g in wanted
            for p in wanted_p
        ]
    else:
        active = detect_active(bdef, today)
        if args.series:
            wanted = {s.strip() for s in args.series.split(",") if s.strip()}
            active = [a for a in active if a["generation"] in wanted]
        if args.phase:
            wanted_p = {p.strip() for p in args.phase.split(",") if p.strip()}
            active = [a for a in active if a["phase"] in wanted_p]
        if not active and args.series and args.phase == "presale":
            # 显式指定代际的预售快照：即使已超出兜底窗口，仍按预售口径出数
            wanted = {s.strip() for s in args.series.split(",") if s.strip()}
            active = [
                {
                    "generation": g,
                    "model_series": model_series_of(bdef, g),
                    "phase": "presale",
                    "label": series_label(bdef, g),
                    "presale_close": None,
                    "open_ended": False,
                }
                for g in wanted
                if phase_of(bdef, g, today) != "launch"
            ]

    live = args.as_of is None and not snapshot
    fresh = None
    if live:
        now = pd.Timestamp(args.now) if args.now else pd.Timestamp.now()
        refresh_ts = pd.Timestamp(args.refresh_ts) if args.refresh_ts else None
        fresh = freshness.check(now=now, bdef=bdef, refresh_ts=refresh_ts)

    # 预售阶段按「start + 兜底天数（end 未确认时）」判定：
    # 显式指定代际但尚未到预售首日时，不应推送「等待数据」卡。
    presale_gens = {x["generation"] for x in detect_active(bdef, today, phases=("presale",))}
    for a in active:
        if a.get("phase") == "presale" and a["generation"] not in presale_gens:
            a["phase"] = phase_of(bdef, a["generation"], today) or "presale"

    scope = {
        "data_source": "dataset/order_data.parquet",
        "time_window": {"as_of": today.date().isoformat()},
        "filters": {"series": args.series, "phase": args.phase},
        "metric_definition": "预售小订 / 上市锁单监控（business_definition.monitor）",
        "launch_retained_lock_rule": (
            "上市锁单中退款审批时间（approve_refund_time）为空，按订单号去重。"
            "款式占比以该口径的累计锁单为分母。"
        ),
        "presale_window_rule": (
            "start <= day < end；end（上市日）未确认时按 start + "
            f"{presale_open_ended_window_days(bdef)} 天持续输出预售监控"
        ),
    }

    if snapshot:
        scope.update(snapshot_scope)
        scope["launch_retained_lock_rule"] = (
            "上市开放以来按订单号去重；累计锁单含已审批退款，留存锁单剔除已审批退款。"
            "款式占比以留存锁单为分母。"
        )

    # ── 无 active 代际 ──
    if not active:
        contract = build_success_contract(
            SCRIPT, " ".join(sys.argv),
            scope,
            {"summary": f"{today.date()} 无处于 presale/launch 阶段的代际", "monitors": []},
            warnings=["无 active 代际"],
        )
        return _emit(contract, args, cards=[])

    # ── 新鲜度 gate ──
    if live and fresh and not fresh["fresh"] and not args.allow_stale:
        card = build_stale_card(fresh, active)
        if args.dry_run:
            print(json.dumps(card, ensure_ascii=False, indent=2))
        else:
            _send(card)
        contract = build_partial_contract(
            SCRIPT, " ".join(sys.argv), scope,
            {"summary": f"数据 stale（{fresh['reason']}），跳过 {len(active)} 个监控", "monitors": []},
            warnings=[f"stale: {fresh['reason']}"],
        )
        return _emit(contract, args, cards=[card])

    # ── 计算 ──
    try:
        df = apply_series_group_logic(load_order(order_path) if snapshot else load_order(), bdef)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if not snapshot:
            raise
        return _emit(build_error_contract(SCRIPT, " ".join(sys.argv), str(exc), scope=scope), args, cards=[])
    monitors: list[dict] = []
    cards: list[dict] = []
    errors: list[str] = []
    for a in active:
        gen, phase = a["generation"], a["phase"]
        try:
            if phase == "presale":
                metrics = presale_monitor.compute(df, bdef, today, gen)
                if snapshot:
                    card = None
                elif metrics.get("data_before_open"):
                    card = presale_monitor.build_waiting_card(metrics)
                else:
                    card = presale_monitor.build_card(metrics, show_notes=args.dry_run)
            elif phase == "launch":
                if snapshot:
                    metrics = launch_monitor.compute(df, bdef, today, gen, include_checks=True)
                    if any(check["status"] != "passed" for check in metrics["checks"].values()):
                        errors.append(f"{gen}/{phase}: snapshot metric checks failed")
                    card = None
                else:
                    metrics = launch_monitor.compute(df, bdef, today, gen)
                    card = launch_monitor.build_card(metrics, show_notes=args.dry_run)
            else:
                continue
            monitors.append({"generation": gen, "phase": phase, "label": a["label"], "metrics": metrics})
            if card is not None:
                cards.append(card)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{gen}/{phase}: {exc}")

    if args.dry_run:
        for card in cards:
            print(json.dumps(card, ensure_ascii=False, indent=2))
    else:
        for card in cards:
            _send(card)

    result = {
        "summary": f"{today.date()} active {len(active)} 个，成功 {len(monitors)}，失败 {len(errors)}",
        "monitors": monitors,
    }
    if errors and monitors:
        contract = build_partial_contract(SCRIPT, " ".join(sys.argv), scope, result, warnings=errors)
    elif errors:
        contract = build_error_contract(SCRIPT, " ".join(sys.argv), "; ".join(errors), scope=scope)
    else:
        contract = build_success_contract(SCRIPT, " ".join(sys.argv), scope, result)
    if snapshot:
        contract["timing_ms"] = {"query": round((perf_counter() - started) * 1000)}
    return _emit(contract, args, cards=cards)


def _send(card: dict) -> bool:
    res = notify(raw_payload=card, provider_name="feishu_webhook")
    if res.ok:
        print("✅ 飞书消息发送成功")
        return True
    print(f"❌ 飞书消息发送失败: {res.error}")
    return False


def _emit(contract: dict, args, cards: list) -> int:
    if args.format == "json":
        print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(f"[Summary] {contract['result'].get('summary', '')}")
        if contract["warnings"]:
            for w in contract["warnings"]:
                print(f"  ⚠ {w}")
    if args.output:
        out = Path(args.output)
        if out.is_dir() or str(args.output).endswith("/"):
            out = out / "vehicle_sales_monitor_result.json"
        save_contract_json(contract, out)
    return 0 if contract["status"] != "error" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="统一预售/上市监控 runner")
    parser.add_argument("--snapshot", type=Path, help="Ticket snapshot.json；只读输出 JSON，不发送卡片")
    parser.add_argument("--as-of", default=None, help="统计基准日 YYYY-MM-DD（默认今天；给定时跳过新鲜度 gate）")
    parser.add_argument("--now", default=None, help="覆盖当前时刻（用于新鲜度 gate 测试）")
    parser.add_argument("--refresh-ts", default=None, help="本轮数据刷新完成时刻（ISO，调度器注入）；缺省回退 parquet mtime")
    parser.add_argument("--series", default=None, help="过滤代际，逗号分隔，如 CM3,DM2")
    parser.add_argument("--phase", default=None, help="过滤阶段，逗号分隔：presale,launch")
    parser.add_argument(
        "--force-phase",
        action="store_true",
        help="配合 --series 强制按 --phase（默认 presale）渲染，忽略 active 窗口判定（用于已 launch 代际发预售快照）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印卡片，不发送飞书")
    parser.add_argument("--allow-stale", action="store_true", help="数据 stale 时仍推送指标")
    parser.add_argument("--format", default="terminal", choices=["terminal", "json"])
    parser.add_argument("--output", default=None, help="Result Contract 输出路径或目录")
    args = parser.parse_args()
    if args.snapshot and (args.output or args.refresh_ts or args.now):
        parser.error("--snapshot cannot be combined with --output, --refresh-ts or --now")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
