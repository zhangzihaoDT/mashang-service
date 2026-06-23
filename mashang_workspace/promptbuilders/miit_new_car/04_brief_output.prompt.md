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

- 本报告基于 MIIT Promptbuilder Prompt Pack v0.3 生成。
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

### 4. 信息边界与禁止结论

**每份简报必须输出本节**。从 03_product_signal_interpretation 模块的信息边界声明和禁止结论示例复制。

#### 本次可确认的信息

| 信息类别 | 内容 | 来源字段 |
|----------|------|----------|
| 批次元信息 | batch_no, status, publish_date | evidence |
| 企业/品牌 | enterprise_name, brand | product_list 或 extracted text |
| 产品名称（大类） | product_name（如"插电式增程混合动力运动型乘用车"） | product_list |
| 公告型号 | product_model 前缀（如 CSA6492） | product_list |
| 能源类型 | BEV / PHEV / EREV / FCV（从 product_name 提取） | product_list |

#### 本次只能谨慎推断的信息

| 推断内容 | 事实依据 | 待验证项 |
|----------|----------|----------|
| 能源路线扩展 | 同一品牌首次出现新能源 / 增程版本 | 具体商品名、上市节奏 |
| 型号连续信号 | 型号前缀在连续批次中出现 | 是否为同一车型的持续申报 |
| 软件或功能升级 | 同一型号前缀下后缀变化 | 具体配置变更内容 |

#### 本次必须外部验证的信息

| 信息 | 外部来源 | 预期获取方式 |
|------|----------|-------------|
| 具体商品名 | 官网、发布会、媒体 | 上市发布会、品牌官网 |
| 价格 | 官网、发布会 | 上市发布会定价公布 |
| 上市时间 | 官网、媒体 | 官方上市公告 |
| 续航 / 电池 / 电机 / 尺寸 | 工信部能耗目录、碳排目录 | 税收目录结构化或人工查阅 |
| 智驾版本 / 配置高低配 | 官网、发布会 | 配置表发布 |

#### 本次禁止输出的信息

| 禁止输出 | 理由 |
|----------|------|
| 将 product_model 映射为商品名（如 CSA6492 → "智己 L6"），除非附件3 提供了 generic_model_name | product_model 为公告型号，商品名需来自附件3 |
| 推断价格（如"预计 25-35 万"） | 所有附件均不包含定价信息 |
| 推断上市时间（如"预计 Q3 2026"） | 申报到上市有 3-12 个月延迟 |
| 推断智驾版本（如"搭载城市 NOA"） | MIIT 不包含智驾相关信息 |
| 推断配置高低配 | 同一型号前缀可对应多个配置 |
| 推断市场威胁强度（如"将影响 LS8 销量"） | MIIT 无法评估市场影响 |

### 5. 分附件证据来源说明

**每份简报必须输出本节**，说明当前分析使用了哪些附件、每个附件支持哪些字段。

#### 使用到的附件

| 附件 | 文件名 | 类型 | 是否可用于提取字段 |
|------|--------|------|-------------------|
| 附件1 主公告 | {filename}.doc | main_announcement | 是（企业名/品牌/产品大类/公告型号） |
| 附件2 车船税目录 | {filename}.doc | vehicle_vessel_tax_catalog | 是/否（仅当存在且可解析） |
| 附件3 购置税目录 | {filename}.doc | purchase_tax_catalog | 是/否（仅当存在且可解析） |

#### 各附件支持的字段

| 来源附件 | 支持的字段 | 说明 |
|----------|-----------|------|
| 附件1 main_announcement | enterprise_name, directory_no, brand, product_name, product_model, new_product/change_extension | 核心字段，所有记录均有 |
| 附件2 vehicle_vessel_tax_catalog | enterprise_name, brand, generic_model_name, product_model, pure_ev_range(PHEV), battery_energy, battery_weight, curb_weight, fuel_consumption, displacement | 仅 PHEV 车型有续航，仅节能型有燃料消耗量 |
| 附件3 purchase_tax_catalog | enterprise_name, generic_model_name, product_name, product_model, cltc_range, battery_energy, battery_weight, curb_weight | 仅 BEV 车型有 CLTC 续航 |

#### 各品牌信息按附件来源分布

| 品牌 | 企业名来源 | 产品大类来源 | 商品名来源 | 深度参数来源 | 缺失字段 |
|------|-----------|-------------|-----------|-------------|----------|
| 比亚迪 | 附件1/2/3 | 附件1/3 | 附件2/3 | 附件2/3 | — |
| 智己 | 附件1/3 | 附件1/3 | 附件3 | 附件3 | 附件2 中未出现（需跨批次跟踪） |

#### 跨附件 join 情况

| product_model | 来源附件 | join 字段 | join 后新增字段 |
|---------------|----------|-----------|----------------|
| CSA6492 | 附件1 + 附件3 | product_model | generic_model_name, cltc_range, battery_energy, curb_weight |
| BYD6510 | 附件1（附件2/3 未出现） | — | 无法获取深度参数，需等后续批次税收目录 |

### 6. 输入资产降级说明

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

### 7. 目标品牌提取结果

按品牌输出。从 02_target_brand_extract 模块输出整理。

| 企业 | 品牌 | 产品名称 | 产品型号 | 型号前缀 | source_attachment_type | source_reliability | 字段问题 | 置信度 | evidence_level | source_field | source_supported_fields | source_join_key | allowed_conclusion | prohibited_conclusion | 待验证事项 | 优先级 |
|------|------|----------|----------|----------|------------------------|--------------------|----------|--------|----------------|--------------|------------------------|-----------------|-------------------|----------------------|------------|--------|
| | | | | | | | | | | | | | | | | |

**品牌统计**：
- 比亚迪：X 条记录（其中字段对齐好 X 条，字段偏移 X 条；降级模式下需注明来源；深度参数来自附件 X）
- 智己：X 条记录（降级模式下需注明是否基于 tax catalog fallback；商品名和深度参数来源）

### 8. 字段清洗与可信度校验

从 01_field_cleaning 模块输出整理。

| 品牌 | 原始记录问题 | issue_type | 清洗建议 | 是否需要回看 extracted text | 理由 |
|------|-------------|------------|----------|----------------------------|------|
| | | | | | |

### 9. 品牌级事实 / 谨慎推断 / 待验证 / 禁止结论（按附件来源标注）

从 03_product_signal_interpretation 模块输出整理。

#### 品牌：{品牌名称}

| 层级 | 内容 |
|------|------|
| **事实（F）** | |
| **谨慎推断（R）** | |
| **待验证假设（H）** | |
| **禁止结论（P）** | |

#### 品牌：{第二个品牌名称}

| 层级 | 内容 |
|------|------|
| **事实（F）** | |
| **谨慎推断（R）** | |
| **待验证假设（H）** | |
| **禁止结论（P）** | |

### 10. 重点车型/型号观察清单

| 优先级 | 品牌 | 企业 | 产品名称 | 产品型号/前缀 | 关注理由 | 后续验证事项 | source_attachment_type | source_join_key | parameter_source | evidence_level |
|--------|------|------|----------|---------------|----------|-------------|------------------------|-----------------|-----------------|----------------|
| S | | | | | | | | | | |
| A | | | | | | | | | | |
| B | | | | | | | | | | |
| C | | | | | | | | | | |

**降级模式限制**：当 `degraded_mode=true` 时，重点观察清单中不允许出现 S 级。所有记录标注 "观察信号" 并注明来源（如 "来源：tax catalog"）。

### 11. 结论摘要

输出三个版本，每个版本必须附带信息边界声明：

**管理层版**：
一句话说明本批次对目标品牌的关键发现和战略建议。降级模式下需附加"本结论基于降级数据"的免责说明。
信息边界：本结论仅基于 MIIT 公告信号，不包含价格、上市时间、配置等商品信息。

**产品规划版**：
从产品线的角度说明本批次中目标品牌的产品变化和趋势。降级模式下需标注"观察信号，待正式 product_list 确认"。
信息边界：型号前缀为公告型号，不映射商品名；能源类型来自产品名称大类。

**情报跟踪版**：
说明需要继续跟踪的具体事项和信号。降级模式下需建议在 official 状态后复跑。
信息边界：跟踪事项限于公告信号，不包括价格、销量、市场反应。

### 12. 后续 7/30/90 天追踪清单

| 时间窗口 | 追踪事项 | 触发信号 | 使用场景 |
|----------|----------|----------|----------|
| 7 天 | | | |
| 30 天 | | | |
| 90 天 | | | |

### 13. Promptbuilder 运行问题清单

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

## 分附件证据边界约束：
- 附件1（main_announcement）只能做公告身份和产品路线判断
- 附件2（vehicle_vessel_tax_catalog）可提供 PHEV 续航、电池、排量、燃料消耗量
- 附件3（purchase_tax_catalog）可提供 CLTC 续航、电池、整备质量
- 所有来自附件2/3 的深度参数必须标注来源附件
- 跨附件合并使用 product_model 作为 join key

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
