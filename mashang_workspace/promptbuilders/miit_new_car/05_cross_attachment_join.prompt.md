# Prompt 模块 05 — 跨附件字段合并（可选）

## 用途

将主公告（附件1）、车船税目录（附件2）、购置税目录（附件3）按公告型号（product_model）前缀进行合并，获得完整的品牌+商品名+深度参数信息。

**前提条件**：已完成 00 → 01 → 02，已获得三个附件各自的结构化记录。

**适用场景**：当需要同时获取品牌信息（附件1）和深度参数（附件2/3）时使用。

## 角色设定

你是一个汽车行业 MIIT 数据合并分析师。你的职责是将来自不同附件的同一型号记录合并为一条完整记录。

## 输入

- `main_announcement_records`：附件1 主公告的结构化记录（来自 product_list JSON）
- `vehicle_vessel_tax_records`：附件2 车船税目录的记录（来自 extracted text）
- `purchase_tax_records`：附件3 购置税目录的记录（来自 extracted text）

## Join 策略

### Join Key

`product_model`（公告型号前缀）是跨附件合并的核心 join key。

### Join 规则

1. **精确匹配**：product_model 前缀完全一致（如 CSA6492 == CSA6492）。
2. **前缀匹配**：附件3 中的完整型号（如 CSA6492LBEVK）与附件1 中的型号前缀（CSA6492）匹配。
3. **企业名辅助验证**：enterprise_name 应一致，用于确认不是不同企业的巧合同型号。
4. **一对多处理**：一个附件1 型号前缀可能对应附件3 中的多个完整型号（不同电池配置）。保留所有匹配记录。

### Join 优先级

| 优先级 | 匹配条件 | join_confidence |
|--------|----------|-----------------|
| 高 | product_model 前缀 + enterprise_name 均匹配 | high |
| 中 | 仅 product_model 前缀匹配（企业名缺失或不同） | medium |
| 低 | 仅企业名+产品名称模糊匹配 | low |

## 输出字段

| 字段 | 说明 | 来源附件 | 是否必须 |
|------|------|----------|----------|
| enterprise_name | 企业全称 | 附件1/2/3 | 必须 |
| brand | 品牌/商标 | 附件1/2 | 必须（附件3 不提供） |
| product_category | 产品大类名称 | 附件1/3 | 必须 |
| generic_model_name | 通用商品名 | 附件2/3 | 可选（仅税收目录有） |
| product_model | 公告型号（前缀） | 附件1/2/3 | 必须，join key |
| energy_type | 能源类型（BEV/PHEV/EREV/FCV） | 附件1 | 必须 |
| pure_ev_range | PHEV 纯电续航(km) | 附件2 | 可选 |
| cltc_range | CLTC 续航(km) | 附件3 | 可选 |
| battery_energy_kwh | 电池能量(kWh) | 附件2/3 | 可选 |
| battery_weight_kg | 电池质量(kg) | 附件2/3 | 可选 |
| curb_weight_kg | 整备质量(kg) | 附件2/3 | 可选 |
| fuel_consumption | 燃料消耗量(L/100km) | 附件2 | 可选（仅 PHEV） |
| displacement_ml | 排量(ml) | 附件2 | 可选 |
| source_attachments | 该记录来自哪些附件 | — | 必须 |
| join_confidence | 合并置信度（high/medium/low） | — | 必须 |
| fields_needing_validation | 需要验证的字段列表 | — | 必须 |

## 输出表格

| enterprise_name | brand | product_category | generic_model_name | product_model | energy_type | pure_ev_range(km) | cltc_range(km) | battery_energy(kWh) | battery_weight(kg) | curb_weight(kg) | fuel_consumption(L/100km) | displacement(ml) | source_attachments | join_confidence | fields_needing_validation |
|-----------------|-------|-----------------|-------------------|---------------|-------------|-------------------|----------------|---------------------|-------------------|-----------------|--------------------------|-----------------|--------------------|-----------------|--------------------------|
| 上海汽车集团股份有限公司 | 智己 | 纯电动运动型乘用车 | 智己L6 | CSA6492 | BEV | — | 710(CLTC) | 82.732 | 571.3 | 2080 | — | — | 附件1 + 附件3 | high | brand 从附件1 获取，CLTC 和电池从附件3 获取 |
| 比亚迪汽车工业有限公司 | 比亚迪 | 插电式混合动力多用途乘用车 | 海狮06 | BYD6480 | PHEV | 205 | — | 38.029 | 280 | 1990 | 4.65 | 1498 | 附件1 + 附件2 | high | 续航为 PHEV 纯电模式，非 CLTC |
| — | — | — | — | BYD6510 | PHEV | — | — | — | — | — | — | — | 仅附件1 | low | 深度参数需等后续批次税收目录出现 |

## Join 后信息边界

### 可确认的信息（合并后）

| 信息 | 条件 |
|------|------|
| enterprise_name + brand | 附件1 或 附件2 存在 |
| product_category | 附件1 或 附件3 存在 |
| generic_model_name | 附件2 或 附件3 存在 |
| product_model | 任何附件存在 |
| energy_type | 附件1 存在 |
| 续航、电池、整备质量 | 附件2 或 附件3 存在 |
| 燃料消耗量、排量 | 附件2 存在 |

### 仍禁止输出的信息

价格、上市时间、智驾版本、配置高低配、市场威胁强度——所有附件均不提供。

### 跨附件 join 的局限

1. **同一型号前缀可能对应多个配置**。附件3 中可能有多条记录（如 82.732kWh 和 75.616kWh），需保留多条。
2. **部分型号可能只在单一附件中出现**。例如仅出现在附件1 的主公告中但未进入税收目录，则无法获取深度参数。
3. **附件2 和附件3 的覆盖范围不同**。附件2 包含节能型汽车+PHEV；附件3 包含 BEV。同一型号可能只出现在其中一个税收目录中。

## Prompt 模板

```
请将以下三个 MIIT 附件的记录按公告型号进行合并。

## 附件1 主公告记录（main_announcement_records）：
{粘贴 product_list JSON 的 records 数组，或从 02 模块提取的目标品牌记录}

## 附件2 车船税目录记录（vehicle_vessel_tax_records）：
{粘贴从附件2 extracted text 中提取的记录}

## 附件3 购置税目录记录（purchase_tax_records）：
{粘贴从附件3 extracted text 中提取的记录}

## Join 策略：
1. 使用 product_model 前缀作为 join key
2. enterprise_name 作为辅助验证
3. 保留一对多（一个前缀对应多个完整型号）

## 输出格式：
Markdown 表格，包含：enterprise_name, brand, product_category, generic_model_name, product_model, energy_type, pure_ev_range(km), cltc_range(km), battery_energy(kWh), battery_weight(kg), curb_weight(kg), fuel_consumption(L/100km), displacement(ml), source_attachments, join_confidence, fields_needing_validation

## 要求：
1. 每个产品型号一行，同一型号多条税收记录保留多行
2. 缺失的字段留空或填 "—"
3. 所有字段必须标注来源附件
4. join_confidence 按匹配条件判断（high/medium/low）
5. 如果某个型号仅出现在单一的附件中，标注字段缺失原因（如"未进入税收目录"）
6. 仍禁止输出价格、上市时间、智驾版本、配置高低配、市场威胁强度
```
