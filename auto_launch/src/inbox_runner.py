"""Layer: Inbox Core — 管线编排 + 交互模式"""
"""
inbox_runner.py — Inbox 管线编排。

流程:
  输入 (文件/stdin/交互)
    → inbox_parser.parse_text()
    → inbox_filter.classify() per item
    → fact_store.insert() for keep items
    → summary output
"""

import sys
from pathlib import Path
from datetime import datetime

from . import inbox_parser, inbox_filter
from .fact_store import FactStore


def run_file(file_path: str, date: str = None, write_facts: bool = True) -> dict:
    """从文件读取并处理"""
    text = Path(file_path).read_text(encoding="utf-8")
    return run_text(text, date=date, write_facts=write_facts, input_channel=f"file:{file_path}")


def run_text(raw_text: str, date: str = None, write_facts: bool = True,
             input_channel: str = "inbox") -> dict:
    """处理原始文本"""
    effective_date = date or datetime.now().strftime("%Y-%m-%d")
    items = inbox_parser.parse_text(raw_text, default_date=effective_date)

    keep_items = []
    discard_items = []

    for item in items:
        result = inbox_filter.classify(item)
        if result["decision"] == "keep":
            keep_items.append(result["item"])
        else:
            discard_items.append(result)

    store = FactStore()
    fact_results = []
    if write_facts and keep_items:
        for ki in keep_items:
            fact_result = store.insert(ki)
            fact_results.append(fact_result)

    summary = {
        "total_raw_items": len(items),
        "kept": len(keep_items),
        "discarded": len(discard_items),
        "fact_results": fact_results,
        "kept_items": keep_items,
        "discarded_items": discard_items,
        "date": effective_date,
    }
    return summary


def run_interactive() -> dict:
    """交互模式：提示用户粘贴文本"""
    print("=" * 50)
    print("Auto Launch Inbox — 交互模式")
    print("粘贴 ChatGPT daily run 结果，输入 /done 结束")
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

    if summary["kept"] > 0:
        resp = input(f"\n写入 {summary['kept']} 条事实到数据库？(y/n): ").strip().lower()
        if resp == "y":
            store = FactStore()
            fact_results = []
            for ki in summary["kept_items"]:
                fr = store.insert(ki)
                fact_results.append(fr)
            summary["fact_results"] = fact_results
            print(f"[inbox] 已写入 {len(fact_results)} 条事实")
        else:
            print("[inbox] 未写入，可稍后重新导入")
    else:
        print("[inbox] 无可写入的事实")

    return summary


def _print_summary(summary: dict):
    print()
    print("-" * 50)
    print(f"Inbox Summary — {summary['date']}")
    print(f"  Raw items:  {summary['total_raw_items']}")
    print(f"  Kept:       {summary['kept']}")
    print(f"  Discarded:  {summary['discarded']}")
    print()

    if summary["kept_items"]:
        print("  [KEEP]")
        for i, ki in enumerate(summary["kept_items"], 1):
            b = ki.get("brand", "") or ""
            m = ki.get("model", "") or ""
            et = ki.get("event_type", "") or ""
            t = (ki.get("title") or "")[:60]
            print(f"    {i}. [{b}][{m}] {et} — {t}")

    if summary["discarded_items"]:
        print()
        print("  [DISCARD]")
        for i, di in enumerate(summary["discarded_items"], 1):
            t = (di["item"].get("title") or "")[:50]
            r = di["reason"]
            print(f"    {i}. {t}  ({r})")

    if summary.get("fact_results"):
        print()
        print("  [FACT STORE]")
        for fr in summary["fact_results"]:
            action = "新增" if fr["action"] == "inserted" else "更新"
            print(f"    {action} fact_id={fr['fact_id']} (seen={fr['seen_count']})")
