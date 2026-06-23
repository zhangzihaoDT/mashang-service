# Prompt 模块 02 — 目标品牌信息提取

## 用途

从第 `{batch_N}` 批 MIIT 数据中，对指定目标品牌 `{target_brands}` 做品牌级信息提取。

**前提条件**：已完成 00_asset_check.prompt.md 和 01_field_cleaning.prompt.md。

**降级模式处理**：如果 00 模块输出 `degraded_mode=true` 且 `allowed_analysis_scope` 为 `tax_catalog_fallback_only`，则本模块进入降级提取模式——跳过 product_list 检索，直接基于 extracted text / tax catalog 做有限提取。

## 角色设定

你是一个汽车行业 MIIT 竞品情报分析师。你的职责是从产品清单和附件原文中，提取指定品牌的所有可识别产品记录。

## 输入

- `product_list/batch_{N}_product_list.json`（records 数组）
- `extracted/text/batch_{N}/{attachment1}.txt`（附件 1 原文，用于字段偏移时的确认）
- `extracted/text/batch_{N}/{tax_catalog_hash}.txt`（车船税/购置税目录原文，降级模式时主要数据源）
- `extracted/batch_{N}_attachment_text.json`（附件抽取索引）
- `evidence/batch_{N}_official_source_evidence.json`（用于确认批次元信息）
- `configs/miit_new_car_watchlist.csv`

## 字段清洗参考

执行本 Prompt 前，应先参考 01_field_cleaning 的输出结果。如果 01 输出 `skipped_empty_product_list`，则本模块直接进入降级提取模式。

## 检索策略（fallback 优先级）

1. **product_list JSON 全字段检索**：在 `enterprise_name`、`brand`、`product_name`、`product_model` 四个字段中搜索目标品牌关键词。如果 product_list records=0，跳过此步。
2. **extracted text 全文检索**：对疑似字段偏移的记录，回看附件 1 原始文本确认。如果主附件 404，则对 tax catalog 文本进行全文检索。
3. **watchlist CSV 关键词匹配**：使用 watchlist 中定义的品牌关键词逐条匹配。
4. **evidence 文件辅助确认**：确认批次号、附件数量、质量等元信息。
5. **如果来源冲突**：以 product_list + extracted text 交叉验证为准，标记 `conflict_between_sources`。

## source_reliability 可选值

| 值 | 含义 |
|----|------|
| `product_list_verified` | 字段对齐好，直接来自 product_list，无需回看 extracted text |
| `extracted_text_verified` | 通过回看 extracted text 确认字段正确 |
| `tax_catalog_verified` | 来自车船税/购置税目录文本，非完整产品清单，字段可用但范围受限 |
| `conflict_between_sources` | product_list 和 extracted text 冲突，需要人工判断 |
| `low_confidence` | 无法确认，字段偏移严重或文本不可读 |

## 降级模式限制

当 `product_list` 为空（records=0）且进入降级提取模式时：

1. **只能基于 extracted text / tax catalog 做有限提取**，不可假装 product_list 有记录。
2. **source_reliability 应标记为 `extracted_text_verified`、`tax_catalog_verified` 或 `low_confidence`**，不可标记 `product_list_verified`。
3. **不得将 tax catalog 记录等同于完整道路机动车产品清单**。tax catalog 仅包含可享受税收优惠的车型，不代表企业的全部申报产品。
4. **对未发现品牌，必须写"当前可用输入未发现"**，不得写"本批次无该品牌"。因为数据来源不完整，不可做否定判断。
5. 输出表格的"来源"列应注明具体来源（如 "tax catalog text" / "extracted text fallback"），不可笼统写 "product_list"。

## 信息边界约束

所有提取结果受限于公告文件的信息边界。参见 README.md "信息边界 / Evidence Boundary" 章节。

### 产品型号的边界声明

`product_model`（如 CSA6492、BYD6510）是**公告申报型号前缀**，不是上市商品名。不允许：
- 将 CSA6492 直接称为"智己 L6"（即使该型号在往批公告中与智己 L6 相关）
- 将 BYD6510 直接称为"比亚迪海狮 08"
- 从型号前缀推断配置级别（如 LFSHEV3 = 低配、LFSHEV4 = 高配）

### 可提取的信息

每条记录只能提取以下可确认的字段：

| 字段 | 可提取内容 | 示例 |
|------|-----------|------|
| enterprise_name | 企业全称 | 上海汽车集团股份有限公司 |
| brand | 品牌 | 智己 |
| product_name | 公告产品名称（大类） | 插电式增程混合动力运动型乘用车 |
| product_model | 公告型号（前缀） | CSA6492 |
| evidence_level | 信息层级：事实 / 谨慎推断 / 待验证 / 禁止结论 | 事实 |
| source_field | 该信息的原始来源字段 | product_model: "CSA6492" |
| allowed_conclusion | 该字段可做出的最大解释 | "智己增程产品进入公告申报阶段" |
| prohibited_conclusion | 该字段禁止输出的解释 | 商品名、价格、上市时间、续航、电池、电机、尺寸 |

## 输出表格

| 企业 | 品牌 | 产品名称 | 产品型号 | 型号前缀 | 来源 | source_reliability | 字段问题 | 置信度 | evidence_level | source_field | allowed_conclusion | prohibited_conclusion | 待验证事项 |
|------|------|----------|----------|----------|------|--------------------|----------|--------|----------------|--------------|-------------------|----------------------|------------|
| 上海汽车集团股份有限公司 | 智己 | 插电式增程混合动力运动型乘用车 | CSA6492 | CSA6492 | product_list | product_list_verified | 无 | high | 事实 | product_name:"插电式增程混合动力", product_model:"CSA6492" | 智己增程产品进入公告申报阶段 | 不得推断商品名、价格、上市时间、续航、电池、电机、尺寸 | 具体商品名、上市节奏、配置参数 |
| 比亚迪汽车工业有限公司 | 比亚迪 | 插电式混合动力多用途乘用车 | BYD6510 | BYD6510 | product_list | product_list_verified | 无 | high | 事实 | product_name:"插电式混合动力", product_model:"BYD6510" | 比亚迪 PHEV 产品进入公告申报阶段 | 不得推断商品名、价格、上市时间、续航 | 具体车型名称、定价 |
| — | 小鹏 | — | — | — | product_list | conflict_between_sources | field_shift | low | 待验证 | 字段偏移无法确认 | — | — | 需回看 extracted text 确认具体产品 |
| 比亚迪汽车有限公司 | 比亚迪牌 | 比亚迪宋Pro HEV | BYD6476ST6HEV12 | BYD6476 | tax catalog text | tax_catalog_verified | 无 | medium | 谨慎推断 | tax catalog 文本:企业/品牌/型号字段 | 比亚迪宋Pro HEV 进入税收目录 | 不得推断续航、价格、配置变化 | 来源为 tax catalog，非完整产品清单 |

## 重点品牌优先级标记

对于提取出的每条记录，标记 S/A/B/C 优先级：

| 优先级 | 含义 | 判断规则 |
|--------|------|----------|
| **S** | 高度相关、可能有战略信号 | 品牌在我方 watchlist 的 S 级（智己/理想/问界/小米/蔚来/小鹏/极氪）；全新车型或战略版本扩展 |
| **A** | 重点品牌新增产品或重要版本 | 品牌在 watchlist 中；新增高配/低配/增程/纯电版本 |
| **B** | 常规新增或补申报 | 品牌在 watchlist 中但非 S/A 级别；已有车型的常规版本扩展 |
| **C** | 低相关或暂不关注 | 品牌不在 watchlist 中；或为非乘用车（卡车/客车/专用车） |

**降级模式优先级限制**：当 `allowed_analysis_scope` 为 `tax_catalog_fallback_only` 时，不允许标记 S 级优先级。所有记录最高为 A 级，且需标注 "来源受限"。

## 关键要求

1. **大样本品牌只输出代表性记录**，并额外说明总命中数量。例如比亚迪命中 8 条，列出字段对齐好的 3 条，其余简述。
2. **重点品牌要尽可能完整输出**。每个品牌至少列出企业名、产品名称、型号前缀。
3. **不编造 product_list 中没有的字段**。不要输出续航、电池容量、电机功率、尺寸等当前不可获取的信息。
4. **不直接推断上市价格、续航、上市时间**。如果需要推断，必须标注为 "estimate" 并说明推理依据。
5. **对疑似重要信号标记 S/A/B/C 优先级**（降级模式下最高 A 级）。
6. **字段问题列说明**：如果该记录在 01 字段清洗中有问题（如 field_shift），在此列说明具体问题。
7. **降级模式下必须注明数据来源限制**：在输出表格前添加一行说明，如"注意：以下数据来源为 tax catalog，非完整产品清单，不代表企业全部申报。"

## Prompt 模板

```
请从以下 MIIT 产品清单中提取目标品牌 {target_brands} 的所有可识别产品记录。

## product_list JSON 的 records 数组：
{将 product_list JSON 的 records 数组粘贴于此}

## 字段清洗结果（如可用）：
{粘贴 01_field_cleaning 的输出，或以"No prior cleaning available"注明}

## extracted text 片段（用于确认字段偏移的记录，如果无可跳过）：
{粘贴附件 1 原文相关片段}

## 目标品牌列表：
{target_brands}，例如：比亚迪, 智己

## watchlist 品牌完整列表：
智己, 理想, 问界, 小米, 蔚来, 小鹏, 极氪, 阿维塔, 深蓝, 零跑, 腾势, 方程豹, 比亚迪, 特斯拉

## 检索策略：
1. 在 enterprise_name / brand / product_name / product_model 中搜索目标品牌关键词
2. 对疑似字段偏移的记录，使用 extracted text 确认
3. 使用 watchlist CSV 中的品牌+关键词补充检索

## 输出格式：
Markdown 表格，包含：企业, 品牌, 产品名称, 产品型号, 型号前缀, 来源, source_reliability, 字段问题, 置信度, evidence_level, source_field, allowed_conclusion, prohibited_conclusion, 待验证事项

## 优先级标记（在"待验证事项"列后附加一列"优先级"）：
- S：高度相关、可能有战略信号
- A：重点品牌新增产品或重要版本
- B：常规新增或补申报
- C：低相关或暂不关注

## 要求：
1. 大样本品牌（如比亚迪）只列出代表性记录，额外说明总命中数量
2. 不编造 product_list 中没有的字段
3. 不推断上市价格、续航、电池、电机、尺寸、上市时间
4. 如果记录字段偏移严重，标记 source_reliability=low_confidence
5. 如果不同来源冲突，标记 conflict_between_sources
6. product_model 只能标记为"公告型号"，不得映射为上市商品名
7. evidence_level 按以下规则标记：直接从公告结构化字段提取→"事实"；需要回看 extracted text 确认→"谨慎推断"；字段偏移无法确认→"待验证"；属于超纲推断→"禁止结论"
```
