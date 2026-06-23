# MIIT New Car Promptbuilder Pack

## 定位

| 目录 / 文件 | 定位 |
|-------------|------|
| `research_scripts/miit_new_car/` | 官方信息获取与结构化（工程层） |
| `docs/miit_promptbuilder_draft.md` | 方法论母版（Prompt 设计和迭代记录） |
| `docs/miit_e2e_runbook.md` | 端到端执行手册（操作指引） |
| `promptbuilders/miit_new_car/` | **可复用 Prompt 模块**（本 Pack） |
| `outputs/miit_new_car/promptbuilder_runs/` | 业务解释结果沉淀区（curated business outputs） |

## 推荐使用顺序

```
1. 00_asset_check.prompt.md          输入资产完整性检查
2. 01_field_cleaning.prompt.md       字段可信度校验与清洗
3. 02_target_brand_extract.prompt.md  目标品牌信息提取
4. 03_product_signal_interpretation.prompt.md  产品信号业务解释
5. 04_brief_output.prompt.md         业务情报简报输出
6. 05_cross_attachment_join.prompt.md（可选）跨附件字段合并
```

## 适用输入

| 输入 | 来源 | 用于哪个 Prompt |
|------|------|-----------------|
| `evidence/batch_{N}_official_source_evidence.json` | `make miit-fetch-batch` | 00, 02, 04 |
| `product_list/batch_{N}_product_list.json` | `make miit-fetch-batch` | 00, 01, 02, 03, 04 |
| `extracted/text/batch_{N}/*.txt` | `make miit-extract-text` | 01, 02 |
| `extracted/batch_{N}_attachment_text.json` | `make miit-extract-text` | 00, 02 |
| `configs/miit_new_car_watchlist.csv` | 项目配置 | 02 |
| `docs/miit_promptbuilder_draft.md` | 项目文档 | 全流程参考 |
| `docs/miit_e2e_runbook.md` | 项目文档 | 全流程参考 |

## 输出文件夹说明

| 路径 | 内容 | 是否可提交 |
|------|------|-----------|
| `outputs/miit_new_car/raw/` | 附件 DOC 原始文件 | 不提交（runtime） |
| `outputs/miit_new_car/parsed/` | 附件级结构化记录 | 不提交（runtime） |
| `outputs/miit_new_car/diff/` | Watchlist 增量 diff | 不提交（runtime） |
| `outputs/miit_new_car/evidence/` | Evidence 分层 JSON | 不提交（runtime） |
| `outputs/miit_new_car/state/` | 最新批次状态缓存 | 不提交（runtime） |
| `outputs/miit_new_car/extracted/` | 附件文本抽取 JSON / 纯文本 | 不提交（runtime） |
| `outputs/miit_new_car/product_list/` | 结构化产品清单 | 不提交（runtime） |
| `outputs/miit_new_car/diagnostics/` | 附件可用性诊断 | 不提交（runtime） |
| `outputs/miit_new_car/discovery/` | 批次发现缓存 | 不提交（runtime） |
| `outputs/miit_new_car/promptbuilder_runs/` | **业务简报（curated markdown）** | **可提交** |

## 使用方式

每个 `.prompt.md` 文件可独立复制到 OpenCode / ChatGPT / DeepSeek 的对话中。将 `{batch_N}` 替换为实际批次号，将 `{target_brands}` 替换为目标品牌列表，将对应输入文件的 JSON / 文本内容粘贴到 Prompt 中的指定位置。

## 降级模式 / Degraded Mode

当批次状态为 **publicity**（公示）而非 official（正式发布），或主附件返回 404、product_list 为空（quality=empty）时，Prompt Pack 自动进入降级模式。

### 降级模式行为

| 模块 | 正常模式 | 降级模式 |
|------|----------|----------|
| 00_asset_check | 预期所有资产完整 | 输出 asset_status=partial/empty，标记 blocking_reason |
| 01_field_cleaning | 对 product_list records 做字段清洗 | 跳过（0 records），输出 skipped_empty_product_list |
| 02_target_brand_extract | 基于 product_list + extracted text | 仅基于 tax catalog / extracted text fallback，source_reliability 受限 |
| 03_product_signal_interpretation | 可输出完整车型判断，含 S/A/B/C | 仅输出"观察信号"，不允许 S 级判断，所有结论标记 low confidence |
| 04_brief_output | 标准简报 | 含"输入资产降级说明"章节，明确告知结论适用范围限制 |

### 降级模式使用限制

- 降级模式下只能做**有限信号提取**，不能输出完整车型判断。
- 所有结论必须注明输入来源限制（如"基于 tax catalog 数据，非完整产品清单"）。
- 降级模式不阻断分析，但会显著降低结论置信度。
- 建议在批次转为 **official** 后复跑完整流程。

## 分附件证据边界 / Source-aware Evidence Boundary

MIIT 不同附件提供不同粒度的字段。Prompt Pack 不是一刀切禁止深度参数，而是要求**按附件来源判断可提取范围**。

### 核心原则

- **公告型号 ≠ 上市商品名**。product_model（如 CSA6492）是公告申报的型号前缀，不代表最终上市的商品名称。
- **申报 ≠ 上市**。MIIT 申报到实际上市通常有 3-12 个月延迟。
- **附件不同 → 证据边界不同**。主公告(附件1)只能做公告身份和产品路线判断；税收目录(附件2/3)可提供续航、电池、整备质量等深度参数。

### 附件字段差异

| 字段 | 附件1 主公告 | 附件2 车船税目录 | 附件3 购置税目录 |
|------|-------------|-----------------|-----------------|
| enterprise_name | ✅ | ✅ | ✅ |
| directory_no（目录序号） | ✅ | — | — |
| brand / 商标 | ✅ | ✅ | — |
| product_name（产品大类） | ✅ | — | ✅ |
| product_model（公告型号） | ✅ | ✅ | ✅ |
| new_product / change_extension | ✅ | — | — |
| **通用商品名**（如"海狮06"） | — | ✅ | ✅ |
| **纯电续航(km)**（PHEV） | — | ✅ | — |
| **CLTC续航(km)**（BEV） | — | — | ✅ |
| **电池能量(kWh)** | — | ✅ | ✅ |
| **电池质量(kg)** | — | ✅ | ✅ |
| **整备质量(kg)** | — | ✅ | ✅ |
| **燃料消耗量(L/100km)** | — | ✅ | — |
| **排量(ml)** | — | ✅ | — |

### 各附件可提取的字段清单

#### 附件 1 — 主公告（道路机动车辆生产企业及产品）

**可提供**：企业名、目录序号、品牌/商标、产品大类名称、公告型号、新产品/变更扩展类型。

**不提供**：通用商品名、续航里程、电池能量、电池质量、整备质量、燃料消耗量、排量、价格、上市时间、智驾版本、配置高低配。

#### 附件 2 — 车船税减免目录

**可提供**：企业名、品牌/商标、通用商品名、公告型号、PHEV 纯电续航、电池能量、电池质量、整备质量、燃料消耗量、排量。

**不提供**：产品大类名称、价格、上市时间、智驾版本、配置高低配。

#### 附件 3 — 购置税减免目录

**可提供**：企业名、产品大类名称、通用商品名、公告型号、CLTC 续航、电池能量、电池质量、整备质量。

**不提供**：品牌/商标、价格、上市时间、智驾版本、配置高低配。

### 跨附件合并说明

`product_model`（公告型号）是跨附件合并的核心 join key。例如：

```
附件1(主公告): 上海汽车集团 / 智己牌 / 纯电动运动型乘用车 / CSA6492
附件3(购置税): 上海汽车集团 / CSA6492LBEVK / 智己L6 / 纯电动运动型乘用车 / 710km / 82.732kWh
```

通过 `product_model` 前缀 `CSA6492` 合并，可获得：
- enterprise_name: 上海汽车集团（附件1）
- brand: 智己（附件1）
- product_name: 纯电动运动型乘用车（附件1/3）
- generic_model_name: 智己L6（附件3）
- product_model: CSA6492（附件1/3）
- cltc_range: 710km（附件3）
- battery_energy_kwh: 82.732kWh（附件3）

### 禁止字段（所有附件均不提供）

价格、上市时间、智驾版本、配置高低配、市场威胁强度。

### 信息边界示例

以一条典型的智己记录为例：

```
附件1: 上海汽车集团 / 智己牌 / 插电式增程混合动力运动型乘用车 / CSA6492
附件3: 上海汽车集团 / CSA6492LBEVK / 智己L6 / 710km / 82.732kWh
```

**可以解释为**：
> "智己增程产品进入公告申报阶段【附件1】；智己L6 纯电版 CLTC 续航 710km，电池 82.732kWh【附件3】。"

**不能解释为**：
> "该车型价格、上市时间、智驾版本、配置高低配、市场威胁强度。"

## 边界验证案例

| 批次 | 状态 | 特点 | 验证意义 |
|------|------|------|----------|
| 第 407 批 | official | 主附件完整，product_list 1111 条/469 企/939 型号 | 正常路径验证 |
| 第 408 批 | publicity | 3 个附件 404，product_list empty (quality=empty)，仅 tax catalog 可用 | 降级路径验证 |

## 版本

- **Version**: v0.4
- **Source**: `docs/miit_promptbuilder_draft.md` v0.2 draft + 第 408 批 publicity 边界验证
- **Date**: 2026-06-23
- **Key changes**: 新增 degraded mode 全流程支持；新增信息边界规则；新增分附件证据边界（Source-aware Evidence Boundary），区分附件1/2/3 字段差异；01 增加附件类型感知规则；02 新增 source_attachment_type / source_supported_fields / source_join_key；03 改为按附件来源解释深度参数；04 新增"分附件证据来源说明"章节；05 新增跨附件 join 模块
