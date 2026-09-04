"""
inbox_runner.py — Planner 日报管线编排。

流程: parse_contract → route → upsert → audit
"""

import sys
from pathlib import Path
from datetime import datetime

from . import inbox_parser, inbox_filter
from .fact_store import FactStore


def _generate_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def run_text(raw_text: str, date: str = None, write_facts: bool = True,
             input_channel: str = "inbox",
             source_pipeline: str = "daily", run_id: str = None, run_mode: str = "") -> dict:
    """处理 Planner 日报文本。"""
    effective_date = date or datetime.now().strftime("%Y-%m-%d")
    rid = run_id or _generate_run_id()

    contract = inbox_parser.parse_contract(raw_text, default_date=effective_date)

    for item in contract["items"]:
        item["source_pipeline"] = source_pipeline
        item["run_id"] = rid
        item["run_mode"] = run_mode or input_channel
        item["input_channel"] = input_channel
        item["monitor_date"] = effective_date

    store = FactStore() if write_facts else None

    confirmed_facts = []
    review_signals = []
    brand_statuses = []
    brand_volumes = []
    others = []
    fact_results = []
    signal_results = []
    status_results = []
    volume_results = []

    for item in contract["items"]:
        route_result = inbox_filter.route(item)
        route_to = route_result["route_to"]

        if route_to == "confirmed_fact":
            confirmed_facts.append(item)
            if store:
                fact_results.append(store.insert(item))

        elif route_to == "review_signal":
            review_signals.append(item)
            if store:
                signal_results.append(store.insert_signal(item))

        elif route_to == "brand_status":
            brand_statuses.append(item)
            if store:
                status_results.append(store.upsert_brand_status(item))

        elif route_to == "brand_volume":
            brand_volumes.append(item)
            if store:
                volume_results.append(store.insert_brand_volume(item))

        else:
            others.append(item)

    coverage = store.audit_coverage() if store else {}

    summary = {
        "source_type": "planner_daily_report",
        "date": effective_date,
        "run_id": rid,
        "total_items": len(contract["items"]),
        "confirmed_facts": len(confirmed_facts),
        "review_signals": len(review_signals),
        "brand_statuses": len(brand_statuses),
        "brand_volumes": len(brand_volumes),
        "other": len(others),
        "sections": contract.get("sections", []),
        "confirmed_fact_items": confirmed_facts,
        "review_signal_items": review_signals,
        "brand_status_items": brand_statuses,
        "brand_volume_items": brand_volumes,
        "other_items": others,
        "fact_results": fact_results,
        "signal_results": signal_results,
        "status_results": status_results,
        "volume_results": volume_results,
        "coverage": coverage,
    }
    return summary


def run_file(file_path: str, date: str = None, write_facts: bool = True,
             source_pipeline: str = "daily", run_id: str = None, run_mode: str = "") -> dict:
    """从文件读取并处理。"""
    text = Path(file_path).read_text(encoding="utf-8")
    return run_text(text, date=date, write_facts=write_facts,
                    input_channel=f"file:{file_path}",
                    source_pipeline=source_pipeline, run_id=run_id, run_mode=run_mode)


def run_interactive() -> dict:
    """交互模式。"""
    print("=" * 50)
    print("Auto Launch Inbox — 交互模式")
    print("粘贴 Planner 日报，输入 /done 结束")
    print("输入 /cancel 取消")
    print("=" * 50)

    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "/done":
            break
        if line.strip() == "/cancel":
            print("[inbox] 已取消")
            return {"action": "cancelled"}
        lines.append(line)

    raw_text = "\n".join(lines)
    if not raw_text.strip():
        print("[inbox] 未输入任何内容")
        return {"action": "no_input"}

    summary = run_text(raw_text, write_facts=False)
    _print_summary(summary)

    total = summary.get("total_items", 0)
    cf = summary.get("confirmed_facts", 0)
    rs = summary.get("review_signals", 0)
    bs = summary.get("brand_statuses", 0)
    bv = summary.get("brand_volumes", 0)

    if cf > 0 or rs > 0 or bs > 0 or bv > 0:
        resp = input(f"\n写入 {cf} 条事实 + {rs} 条信号 + {bs} 条品牌状态 + {bv} 条声量到数据库？(y/n): ").strip().lower()
        if resp == "y":
            summary = run_text(raw_text, write_facts=True)
            _print_summary(summary)
            print("[inbox] 已完成写入")
        else:
            print("[inbox] 未写入，可稍后重新导入")
    else:
        print("[inbox] 无可写入的数据")

    return summary


def _print_summary(summary: dict):
    print()
    print("-" * 50)
    ds = summary.get("date", "")
    print(f"Inbox Summary — {ds}  (planner_daily_report)")
    print(f"  Total items:      {summary.get('total_items', 0)}")
    print(f"  Confirmed facts:  {summary.get('confirmed_facts', 0)}")
    print(f"  Review signals:   {summary.get('review_signals', 0)}")
    print(f"  Brand statuses:   {summary.get('brand_statuses', 0)}")
    print(f"  Brand volumes:    {summary.get('brand_volumes', 0)}")
    print(f"  Other:            {summary.get('other', 0)}")
    print()

    if summary.get("confirmed_fact_items"):
        print("  [CONFIRMED FACTS]")
        for i, ki in enumerate(summary["confirmed_fact_items"], 1):
            b = ki.get("brand", "") or ""
            m = ki.get("model", "") or ""
            et = ki.get("event_type", "") or ""
            t = (ki.get("title") or "")[:60]
            print(f"    {i}. [{b}][{m}] {et} — {t}")

    if summary.get("review_signal_items"):
        print()
        print("  [REVIEW SIGNALS]")
        for i, si in enumerate(summary["review_signal_items"], 1):
            b = si.get("brand", "") or ""
            c = (si.get("claim") or si.get("title") or "")[:60]
            print(f"    {i}. [{b}] {c}")

    if summary.get("brand_status_items"):
        print()
        print(f"  [BRAND STATUSES]  ({len(summary['brand_status_items'])} brands)")
        for i, si in enumerate(summary["brand_status_items"], 1):
            b = si.get("brand", "") or ""
            ph = si.get("status_phase", "") or ""
            le = si.get("last_event", "") or ""
            print(f"    {i}. {b:<12}  phase={ph:<12}  last_event={le}")

    if summary.get("brand_volume_items"):
        print()
        print("  [BRAND VOLUMES]")
        for i, vi in enumerate(summary["brand_volume_items"], 1):
            b = vi.get("brand", "") or ""
            t = vi.get("volume_trend", "") or ""
            h = vi.get("heat_change", "") or ""
            print(f"    {i}. {b:<12}  trend={t:<6}  heat={h}")

    if summary.get("fact_results"):
        print()
        print("  [FACT STORE]")
        for fr in summary["fact_results"]:
            action = "新增" if fr["action"] == "inserted" else "更新"
            print(f"    fact {action}  fact_id={fr['fact_id']} (seen={fr['seen_count']})")

    if summary.get("signal_results"):
        print()
        print("  [SIGNAL STORE]")
        for sr in summary["signal_results"]:
            action = "新增" if sr["action"] == "inserted" else "更新"
            print(f"    signal {action}  signal_id={sr['signal_id']} (seen={sr['seen_count']})")

    if summary.get("status_results"):
        print()
        print("  [BRAND STATUS STORE]")
        for sr in summary["status_results"]:
            action = "新增" if sr["action"] == "inserted" else "更新"
            print(f"    {sr['brand']:<12}  {action}")

    if summary.get("volume_results"):
        print()
        print("  [BRAND VOLUME STORE]")
        for vr in summary["volume_results"]:
            print(f"    {vr['brand']:<12}  inserted  volume_id={vr.get('volume_id','')}")

    coverage = summary.get("coverage", {})
    if coverage:
        print()
        print("  [COVERAGE AUDIT]")
        print(f"    facts table:         {coverage.get('facts_total', 0)}")
        print(f"    signals table:       {coverage.get('signals_total', 0)}")
        print(f"    brand_status table:  {coverage.get('brand_status_total', 0)}")
        print(f"    brand_volume table:  {coverage.get('brand_volume_total', 0)}")
        print(f"    evidence table:      {coverage.get('evidence_total', 0)}")
