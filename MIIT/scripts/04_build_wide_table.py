#!/usr/bin/env python3
"""
MIIT Pipeline P4: 参数宽表构建器

Parse 新车 models from batch scan and generate a wide table
by merging 附件1 (brand .md detail pages) and 附件2 (车船税 JSON).

Outputs: data/wide_tables/wide_table_{batch}.csv + .md

输入统一来自 data/search_results + data/vehicle_tax + data/vehicle_details。
批次配置（scan/tax 文件名）统一读取 workflow/batches.yaml。
领域逻辑（标准字段构建/衍生指标/多配置展开）统一来自 vehicle_record_builder。

Derived metrics:
  - 百公里电耗近似值 (kWh/100km): battery_energy / range * 100 (BEV only)
  - 电池包能量密度 (Wh/kg): battery_energy_kWh / battery_mass_kg * 1000
  - 单位电量续航 (km/kWh): range / battery_energy
  - 整车电池质量占比: battery_mass / curb_weight
  - 电池供应商装机结构: supplier count per brand (summary output)

用法:
  python3 scripts/04_build_wide_table.py --batch 410
  python3 scripts/04_build_wide_table.py --batch 410 --output-dir 自定义目录
"""

import csv
import argparse
import sys
from pathlib import Path

from miit_paths import (  # noqa: E402
    DEFAULT_BATCH,
    load_batches,
    scan_path,
    tax_json_path,
    wide_table_path,
    WIDE_TABLES_DIR,
    ensure_dir,
)
from vehicle_record_builder import (  # noqa: E402
    parse_scan_md,
    load_tax_index,
    read_brand_md,
    build_record,
    explode_variants,
    supplier_summary,
    _dedup_by_model,
    is_canonical_in_scope,
)


def main():
    parser = argparse.ArgumentParser(description="MIIT 新车参数宽表生成器")
    parser.add_argument("--batch", default=DEFAULT_BATCH,
                        help=f"公告批次号（默认 {DEFAULT_BATCH}），如 410")
    parser.add_argument("--output-dir", default="",
                        help="输出目录（默认 MIIT/{batch}-Parameter/）")
    args = parser.parse_args()

    batch = args.batch
    cfg = load_batches().get(batch, load_batches()[DEFAULT_BATCH])
    SCAN_PATH = scan_path(batch)
    TAX_PATH = tax_json_path(batch)
    out_dir = Path(args.output_dir) if args.output_dir else WIDE_TABLES_DIR
    ensure_dir(out_dir)
    csv_path = out_dir / ("wide_table_" + batch + ".csv")
    md_path = out_dir / ("wide_table_" + batch + ".md")
    out_dir.mkdir(parents=True, exist_ok=True)

    models = parse_scan_md(SCAN_PATH)
    print(f"Found {len(models)} models in scan file")

    tax_index = load_tax_index(TAX_PATH)
    print(f"Tax index has {len(tax_index)} entries")

    records = []
    missing_md = []
    missing_tax = []
    missing_both = []

    for m in models:
        mid = m["model_id"]
        brand = m["brand"]

        md_data = read_brand_md(brand, mid, batch)
        tax_data = tax_index.get(mid, {})

        if md_data is None:
            missing_md.append(mid)
        if not tax_data:
            missing_tax.append(mid)

        rec = build_record(m, md_data, tax_data)
        # 业务分析宽表默认 passenger scope（与 canonical 同 gate，不破坏 variant explosion）
        if not is_canonical_in_scope(rec):
            continue
        records.append(rec)

    # ── Expand multi-value variants and compute derived metrics ──
    records, original_model_ids = explode_variants(records)
    n_original = len(original_model_ids)
    n_expanded = len(records)
    print(f"Original models: {n_original}, after variant expansion: {n_expanded} rows")

    # ── Output CSV ──
    field_names = [
        "品牌", "企业名称", "产品型号", "产品名称",
        "动力形式",
        # Motor
        "电机功率(kW)", "motor_count", "motor_total_peak_kw", "single_multi_motor",
        # Battery chemistry
        "电池类型", "battery_chemistry", "battery_chemistry_cn", "battery_ncm_explicit_flag",
        # Core metrics
        "电池容量(kWh)", "电池质量(kg)", "纯电续航(km)", "整备质量(kg)",
        # Suppliers (split)
        "cell_supplier", "pack_supplier",
        "cell_supplier_group", "pack_supplier_group", "vertical_integration_flag",
        # Legacy combined
        "电芯/总成供应商",
        # Engine
        "增程器",
        # Dimensions
        "长(mm)", "宽(mm)", "高(mm)",
        # Derived
        "总电量口径近似电耗(kWh/100km)", "电池包能量密度(Wh/kg)",
        "单位电量续航(km/kWh)", "电池质量占整备质量比(%)",
        # Data quality
        "tax_catalog_match_flag", "battery_metrics_available_flag",
        "missing_reason", "metric_scope",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=field_names, extrasaction="ignore")
        w.writeheader()
        for rec in records:
            w.writerow(rec)
    print(f"CSV written: {csv_path}")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 第{batch}批 MIIT 新车参数宽表\n\n")
        f.write(f"**数据来源**: 附件1 企业申报详情页 + 附件2 车船税目录\n\n")
        f.write(f"**行数(含配置展开)**: {len(records)} 行 | ")
        f.write(f"**原始车型数**: {n_original} | ")
        f.write(f"附件1缺失: {len(missing_md)} | ")
        f.write(f"附件2缺失: {len(missing_tax)}\n\n")
        f.write("> 备注：含 `/` 的续航/质量字段已按配置版本展开为独立行。电机功率中 `/` 表前/后双电机，不做拆分。\n\n")

        # Table
        table_fields = [
            "品牌", "产品型号", "产品名称", "动力形式",
            "电机功率(kW)", "single_multi_motor",
            "电池类型", "battery_chemistry_cn",
            "电池容量(kWh)", "电池质量(kg)", "纯电续航(km)", "整备质量(kg)",
            "总电量口径近似电耗(kWh/100km)", "电池包能量密度(Wh/kg)",
            "单位电量续航(km/kWh)", "电池质量占整备质量比(%)",
            "cell_supplier", "pack_supplier", "vertical_integration_flag",
            "metric_scope",
        ]
        header = "| " + " | ".join(table_fields) + " |"
        sep = "| " + " | ".join(["---"] * len(table_fields)) + " |"
        f.write(header + "\n")
        f.write(sep + "\n")
        for rec in records:
            row = []
            for k in table_fields:
                v = str(rec.get(k, "") or "")
                # Shorten long supplier names — keep only first supplier
                if k == "电芯/总成供应商" and len(v) > 40:
                    v = v[:40] + "…"
                row.append(v)
            f.write("| " + " | ".join(row) + " |\n")

        # Summary
        f.write("\n---\n\n")
        f.write("## 数据质量\n\n")
        f.write(f"- 附件1详情页缺失的型号: {', '.join(missing_md) if missing_md else '无'}\n")
        f.write(f"- 附件2车船税缺失的型号: {', '.join(missing_tax) if missing_tax else '无'}\n\n")

        # Per-brand breakdown (deduplicated by original model)
        f.write("## 各品牌车型数量\n\n")
        f.write("> 统计口径：按原始产品型号去重（去除#1/#2配置后缀），下同。\n\n")
        from collections import defaultdict
        brand_counts: dict[str, set[str]] = defaultdict(set)
        for r in records:
            mid = r.get("产品型号", "").split("#")[0]
            brand_counts[r["品牌"]].add(mid)
        f.write(f"| 品牌 | 原始车型数 | 配置行数 |\n|------|:--------:|:-------:|\n")
        for b in sorted(brand_counts, key=lambda x: len(brand_counts[x]), reverse=True):
            models_in_brand = len(brand_counts[b])
            configs_in_brand = sum(1 for r in records if r.get("品牌") == b)
            f.write(f"| {b} | {models_in_brand} | {configs_in_brand} |\n")
        f.write(f"| **合计** | **{n_original}** | **{n_expanded}** |\n")

        # Supplier coverage
        f.write("\n## 电池供应商覆盖结构\n\n")
        f.write("**电芯集团级覆盖（车型去重）**:\n\n")
        f.write(f"```\n{supplier_summary(records, by_model=True, by_group=True)}\n```\n")
        f.write("**电芯/总成组合级**:\n\n")
        f.write(f"```\n{supplier_summary(records, by_model=True, by_group=False)}\n```\n")
        f.write(f"**配置展开视角（{n_expanded}行）**:\n\n")
        f.write(f"```\n{supplier_summary(records, by_model=False, by_group=False)}\n```\n")

        f.write("**垂直整合分类**:\n\n")
        from collections import Counter
        vi_counts = Counter()
        for r in _dedup_by_model(records):
            vi = r.get("vertical_integration_flag", "")
            if vi:
                vi_counts[vi] += 1
        for vi, cnt in vi_counts.most_common():
            label_map = {"same_company": "同一企业", "same_group": "同集团不同主体", "cross_group": "跨企业合作"}
            f.write(f"- {label_map.get(vi, vi)}: {cnt}款\n")

        # Derived metric summary — dual perspective with explicit scope
        f.write("\n## 衍生指标汇总\n\n")
        covered = sum(1 for r in _dedup_by_model(records) if r.get("tax_catalog_match_flag") == "1")
        f.write("> **以下容量、续航、电池质量及近似电耗统计，仅覆盖附件2（车船税目录）成功匹配的"
                f"{covered}款增程/插混车型，不包含{len(original_model_ids)-covered}款纯电车型。**\n\n")
        f.write("> 电耗指标为\u201c总电量口径近似电耗\u201d，即电池总能量\u00f7纯电续航\u00d7100，为非官方口径"
                "（总电量≠可用电量，续航工况未统一），适用于**异常值筛查、同平台配置对比、同类车型粗略排序**，"
                "不宜直接认定为产品官方电耗。\n\n")

        # Deduplicate for model-level averages
        deduped = _dedup_by_model(records)

        eds_model = [r["总电量口径近似电耗(kWh/100km)"] for r in deduped
                     if isinstance(r.get("总电量口径近似电耗(kWh/100km)"), (int, float))]
        eds_config = [r["总电量口径近似电耗(kWh/100km)"] for r in records
                      if isinstance(r.get("总电量口径近似电耗(kWh/100km)"), (int, float))]
        if eds_model:
            f.write(f"- **按车型等权**（{len(eds_model)}个原始车型）平均近似电耗: {round(sum(eds_model)/len(eds_model), 1)} kWh/100km\n")
            f.write(f"  - 最低: {min(eds_model)} kWh/100km | 最高: {max(eds_model)} kWh/100km\n")
        if eds_config and len(eds_config) != len(eds_model):
            f.write(f"- **按配置行**（{len(eds_config)}行）平均近似电耗: {round(sum(eds_config)/len(eds_config), 1)} kWh/100km\n")

        ev_deduped = [r for r in deduped if r.get("动力形式") == "纯电动"]
        ev_all = [r for r in records if r.get("动力形式") == "纯电动"]
        phev_deduped = [r for r in deduped if "混合" in (r.get("动力形式") or "")]
        phev_all = [r for r in records if "混合" in (r.get("动力形式") or "")]

        if ev_deduped:
            ev_eds = [r["总电量口径近似电耗(kWh/100km)"] for r in ev_deduped
                      if isinstance(r.get("总电量口径近似电耗(kWh/100km)"), (int, float))]
            if ev_eds:
                f.write(f"- 纯电动（车型等权 {len(ev_deduped)}个）平均近似电耗: {round(sum(ev_eds)/len(ev_eds), 1)} kWh/100km\n")
        if phev_deduped:
            phev_ranges_model = [r["_range_num"] for r in phev_deduped if isinstance(r.get("_range_num"), (int, float))]
            phev_ranges_config = [r["_range_num"] for r in phev_all if isinstance(r.get("_range_num"), (int, float))]
            if phev_ranges_model:
                f.write(f"- PHEV/增程（车型等权 {len(phev_ranges_model)}个）平均纯电续航: {round(sum(phev_ranges_model)/len(phev_ranges_model))} km\n")
                if len(phev_ranges_config) != len(phev_ranges_model):
                    f.write(f"- PHEV/增程（配置行 {len(phev_ranges_config)}行）平均纯电续航: {round(sum(phev_ranges_config)/len(phev_ranges_config))} km\n")

    print(f"MD written: {md_path}")
    print(f"附件1缺失: {len(missing_md)}, 附件2缺失: {len(missing_tax)}")


if __name__ == "__main__":
    main()
