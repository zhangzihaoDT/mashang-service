# Prompt 模块 04 — MIIT 业务情报简报输出

## 用途

将 00（资产检查）、01（字段清洗）、02（目标品牌提取）、03（产品信号解释）的输出结果，整合为一份面向管理层/产品规划/情报跟踪的 MIIT 业务情报简报。

**前提条件**：已完成 00 → 01 → 02 → 03，获得全部四个模块的输出。

## 角色设定

你是一个汽车行业 MIIT 情报分析师。你的职责是将多个 Prompt 模块的分析结果整合为一份结构清晰、可交付的业务简报。

## 报告标题模板

```
# 第 {batch_no} 批 MIIT 目标品牌信息提取简报：{target_brands}
```

## 报告结构

### 1. 简报说明

- 本报告基于 MIIT Promptbuilder Prompt Pack v0.2 生成。
- 使用 Prompt 模块：00（资产检查）→ 01（字段清洗）→ 02（目标品牌提取）→ 03（产品信号解释）→ 04（简报输出）。
- 本报告仅为业务情报辅助，**不代表最终业务结论**。
- MIIT 阶段只能判断**潜在产品信号**，不能等同于上市后的真实竞争威胁。
- 所有无法确认的信息均标记为 **待验证** 或 **low confidence**。
- 如果本批次进入降级模式（degraded_mode=true），详见"输入资产降级说明"章节。

### 2. 输入资产检查

从 00_asset_check 模块输出复制：

| 资产 | 路径 | 是否存在 | 用途 | 备注 |
|------|------|----------|------|------|
| evidence JSON | `outputs/miit_new_car/evidence/batch_{N}_official_source_evidence.json` | | | |
| product_list JSON | `outputs/miit_new_car/product_list/batch_{N}_product_list.json` | | | |
| 附件文本抽取 | `outputs/miit_new_car/extracted/batch_{N}_attachment_text.json` | | | |
| 附件 1 原文 | `outputs/miit_new_car/extracted/text/batch_{N}/{hash}.txt` | | | |
| Watchlist CSV | `configs/miit_new_car_watchlist.csv` | | | |

### 3. 批次扫描结果

| 字段 | 结果 |
|------|------|
| batch_no | {batch_no} |
| status | official / publicity |
| publish_date | 从 detail_url 提取 |
| product_record_count | 从 evidence 提取 |
| enterprise_count | 从 evidence 提取 |
| attachment_count | 从 evidence 提取 |
| quality | usable / partial / unusable |
| key_observation | 一句话观察 |

### 4. 输入资产降级说明

**仅当 00_asset_check 输出 `degraded_mode=true` 时填写本节，否则跳过。**

从 00_asset_check 模块的 asset_status 和 blocking_reason 复制：

| 字段 | 值 |
|------|----|
| asset_status | complete / partial / empty / blocked |
| degraded_mode | true / false |
| batch_status | official / publicity |
| blocking_reason | 文本说明 |
| allowed_analysis_scope | 当前资产允许的分析范围 |
| prohibited_conclusions | 当前资产禁止输出的结论类型 |

**当前结论可用于**：
- 文本说明：例如"基于 tax catalog 做品牌存在性判断"。

**当前结论不能用于**：
- 文本说明：例如"不能用于输出完整车型判断、不能用于推断上市时间"。

**是否建议 official 状态后复跑**：
- 是 / 否（如果批次为 publicity，应建议复跑）

### 5. 目标品牌提取结果

按品牌输出。从 02_target_brand_extract 模块输出整理。

| 企业 | 品牌 | 产品名称 | 产品型号 | 型号前缀 | 来源 | source_reliability | 字段问题 | 置信度 | 待验证事项 | 优先级 |
|------|------|----------|----------|----------|------|--------------------|----------|--------|------------|--------|
| | | | | | | | | | | |

**品牌统计**：
- 比亚迪：X 条记录（其中字段对齐好 X 条，字段偏移 X 条；降级模式下需注明来源）
- 智己：X 条记录（降级模式下需注明是否基于 tax catalog fallback）

### 6. 字段清洗与可信度校验

从 01_field_cleaning 模块输出整理。

| 品牌 | 原始记录问题 | issue_type | 清洗建议 | 是否需要回看 extracted text | 理由 |
|------|-------------|------------|----------|----------------------------|------|
| | | | | | |

### 7. 品牌级事实 / 推断 / 待验证

从 03_product_signal_interpretation 模块输出整理。

#### 品牌：{品牌名称}

| 层级 | 内容 |
|------|------|
| **事实（F）** | |
| **合理推断（R）** | |
| **待验证假设（H）** | |

#### 品牌：{第二个品牌名称}

| 层级 | 内容 |
|------|------|
| **事实（F）** | |
| **合理推断（R）** | |
| **待验证假设（H）** | |

### 8. 重点车型/型号观察清单

| 优先级 | 品牌 | 企业 | 产品名称 | 产品型号/前缀 | 关注理由 | 后续验证事项 | 来源说明 |
|--------|------|------|----------|---------------|----------|-------------|----------|
| S | | | | | | | |
| A | | | | | | | |
| B | | | | | | | |
| C | | | | | | | |

**降级模式限制**：当 `degraded_mode=true` 时，重点观察清单中不允许出现 S 级。所有记录标注 "观察信号" 并注明来源（如 "来源：tax catalog"）。

### 9. 结论摘要

输出三个版本：

**管理层版**：
一句话说明本批次对目标品牌的关键发现和战略建议。降级模式下需附加"本结论基于降级数据"的免责说明。

**产品规划版**：
从产品线的角度说明本批次中目标品牌的产品变化和趋势。降级模式下需标注"观察信号，待正式 product_list 确认"。

**情报跟踪版**：
说明需要继续跟踪的具体事项和信号。降级模式下需建议在 official 状态后复跑。

### 10. 后续 7/30/90 天追踪清单

| 时间窗口 | 追踪事项 | 触发信号 | 使用场景 |
|----------|----------|----------|----------|
| 7 天 | | | |
| 30 天 | | | |
| 90 天 | | | |

### 11. Promptbuilder 运行问题清单

| 问题 | 类型 | 影响 | 建议 |
|------|------|------|------|
| | | | |

## Prompt 模板

```
请基于以下四个 Prompt 模块的输出结果，整合为一份 MIIT 业务情报简报。

## 00 输入资产检查结果：
{粘贴 00_asset_check 的输出}

## 01 字段清洗结果：
{粘贴 01_field_cleaning 的输出}

## 02 目标品牌提取结果：
{粘贴 02_target_brand_extract 的输出}

## 03 产品信号解释结果：
{粘贴 03_product_signal_interpretation 的输出}

## 目标品牌：
{target_brands}

## 简报标题：
第 {batch_no} 批 MIIT 目标品牌信息提取简报：{target_brands}

## 报告结构要求：
{粘贴上方"报告结构"的完整内容}

## 降级模式约束：
{如果 00 模块输出 degraded_mode=true，补充以下约束}
- 所有结论必须标注数据来源限制（如 "来源：tax catalog，非完整产品清单"）
- 禁止输出 S 级战略判断
- 禁止将 tax catalog 记录等同于完整道路机动车产品清单
- 建议在 official 状态后复跑

## 输出约束：
1. 所有结论必须标注来源
2. 涉及价格、上市时间、配置等需标注 "estimate" 或 "待确认"
3. 使用 Markdown 格式
4. 无法确认的信息标记为"待验证"
5. 本报告仅为业务情报辅助，不代表最终业务结论
6. 禁止编造任何来自 MIIT product_list 或 extracted text 之外的字段信息
```
