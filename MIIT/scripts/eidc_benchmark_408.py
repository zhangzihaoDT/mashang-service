#!/usr/bin/env python3
"""
EIDC 408 Benchmark — 验证 EIDC confirmed source adapter 进入 canonical 链路

基准拆成两块（Task §10）：
  A. Source Health — 全量（验证 parser 没有漏掉官方数据）
       raw rows / valid rate / invalid rows / category distribution / attachment status
  B. Passenger Business Health — 仅乘用车
       passenger rows / unique model_code / duplicate groups / multi_enterprise / multi_brand
       vehicle_tax_match / purchase_tax_match / 参数 coverage / legacy reconciliation / canonical count

数据来源：
  - data/eidc/batch_408/import_manifest.json
  - data/eidc/batch_408/attachment_text_src/{road txt}（按附件 title 选路）
  - data/vehicle_tax/车型清单_第{N}批车船税.json
  - data/vehicle_tax/车型清单_第{N}批购置税.json
  - data/vehicle_parameters/product_master.csv + vehicle_parameter.csv

用法:
  python3 scripts/eidc_benchmark_408.py
"""

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from miit_paths import EIDC_DIR, VEHICLE_PARAMETERS_DIR, VEHICLE_TAX_DIR  # noqa: E402
from eidc_parser import parse_road_products  # noqa: E402
from vehicle_record_builder import classify_source_record  # noqa: E402

RE_MODEL = re.compile(r'^[A-Z]{2,4}\d{2,}[A-Z0-9]{0,6}$')

BATCH = "408"


def _load_road_text(bdir: Path, manifest: dict) -> Path | None:
    """从 import_manifest 中找道路机动车辆附件对应的 txt。"""
    for att in manifest.get("attachments", []):
        if "道路机动车辆" in att.get("title", ""):
            txt = bdir / "attachment_text_src" / att["filename"].replace(".doc", ".txt")
            if txt.exists():
                return txt
    return None


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    bdir = EIDC_DIR / f"batch_{BATCH}"
    manifest = json.loads((bdir / "import_manifest.json").read_text())
    road_txt = _load_road_text(bdir, manifest)

    print("=" * 64)
    print(f"EIDC {BATCH} Benchmark")
    print("=" * 64)

    # ══════════════ A. Source Health — 全量 ══════════════
    print("\n" + "═" * 64)
    print("A. Source Health (full regulatory universe)")
    print("═" * 64)

    # ── A1. Source ──
    print("\n[A1] Source")
    print(f"  source_url:       {manifest.get('source_url')}")
    print(f"  announcement_no:  {manifest.get('announcement_no')}")
    print(f"  publish_date:     {manifest.get('publish_date')}")
    print(f"  fetch_mode:       {manifest.get('fetch_mode')}")
    print(f"  vehicle_tax_batch:{manifest.get('vehicle_tax_batch')}")
    print(f"  purchase_tax_batch:{manifest.get('purchase_tax_batch')}")
    print(f"  attachments:      {len(manifest.get('attachments', []))}")
    for att in manifest.get("attachments", []):
        print(f"    - {att.get('title')} ({att.get('download_status')}, sha256={att.get('sha256','')[:10]}..., size={att.get('size',0)})")
    print(f"  raw_product_rows: {manifest.get('raw_product_rows')}")

    if not road_txt:
        print("\n[error] road txt 未找到，benchmark 中止")
        sys.exit(1)
    print(f"  road_txt:         {road_txt.name}")

    # ── A2. Full Identity + category distribution ──
    print("\n[A2] Full source identity & category")
    recs = parse_road_products(road_txt.read_text(), BATCH)
    valid = [r for r in recs if RE_MODEL.match(r["model_code_raw"])]
    invalid = [r for r in recs if not RE_MODEL.match(r["model_code_raw"])]
    uniq = {r["model_code_raw"] for r in valid}
    dup = {m for m, c in Counter(r["model_code_raw"] for r in valid).items() if c > 1}
    print(f"  raw rows:          {len(recs)}")
    print(f"  valid model_code:  {len(valid)}")
    print(f"  invalid rows:      {len(invalid)} （含空型号 / 表头残留）")
    print(f"  unique model_code: {len(uniq)}")
    print(f"  dup model_code:    {len(dup)} （同一型号多企业/多产品名申报）")

    # 全量 category distribution（验证 parser 没漏官方数据）
    cat_cnt = Counter()
    for r in valid:
        cat, _sub = classify_source_record(r)
        cat_cnt[cat] += 1
    print(f"  category_counts (full): {dict(cat_cnt.most_common())}")

    if invalid:
        sample_invalid = [r for r in invalid if r["model_code_raw"] or r["manufacturer_raw"]][:3]
        print(f"  invalid 样本(前3):")
        for r in sample_invalid:
            print(f"    - manu={r['manufacturer_raw'][:30]} brand={r['brand_raw']} model='{r['model_code_raw']}'")

    # ══════════════ B. Passenger Business Health — 仅乘用车 ══════════════
    print("\n" + "═" * 64)
    print("B. Passenger Business Health (canonical scope)")
    print("═" * 64)

    pm = _read_csv(VEHICLE_PARAMETERS_DIR / "product_master.csv")
    vp = _read_csv(VEHICLE_PARAMETERS_DIR / "vehicle_parameter.csv")
    pm_408 = [r for r in pm if r.get("batch_no") == BATCH and r.get("source") == "eidc"]
    vp_408 = [r for r in vp if r.get("batch_no") == BATCH and r.get("source") == "eidc"]

    # ── B1. Canonical scope ──
    print("\n[B1] Canonical (passenger scope gate)")
    obs_ids = [r["observation_id"] for r in pm_408]
    vids = [r["vehicle_record_id"] for r in pm_408]
    canonical_mc = {v.split(":", 1)[1] for v in vids if ":" in v}
    print(f"  product_master 408 eidc rows: {len(pm_408)}")
    print(f"  vehicle_parameter 408 eidc rows: {len(vp_408)}")
    print(f"  stage=confirmed: {sum(1 for r in pm_408 if r.get('stage')=='confirmed')}")
    print(f"  observation_id unique: {len(set(obs_ids)) == len(obs_ids)} ({len(set(obs_ids))}/{len(obs_ids)})")
    print(f"  vehicle_record_id unique: {len(set(vids)) == len(vids)} ({len(set(vids))}/{len(vids)})")
    print(f"  all passenger: {all(r.get('vehicle_category')=='passenger_vehicle' for r in pm_408)}")
    print(f"  all in_scope:  {all(r.get('analysis_scope')=='in_scope' for r in pm_408)}")
    print(f"  record_quality: {dict(Counter(r.get('record_quality') for r in pm_408))}")

    # ── B2. Passenger identity ──
    print("\n[B2] Passenger identity")
    pass_recs = [r for r in valid if classify_source_record(r)[0] == "passenger_vehicle"]
    pass_uniq = {r["model_code_raw"] for r in pass_recs}
    print(f"  passenger source candidates: {len(pass_recs)} records / {len(pass_uniq)} unique model_code")
    print(f"  canonical passenger rows: {len(pm_408)}")
    print(f"  passenger unique vs canonical diff: {len(pass_uniq ^ canonical_mc)}")

    # ── B3. Passenger duplicate / multi markers ──
    print("\n[B3] Passenger duplicate & multi-enterprise/multi-brand")
    print(f"  multi_enterprise_count: {dict(Counter(r.get('multi_enterprise_count') for r in pm_408))}")
    print(f"  multi_brand_flag:        {dict(Counter(r.get('multi_brand_flag') for r in pm_408))}")
    multi_brand_rows = [r for r in pm_408 if r.get("multi_brand_flag") == "1"]
    if multi_brand_rows:
        print(f"  multi_brand rows ({len(multi_brand_rows)}):")
        for r in multi_brand_rows:
            print(f"    {r['model_code']:14s} brand={r['brand']:8s} manufacturer={r['manufacturer'][:32]:32s} ent_count={r['multi_enterprise_count']}")

    # ── B4. Regulatory enrichment（passenger 母体） ──
    print("\n[B4] Regulatory enrichment (passenger 母体)")
    vt_match = sum(1 for r in pm_408 if r.get("vehicle_tax_match_flag") == "1")
    pr_match = sum(1 for r in pm_408 if r.get("purchase_tax_match_flag") == "1")
    either = sum(1 for r in pm_408 if r.get("vehicle_tax_match_flag") == "1" or r.get("purchase_tax_match_flag") == "1")
    both = sum(1 for r in pm_408 if r.get("vehicle_tax_match_flag") == "1" and r.get("purchase_tax_match_flag") == "1")
    print(f"  passenger rows: {len(pm_408)}")
    print(f"  vehicle_tax hit: {vt_match} ({vt_match*100//len(pm_408)}%)")
    print(f"  purchase_tax hit: {pr_match} ({pr_match*100//len(pm_408)}%)")
    print(f"  either: {either} | both: {both}")

    # ── B5. Passenger 参数 coverage ──
    print("\n[B5] Passenger 参数 coverage")
    fields = ["common_name", "energy_type", "curb_weight_kg", "battery_capacity_kwh", "ev_range_km"]
    for f in fields:
        n = sum(1 for r in vp_408 if (r.get(f) or "").strip())
        print(f"    {f:22s}: {n:4d} ({n*100//len(vp_408)}%)")
    nev = [r for r in vp_408 if r.get("vehicle_tax_match_flag") == "1" or r.get("purchase_tax_match_flag") == "1"]
    if nev:
        bc = sum(1 for r in nev if r.get("battery_capacity_kwh"))
        rg = sum(1 for r in nev if r.get("ev_range_km"))
        print(f"    NEV passenger hit={len(nev)}: battery_capacity={bc} ev_range={rg}")

    # ── B6. Legacy reconciliation ──
    print("\n[B6] Legacy reconciliation")
    legacy_path = bdir / "legacy" / "legacy_product_list.json"
    if legacy_path.exists():
        legacy = json.loads(legacy_path.read_text())
        legacy_recs = legacy.get("records", []) if isinstance(legacy, dict) else legacy
        legacy_short = {r.get("product_model", "").strip() for r in legacy_recs
                        if (r.get("product_model") or "").strip()}
        print(f"  legacy 408 records: {len(legacy_recs)} (公示期 product_list, 短型号 {legacy_short})")
        print(f"  口径不同 (公示 html_table vs 正式公告), 仅作历史参考")
    else:
        print("  (无 legacy 408 evidence)")

    print("\n" + "=" * 64)
    print("Benchmark done")


if __name__ == "__main__":
    main()