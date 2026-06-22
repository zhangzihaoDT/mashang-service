#!/usr/bin/env python
"""
MIIT 新车公告批次监控 — 串联完整流程。

串联: discover → fetch → parse → diff → report

用法:
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --latest
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --batch 408
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --batch 408 --watchlist path/to/watchlist.csv
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --batch 408 --no-download
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --all
"""

import sys, json, argparse
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT))

from discover_batches import discover_batches
from fetch_batch import fetch_batch
from parse_products import parse_batch
from diff_watchlist import diff_batch

OUTPUT_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car"
STATE_FILE = OUTPUT_BASE / "state" / "latest_processed_batch.json"
DEFAULT_WATCHLIST = WORKSPACE_ROOT / "configs" / "miit_new_car_watchlist.csv"


def _is_already_processed(batch_no: int) -> bool:
    parsed_dir = OUTPUT_BASE / "parsed"
    return (parsed_dir / f"batch_{batch_no}_products.json").exists()


def run_monitor(
    batch_no: int,
    watchlist_path: Path | None = None,
    download: bool = True,
    state_update: bool = True,
) -> dict:
    """运行单批次的完整监控流程。"""
    wl_path = watchlist_path or DEFAULT_WATCHLIST

    print(f"\n{'='*60}")
    print(f"  第 {batch_no} 批 MIIT 新车公告监控")
    print(f"{'='*60}\n")

    # 1. Fetch
    print("[1/4] 抓取批次详情...")
    meta = fetch_batch(batch_no=batch_no, download=download)
    print(f"  ✓ 第 {meta['batch_no']} 批 {meta.get('status', '')}")
    print(f"  {meta.get('publish_date', '')}")

    # 2. Parse
    print(f"\n[2/4] 解析产品信息...")
    products = parse_batch(batch_no=batch_no)
    print(f"  ✓ 解析完成: {len(products)} 个产品")

    # 3. Diff
    print(f"\n[3/4] Watchlist Diff...")
    diff = diff_batch(
        batch_no=batch_no,
        watchlist_path=wl_path,
        state_update=state_update,
    )
    print(f"  ✓ Watchlist 命中: {diff['watchlist_matched']} 个")
    print(f"  新增产品: {diff['new_products']} 个 (关联: {diff['new_watchlist_matched']})")

    # 4. Report
    print(f"\n[4/4] 报告输出...")
    status_label = "公示" if meta.get("status") == "publicity" else "正式发布"
    result = {
        "batch_no": batch_no,
        "status": meta.get("status", ""),
        "status_label": status_label,
        "publish_date": meta.get("publish_date", ""),
        "title": meta.get("title", ""),
        "product_count": len(products),
        "watchlist_matched": diff["watchlist_matched"],
        "new_products": diff["new_products"],
        "new_watchlist_matched": diff["new_watchlist_matched"],
        "files": {
            "metadata": str(OUTPUT_BASE / "raw" / f"batch_{batch_no}" / "metadata.json"),
            "parsed_csv": str(OUTPUT_BASE / "parsed" / f"batch_{batch_no}_products.csv"),
            "parsed_json": str(OUTPUT_BASE / "parsed" / f"batch_{batch_no}_products.json"),
            "parsed_md": str(OUTPUT_BASE / "parsed" / f"batch_{batch_no}_products.md"),
            "diff_json": str(OUTPUT_BASE / "diff" / f"batch_{batch_no}_watchlist_diff.json"),
            "diff_md": str(OUTPUT_BASE / "diff" / f"batch_{batch_no}_watchlist_diff.md"),
        },
    }
    print(f"  ✓ 报告已生成")

    return result


def main():
    p = argparse.ArgumentParser(description="MIIT 新车公告批次监控")
    p.add_argument("--latest", action="store_true", help="自动发现最新未处理批次")
    p.add_argument("--batch", type=int, help="指定批次号")
    p.add_argument("--all", action="store_true", help="处理所有未处理批次")
    p.add_argument("--watchlist", type=str, help="watchlist CSV 路径")
    p.add_argument("--no-download", action="store_true", help="不下载附件")
    p.add_argument("--no-state-update", action="store_true", help="不更新 state 文件")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    if not args.latest and not args.batch and not args.all:
        p.error("请提供 --latest, --batch N, 或 --all")

    watchlist_path = Path(args.watchlist) if args.watchlist else None

    if args.batch:
        batch_numbers = [args.batch]
    elif args.latest:
        # Discover latest batch
        print("正在连接工信部 EIDC 网站获取最新公告批次...", flush=True)
        try:
            batches = discover_batches(limit=5)
        except Exception as e:
            print(f"[ERROR] discover_batches 异常: {e}", file=sys.stderr)
            sys.exit(1)
        if not batches:
            sys.exit(1)
        # Pick the highest batch_no
        latest = batches[0]
        print(f"  最新批次: 第 {latest['batch_no']} 批 ({latest['status']})")

        if _is_already_processed(latest["batch_no"]):
            print(f"  第 {latest['batch_no']} 批已处理过。")
            print(f"  详情: {OUTPUT_BASE / 'diff' / f'batch_{latest['batch_no']}_watchlist_diff.md'}")
            if args.format != "json":
                print(f"\n使用 --batch {latest['batch_no']} 重新处理")
            sys.exit(0)

        batch_numbers = [latest["batch_no"]]
    else:
        # --all: find all unprocessed
        try:
            batches = discover_batches(limit=20)
        except Exception as e:
            print(f"[ERROR] discover_batches 异常: {e}", file=sys.stderr)
            sys.exit(1)
        batch_numbers = [b["batch_no"] for b in batches if not _is_already_processed(b["batch_no"])]
        if not batch_numbers:
            print("[INFO] 所有批次均已处理")
            sys.exit(0)
        print(f"待处理批次: {batch_numbers}")

    results = []
    for bn in batch_numbers:
        try:
            result = run_monitor(
                batch_no=bn,
                watchlist_path=watchlist_path,
                download=not args.no_download,
                state_update=not args.no_state_update,
            )
            results.append(result)
        except Exception as e:
            print(f"\n[ERROR] 第 {bn} 批处理失败: {e}", file=sys.stderr)
            results.append({"batch_no": bn, "error": str(e)})

    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print(f"\n{'='*60}")
    print(f"  监控完成")
    for r in results:
        if "error" in r:
            print(f"  ✗ 第 {r['batch_no']} 批: {r['error']}")
        else:
            print(f"  ✓ 第 {r['batch_no']} 批: {r['product_count']} 产品, {r['watchlist_matched']} 匹配, {r['new_products']} 新增")
            print(f"    解析: {r['files']['parsed_csv']}")
            print(f"    Diff: {r['files']['diff_md']}")


if __name__ == "__main__":
    main()
