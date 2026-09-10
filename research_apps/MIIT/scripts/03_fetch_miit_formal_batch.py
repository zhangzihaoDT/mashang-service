#!/usr/bin/env python3
"""
MIIT Pipeline P3.5: Gov 正式公告抓取 + 解析 + 归档（source 层编排）

从 miit.gov.cn 装备工业一司 → 文件发布栏目获取「道路机动车辆生产企业及产品」正式公告（第 N 批）：
  定位正式公告详情页 → 提取元数据 → 发现并下载「道路机动车辆生产企业及产品（第N批）」附件
  → doc → txt → 复用 eidc_parser 解析 road 产品 → 生成 formal product_list.json。

职责边界：
  - 本脚本只做 source 获取与归档（miit_formal_source + eidc_parser）
  - 不写 product_master / vehicle_parameter（canonical 由 06 负责）
  - 不做 CMS 栏目级 reconcile：公告详情页 URL 由 --url 或 文件发布栏目搜索（--discover）定位

产出（沿用 EIDC Source Archive Contract，落 data/miit_formal/batch_{N}/）：
  data/miit_formal/batch_409/
    ├── import_manifest.json      provenance + 附件 sha256（source=miit_gov, stage=confirmed）
    ├── product_list.json         MIIT formal source record（road 产品，eidc_parser 解析）
    ├── raw_metadata.json         公告元数据（标题/公告号/日期/附件清单）
    ├── attachment_text_src/      附件 .txt（转换后）
    ├── attachments/              gitignored 原始 .doc
    └── raw_detail.html           gitignored 原始公告页

用法:
  python3 scripts/03_fetch_miit_formal_batch.py --batch 409
  python3 scripts/03_fetch_miit_formal_batch.py --batch 409 --discover   # 先按标题搜索公告页
  python3 scripts/03_fetch_miit_formal_batch.py --batch 409 --url https://www.miit.gov.cn/jgsj/zbys/wjfb/art/2026/art_xxx.html
  python3 scripts/03_fetch_miit_formal_batch.py --batch 409 --offline    # 复用缓存 raw_detail.html（无网络）
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from miit_paths import ensure_dir, miit_formal_batch_dir  # noqa: E402
import eidc_parser  # noqa: E402
import miit_formal_source as src  # noqa: E402

# olefile 为超大 .doc 备用提取的可选依赖（仅在 textutil 失败时惰性加载）
try:
    import eidc_doc_extract  # noqa: E402
except ImportError:
    eidc_doc_extract = None

MANIFEST_SCHEMA = "miit_formal_import_manifest.v1"


def _find_road_attachment(meta: dict) -> dict | None:
    """定位「道路机动车辆生产企业及产品（第N批）」附件（附件1）。"""
    for att in meta.get("attachments", []):
        if "道路机动车辆" in att.get("title", ""):
            return att
    return None


def build_manifest(batch: str, meta: dict, detail_url: str,
                   product_records: list[dict]) -> dict:
    """构造 MIIT 正式公告 import_manifest（provenance contract）。"""
    return {
        "schema_version": MANIFEST_SCHEMA,
        "batch_no": str(batch),
        "source": "miit_gov",
        "stage": "confirmed",
        "fetch_mode": "gov_formal",
        "legacy_source": None,
        "parser_version": "miit_formal_source + eidc_parser (MIIT)",
        "imported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_url": detail_url,
        "announcement_no": meta.get("announcement_no", ""),
        "publish_date": meta.get("publish_date", ""),
        "vehicle_tax_batch": meta.get("vehicle_tax_batch", ""),
        "purchase_tax_batch": meta.get("purchase_tax_batch", ""),
        "attachments": meta.get("attachments", []),
        "raw_product_rows": len(product_records),
        "notes": "gov_formal：miit.gov.cn 装备工业一司文件发布栏目的正式公告附件（source=miit_gov, stage=confirmed）",
    }


def run(batch: str, discovery_only: bool = False, no_download: bool = False,
        offline: bool = False, url: str = "") -> dict:
    batch_dir = miit_formal_batch_dir(batch)
    ensure_dir(batch_dir)
    ensure_dir(batch_dir / "attachments")
    ensure_dir(batch_dir / "attachment_text_src")

    # ── 1. 定位正式公告详情页（--url / --discover / 缓存）──
    detail_url = url or ""
    if not detail_url and not offline:
        found = src.discover_formal_notice(batch)
        if not found:
            print(f"batch {batch} 未在文件发布栏目发现正式公告（可用 --url 显式指定）")
            sys.exit(1)
        detail_url = found["source_url"]
        print(f"[0/5] discover: {found['title'][:50]} @ {detail_url}")
    if not detail_url:
        cached_meta = batch_dir / "raw_metadata.json"
        if cached_meta.exists():
            meta = json.loads(cached_meta.read_text())
            detail_url = meta.get("source_url", "")
            print(f"[0/5] offline: 复用缓存 raw_metadata.json（{detail_url}）")
        else:
            print("offline 无缓存且未指定 --url，无法定位公告页", file=sys.stderr)
            sys.exit(1)

    # ── 2. 抓取公告页 + 解析元数据 ──
    if offline and (batch_dir / "raw_metadata.json").exists():
        meta = json.loads((batch_dir / "raw_metadata.json").read_text())
        print(f"[1/5] offline: 复用缓存 raw_metadata.json")
        html = ""
    else:
        print(f"[1/5] fetch formal announcement: {detail_url}")
        html = src.fetch_formal_detail(detail_url)
        meta = src.parse_formal_metadata(html, detail_url)
        meta["batch_no"] = str(batch)
        meta["source"] = "miit_gov"
        meta["stage"] = "confirmed"
        meta["fetch_mode"] = "gov_formal"
        (batch_dir / "raw_metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2))
        (batch_dir / "raw_detail.html").write_text(html, encoding="utf-8")
        print(f"  title: {meta.get('title', '')[:60]}")
        print(f"  announcement_no: {meta.get('announcement_no', '')} | "
              f"publish: {meta.get('publish_date', '')}")
        print(f"  attachments: {len(meta.get('attachments', []))}")

    if discovery_only:
        print("\n[discovery-only] 完成，未下载附件")
        return meta

    # ── 3. 下载附件 + 转文本 ──
    print("[2/5] download attachments")
    for att in meta.get("attachments", []):
        doc_path = batch_dir / "attachments" / att["filename"]
        dl = src.download_attachment(att["url"], doc_path, force=False)
        att["download_status"] = dl["status"]
        att["sha256"] = dl.get("sha256", "")
        att["size"] = dl.get("size", 0)
        print(f"  {att['filename']}: {dl['status']} ({dl.get('sha256', '')[:10]}...)")

    print("[3/5] convert doc -> txt")
    for att in meta.get("attachments", []):
        doc_path = batch_dir / "attachments" / att["filename"]
        txt_path = batch_dir / "attachment_text_src" / att["filename"].replace(".doc", ".txt")
        if not doc_path.exists():
            continue
        try:
            conv = src.doc_to_txt(doc_path, txt_path)
            print(f"  {att['filename']}: {conv['status']}")
        except Exception as e:
            # textutil 失败（超大 .doc）→ olefile FIB 文本区提取（可选依赖）
            print(f"  ⚠ {att['filename']} textutil 失败: {str(e)[:80]}")
            if eidc_doc_extract is None:
                print("  ✗ olefile 未安装，无法备用提取（pip install olefile）")
                continue
            try:
                text = eidc_doc_extract.doc_to_txt_ole(doc_path)
                txt_path.write_text(text, encoding="utf-8")
                print(f"  {att['filename']}: olefile 提取 {len(text)} chars")
            except Exception as e2:
                print(f"  ✗ {att['filename']} olefile 亦失败: {str(e2)[:80]}")

    # ── 4. 解析 road 产品（附件1）──
    print("[4/5] parse road products")
    road_att = _find_road_attachment(meta)
    product_records = []
    if road_att:
        road_txt = (batch_dir / "attachment_text_src"
                    / road_att["filename"].replace(".doc", ".txt"))
        if road_txt.exists():
            text = road_txt.read_text(encoding="utf-8")
            product_records = eidc_parser.parse_road_products(text, batch)
    (batch_dir / "product_list.json").write_text(
        json.dumps(product_records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  road products: {len(product_records)}")

    # ── 5. import_manifest ──
    print("[5/5] write import_manifest")
    manifest = build_manifest(batch, meta, detail_url, product_records)
    (batch_dir / "import_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n完成: data/miit_formal/batch_{batch}/")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="MIIT Gov 正式公告 source 抓取/解析/归档")
    parser.add_argument("--batch", required=True, help="公告批次号（如 409）")
    parser.add_argument("--url", default="", help="正式公告详情页 URL（默认文件发布栏目搜索）")
    parser.add_argument("--discover", action="store_true", help="仅搜索定位公告页（不抓取）")
    parser.add_argument("--discovery-only", action="store_true",
                        help="抓取公告页元数据后停止，不下载附件")
    parser.add_argument("--no-download", action="store_true", help="跳过附件下载")
    parser.add_argument("--offline", action="store_true",
                        help="复用缓存 raw_metadata.json（网络不可用时）")
    args = parser.parse_args()

    if args.discover:
        found = src.discover_formal_notice(args.batch)
        if found:
            print(json.dumps(found, ensure_ascii=False, indent=2))
        else:
            print(f"batch {args.batch} 未发现正式公告")
            sys.exit(1)
        return

    run(args.batch, discovery_only=args.discovery_only,
        no_download=args.no_download, offline=args.offline, url=args.url)


if __name__ == "__main__":
    main()
