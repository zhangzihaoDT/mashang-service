#!/usr/bin/env python3
"""
MIIT Pipeline P4.7: EIDC 正式公告抓取 + 解析 + 归档（source 层编排）

从 EIDC 官方正式公告页获取批次 → 下载附件 → 解析 source record → 写入 data/eidc/batch_{N}/。

职责边界：
  - 本脚本只做 source 获取与归档（eidc_source + eidc_parser）
  - 不写 product_master / vehicle_parameter（canonical 由 07 负责）
  - 不继承 legacy product_list 字段位置假设

用法:
  python3 scripts/09_fetch_eidc_batch.py --batch 408
  python3 scripts/09_fetch_eidc_batch.py --batch 408 --discovery-only
  python3 scripts/09_fetch_eidc_batch.py --batch 408 --no-download

产出（沿用 Source Archive Contract）：
  data/eidc/batch_408/
    ├── import_manifest.json      provenance + 附件 sha256
    ├── product_list.json         EIDC source record（road 产品，解析后）
    ├── source_evidence.json      批次元数据 + 附件清单
    ├── attachment_text_src/      附件 .txt（转换后）
    ├── raw_metadata.json         批次原始元数据
    ├── attachments/              gitignored 原始 .doc
    └── raw_detail.html           gitignored 原始公告页
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from miit_paths import EIDC_DIR, ensure_dir  # noqa: E402
import eidc_source as src  # noqa: E402
import eidc_parser  # noqa: E402

# 已知正式公告页映射（EIDC 公告发布栏目）
KNOWN_ANNOUNCEMENT = {
    "401": "https://www.miit-eidc.org.cn/art/2025/12/15/art_1691_11915.html",
    "402": "https://www.miit-eidc.org.cn/art/2025/12/31/art_1691_11974.html",
    "403": "https://www.miit-eidc.org.cn/art/2026/2/9/art_1691_12093.html",
    "404": "https://www.miit-eidc.org.cn/art/2026/3/18/art_1691_12168.html",
    "405": "https://www.miit-eidc.org.cn/art/2026/4/14/art_1691_12236.html",
    "406": "https://www.miit-eidc.org.cn/art/2026/5/9/art_1691_12292.html",
    "407": "https://www.miit-eidc.org.cn/art/2026/6/12/art_1691_12457.html",
    "408": "https://www.miit-eidc.org.cn/art/2026/7/17/art_1691_12598.html",
}

MANIFEST_SCHEMA = "eidc_import_manifest.v2"


def run(batch: str, discovery_only: bool = False, no_download: bool = False,
        offline: bool = False) -> dict:
    detail_url = KNOWN_ANNOUNCEMENT.get(batch)
    if not detail_url:
        print(f"batch {batch} 无已知正式公告页（KNOWN_ANNOUNCEMENT）")
        sys.exit(1)

    batch_dir = EIDC_DIR / f"batch_{batch}"
    ensure_dir(batch_dir)
    ensure_dir(batch_dir / "attachments")
    ensure_dir(batch_dir / "attachment_text_src")

    # ── 1. 抓取公告页 + 解析元数据 ──
    if offline and (batch_dir / "raw_metadata.json").exists():
        # offline 模式：复用已缓存的批次元数据（网络不可用时重解析附件）
        meta = json.loads((batch_dir / "raw_metadata.json").read_text())
        print(f"[1/5] offline: 复用缓存 raw_metadata.json")
        html = ""
    else:
        print(f"[1/5] fetch announcement: {detail_url}")
        html = src.fetch_announcement_page(detail_url)
        meta = src.parse_announcement_metadata(html, detail_url)
        meta["batch_no"] = str(batch)
        meta["source"] = "eidc"
        meta["stage"] = "confirmed"
        meta["fetch_mode"] = "fresh_rebuild"
        (batch_dir / "raw_metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        (batch_dir / "raw_detail.html").write_text(html, encoding="utf-8")
        print(f"  title: {meta.get('title', '')[:60]}")
        print(f"  announcement_no: {meta.get('announcement_no', '')} | publish: {meta.get('publish_date', '')}")
        print(f"  attachments: {len(meta.get('attachments', []))}")

    if discovery_only:
        print("\n[discovery-only] 完成，未下载附件")
        return meta

    # ── 2. 下载附件 + 转文本 ──
    print("[2/5] download attachments")
    attachments_status = []
    for att in meta.get("attachments", []):
        fname = att["filename"]
        doc_path = batch_dir / "attachments" / fname
        dl = src.download_attachment(att["url"], doc_path, force=False)
        att["download_status"] = dl["status"]
        att["sha256"] = dl.get("sha256", "")
        att["size"] = dl.get("size", 0)
        attachments_status.append(dl)
        print(f"  {fname}: {dl['status']} ({dl.get('sha256', '')[:10]}...)")

    # ── 3. 附件 .doc → .txt（textutil）──
    print("[3/5] convert doc -> txt")
    for att in meta.get("attachments", []):
        fname = att["filename"]
        doc_path = batch_dir / "attachments" / fname
        txt_path = batch_dir / "attachment_text_src" / fname.replace(".doc", ".txt")
        if doc_path.exists():
            conv = src.doc_to_txt(doc_path, txt_path)
            print(f"  {fname}: {conv['status']}")

    # ── 4. 解析 road 产品（附件1）──
    print("[4/5] parse road products")
    road_txt = None
    for att in meta.get("attachments", []):
        if "道路机动车辆" in att.get("title", ""):
            road_txt = batch_dir / "attachment_text_src" / att["filename"].replace(".doc", ".txt")
            break
    product_records = []
    if road_txt and road_txt.exists():
        text = road_txt.read_text()
        product_records = eidc_parser.parse_road_products(text, batch)
    (batch_dir / "product_list.json").write_text(
        json.dumps(product_records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  road products: {len(product_records)}")

    # ── 5. import_manifest ──
    print("[5/5] write import_manifest")
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "batch_no": str(batch),
        "source": "eidc",
        "stage": "confirmed",
        "fetch_mode": "fresh_rebuild",
        "legacy_source": None,
        "parser_version": "eidc_source/eidc_parser (MIIT)",
        "imported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_url": detail_url,
        "announcement_no": meta.get("announcement_no", ""),
        "publish_date": meta.get("publish_date", ""),
        "vehicle_tax_batch": meta.get("vehicle_tax_batch", ""),
        "purchase_tax_batch": meta.get("purchase_tax_batch", ""),
        "attachments": meta.get("attachments", []),
        "raw_product_rows": len(product_records),
        "notes": "fresh_rebuild：直接来自 EIDC 官方正式公告附件，非 legacy 导入",
    }
    (batch_dir / "import_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n完成: data/eidc/batch_{batch}/")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="EIDC 正式公告 source 抓取/解析/归档")
    parser.add_argument("--batch", required=True, help="公告批次号（当前支持 407/408）")
    parser.add_argument("--discovery-only", action="store_true", help="只抓取公告页元数据，不下载附件")
    parser.add_argument("--no-download", action="store_true", help="跳过附件下载（仅重新解析已有 txt）")
    parser.add_argument("--offline", action="store_true", help="复用缓存 raw_metadata.json（网络不可用时）")
    args = parser.parse_args()
    run(args.batch, discovery_only=args.discovery_only, no_download=args.no_download,
        offline=args.offline)


if __name__ == "__main__":
    main()
