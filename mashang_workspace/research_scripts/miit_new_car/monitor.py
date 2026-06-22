#!/usr/bin/env python
"""
MIIT 新车公告批次监控 — 串联完整流程。

V0.2.1:
  - 网络重试与 backoff（通过 http_utils）
  - discovery cache fallback
  - detail page cache fallback
  - 已处理批次幂等复用 evidence
  - --refresh / --force-refresh
  - summary 包含 cache 标记

用法:
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --latest
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --latest-publicity
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --latest-official
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --batch 408
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --batch 408 --refresh
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --batch 408 --force-refresh
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --all
"""

import sys, json, argparse
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from discover_batches import discover_batches, discover_latest_by_status
from fetch_batch import fetch_batch
from parse_products import parse_batch
from diff_watchlist import diff_batch
from extract_attachment_text import extract_attachment_text
from research_scripts.miit_new_car.http_utils import NetworkError, get_and_reset_retry_count

OUTPUT_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car"
STATE_FILE = OUTPUT_BASE / "state" / "latest_processed_batch.json"
DEFAULT_WATCHLIST = WORKSPACE_ROOT / "configs" / "miit_new_car_watchlist.csv"
EVIDENCE_BASE = OUTPUT_BASE / "evidence"


def _evidence_path(batch_no: int) -> Path:
    return EVIDENCE_BASE / f"batch_{batch_no}_official_source_evidence.json"


def _is_already_processed(batch_no: int) -> bool:
    return _evidence_path(batch_no).exists()


def _load_existing_evidence(batch_no: int) -> dict | None:
    path = _evidence_path(batch_no)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _write_evidence(
    batch_no: int,
    meta: dict,
    diff_result: dict,
    attachment_statuses: list[dict],
    extraction_results: list[dict],
    products: list[dict],
    discovery_source: str = "remote",
    network_retry_count: int = 0,
) -> dict:
    watchlist_hits = []
    for p in diff_result.get("matched_products", []):
        watchlist_hits.append({
            "brand": p.get("brand", ""),
            "matched_keyword": p.get("matched_keyword", ""),
            "matched_text": p.get("matched_text", ""),
            "confidence": "high",
            "evidence_type": "official_announcement_publicity" if meta.get("status") == "publicity" else "official_announcement_official",
        })

    evidence = {
        "source_type": "official",
        "source_name": "MIIT New Car Announcement",
        "batch_no": batch_no,
        "batch_status": meta.get("status", ""),
        "publish_date": meta.get("publish_date", ""),
        "detail_url": meta.get("detail_url", ""),
        "discovery_source": discovery_source,
        "detail_source": meta.get("detail_source", "remote"),
        "evidence_source": "generated",
        "artifacts": {
            "metadata": str(OUTPUT_BASE / "raw" / f"batch_{batch_no}" / "metadata.json"),
            "products_json": str(OUTPUT_BASE / "parsed" / f"batch_{batch_no}_products.json"),
            "watchlist_diff": str(OUTPUT_BASE / "diff" / f"batch_{batch_no}_watchlist_diff.json"),
            "attachment_text": str(OUTPUT_BASE / "extracted" / f"batch_{batch_no}_attachment_text.json"),
        },
        "attachment_summary": {
            "total": len(attachment_statuses),
            "downloaded": sum(1 for s in attachment_statuses if s.get("status") == "downloaded"),
            "failed": sum(1 for s in attachment_statuses if s.get("status") == "failed"),
        },
        "extraction_summary": {
            "total": len(extraction_results),
            "success": sum(1 for r in extraction_results if r["extract_status"] == "success"),
            "unsupported": sum(1 for r in extraction_results if r["extract_status"] == "unsupported"),
            "failed": sum(1 for r in extraction_results if r["extract_status"] == "failed"),
        },
        "parsed_product_count": len(products),
        "watchlist_hits": watchlist_hits,
        "network_retry_count": network_retry_count,
        "generated_at": meta.get("fetched_at", ""),
    }

    EVIDENCE_BASE.mkdir(parents=True, exist_ok=True)
    path = _evidence_path(batch_no)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(f"  Evidence: {path}")
    return evidence


def _build_summary_from_evidence(evidence: dict) -> dict:
    """从已有的 evidence 构建 summary，标记 skipped_existing。"""
    ew = evidence
    return {
        "batch_no": ew.get("batch_no", 0),
        "status": ew.get("batch_status", ""),
        "publish_date": ew.get("publish_date", ""),
        "structured_records": ew.get("parsed_product_count", 0),
        "watchlist_matched": len(ew.get("watchlist_hits", [])),
        "discovery_source": "skipped_existing",
        "detail_source": "skipped_existing",
        "evidence_source": "existing",
        "network_retry_count": 0,
        "network_warnings_count": 0,
        "files": {"evidence_json": str(_evidence_path(ew.get("batch_no", 0)))},
        "evidence": ew,
    }


def run_monitor(
    batch_no: int,
    detail_url: str | None = None,
    watchlist_path: Path | None = None,
    download: bool = True,
    state_update: bool = True,
    force_refresh: bool = False,
    discovery_source: str = "remote",
) -> dict:
    wl_path = watchlist_path or DEFAULT_WATCHLIST
    network_warnings_count = 0

    print(f"\n{'='*60}")
    print(f"  第 {batch_no} 批 MIIT 新车公告监控")
    print(f"{'='*60}\n")

    # 1. Fetch
    print("[1/4] 抓取批次详情...")
    try:
        meta = fetch_batch(batch_no=batch_no, detail_url=detail_url, download=download)
    except NetworkError as e:
        network_warnings_count += 1
        if force_refresh:
            raise
        meta = fetch_batch(batch_no=batch_no, detail_url=detail_url, download=download)

    status_label = "公示" if meta.get("status") == "publicity" else "正式发布"
    att_statuses = meta.get("attachment_statuses", [])
    att_downloaded = sum(1 for s in att_statuses if s["status"] == "downloaded")
    att_failed = sum(1 for s in att_statuses if s["status"] == "failed")
    detail_source = meta.get("detail_source", "remote")
    detail_tag = f" [{detail_source.upper()}]" if detail_source != "remote" else ""
    print(f"  ✓ 第 {meta['batch_no']} 批 [{status_label}]{detail_tag} {meta.get('publish_date', '')}")
    print(f"  附件: 下载 {att_downloaded}, 失败 {att_failed}")

    # 2. Text Extraction
    print(f"\n[1b] 附件文本抽取...")
    try:
        extraction_results = extract_attachment_text(batch_no=batch_no)
    except Exception as e:
        print(f"  [WARN] 文本抽取异常: {e}")
        extraction_results = []

    # 3. Parse
    print(f"\n[2/4] 解析产品信息...")
    try:
        products = parse_batch(batch_no=batch_no)
        print(f"  ✓ 解析完成: {len(products)} 条可结构化记录")
    except Exception as e:
        print(f"  [WARN] 解析异常: {e}")
        products = []

    # 4. Diff
    print(f"\n[3/4] Watchlist Diff...")
    try:
        diff = diff_batch(
            batch_no=batch_no,
            watchlist_path=wl_path,
            state_update=state_update,
        )
        print(f"  ✓ Watchlist 命中: {diff['watchlist_matched']} 个")
        print(f"  新增产品: {diff['new_products']} 个 (关联: {diff['new_watchlist_matched']})")
    except FileNotFoundError as e:
        print(f"  [WARN] Diff 跳过 (parse 未生成): {e}")
        diff = {"watchlist_matched": 0, "new_products": 0, "new_watchlist_matched": 0, "matched_products": []}

    # 5. Evidence
    print(f"\n[4/4] 输出报告与 Evidence...")
    retry_count = get_and_reset_retry_count()
    evidence = _write_evidence(
        batch_no=batch_no,
        meta=meta,
        diff_result=diff,
        attachment_statuses=att_statuses,
        extraction_results=extraction_results,
        products=products,
        discovery_source=discovery_source,
        network_retry_count=retry_count,
    )

    result = {
        "batch_no": batch_no,
        "status": meta.get("status", ""),
        "status_label": status_label,
        "publish_date": meta.get("publish_date", ""),
        "title": meta.get("title", ""),
        "structured_records": len(products),
        "watchlist_matched": diff.get("watchlist_matched", 0),
        "new_products": diff.get("new_products", 0),
        "new_watchlist_matched": diff.get("new_watchlist_matched", 0),
        "attachments_downloaded": att_downloaded,
        "attachments_failed": att_failed,
        "extraction_success": sum(1 for r in extraction_results if r.get("extract_status") == "success"),
        "extraction_unsupported": sum(1 for r in extraction_results if r.get("extract_status") == "unsupported"),
        "discovery_source": discovery_source,
        "detail_source": detail_source,
        "evidence_source": "generated",
        "network_retry_count": retry_count,
        "network_warnings_count": network_warnings_count,
        "files": {
            "metadata": str(OUTPUT_BASE / "raw" / f"batch_{batch_no}" / "metadata.json"),
            "parsed_csv": str(OUTPUT_BASE / "parsed" / f"batch_{batch_no}_products.csv"),
            "parsed_json": str(OUTPUT_BASE / "parsed" / f"batch_{batch_no}_products.json"),
            "parsed_md": str(OUTPUT_BASE / "parsed" / f"batch_{batch_no}_products.md"),
            "diff_json": str(OUTPUT_BASE / "diff" / f"batch_{batch_no}_watchlist_diff.json"),
            "diff_md": str(OUTPUT_BASE / "diff" / f"batch_{batch_no}_watchlist_diff.md"),
            "evidence_json": str(OUTPUT_BASE / "evidence" / f"batch_{batch_no}_official_source_evidence.json"),
        },
        "evidence": evidence,
    }
    print(f"  ✓ 报告已生成")
    print(f"  ✓ Evidence 已输出")

    return result


def main():
    p = argparse.ArgumentParser(description="MIIT 新车公告批次监控 V0.2.1")
    p.add_argument("--latest", action="store_true", help="自动发现最新批次（按 batch_no 最大）")
    p.add_argument("--latest-publicity", action="store_true", help="自动发现最新公示批次")
    p.add_argument("--latest-official", action="store_true", help="自动发现最新正式公告批次")
    p.add_argument("--batch", type=int, help="指定批次号")
    p.add_argument("--all", action="store_true", help="处理所有未处理批次")
    p.add_argument("--refresh", action="store_true", help="重新处理（允许 cache fallback）")
    p.add_argument("--force-refresh", action="store_true", help="强制远端请求，失败则失败")
    p.add_argument("--watchlist", type=str, help="watchlist CSV 路径")
    p.add_argument("--no-download", action="store_true", help="不下载附件")
    p.add_argument("--no-state-update", action="store_true", help="不更新 state 文件")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    flags = [args.latest, args.latest_publicity, args.latest_official, bool(args.batch), args.all]
    if sum(flags) != 1:
        p.error("请提供 --latest / --latest-publicity / --latest-official / --batch N / --all 之一")

    if args.force_refresh and args.refresh:
        p.error("--refresh 和 --force-refresh 不能同时使用")

    watchlist_path = Path(args.watchlist) if args.watchlist else None
    network_warnings_count = 0

    # Determine batch number(s) and collect detail_urls from discovery
    batch_detail_map: dict[int, str | None] = {}

    if args.batch:
        batch_numbers = [args.batch]
        batch_detail_map[args.batch] = None  # resolve inside fetch
        discovery_source = "direct"
    elif args.all:
        batches, discovery_source = discover_batches(limit=20, force_refresh=args.force_refresh)
        if discovery_source == "network_unavailable":
            print("[ERROR] network_unavailable: 无法连接工信部 EIDC 网站，且本地无 discovery cache", file=sys.stderr)
            sys.exit(1)
        batch_numbers = [b["batch_no"] for b in batches if not _is_already_processed(b["batch_no"])]
        if not batch_numbers:
            print("[INFO] 所有批次均已处理")
            sys.exit(0)
        for b in batches:
            batch_detail_map[b["batch_no"]] = b.get("detail_url")
        print(f"待处理批次: {batch_numbers}")
    else:
        # --latest / --latest-publicity / --latest-official
        print("正在获取最新公告批次...", flush=True)
        if args.latest_publicity:
            latest, discovery_source = discover_latest_by_status("publicity")
            label = "公示"
        elif args.latest_official:
            latest, discovery_source = discover_latest_by_status("official")
            label = "正式发布"
        else:
            batches, discovery_source = discover_batches(limit=5, force_refresh=args.force_refresh)
            latest = batches[0] if batches else None
            label = ""

        if discovery_source == "network_unavailable":
            print("[ERROR] network_unavailable: 无法连接工信部 EIDC 网站，且本地无 discovery cache", file=sys.stderr)
            sys.exit(1)

        if not latest:
            print("[ERROR] 未发现任何批次", file=sys.stderr)
            sys.exit(1)

        latest_batch_no = latest["batch_no"]
        latest_status = latest["status"]
        cache_tag = " [CACHE]" if discovery_source == "cache" else ""
        print(f"  最新批次: 第 {latest_batch_no} 批 ({latest_status}) [{label}]{cache_tag}")

        # Store detail_url from discovery so fetch doesn't re-discover
        batch_detail_map[latest_batch_no] = latest.get("detail_url")

        # Idempotent check: if evidence already exists and not refresh, reuse
        if _is_already_processed(latest_batch_no) and not args.refresh and not args.force_refresh:
            evidence = _load_existing_evidence(latest_batch_no)
            if evidence:
                print(f"  第 {latest_batch_no} 批已处理过，复用本地 evidence。")
                summary = _build_summary_from_evidence(evidence)
                print(f"\n{'='*60}")
                print(f"  MIIT New Car Monitor Summary")
                print(f"{'='*60}")
                print(f"  batch_no: {summary['batch_no']}")
                print(f"  status: {summary['status']}")
                print(f"  discovery_source: {summary['discovery_source']}")
                print(f"  detail_source: {summary['detail_source']}")
                print(f"  evidence_source: {summary['evidence_source']}")
                print(f"  network_retry_count: {summary['network_retry_count']}")
                print(f"  network_warnings_count: {summary['network_warnings_count']}")
                print(f"  evidence: {summary['files']['evidence_json']}")
                if args.format == "json":
                    print(json.dumps(summary, ensure_ascii=False, indent=2))
                sys.exit(0)

    # Process each batch
    results = []
    for bn in batch_numbers:
        try:
            result = run_monitor(
                batch_no=bn,
                detail_url=batch_detail_map.get(bn),
                watchlist_path=watchlist_path,
                download=not args.no_download,
                state_update=not args.no_state_update,
                force_refresh=args.force_refresh,
                discovery_source=discovery_source,
            )
            results.append(result)
        except Exception as e:
            print(f"\n[ERROR] 第 {bn} 批处理失败: {e}", file=sys.stderr)
            results.append({"batch_no": bn, "error": str(e)})

    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print(f"\n{'='*60}")
    print(f"  MIIT New Car Monitor Summary")
    print(f"{'='*60}")
    for r in results:
        if "error" in r:
            print(f"  ✗ 第 {r['batch_no']} 批: {r['error']}")
        else:
            print(f"  batch_no: {r['batch_no']}")
            print(f"  status: {r['status']}")
            print(f"  discovery_source: {r.get('discovery_source', 'unknown')}")
            print(f"  detail_source: {r.get('detail_source', 'unknown')}")
            print(f"  evidence_source: {r.get('evidence_source', 'unknown')}")
            print(f"  network_retry_count: {r.get('network_retry_count', 0)}")
            print(f"  network_warnings_count: {r.get('network_warnings_count', 0)}")
            print(f"  可结构化记录: {r['structured_records']}, Watchlist: {r['watchlist_matched']}, 新增: {r['new_products']}")
            print(f"  附件: {r.get('attachments_downloaded', '?')} 下载 / {r.get('attachments_failed', '?')} 失败")
            print(f"  文本抽取: {r.get('extraction_success', '?')} 成功 / {r.get('extraction_unsupported', '?')} 不支持")
            print(f"  evidence: {r['files']['evidence_json']}")


if __name__ == "__main__":
    main()
