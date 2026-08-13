#!/usr/bin/env python3
"""
MIIT Pipeline P4.5: 统一 Dataset 构建器（canonical 目标层）

从已归档批次构建两张规范表，统一落 data/vehicle_parameters/：

- product_master    一车型一行（身份 vehicle_record_id = {batch_no}:{model_code}）
- vehicle_parameter 一车型一行（身份同上）

**Canonical Eligibility（scope gate）**：
  model_code valid
  AND vehicle_category == passenger_vehicle

Source / Parser 层保留全量道路机动车辆；data/vehicle_parameters/ 只保留乘用车业务 canonical
records。Gov（miit_gov/proposed）与 EIDC（eidc/confirmed）两条 branch 共用同一 scope gate
（vehicle_record_builder.is_canonical_in_scope）。非乘用车不进入本层，但完整保留在 source archive。

数据来源（与 04 宽表同源，但去配置展开、一车型一行）：
  P1 scan（search_results/scan_batch_XXX.md）→ 身份字段
  P2 详情页（vehicle_details/）→ 尺寸/电池/电机/供应商/座位
  P3 车船税（vehicle_tax/）→ 容量/续航/整备/通用名称
  workflow/model_name_map.json → 车船税缺失车型的通用名称补充

领域逻辑统一来自 vehicle_record_builder（与 04 宽表共用）。

用法:
  python3 scripts/07_build_vehicle_dataset.py                      # 构建全部批次（默认输出 canonical 层）
  python3 scripts/07_build_vehicle_dataset.py --batch 410 --output-dir 自定义目录   # 只构建单批（隔离输出，避免覆盖全量）
"""

import json
import csv
import argparse
import re
import sys
from pathlib import Path

from miit_paths import (  # noqa: E402
    VEHICLE_PARAMETERS_DIR,
    VEHICLE_TAX_DIR,
    EIDC_DIR,
    load_batches,
    scan_path,
    tax_json_path,
    vehicle_record_id,
    get_batch_config,
    ensure_dir,
)
from vehicle_record_builder import (  # noqa: E402
    parse_scan_md,
    load_tax_index,
    read_brand_md,
    build_record,
    build_eidc_record,
    match_eidc_enrichment,
    classify_source_record,
    is_canonical_in_scope,
    CANONICAL_VEHICLE_CATEGORY,
    derive_metrics,
    resolve_name,
)
from report_common import load_name_map  # noqa: E402

MIIT_URL_BASE = "https://www.miit.gov.cn"

# Gov 公示批次（409/410 当前）→ proposed 观测；EIDC 历史（401-408）→ confirmed
GOV_SOURCE = "miit_gov"
GOV_STAGE = "proposed"
EIDC_SOURCE = "eidc"
EIDC_STAGE = "confirmed"

# 登记的 Gov 批次（batches.yaml）与 EIDC 归档批次（data/eidc/）自动合并
EIDC_BATCHES = [f"{b:03d}" for b in range(401, 409)]

MASTER_COLUMNS = [
    "vehicle_record_id", "observation_id", "batch_no", "model_code",
    "brand", "manufacturer", "product_name", "common_name",
    "detail_url", "publish_date", "source", "stage",
    "record_quality",
    # vehicle type classification (derived dimension, not identity)
    "source_vehicle_type", "vehicle_category", "vehicle_subcategory", "analysis_scope",
    # EIDC official structure evidence
    # catalog_no = 目录序号；source_section = 最近捕获的官方分节标题。
    # ⚠ source_section 对第一部分（新产品）混排产品不可靠：摩托车/底盘/起重机等
    #   共享"一、汽车生产企业"下稀疏标题，仅作位置 evidence，分类请用 vehicle_category。
    "catalog_no", "source_section",
    # regulatory attachment join flags (independent of field coverage)
    "vehicle_tax_match_flag", "purchase_tax_match_flag",
    # multi-enterprise / multi-brand markers (from duplicate_model_code_audit)
    "multi_enterprise_count", "multi_brand_flag",
    # legacy compatibility alias (deprecated, kept for downstream consumers)
    "tax_catalog_match_flag",
]

PARAM_COLUMNS = [
    "vehicle_record_id", "observation_id", "batch_no", "model_code",
    "brand", "common_name", "energy_type",
    "source", "stage", "record_quality",
    # vehicle type classification (derived dimension, not identity)
    "source_vehicle_type", "vehicle_category", "vehicle_subcategory", "analysis_scope",
    # EIDC official structure evidence
    # catalog_no = 目录序号；source_section = 最近捕获的官方分节标题。
    # ⚠ source_section 对第一部分（新产品）混排产品不可靠：摩托车/底盘/起重机等
    #   共享"一、汽车生产企业"下稀疏标题，仅作位置 evidence，分类请用 vehicle_category。
    "catalog_no", "source_section",
    # 尺寸
    "length_mm", "width_mm", "height_mm", "wheelbase_mm",
    # 质量 / 电池
    "curb_weight_kg", "curb_weight_num",
    "battery_capacity_kwh", "battery_capacity_num",
    "battery_mass_kg", "battery_mass_num",
    "ev_range_km", "ev_range_num",
    "battery_type", "battery_chemistry", "battery_chemistry_cn",
    # 电机
    "motor_power_kw", "motor_count", "motor_total_peak_kw", "single_multi_motor",
    # 供应链
    "cell_supplier", "pack_supplier",
    "cell_supplier_group", "pack_supplier_group", "vertical_integration_flag",
    # 增程 / 座位
    "range_extender", "seat_count",
    # 衍生指标
    "approx_energy_consumption_kwh_100km", "battery_energy_density_wh_kg",
    "km_per_kwh", "battery_mass_ratio_pct",
    # 质量
    "variant_count",
    # regulatory attachment join flags (independent of field coverage)
    "vehicle_tax_match_flag", "purchase_tax_match_flag",
    "metric_scope",
    "source_detail", "source_tax",
]


def parse_scan_models(path: Path) -> list[dict]:
    """从 scan md 内嵌 JSON 提取车型行（含 detail_url）。"""
    return parse_scan_md(path)


def _multi_count(*values: str) -> int:
    """多值字段的配置版本数（按 '/' 分隔），无多值返回 1。"""
    n = 1
    for v in values:
        if v and "/" in v:
            n = max(n, len(v.split("/")))
    return n


def _seat_count(md: dict | None) -> str:
    for key in ("额定载客（含驾驶员）（座位数）", "额定载客(人)", "额定载客（人）"):
        v = (md or {}).get(key, "")
        if v:
            m = re.search(r'\d+', str(v))
            if m:
                return m.group()
    return ""


def _wheelbase(md: dict | None) -> str:
    for key in ("轴距(mm)", "轴距"):
        v = (md or {}).get(key, "")
        if v:
            m = re.search(r'\d+', str(v))
            if m:
                return m.group()
    return ""


def build_rows(batch: str, name_map: dict) -> tuple[list[dict], list[dict]]:
    cfg = get_batch_config(batch)
    models = parse_scan_models(scan_path(batch))
    tax_index = load_tax_index(tax_json_path(batch))

    master_rows, param_rows = [], []
    for m in models:
        mid = m["model_id"]
        md = read_brand_md(m["brand"], mid, batch)
        tax = tax_index.get(mid, {})
        rec = build_record(m, md, tax)

        # canonical scope gate：仅乘用车进入 canonical（Gov/EIDC 同一规则）
        if not is_canonical_in_scope(rec):
            continue

        vid = vehicle_record_id(batch, mid)

        common_name = resolve_name(tax, mid, name_map)

        tax_match = rec.get("tax_catalog_match_flag", "0")

        publish_date = cfg.get("notice_date", "")
        if not isinstance(publish_date, str):
            publish_date = str(publish_date)

        detail_url = m.get("detail_url", "")
        if detail_url and not detail_url.startswith("http"):
            detail_url = MIIT_URL_BASE + detail_url

        master_rows.append({
            "vehicle_record_id": vid,
            "observation_id": f"{vid}:{GOV_STAGE}",
            "batch_no": batch,
            "model_code": mid,
            "brand": m["brand"],
            "manufacturer": m["enterprise_name"],
            "product_name": m["product_name"],
            "common_name": common_name,
            "detail_url": detail_url,
            "publish_date": publish_date,
            "source": GOV_SOURCE,
            "stage": GOV_STAGE,
            "record_quality": "high",
            # vehicle type classification
            "source_vehicle_type": rec.get("source_vehicle_type", ""),
            "vehicle_category": rec.get("vehicle_category", ""),
            "vehicle_subcategory": rec.get("vehicle_subcategory", ""),
            "analysis_scope": rec.get("analysis_scope", "out_of_scope"),
            "catalog_no": rec.get("catalog_no", ""),
            "source_section": "",
            # Gov 公示 batch 已附 P3 车船税 → vehicle_tax_match_flag = tax_match
            "vehicle_tax_match_flag": tax_match,
            "purchase_tax_match_flag": "0",
            # Gov 公示 P1 scan 一行一车型，无重复 view
            "multi_enterprise_count": "1",
            "multi_brand_flag": "0",
            "tax_catalog_match_flag": tax_match,
        })

        # 衍生指标（首值口径，多值字段保留原始串）
        derive_metrics(rec)

        tax_section = tax.get("_tax_section", "")

        param_rows.append({
            "vehicle_record_id": vid,
            "observation_id": f"{vid}:{GOV_STAGE}",
            "batch_no": batch,
            "model_code": mid,
            "brand": m["brand"],
            "common_name": common_name,
            "energy_type": rec.get("动力形式", ""),
            "source": GOV_SOURCE,
            "stage": GOV_STAGE,
            "record_quality": "high",
            "length_mm": rec.get("长(mm)", ""),
            "width_mm": rec.get("宽(mm)", ""),
            "height_mm": rec.get("高(mm)", ""),
            "wheelbase_mm": _wheelbase(md),
            # vehicle type classification (param table)
            "source_vehicle_type": rec.get("source_vehicle_type", ""),
            "vehicle_category": rec.get("vehicle_category", ""),
            "vehicle_subcategory": rec.get("vehicle_subcategory", ""),
            "analysis_scope": rec.get("analysis_scope", "out_of_scope"),
            "catalog_no": rec.get("catalog_no", ""),
            "source_section": "",
            "curb_weight_kg": rec.get("整备质量(kg)", ""),
            "curb_weight_num": rec.get("整备质量_num", ""),
            "battery_capacity_kwh": rec.get("电池容量(kWh)", ""),
            "battery_capacity_num": rec.get("电池容量_num", ""),
            "battery_mass_kg": rec.get("电池质量(kg)", ""),
            "battery_mass_num": rec.get("电池质量_num", ""),
            "ev_range_km": rec.get("纯电续航(km)", ""),
            "ev_range_num": rec.get("纯电续航_num", ""),
            "battery_type": rec.get("电池类型", ""),
            "battery_chemistry": rec.get("battery_chemistry", ""),
            "battery_chemistry_cn": rec.get("battery_chemistry_cn", ""),
            "motor_power_kw": rec.get("电机功率(kW)", ""),
            "motor_count": rec.get("motor_count", ""),
            "motor_total_peak_kw": rec.get("motor_total_peak_kw", ""),
            "single_multi_motor": rec.get("single_multi_motor", ""),
            "cell_supplier": rec.get("cell_supplier", ""),
            "pack_supplier": rec.get("pack_supplier", ""),
            "cell_supplier_group": rec.get("cell_supplier_group", ""),
            "pack_supplier_group": rec.get("pack_supplier_group", ""),
            "vertical_integration_flag": rec.get("vertical_integration_flag", ""),
            "range_extender": rec.get("增程器", ""),
            "seat_count": _seat_count(md),
            "approx_energy_consumption_kwh_100km": rec.get("总电量口径近似电耗(kWh/100km)", ""),
            "battery_energy_density_wh_kg": rec.get("电池包能量密度(Wh/kg)", ""),
            "km_per_kwh": rec.get("单位电量续航(km/kWh)", ""),
            "battery_mass_ratio_pct": rec.get("电池质量占整备质量比(%)", ""),
            "variant_count": _multi_count(
                rec.get("电池容量(kWh)", ""), rec.get("电池质量(kg)", ""),
                rec.get("纯电续航(km)", ""), rec.get("整备质量(kg)", "")),
            "vehicle_tax_match_flag": tax_match,
            "purchase_tax_match_flag": "0",
            "metric_scope": rec.get("metric_scope", ""),
            "source_detail": (md or {}).get("_md_file", "") if md else "",
            "source_tax": tax_section,
        })
    return master_rows, param_rows


def _load_eidc_tax_purchase_index(batch: str, manifest: dict) -> tuple[dict, dict]:
    """读取 EIDC 批次的 vehicle_tax / purchase_tax 索引。

    由 manifest 的 vehicle_tax_batch / purchase_tax_batch 字段决定文件路径；
    支持逗号分隔多批次（如 402 的购置税"第二十五、二十六批" → "25,26"）。
    回落到 VEHICLE_TAX_DIR/车型清单_第{N}批{车船税|购置税}.json。
    """
    tax_index, purchase_index = {}, {}

    def _load(batch_nos: str, suffix: str, mid_key, idx: dict, sec_attr: str):
        for nb in [x for x in (batch_nos or "").replace("，", ",").split(",") if x.strip()]:
            path = VEHICLE_TAX_DIR / f"车型清单_第{nb}批{suffix}.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text())
            for sec_name, sec in data.get("sections", {}).items():
                for rec in sec.get("records", []):
                    mid = rec.get("产品型号", "") or rec.get("车辆型号", "")
                    if mid and mid not in idx:
                        rec_with_sec = dict(rec)
                        rec_with_sec[sec_attr] = sec_name
                        idx[mid] = rec_with_sec

    _load(manifest.get("vehicle_tax_batch", ""), "车船税",
          None, tax_index, "_tax_section")
    _load(manifest.get("purchase_tax_batch", ""), "购置税",
          None, purchase_index, "_purchase_section")
    return tax_index, purchase_index


def build_eidc_rows(batch: str) -> tuple[list[dict], list[dict]]:
    """从 data/eidc/batch_{N}/product_list.json 构建 EIDC confirmed 行。

    EIDC source record（eidc_parser 产出）→ vehicle_record_builder.build_eidc_record
    → canonical 行（source=eidc, stage=confirmed）。
    流程（scope gate 提前，enrichment 只对 passenger）：
      product_list → normalize model_code → classify source record
      → passenger scope gate → tax/purchase enrichment → build_eidc_record → canonical
    只有 model_code_valid=true AND vehicle_category==passenger_vehicle 才生成主键；
    非乘用车 / 非法型号仅留 source evidence（不进入 canonical）。

    ⚠ 架构约束（passenger eligibility 是 source-record 级 existential）：
      gate 必须在聚合（by model_code）之前、逐 source record 执行。
      同一 batch:model_code 只要存在至少一条合法 passenger_vehicle source record，
      该 vehicle record 即进入 passenger canonical；非乘用变体仍留在 source evidence。
      不得把 gate 移到聚合之后按"首条记录分类"判定——那会漏掉
      同 chassis 多车型（旅居车/商务车 + 专用车）的乘用变体（如 407:KLF5040X）。
    """
    pl_path = EIDC_DIR / f"batch_{batch}" / "product_list.json"
    if not pl_path.exists():
        return [], []

    manifest = {}
    mpath = EIDC_DIR / f"batch_{batch}" / "import_manifest.json"
    if mpath.exists():
        manifest = json.loads(mpath.read_text())

    source_records = json.loads(pl_path.read_text())
    # fresh（eidc_parser 产出，数组，`*_raw` contract）
    source_records = list(source_records)

    # 第一步：normalize model_code + classify source record + passenger gate
    # （在 enrichment / build 之前完成轻量分类，非乘用车不再走深度匹配）
    passenger_records: list[tuple[str, dict]] = []
    from vehicle_record_builder import normalize_model_code  # noqa: E402
    for sr in source_records:
        raw_model = sr.get("model_code_raw") or sr.get("model_code") or ""
        _mc, valid = normalize_model_code(raw_model)
        if not valid:
            continue
        cat, _sub = classify_source_record(sr)
        if cat != CANONICAL_VEHICLE_CATEGORY:
            continue
        passenger_records.append((_mc, sr))

    # 第二遍：按 model_code 聚合 passenger source records（保留共号 evidence）
    by_model: dict[str, list[dict]] = {}
    for _mc, sr in passenger_records:
        by_model.setdefault(_mc, []).append(sr)

    tax_index, purchase_index = _load_eidc_tax_purchase_index(batch, manifest)

    master_rows, param_rows = [], []

    for mid, sr_group in by_model.items():
        # 主记录：首条申报；其余合并 product_name / 标记 multi_enterprise / multi_brand
        first = sr_group[0]
        if tax_index or purchase_index:
            tax_rec, pur_rec = match_eidc_enrichment(mid, tax_index, purchase_index)
        else:
            tax_rec, pur_rec = {}, {}
        rec = build_eidc_record(first, tax_rec, pur_rec)

        # 多企业/多品牌聚合
        ents = sorted({(sr.get("manufacturer_raw") or sr.get("enterprise_name") or "").strip()
                       for sr in sr_group if (sr.get("manufacturer_raw") or sr.get("enterprise_name") or "").strip()})
        brands = sorted({(sr.get("brand_raw") or sr.get("brand") or "").replace("牌", "").strip()
                          for sr in sr_group if (sr.get("brand_raw") or sr.get("brand") or "").strip()})
        pnames = sorted({(sr.get("product_name_raw") or sr.get("product_name") or "").strip()
                          for sr in sr_group if (sr.get("product_name_raw") or sr.get("product_name") or "").strip()})
        multi_ent_count = len(ents)
        multi_brand_flag = "1" if len(brands) > 1 else "0"

        product_name_merged = " / ".join(pnames) if pnames else ""

        quality = first.get("quality") or rec.get("record_quality", "high")
        vid = vehicle_record_id(batch, mid)
        obs = f"{vid}:{EIDC_STAGE}"
        publish_date = manifest.get("publish_date", "")
        if publish_date:
            publish_date = str(publish_date)[:10]

        tax_match = rec.get("vehicle_tax_match_flag", "0")
        pur_match = rec.get("purchase_tax_match_flag", "0")
        # legacy compatibility alias: hit 任一目录 = 1
        legacy_tax_match = "1" if (tax_match == "1" or pur_match == "1") else "0"

        master_row = {
            "vehicle_record_id": vid,
            "observation_id": obs,
            "batch_no": batch,
            "model_code": mid,
            "brand": rec["品牌"],
            "manufacturer": rec["企业名称"],
            "product_name": product_name_merged,
            "common_name": rec.get("common_name", ""),
            "detail_url": manifest.get("source_url", ""),
            "publish_date": publish_date,
            "source": EIDC_SOURCE,
            "stage": EIDC_STAGE,
            "record_quality": quality,
            # vehicle type classification
            "source_vehicle_type": rec.get("source_vehicle_type", ""),
            "vehicle_category": rec.get("vehicle_category", ""),
            "vehicle_subcategory": rec.get("vehicle_subcategory", ""),
            "analysis_scope": rec.get("analysis_scope", "out_of_scope"),
            "catalog_no": rec.get("catalog_no", ""),
            "source_section": first.get("source_section", ""),
            "vehicle_tax_match_flag": tax_match,
            "purchase_tax_match_flag": pur_match,
            "multi_enterprise_count": str(multi_ent_count),
            "multi_brand_flag": multi_brand_flag,
            "tax_catalog_match_flag": legacy_tax_match,
        }

        param_row = {
            "vehicle_record_id": vid,
            "observation_id": obs,
            "batch_no": batch,
            "model_code": mid,
            "brand": rec["品牌"],
            "common_name": rec.get("common_name", ""),
            "energy_type": rec.get("energy_type", ""),
            "source": EIDC_SOURCE,
            "stage": EIDC_STAGE,
            "record_quality": quality,
            "length_mm": "", "width_mm": "", "height_mm": "", "wheelbase_mm": "",
            # vehicle type classification (param table)
            "source_vehicle_type": rec.get("source_vehicle_type", ""),
            "vehicle_category": rec.get("vehicle_category", ""),
            "vehicle_subcategory": rec.get("vehicle_subcategory", ""),
            "analysis_scope": rec.get("analysis_scope", "out_of_scope"),
            "catalog_no": rec.get("catalog_no", ""),
            "source_section": first.get("source_section", ""),
            "curb_weight_kg": rec.get("curb_weight_kg", ""),
            "curb_weight_num": rec.get("curb_weight_num") if rec.get("curb_weight_num") is not None else "",
            "battery_capacity_kwh": rec.get("battery_capacity_kwh", ""),
            "battery_capacity_num": rec.get("battery_capacity_num") if rec.get("battery_capacity_num") is not None else "",
            "battery_mass_kg": rec.get("battery_mass_kg", ""),
            "battery_mass_num": rec.get("battery_mass_num") if rec.get("battery_mass_num") is not None else "",
            "ev_range_km": rec.get("ev_range_km", ""),
            "ev_range_num": rec.get("ev_range_num") if rec.get("ev_range_num") is not None else "",
            "battery_type": "", "battery_chemistry": "", "battery_chemistry_cn": "",
            "motor_power_kw": "", "motor_count": "", "motor_total_peak_kw": "", "single_multi_motor": "",
            "cell_supplier": "", "pack_supplier": "",
            "cell_supplier_group": "", "pack_supplier_group": "", "vertical_integration_flag": "",
            "range_extender": "", "seat_count": "",
            "approx_energy_consumption_kwh_100km": rec.get("总电量口径近似电耗(kWh/100km)", ""),
            "battery_energy_density_wh_kg": rec.get("电池包能量密度(Wh/kg)", ""),
            "km_per_kwh": rec.get("单位电量续航(km/kWh)", ""),
            "battery_mass_ratio_pct": rec.get("电池质量占整备质量比(%)", ""),
            "variant_count": "1",
            "vehicle_tax_match_flag": tax_match,
            "purchase_tax_match_flag": pur_match,
            "metric_scope": rec.get("metric_scope", ""),
            "source_detail": "",
            "source_tax": tax_rec.get("_tax_section", "") or pur_rec.get("_purchase_section", ""),
        }
        master_rows.append(master_row)
        param_rows.append(param_row)

    return master_rows, param_rows


def write_table(dir_path: Path, name: str, rows: list[dict], columns: list[str]):
    csv_path = dir_path / f"{name}.csv"
    json_path = dir_path / f"{name}.json"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"  {name}: {len(rows)} rows -> {csv_path.name} / {json_path.name}")


def main():
    parser = argparse.ArgumentParser(description="MIIT 统一 Dataset 构建器（product_master / vehicle_parameter）")
    parser.add_argument("--batch", default="",
                        help="只构建指定批次（须配合 --output-dir 隔离输出，避免覆盖全量数据集）")
    parser.add_argument("--output-dir", default="",
                        help="输出目录（默认 data/vehicle_parameters/）")
    args = parser.parse_args()

    batches = load_batches()
    if args.batch:
        if not args.output_dir:
            print("--batch 需配合 --output-dir 使用（canonical 数据集必须保持全批次累积，避免单批覆盖全量）")
            sys.exit(1)
        batches = {args.batch: batches.get(args.batch, {})}
        if not args.batch in batches:
            print(f"batch {args.batch} 未在 batches.yaml 登记")
            sys.exit(1)

    out_dir = Path(args.output_dir) if args.output_dir else VEHICLE_PARAMETERS_DIR
    ensure_dir(out_dir)

    name_map = load_name_map()
    master_rows, param_rows = [], []

    # Gov proposed 批次（batches.yaml 登记）
    for batch in sorted(batches):
        print(f"batch {batch} (gov): 构建中...")
        m, p = build_rows(batch, name_map)
        master_rows += m
        param_rows += p

    # EIDC confirmed 批次（data/eidc/ 归档，全部 fresh rebuild 401-408）
    for batch in EIDC_BATCHES:
        if (EIDC_DIR / f"batch_{batch}" / "product_list.json").exists():
            m, p = build_eidc_rows(batch)
            if m:
                print(f"batch {batch} (eidc): {len(m)} canonical rows")
                master_rows += m
                param_rows += p

    master_rows.sort(key=lambda r: r["vehicle_record_id"])
    param_rows.sort(key=lambda r: r["vehicle_record_id"])

    write_table(out_dir, "product_master", master_rows, MASTER_COLUMNS)
    write_table(out_dir, "vehicle_parameter", param_rows, PARAM_COLUMNS)

    print(f"\n总计: {len(master_rows)} 车型 (product_master) / {len(param_rows)} 行 (vehicle_parameter)")
    print(f"输出目录: {out_dir}")


if __name__ == "__main__":
    main()
