#!/usr/bin/env python3
"""
EIDC 401-408 fresh rebuild summary — 每批一张验收表（轻量）

每批输出：
  batch / announcement / raw_rows / valid_rate / passenger_source_rows / passenger_canonical_rows
  multi_brand / vehicle_tax_hit / purchase_tax_hit / schema_status

schema_status=REVIEW 才需深入附件。

用法:
  python3 scripts/eidc_summary_fresh.py
  python3 scripts/eidc_summary_fresh.py --batch 403
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from miit_paths import EIDC_DIR, VEHICLE_PARAMETERS_DIR  # noqa: E402
from eidc_parser import parse_road_products  # noqa: E402
from vehicle_record_builder import classify_source_record  # noqa: E402

RE_MODEL = re.compile(r'^[A-Z]{2,4}\d{2,}[A-Z0-9]{0,6}$')

BATCHES = [f"{i:03d}" for i in range(401, 409)]


def _road_text(bdir, manifest):
    for att in manifest.get("attachments", []):
        if "道路机动车辆" in att.get("title", ""):
            txt = bdir / "attachment_text_src" / att["filename"].replace(".doc", ".txt")
            if txt.exists():
                return txt
    return None


def summary_batch(batch: str, canonical_rows: dict[str, list[dict]]) -> dict:
    bdir = EIDC_DIR / f"batch_{batch}"
    manifest_path = bdir / "import_manifest.json"
    if not manifest_path.exists():
        return {"batch": batch, "schema_status": "REVIEW", "error": "no import_manifest"}
    manifest = json.loads(manifest_path.read_text())

    road_txt = _road_text(bdir, manifest)
    raw_rows = manifest.get("raw_product_rows", 0)
    valid = invalid = 0
    cat_full = Counter()
    if road_txt:
        recs = parse_road_products(road_txt.read_text(), batch)
        valid = sum(1 for r in recs if RE_MODEL.match(r["model_code_raw"]))
        invalid = len(recs) - valid
        for r in recs:
            if RE_MODEL.match(r["model_code_raw"]):
                c, _ = classify_source_record(r)
                cat_full[c] += 1

    # passenger source candidates（逐 record，含重复）
    pass_source = cat_full.get("passenger_vehicle", 0)
    if road_txt:
        pass_source_uniq = len({r["model_code_raw"] for r in
                                parse_road_products(road_txt.read_text(), batch)
                                if RE_MODEL.match(r["model_code_raw"])
                                and classify_source_record(r)[0] == "passenger_vehicle"})
    else:
        pass_source_uniq = 0

    # canonical passenger rows
    rows = canonical_rows.get(batch, [])
    n_canon = len(rows)
    multi_brand = sum(1 for r in rows if r.get("multi_brand_flag") == "1")
    vt_hit = sum(1 for r in rows if r.get("vehicle_tax_match_flag") == "1")
    pr_hit = sum(1 for r in rows if r.get("purchase_tax_match_flag") == "1")

    valid_rate = valid / raw_rows * 100 if raw_rows else 0

    # schema_status：road parser 正常 + 无异常 → OK；否则 REVIEW
    schema_status = "OK"
    issues = []
    if not road_txt or valid == 0:
        schema_status = "REVIEW"
        issues.append("road parser 产出 0 valid")
    if valid_rate < 90:
        schema_status = "REVIEW"
        issues.append(f"valid_rate={valid_rate:.1f}% < 90%")
    if n_canon == 0:
        schema_status = "REVIEW"
        issues.append("canonical passenger rows = 0")
    if n_canon != pass_source_uniq:
        schema_status = "REVIEW"
        issues.append(f"canonical({n_canon}) != passenger_source_uniq({pass_source_uniq})")

    return {
        "batch": batch,
        "announcement": manifest.get("announcement_no", ""),
        "publish_date": manifest.get("publish_date", ""),
        "raw_rows": raw_rows,
        "valid_rate": f"{valid_rate:.1f}%",
        "invalid_rows": invalid,
        "category_counts_full": dict(cat_full),
        "passenger_source_rows": pass_source,
        "passenger_source_uniq": pass_source_uniq,
        "passenger_canonical_rows": n_canon,
        "multi_brand": multi_brand,
        "vehicle_tax_hit": vt_hit,
        "purchase_tax_hit": pr_hit,
        "schema_status": schema_status,
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser(description="EIDC 401-408 fresh rebuild summary")
    parser.add_argument("--batch", default="")
    args = parser.parse_args()

    batches = [args.batch] if args.batch else BATCHES

    pm = []
    if VEHICLE_PARAMETERS_DIR.joinpath("product_master.csv").exists():
        with open(VEHICLE_PARAMETERS_DIR / "product_master.csv", encoding="utf-8") as f:
            pm = list(csv.DictReader(f))
    canonical_rows = {}
    for r in pm:
        canonical_rows.setdefault(r.get("batch_no"), []).append(r)

    print("=" * 100)
    print(f"{'batch':<6}{'announcement':<14}{'rows':>6}{'valid':>8}{'p_src':>6}{'p_uniq':>6}{'p_canon':>8}{'m_brand':>7}{'vt':>4}{'pt':>4}  status")
    print("-" * 100)
    results = []
    for b in batches:
        s = summary_batch(b, canonical_rows)
        results.append(s)
        print(f"{s['batch']:<6}{s['announcement']:<14}{s['raw_rows']:>6}{s['valid_rate']:>8}"
              f"{s['passenger_source_rows']:>6}{s['passenger_source_uniq']:>6}{s['passenger_canonical_rows']:>8}"
              f"{s['multi_brand']:>7}{s['vehicle_tax_hit']:>4}{s['purchase_tax_hit']:>4}  {s['schema_status']}")
        if s["issues"]:
            for i in s["issues"]:
                print(f"       ⚠ {i}")

    print("-" * 100)
    n_review = sum(1 for s in results if s["schema_status"] == "REVIEW")
    print(f"schema_status: {len(results)-n_review} OK / {n_review} REVIEW")
    print("=" * 100)


if __name__ == "__main__":
    main()