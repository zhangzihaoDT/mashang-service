# vehicle_parameters/ —— 乘用车业务 Canonical Fact Layer

**定位**：MIIT 的**乘用车业务 canonical fact layer**（不是全量道路机动车辆镜像）。由 `scripts/07_build_vehicle_dataset.py` 从已归档批次构建，一车型一行，reports/ 与 Agent 默认消费这一层。

> **Canonical Eligibility** = `model_code valid` **AND** `vehicle_category == passenger_vehicle`

Source / Parser 层仍保留并解析全量道路机动车辆（商用车/摩托车/挂车/专用车等全部在 `data/eidc/` 等 source archive）；`vehicle_parameters/` 只落乘用车。非乘用车不进入本层，也不制造第二套"垃圾桶"数据集。

### ⚠ 架构约束：Passenger eligibility = source-record 级 existential

```
同一 batch:model_code 只要存在至少一条合法 passenger_vehicle source record，
该 vehicle record 即进入本层 canonical；
非乘用变体仍留在 source evidence。
```

gate 在 07 build 时**逐 source record 执行、先于 by model_code 聚合**（`classify_source_record` → `is_canonical_in_scope` → enrichment）。禁止改为聚合后按首条记录分类判定。

## 两张核心表

- **product_master** — 车型身份主表，一车型一行，身份 `vehicle_record_id = {batch_no}:{model_code}`
  - 字段：batch_no / model_code / brand / manufacturer / product_name / common_name / detail_url / publish_date / source / stage / record_quality / vehicle_tax_match_flag / purchase_tax_match_flag / multi_enterprise_count / multi_brand_flag
- **vehicle_parameter** — 车型参数事实表，一车型一行，身份同上
  - 字段：尺寸 / 轴距 / 整备质量 / 电池类型与化学体系 / 电芯·总成供应商与集团 / 电机功率与数量 / 容量·续航·增程器 / 座位数 / 衍生指标（近似电耗、能量密度、单位电量续航、电池质量占比）/ 数据质量标记

## 分类维度（derived，不参与 identity）

- **source_vehicle_type** — 原始产品名称/类别（source fact，不丢原始语义）
- **vehicle_category** — 统一大类：`passenger_vehicle` / `commercial_vehicle` / `motorcycle` / `trailer` / `other`
- **vehicle_subcategory** — 业务二级：`sedan`/`suv_mpv`/`other_passenger`；`bus`/`truck`/`tractor`/`special_vehicle`/`sanitation_fire`；`motorcycle`/`trailer`
- **analysis_scope** — `in_scope`（passenger_vehicle）/ `out_of_scope`。**canonical 已在 build 阶段执行 passenger gate，因此 analysis_scope 目前主要作为兼容/显式语义字段，而不是再次过滤的必要条件**（后续再决定是否废弃）
- **catalog_no / source_section** — EIDC 目录序号与官方分节标题（evidence）
  - ⚠ **source_section 对第一部分（新产品）混排产品不可靠**：第一部分仅"一、汽车生产企业"一个一级标题，摩托车/底盘/起重机等产品表共享稀疏标题，source_section 只是"最近捕获的官方标题"（位置 evidence）。**分类请一律使用 vehicle_category**（产品名强规则优先 + 目录序号官方信号兜底），不要用 source_section 分类。

分类逻辑在 `scripts/vehicle_record_builder.py` 的 `classify_vehicle_type()`，Gov/EIDC 共用；scope gate 统一为 `is_canonical_in_scope()`。

## 口径说明

- **身份**：同一 `model_code` 跨批次再次申报时，`batch_no` 不同即视为不同记录（版本），便于将来识别"同一车型跨批次变化"，而不是被覆盖。
- **一车型一行**：多配置（容量/续航/整备质量带 `/`）保留原始串 + 首值数值列，另设 `variant_count` 标记配置版本数；如需逐配置行请用 `data/wide_tables/`。
- **通用名称 `common_name`**：优先车船税 `通用名称`，其次 `workflow/model_name_map.json`；纯电/燃油车型可能为空（车船税目录未收录，属正常口径）。
- **衍生指标口径**：与 `data/wide_tables/` 一致——电耗为"总电量口径近似电耗"（电池总能量÷纯电续航×100，非官方口径），电池质量占比支持公差区间显示。仅车船税命中车型（`vehicle_tax_match_flag=1`）有值。

## 重建

```bash
python3 scripts/07_build_vehicle_dataset.py             # canonical（passenger only，Gov + EIDC）
python3 scripts/eidc_summary_fresh.py                    # 每批 fresh summary（轻量验收）
```

当前：831 车型，全部 `vehicle_category == passenger_vehicle`（eidc/confirmed 401-408 fresh + miit_gov/proposed 409-410）。
