# eidc/ —— EIDC Source Archive（confirmed 层）

**定位**：EIDC（工信部装备工业发展中心 miit-eidc.org.cn）正式公告的 **source evidence + pipeline 文档**。足以重新构建 canonical Dataset 的最小历史证据集（401–408）。只保留 source evidence 与其 provenance；投影/分析产物不在此列（删除后可由 source 重新生成）。

**进入 canonical 时**：`source=eidc, stage=confirmed`，且 **仅 `vehicle_category == passenger_vehicle`** 进入 `data/vehicle_parameters/`。

> **Source Archive = full regulatory universe；Canonical Dataset = passenger vehicle business scope。**
> 本层（data/eidc/）保留全部商用车/摩托车/挂车/专用车 source evidence；canonical 收敛只发生在 06 build 的 passenger scope gate。

### ⚠ 架构约束：Passenger eligibility = source-record 级 existential

```
同一 batch:model_code 只要存在至少一条合法 passenger_vehicle source record，
该 vehicle record 即进入 passenger canonical；
非乘用变体仍留在 source evidence（不进 canonical，不删除）。
```

- **gate 必须逐 source record 执行、在 by model_code 聚合之前**（`classify_source_record` 先于 `match_eidc_enrichment`）。
- **禁止**把 gate 移到聚合之后按"首条记录分类"判定——会漏掉同 chassis 多车型（旅居车/商务车 + 救护车/巡逻车等）的乘用变体（如 407:KLF5040X、408:JKF5030X）。
- 该语义已落档：`scripts/vehicle_record_builder.py`（gate 常量区）+ `scripts/06_build_vehicle_dataset.py:build_eidc_rows`。

---

## 1. EIDC Pipeline（当前架构）

```
官方公告页 (miit-eidc.org.cn)
   ↓ 03_fetch_eidc_batch.py（source orchestration）
   ↓   [1] fetch announcement page + parse metadata
   ↓   [2] download attachments (.doc)   → attachments/
   ↓   [3] doc → txt (textutil)          → attachment_text_src/
   ↓   [4] eidc_parser.parse_road_products → product_list.json（source records）
   ↓   [5] write import_manifest.json（provenance）
   ↓
data/eidc/batch_{N}/
   ↓
06_build_vehicle_dataset.py（canonical 唯一入口）
   ├─ Gov proposed（batches.yaml 409/410）→ build_rows
   └─ EIDC confirmed（自动遍历 data/eidc/ 401-408）→ build_eidc_rows
        ├─ normalize model_code → classify source record（classify_source_record）
        ├─ passenger scope gate（is_canonical_in_scope）
        ├─ match_eidc_enrichment(model_code, tax_index, purchase_index)  ← 仅 passenger
        ├─ build_eidc_record(source_record, tax_rec, purchase_rec)       ← 领域解释
        └─ 一车型一行，vehicle_record_id = {batch}:{model_code}
   ↓
data/vehicle_parameters/product_master + vehicle_parameter
   = passenger vehicle business canonical（vehicle_category == passenger_vehicle）
```

### 各层职责边界

| 层 | 文件 | 职责 | 禁止 |
|---|---|---|---|
| Source 层 | `scripts/eidc_source.py` | 网络抓取 / 附件下载 / doc→txt / sha256 | canonical 字段推断 |
| Parser 层 | `scripts/eidc_parser.py` | 解析 EIDC 数据结构 → source record（`*_raw` + `source_section`） | 领域语义解释 |
| Parser 层 | `scripts/04_parse_vehicle_tax.py` | 车船税目录（附件2）解析 | — |
| Parser 层 | `scripts/05_parse_purchase_tax.py` | 购置税目录（附件3）解析 | — |
| 公共领域层 | `scripts/vehicle_record_builder.py` | `build_eidc_record` / `normalize_model_code` / `classify_vehicle_type` / 衍生指标 | parse_eidc_html/xml |
| Canonical 层 | `scripts/06_build_vehicle_dataset.py` | 唯一 Dataset writer | 第二个 builder |

> 边界原则：**EIDC source 层回答"官方页面提供了什么"；vehicle_record_builder 回答"这些字段在统一车型模型里意味着什么"。** 不分叉、不建第二套 canonical writer。

---

## 2. 批次目录结构

```
eidc/
├── README.md
├── import_manifests.json       ← 全量 provenance 汇总（401-408）
└── batch_{N}/
    ├── import_manifest.json    ← 每批 provenance：source_url/announcement_no/publish_date/
    │                             vehicle_tax_batch/purchase_tax_batch/附件 sha256/fetch_mode
    ├── product_list.json       ← EIDC source records（`*_raw` contract + source_section）
    ├── raw_metadata.json       ← 批次原始元数据（标题/公告号/日期/附件清单）
    ├── attachment_text_src/    ← 附件 txt（附件1 road / 附件2 车船税 / 附件3 购置税）
    ├── attachments/            ← 原始 .doc（gitignored）
    ├── raw_detail.html         ← 原始公告页（gitignored）
    ├── duplicate_model_code_audit.json ← 同型号多企业/多品牌聚合审计（evidence）
```
（legacy 已删除：fresh rebuild 完成后，旧 workspace 导入产物随迁移完成清理，见 `migration_eidc_fresh_rebuild.json`）

### product_list.json（source record contract）

由 `eidc_parser.parse_road_products` 产出，保留 EIDC 原字段语义（不做 canonical 推断）：

```json
{
  "batch_no": "408",
  "manufacturer_raw": "中国第一汽车集团有限公司",
  "catalog_no_raw": "1",
  "brand_raw": "一汽牌",
  "product_name_raw": "插电式混合动力多用途乘用车",
  "model_code_raw": "CA6471",
  "vehicle_type_raw": "插电式混合动力多用途乘用车",
  "source_section": "一、汽车生产企业"
}
```

---

## 3. Source Schema（附件一真实结构）

`textutil` 导出的附件一（道路机动车辆生产企业及产品）为 `\x07` 扁平表：

- 表头 4 列：`序号 / 商标 / 产品名称 / 产品型号`
- 重复 5 列数据组：`企业名称 / 目录序号 / 商标 / 产品名称 / 产品型号`
- 多型号记录（`CA4250、CA4185、…`）按 `、，,;；` 拆分为多个 source record

### 官方分节结构（evidence，见可靠性注意）

```
第一部分 新产品
  一、汽车生产企业（唯一一级标题，混排乘用车/商用车/底盘/起重机/摩托车）
  民用改装车生产企业 / 汽车起重机生产企业（子标题）
第二部分 变更扩展产品（(一)汽车 / (二)摩托车 / (三)三轮汽车）
第三部分 暂停、恢复企业及产品
第四部分 撤销企业及产品
```

### 目录序号格式（官方企业类别信号）

- `（X）数字`（如 `(一)03`、`(十五)125`）= 带地区前缀 → **专用车/改装车企业**
- `纯数字`（如 `1`、`80`）= 整车企业（乘用车/商用车/摩托车/起重机混排）

---

## 4. 分类维度（derived，不参与 identity）

- **source_vehicle_type** — 原始产品名称/类别（source fact）
- **vehicle_category** — `passenger_vehicle` / `commercial_vehicle` / `motorcycle` / `trailer` / `other`
- **vehicle_subcategory** — `sedan`/`suv_mpv`/`other_passenger`；`bus`/`truck`/`tractor`/`special_vehicle`/`sanitation_fire`；`motorcycle`/`trailer`
- **analysis_scope** — `in_scope`（passenger_vehicle）/ `out_of_scope`。业务分析默认 `in_scope`（乘用车）
- **catalog_no / source_section** — EIDC 目录序号 / 官方分节标题（evidence）

分类逻辑在 `scripts/vehicle_record_builder.py:classify_vehicle_type()`，优先级：
1. 产品名强规则（摩托/挂车/乘用车/客车/牵引/消防环卫/货车/专用车）→ 产品名优先
2. 产品名无强规则 + `（X）数字`目录序号 → 官方信号归 `commercial_vehicle/special_vehicle`
3. 产品名 category 规则兜底 → 其余 `other`

---

## 5. ⚠ 可靠性注意

1. **source_section 对第一部分（新产品）混排产品不可靠**：第一部分仅"一、汽车生产企业"一个一级标题，摩托车/底盘/起重机等产品表共享稀疏标题，source_section 只是"最近捕获的官方标题"（位置 evidence）。**分类请一律使用 vehicle_category**，不要用 source_section 分类。
2. **model_code 质量门禁**：`normalize_model_code()` 校验，非法型号不进 canonical（仅留 source evidence）。408 valid 99.89% / 407 valid 99.6%。
3. **401-408 全部为 fresh rebuild**：legacy 导入已随 fresh 迁移完成删除（见 `migration_eidc_fresh_rebuild.json`），本层不含 legacy 解析产物。
4. **重复型号聚合**：同型号多企业/多产品名合并为一行，`multi_enterprise_count` / `multi_brand_flag` 标记冲突（408 有 7 条 multi_brand）。详见各批 `duplicate_model_code_audit.json`。
5. **无车型详情页**：EIDC 无 Gov 式详情页，dimensions/motor_power/电池供应商 等深度参数依赖车船税/购置税附件或 Gov 详情页补全，本层 source 不含。

---

## 6. 命令速查

```bash
# fresh 抓取 + 解析（source 层）
python3 MIIT/scripts/03_fetch_eidc_batch.py --batch 408
python3 MIIT/scripts/03_fetch_eidc_batch.py --batch 408 --discovery-only   # 只抓公告页元数据
python3 MIIT/scripts/03_fetch_eidc_batch.py --batch 407 --offline          # 网络不可用时复用缓存 raw_metadata

# 超大附件（textutil 失败）备用提取
python3 MIIT/scripts/eidc_doc_extract.py --input a.doc --output a.txt       # olefile FIB 文本区提取

# regulatory 附件解析（04/05 输出落 data/vehicle_tax/）
python3 MIIT/scripts/04_parse_vehicle_tax.py --input 附件2.txt --output 车型清单_第87批车船税 --batch 第八十七批 --date 2026-07-17
python3 MIIT/scripts/05_parse_purchase_tax.py --input 附件3.txt --output 车型清单_第32批购置税 --batch 第三十二批 --date 2026-07-17

# canonical 构建（唯一入口）
python3 MIIT/scripts/06_build_vehicle_dataset.py

# 每批 fresh summary（轻量验收）
python3 MIIT/scripts/validate_eidc_batch.py

# benchmark（验证 source → canonical 全链路）

# 测试
python3 -m pytest MIIT/scripts/tests -q
```

---

## 7. 当前覆盖

| 批次 | 方式 | source raw valid | **canonical passenger rows** | vehicle_tax_batch | purchase_tax_batch |
|---|---|---|---|---|---|
| 401 | **fresh rebuild** | 1585 | 117 | 80 | 24 |
| 402 | **fresh rebuild** | 1547 | 135 | 81 | 25,26 |
| 403 | **fresh rebuild** | 625 | 43 | 82 | 27 |
| 404 | **fresh rebuild** | 1336 | 84 | 83 | 28 |
| 405 | **fresh rebuild** | 860 | 63 | 84 | 29 |
| 406 | **fresh rebuild** | 1354 | 94 | 85 | 30 |
| 407 | **fresh rebuild** | 1424 | 96 | 86 | 31 |
| 408 | **fresh rebuild** | 1881 | 133 | 87 | 32 |

- **401-408 全部为 fresh rebuild / confirmed**（2026-08 fresh 重建完成；legacy 导入已删除，见 `migration_eidc_fresh_rebuild.json`）。
- canonical 收敛为乘用车：`data/vehicle_parameters/` 只落 `vehicle_category==passenger_vehicle`（`model_code valid AND passenger`）。
- source raw valid 列显示**全量**道路机动车辆（含商用车/摩托车/挂车），证明 parser 未漏官方数据；canonical 只保留乘用车业务对象。
- **超大附件**（如 402 购置税26批、403 车船税82批，完整版 32MB 目录）：textutil 无法转换，用 `eidc_doc_extract.py`（olefile FIB 文本区提取）处理后走 04/05 parser。
- 402 的购置税为两批（第二十五、二十六批），manifest `purchase_tax_batch="25,26"` 逗号分隔。
- 每批验收：`validate_eidc_batch.py`（batch/announcement/raw/valid/passenger/multi_brand/tax hit/schema_status）。
