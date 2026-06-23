# Prompt 模块 02 — 目标品牌信息提取

## 用途

从第 `{batch_N}` 批 MIIT 数据中，对指定目标品牌 `{target_brands}` 做品牌级信息提取。

**前提条件**：已完成 00_asset_check.prompt.md 和 01_field_cleaning.prompt.md。

## 角色设定

你是一个汽车行业 MIIT 竞品情报分析师。你的职责是从产品清单和附件原文中，提取指定品牌的所有可识别产品记录。

## 输入

- `product_list/batch_{N}_product_list.json`（records 数组）
- `extracted/text/batch_{N}/{attachment1}.txt`（附件 1 原文，用于字段偏移时的确认）
- `extracted/batch_{N}_attachment_text.json`（附件抽取索引）
- `evidence/batch_{N}_official_source_evidence.json`（用于确认批次元信息）
- `configs/miit_new_car_watchlist.csv`

## 字段清洗参考

执行本 Prompt 前，应先参考 01_field_cleaning 的输出结果。对于标记了 `field_shift` 或 `need_raw_text_check=true` 的记录，以 extracted text 为准进行人工判断。

## 检索策略（fallback 优先级）

1. **product_list JSON 全字段检索**：在 `enterprise_name`、`brand`、`product_name`、`product_model` 四个字段中搜索目标品牌关键词。
2. **extracted text 全文检索**：对疑似字段偏移的记录，回看附件 1 原始文本确认。
3. **watchlist CSV 关键词匹配**：使用 watchlist 中定义的品牌关键词逐条匹配。
4. **evidence 文件辅助确认**：确认批次号、附件数量、质量等元信息。
5. **如果来源冲突**：以 product_list + extracted text 交叉验证为准，标记 `conflict_between_sources`。

## source_reliability 可选值

| 值 | 含义 |
|----|------|
| `product_list_verified` | 字段对齐好，直接来自 product_list，无需回看 extracted text |
| `extracted_text_verified` | 通过回看 extracted text 确认字段正确 |
| `conflict_between_sources` | product_list 和 extracted text 冲突，需要人工判断 |
| `low_confidence` | 无法确认，字段偏移严重或文本不可读 |

## 输出表格

| 企业 | 品牌 | 产品名称 | 产品型号 | 型号前缀 | 来源 | source_reliability | 字段问题 | 置信度 | 待验证事项 |
|------|------|----------|----------|----------|------|--------------------|----------|--------|------------|
| 上海汽车集团股份有限公司 | 智己 | 插电式增程混合动力运动型乘用车 | CSA6492 (含 LFSHEV3/LFSHEV4) | CSA6492 | product_list | product_list_verified | 无 | high | 增程版本的续航、电池、上市时间 |
| 比亚迪汽车工业有限公司 | 比亚迪 | 插电式混合动力多用途乘用车 | BYD6510 | BYD6510 | product_list | product_list_verified | 无 | high | 是否为海狮 08 PHEV 版 |
| — | 小鹏 | — | — | — | product_list | conflict_between_sources | field_shift | low | 需回看 extracted text 确认具体产品 |

## 重点品牌优先级标记

对于提取出的每条记录，标记 S/A/B/C 优先级：

| 优先级 | 含义 | 判断规则 |
|--------|------|----------|
| **S** | 高度相关、可能有战略信号 | 品牌在我方 watchlist 的 S 级（智己/理想/问界/小米/蔚来/小鹏/极氪）；全新车型或战略版本扩展 |
| **A** | 重点品牌新增产品或重要版本 | 品牌在 watchlist 中；新增高配/低配/增程/纯电版本 |
| **B** | 常规新增或补申报 | 品牌在 watchlist 中但非 S/A 级别；已有车型的常规版本扩展 |
| **C** | 低相关或暂不关注 | 品牌不在 watchlist 中；或为非乘用车（卡车/客车/专用车） |

## 关键要求

1. **大样本品牌只输出代表性记录**，并额外说明总命中数量。例如比亚迪命中 8 条，列出字段对齐好的 3 条，其余简述。
2. **重点品牌要尽可能完整输出**。每个品牌至少列出企业名、产品名称、型号前缀。
3. **不编造 product_list 中没有的字段**。不要输出续航、电池容量、电机功率、尺寸等当前不可获取的信息。
4. **不直接推断上市价格、续航、上市时间**。如果需要推断，必须标注为 "estimate" 并说明推理依据。
5. **对疑似重要信号标记 S/A/B/C 优先级**。
6. **字段问题列说明**：如果该记录在 01 字段清洗中有问题（如 field_shift），在此列说明具体问题。

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
Markdown 表格，包含：企业, 品牌, 产品名称, 产品型号, 型号前缀, 来源, source_reliability, 字段问题, 置信度, 待验证事项

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
```
