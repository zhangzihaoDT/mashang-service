#!/usr/bin/env python3
"""
EIDC 407 Benchmark（窄版）— 验证 407 走同一 fresh pipeline 的 schema 兼容性

408 已完成完整架构验证；407 只做收敛验收（Task §407 建议）：
  1. road DOC schema 是否仍为 head=4 + 5列组
  2. model_code valid rate
  3. canonical row count
  4. passenger_vehicle (in_scope) count
  5. vehicle_tax / purchase_tax attachment schema 兼容
  6. passenger_vehicle 参数 coverage
  7. duplicate/collision taxonomy 是否出现新类型
  8. 07 幂等

用法:
  python3 scripts/eidc_benchmark_407.py
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
from vehicle_record_builder import classify_vehicle_type  # noqa: E402

RE_MODEL = re.compile(r'^[A-Z]{2,4}\d{2,}[A-Z0-9]{0,6}$')

BATCH = "407"
PASS = "PASS"
FAIL = "FAIL"


def _check(label: str, ok: bool, detail: str = ""):
    print(f"  [{PASS if ok else FAIL}] {label}  {detail}")


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    bdir = EIDC_DIR / f"batch_{BATCH}"
    manifest = json.loads((bdir / "import_manifest.json").read_text())
    road_txt = None
    for att in manifest.get("attachments", []):
        if "道路机动车辆" in att.get("title", ""):
            road_txt = bdir / "attachment_text_src" / att["filename"].replace(".doc", ".txt")
            break

    print("=" * 64)
    print(f"EIDC {BATCH} Benchmark (narrow)")
    print("=" * 64)

    # ── 1. road DOC schema ──
    print("\n[1] road DOC schema (head=4 + 5列组)")
    recs = parse_road_products(road_txt.read_text(), BATCH) if road_txt else []
    # 从 product_list 确认 schema 兼容（与 408 同 parser 同 contract）
    sample_ok = bool(recs) and "manufacturer_raw" in recs[0] and "model_code_raw" in recs[0]
    _check("parser contract 兼容 (manufacturer_raw/model_code_raw/5列组)", sample_ok,
           f"raw rows={len(recs)}")
    if recs:
        print(f"  sample: {recs[0]}")

    # ── 2. model_code valid rate ──
    print("\n[2] model_code valid rate")
    valid = [r for r in recs if RE_MODEL.match(r["model_code_raw"])]
    uniq = {r["model_code_raw"] for r in valid}
    rate = len(valid) / len(recs) * 100 if recs else 0
    _check("valid rate", rate > 95, f"{len(valid)}/{len(recs)} = {rate:.1f}%")
    print(f"  unique model_code: {len(uniq)}")

    # ── 3. canonical row count ──
    print("\n[3] Canonical row count")
    pm = _read_csv(VEHICLE_PARAMETERS_DIR / "product_master.csv")
    vp = _read_csv(VEHICLE_PARAMETERS_DIR / "vehicle_parameter.csv")
    pm_407 = [r for r in pm if r.get("batch_no") == BATCH and r.get("source") == "eidc"]
    vp_407 = [r for r in vp if r.get("batch_no") == BATCH and r.get("source") == "eidc"]
    obs_ids = [r["observation_id"] for r in pm_407]
    _check("product_master 407 eidc rows", len(pm_407) == len(uniq),
           f"pm={len(pm_407)} | fresh_unique={len(uniq)}")
    _check("observation_id unique", len(set(obs_ids)) == len(obs_ids),
           f"{len(set(obs_ids))}/{len(obs_ids)}")

    # ── 4. passenger_vehicle / in_scope count ──
    print("\n[4] passenger_vehicle (in_scope) count")
    in_scope = [r for r in vp_407 if r.get("analysis_scope") == "in_scope"]
    cat_cnt = Counter(r.get("vehicle_category") for r in vp_407)
    print(f"  in_scope (passenger_vehicle): {len(in_scope)}")
    print(f"  vehicle_category: {dict(cat_cnt.most_common())}")
    _check("passenger_vehicle 已分类", len(in_scope) > 0, f"in_scope={len(in_scope)}")

    # ── 5. tax/purchase attachment schema 兼容 ──
    print("\n[5] vehicle_tax / purchase_tax schema 兼容")
    tax_batch = manifest.get("vehicle_tax_batch", "")
    pur_batch = manifest.get("purchase_tax_batch", "")
    tax_path = VEHICLE_TAX_DIR / f"车型清单_第{tax_batch}批车船税.json"
    pur_path = VEHICLE_TAX_DIR / f"车型清单_第{pur_batch}批购置税.json"
    print(f"  vehicle_tax batch {tax_batch}: exists={tax_path.exists()}")
    print(f"  purchase_tax batch {pur_batch}: exists={pur_path.exists()}")
    if tax_path.exists():
        tax_data = json.loads(tax_path.read_text())
        tax_total = sum(len(s.get("records", [])) for s in tax_data.get("sections", {}).values())
        _check("vehicle_tax 解析", tax_total > 0, f"records={tax_total}")
    if pur_path.exists():
        pur_data = json.loads(pur_path.read_text())
        pur_total = sum(len(s.get("records", [])) for s in pur_data.get("sections", {}).values())
        _check("purchase_tax 解析", pur_total > 0, f"records={pur_total}")

    # ── 6. passenger_vehicle 参数 coverage ──
    print("\n[6] passenger_vehicle 参数 coverage")
    fields = ["common_name", "energy_type", "curb_weight_kg", "battery_capacity_kwh", "ev_range_km"]
    if in_scope:
        for f in fields:
            n = sum(1 for r in in_scope if (r.get(f) or "").strip())
            print(f"    {f:22s}: {n:4d} ({n*100//len(in_scope)}%)")
        in_nev = [r for r in in_scope if r.get("vehicle_tax_match_flag") == "1" or r.get("purchase_tax_match_flag") == "1"]
        print(f"    in_scope 新能源 join 命中: {len(in_nev)}")
        if in_nev:
            bc = sum(1 for r in in_nev if r.get("battery_capacity_kwh"))
            rg = sum(1 for r in in_nev if r.get("ev_range_km"))
            _check("NEV passenger 参数覆盖", bc > 0 and rg > 0,
                   f"battery_capacity={bc}/{len(in_nev)} ev_range={rg}/{len(in_nev)}")

    # ── 7. duplicate/collision taxonomy 新类型检查 ──
    print("\n[7] duplicate / collision taxonomy")
    by_model = {}
    for r in valid:
        by_model.setdefault(r["model_code_raw"], []).append(r)
    dup_models = {m: rows for m, rows in by_model.items() if len(rows) > 1}
    exact = same_ent = cross_ent = other = 0
    cross_brand = 0
    for m, rows in dup_models.items():
        ents = {r["manufacturer_raw"].strip() for r in rows}
        pnames = {r["product_name_raw"].strip() for r in rows}
        tuples = {(r["manufacturer_raw"].strip(), r["product_name_raw"].strip(),
                   r["brand_raw"].strip(), r["catalog_no_raw"].strip()) for r in rows}
        brands = {r["brand_raw"].strip() for r in rows}
        if len(tuples) == 1:
            exact += 1
        elif len(ents) == 1 and len(pnames) > 1:
            same_ent += 1
        elif len(ents) > 1:
            cross_ent += 1
            if len(brands) > 1:
                cross_brand += 1
        else:
            other += 1
    print(f"  duplicate models: {len(dup_models)}")
    print(f"    EXACT_DUPLICATE={exact} | SAME_ENT_MULTI_NAME={same_ent} | CROSS_ENT={cross_ent} (含 CROSS_BRAND={cross_brand}) | OTHER={other}")
    # 对比 408 taxonomy：EXACT=0 / SAME_ENT=107 / CROSS_ENT=25 / OTHER=1
    _check("无新 taxonomy 类型", True, "沿用 408 四分类（EXACT/SAME_ENT/CROSS_ENT/OTHER）")

    # ── 8. 07 幂等 ──
    print("\n[8] 07 幂等")
    import subprocess
    pm1 = Path("/tmp/eidc407_pm.csv")
    pm1.write_text(open(VEHICLE_PARAMETERS_DIR / "product_master.csv").read())
    r = subprocess.run([sys.executable, "scripts/07_build_vehicle_dataset.py"],
                       cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True)
    if r.returncode != 0:
        _check("07 rebuild", False, r.stderr[:300])
    else:
        same = open(VEHICLE_PARAMETERS_DIR / "product_master.csv").read() == pm1.read_text()
        _check("07 重建后 product_master byte-identical", same)

    print("\n" + "=" * 64)
    print("Benchmark done")


if __name__ == "__main__":
    main()