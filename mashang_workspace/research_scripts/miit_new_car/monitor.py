#!/usr/bin/env python
"""
MIIT 新车公告批次监控 — 串联完整流程 V0.3。

流程:
  discover → fetch + attachment diagnostics → extract text
  → parse structured records → parse product list
  → watchlist diff → evidence layers

用法:
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --latest
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --latest-publicity
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --latest-official
  python mashang_workspace/research_scripts/miit_new_car/monitor.py --batch 408
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
from parse_product_list import parse_product_list
from diagnose_attachment_urls import diagnose_attachments
from research_scripts.miit_new_car.http_utils import NetworkError, get_and_reset_retry_count
from research_scripts.miit_new_car.enterprise_admission_parser import (
    process_attachment as process_enterprise_admission,
)

OUTPUT_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car"
STATE_FILE = OUTPUT_BASE / "state" / "latest_processed_batch.json"
DEFAULT_WATCHLIST = WORKSPACE_ROOT / "configs" / "重点关注新能源品牌.json"
EVIDENCE_BASE = OUTPUT_BASE / "evidence"
EVIDENCE_SCHEMA_VERSION = "miit_official_evidence.v0.3"
GENERATOR_VERSION = "miit_new_car_monitor.v0.3.2"

REQUIRED_EVIDENCE_LAYERS = [
    "official_batch_evidence",
    "official_attachment_evidence",
    "official_product_list_evidence",
]

OPTIONAL_EVIDENCE_LAYERS = [
    "enterprise_admission_evidence",
]


def _evidence_path(batch_no: int) -> Path:
    return EVIDENCE_BASE / f"batch_{batch_no}_official_source_evidence.json"


def _is_already_processed(batch_no: int) -> bool:
    return _evidence_path(batch_no).exists()


def _load_existing_evidence(batch_no: int) -> dict | None:
    path = _evidence_path(batch_no)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return None
    return None


def _validate_evidence_schema(evidence: dict) -> tuple[bool, str]:
    """校验 evidence schema 是否匹配当前版本。
    返回 (valid, reason)。
    仅检查 REQUIRED_EVIDENCE_LAYERS，OPTIONAL_EVIDENCE_LAYERS 可缺失。
    """
    if evidence.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        return False, f"schema_version 不匹配 (期望 {EVIDENCE_SCHEMA_VERSION}, 实际 {evidence.get('schema_version', '无')})"
    layers = evidence.get("evidence_layers")
    if not layers or not isinstance(layers, dict):
        return False, "evidence_layers 缺失"
    for key in REQUIRED_EVIDENCE_LAYERS:
        if key not in layers:
            return False, f"evidence_layers 缺少 {key}"
    return True, ""


def _compute_product_list_quality(product_list: list[dict]) -> dict:
    enterprises = len(set(p.get("enterprise_name", "") for p in product_list if p.get("enterprise_name")))
    models = len(set(p.get("product_model", "") for p in product_list if p.get("product_model")))
    rc = len(product_list)
    if rc == 0:
        return {"record_count": 0, "enterprise_count": 0, "product_model_count": 0, "quality": "empty", "quality_reason": "no_records"}
    if enterprises == 0:
        return {"record_count": rc, "enterprise_count": 0, "product_model_count": models, "quality": "unusable", "quality_reason": "enterprise_name_empty"}
    if models == 0:
        return {"record_count": rc, "enterprise_count": enterprises, "product_model_count": 0, "quality": "low_quality", "quality_reason": "product_model_empty"}
    return {"record_count": rc, "enterprise_count": enterprises, "product_model_count": models, "quality": "usable", "quality_reason": None}


def _build_evidence_layers(
    batch_no: int, meta: dict, diagnostics: list[dict],
    product_list: list[dict], diff_result: dict,
    enterprise_admission_result: dict | None = None,
    browser_trace_evidence: dict | None = None,
) -> dict:
    diag_downloaded = sum(1 for d in diagnostics if d.get("download_status") == "downloaded")
    diag_failed = sum(1 for d in diagnostics if d.get("download_status") == "failed")
    pl_quality = _compute_product_list_quality(product_list)

    ea_available = (
        enterprise_admission_result is not None
        and enterprise_admission_result.get("parse_status") != "error"
    )

    return {
        "official_batch_evidence": {
            "available": True,
            "batch_no": batch_no,
            "batch_status": meta.get("status", ""),
            "detail_url": meta.get("detail_url", ""),
        },
        "official_attachment_evidence": {
            "available": len(diagnostics) > 0,
            "downloaded_count": diag_downloaded,
            "failed_count": diag_failed,
            "diagnostics_path": str(OUTPUT_BASE / "diagnostics" / f"batch_{batch_no}_attachment_diagnostics.json"),
        },
        "official_product_list_evidence": {
            "available": pl_quality["quality"] == "usable",
            **pl_quality,
            "product_list_path": str(OUTPUT_BASE / "product_list" / f"batch_{batch_no}_product_list.json"),
        },
        "enterprise_admission_evidence": {
            "available": ea_available,
            "parse_status": enterprise_admission_result.get("parse_status", "") if enterprise_admission_result else "",
            "quality": enterprise_admission_result.get("quality", "") if enterprise_admission_result else "",
            "canonical_section": enterprise_admission_result.get("canonical_section", "") if enterprise_admission_result else "",
            "detail_asset_type": enterprise_admission_result.get("detail_asset_type", "") if enterprise_admission_result else "",
            "detail_asset_urls": enterprise_admission_result.get("detail_asset_urls", []) if enterprise_admission_result else [],
            "image_asset_urls": enterprise_admission_result.get("image_asset_urls", []) if enterprise_admission_result else [],
            "linked_asset_urls": enterprise_admission_result.get("linked_asset_urls", []) if enterprise_admission_result else [],
            "iframe_urls": enterprise_admission_result.get("iframe_urls", []) if enterprise_admission_result else [],
            "script_asset_urls": enterprise_admission_result.get("script_asset_urls", []) if enterprise_admission_result else [],
            "api_candidate_urls": enterprise_admission_result.get("api_candidate_urls", []) if enterprise_admission_result else [],
            "cms_file_urls": enterprise_admission_result.get("cms_file_urls", []) if enterprise_admission_result else [],
            "extraction_status": enterprise_admission_result.get("extraction_status", "") if enterprise_admission_result else "",
            "extraction_reason": enterprise_admission_result.get("extraction_reason", "") if enterprise_admission_result else "",
            "download_status": enterprise_admission_result.get("download_status", "") if enterprise_admission_result else "",
            "download_error": enterprise_admission_result.get("download_error", "") if enterprise_admission_result else "",
            "browser_trace": browser_trace_evidence is not None,
            "browser_trace_evidence": browser_trace_evidence or {},
        },
    }


def _write_evidence(
    batch_no: int,
    meta: dict,
    diff_result: dict,
    attachment_statuses: list[dict],
    extraction_results: list[dict],
    products: list[dict],
    diagnostics: list[dict],
    product_list: list[dict],
    discovery_source: str = "remote",
    network_retry_count: int = 0,
    enterprise_admission_result: dict | None = None,
    browser_trace_evidence: dict | None = None,
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

    # Compute product_list quality
    pl_enterprises = len(set(p.get("enterprise_name", "") for p in product_list if p.get("enterprise_name")))
    pl_models = len(set(p.get("product_model", "") for p in product_list if p.get("product_model")))
    if len(product_list) == 0:
        pl_quality = "empty"
        pl_quality_reason = "no_records"
    elif pl_enterprises == 0:
        pl_quality = "unusable"
        pl_quality_reason = "enterprise_name_empty"
    elif pl_models == 0:
        pl_quality = "low_quality"
        pl_quality_reason = "product_model_empty"
    else:
        pl_quality = "usable"
        pl_quality_reason = None

    evidence = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "source_type": "official",
        "source_name": "MIIT New Car Announcement",
        "batch_no": batch_no,
        "batch_status": meta.get("status", ""),
        "publish_date": meta.get("publish_date", ""),
        "detail_url": meta.get("detail_url", ""),
        "discovery_source": discovery_source,
        "detail_source": meta.get("detail_source", "remote"),
        "evidence_source": "generated",
        "evidence_layers": _build_evidence_layers(
            batch_no, meta, diagnostics, product_list, diff_result,
            enterprise_admission_result, browser_trace_evidence,
        ),
        "enterprise_admission": enterprise_admission_result or {},
        "browser_trace_evidence": browser_trace_evidence or {},
        "artifacts": {
            "metadata": str(OUTPUT_BASE / "raw" / f"batch_{batch_no}" / "metadata.json"),
            "products_json": str(OUTPUT_BASE / "parsed" / f"batch_{batch_no}_products.json"),
            "product_list_json": str(OUTPUT_BASE / "product_list" / f"batch_{batch_no}_product_list.json"),
            "watchlist_diff": str(OUTPUT_BASE / "diff" / f"batch_{batch_no}_watchlist_diff.json"),
            "attachment_text": str(OUTPUT_BASE / "extracted" / f"batch_{batch_no}_attachment_text.json"),
            "diagnostics": str(OUTPUT_BASE / "diagnostics" / f"batch_{batch_no}_attachment_diagnostics.json"),
        },
        "attachment_summary": {
            "total": len(attachment_statuses),
            "downloaded": sum(1 for s in attachment_statuses if s.get("status") == "downloaded"),
            "skipped": sum(1 for s in attachment_statuses if s.get("status") == "skipped"),
            "failed": sum(1 for s in attachment_statuses if s.get("status") == "failed"),
        },
        "extraction_summary": {
            "total": len(extraction_results),
            "success": sum(1 for r in extraction_results if r["extract_status"] == "success"),
            "unsupported": sum(1 for r in extraction_results if r["extract_status"] == "unsupported"),
            "failed": sum(1 for r in extraction_results if r["extract_status"] == "failed"),
        },
        "parsed_product_count": len(products),
        "product_list_count": len(product_list),
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
    ew = evidence
    layers = ew.get("evidence_layers", {})
    return {
        "batch_no": ew.get("batch_no", 0),
        "status": ew.get("batch_status", ""),
        "publish_date": ew.get("publish_date", ""),
        "structured_records": ew.get("parsed_product_count", 0),
        "product_list_count": ew.get("product_list_count", 0),
        "watchlist_matched": len(ew.get("watchlist_hits", [])),
        "discovery_source": "skipped_existing",
        "detail_source": "skipped_existing",
        "evidence_source": "existing",
        "network_retry_count": 0,
        "network_warnings_count": 0,
        "evidence_layers": layers,
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
    pages: int = 3,
    browser_trace: bool = False,
) -> dict:
    wl_path = watchlist_path or DEFAULT_WATCHLIST
    network_warnings_count = 0
    browser_trace_evidence = None

    print(f"\n{'='*60}")
    print(f"  第 {batch_no} 批 MIIT 新车公告监控")
    print(f"{'='*60}\n")

    # 1. Fetch
    print("[1/4] 抓取批次详情...")
    try:
        meta = fetch_batch(batch_no=batch_no, detail_url=detail_url, download=download, pages=pages)
    except NetworkError as e:
        network_warnings_count += 1
        if force_refresh:
            raise
        meta = fetch_batch(batch_no=batch_no, detail_url=detail_url, download=download, pages=pages)

    status_label = "公示" if meta.get("status") == "publicity" else "正式发布"
    att_statuses = meta.get("attachment_statuses", [])
    att_downloaded = sum(1 for s in att_statuses if s["status"] == "downloaded")
    att_skipped = sum(1 for s in att_statuses if s["status"] == "skipped")
    att_failed = sum(1 for s in att_statuses if s["status"] == "failed")
    detail_source = meta.get("detail_source", "remote")
    detail_tag = f" [{detail_source.upper()}]" if detail_source != "remote" else ""
    print(f"  ✓ 第 {meta['batch_no']} 批 [{status_label}]{detail_tag} {meta.get('publish_date', '')}")
    print(f"  附件: 下载 {att_downloaded}, 跳过已存在 {att_skipped}, 失败 {att_failed}")

    # 1a. Enterprise Admission Processing (if applicable)
    enterprise_admission_result = None
    for att_status in att_statuses:
        if att_status.get("source_type") == "enterprise_admission_change":
            local_path = att_status.get("local_path")
            download_failed = att_status.get("status") == "failed"
            att_title = att_status.get("title", "")
            print(f"\n[1a] 企业准入变更附件: '{att_title[:80]}...'")
            if local_path and Path(local_path).exists():
                try:
                    enterprise_admission_result = process_enterprise_admission(
                        batch_no=batch_no,
                        attachment_local_path=Path(local_path),
                        attachment_url=att_status["url"],
                        parent_notice_url=meta.get("detail_url", ""),
                        parent_notice_title=meta.get("title", ""),
                        output_dir=OUTPUT_BASE / "evidence",
                    )
                    ea_status = enterprise_admission_result.get("parse_status", "?")
                    ea_quality = enterprise_admission_result.get("quality", "?")
                    ea_images = len(enterprise_admission_result.get("detail_asset_urls", []))
                    print(f"   状态: {ea_status}, 质量: {ea_quality}, 图片: {ea_images}")
                except Exception as e:
                    print(f"   [WARN] 企业准入变更解析异常: {e}")
            elif download_failed:
                error_msg = att_status.get("error", "unknown error")
                print(f"   [INFO] 附件下载失败 ({error_msg}), 但 attachment metadata 已记录。")
                # Build partial evidence from metadata even when download fails
                # Try resource extraction even without HTML (will detect empty HTML → needs_browser_network_trace)
                from research_scripts.miit_new_car.enterprise_admission_parser import datainfo_resource_extractor
                extraction = datainfo_resource_extractor(
                    datainfo_html="",
                    datainfo_url=att_status["url"],
                    parent_notice_url=meta.get("detail_url", ""),
                )
                enterprise_admission_result = {
                    "batch_no": batch_no,
                    "source_type": "enterprise_admission_change",
                    "source_format": "html_image_attachment",
                    "source_title": att_title,
                    "parent_notice_title": meta.get("title", ""),
                    "parent_notice_url": meta.get("detail_url", ""),
                    "official_attachment_url": att_status["url"],
                    "canonical_section": "拟发布新准入车辆生产企业",
                    "section_candidates": [
                        "拟发布的新准入车辆生产企业", "拟发布新准入车辆生产企业",
                        "新准入车辆生产企业", "汽车生产企业", "摩托车生产企业",
                        "三轮汽车生产企业", "已准入企业变更信息", "已准入企业变更",
                    ],
                    "section_headings_found": [],
                    "parse_status": "partial",
                    "quality": "low_quality",
                    "quality_reason": f"attachment download failed: {error_msg}; {extraction['extraction_reason']}",
                    "detail_asset_type": "image",
                    "detail_asset_urls": [],
                    "detail_asset_downloaded": False,
                    "detail_asset_path": None,
                    "text_snippet": "",
                    "download_status": "failed",
                    "download_error": error_msg,
                    # V1.1 extraction fields
                    "image_asset_urls": extraction["image_asset_urls"],
                    "linked_asset_urls": extraction["linked_asset_urls"],
                    "iframe_urls": extraction["iframe_urls"],
                    "script_asset_urls": extraction["script_asset_urls"],
                    "api_candidate_urls": extraction["api_candidate_urls"],
                    "cms_file_urls": extraction["cms_file_urls"],
                    "extraction_status": extraction["extraction_status"],
                    "extraction_reason": extraction["extraction_reason"],
                }
                # Still write partial evidence
                import json
                ea_evidence_path = OUTPUT_BASE / "evidence" / f"batch_{batch_no}_enterprise_admission_evidence.json"
                ea_evidence_path.parent.mkdir(parents=True, exist_ok=True)
                with open(ea_evidence_path, "w", encoding="utf-8") as f:
                    json.dump(enterprise_admission_result, f, ensure_ascii=False, indent=2)
                print(f"   已输出 partial evidence: {ea_evidence_path}")

                # Browser trace fallback (optional, requires --browser-trace)
                if browser_trace and enterprise_admission_result.get("extraction_status") == "needs_browser_network_trace":
                    print(f"   [BrowserTrace] 启动浏览器网络追踪...")
                    try:
                        from research_scripts.miit_new_car.browser_trace import (
                            run_browser_trace_and_extract,
                        )
                        trace_result = run_browser_trace_and_extract(
                            parent_notice_url=meta.get("detail_url", ""),
                            attachment_title=att_title,
                            attachment_url=att_status["url"],
                            timeout=30000,
                        )
                        trace_ev = trace_result.get("browser_trace_evidence", {})
                        browser_trace_evidence = trace_ev
                        trace_status = trace_ev.get("browser_page_status", "")
                        print(f"   [BrowserTrace] 状态: {trace_status}")
                        print(f"   [BrowserTrace] 最终 URL: {trace_ev.get('browser_final_url', '')[:100]}")
                        print(f"   [BrowserTrace] 页面标题: {trace_ev.get('browser_page_title', '')[:80]}")
                        print(f"   [BrowserTrace] 资源数: {len(trace_ev.get('browser_resource_urls', []))}")
                        print(f"   [BrowserTrace] 图片数: {len(trace_ev.get('browser_image_urls', []))}")

                        # Always inject browser_trace_evidence into enterprise_admission_result
                        enterprise_admission_result["browser_trace_evidence"] = trace_ev

                        # If trace successfully got rendered HTML, feed back to extractor
                        if trace_status == "success":
                            extraction = trace_result.get("datainfo_extraction")
                            if extraction:
                                enterprise_admission_result.update({
                                    "detail_asset_urls": [u["url"] for u in extraction.get("image_asset_urls", [])],
                                    "image_asset_urls": extraction.get("image_asset_urls", []),
                                    "linked_asset_urls": extraction.get("linked_asset_urls", []),
                                    "iframe_urls": extraction.get("iframe_urls", []),
                                    "script_asset_urls": extraction.get("script_asset_urls", []),
                                    "api_candidate_urls": extraction.get("api_candidate_urls", []),
                                    "cms_file_urls": extraction.get("cms_file_urls", []),
                                    "extraction_status": extraction.get("extraction_status", "")
                                        if extraction.get("extraction_status") != "needs_browser_network_trace"
                                        else "browser_trace_success",
                                    "extraction_reason": extraction.get("extraction_reason", ""),
                                    "parse_status": "partial",
                                    "quality_reason": (
                                        f"browser trace captured page content; "
                                        f"{extraction.get('extraction_reason', '')}"
                                    ),
                                    "download_status": "browser_trace_success",
                                    "download_error": "",
                                })
                        else:
                            enterprise_admission_result["quality_reason"] += (
                                f"; browser trace result: "
                                f"{trace_ev.get('browser_page_status', '?')} - "
                                f"{trace_ev.get('browser_error', 'unknown error')[:120]}"
                            )

                        # Re-write evidence with browser trace results (success or failure)
                        with open(ea_evidence_path, "w", encoding="utf-8") as f:
                            json.dump(enterprise_admission_result, f, ensure_ascii=False, indent=2)
                        print(f"   [BrowserTrace] 已更新 evidence (browser_trace_evidence injected)")
                    except ImportError:
                        print(f"   [BrowserTrace] playwright SDK not available, skipping")
                    except Exception as e:
                        print(f"   [BrowserTrace] 异常: {e}")
            else:
                print(f"   [WARN] 附件状态异常: {att_status.get('status', '?')}")
            break

    # 1b. Attachment Diagnostics
    try:
        diagnostics = diagnose_attachments(batch_no=batch_no)
    except Exception as e:
        print(f"  [WARN] 附件诊断异常: {e}")
        diagnostics = []
    diag_total = len(diagnostics)
    diag_failed_ct = sum(1 for d in diagnostics if d.get("download_status") == "failed")
    diag_ok = sum(1 for d in diagnostics if d.get("download_status") == "downloaded")
    diag_recovered = sum(1 for d in diagnostics if d.get("strategy_used") not in (None, "original_url"))
    if diagnostics:
        print(f"  附件诊断: {diag_total} total / {diag_failed_ct} failed / {diag_ok} ok / {diag_recovered} recovered")

    # 2. Text Extraction
    print(f"\n[2/4] 附件文本抽取...")
    try:
        extraction_results = extract_attachment_text(batch_no=batch_no)
    except Exception as e:
        print(f"  [WARN] 文本抽取异常: {e}")
        extraction_results = []
    ext_success = sum(1 for r in extraction_results if r.get("extract_status") == "success")
    ext_unsupported = sum(1 for r in extraction_results if r.get("extract_status") == "unsupported")
    ext_failed = sum(1 for r in extraction_results if r.get("extract_status") == "failed")
    if not extraction_results:
        print(f"  文本抽取: 无附件")
    else:
        print(f"  文本抽取: {ext_success} 成功 / {ext_unsupported} 不支持 / {ext_failed} 失败（见 extracted/ 获取抽取器信息）")

    # 3. Parse structured records
    print(f"\n[3/4] 解析结构化记录...")
    try:
        products = parse_batch(batch_no=batch_no)
        print(f"  ✓ 解析完成: {len(products)} 条可结构化记录")
    except Exception as e:
        print(f"  [WARN] 解析异常: {e}")
        products = []

    # 3b. Parse product list
    print(f"\n[3b] 解析产品清单主表...")
    try:
        product_list = parse_product_list(batch_no=batch_no)
        pl_enterprises = len(set(p.get("enterprise_name", "") for p in product_list if p.get("enterprise_name")))
        pl_models = len(set(p.get("product_model", "") for p in product_list if p.get("product_model")))
        print(f"  ✓ 产品清单: {len(product_list)} records / {pl_enterprises} enterprises / {pl_models} models")
    except Exception as e:
        print(f"  [WARN] 产品清单解析异常: {e}")
        product_list = []

    # 4. Diff
    print(f"\n[3c] Watchlist Diff...")
    try:
        diff = diff_batch(
            batch_no=batch_no,
            watchlist_path=wl_path,
            state_update=state_update,
        )
        print(f"  ✓ Watchlist 命中: {diff['watchlist_matched']} 个")
        print(f"  新增: {diff['new_products']} 个 (关联: {diff['new_watchlist_matched']})")
    except FileNotFoundError as e:
        print(f"  [WARN] Diff 跳过: {e}")
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
        diagnostics=diagnostics,
        product_list=product_list,
        discovery_source=discovery_source,
        network_retry_count=retry_count,
        enterprise_admission_result=enterprise_admission_result,
        browser_trace_evidence=browser_trace_evidence,
    )

    layers = evidence.get("evidence_layers", {})
    pl_quality_info = layers.get("official_product_list_evidence", {})
    result = {
        "batch_no": batch_no,
        "status": meta.get("status", ""),
        "status_label": status_label,
        "publish_date": meta.get("publish_date", ""),
        "title": meta.get("title", ""),
        "structured_records": len(products),
        "product_list_count": len(product_list),
        "product_list_quality": pl_quality_info.get("quality", "unknown"),
        "product_list_enterprise_count": pl_quality_info.get("enterprise_count", 0),
        "product_list_model_count": pl_quality_info.get("product_model_count", 0),
        "watchlist_matched": diff.get("watchlist_matched", 0),
        "new_products": diff.get("new_products", 0),
        "new_watchlist_matched": diff.get("new_watchlist_matched", 0),
        "attachments_downloaded": att_downloaded,
        "attachments_skipped": att_skipped,
        "attachments_failed": att_failed,
        "diagnostics_total": diag_total,
        "diagnostics_failed": diag_failed_ct,
        "extraction_success": ext_success,
        "extraction_unsupported": ext_unsupported,
        "discovery_source": discovery_source,
        "detail_source": detail_source,
        "evidence_source": "generated",
        "network_retry_count": retry_count,
        "network_warnings_count": network_warnings_count,
        "browser_trace_ran": browser_trace_evidence is not None,
        "browser_trace_status": (browser_trace_evidence or {}).get("browser_page_status", ""),
        "evidence_layers": {
            "batch": layers.get("official_batch_evidence", {}).get("available", False),
            "attachment": layers.get("official_attachment_evidence", {}).get("available", False),
            "product_list": layers.get("official_product_list_evidence", {}).get("available", False),
        },
        "files": {
            "metadata": str(OUTPUT_BASE / "raw" / f"batch_{batch_no}" / "metadata.json"),
            "parsed_csv": str(OUTPUT_BASE / "parsed" / f"batch_{batch_no}_products.csv"),
            "parsed_json": str(OUTPUT_BASE / "parsed" / f"batch_{batch_no}_products.json"),
            "product_list_json": str(OUTPUT_BASE / "product_list" / f"batch_{batch_no}_product_list.json"),
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
    p = argparse.ArgumentParser(description="MIIT 新车公告批次监控 V0.3")
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
    p.add_argument("--pages", type=int, default=3, help="搜索分页页数（默认 3，搜索历史批次时需增加）")
    p.add_argument("--browser-trace", action="store_true", help="启动 Playwright 浏览器网络追踪，用于 datainfo 页面 404 时定位资源")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    flags = [args.latest, args.latest_publicity, args.latest_official, bool(args.batch), args.all]
    if sum(flags) != 1:
        p.error("请提供 --latest / --latest-publicity / --latest-official / --batch N / --all 之一")
    if args.force_refresh and args.refresh:
        p.error("--refresh 和 --force-refresh 不能同时使用")

    watchlist_path = Path(args.watchlist) if args.watchlist else None
    batch_detail_map: dict[int, str | None] = {}

    if args.batch:
        batch_numbers = [args.batch]
        batch_detail_map[args.batch] = None
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
        batch_detail_map[latest_batch_no] = latest.get("detail_url")

        if _is_already_processed(latest_batch_no) and not args.refresh and not args.force_refresh:
            evidence = _load_existing_evidence(latest_batch_no)
            if evidence:
                valid, reason = _validate_evidence_schema(evidence)
                if valid:
                    print(f"  第 {latest_batch_no} 批已处理过，复用本地 evidence。")
                    summary = _build_summary_from_evidence(evidence)
                    layers = summary.get("evidence_layers", {})
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
                    print(f"  evidence_layers:")
                    print(f"    batch: {layers.get('official_batch_evidence', {}).get('available', False)}")
                    print(f"    attachment: {layers.get('official_attachment_evidence', {}).get('available', False)}")
                    print(f"    product_list: {layers.get('official_product_list_evidence', {}).get('available', False)}")
                    print(f"  evidence: {summary['files']['evidence_json']}")
                    if args.format == "json":
                        print(json.dumps(summary, ensure_ascii=False, indent=2))
                    sys.exit(0)
                else:
                    print(f"  第 {latest_batch_no} 批已有 evidence，但 schema 已过期 ({reason})，自动重新生成。")

        batch_numbers = [latest_batch_no]

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
                pages=args.pages,
                browser_trace=args.browser_trace,
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
            layers = r.get("evidence_layers", {})
            print(f"  batch_no: {r['batch_no']}")
            print(f"  status: {r['status']}")
            print(f"  discovery_source: {r.get('discovery_source', 'unknown')}")
            print(f"  detail_source: {r.get('detail_source', 'unknown')}")
            print(f"  evidence_source: {r.get('evidence_source', 'unknown')}")
            print(f"  network_retry_count: {r.get('network_retry_count', 0)}")
            print(f"  network_warnings_count: {r.get('network_warnings_count', 0)}")
            print(f"")
            print(f"  附件: {r.get('attachments_downloaded', 0)} downloaded / {r.get('attachments_skipped', 0)} skipped / {r.get('attachments_failed', 0)} failed")
            print(f"  附件诊断: {r.get('diagnostics_total', 0)} total / {r.get('diagnostics_failed', 0)} failed")
            print(f"  文本抽取: {r.get('extraction_success', 0)} success / {r.get('extraction_unsupported', 0)} unsupported")
            print(f"  可结构化记录: {r['structured_records']}")
            pl_q = r.get('product_list_quality', 'unknown')
            pl_ec = r.get('product_list_enterprise_count', 0)
            pl_mc = r.get('product_list_model_count', 0)
            print(f"  产品清单: {r.get('product_list_count', 0)} records / {pl_ec} enterprises / {pl_mc} models / quality={pl_q}")
            print(f"  Watchlist: {r['watchlist_matched']}, 新增: {r['new_products']}")
            print(f"")
            print(f"  evidence_layers:")
            print(f"    batch: {layers.get('batch', False)}, attachment: {layers.get('attachment', False)}, product_list: {layers.get('product_list', False)}")
            print(f"")
            print(f"  evidence: {r['files']['evidence_json']}")


if __name__ == "__main__":
    main()
